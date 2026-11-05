"""Tests for the 2026-11-05 crawler rebuild: tree sync, multi-category jobs,
unauthenticated runs, UK parsers, dataset writer and the staging pipeline."""

import json
import sys
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path
from unittest import mock

CRAWLER_DIR = Path(__file__).resolve().parents[3] / "crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

from django.test import TestCase  # noqa: E402

from crawler_control.models import (  # noqa: E402
    CrawlRun,
    CrawlRunEvent,
    StagingProduct,
)
from crawler_control.services import (  # noqa: E402
    create_crawl_job,
    mark_job_ready,
    start_run,
)
from crawler_control.tests.test_crawler_control_domain import (  # noqa: E402
    CrawlerControlTestBase,
)

SCRAPY_AVAILABLE = find_spec("scrapy") is not None


class TreeSyncTests(CrawlerControlTestBase):
    def _catalog(self):
        from catalog.models import SourceCatalog

        catalog, _ = SourceCatalog.objects.get_or_create(
            source_system="joybuy_uk", defaults={"display_name": "Joybuy UK"}
        )
        return catalog

    def test_sync_publishes_version_with_verbatim_ids(self):
        from catalog.models import SourceCategorySnapshot
        from crawler_control.tree_sync import MenuNode, sync_category_tree, tree_to_payload

        catalog = self._catalog()
        nodes = [
            MenuNode(
                name="Electronics",
                source_id="l1:1409",
                source_url="https://www.joybuy.co.uk/s?k=Electronics&l1=1409",
                children=[
                    MenuNode(
                        name="Camera & Photo",
                        source_id="cid2:1416",
                        source_url="https://www.joybuy.co.uk/s?k=Camera&cid2=1416",
                    )
                ],
            )
        ]
        result = sync_category_tree(catalog, nodes, publish=True)

        self.assertEqual(result.tree_version.status, "PUBLISHED")
        self.assertEqual(result.tree_version.version_key, result.tree_version.version_key)
        self.assertTrue(result.tree_version.version_key.startswith("joybuy-uk-"))
        self.assertEqual(result.created_snapshots, 2)
        self.assertIn("l1:1409", result.new_source_ids)

        # Verbatim ids become real SourceCategory rows.
        category = SourceCategorySnapshot.objects.get(
            tree_version=result.tree_version, depth=0
        ).category
        self.assertEqual(category.source_id, "l1:1409")

        payload = tree_to_payload(result.tree_version)
        self.assertEqual(payload["version_key"], result.tree_version.version_key)
        self.assertEqual(len(payload["categories"]), 1)
        self.assertEqual(payload["categories"][0]["children"][0]["source_id"], "cid2:1416")

    def test_sync_reports_removed_ids_against_previous_version(self):
        from crawler_control.tree_sync import MenuNode, sync_category_tree

        catalog = self._catalog()
        first = sync_category_tree(
            catalog,
            [MenuNode("Electronics", "l1:1409"), MenuNode("Gaming", "l1:1407")],
            publish=True,
        )
        second = sync_category_tree(catalog, [MenuNode("Electronics", "l1:1409")], publish=True)

        self.assertNotEqual(first.tree_version.version_key, second.tree_version.version_key)
        self.assertEqual(second.missing_source_ids, ["l1:1407"])

    def test_sync_rejects_empty_or_unidentified_menu(self):
        from crawler_control.domain import CrawlJobParamsInvalid
        from crawler_control.tree_sync import MenuNode, sync_category_tree

        catalog = self._catalog()
        with self.assertRaises(CrawlJobParamsInvalid):
            sync_category_tree(catalog, [], publish=True)
        with self.assertRaises(CrawlJobParamsInvalid):
            sync_category_tree(catalog, [MenuNode("No id", "")], publish=True)

    def test_chinese_names_match_by_source_id_and_survive_resync(self):
        from crawler_control.tree_sync import (
            MenuNode,
            apply_chinese_names,
            sync_category_tree,
            tree_to_payload,
        )

        catalog = self._catalog()
        english = [
            MenuNode(
                name="Electronics",
                source_id="minihome:UK-Mini-HP-Electronics",
                children=[MenuNode(name="Phones", source_id="l2:1420")],
            )
        ]
        first = sync_category_tree(catalog, english, publish=True)

        result = apply_chinese_names(
            catalog,
            [
                MenuNode(
                    name="电子产品",
                    source_id="minihome:UK-Mini-HP-Electronics",
                    name_zh="电子产品",
                    children=[MenuNode(name="手机", source_id="l2:1420", name_zh="手机")],
                )
            ],
        )

        self.assertEqual(len(result.matched_source_ids), 2)
        self.assertEqual(result.unknown_source_ids, [])
        self.assertEqual(result.missing_source_ids, [])
        self.assertEqual(result.updated_categories, 2)
        self.assertEqual(result.updated_snapshots, 2)

        payload = tree_to_payload(first.tree_version)
        self.assertEqual(payload["categories"][0]["name"], "Electronics")
        self.assertEqual(payload["categories"][0]["name_zh"], "电子产品")
        self.assertEqual(payload["categories"][0]["children"][0]["name_zh"], "手机")

        # 英文名仍然是结构基线；重建一个新版本时中文名从 SourceCategory 继承。
        english.append(MenuNode(name="Pets", source_id="minihome:UK-Mini-HP-Pets"))
        second = sync_category_tree(catalog, english, publish=True)
        self.assertNotEqual(first.tree_version.version_key, second.tree_version.version_key)
        rebuilt = tree_to_payload(second.tree_version)
        electronics = next(
            node
            for node in rebuilt["categories"]
            if node["source_id"] == "minihome:UK-Mini-HP-Electronics"
        )
        self.assertEqual(electronics["name_zh"], "电子产品")

    def test_chinese_name_sync_reports_unknown_and_missing_ids(self):
        from crawler_control.tree_sync import (
            MenuNode,
            apply_chinese_names,
            sync_category_tree,
        )

        catalog = self._catalog()
        sync_category_tree(
            catalog,
            [
                MenuNode(
                    name="Electronics",
                    source_id="minihome:UK-Mini-HP-Electronics",
                    children=[MenuNode(name="Phones", source_id="l2:1420")],
                )
            ],
            publish=True,
        )

        result = apply_chinese_names(
            catalog,
            [
                MenuNode(
                    name="电子产品",
                    source_id="minihome:UK-Mini-HP-Electronics",
                    name_zh="电子产品",
                    children=[MenuNode(name="不存在", source_id="l2:9999", name_zh="不存在")],
                )
            ],
        )

        self.assertEqual(result.unknown_source_ids, ["l2:9999"])
        self.assertEqual(result.missing_source_ids, ["l2:1420"])
        self.assertEqual(result.matched_source_ids, ["minihome:UK-Mini-HP-Electronics"])


class MultiCategoryJobTests(CrawlerControlTestBase):
    def test_multi_category_selections_are_frozen_and_ordered(self):
        job = create_crawl_job(
            name="Multi job",
            market=self.market,
            source_catalog=self.catalog,
            source_categories=[
                {"category": self.l2, "include_descendants": True},
                {"category": self.l3, "include_descendants": False},
            ],
            product_limit=10,
        )
        selections = list(job.source_selections.order_by("sort_order"))
        self.assertEqual(len(selections), 2)
        self.assertEqual(selections[0].source_category_id, self.l2.pk)
        self.assertTrue(selections[0].include_descendants)
        self.assertFalse(selections[1].include_descendants)
        # Legacy column keeps the first selection; tree version is frozen.
        self.assertEqual(job.source_category_id, self.l2.pk)
        self.assertEqual(job.source_tree_version_id, self.version.pk)

        run = start_run(mark_job_ready(job))
        self.assertEqual(len(run.params_snapshot["source_categories"]), 2)
        self.assertEqual(
            run.params_snapshot["source_categories"][0]["source_category_id"], "l2-electronics"
        )

    def test_duplicate_selection_is_rejected(self):
        from crawler_control.domain import CrawlJobParamsInvalid

        with self.assertRaises(CrawlJobParamsInvalid):
            create_crawl_job(
                name="Dup job",
                market=self.market,
                source_catalog=self.catalog,
                source_categories=[
                    {"category": self.l2},
                    {"category": self.l2},
                ],
                product_limit=10,
            )

    def test_legacy_single_category_still_creates_one_selection(self):
        job = create_crawl_job(
            name="Legacy job",
            market=self.market,
            source_catalog=self.catalog,
            source_category=self.l2,
            product_limit=5,
        )
        self.assertEqual(job.source_selections.count(), 1)
        self.assertTrue(job.source_selections.first().include_descendants)

    def test_start_run_without_account_is_unauthenticated(self):
        job = mark_job_ready(
            create_crawl_job(
                name="No account job",
                market=self.market,
                source_catalog=self.catalog,
                source_category=self.l2,
                product_limit=5,
                account_group="empty-group",
            )
        )
        run = start_run(job)
        self.assertIsNone(run.account)
        self.assertTrue(CrawlRunEvent.objects.filter(run=run, code="RUN_UNAUTHENTICATED").exists())


@unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy (parsel) is not installed")
class JoybuyUkParserTests(unittest.TestCase):
    LISTING_HTML = """
    <div class="list">
      <a href="/dp/some-slug/104001"><span class="title">Kettle 1.7L</span>
        <span class="price"><span class="crossOffPrice">£29.99</span>
        <span class="mainPrice">£19.99</span></span>
        <img src="//images3.joy-sourcing.com/product/s480x480_p/k1.png.webp"/></a>
      <a href="/dp/other/104002"><span class="title">Toaster</span></a>
      <a href="/dp/some-slug/104001"><span>dup</span></a>
    </div>
    """

    def test_listing_parses_cards_with_original_price(self):
        from joybuy_crawler.parsers.joybuy_uk import parse_uk_listing

        entries = parse_uk_listing(self.LISTING_HTML)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].source_url, "https://www.joybuy.co.uk/dp/some-slug/104001")
        self.assertEqual(entries[0].original_price, "29.99")
        self.assertEqual(entries[0].rank, 1)
        self.assertTrue(entries[0].image_url.startswith("https://images3."))

    def test_listing_without_cards_raises(self):
        from joybuy_crawler.parsers.joybuy_uk import parse_uk_listing

        with self.assertRaises(RuntimeError):
            parse_uk_listing("<div>nothing here</div>")

    def test_detail_maps_joybuy_native_fields(self):
        from joybuy_crawler.parsers.joybuy_uk import parse_uk_product_detail

        html = """
        <html><body>
          <h1>Stainless Kettle 1.7L</h1>
          <span class="brand">Ochama</span>
          <span class="crossOffPrice">£29.99</span><span class="mainPrice">£19.99</span>
          <img src="https://images4.joy-sourcing.com/product/s480x480_p/k1.png.webp"/>
          <a href="/store/xiablaqa">xiablaqa</a>
          <div class="description">Fast boil kettle for tea.</div>
        </body></html>
        """
        product = parse_uk_product_detail(
            html, source_url="https://www.joybuy.co.uk/dp/kettle/104001"
        )
        self.assertEqual(product.source_id, "104001")
        self.assertEqual(product.title, "Stainless Kettle 1.7L")
        self.assertEqual(product.current_price, "29.99")
        self.assertIsNone(product.list_price)  # discount never kept
        self.assertEqual(product.main_price, "19.99")
        self.assertEqual(product.currency, "GBP")
        self.assertEqual(len(product.skus), 1)
        self.assertEqual(product.skus[0]["source_id"], "104001")
        payload = product.to_payload()
        # Joybuy-native block keeps source field names verbatim.
        self.assertEqual(payload["joybuy"]["productId"], "104001")
        self.assertEqual(payload["joybuy"]["priceInfo"]["crossOffPrice"], "29.99")
        self.assertEqual(payload["joybuy"]["priceInfo"]["mainPrice"], "19.99")
        self.assertEqual(payload["joybuy"]["skus"][0]["skuId"], "104001")
        self.assertEqual(payload["current_price"], "29.99")

    def test_image_variant_ladder_prefers_largest(self):
        from joybuy_crawler.image_variants import candidate_variants, resolve_highest_resolution

        url = "https://images3.joy-sourcing.com/product/s480x480_p/k1.png.webp"
        candidates = candidate_variants(url)
        # Ladder head is s1248 (live-verified hi-res variant, 2026-11-05).
        self.assertEqual(candidates[0], url.replace("s480x480", "s1248x1248"))
        self.assertIn(url, candidates)
        self.assertEqual(
            candidates[-1],
            "https://images3.joy-sourcing.com/product/p/k1.png.webp",
        )

        calls = []

        def fake_fetch(candidate, headers=None, timeout_seconds=30):
            calls.append(candidate)
            if "s1248x1248" in candidate:
                raise RuntimeError("404")

            class Result:
                status_code = 200
                body = b"image-bytes"

            return Result()

        with mock.patch("joybuy_crawler.image_variants.fetch_url", side_effect=fake_fetch):
            resolved_url, payload = resolve_highest_resolution(url)
        # s1248 fails, so the ladder lands on the next available size.
        self.assertEqual(resolved_url, url.replace("s480x480", "s800x800"))
        self.assertEqual(payload, b"image-bytes")
        self.assertEqual(calls[0], url.replace("s480x480", "s1248x1248"))


class DatasetTests(TestCase):
    """Dataset writer: per-category folders with a 1:1 index mapping."""

    def test_save_product_writes_json_images_and_index(self):
        from joybuy_crawler.dataset import save_product

        payload = {
            "source_id": "104001",
            "title": "Kettle",
            "image_urls": [
                "https://images3.joy-sourcing.com/product/s480x480_p/k1.png.webp",
                "https://images3.joy-sourcing.com/product/s480x480_p/k2.jpg!q70.webp",
            ],
            "detail_image_urls": [
                "https://images3.joy-sourcing.com/product/s480x480_d/d1.png.webp"
            ],
            "joybuy": {"breadcrumbs": [{"name": "Electronics"}, {"name": "Camera"}]},
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "job-a"

            def fake_resolve(url, timeout=30):
                return url, b"img:" + url.encode()

            index = save_product(
                root,
                breadcrumb_names=["Electronics", "Camera & Photo"],
                payload=payload,
                resolve_image=fake_resolve,
            )
            product_dir = root / "electronics" / "camera-photo" / "104001"
            self.assertTrue((product_dir / "product.json").exists())
            written = json.loads((product_dir / "product.json").read_text(encoding="utf-8"))
            self.assertEqual(written["source_id"], "104001")
            # First image = main; the rest + description images = detail.
            self.assertTrue((product_dir / "images" / "main" / "01.webp").exists())
            self.assertFalse((product_dir / "images" / "main" / "02.webp").exists())
            self.assertTrue((product_dir / "images" / "detail" / "01.webp").exists())
            self.assertTrue((product_dir / "images" / "detail" / "02.webp").exists())
            index_file = root / "electronics" / "camera-photo" / "dataset_index.jsonl"
            line = json.loads(index_file.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(line["source_id"], "104001")
            self.assertIn("product.json", line["product_json"])
            self.assertEqual(index["source_id"], "104001")

    def test_dataset_image_failure_is_recorded_not_fatal(self):
        from joybuy_crawler.dataset import save_product

        payload = {
            "source_id": "104002",
            "title": "Toaster",
            "image_urls": ["https://images3.joy-sourcing.com/product/s480x480_p/bad.png.webp"],
            "joybuy": {"breadcrumbs": [{"name": "Electronics"}]},
        }
        with tempfile.TemporaryDirectory() as tmp:

            def broken_resolve(url, timeout=30):
                raise RuntimeError("CDN 400")

            index = save_product(
                Path(tmp),
                breadcrumb_names=["Electronics"],
                payload=payload,
                resolve_image=broken_resolve,
            )
            self.assertIn("main_errors", index["images"])


@unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy (parsel) is not installed")
class StagingPipelineTests(CrawlerControlTestBase):
    def _pipeline(self):
        from joybuy_crawler.pipelines import StagingPipeline

        run = start_run(self.make_job(name="Pipeline job"))
        pipeline = StagingPipeline()
        pipeline.run = run
        pipeline.job = run.job
        return pipeline, run

    def _item(self, source_id="104001"):
        from joybuy_crawler.parsers.joybuy_uk import parse_uk_product_detail

        html = (
            "<html><body><h1>Kettle</h1><span class='crossOffPrice'>£29.99</span>"
            "<img src='https://images3.joy-sourcing.com/product/s480x480_p/k1.png.webp'/>"
            "</body></html>"
        )
        payload = parse_uk_product_detail(
            html, source_url=f"https://www.joybuy.co.uk/dp/k/{source_id}"
        )
        return {
            "type": "product",
            "payload": payload.to_payload(),
            "breadcrumb_names": ["Electronics", "Camera"],
            "source_url": "https://www.joybuy.co.uk/dp/k/104001",
            "structure_version": 2,
            "parser_version": "joybuy_uk.v2",
        }

    def test_process_item_imports_records_progress_and_event(self):
        pipeline, run = self._pipeline()
        with mock.patch("crawler_control.import_services._fetch_image_bytes", return_value=None):
            pipeline.process_item(self._item(), spider=None)

        run.refresh_from_db()
        self.assertEqual(run.downloaded_count, 1)
        self.assertEqual(run.succeeded_count, 1)
        staging = StagingProduct.objects.get(source_id="104001")
        self.assertEqual(staging.status, StagingProduct.Status.IMPORTED)
        self.assertEqual(staging.imported_refs["gallery_images"], {"downloaded": 0, "failed": 1})
        self.assertTrue(CrawlRunEvent.objects.filter(run=run, code="PRODUCT_IMPORTED").exists())
        from catalog.models import Spu

        self.assertTrue(Spu.objects.filter(source_identities__source_id="104001").exists())

    @staticmethod
    def _fake_spider(fatal_error="", finish_reason="finished"):
        """Scrapy 2.13 calls close_spider(spider); reason comes from stats."""

        from unittest.mock import MagicMock

        spider = MagicMock()
        spider.fatal_error = fatal_error
        spider.crawler.stats.get_stats.return_value = {"finish_reason": finish_reason}
        return spider

    def test_close_spider_marks_success_and_failure(self):
        from crawler_control.services import update_run_progress

        pipeline, run = self._pipeline()
        update_run_progress(run, discovered=3, downloaded=3, succeeded=3)
        pipeline.close_spider(self._fake_spider())
        run.refresh_from_db()
        self.assertEqual(run.status, CrawlRun.Status.SUCCEEDED)

        pipeline2, run2 = self._pipeline()
        pipeline2.close_spider(self._fake_spider())
        run2.refresh_from_db()
        # No discovery, no success -> explicit failure with the reason event.
        self.assertEqual(run2.status, CrawlRun.Status.FAILED)
        self.assertTrue(CrawlRunEvent.objects.filter(run=run2, code="RUN_FAILED").exists())

    def test_close_spider_reports_fatal_error(self):
        pipeline, run = self._pipeline()
        pipeline.close_spider(self._fake_spider(fatal_error="site blocked us"))
        run.refresh_from_db()
        self.assertEqual(run.status, CrawlRun.Status.FAILED)
        event = CrawlRunEvent.objects.filter(run=run, code="RUN_FAILED").latest("pk")
        self.assertIn("site blocked us", event.message)

    def test_close_spider_fails_when_every_product_failed(self):
        from crawler_control.services import update_run_progress

        pipeline, run = self._pipeline()
        update_run_progress(run, discovered=2, downloaded=2, failed=2)
        pipeline.close_spider(self._fake_spider())
        run.refresh_from_db()
        self.assertEqual(run.status, CrawlRun.Status.FAILED)


@unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy is not installed")
class DetailedRunLogTests(CrawlerControlTestBase):
    """The run log must say where a product came from and where it went."""

    def test_dataset_and_import_events_carry_paths_and_ids(self):
        from joybuy_crawler.parsers.joybuy_uk import parse_uk_product_detail
        from joybuy_crawler.pipelines import StagingPipeline

        run = start_run(self.make_job(name="Logging job"))
        pipeline = StagingPipeline()
        pipeline.run = run
        pipeline.job = run.job

        html = (
            "<html><body><h1>Kettle</h1>"
            "<span class='crossOffPrice'>£29.99</span>"
            "<img src='https://images3.joy-sourcing.com/product/s480x480_p/k1.png.webp'/>"
            "</body></html>"
        )
        payload = parse_uk_product_detail(html, source_url="https://www.joybuy.co.uk/dp/k/104001")
        item = {
            "type": "product",
            "payload": payload.to_payload(),
            "breadcrumb_names": ["Electronics"],
            "source_url": "https://www.joybuy.co.uk/dp/k/104001",
            "structure_version": 2,
            "parser_version": "joybuy_uk.v2",
        }
        with mock.patch("crawler_control.import_services._fetch_image_bytes", return_value=None):
            pipeline.process_item(item, spider=None)

        saved = CrawlRunEvent.objects.get(run=run, code="DATASET_SAVED")
        self.assertIn("104001", saved.message)
        self.assertIn("var/crawl_exports/", saved.message)
        self.assertIn("product.json", saved.message)

        imported = CrawlRunEvent.objects.get(run=run, code="PRODUCT_IMPORTED")
        self.assertIn("SPU", imported.message)
        self.assertIn("SKU", imported.message)
        self.assertIn("Offer", imported.message)
        self.assertIn("暂存记录", imported.message)


@unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy is not installed")
class SpiderLoggingTests(CrawlerControlTestBase):
    """The spider logs what it fetched and what it parsed.

    Regression guard for 2026-11-05: ``record_run_event`` was imported inside
    a conditional branch, which made it a function-local name that was unbound
    on the success path — every detail page raised UnboundLocalError.
    """

    def _response(self, url, html, target, latency=1.5):
        import types

        return types.SimpleNamespace(
            url=url,
            status=200,
            body=html.encode("utf-8"),
            text=html,
            meta={"target": target, "rank": 1, "download_latency": latency},
        )

    def _spider(self):
        from joybuy_crawler.spiders.joybuy_run import JoybuyRunSpider

        run = start_run(self.make_job(name="Spider log job"))
        return JoybuyRunSpider(run_public_id=str(run.public_id)), run

    def test_detail_page_logs_url_fields_and_parse_summary(self):
        spider, run = self._spider()
        html = (
            "<html><body><h1>Stainless Kettle 1.7L</h1>"
            "<span class='brand'>Ochama</span>"
            "<span class='crossOffPrice'>£29.99</span>"
            "<img src='https://images4.joy-sourcing.com/product/k1.webp'/>"
            "</body></html>"
        )
        item = next(
            iter(
                spider.parse_detail(
                    self._response(
                        "https://www.joybuy.co.uk/dp/kettle/104001",
                        html,
                        spider.targets[0],
                    )
                )
            )
        )
        self.assertEqual(item["type"], "product")
        event = CrawlRunEvent.objects.get(run=run, code="PRODUCT_PARSED")
        self.assertIn("https://www.joybuy.co.uk/dp/kettle/104001", event.message)
        self.assertIn("104001", event.message)
        self.assertIn("29.99", event.message)
        self.assertIn("KB", event.message)

    def test_listing_page_logs_card_counts(self):
        spider, run = self._spider()
        html = (
            '<div class="style_UK_product_card__x"><div class="style_UK_content_wrapper">'
            '<a class="style_UK_image_wrapper" href="/dp/kettle/104001">'
            '<img alt="Stainless Kettle 1.7L" src="//images4.joy-sourcing.com/k1.webp"/></a>'
            '<div class="style_title__x">Stainless Kettle 1.7L</div>'
            '<div class="style_crossOffPrice__x">£ 29 . 99</div></div></div>'
        )
        requests = list(
            spider.parse_listing(
                self._response(
                    "https://www.joybuy.co.uk/s?k=Kettles",
                    html,
                    spider.targets[0],
                )
            )
        )
        self.assertEqual(len(requests), 1)
        event = CrawlRunEvent.objects.get(run=run, code="LISTING_FETCHED")
        self.assertIn("解析出 1 张卡片", event.message)
        self.assertIn("本轮入队 1 个商品", event.message)
