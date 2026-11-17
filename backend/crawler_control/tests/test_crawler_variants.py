"""WP-45 阶段 1：变体列表（``variants`` payload 字段）契约测试。

对应 `docs/14-crawler-product-detail-issues.md` §10 与 WP-45：每个规格组合
（源 sku id + 真实规格名值对 + 价格 + 库存状态码 + 规格图 + 主变体标记）。
测试只使用小型合成 flight 片段，不提交真实页面 HTML。
"""

import json
import sys
import unittest
from importlib.util import find_spec
from pathlib import Path

CRAWLER_DIR = Path(__file__).resolve().parents[3] / "crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

from crawler_control.services import start_run  # noqa: E402
from crawler_control.tests.test_crawler_control_domain import (  # noqa: E402
    CrawlerControlTestBase,
)
from crawler_control.tests.test_crawler_detail_extras import (  # noqa: E402
    MEDIA,
    PC_SECTIONS_HEAD,
    PRODUCT_ID,
    SUMMARY_CHUNK,
    _flight_html,
    _server_product,
)

PARSER_AVAILABLE = find_spec("parsel") is not None

OTHER_SKU = "9002"
THIRD_SKU = "9003"

VARIANT_SERIES = [
    {"name": "1TB", "skus": [THIRD_SKU], "id": "1"},
    {"name": "256GB", "skus": [PRODUCT_ID, OTHER_SKU], "id": "2"},
]

#: 与 test_crawler_detail_extras.COLORS 同构，但带上 stockState，并把两个
#: 颜色分别指向两个真实源 sku（对应「一个规格组合 = 一个源 sku」的实测结构）。
VARIANT_COLORS = [
    {
        "C-P#dimension&dimension": {"dimTitle": "颜色", "dimensionNumber": 1},
        "buttonPartList": [
            {
                "C-P#dimensionButton&dimensionButton": {
                    "text": "白色",
                    "imgUrl": "jfsintlpro-000-product/t1/white.jpg",
                    "skuList": [PRODUCT_ID],
                    "stockState": 34,
                }
            },
            {
                "C-P#dimensionButton&dimensionButton": {
                    "text": "黑色",
                    "imgUrl": "jfsintlpro-000-product/t1/black.jpg",
                    "skuList": [OTHER_SKU],
                    "stockState": 33,
                }
            },
        ],
    }
]

VARIANT_SKU_STATUS = {OTHER_SKU: "0", PRODUCT_ID: "-2"}


def _detail_html(*, series=None, colors=None, sku_status=None, media=None):
    server_product = _server_product(media=media, series=series, colors=colors)
    if sku_status is not None:
        for floor in server_product["serverProduct"]["data"]["floors"]:
            if floor.get("floorId") == "productSelectedFloor":
                floor["data"]["skuStatus"] = sku_status
    return _flight_html(server_product, SUMMARY_CHUNK, head=PC_SECTIONS_HEAD)


def _parse(html, source_id=PRODUCT_ID):
    from joybuy_crawler.parsers.joybuy_uk import parse_uk_product_detail

    return parse_uk_product_detail(
        html, source_url=f"https://www.joybuy.co.uk/dp/kettle/{source_id}"
    )


def _variant_price_page(cross=None, main=None):
    """合成一个变体自己的 /dp/<sku> 页（只带 productPriceFloor）。"""

    price_floor = {"floorId": "productPriceFloor", "data": {}}
    if cross is not None:
        price_floor["data"]["crossOffPrice"] = cross
    if main is not None:
        price_floor["data"]["mainPrice"] = main
    server_product = {"serverProduct": {"data": {"floors": [price_floor]}}}
    return _flight_html(server_product)


@unittest.skipUnless(PARSER_AVAILABLE, "parsel is not installed")
class VariantParserTests(unittest.TestCase):
    """extract_variants / payload 契约 / 变体价格页提取。"""

    def test_variants_carry_spec_pairs_primary_and_raw_state(self):
        product = _parse(
            _detail_html(
                series=VARIANT_SERIES,
                colors=VARIANT_COLORS,
                sku_status=VARIANT_SKU_STATUS,
            )
        )
        payload = product.to_payload()
        variants = payload["variants"]
        # 系列轴在前（1TB 一个 sku + 256GB 两个 sku），颜色轴补充第二个维度。
        self.assertEqual(
            [v["source_sku_id"] for v in variants],
            [THIRD_SKU, PRODUCT_ID, OTHER_SKU],
        )
        by_sku = {v["source_sku_id"]: v for v in variants}

        primary = by_sku[PRODUCT_ID]
        self.assertTrue(primary["is_primary"])
        self.assertEqual(primary["specification"], {"系列": "256GB", "颜色": "白色"})
        # 主变体继承页面原价（crossOffPrice 优先的业务规则）。
        self.assertEqual(primary["price"], "29.99")
        self.assertEqual(primary["price_source"], "detail_page")
        self.assertIn("s96x96", primary["image_url"])
        self.assertIn("white.jpg", primary["image_url"])
        self.assertEqual(primary["stock_state"], 34)
        self.assertEqual(primary["sku_status"], "-2")
        self.assertEqual(primary["currency"], "GBP")

        other = by_sku[OTHER_SKU]
        self.assertFalse(other["is_primary"])
        self.assertEqual(other["specification"], {"系列": "256GB", "颜色": "黑色"})
        self.assertIsNone(other["price"])
        self.assertEqual(other["price_source"], "")
        self.assertIn("black.jpg", other["image_url"])
        self.assertEqual(other["stock_state"], 33)
        self.assertEqual(other["sku_status"], "0")

        third = by_sku[THIRD_SKU]
        self.assertEqual(third["specification"], {"系列": "1TB"})
        # 系列轴按钮没有规格图/库存信息：留空而不是编造。
        self.assertEqual(third["image_url"], "")
        self.assertIsNone(third["stock_state"])
        self.assertIsNone(third["sku_status"])

        # native（joybuy）块同样携带 variants。
        self.assertEqual(payload["joybuy"]["variants"], variants)

    def test_product_without_spec_axes_has_empty_variants(self):
        """没有规格轴的商品 variants 为空列表 —— 旧 payload 导入行为不变。"""

        product = _parse(_detail_html(media=MEDIA))
        payload = product.to_payload()
        self.assertEqual(payload["variants"], [])
        self.assertEqual(payload["joybuy"]["variants"], [])

    def test_variant_price_page_prefers_the_original_price(self):
        from joybuy_crawler.parsers.joybuy_uk import extract_variant_price

        self.assertEqual(
            extract_variant_price(_variant_price_page(cross="30.99", main="20.99")),
            "30.99",
        )
        self.assertEqual(extract_variant_price(_variant_price_page(main="20.99")), "20.99")
        self.assertIsNone(extract_variant_price(_variant_price_page()))
        # 与主页面同规则：风控页/空页返回 None，不抛异常。
        self.assertIsNone(extract_variant_price(_detail_html(media=MEDIA)))

    def test_quality_rules_keep_variants_untouched(self):
        """质量规则不认识 variants 也不能破坏它（向后兼容的守门断言）。"""

        from joybuy_crawler.quality import apply_product_rules

        payload = _parse(
            _detail_html(
                series=VARIANT_SERIES,
                colors=VARIANT_COLORS,
                sku_status=VARIANT_SKU_STATUS,
            )
        ).to_payload()
        cleaned, outcome = apply_product_rules(
            payload, source_url=f"https://www.joybuy.co.uk/dp/kettle/{PRODUCT_ID}"
        )
        self.assertFalse(outcome.fatal)
        self.assertEqual(cleaned["variants"], payload["variants"])


class _FakeResponse:
    def __init__(self, url, text, meta=None, status=200):
        self.url = url
        self.text = text
        self.meta = meta or {}
        self.status = status
        self.body = text.encode("utf-8")


class _FakeFailure:
    def __init__(self, request, value=None):
        self.request = request
        self.value = value or TimeoutError("variant price page failed")


@unittest.skipUnless(PARSER_AVAILABLE, "parsel is not installed")
class VariantSpiderFlowTests(CrawlerControlTestBase):
    """正式链路：PC 详情 → /dg/ → 逐个变体价格页 → 只产出一条商品 item。"""

    def setUp(self):
        super().setUp()
        self.make_account()
        self.run = start_run(self.make_job(name="Variant price job"))
        from joybuy_crawler.spiders.joybuy_run import JoybuyRunSpider

        self.spider = JoybuyRunSpider(run_public_id=str(self.run.public_id))

    def _pc_response(self):
        return _FakeResponse(
            url=f"https://www.joybuy.co.uk/dp/kettle/{PRODUCT_ID}",
            text=_detail_html(
                series=VARIANT_SERIES,
                colors=VARIANT_COLORS,
                sku_status=VARIANT_SKU_STATUS,
            ),
            meta={
                "target": {
                    "category_name": "Electronics",
                    "source_category_id": "l2-electronics",
                }
            },
        )

    def _drain_variant_chain(self, first_yield):
        """按爬虫真实回调顺序走完整条链，返回最终 item。"""

        from crawler_control.tests.test_crawler_detail_extras import MOBILE_HTML

        pending = list(first_yield)
        item = None
        guard = 0
        while pending and not item:
            guard += 1
            self.assertLess(guard, 30, "变体价格链没有收敛，疑似死循环")
            step = pending.pop(0)
            if isinstance(step, dict) and step.get("type") == "product":
                item = step
                break
            url = step.url
            if "/dg/" in url:
                response = _FakeResponse(url=url, text=MOBILE_HTML, meta=step.meta)
                pending = list(self.spider.parse_mobile_detail(response))
            else:
                response = _FakeResponse(
                    url=url,
                    text=_variant_price_page(cross="30.99", main="20.99"),
                    meta=step.meta,
                )
                pending = list(self.spider.parse_variant_price(response))
        self.assertIsNotNone(item, "变体价格链没有产出商品 item")
        return item

    def test_chain_fetches_every_variant_then_yields_one_item(self):
        first = list(self.spider.parse_detail(self._pc_response()))
        self.assertEqual(len(first), 1)
        self.assertIn("/dg/", first[0].url)

        item = self._drain_variant_chain(first)
        payload = item["payload"]
        self.assertEqual(payload["source_id"], PRODUCT_ID)
        variants = payload["variants"]
        self.assertEqual(len(variants), 3)
        by_sku = {v["source_sku_id"]: v for v in variants}
        # 两个非主变体都从自己的 /dp/<sku> 页补到了价格。
        for sku in (OTHER_SKU, THIRD_SKU):
            self.assertEqual(by_sku[sku]["price"], "30.99")
            self.assertEqual(by_sku[sku]["price_source"], "variant_page")
        self.assertEqual(by_sku[PRODUCT_ID]["price"], "29.99")
        self.assertEqual(by_sku[PRODUCT_ID]["price_source"], "detail_page")

        from crawler_control.models import CrawlRunEvent

        self.assertTrue(
            CrawlRunEvent.objects.filter(run=self.run, code="VARIANT_PRICES_MERGED").exists()
        )

    def test_variant_price_failure_keeps_price_empty_and_yields_item(self):
        first = list(self.spider.parse_detail(self._pc_response()))
        mobile_request = first[0]
        pending = list(
            self.spider.parse_mobile_detail(
                _FakeResponse(
                    url=mobile_request.url,
                    text=json.dumps({"structuredFloors": []}),
                    meta=mobile_request.meta,
                )
            )
        )
        # 第一个变体价格请求失败：价格留空，链继续并最终产出 item。
        # 注意先取出本次请求对应的 sku：meta 在链上被复用，后续会被改写。
        failed_sku = pending[0].meta["variant_sku_id"]
        failure = _FakeFailure(pending[0])
        pending = list(self.spider.variant_price_failed(failure))
        item = self._drain_variant_chain(pending)
        by_sku = {v["source_sku_id"]: v for v in item["payload"]["variants"]}
        self.assertIsNone(by_sku[failed_sku]["price"])
        self.assertEqual(by_sku[failed_sku]["price_source"], "")
        # 其余变体不受单次失败影响。
        self.assertEqual(by_sku[PRODUCT_ID]["price_source"], "detail_page")

    def test_disabled_setting_yields_item_without_price_fetches(self):
        self.spider._variant_prices_enabled = lambda: False
        first = list(self.spider.parse_detail(self._pc_response()))
        pending = list(
            self.spider.parse_mobile_detail(
                _FakeResponse(
                    url=first[0].url,
                    text=json.dumps({"structuredFloors": []}),
                    meta=first[0].meta,
                )
            )
        )
        items = [step for step in pending if isinstance(step, dict)]
        self.assertEqual(len(items), 1)
        by_sku = {v["source_sku_id"]: v for v in items[0]["payload"]["variants"]}
        self.assertEqual(by_sku[PRODUCT_ID]["price"], "29.99")
        self.assertIsNone(by_sku[OTHER_SKU]["price"])

    def test_price_limit_caps_the_number_of_variant_requests(self):
        self.spider._variant_price_limit = lambda: 1
        first = list(self.spider.parse_detail(self._pc_response()))
        pending = list(
            self.spider.parse_mobile_detail(
                _FakeResponse(
                    url=first[0].url,
                    text=json.dumps({"structuredFloors": []}),
                    meta=first[0].meta,
                )
            )
        )
        item = self._drain_variant_chain(pending)
        by_sku = {v["source_sku_id"]: v for v in item["payload"]["variants"]}
        priced = [v for v in item["payload"]["variants"] if v["price_source"] == "variant_page"]
        self.assertEqual(len(priced), 1)
        # 主变体价格不受上限影响。
        self.assertEqual(by_sku[PRODUCT_ID]["price_source"], "detail_page")


if __name__ == "__main__":
    unittest.main()
