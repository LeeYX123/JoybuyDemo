"""Record-level field rules, listing-card checks and the price guard.

These tests target the layer that sits between the parsers and staging:
the parsers may still return a plausible-looking record after a site
change, so the rules are what stops junk from being imported.
"""

import json
import sys
import tempfile
from pathlib import Path

CRAWLER_DIR = Path(__file__).resolve().parents[3] / "crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

from django.test import SimpleTestCase, TestCase  # noqa: E402
from joybuy_crawler.quality import (  # noqa: E402
    PriceDistributionGuard,
    RuleOutcome,
    Violation,
    apply_product_rules,
    check_listing_entry,
    parse_price,
)

from crawler_control.models import CrawlRunEvent  # noqa: E402
from crawler_control.tests.test_crawler_control_domain import (  # noqa: E402
    CrawlerControlTestBase,
)


def good_payload(**overrides):
    payload = {
        "source_id": "10001234",
        "title": "Wireless Noise Cancelling Headphones",
        "currency": "GBP",
        "current_price": "129.99",
        "skus": [{"source_id": "10001234", "price": "129.99", "specs": []}],
        "image_urls": [
            "https://cdn.joy-sourcing.com/product/a.webp",
            "https://cdn.joy-sourcing.com/product/b.webp",
        ],
        "joybuy": {"priceInfo": {"crossOffPrice": "129.99", "mainPrice": "99.99"}},
    }
    payload.update(overrides)
    return payload


class PriceParsingTests(SimpleTestCase):
    def test_accepts_the_shapes_the_parsers_produce(self):
        self.assertEqual(str(parse_price("12.99")), "12.99")
        self.assertEqual(str(parse_price("£12.99")), "12.99")
        self.assertEqual(str(parse_price("1,299.00")), "1299.00")
        self.assertEqual(str(parse_price(1299.0)), "1299.0")

    def test_rejects_ambiguous_or_non_numeric_values(self):
        for raw in (None, "", "N/A", "from 9.99", "9.99 - 12.99", True):
            self.assertIsNone(parse_price(raw), raw)


class ProductRuleTests(SimpleTestCase):
    def test_a_clean_product_has_no_violations(self):
        payload, outcome = apply_product_rules(
            good_payload(), source_url="https://www.joybuy.co.uk/dp/slug/10001234"
        )
        self.assertFalse(outcome.fatal)
        self.assertEqual(outcome.violations, [])
        self.assertEqual(payload["rule_warnings"], [])

    def test_the_input_payload_is_never_mutated(self):
        original = good_payload(image_urls=["https://evil.example.com/a.webp"])
        snapshot = json.dumps(original, sort_keys=True)
        apply_product_rules(original, source_url="https://www.joybuy.co.uk/dp/s/1")
        self.assertEqual(json.dumps(original, sort_keys=True), snapshot)

    def test_short_title_is_fatal(self):
        _, outcome = apply_product_rules(good_payload(title="Buy"))
        self.assertTrue(outcome.fatal)
        self.assertIn("TITLE_TOO_SHORT", outcome.codes)

    def test_zero_price_is_fatal_rather_than_silently_imported(self):
        _, outcome = apply_product_rules(good_payload(current_price="0"))
        self.assertTrue(outcome.fatal)
        self.assertIn("PRICE_NOT_POSITIVE", outcome.codes)

    def test_unparseable_price_is_fatal(self):
        _, outcome = apply_product_rules(good_payload(current_price="Ask seller"))
        self.assertTrue(outcome.fatal)
        self.assertIn("PRICE_MISSING", outcome.codes)

    def test_absurd_price_is_fatal(self):
        _, outcome = apply_product_rules(good_payload(current_price="9876543"))
        self.assertTrue(outcome.fatal)
        self.assertIn("PRICE_OUT_OF_RANGE", outcome.codes)

    def test_currency_is_normalised_and_validated(self):
        payload, outcome = apply_product_rules(good_payload(currency="gbp"))
        self.assertFalse(outcome.fatal)
        self.assertEqual(payload["currency"], "GBP")
        _, bad = apply_product_rules(good_payload(currency="pounds"))
        self.assertTrue(bad.fatal)
        self.assertIn("CURRENCY_INVALID", bad.codes)

    def test_missing_skus_is_fatal(self):
        _, outcome = apply_product_rules(good_payload(skus=[]))
        self.assertTrue(outcome.fatal)
        self.assertIn("SKUS_MISSING", outcome.codes)

    def test_off_host_source_url_is_fatal(self):
        _, outcome = apply_product_rules(
            good_payload(), source_url="https://evil.example.com/dp/slug/1"
        )
        self.assertTrue(outcome.fatal)
        self.assertIn("SOURCE_URL_HOST_INVALID", outcome.codes)

    def test_non_product_url_is_fatal(self):
        _, outcome = apply_product_rules(
            good_payload(), source_url="https://www.joybuy.co.uk/login"
        )
        self.assertTrue(outcome.fatal)
        self.assertIn("SOURCE_URL_NOT_PRODUCT", outcome.codes)

    def test_off_host_images_are_dropped_from_the_cleaned_payload(self):
        payload, outcome = apply_product_rules(
            good_payload(
                image_urls=[
                    "https://cdn.joy-sourcing.com/product/a.webp",
                    "https://evil.example.com/tracker.webp",
                ]
            )
        )
        self.assertFalse(outcome.fatal)
        self.assertEqual(payload["image_urls"], ["https://cdn.joy-sourcing.com/product/a.webp"])
        self.assertIn("IMAGE_HOST_DROPPED", outcome.codes)

    def test_swapped_price_selectors_are_flagged(self):
        payload = good_payload(
            current_price="79.99",
            joybuy={"priceInfo": {"crossOffPrice": "79.99", "mainPrice": "99.99"}},
        )
        _, outcome = apply_product_rules(payload)
        self.assertFalse(outcome.fatal)
        self.assertIn("PRICE_INVERSION", outcome.codes)

    def test_bad_sku_price_is_a_warning_not_a_rejection(self):
        payload = good_payload(
            skus=[
                {"source_id": "10001234", "price": "129.99", "specs": []},
                {"source_id": "10001235", "price": None, "specs": []},
            ]
        )
        cleaned, outcome = apply_product_rules(payload)
        self.assertFalse(outcome.fatal)
        self.assertIn("SKU_PRICE_INVALID", outcome.codes)
        self.assertEqual(cleaned["rule_warnings"], ["SKU_PRICE_INVALID"])


class ListingCardTests(SimpleTestCase):
    def test_real_card_passes(self):
        outcome = check_listing_entry(
            title="Ninja Air Fryer 7.6L",
            source_url="https://www.joybuy.co.uk/dp/ninja-air-fryer/10001234",
        )
        self.assertFalse(outcome.fatal)

    def test_advert_tile_without_title_is_rejected(self):
        outcome = check_listing_entry(
            title=" Ad ", source_url="https://www.joybuy.co.uk/dp/promo/999"
        )
        self.assertTrue(outcome.fatal)
        self.assertIn("LISTING_TITLE_TOO_SHORT", outcome.codes)

    def test_sponsored_card_is_rejected(self):
        outcome = check_listing_entry(
            title="Sponsored: Top picks for you",
            source_url="https://www.joybuy.co.uk/dp/promo/999",
        )
        self.assertTrue(outcome.fatal)
        self.assertIn("LISTING_PROMO_CARD", outcome.codes)

    def test_card_without_product_id_is_rejected(self):
        outcome = check_listing_entry(
            title="Some product", source_url="https://www.joybuy.co.uk/s?k=cats"
        )
        self.assertTrue(outcome.fatal)
        self.assertIn("LISTING_PRODUCT_ID_MISSING", outcome.codes)


class PriceGuardTests(SimpleTestCase):
    def test_small_runs_never_alarm(self):
        guard = PriceDistributionGuard(min_samples=3)
        guard.observe(good_payload(current_price="0"))
        guard.observe(good_payload(current_price="0"))
        self.assertIsNone(guard.verdict())

    def test_missing_prices_across_the_run_raise_an_error(self):
        guard = PriceDistributionGuard(min_samples=3)
        for _ in range(3):
            guard.observe(good_payload(current_price=None))
        verdict = guard.verdict()
        self.assertEqual(verdict["code"], "PRICE_ANOMALY_MISSING")
        self.assertEqual(verdict["level"], "ERROR")

    def test_one_shared_price_across_the_run_is_suspicious(self):
        guard = PriceDistributionGuard(min_samples=3)
        for _ in range(4):
            guard.observe(good_payload(current_price="9.99"))
        verdict = guard.verdict()
        self.assertEqual(verdict["code"], "PRICE_ANOMALY_UNIFORM")
        self.assertEqual(verdict["level"], "WARNING")

    def test_a_normal_price_spread_is_silent(self):
        guard = PriceDistributionGuard(min_samples=3)
        for price in ("9.99", "129.99", "45.00"):
            guard.observe(good_payload(current_price=price))
        self.assertIsNone(guard.verdict())


class OutcomeReportingTests(SimpleTestCase):
    def test_summary_lists_every_violation_with_its_severity(self):
        outcome = RuleOutcome()
        outcome.add("A", "title", "标题过短", fatal=True)
        outcome.add("B", "image_urls", "已剔除", fatal=False)
        summary = outcome.summary()
        # 文案面向运维，中文输出；事件码保持英文常量便于检索。
        self.assertIn("[A] title：标题过短（致命）", summary)
        self.assertIn("[B] image_urls：已剔除（警告）", summary)
        self.assertTrue(outcome.fatal)
        self.assertEqual([item.code for item in outcome.warnings], ["B"])
        self.assertIsInstance(outcome.violations[0], Violation)


class RecordRulePipelineTests(CrawlerControlTestBase):
    """The pipeline is the only place where a fatal rule can stop a row."""

    class FakeSpider:
        class Logger:
            def warning(self, *args, **kwargs):
                pass

            def info(self, *args, **kwargs):
                pass

        def __init__(self, run):
            self.run = run
            self.logger = self.Logger()

    def setUp(self):
        super().setUp()
        self.make_account()
        from crawler_control.services import start_run

        self.run = start_run(self.make_job(name="Rule pipeline job"))
        self.spider = self.FakeSpider(self.run)

    def build_pipeline(self):
        from joybuy_crawler.pipelines import RecordRulePipeline

        pipeline = RecordRulePipeline()
        pipeline.open_spider(self.spider)
        return pipeline

    def test_fatal_record_is_dropped_before_staging(self):
        from scrapy.exceptions import DropItem

        pipeline = self.build_pipeline()
        with self.assertRaises(DropItem):
            pipeline.process_item(
                {
                    "type": "product",
                    "payload": good_payload(current_price="0"),
                    "source_url": "https://www.joybuy.co.uk/dp/slug/10001234",
                },
                self.spider,
            )
        self.run.refresh_from_db()
        self.assertEqual(self.run.failed_count, 1)
        self.assertEqual(self.run.succeeded_count, 0)
        event = CrawlRunEvent.objects.get(run=self.run, code="RECORD_REJECTED")
        self.assertEqual(event.level, "ERROR")
        self.assertIn("PRICE_NOT_POSITIVE", event.message)

    def test_warning_record_continues_with_its_flags(self):
        pipeline = self.build_pipeline()
        item = pipeline.process_item(
            {
                "type": "product",
                "payload": good_payload(
                    image_urls=["https://evil.example.com/a.webp"],
                ),
                "source_url": "https://www.joybuy.co.uk/dp/slug/10001234",
            },
            self.spider,
        )
        self.assertEqual(item["payload"]["rule_warnings"], ["IMAGE_HOST_DROPPED"])
        self.assertTrue(CrawlRunEvent.objects.filter(run=self.run, code="RECORD_FLAGGED").exists())

    def test_run_level_anomaly_is_written_when_the_spider_closes(self):
        """The "every price came back empty" case must surface even though
        each individual record was already rejected as fatal."""

        from scrapy.exceptions import DropItem

        pipeline = self.build_pipeline()
        for index in range(3):
            with self.assertRaises(DropItem):
                pipeline.process_item(
                    {
                        "type": "product",
                        "payload": good_payload(source_id=f"1000{index}", current_price=None),
                        "source_url": f"https://www.joybuy.co.uk/dp/slug/1000{index}",
                    },
                    self.spider,
                )
        self.assertEqual(pipeline.rejected, 3)
        self.assertEqual(pipeline.guard.samples, 3)
        pipeline.spider_closed(self.spider)
        event = CrawlRunEvent.objects.get(run=self.run, code="PRICE_ANOMALY_MISSING")
        self.assertEqual(event.level, "ERROR")
        self.assertIn("3/3", event.message)


class DatasetIncrementalTests(TestCase):
    """Unchanged products keep their index line; the raw JSON is refreshed."""

    def stub_image(self, url):
        return url, b"image-bytes"

    def save(self, root, payload):
        from joybuy_crawler.dataset import save_product

        return save_product(
            root,
            breadcrumb_names=["Electronics", "Audio"],
            payload=payload,
            resolve_image=self.stub_image,
        )

    def test_second_identical_capture_is_marked_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = good_payload()
            first = self.save(root, payload)
            second = self.save(root, payload)
            self.assertTrue(first["changed"])
            self.assertFalse(second["changed"])

            index_path = Path(second["index_path"])
            lines = [
                json.loads(line)
                for line in index_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(
                len(lines), 1, "an unchanged product must not duplicate its index line"
            )

            meta = json.loads(
                (root / "electronics" / "audio" / "10001234" / "meta.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(meta["capture_count"], 2)
            self.assertFalse(meta["changed"])
            self.assertTrue(meta["first_captured_at"])

    def test_changed_price_appends_a_new_index_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.save(root, good_payload())
            changed = self.save(root, good_payload(current_price="99.99"))
            self.assertTrue(changed["changed"])
            index_path = Path(changed["index_path"])
            lines = [
                json.loads(line)
                for line in index_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(lines), 2)

    def test_raw_snapshot_is_always_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = self.save(root, good_payload())
            product_json = root / first["product_json"]
            product_json.write_text("{}", encoding="utf-8")
            self.save(root, good_payload())
            self.assertIn('"10001234"', product_json.read_text(encoding="utf-8"))
