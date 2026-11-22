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
from crawler_control.domain import ImportSourceConflict  # noqa: E402
from crawler_control.import_services import (  # noqa: E402
    StagingImportRejected,
    import_staging_product,
)
from crawler_control.models import StagingProduct  # noqa: E402
from crawler_control.services import start_run  # noqa: E402
from crawler_control.tests.test_crawler_control_domain import CrawlerControlTestBase  # noqa: E402
from merchants.models import Merchant  # noqa: E402
from merchants.services import get_import_fallback_merchant  # noqa: E402
from offers.models import Offer  # noqa: E402

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
        with self.assertRaises(ImportSourceConflict) as ctx:
            self.import_staging(staging)
        message = str(ctx.exception)
        self.assertIn("来源 SKU", message)
        self.assertIn("已绑定到同一商品下的另一个规格", message)
        self.assertIn("系统不会自动改绑", message)
        staging.refresh_from_db()
        self.assertEqual(staging.status, StagingProduct.Status.PENDING)

    def test_seller_name_drift_conflict_is_chinese_and_never_rebinds(self):
        """Same source offer identity + different merchant = conflict, not duplicate.

        100859032 的真实场景：旧 Offer 属于 Samsung，新抓取把卖家名解析成
        「三星 查看店铺」→ 新商家。不能静默改绑，且提示必须是中文可执行的。
        """

        first = self.import_staging()
        first_offer = first.offers[0]
        identity = first_offer.source_identities.get()

        drifted = parse_fixture("product_detail_v1.html").to_payload()
        drifted["source_seller_id"] = "seller-88-cn"
        drifted["source_seller_name"] = "卖家八十八 查看店铺"
        staging = self.ingest(
            self.run,
            drifted,
            source_system="joybuy",
            source_url="https://fixture.test/p/1001.html",
            parser_version="product-1",
            structure_version=1,
        )

        with self.assertRaises(ImportSourceConflict) as ctx:
            self.import_staging(staging)

        message = str(ctx.exception)
        self.assertIn(f"来源 Offer「joybuy:{identity.source_id}」", message)
        self.assertIn("已绑定到另一个 Offer", message)
        self.assertIn(
            f"现有商家 {first_offer.merchant.display_name}/{first_offer.merchant_id}",
            message,
        )
        self.assertIn("本次商家 卖家八十八 查看店铺/", message)
        self.assertIn("不一致：商家", message)
        self.assertIn("卖家名称/本地化", message)
        self.assertIn("系统不会自动改绑", message)
        self.assertNotIn("The source offer identity", message)

        # No silent rebind: the identity still points at the original offer,
        # and the outer transaction rolled the new merchant back.
        self.assertEqual(first_offer.source_identities.get().pk, identity.pk)
        self.assertEqual(Offer.objects.count(), 3)
        self.assertEqual(Merchant.objects.count(), 2)


class ImportMerchantLegacyColumnTests(CrawlerControlTestBase):
    """回归（2026-11-22 08:40 UTC 事故，60 条导入被记成不可重试失败）。

    ``Merchant.public_id`` 由 UUIDField 迁移为 CharField（MER+6 位）后，仍在运行
    的长生命周期导入进程内存里还是旧模型元数据（UUIDField）；MySQL 后端
    ``get_db_converters`` 会按 ``UUIDField`` 给该列挂上
    ``convert_uuidfield_value``，直接 ``uuid.UUID('MER001000')`` →
    ``ValueError('badly formed hexadecimal UUID string')``，异常在
    ``import_staging_product`` 建任何对象之前抛出，整条导入被判死。

    导入链路只应 SELECT 自己用到的列：这里把真实 Merchant 模型的 public_id 字段
    临时伪装成 UUIDField（复刻旧进程元数据），断言商家解析与整条导入都不再因为
    可选展示列崩溃。
    """

    def setUp(self):
        super().setUp()
        from merchants.services import resolve_import_merchant

        self.mapped = resolve_import_merchant(
            source_system="joybuy_uk",
            source_seller_id="seller-legacy",
            source_name="Legacy Seller",
        )
        self.fallback = resolve_import_merchant(
            source_system="joybuy_uk",
            source_seller_id=None,
        )

    def _make_staging(self, source_id: str, seller_id: str):
        from joybuy_crawler.ingest import ingest_product_payload

        payload = {
            "source_id": source_id,
            "title": "Legacy UUID Merchant Probe",
            "currency": "GBP",
            "current_price": "9.99",
            "brand": "Probe",
            "source_seller_id": seller_id,
            "source_seller_name": "Legacy Seller" if seller_id else "",
            "skus": [
                {
                    "source_id": f"{source_id}-sku",
                    "price": "9.99",
                    "specs": [{"name": "Colour", "value": "Black"}],
                }
            ],
        }
        return ingest_product_payload(
            None,
            payload,
            source_system="joybuy_uk",
            source_url=f"https://example.test/dp/{source_id}",
            parser_version="probe-v1",
            structure_version=1,
        )

    def test_import_survives_legacy_uuid_public_id_column(self):
        from unittest import mock

        from merchants import services as merchant_services

        staging = self._make_staging("legacy-uuid-1", "seller-legacy")
        public_id_field = Merchant._meta.get_field("public_id")
        with mock.patch.object(public_id_field, "get_internal_type", return_value="UUIDField"):
            # 先证明事故机制在本次伪装下真实存在：整行读取会抛 ValueError
            with self.assertRaises(ValueError) as ctx:
                Merchant.objects.get(slug=merchant_services.IMPORT_FALLBACK_SLUG, is_system=True)
            self.assertIn("badly formed hexadecimal UUID string", str(ctx.exception))

            # 已存在的来源商家映射：不得 select_related 整行商家
            resolved = merchant_services.resolve_import_merchant(
                source_system="joybuy_uk", source_seller_id="seller-legacy"
            )
            self.assertEqual(resolved.pk, self.mapped.pk)

            # fallback 商家（payload 无卖家）：同样只读用到的列
            fallback = merchant_services.resolve_import_merchant(
                source_system="joybuy_uk", source_seller_id=""
            )
            self.assertEqual(fallback.pk, self.fallback.pk)

            # 整条导入必须成功，而不是在建任何对象前抛 ValueError
            outcome = import_staging_product(staging, market=self.market, currency=self.currency)

        self.assertTrue(outcome.created_spu)
        self.assertEqual(len(outcome.offers), 1)
        self.assertEqual(outcome.offers[0].merchant_id, self.mapped.pk)
        staging.refresh_from_db()
        self.assertEqual(staging.status, StagingProduct.Status.IMPORTED)


@unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy (parsel) is not installed")
class SellerNameNormalizationTests(unittest.TestCase):
    def test_store_ui_suffixes_are_stripped_in_both_locales(self):
        from joybuy_crawler.parsers.joybuy_uk import normalize_seller_name

        cases = {
            "三星 查看店铺": "三星",
            "查看店铺 三星 查看店铺": "三星",
            "Samsung View store": "Samsung",
            "View store Samsung Visit store": "Samsung",
            "  Samsung   官方店  ": "Samsung 官方店",
            "Pure Store": "Pure Store",
            "": "",
        }
        for raw, expected in cases.items():
            self.assertEqual(normalize_seller_name(raw), expected, raw)

    def test_detail_parser_strips_the_store_link_label_from_seller_name(self):
        from joybuy_crawler.parsers.joybuy_uk import parse_uk_product_detail

        html = (
            "<html><body><h1>Galaxy S24</h1>"
            '<span class="crossOffPrice">£699.00</span>'
            '<div class="seller-card"><a href="/store/88">查看店铺</a>'
            " 三星 查看店铺</div>"
            "</body></html>"
        )
        product = parse_uk_product_detail(
            html, source_url="https://www.joybuy.co.uk/dp/galaxy-s24/100859032"
        )
        self.assertEqual(product.source_id, "100859032")
        self.assertEqual(product.seller_name, "三星")
        self.assertEqual(product.seller_url, "https://www.joybuy.co.uk/store/88")
        self.assertEqual(product.to_payload()["source_seller_id"], "三星")


@unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy (parsel) is not installed")
class ImportLocalMediaReuseTests(CrawlerControlTestBase):
    """导入媒体库时复用 dataset 已下载的文件（2026-11-10 爬取提速）。

    同一张图在 dataset 落盘时下载过一次，导入时不能再下载第二次；
    只有本地文件缺失时才回退到网络。
    """

    def make_spu(self):
        from decimal import Decimal as DecimalValue

        return Spu.objects.create(
            status=Spu.Status.ACTIVE,
            cost_price=None,
            retail_price=DecimalValue("19.99"),
        )

    def make_webp(self, directory: Path) -> Path:
        import io

        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (4, 4), (200, 30, 30)).save(buffer, "WEBP")
        path = Path(directory) / "gallery-01.webp"
        path.write_bytes(buffer.getvalue())
        return path

    def test_gallery_uses_local_file_without_network(self):
        import tempfile
        from unittest import mock

        from django.test import override_settings
        from django.utils import timezone

        from crawler_control.import_services import _import_gallery_images

        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_webp(tmp)
            spu = self.make_spu()
            url = "https://cdn.joy-sourcing.com/product/a.webp"
            with override_settings(MEDIA_ROOT=Path(tmp) / "media"):
                with mock.patch(
                    "crawler_control.import_services._fetch_image_bytes",
                    side_effect=AssertionError("local file should be reused"),
                ):
                    summary = _import_gallery_images(
                        spu,
                        {"image_urls": [url]},
                        observed_at=timezone.now(),
                        local_files={url: str(path)},
                    )
            self.assertEqual(summary, {"downloaded": 1, "failed": 0, "reused": 1})

    def test_missing_local_file_falls_back_to_download(self):
        import tempfile
        from unittest import mock

        from django.test import override_settings
        from django.utils import timezone

        from crawler_control.import_services import _import_gallery_images

        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_webp(tmp)
            spu = self.make_spu()
            url = "https://cdn.joy-sourcing.com/product/a.webp"
            with override_settings(MEDIA_ROOT=Path(tmp) / "media"):
                with mock.patch(
                    "crawler_control.import_services._fetch_image_bytes",
                    return_value=path.read_bytes(),
                ) as fetch:
                    summary = _import_gallery_images(
                        spu,
                        {"image_urls": [url]},
                        observed_at=timezone.now(),
                        local_files={url: str(Path(tmp) / "gone.webp")},
                    )
            fetch.assert_called_once_with(url)
            self.assertEqual(summary, {"downloaded": 1, "failed": 0, "reused": 0})


class SaleFloorImportTests(CrawlerControlTestBase):
    """productCommentSaleFloor 的 saleAmount/commentCountDisplay 入库（2026-11-19）。"""

    def test_sale_fields_land_on_spu_detail(self):

        from catalog.models import SpuDetail

        self.make_account()
        self.job = self.make_job(name="Sale floor import job")
        self.run = start_run(self.job)
        from joybuy_crawler.ingest import ingest_product_payload
        from joybuy_crawler.parsers.product_detail import PRODUCT_STRUCTURE_VERSION

        parsed = parse_fixture("product_detail_v1.html")
        payload = parsed.to_payload()
        payload["sale_amount"] = "10k+"
        payload["comment_count_display"] = "80+"
        payload.setdefault("joybuy", {})["saleInfo"] = {
            "saleAmount": "10k+",
            "commentCountDisplay": "80+",
        }
        staging = ingest_product_payload(
            self.run,
            payload,
            source_system="joybuy",
            source_url="https://fixture.test/p/2001.html",
            parser_version="product-1",
            structure_version=PRODUCT_STRUCTURE_VERSION,
        )
        import_staging_product(staging, market=self.market, currency=self.currency)

        spu = SpuDetail.objects.get(
            spu__source_identities__source_id="1001",
            spu__source_identities__source_system="joybuy",
        )
        self.assertEqual(spu.sale_amount, "10k+")
        self.assertEqual(spu.comment_count_display, "80+")

    def test_empty_sale_fields_do_not_overwrite(self):
        from catalog.models import SpuDetail

        self.make_account()
        self.job = self.make_job(name="Sale floor empty job")
        self.run = start_run(self.job)
        from joybuy_crawler.ingest import ingest_product_payload
        from joybuy_crawler.parsers.product_detail import PRODUCT_STRUCTURE_VERSION

        parsed = parse_fixture("product_detail_v1.html")
        payload = parsed.to_payload()
        payload["sale_amount"] = "10k+"
        payload["comment_count_display"] = "80+"
        payload.setdefault("joybuy", {})["saleInfo"] = {
            "saleAmount": "10k+",
            "commentCountDisplay": "80+",
        }
        staging = ingest_product_payload(
            self.run,
            payload,
            source_system="joybuy",
            source_url="https://fixture.test/p/3001.html",
            parser_version="product-1",
            structure_version=PRODUCT_STRUCTURE_VERSION,
        )
        import_staging_product(staging, market=self.market, currency=self.currency)
        # 第二次导入：payload 没带销量字段（例如改版后 floor 消失）→ 不清空已有值
        payload2 = parsed.to_payload()
        payload2.pop("sale_amount", None)
        payload2.pop("comment_count_display", None)
        payload2.get("joybuy", {}).pop("saleInfo", None)
        staging2 = ingest_product_payload(
            self.run,
            payload2,
            source_system="joybuy",
            source_url="https://fixture.test/p/3001.html",
            parser_version="product-1",
            structure_version=PRODUCT_STRUCTURE_VERSION,
        )
        import_staging_product(staging2, market=self.market, currency=self.currency)

        spu = SpuDetail.objects.get(
            spu__source_identities__source_id="1001",
            spu__source_identities__source_system="joybuy",
        )
        self.assertEqual(spu.sale_amount, "10k+")
        self.assertEqual(spu.comment_count_display, "80+")
