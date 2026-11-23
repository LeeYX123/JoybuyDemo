"""商品后台类目（2 级）解析与导入的针对性测试（2026-11-09）。"""

import json
import sys
import unittest
from decimal import Decimal
from importlib.util import find_spec
from pathlib import Path

CRAWLER_DIR = Path(__file__).resolve().parents[3] / "crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

from catalog.models import (  # noqa: E402
    CategoryMapping,
    LocalCategory,
    ProductCategory,
    SourceCategory,
)

from crawler_control.import_services import (  # noqa: E402
    StagingImportRejected,
    _parse_rating_summary,
    _parse_spu_retail_price,
    import_staging_product,
)
from crawler_control.services import start_run  # noqa: E402
from crawler_control.tests.test_crawler_control_domain import (  # noqa: E402
    CrawlerControlTestBase,
)

PARSER_AVAILABLE = find_spec("parsel") is not None
CATEGORY_PATH = [
    {"name": "厨具餐具", "id": "288"},
    {"name": "锅具", "id": "361"},
    {"name": "炒锅", "id": "372"},
]


def _flight_html(categories, *, title="Test product"):
    payload = json.dumps(
        {
            "serverProduct": {
                "success": True,
                "data": {
                    "floors": [
                        {
                            "floorId": "productBreadCrumbFloor",
                            "data": {"C-M#viewBreadCrumbItem&core": {"categories": categories}},
                        }
                    ]
                },
            }
        },
        ensure_ascii=False,
    )
    chunk = json.dumps(payload, ensure_ascii=False)[1:-1]
    return (
        f"<html><body><h1>{title}</h1>"
        f'<script>self.__next_f.push([1,"{chunk}"])</script></body></html>'
    )


@unittest.skipUnless(PARSER_AVAILABLE, "parsel is not installed")
class ProductCategoryParserTests(unittest.TestCase):
    def test_keeps_first_two_levels_with_ids(self):
        from joybuy_crawler.parsers.joybuy_uk import parse_uk_product_detail

        product = parse_uk_product_detail(
            _flight_html(CATEGORY_PATH),
            source_url="https://www.joybuy.co.uk/dp/wok/10003152",
        )
        payload = product.to_payload()

        self.assertEqual(
            [item["name"] for item in payload["joybuy"]["breadcrumbs"]],
            ["厨具餐具", "锅具"],
        )
        self.assertEqual(
            payload["product_category_path"],
            [
                {"id": "288", "name": "厨具餐具", "depth": 0},
                {"id": "361", "name": "锅具", "depth": 1},
            ],
        )
        self.assertEqual(payload["product_category_id"], "361")
        self.assertEqual(payload["source_category_id"], "")
        self.assertEqual(
            payload["joybuy"]["productCategoryPath"],
            payload["product_category_path"],
        )
        self.assertNotIn("炒锅", json.dumps(payload, ensure_ascii=False))

    def test_dom_fallback_still_two_levels(self):
        from joybuy_crawler.parsers.joybuy_uk import parse_uk_product_detail

        html = """
        <html><body>
          <h1>Fallback</h1>
          <nav class="breadcrumb">
            <a href="/">Home</a>
            <a href="/c/1">母婴用品</a>
            <a href="/c/2">健康护理</a>
            <a href="/c/3">湿巾</a>
          </nav>
        </body></html>
        """
        payload = parse_uk_product_detail(
            html, source_url="https://www.joybuy.co.uk/dp/fallback/1001"
        ).to_payload()
        self.assertEqual(
            [item["name"] for item in payload["joybuy"]["breadcrumbs"]],
            ["母婴用品", "健康护理"],
        )
        self.assertEqual(payload["product_category_path"], [])


@unittest.skipUnless(PARSER_AVAILABLE, "parsel is not installed")
class ProductCategoryImportTests(CrawlerControlTestBase):
    def setUp(self):
        super().setUp()
        self.make_account()
        self.job = self.make_job(name="Category import job")
        self.run = start_run(self.job)

    def _payload(self):
        return {
            "source_id": "10003152",
            "title": "Ochama 炒锅",
            "currency": "GBP",
            "current_price": "25.99",
            "skus": [
                {
                    "source_id": "10003152",
                    "price": "25.99",
                    "availability": "IN_STOCK",
                    "specs": [],
                }
            ],
            "image_urls": [],
            "product_category_path": [
                {"id": "288", "name": "厨具餐具", "depth": 0},
                {"id": "361", "name": "锅具", "depth": 1},
                {"id": "372", "name": "炒锅", "depth": 2},
            ],
        }

    def _import(self, payload=None):
        from joybuy_crawler.ingest import ingest_product_payload

        staging = ingest_product_payload(
            self.run,
            payload or self._payload(),
            source_system="joybuy",
            source_url="https://www.joybuy.co.uk/dp/wok/10003152",
            parser_version="joybuy_uk.v3",
            structure_version=2,
        )
        return import_staging_product(staging, market=self.market, currency=self.currency)

    def test_import_creates_two_levels_and_links_spu(self):
        outcome = self._import()

        self.assertEqual(ProductCategory.objects.count(), 2)
        self.assertEqual(outcome.spu.product_category.source_id, "361")
        self.assertEqual(outcome.spu.product_category.parent.source_id, "288")
        self.assertFalse(ProductCategory.objects.filter(source_id="372").exists())
        self.assertFalse(outcome.spu.is_activity)

    def test_activity_source_marks_spu_and_skips_local_category(self):
        payload = self._payload()
        payload["source_id"] = "seasonal-1"
        payload["skus"][0]["source_id"] = "seasonal-1"
        payload["crawl_source_category_id"] = "l2:1580"
        payload["crawl_source_category_name"] = "节庆装饰品"

        outcome = self._import(payload)

        self.assertTrue(outcome.spu.is_activity)
        self.assertIsNone(outcome.spu.local_category_id)
        # 商品类目表仍按两级保存（节日派对/节日与活动），只是不挂本地类目。
        self.assertEqual(outcome.spu.product_category.source_id, "361")

    def test_activity_product_category_fallback(self):
        payload = self._payload()
        payload["source_id"] = "seasonal-2"
        payload["skus"][0]["source_id"] = "seasonal-2"
        payload["product_category_path"] = [
            {"id": "4909", "name": "节日派对", "depth": 0},
            {"id": "4945", "name": "节日与活动", "depth": 1},
        ]

        outcome = self._import(payload)

        self.assertTrue(outcome.spu.is_activity)
        self.assertIsNone(outcome.spu.local_category_id)

    def test_party_category_is_not_activity(self):
        payload = self._payload()
        payload["source_id"] = "party-1"
        payload["skus"][0]["source_id"] = "party-1"
        payload["product_category_path"] = [
            {"id": "4909", "name": "节日派对", "depth": 0},
            {"id": "4910", "name": "派对用品", "depth": 1},
        ]

        outcome = self._import(payload)

        self.assertFalse(outcome.spu.is_activity)

    def test_reimport_is_idempotent(self):
        self._import()
        self._import()
        self.assertEqual(ProductCategory.objects.count(), 2)


@unittest.skipUnless(PARSER_AVAILABLE, "parsel is not installed")
class LocalCategoryFromJobSelectionTests(CrawlerControlTestBase):
    """品类（LocalCategory）来自任务所选菜单类目的 CategoryMapping（2026-11-10）。

    蜘蛛把任务所选菜单类目写进 payload["source_category_id"]（语义仍是
    「菜单来源类目」，docs/05 §9.2）；导入按它的 primary CategoryMapping
    解析本地类目。活动商品保持无品类；人工品类不被覆盖。
    """

    def setUp(self):
        super().setUp()
        self.make_account()
        self.job = self.make_job(name="Local category job")
        self.run = start_run(self.job)
        self.local_parent = LocalCategory.objects.create(
            name="电子产品",
            slug="electronics",
            depth=0,
            path="/electronics/",
        )
        self.local_child = LocalCategory.objects.create(
            name="手机",
            slug="mobile-phones",
            parent=self.local_parent,
            depth=1,
            path="/electronics/mobile-phones/",
        )
        self.other_child = LocalCategory.objects.create(
            name="冰箱/冰柜",
            slug="fridges-freezers",
            parent=self.local_parent,
            depth=1,
            path="/electronics/fridges-freezers/",
        )
        self.source_category = SourceCategory.objects.get(
            catalog=self.catalog, source_id="l3-phones"
        )
        CategoryMapping.objects.create(
            local_category=self.local_child,
            source_category=self.source_category,
            is_primary=True,
        )

    def _payload(self, source_id="phone-1"):
        return {
            "source_id": source_id,
            "title": "Test phone",
            "currency": "GBP",
            "current_price": "199.00",
            "skus": [
                {
                    "source_id": source_id,
                    "price": "199.00",
                    "availability": "IN_STOCK",
                    "specs": [],
                }
            ],
            "image_urls": [],
            "product_category_path": [],
        }

    def _import(self, payload):
        from joybuy_crawler.ingest import ingest_product_payload

        staging = ingest_product_payload(
            self.run,
            payload,
            source_system="joybuy",
            source_url="https://www.joybuy.co.uk/dp/phone/1",
            parser_version="joybuy_uk.v3",
            structure_version=2,
        )
        return import_staging_product(staging, market=self.market, currency=self.currency)

    def test_source_category_id_maps_local_category_on_create(self):
        payload = self._payload()
        payload["source_category_id"] = "l3-phones"

        outcome = self._import(payload)

        self.assertEqual(outcome.spu.local_category_id, self.local_child.pk)

    def test_fallback_to_crawl_source_category_id(self):
        payload = self._payload("phone-fallback")
        payload["crawl_source_category_id"] = "l3-phones"

        outcome = self._import(payload)

        self.assertEqual(outcome.spu.local_category_id, self.local_child.pk)

    def test_reimport_fills_existing_spu_without_local_category(self):
        payload = self._payload("phone-existing")

        first = self._import(payload)
        self.assertIsNone(first.spu.local_category_id)

        payload["source_category_id"] = "l3-phones"
        second = self._import(payload)
        second.spu.refresh_from_db()
        self.assertEqual(second.spu.local_category_id, self.local_child.pk)

    def test_manual_local_category_is_not_overwritten(self):
        payload = self._payload("phone-manual")
        payload["source_category_id"] = "l3-phones"

        outcome = self._import(payload)
        spu = outcome.spu
        spu.local_category = self.other_child
        spu.save(update_fields=["local_category", "updated_at"])

        again = self._import(payload)
        again.spu.refresh_from_db()
        self.assertEqual(again.spu.local_category_id, self.other_child.pk)

    def test_activity_product_stays_without_local_category(self):
        payload = self._payload("activity-1")
        # 任务选中的是「节庆装饰品」活动类目，即使 payload 里带了
        # 有映射的 source_category_id，活动规则仍然优先。
        payload["source_category_id"] = "l3-phones"
        payload["crawl_source_category_id"] = "l2:1580"
        payload["crawl_source_category_name"] = "节庆装饰品"

        outcome = self._import(payload)

        self.assertTrue(outcome.spu.is_activity)
        self.assertIsNone(outcome.spu.local_category_id)


@unittest.skipUnless(PARSER_AVAILABLE, "parsel is not installed")
class AccessoryParentValidationTests(CrawlerControlTestBase):
    """配件类目导入时校验父级（2026-11-23 批次 A，Q2）。

    「配件」在电子产品（electronics-accessories）与服装与配饰
    （fashion-accessories，0 商品）下同名。导入解析时若库内节点的父级与
    源面包屑父级不一致，必须拒绝自动归类（保留库内父级）并记录
    ``PRODUCT_CATEGORY_PARENT_MISMATCH``；父级一致时正常导入、无误报。
    """

    def setUp(self):
        super().setUp()
        self.make_account()
        self.job = self.make_job(name="Accessory parent job")
        self.run = start_run(self.job)
        self.electronics = ProductCategory.objects.create(
            catalog=self.catalog, source_id="1849", name="电子产品", depth=0, path="/1849/"
        )
        self.clothing = ProductCategory.objects.create(
            catalog=self.catalog, source_id="13101", name="服装与配饰", depth=0, path="/13101/"
        )

    def _payload(self, source_id, path):
        return {
            "source_id": source_id,
            "title": "Phone case",
            "currency": "GBP",
            "current_price": "9.99",
            "skus": [
                {
                    "source_id": source_id,
                    "price": "9.99",
                    "availability": "IN_STOCK",
                    "specs": [],
                }
            ],
            "image_urls": [],
            "product_category_path": path,
        }

    def _import(self, payload):
        from joybuy_crawler.ingest import ingest_product_payload

        staging = ingest_product_payload(
            self.run,
            payload,
            source_system="joybuy",
            source_url="https://www.joybuy.co.uk/dp/case/1",
            parser_version="joybuy_uk.v3",
            structure_version=2,
        )
        return import_staging_product(staging, market=self.market, currency=self.currency)

    def _events(self):
        from crawler_control.models import CrawlRunEvent

        return CrawlRunEvent.objects.filter(run=self.run, code="PRODUCT_CATEGORY_PARENT_MISMATCH")

    def test_matching_parent_imports_without_warning(self):
        ProductCategory.objects.create(
            catalog=self.catalog,
            source_id="1801",
            name="Accessories",
            depth=1,
            path="/1849/1801/",
            parent=self.electronics,
        )
        payload = self._payload(
            "case-ok",
            [{"id": "1849", "name": "Electronics"}, {"id": "1801", "name": "Accessories"}],
        )

        outcome = self._import(payload)

        self.assertEqual(outcome.spu.product_category.source_id, "1801")
        self.assertEqual(outcome.spu.product_category.parent_id, self.electronics.pk)
        self.assertFalse(self._events().exists())

    def test_parent_mismatch_keeps_existing_parent_and_records_event(self):
        accessory = ProductCategory.objects.create(
            catalog=self.catalog,
            source_id="1801",
            name="Accessories",
            depth=1,
            path="/13101/1801/",
            parent=self.clothing,
        )
        payload = self._payload(
            "case-mismatch",
            [{"id": "1849", "name": "Electronics"}, {"id": "1801", "name": "Accessories"}],
        )

        outcome = self._import(payload)

        accessory.refresh_from_db()
        # 不静默改挂到电子产品下：仍属服装与配饰，商品也归该节点。
        self.assertEqual(accessory.parent_id, self.clothing.pk)
        self.assertEqual(
            ProductCategory.objects.get(source_id="1801", catalog=self.catalog).path,
            "/13101/1801/",
        )
        self.assertEqual(outcome.spu.product_category_id, accessory.pk)
        event = self._events().get()
        self.assertEqual(event.level, "WARNING")
        self.assertIn("1849", event.message)

    def test_missing_parent_in_payload_is_treated_as_mismatch(self):
        accessory = ProductCategory.objects.create(
            catalog=self.catalog,
            source_id="1801",
            name="配件",
            depth=1,
            path="/1849/1801/",
            parent=self.electronics,
        )
        payload = self._payload("case-leaf-only", [{"id": "1801", "name": "配件"}])

        outcome = self._import(payload)

        accessory.refresh_from_db()
        self.assertEqual(accessory.parent_id, self.electronics.pk)
        self.assertEqual(outcome.spu.product_category_id, accessory.pk)
        self.assertEqual(self._events().count(), 1)

    def test_non_accessory_categories_still_follow_the_payload_path(self):
        cookware = ProductCategory.objects.create(
            catalog=self.catalog,
            source_id="361",
            name="锅具",
            depth=1,
            path="/13101/361/",
            parent=self.clothing,
        )
        payload = self._payload(
            "wok-1",
            [{"id": "1849", "name": "电子产品"}, {"id": "361", "name": "锅具"}],
        )

        self._import(payload)

        cookware.refresh_from_db()
        self.assertEqual(cookware.parent_id, self.electronics.pk)
        self.assertFalse(self._events().exists())


class ParseSpuRetailPriceTests(unittest.TestCase):
    """抓取价 → Spu.retail_price 的纯函数解析（2026-11-10）。

    解析失败返回 None（调用方保留旧值）；位数/格式必须匹配模型
    DecimalField(max_digits=18, decimal_places=4)。
    """

    def test_valid_prices_quantize_to_four_places(self):
        self.assertEqual(_parse_spu_retail_price("29.99"), Decimal("29.9900"))
        self.assertEqual(_parse_spu_retail_price("199"), Decimal("199.0000"))
        self.assertEqual(_parse_spu_retail_price(0), Decimal("0.0000"))
        self.assertEqual(_parse_spu_retail_price(" 12.5 "), Decimal("12.5000"))

    def test_invalid_prices_return_none(self):
        self.assertIsNone(_parse_spu_retail_price(None))
        self.assertIsNone(_parse_spu_retail_price(""))
        self.assertIsNone(_parse_spu_retail_price("   "))
        self.assertIsNone(_parse_spu_retail_price("abc"))
        self.assertIsNone(_parse_spu_retail_price("-1"))
        self.assertIsNone(_parse_spu_retail_price("NaN"))
        self.assertIsNone(_parse_spu_retail_price(10**15))  # 超过 14 位整数


class ParseRatingSummaryTests(unittest.TestCase):
    """源站评价汇总 → SpuDetail.rating_*（2026-11-10）。"""

    def test_parses_average_count_and_distribution(self):
        fields = _parse_rating_summary(
            {
                "rating_average": "4.5",
                "rating_count": 9,
                "rating_distribution": {"1": 1, "5": 7, "4": 1},
            }
        )
        self.assertEqual(fields["rating_count"], 9)
        self.assertEqual(fields["rating_average"], Decimal("4.50"))
        self.assertEqual(fields["rating_distribution"], {"1": 1, "5": 7, "4": 1})

    def test_empty_or_invalid_count_returns_nothing(self):
        self.assertEqual(_parse_rating_summary({}), {})
        self.assertEqual(_parse_rating_summary({"rating_count": 0}), {})
        self.assertEqual(_parse_rating_summary({"rating_count": "abc"}), {})

    def test_invalid_average_and_distribution_are_dropped(self):
        fields = _parse_rating_summary(
            {
                "rating_count": 3,
                "rating_average": "9.9",
                "rating_distribution": {"5": 2, "x": 1, "0": 4, "4": -1},
            }
        )
        self.assertEqual(fields["rating_count"], 3)
        self.assertNotIn("rating_average", fields)
        self.assertEqual(fields["rating_distribution"], {"5": 2})


@unittest.skipUnless(PARSER_AVAILABLE, "parsel is not installed")
class MerchantCategoryAndRetailPriceTests(CrawlerControlTestBase):
    """商家端品类（父品类推导）+ 抓取原价 → 零售价（2026-11-10）。

    - ``Spu.merchant_category``：``local_category`` 的父级（一级类目）经
      ``LOCAL_PARENT_MERCHANT_CATEGORY`` 推导（mobile-phones → electronics →
      ELECTRONICS）；只填空、绝不覆盖人工/管理端设置的值。
    - ``Spu.retail_price``：payload ``current_price``（抓取价=入库价=零售价），
      新建必填、重导覆盖；价格缺失/非法时保留旧值。
    """

    def setUp(self):
        super().setUp()
        self.make_account()
        self.job = self.make_job(name="Merchant category job")
        self.run = start_run(self.job)
        self.local_parent = LocalCategory.objects.create(
            name="电子产品",
            slug="electronics",
            depth=0,
            path="/electronics/",
        )
        self.local_child = LocalCategory.objects.create(
            name="手机",
            slug="mobile-phones",
            parent=self.local_parent,
            depth=1,
            path="/electronics/mobile-phones/",
        )
        self.source_category = SourceCategory.objects.get(
            catalog=self.catalog, source_id="l3-phones"
        )
        CategoryMapping.objects.create(
            local_category=self.local_child,
            source_category=self.source_category,
            is_primary=True,
        )

    def _payload(self, source_id="mc-1", price="199.00", sku_price=None):
        return {
            "source_id": source_id,
            "title": "Test phone",
            "currency": "GBP",
            "current_price": price,
            "skus": [
                {
                    "source_id": source_id,
                    "price": sku_price or price,
                    "availability": "IN_STOCK",
                    "specs": [],
                }
            ],
            "image_urls": [],
            "product_category_path": [],
        }

    def _import(self, payload):
        from joybuy_crawler.ingest import ingest_product_payload

        staging = ingest_product_payload(
            self.run,
            payload,
            source_system="joybuy",
            source_url="https://www.joybuy.co.uk/dp/phone/1",
            parser_version="joybuy_uk.v3",
            structure_version=2,
        )
        return import_staging_product(staging, market=self.market, currency=self.currency)

    def test_create_sets_merchant_category_and_retail_price(self):
        payload = self._payload()
        payload["source_category_id"] = "l3-phones"

        outcome = self._import(payload)

        self.assertEqual(outcome.spu.local_category_id, self.local_child.pk)
        self.assertEqual(outcome.spu.merchant_category, "ELECTRONICS")
        self.assertEqual(outcome.spu.retail_price, Decimal("199.0000"))

    def test_reimport_fills_empty_merchant_category(self):
        first = self._import(self._payload("mc-empty"))
        self.assertIsNone(first.spu.local_category_id)
        self.assertEqual(first.spu.merchant_category, "")

        payload = self._payload("mc-empty")
        payload["source_category_id"] = "l3-phones"
        second = self._import(payload)
        second.spu.refresh_from_db()

        self.assertEqual(second.spu.local_category_id, self.local_child.pk)
        self.assertEqual(second.spu.merchant_category, "ELECTRONICS")

    def test_manual_merchant_category_is_not_overwritten(self):
        payload = self._payload("mc-manual")
        payload["source_category_id"] = "l3-phones"

        outcome = self._import(payload)
        spu = outcome.spu
        self.assertEqual(spu.merchant_category, "ELECTRONICS")
        spu.merchant_category = "HOME"
        spu.save(update_fields=["merchant_category", "updated_at"])

        again = self._import(payload)
        again.spu.refresh_from_db()
        self.assertEqual(again.spu.merchant_category, "HOME")

    def test_reimport_updates_retail_price_from_payload(self):
        self._import(self._payload("mc-reprice"))

        second = self._import(self._payload("mc-reprice", price="249.50"))
        second.spu.refresh_from_db()

        self.assertEqual(second.spu.retail_price, Decimal("249.5000"))

    def test_invalid_price_keeps_old_retail_price(self):
        first = self._import(self._payload("mc-badprice"))
        self.assertEqual(first.spu.retail_price, Decimal("199.0000"))

        # 顶层原价非法但 SKU 价仍有效：SPU 零售价保留旧值，导入不因此失败。
        second = self._import(self._payload("mc-badprice", price="not-a-price", sku_price="199.00"))
        second.spu.refresh_from_db()

        self.assertEqual(second.spu.retail_price, Decimal("199.0000"))

    def test_missing_price_rejected_and_keeps_old_retail_price(self):
        first = self._import(self._payload("mc-missing"))
        self.assertEqual(first.spu.retail_price, Decimal("199.0000"))

        with self.assertRaises(StagingImportRejected):
            self._import(self._payload("mc-missing", price=""))

        first.spu.refresh_from_db()
        self.assertEqual(first.spu.retail_price, Decimal("199.0000"))

    def test_import_persists_crawled_rating_snapshot(self):
        """源站评分写入 SpuDetail，购物端才能在没有本地评价时显示评分。"""
        payload = self._payload("mc-rating")
        payload.update(
            {
                "rating_average": "4.5",
                "rating_count": 9,
                "rating_distribution": {"5": 7, "4": 1, "1": 1},
            }
        )
        outcome = self._import(payload)
        detail = outcome.spu.detail
        self.assertEqual(detail.rating_count, 9)
        self.assertEqual(detail.rating_average, Decimal("4.50"))
        self.assertEqual(detail.rating_distribution, {"5": 7, "4": 1, "1": 1})

        # 后续 payload 没有评分时不覆盖已有快照。
        self._import(self._payload("mc-rating"))
        detail.refresh_from_db()
        self.assertEqual(detail.rating_count, 9)
