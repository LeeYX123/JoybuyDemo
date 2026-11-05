"""Review aggregates and the two-level breadcrumb rule (2026-11-05).

Requirement: review *content* is never crawled. Only the 1–5 star
counts, the average, the total count and — when the page renders one —
the AI-written summary are kept. Categories are recorded two levels deep.
"""

import json
import re
import sys
import unittest
from pathlib import Path

CRAWLER_DIR = Path(__file__).resolve().parents[3] / "crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

FIXTURE = CRAWLER_DIR / "fixtures" / "product_detail_reviews_v2.html"

try:
    import parsel  # noqa: F401

    SCRAPY_AVAILABLE = True
except ImportError:  # pragma: no cover - parser tests need parsel
    SCRAPY_AVAILABLE = False

_FLIGHT_CALL = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', re.DOTALL)


def _escape(text: str) -> str:
    """Mirror how Next.js writes the payload into a JS string literal."""

    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def with_flight(html: str, flight_text: str) -> str:
    """Swap the fixture's flight payload for a variant under test."""

    return _FLIGHT_CALL.sub(
        lambda _match: f'self.__next_f.push([1,"{_escape(flight_text)}"])',
        html,
        count=1,
    )


def review_flight(*, ai_summary: str | None, stars: str = "4.8", counts=None, total=47):
    counts = counts or {"1": 1, "2": 1, "3": 2, "4": 9, "5": 34}
    rating_slot = (
        '19c:{"commentCount":%d,"averageScore":%s,'
        '"score1Count":%d,"score2Count":%d,"score3Count":%d,'
        '"score4Count":%d,"score5Count":%d,"tnInfo":null}'
        % (
            total,
            "4.8" if total else "5",
            counts["1"],
            counts["2"],
            counts["3"],
            counts["4"],
            counts["5"],
        )
    )
    summary = "null" if ai_summary is None else json.dumps(ai_summary, ensure_ascii=False)
    review_slot = (
        '196:{"commentCount":%d,"star":"%s","starShow":"%s","aiSummary":%s,'
        '"aiTagTitle":%s,"aiTagList":%s,"totalCommentCount":%d,"ratingInfo":"$19c"}'
        % (
            total,
            stars,
            stars,
            summary,
            "null"
            if ai_summary is None
            else json.dumps("内容由人工智能总结自用户评价", ensure_ascii=False),
            "null" if ai_summary is None else json.dumps(["质地柔软"], ensure_ascii=False),
            total,
        )
    )
    product_slot = (
        '1a0:{"productId":"10524192","title":"Bc Babycare 湿巾",'
        '"crossOffPrice":"8.99","mainPrice":"6.99","availability":"IN_STOCK"}'
    )
    return "\n".join(['2b:[["$","$L8f",null,{}]]', rating_slot, review_slot, product_slot])


@unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy (parsel) is not installed")
class ReviewAggregateTests(unittest.TestCase):
    def setUp(self):
        from joybuy_crawler.parsers.joybuy_uk import parse_uk_product_detail

        self.html = FIXTURE.read_text(encoding="utf-8")
        self.product = parse_uk_product_detail(
            self.html, source_url="https://www.joybuy.co.uk/dp/bc-babycare/10524192"
        )

    def test_star_distribution_average_and_count(self):
        self.assertEqual(self.product.rating_average, "4.8")
        self.assertEqual(self.product.rating_count, 47)
        self.assertEqual(
            self.product.rating_distribution,
            {"1": 1, "2": 1, "3": 2, "4": 9, "5": 34},
        )
        # The buckets must add up to the headline count, otherwise one of
        # the two numbers was read from the wrong place.
        self.assertEqual(sum(self.product.rating_distribution.values()), self.product.rating_count)
        self.assertEqual(self.product.rating_source, "flight")

    def test_no_review_text_is_captured(self):
        payload = self.product.to_payload()
        self.assertNotIn("review_text", payload)
        self.assertNotIn("reviews", payload)
        self.assertFalse([key for key in payload if key.lower().startswith("comment")])
        # No review body leaks into free-text fields either.
        self.assertNotIn("湿巾质地柔软", payload["description"])

    def test_ai_summary_block_is_kept_when_present(self):
        self.assertTrue(self.product.ai_summary.startswith("多数买家反馈"))
        self.assertEqual(self.product.ai_summary_title, "内容由人工智能总结自用户评价")
        self.assertEqual(self.product.ai_summary_tags, ["质地柔软", "不掉屑", "性价比高"])
        native = self.product.to_payload()["joybuy"]
        self.assertEqual(native["aiReviewSummary"]["title"], "内容由人工智能总结自用户评价")
        self.assertEqual(native["aiReviewSummary"]["tags"][0], "质地柔软")

    def test_ai_summary_is_absent_when_the_page_has_none(self):
        from joybuy_crawler.parsers.joybuy_uk import parse_uk_product_detail

        html = with_flight(self.html, review_flight(ai_summary=None))
        stripped = parse_uk_product_detail(
            html, source_url="https://www.joybuy.co.uk/dp/bc-babycare/10524192"
        )
        self.assertEqual(stripped.ai_summary, "")
        self.assertEqual(stripped.ai_summary_tags, [])
        self.assertNotIn("aiReviewSummary", stripped.to_payload()["joybuy"])
        # The rating aggregates still come through.
        self.assertEqual(stripped.rating_count, 47)

    def test_product_without_reviews_does_not_invent_an_average(self):
        from joybuy_crawler.parsers.joybuy_uk import parse_uk_product_detail

        # Real pages leave averageScore at its 5 default when nothing is rated.
        html = with_flight(
            self.html,
            review_flight(
                ai_summary=None,
                stars="0.0",
                counts={"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
                total=0,
            ),
        )
        product = parse_uk_product_detail(
            html, source_url="https://www.joybuy.co.uk/dp/bc-babycare/10524192"
        )
        self.assertIsNone(product.rating_average)
        self.assertEqual(product.rating_count, 0)
        self.assertEqual(sum(product.rating_distribution.values()), 0)


class BreadcrumbTruncationTests(unittest.TestCase):
    def test_keeps_two_levels_dropping_the_home_crumb(self):
        from joybuy_crawler.parsers.joybuy_uk import truncate_breadcrumbs

        crumbs = [
            {"name": "首页", "cid": ""},
            {"name": "母婴用品", "cid": ""},
            {"name": "健康护理", "cid": ""},
            {"name": "湿巾及配件", "cid": ""},
            {"name": "湿巾", "cid": ""},
            {"name": "Bc Babycare 旅行婴儿护理必备品", "cid": ""},
        ]
        kept = truncate_breadcrumbs(crumbs)
        self.assertEqual([item["name"] for item in kept], ["母婴用品", "健康护理"])

    def test_english_home_crumb_is_also_dropped(self):
        from joybuy_crawler.parsers.joybuy_uk import truncate_breadcrumbs

        kept = truncate_breadcrumbs(
            [{"name": "Home"}, {"name": "Home Appliances"}, {"name": "Small Kitchen"}]
        )
        self.assertEqual([item["name"] for item in kept], ["Home Appliances", "Small Kitchen"])

    def test_short_and_empty_trails_are_untouched(self):
        from joybuy_crawler.parsers.joybuy_uk import truncate_breadcrumbs

        self.assertEqual(truncate_breadcrumbs([]), [])
        self.assertEqual(
            [item["name"] for item in truncate_breadcrumbs([{"name": "Beauty"}])],
            ["Beauty"],
        )

    def test_deeper_levels_are_gone_from_the_payload(self):
        from joybuy_crawler.parsers.joybuy_uk import parse_uk_product_detail

        product = parse_uk_product_detail(
            FIXTURE.read_text(encoding="utf-8"),
            source_url="https://www.joybuy.co.uk/dp/bc-babycare/10524192",
        )
        names = [crumb["name"] for crumb in product.to_payload()["joybuy"]["breadcrumbs"]]
        self.assertEqual(names, ["母婴用品", "健康护理"])
        self.assertNotIn("湿巾及配件", names)
        self.assertNotIn("湿巾", names)


class ListingCardLayoutTests(unittest.TestCase):
    """Search pages moved the title/price out of the anchor (2026-11-05).

    The image anchor carries no text, so an anchor-only parser returns
    titleless, priceless cards — which is exactly what the first authenticated
    run produced.
    """

    @classmethod
    def setUpClass(cls):
        cls.html = (CRAWLER_DIR / "fixtures" / "listing_cards_v2.html").read_text(encoding="utf-8")

    @unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy (parsel) is not installed")
    def test_cards_expose_title_price_and_image(self):
        from joybuy_crawler.parsers.joybuy_uk import parse_uk_listing

        entries = parse_uk_listing(self.html)
        self.assertEqual(len(entries), 2)
        first = entries[0]
        self.assertEqual(first.title, "KOMORE 2000 W 即热饮水机 带可拆卸 3 L 水箱和滴水盘")
        # Original price wins over the discounted one (business rule).
        self.assertEqual(first.original_price, "35.99")
        self.assertTrue(first.source_url.endswith("/100023685670315?requestIdentity=searchKeyWord"))
        self.assertTrue(first.image_url.startswith("https://images4.joy-sourcing.com/"))

    @unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy (parsel) is not installed")
    def test_card_without_original_price_falls_back_to_main_price(self):
        from joybuy_crawler.parsers.joybuy_uk import parse_uk_listing

        entries = parse_uk_listing(self.html)
        self.assertEqual(entries[1].original_price, "15.99")

    @unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy (parsel) is not installed")
    def test_anchor_layout_still_parses(self):
        from joybuy_crawler.parsers.joybuy_uk import parse_uk_listing

        legacy = (
            '<a href="/dp/some-slug/104001"><span class="title">Kettle 1.7L</span>'
            '<span class="crossOffPrice">£29.99</span></a>'
        )
        entries = parse_uk_listing(legacy)
        self.assertEqual(entries[0].title, "Kettle 1.7L")
        self.assertEqual(entries[0].original_price, "29.99")
