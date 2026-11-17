"""商品详情增量解析（2026-11-09）：画廊 / 系列规格 / 图文子标题 / 规格表格 /
AI 摘要 / 视频，以及移动端图文详情的两步合并。

对应 `docs/14-crawler-product-detail-issues.md` §7（调试脚本已验证的行为）。
测试只使用小型合成 flight 片段，不提交真实页面 HTML。
"""

import json
import sys
import tempfile
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

PARSER_AVAILABLE = find_spec("parsel") is not None

PRODUCT_ID = "10404455"


def _js_escape(text: str) -> str:
    """模拟 Next.js 把 payload 写进 JS 字符串字面量的转义方式。"""

    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _flight_html(*chunks: dict, head: str = "") -> str:
    """把若干个 flight 片段塞进一个最小详情页。"""

    body = "\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks)
    return (
        "<html><body><h1>Test product</h1>"
        '<span class="crossOffPrice">£29.99</span>'
        '<span class="mainPrice">£19.99</span>'
        f"{head}"
        f'<script>self.__next_f.push([1,"{_js_escape(body)}"])</script>'
        "</body></html>"
    )


def _server_product(*, media=None, series=None, colors=None) -> dict:
    floors = []
    if media is not None:
        floors.append({"floorId": "productMainImageFloor", "data": {"mediaData": media}})
    if series is not None:
        floors.append(
            {
                "floorId": "productSeriesFloor",
                "data": {"title": "系列", "series": series},
            }
        )
    if colors is not None:
        floors.append(
            {
                "floorId": "productSelectedFloor",
                "data": {"colorSizePartList": colors},
            }
        )
    return {"serverProduct": {"data": {"floors": floors}}}


MEDIA = [
    {"image": True, "bigImageUrl": "jfsintlpro-000-product/t1/aaa.jpg"},
    # 同一张图另一个尺寸 / 另一个 CDN 主机：必须按路径去重。
    {
        "image": True,
        "bigImageUrl": (
            "https://images3.joy-sourcing.com/product/s598x598_jfsintlpro-000-product/t1/aaa.jpg"
        ),
    },
    # 服务/保障 icon（s32 + -000-com）必须丢弃。
    {
        "image": True,
        "bigImageUrl": (
            "https://images3.joy-sourcing.com/product/s32x32_jfsintlpro-000-com/benefit.png.webp"
        ),
    },
    # 非 /product/ 的静态资源也必须丢弃。
    {"image": True, "bigImageUrl": "https://images4.joy-sourcing.com/static/st.png.webp"},
    {"image": True, "bigImageUrl": "jfsintlpro-000-product/t1/bbb.jpg"},
    {
        "mediaType": 2,
        "video": True,
        "videoUrl": "https://video.example/1.mp4",
        "duration": 23,
        "coverImageUrl": "https://images1.joy-sourcing.com/da/cover.jpg",
        "videoId": "vid-1",
    },
]

SERIES = [
    {"name": "1TB", "skus": ["9001"], "id": "1"},
    {"name": "256GB", "skus": [PRODUCT_ID], "id": "2"},
]

COLORS = [
    {
        "C-P#dimension&dimension": {"dimTitle": "颜色", "dimensionNumber": 1},
        "buttonPartList": [
            {
                "C-P#dimensionButton&dimensionButton": {
                    "text": "白色",
                    "imgUrl": "jfsintlpro-000-product/t1/white.jpg",
                    "skuList": [PRODUCT_ID],
                }
            },
            {
                "C-P#dimensionButton&dimensionButton": {
                    "text": "黑色",
                    "imgUrl": "jfsintlpro-000-product/t1/black.jpg",
                    "skuList": ["9002"],
                }
            },
        ],
    }
]

SUMMARY_CHUNK = {
    "productId": PRODUCT_ID,
    "title": "Test product",
    "crossOffPrice": "29.99",
    "mainPrice": "19.99",
    "aiSummary": {
        "summaryContent": "多数买家反馈做工扎实、加热快。",
        "summaryText": "内容由人工智能总结自用户评价",
    },
    "aiTagList": [{"tagName": "做工扎实"}, {"tagName": "加热快"}],
}

MOBILE_FLOORS = {
    "structuredFloors": [
        {
            "data": {
                "structuredName": "核心卖点与优势",
                "mode": 9,
                "moduleType": 2,
                "modules": [
                    {
                        "moduleCode": "pure-text",
                        "dataBatch": {
                            "moduleData": [
                                {
                                    "title": "材质与工艺",
                                    "text": "不锈钢锅体，导热均匀。",
                                    "__types__": {"title": "TEXT", "text": "TEXT_AREA"},
                                }
                            ]
                        },
                    }
                ],
            }
        },
        {
            "data": {
                "structuredName": "产品详情",
                "mode": 10,
                "moduleType": 2,
                "modules": [
                    {
                        "moduleCode": "Image-Text",
                        "dataBatch": {
                            "moduleData": [
                                {
                                    "image": [
                                        {
                                            "imageUrl": (
                                                "https://images1.joy-sourcing.com/da/detail-1.jpg"
                                            )
                                        }
                                    ]
                                },
                                {"title": "使用说明", "text": "首次使用请先清洗。"},
                            ]
                        },
                    }
                ],
            }
        },
        {
            "data": {
                "structuredName": "材质与规格",
                "mode": 8,
                "moduleType": 3,
                "modules": [
                    {
                        "dataBatch": {
                            "moduleData": {
                                "extendPartList": [
                                    {
                                        "attributePartList": [
                                            {
                                                "C-P#Attribute&attributeBasic": {
                                                    "attributeName": "材质",
                                                    "attributes": "不锈钢",
                                                    "attributeSort": 3,
                                                }
                                            },
                                            {
                                                "C-P#Attribute&attributeBasic": {
                                                    "attributeName": "用途",
                                                    "attributes": "适用于燃气灶,适用于电磁炉",
                                                    "attributeSort": 1,
                                                }
                                            },
                                        ]
                                    }
                                ]
                            }
                        }
                    }
                ],
            }
        },
    ]
}

MOBILE_HTML = _flight_html(MOBILE_FLOORS)

PC_SECTIONS_HEAD = """
<div class="MuiAccordion-root Accordion_root">
  <div class="Accordion_title">商品描述</div>
  <div class="MuiAccordionDetails-root">
    <div aria-label="rich text container">
      <p><strong>产品特点：</strong>1.8L 小巧容量</p>
      <p>普通段落文字。</p>
    </div>
  </div>
</div>
<div class="MuiAccordion-root Accordion_root">
  <div class="Accordion_title">重要信息</div>
  <div class="MuiAccordionDetails-root">
    <img src="https://images1.joy-sourcing.com/da/warning.jpg"/>
  </div>
</div>
"""


@unittest.skipUnless(PARSER_AVAILABLE, "parsel is not installed")
class DetailExtrasParserTests(unittest.TestCase):
    def _product(self, **kwargs):
        from joybuy_crawler.parsers.joybuy_uk import parse_uk_product_detail

        html = _flight_html(
            _server_product(
                media=kwargs.pop("media", MEDIA),
                series=kwargs.pop("series", SERIES),
                colors=kwargs.pop("colors", COLORS),
            ),
            kwargs.pop("summary", SUMMARY_CHUNK),
            head=kwargs.pop("head", ""),
        )
        return parse_uk_product_detail(
            html, source_url=f"https://www.joybuy.co.uk/dp/kettle/{PRODUCT_ID}"
        )

    def test_gallery_keeps_every_big_image_and_drops_icons(self):
        product = self._product()
        self.assertEqual(len(product.gallery), 2)
        self.assertTrue(all("s1248x1248" in url for url in product.gallery), product.gallery)
        self.assertTrue(product.gallery[0].endswith("aaa.jpg!q70.webp"))
        self.assertTrue(product.gallery[1].endswith("bbb.jpg!q70.webp"))
        joined = " ".join(product.gallery)
        self.assertNotIn("-000-com", joined)
        self.assertNotIn("st.png", joined)

    def test_series_then_colour_options_fill_sku_specs(self):
        product = self._product()
        self.assertEqual([option["name"] for option in product.spec_options], ["系列", "颜色"])
        series = product.spec_options[0]
        self.assertEqual([value["value"] for value in series["values"]], ["1TB", "256GB"])
        color = product.spec_options[1]["values"][0]
        self.assertEqual(color["value"], "白色")
        self.assertIn("s96x96_", color["image_url"])
        self.assertEqual(
            product.skus[0]["specs"],
            [{"name": "系列", "value": "256GB"}, {"name": "颜色", "value": "白色"}],
        )

    def test_single_value_dimension_is_applied_to_the_only_sku(self):
        # 当前 SKU 不在任何 skuList 里（页面换版时会出现）：只有单值维度可用。
        product = self._product(
            series=[{"name": "1TB", "skus": ["9001"]}, {"name": "256GB", "skus": ["9003"]}],
            colors=[
                {
                    "C-P#dimension&dimension": {"dimTitle": "颜色"},
                    "buttonPartList": [
                        {
                            "C-P#dimensionButton&dimensionButton": {
                                "text": "白色",
                                "skuList": ["9009"],
                            }
                        }
                    ],
                }
            ],
        )
        self.assertEqual(product.skus[0]["specs"], [{"name": "颜色", "value": "白色"}])

    def test_ai_summary_and_tags_come_from_the_inline_block(self):
        product = self._product()
        self.assertEqual(product.ai_summary, "多数买家反馈做工扎实、加热快。")
        self.assertEqual(product.ai_summary_title, "内容由人工智能总结自用户评价")
        self.assertEqual(product.ai_summary_tags, ["做工扎实", "加热快"])
        payload = product.to_payload()
        self.assertEqual(payload["ai_summary_tags"], ["做工扎实", "加热快"])
        self.assertEqual(
            payload["joybuy"]["aiReviewSummary"]["text"],
            "多数买家反馈做工扎实、加热快。",
        )

    def test_no_ai_summary_is_invented_when_absent(self):
        product = self._product(summary={"productId": PRODUCT_ID})
        self.assertEqual(product.ai_summary, "")
        self.assertEqual(product.ai_summary_tags, [])
        self.assertNotIn("aiReviewSummary", product.to_payload()["joybuy"])

    def test_video_media_entry_is_parsed(self):
        product = self._product()
        self.assertEqual(len(product.videos), 1)
        video = product.videos[0]
        self.assertEqual(video["url"], "https://video.example/1.mp4")
        self.assertEqual(video["duration"], 23)
        self.assertEqual(video["cover"], "https://images1.joy-sourcing.com/da/cover.jpg")
        self.assertEqual(video["video_id"], "vid-1")
        payload = product.to_payload()
        self.assertEqual(payload["video_urls"], ["https://video.example/1.mp4"])
        self.assertEqual(payload["joybuy"]["videos"][0]["url"], "https://video.example/1.mp4")

    def test_pc_accordion_strong_is_a_heading_and_images_are_kept(self):
        product = self._product(head=PC_SECTIONS_HEAD)
        titles = [section["title"] for section in product.content_sections]
        self.assertEqual(titles, ["商品描述", "重要信息"])
        blocks = product.content_sections[0]["blocks"]
        self.assertEqual(blocks[0], {"type": "heading", "text": "产品特点："})
        self.assertEqual(blocks[1], {"type": "paragraph", "text": "1.8L 小巧容量"})
        self.assertEqual(blocks[2], {"type": "paragraph", "text": "普通段落文字。"})
        self.assertEqual(
            product.content_sections[1]["images"],
            ["https://images1.joy-sourcing.com/da/warning.jpg"],
        )
        # 扁平文本兜底仍在，子标题用 ## 标记。
        self.assertIn("## 产品特点：", product.description)
        self.assertIn("【重要信息】", product.description)
        self.assertIn(
            "https://images1.joy-sourcing.com/da/warning.jpg",
            product.to_payload()["detail_image_urls"],
        )


@unittest.skipUnless(PARSER_AVAILABLE, "parsel is not installed")
class MobileDetailParserTests(unittest.TestCase):
    def test_structured_floors_yield_blocks_images_and_tables(self):
        from joybuy_crawler.parsers.joybuy_uk import parse_uk_mobile_detail

        sections, specifications = parse_uk_mobile_detail(MOBILE_HTML)
        self.assertEqual(
            [section["title"] for section in sections],
            ["核心卖点与优势", "产品详情"],
        )
        first = sections[0]
        self.assertEqual(first["blocks"][0], {"type": "heading", "text": "材质与工艺"})
        self.assertEqual(first["blocks"][1]["type"], "paragraph")
        self.assertEqual(
            sections[1]["images"],
            ["https://images1.joy-sourcing.com/da/detail-1.jpg"],
        )
        # 行顺序按源站，不按 attributeSort 重排。
        self.assertEqual(
            [(item["group"], item["name"], item["value"]) for item in specifications],
            [
                ("材质与规格", "材质", "不锈钢"),
                ("材质与规格", "用途", "适用于燃气灶,适用于电磁炉"),
            ],
        )

    def test_merge_prefers_mobile_and_fills_missing_pc_sections(self):
        from joybuy_crawler.parsers.joybuy_uk import (
            merge_mobile_detail,
            parse_uk_product_detail,
        )

        html = _flight_html(
            _server_product(media=MEDIA, series=SERIES, colors=COLORS),
            SUMMARY_CHUNK,
            head=PC_SECTIONS_HEAD,
        )
        product = parse_uk_product_detail(
            html, source_url=f"https://www.joybuy.co.uk/dp/kettle/{PRODUCT_ID}"
        )
        self.assertEqual(product.specifications, [])

        merge_mobile_detail(product, MOBILE_HTML)

        titles = [section["title"] for section in product.content_sections]
        # 移动端为先；PC 独有的「重要信息」补在后面；同名区块不重复。
        self.assertEqual(titles, ["核心卖点与优势", "产品详情", "商品描述", "重要信息"])
        self.assertEqual(product.specifications[0]["group"], "材质与规格")
        self.assertEqual(
            product.specification_tables,
            [
                {
                    "title": "材质与规格",
                    "columns": ["属性", "值"],
                    "rows": [
                        {"name": "材质", "value": "不锈钢"},
                        {"name": "用途", "value": "适用于燃气灶,适用于电磁炉"},
                    ],
                }
            ],
        )
        self.assertIn("## 材质与工艺", product.description)
        self.assertIn("https://images1.joy-sourcing.com/da/detail-1.jpg", product.detail_images)
        self.assertIn("https://images1.joy-sourcing.com/da/warning.jpg", product.detail_images)
        # 规格区块不进 description 正文（只以表格形式保存）。
        self.assertNotIn("【材质与规格】", product.description)

    def test_merge_without_mobile_data_keeps_pc_result(self):
        from joybuy_crawler.parsers.joybuy_uk import (
            merge_mobile_detail,
            parse_uk_product_detail,
        )

        html = _flight_html(
            _server_product(media=MEDIA, series=SERIES, colors=COLORS),
            SUMMARY_CHUNK,
            head=PC_SECTIONS_HEAD,
        )
        product = parse_uk_product_detail(
            html, source_url=f"https://www.joybuy.co.uk/dp/kettle/{PRODUCT_ID}"
        )
        merge_mobile_detail(product, "<html><body>no flight here</body></html>")
        self.assertEqual(
            [section["title"] for section in product.content_sections],
            ["商品描述", "重要信息"],
        )
        self.assertEqual(product.specifications, [])
        self.assertEqual(product.specification_tables, [])


class SpecEnrichmentImportTests(CrawlerControlTestBase):
    """旧 SKU 规格为空、重抓后补上规格：沿用同一 SKU，不新增也不报错。"""

    def setUp(self):
        super().setUp()
        self.make_account()
        self.run = start_run(self.make_job(name="Spec enrichment job"))

    def _payload(self, specs):
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
                    "specs": specs,
                }
            ],
            "image_urls": [],
        }

    def _import(self, specs):
        from unittest import mock

        from joybuy_crawler.ingest import ingest_product_payload

        from crawler_control.import_services import import_staging_product

        staging = ingest_product_payload(
            self.run,
            self._payload(specs),
            source_system="joybuy",
            source_url="https://www.joybuy.co.uk/dp/wok/10003152",
            parser_version="joybuy_uk.v2",
            structure_version=2,
        )
        with mock.patch("crawler_control.import_services._fetch_image_bytes", return_value=None):
            return import_staging_product(staging, market=self.market, currency=self.currency)

    def test_empty_specs_are_enriched_without_duplicating_the_sku(self):
        from catalog.models import Sku

        first = self._import([])
        sku_pk = first.skus[0].pk
        self.assertEqual(first.skus[0].specification, {})

        second = self._import([{"name": "系列", "value": "蜂窝炒锅 30cm"}])

        self.assertEqual(second.skus[0].pk, sku_pk)
        self.assertEqual(second.skus[0].specification, {"系列": "蜂窝炒锅 30cm"})
        self.assertEqual(Sku.objects.count(), 1)

    def test_conflicting_existing_spec_still_raises(self):
        from crawler_control.domain import ImportSourceConflict

        self._import([{"name": "系列", "value": "蜂窝炒锅 30cm"}])
        with self.assertRaises(ImportSourceConflict) as ctx:
            self._import([{"name": "系列", "value": "精铁锅 32cm"}])
        self.assertIn("来源 SKU", str(ctx.exception))
        self.assertIn("另一个规格", str(ctx.exception))


class DatasetVideoTests(CrawlerControlTestBase):
    """视频落到 <商品>/videos/ 并写进数据集索引（2026-11-09）。"""

    def _payload(self):
        return {
            "source_id": "104001",
            "title": "Kettle",
            "videos": [{"url": "https://video.example/1.mp4", "duration": 23}],
            "joybuy": {"breadcrumbs": [{"name": "Electronics"}]},
        }

    def test_video_is_written_and_indexed(self):
        from joybuy_crawler.dataset import save_product

        with tempfile.TemporaryDirectory() as tmp:
            index = save_product(
                Path(tmp),
                breadcrumb_names=["Electronics"],
                payload=self._payload(),
                resolve_image=lambda url, timeout=30: (url, b"img"),
                resolve_video=lambda url: b"video-bytes",
            )
            product_dir = Path(tmp) / "electronics" / "104001"
            video = product_dir / "videos" / "01.mp4"
            self.assertTrue(video.exists())
            self.assertEqual(video.read_bytes(), b"video-bytes")
            self.assertEqual(index["videos"], [str(Path("videos") / "01.mp4")])
            line = json.loads(
                (product_dir.parent / "dataset_index.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()[0]
            )
            self.assertEqual(line["videos"], [str(Path("videos") / "01.mp4")])

    def test_video_failure_is_recorded_not_fatal(self):
        from joybuy_crawler.dataset import save_product

        def broken(url):
            raise RuntimeError("CDN 403")

        with tempfile.TemporaryDirectory() as tmp:
            index = save_product(
                Path(tmp),
                breadcrumb_names=["Electronics"],
                payload=self._payload(),
                resolve_image=lambda url, timeout=30: (url, b"img"),
                resolve_video=broken,
            )
            self.assertEqual(index["videos"], [])
            self.assertEqual(index["video_errors"][0]["url"], "https://video.example/1.mp4")


class _FakeResponse:
    def __init__(self, url, text, meta=None, status=200):
        self.url = url
        self.text = text
        self.meta = meta or {}
        self.status = status
        self.body = text.encode("utf-8")


def _variant_price_page_html(cross="21.99", main="19.99"):
    """WP-45：合成一个变体自己的 /dp/<sku> 价格页（只带 productPriceFloor）。"""

    price_floor = {
        "floorId": "productPriceFloor",
        "data": {"crossOffPrice": cross, "mainPrice": main},
    }
    return _flight_html({"serverProduct": {"data": {"floors": [price_floor]}}})


@unittest.skipUnless(PARSER_AVAILABLE, "parsel is not installed")
class MobileDetailSpiderFlowTests(CrawlerControlTestBase):
    """两步请求：PC 详情 → /dg/<sku> → 只产出一条商品 item。"""

    def setUp(self):
        super().setUp()
        self.make_account()
        self.run = start_run(self.make_job(name="Mobile detail job"))
        from joybuy_crawler.spiders.joybuy_run import JoybuyRunSpider

        self.spider = JoybuyRunSpider(run_public_id=str(self.run.public_id))

    def _pc_response(self):
        html = _flight_html(
            _server_product(media=MEDIA, series=SERIES, colors=COLORS),
            SUMMARY_CHUNK,
            head=PC_SECTIONS_HEAD,
        )
        return _FakeResponse(
            url=f"https://www.joybuy.co.uk/dp/kettle/{PRODUCT_ID}",
            text=html,
            meta={
                "target": {"category_name": "Electronics", "source_category_id": "l2-electronics"}
            },
        )

    def _drain_variant_chain(self, steps):
        """WP-45：变体价格补抓链上逐个应答，直到产出商品 item。"""

        steps = list(steps)
        while steps and not (isinstance(steps[0], dict) and steps[0].get("type") == "product"):
            request = steps.pop(0)
            response = _FakeResponse(
                url=request.url,
                text=_variant_price_page_html(),
                meta=request.meta,
            )
            steps = list(self.spider.parse_variant_price(response)) + steps
        return steps

    def test_detail_then_mobile_request_yields_one_item(self):
        first = list(self.spider.parse_detail(self._pc_response()))
        self.assertEqual(len(first), 1)
        request = first[0]
        self.assertTrue(request.url.endswith(f"/dg/{PRODUCT_ID}"))
        self.assertTrue(request.url.startswith("https://www.joybuy.co.uk/"))
        self.assertIn(PRODUCT_ID, request.meta["product"].source_id)

        items = list(
            self.spider.parse_mobile_detail(
                _FakeResponse(url=request.url, text=MOBILE_HTML, meta=request.meta)
            )
        )
        items = self._drain_variant_chain(items)
        self.assertEqual(len(items), 1)
        payload = items[0]["payload"]
        self.assertEqual(payload["source_id"], PRODUCT_ID)
        self.assertEqual(payload["specification_tables"][0]["title"], "材质与规格")
        self.assertEqual(len(payload["image_urls"]), 2)
        self.assertEqual(payload["videos"][0]["url"], "https://video.example/1.mp4")
        self.assertEqual(items[0]["breadcrumb_names"][0], "Electronics")

        from crawler_control.models import CrawlRunEvent

        codes = set(CrawlRunEvent.objects.filter(run=self.run).values_list("code", flat=True))
        self.assertIn("PRODUCT_PARSED", codes)
        self.assertIn("MOBILE_DETAIL_MERGED", codes)

    def test_mobile_failure_still_yields_the_pc_item(self):
        first = list(self.spider.parse_detail(self._pc_response()))
        request = first[0]

        class _Failure:
            value = TimeoutError("robots.txt forbids /dg/")
            request = None

        failure = _Failure()
        failure.request = type("Req", (), {"meta": request.meta, "url": request.url})()
        items = list(self.spider.mobile_detail_failed(failure))
        items = self._drain_variant_chain(items)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["payload"]["specifications"], [])

        from crawler_control.models import CrawlRunEvent

        self.assertTrue(
            CrawlRunEvent.objects.filter(run=self.run, code="MOBILE_DETAIL_FAILED").exists()
        )
