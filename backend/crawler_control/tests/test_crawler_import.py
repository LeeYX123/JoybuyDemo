import sys
import unittest
from importlib.util import find_spec
from pathlib import Path

CRAWLER_DIR = Path(__file__).resolve().parents[3] / "crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

from catalog.models import (  # noqa: E402
    LocalFieldOverride,
    Spu,
    SpuTranslation,
)
from catalog.override_services import (  # noqa: E402
    propose_local_override,
    resolve_effective_value,
    review_local_override,
)
from merchants.models import Merchant  # noqa: E402
from merchants.services import get_import_fallback_merchant  # noqa: E402
from offers.models import Offer  # noqa: E402

from crawler_control.import_services import (  # noqa: E402
    StagingImportRejected,
    import_staging_product,
)
from crawler_control.models import StagingProduct  # noqa: E402
from crawler_control.services import start_run  # noqa: E402
from crawler_control.tests.test_crawler_control_domain import CrawlerControlTestBase  # noqa: E402

SCRAPY_AVAILABLE = find_spec("scrapy") is not None
FIXTURES_DIR = CRAWLER_DIR / "fixtures"


def parse_fixture(name: str):
    from joybuy_crawler.parsers.product_detail import parse_product_detail

    html = (FIXTURES_DIR / name).read_text(encoding="utf-8")
    return parse_product_detail(html)


@unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy (parsel) is not installed")
class ProductImportTests(CrawlerControlTestBase):
    def setUp(self):
        super().setUp()
        self.make_account()
        self.job = self.make_job(name="Import job")
        self.run = start_run(self.job)
        from joybuy_crawler.ingest import ingest_product_payload
        from joybuy_crawler.parsers.product_detail import PRODUCT_STRUCTURE_VERSION

        parsed = parse_fixture("product_detail_v1.html")
        self.ingest = ingest_product_payload
        self.structure_version = PRODUCT_STRUCTURE_VERSION
        self.staging = self.ingest(
            self.run,
            parsed.to_payload(),
            source_system="joybuy",
            source_url="https://fixture.test/p/1001.html",
            parser_version="product-1",
            structure_version=self.structure_version,
        )

    def import_staging(self, staging=None, **kwargs):
        return import_staging_product(
            staging or self.staging,
            market=self.market,
            currency=self.currency,
            **kwargs,
        )

    def test_parser_contract_with_fixture(self):
        parsed = parse_fixture("product_detail_v1.html")
        self.assertEqual(parsed.source_id, "1001")
        self.assertEqual(parsed.title, "Wireless Earbuds Pro")
        self.assertEqual(parsed.currency, "GBP")
        # Business rule: only the original price is crawled. The discounted
        # 19.99 is discarded; every SKU inherits the original 29.99 and the
        # list-price split is not kept.
        self.assertEqual(parsed.current_price, "29.99")
        self.assertIsNone(parsed.list_price)
        self.assertEqual(parsed.promotion_label, "Flash Sale")
        self.assertEqual(parsed.brand, "SoundCore")
        self.assertEqual(parsed.source_category_id, "l3-phones")
        self.assertEqual(parsed.source_seller_id, "seller-88")
        self.assertEqual(len(parsed.skus), 3)
        self.assertEqual(parsed.skus[0]["specs"][0], {"name": "Colour", "value": "Black"})
        for sku in parsed.skus:
            self.assertEqual(sku["price"], "29.99")
        self.assertEqual(len(parsed.image_urls), 2)
        self.assertEqual(parsed.missing_fields, [])

        broken = parse_fixture("product_detail_missing_price_v1.html")
        self.assertIn("current_price", broken.missing_fields)
        self.assertIn("skus", broken.missing_fields)

    def test_ingest_is_idempotent_and_resets_status(self):

        self.assertEqual(StagingProduct.objects.count(), 1)
        again = self.ingest(
            self.run,
            parse_fixture("product_detail_v1.html").to_payload(),
            source_system="joybuy",
            source_url="https://fixture.test/p/1001.html",
            parser_version="product-1",
            structure_version=1,
        )
        self.assertEqual(again.pk, self.staging.pk)
        self.assertEqual(StagingProduct.objects.count(), 1)
        self.assertEqual(again.status, StagingProduct.Status.PENDING)

    def test_import_creates_spu_sku_offer_with_fallback_and_mapped_merchants(self):
        outcome = self.import_staging()

        self.assertTrue(outcome.created_spu)
        self.assertEqual(len(outcome.skus), 3)
        self.assertEqual(len(outcome.offers), 3)
        spu = outcome.spu
        self.assertEqual(Spu.objects.count(), 1)
        self.assertEqual(spu.brand.name, "SoundCore")
        self.assertEqual(spu.source_identities.get().source_id, "1001")
        self.assertEqual(outcome.staging.status, StagingProduct.Status.IMPORTED)
        self.assertEqual(outcome.staging.imported_refs["sku_count"], 3)

        # All specs differ, so three SKUs with distinct signatures exist.
        self.assertEqual(spu.skus.count(), 3)
        # Seller mapping created a dedicated virtual merchant for seller-88.
        offer = outcome.offers[0]
        self.assertNotEqual(offer.merchant, get_import_fallback_merchant())
        self.assertEqual(offer.local_inventory, 9999)
        self.assertEqual(offer.display_inventory, "999+")

        # Source field layer holds the parsed content values.
        translation = SpuTranslation.objects.get(spu=spu)
        resolved = resolve_effective_value(translation, "title")
        self.assertEqual(resolved["effective"], "Wireless Earbuds Pro")
        self.assertEqual(resolved["effective_origin"], "source")

    def test_products_without_seller_land_on_the_fallback_merchant(self):
        payload = parse_fixture("product_detail_v1.html").to_payload()
        payload["source_id"] = "no-seller-product"
        payload["source_seller_id"] = ""
        payload["source_seller_name"] = ""

        staging = self.ingest(
            self.run,
            payload,
            source_system="joybuy",
            source_url="https://fixture.test/p/no-seller",
            parser_version="product-1",
            structure_version=1,
        )
        outcome = self.import_staging(staging)
        self.assertEqual(outcome.offers[0].merchant, get_import_fallback_merchant())

    def test_repeat_import_never_duplicates_entities(self):
        from datetime import timedelta

        from django.utils import timezone

        first_observed = timezone.now()
        first = self.import_staging(observed_at=first_observed)
        offer_pk = first.offers[0].pk

        # Re-import at the same observation time: fully idempotent.
        second = self.import_staging(observed_at=first_observed)
        self.assertFalse(second.created_spu)
        self.assertEqual(Spu.objects.count(), 1)
        self.assertEqual(SpuTranslation.objects.count(), 1)
        self.assertEqual(second.spu.skus.count(), 3)
        self.assertEqual(Offer.objects.count(), 3)
        self.assertEqual(
            Offer.objects.get(pk=offer_pk).price_snapshots.count(),
            1,
            "Same-observation re-import must not append snapshots.",
        )
        self.assertEqual(Merchant.objects.count(), 2)

        # A later crawl is a new observation: price snapshot history grows.
        self.import_staging(observed_at=first_observed + timedelta(hours=6))
        self.assertEqual(
            Offer.objects.get(pk=offer_pk).price_snapshots.count(),
            2,
        )

    def test_missing_required_fields_reject_without_business_rows(self):

        broken_payload = parse_fixture("product_detail_missing_price_v1.html").to_payload()
        broken = self.ingest(
            self.run,
            broken_payload,
            source_system="joybuy",
            source_url="https://fixture.test/p/9999",
            parser_version="product-1",
            structure_version=1,
        )
        self.assertEqual(broken.missing_fields, ["current_price", "skus"])

        before_spu = Spu.objects.count()
        with self.assertRaises(StagingImportRejected):
            self.import_staging(broken)
        broken.refresh_from_db()
        self.assertEqual(broken.status, StagingProduct.Status.REJECTED)
        self.assertIn("current_price", broken.error_message)
        self.assertEqual(Spu.objects.count(), before_spu)

    def test_source_updates_never_shadow_approved_local_overrides(self):
        outcome = self.import_staging()
        translation = SpuTranslation.objects.get(spu=outcome.spu)
        offer = outcome.offers[0]

        propose_local_override(translation, "title", "Curated Title", reason="Editorial fix")
        review_local_override(
            translation, "title", LocalFieldOverride.Status.APPROVED, reason="Approved copy"
        )
        propose_local_override(offer, "promotion_label", "Editor Pick", reason="Campaign")
        review_local_override(
            offer, "promotion_label", LocalFieldOverride.Status.APPROVED, reason="Approved"
        )

        # Crawler re-import with changed source values.
        changed = parse_fixture("product_detail_v1.html").to_payload()
        changed["title"] = "Renamed at source"
        changed["promotion_label"] = "Weekend Deal"

        staging = self.ingest(
            self.run,
            changed,
            source_system="joybuy",
            source_url="https://fixture.test/p/1001.html",
            parser_version="product-1",
            structure_version=1,
        )
        self.import_staging(staging)

        title_state = resolve_effective_value(translation, "title")
        self.assertEqual(title_state["effective"], "Curated Title")
        self.assertEqual(title_state["effective_origin"], "local_override")
        self.assertEqual(title_state["source"], "Renamed at source")

        promo_state = resolve_effective_value(offer, "promotion_label")
        self.assertEqual(promo_state["effective"], "Editor Pick")
        self.assertEqual(promo_state["source"], "Weekend Deal")

    def test_source_sku_identity_conflicts_are_surfaces_not_silent(self):

        self.import_staging()
        swapped = parse_fixture("product_detail_v1.html").to_payload()
        swapped["skus"][0]["specs"] = [{"name": "Colour", "value": "Neon"}]
        staging = self.ingest(
            self.run,
            swapped,
            source_system="joybuy",
            source_url="https://fixture.test/p/1001.html",
            parser_version="product-1",
            structure_version=1,
        )
        with self.assertRaises(Exception):
            self.import_staging(staging)
        staging.refresh_from_db()
        self.assertEqual(staging.status, StagingProduct.Status.PENDING)
