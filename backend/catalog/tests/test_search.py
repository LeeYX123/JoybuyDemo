import unittest
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from catalog.models import ProductSearchDocument, Spu
from catalog.product_services import (
    get_or_create_sku_from_source,
    get_or_create_spu_from_source,
)
from catalog.search_services import (
    SearchParamsInvalid,
    rebuild_search_document,
    recommendation_documents,
    search_documents,
)
from catalog.services import create_local_category
from media.models import MediaAsset, MediaUsage
from merchants.services import get_import_fallback_merchant
from offers.models import Currency, Locale, Market, Offer
from offers.services import import_offer_from_source
from reviews.services import upsert_source_review


class SearchFixtureBase(TestCase):
    def setUp(self):
        self.merchant = get_import_fallback_merchant()
        self.market = Market.objects.get(code="GB")
        self.currency = Currency.objects.get(code="GBP")
        self.electronics = create_local_category(
            name="Electronics", slug="electronics", parent=None, sort_order=1
        )
        self.phones = create_local_category(
            name="Phones", slug="phones", parent=self.electronics, sort_order=1
        )

    def seed_product(
        self,
        *,
        source_id,
        title,
        price,
        category,
        brand_name=None,
        rating=None,
        review_count=0,
        status=Spu.Status.ACTIVE,
    ):
        brand = None
        if brand_name:
            from catalog.models import Brand

            brand, _ = Brand.objects.get_or_create(
                name=brand_name, defaults={"slug": brand_name.lower().replace(" ", "-")}
            )
        spu, _ = get_or_create_spu_from_source(
            source_system="joybuy",
            source_id=source_id,
            title=title,
            local_category=category,
            brand=brand,
        )
        spu.status = status
        spu.save(update_fields=["status", "updated_at"])
        sku, _ = get_or_create_sku_from_source(
            spu=spu,
            source_system="joybuy",
            source_id=f"{source_id}-sku",
            specification={},
            skip_attribute_validation=True,
        )
        offer, _ = import_offer_from_source(
            sku=sku,
            merchant=self.merchant,
            market=self.market,
            currency=self.currency,
            source_system="joybuy",
            source_id=f"{source_id}-offer",
            current_price=price,
            source_availability=Offer.SourceAvailability.IN_STOCK,
        )
        # Listing an offer is an admin action (WP-31); seeds do it directly.
        offer.status = Offer.Status.ACTIVE
        offer.save(update_fields=["status", "updated_at"])
        for index in range(review_count):
            upsert_source_review(
                spu,
                source_system="joybuy",
                source_id=f"{source_id}-review-{index}",
                rating=rating or 5,
                guest_display_name=f"Guest {index}",
                source_reviewed_at=timezone.now(),
            )
        return rebuild_search_document(spu, market=self.market)


class SearchServiceTests(SearchFixtureBase):
    def seed_standard_catalog(self):
        self.seed_product(
            source_id="earbuds",
            title="Wireless Earbuds Pro",
            price="19.99",
            category=self.phones,
            brand_name="SoundCore",
            rating=5,
            review_count=4,
        )
        self.seed_product(
            source_id="watch",
            title="Smart Watch S2",
            price="39.50",
            category=self.electronics,
            brand_name="FitLine",
            rating=4,
            review_count=2,
        )
        self.seed_product(
            source_id="cable",
            title="USB-C Charging Cable",
            price="4.99",
            category=self.electronics,
            brand_name="SoundCore",
        )
        # Draft SPU with an active offer must stay unsearchable.
        self.seed_product(
            source_id="draft",
            title="Unreleased Gadget",
            price="99.00",
            category=self.electronics,
            status=Spu.Status.DRAFT,
        )

    def test_rebuild_marks_only_sellable_active_products(self):
        self.seed_standard_catalog()
        self.assertEqual(ProductSearchDocument.objects.count(), 4)
        searchable = ProductSearchDocument.objects.filter(is_searchable=True)
        self.assertEqual(searchable.count(), 3)
        self.assertFalse(
            ProductSearchDocument.objects.filter(title="Unreleased Gadget").get().is_searchable
        )

        # Review stats roll up into the document.
        earbuds = ProductSearchDocument.objects.get(title="Wireless Earbuds Pro")
        self.assertEqual(earbuds.rating_count, 4)
        self.assertEqual(earbuds.rating_average, Decimal("5.00"))

    def test_category_filter_includes_descendants(self):
        self.seed_standard_catalog()
        electronics = search_documents(market=self.market, category=self.electronics)
        self.assertEqual(electronics["total"], 3)
        phones_only = search_documents(market=self.market, category=self.phones)
        self.assertEqual([item["title"] for item in phones_only["items"]], ["Wireless Earbuds Pro"])

    def test_sorting_and_price_filters_are_inclusive(self):
        self.seed_standard_catalog()
        price_asc = search_documents(market=self.market, sort="price_asc")
        self.assertEqual(
            [item["price_min"] for item in price_asc["items"]],
            ["4.9900", "19.9900", "39.5000"],
        )
        rating = search_documents(market=self.market, sort="rating_desc")
        self.assertEqual(rating["items"][0]["title"], "Wireless Earbuds Pro")
        newest = search_documents(market=self.market, sort="newest")
        self.assertEqual(newest["total"], 3)

        window = search_documents(market=self.market, min_price="5.00", max_price="40.00")
        self.assertEqual(
            {item["title"] for item in window["items"]},
            {"Wireless Earbuds Pro", "Smart Watch S2"},
        )

    def test_pagination_caps_depth_and_reports_totals(self):
        for index in range(30):
            self.seed_product(
                source_id=f"bulk-{index}",
                title=f"Bulk Product {index:02d}",
                price=f"{index + 1}.00",
                category=self.electronics,
            )
        page_one = search_documents(market=self.market, sort="price_asc", page=1)
        self.assertEqual(page_one["total"], 30)
        self.assertEqual(page_one["total_pages"], 2)
        self.assertEqual(len(page_one["items"]), 24)
        page_two = search_documents(market=self.market, sort="price_asc", page=2)
        self.assertEqual(len(page_two["items"]), 6)
        deep = search_documents(market=self.market, page=999)
        self.assertEqual(deep["page"], 50, "Page depth is capped.")

    def test_invalid_params_are_rejected_and_empty_state_is_clean(self):
        with self.assertRaises(SearchParamsInvalid):
            search_documents(market=self.market, sort="cheapest")
        with self.assertRaises(SearchParamsInvalid):
            search_documents(market=self.market, page=0)

        empty = search_documents(market=self.market, query="nothing-matches-this")
        self.assertEqual(empty["total"], 0)
        self.assertEqual(empty["items"], [])
        self.assertEqual(empty["total_pages"], 0)

    def test_items_carry_retail_price_from_spu_without_extra_queries(self):
        """每个商品带 ``retail_price``（Spu 后台零售价），Decimal → 4 位小数字符串。

        null → null；取值来自已 ``select_related("spu")`` 的行，不额外查库。
        """

        priced = self.seed_product(
            source_id="retail-priced",
            title="Retail Priced Product",
            price="10.00",
            category=self.electronics,
        )
        unpriced = self.seed_product(
            source_id="retail-null",
            title="Retail Null Product",
            price="5.00",
            category=self.electronics,
        )
        priced.spu.retail_price = Decimal("19.99")
        priced.spu.save(update_fields=["retail_price"])

        with CaptureQueriesContext(connection) as queries:
            result = search_documents(market=self.market, sort="price_asc", page=1)

        items = {item["spu_public_id"]: item for item in result["items"]}
        item = items[str(priced.spu.public_id)]
        self.assertEqual(item["retail_price"], "19.9900")
        self.assertEqual(item["price_min"], "10.0000")
        self.assertIsNone(items[str(unpriced.spu.public_id)]["retail_price"])
        self.assertLessEqual(len(queries), 5)

    def test_search_returns_first_local_gallery_image_without_n_plus_one(self):
        document = self.seed_product(
            source_id="pictured",
            title="Pictured Product",
            price="12.00",
            category=self.electronics,
        )
        now = timezone.now()
        asset = MediaAsset.objects.create(
            sha256="a" * 64,
            kind=MediaAsset.Kind.PRODUCT,
            relative_path="products/original/aa/aa/pictured.webp",
            mime_type="image/webp",
            extension="webp",
            byte_size=12,
            first_seen_at=now,
            last_seen_at=now,
            download_status=MediaAsset.DownloadStatus.DOWNLOADED,
        )
        MediaUsage.objects.create(
            asset=asset,
            content_type=ContentType.objects.get_for_model(Spu),
            object_id=document.spu_id,
            role="gallery",
            sort_order=0,
        )

        with CaptureQueriesContext(connection) as queries:
            result = search_documents(market=self.market, category=self.electronics)

        self.assertEqual(
            result["items"][0]["image_path"],
            "/media/products/original/aa/aa/pictured.webp",
        )
        self.assertLessEqual(len(queries), 5)


@unittest.skipUnless(connection.vendor == "mysql", "EXPLAIN plan shape is MySQL-specific")
class SearchQueryPlanTests(SearchFixtureBase):
    """docs/01 §9: query plans must use indexes, not table scans."""

    @classmethod
    def setUpTestData(cls):
        cls.merchant = get_import_fallback_merchant()
        cls.market = Market.objects.get(code="GB")
        cls.currency = Currency.objects.get(code="GBP")
        cls.category = create_local_category(name="Plan", slug="plan", parent=None)
        rows = []
        spus = []
        for index in range(3000):
            spus.append(
                Spu(
                    status=Spu.Status.ACTIVE,
                    local_category=cls.category,
                )
            )
        Spu.objects.bulk_create(spus)
        spus = Spu.objects.filter(local_category=cls.category)
        documents = []
        for spu in spus:
            rows.append(
                ProductSearchDocument(
                    spu=spu,
                    market=cls.market,
                    title=f"Bulk product {spu.pk}",
                    local_category=cls.category,
                    min_price=Decimal("1.00"),
                    max_price=Decimal("2.00"),
                    currency_code="GBP",
                    is_searchable=True,
                    published_at=timezone.now(),
                )
            )
        ProductSearchDocument.objects.bulk_create(documents)
        del rows

    def test_category_and_price_filter_uses_the_composite_index(self):
        queryset = ProductSearchDocument.objects.filter(
            market=self.market,
            is_searchable=True,
            local_category=self.category,
            min_price__lte=Decimal("2.00"),
        )
        sql, params = queryset.query.sql_with_params()
        with connection.cursor() as cursor:
            cursor.execute(f"EXPLAIN {sql}", params)
            plan = cursor.fetchone()
        # MySQL: possible_keys/key mention the composite index; ref/range access.
        explain_columns = [column[0] for column in cursor.description]
        plan_dict = dict(zip(explain_columns, plan))
        self.assertIn("psd_market_locale_cat_idx", plan_dict.get("possible_keys") or "")
        self.assertIn(plan_dict.get("type") or "", {"ref", "range", "eq_ref"})

    def test_full_table_scan_is_absent_for_newest_sort(self):
        queryset = ProductSearchDocument.objects.filter(
            market=self.market, is_searchable=True
        ).order_by("-published_at", "-pk")
        sql, params = queryset.query.sql_with_params()
        with connection.cursor() as cursor:
            cursor.execute(f"EXPLAIN {sql}", params)
            plan = cursor.fetchone()
            explain_columns = [column[0] for column in cursor.description]
        plan_dict = dict(zip(explain_columns, plan))
        self.assertIn(plan_dict.get("type") or "", {"ref", "range", "index"})


class SearchTextTests(TransactionTestCase):
    """InnoDB FULLTEXT only indexes committed rows, so text search needs
    real transactions instead of the wrapped TestCase ones."""

    def setUp(self):
        # TransactionTestCase truncates seeded rows; recreate the system
        # merchant that migrations normally provide.
        from merchants.models import Merchant

        self.merchant, _ = Merchant.objects.update_or_create(
            slug="joybuy-self-operated-import",
            defaults={
                "display_name": "Joybuy 自营导入",
                "merchant_type": Merchant.Type.IMPORT_FALLBACK,
                "onboarding_status": Merchant.OnboardingStatus.ACTIVE,
                "is_system": True,
            },
        )
        self.currency, _ = Currency.objects.get_or_create(
            code="GBP",
            defaults={"name": "Pound sterling", "symbol": "£", "exponent": 2},
        )
        self.market, _ = Market.objects.get_or_create(
            code="GB",
            defaults={
                "name": "United Kingdom",
                "default_locale": "en-GB",
                "time_zone": "Europe/London",
                "default_currency": self.currency,
            },
        )
        Locale.objects.get_or_create(
            code="en-GB",
            defaults={
                "language_code": "en",
                "region_code": "GB",
                "name": "English (United Kingdom)",
                "native_name": "English",
            },
        )
        self.electronics = create_local_category(
            name="TextSearch", slug="text-search", parent=None, sort_order=1
        )
        self.phones = create_local_category(
            name="TextPhones", slug="text-phones", parent=self.electronics, sort_order=1
        )
        self.seed_product = SearchFixtureBase.seed_product.__get__(self)
        self.seed_product(
            source_id="earbuds",
            title="Wireless Earbuds Pro",
            price="19.99",
            category=self.phones,
            brand_name="SoundCore",
        )
        self.seed_product(
            source_id="cable",
            title="USB-C Charging Cable",
            price="4.99",
            category=self.electronics,
            brand_name="SoundCore",
        )

    def test_text_search_matches_title_and_brand(self):
        result = search_documents(market=self.market, query="earbuds")
        self.assertEqual([item["title"] for item in result["items"]], ["Wireless Earbuds Pro"])

        by_brand = search_documents(market=self.market, query="soundcore")
        self.assertEqual(by_brand["total"], 2)

    def test_short_numeric_token_does_not_kill_the_match(self):
        """「iPhone 17」里的 17 短于 FULLTEXT 最小词长 3：不能让整条 MATCH 归零。"""
        self.seed_product(
            source_id="iphone-17",
            title="Apple iPhone 17 256GB",
            price="799.00",
            category=self.phones,
        )
        result = search_documents(market=self.market, query="iPhone 17")
        self.assertEqual([item["title"] for item in result["items"]], ["Apple iPhone 17 256GB"])

        short_only = search_documents(market=self.market, query="17")
        self.assertEqual(short_only["total"], 1)

    def test_operator_only_query_returns_empty(self):
        result = search_documents(market=self.market, query="++ --")
        self.assertEqual(result["total"], 0)

    def test_no_match_returns_clean_empty_state(self):
        empty = search_documents(market=self.market, query="nothing-matches-this")
        self.assertEqual(empty["total"], 0)
        self.assertEqual(empty["items"], [])


class RecommendationTests(SearchFixtureBase):
    """首页【为您推荐】池（需求文档03 11.6）：确定性混排 + 分页 + 只含可售商品。"""

    def test_recommendations_are_deterministic_and_paginated(self):
        for index in range(30):
            self.seed_product(
                source_id=f"reco-{index}",
                title=f"Reco Product {index:02d}",
                price=f"{10 + index}.00",
                category=self.electronics if index % 2 else self.phones,
                brand_name="BrandX",
            )
        first = recommendation_documents(market=self.market, page=1)
        self.assertEqual(first["page_size"], 24)
        self.assertEqual(first["total"], 30)
        self.assertEqual(first["total_pages"], 2)
        self.assertEqual(len(first["items"]), 24)

        # 确定性：同样的入参两次调用顺序完全一致（刷新不乱序）。
        again = recommendation_documents(market=self.market, page=1)
        self.assertEqual(
            [item["spu_public_id"] for item in first["items"]],
            [item["spu_public_id"] for item in again["items"]],
        )

        # 翻页无重复、无空窗。
        second = recommendation_documents(market=self.market, page=2)
        self.assertEqual(len(second["items"]), 6)
        page_one_ids = {item["spu_public_id"] for item in first["items"]}
        page_two_ids = {item["spu_public_id"] for item in second["items"]}
        self.assertEqual(page_one_ids & page_two_ids, set())
        self.assertEqual(len(page_one_ids | page_two_ids), 30)

    def test_recommendations_only_include_purchasable_products(self):
        active = self.seed_product(
            source_id="reco-active",
            title="Active Reco Product",
            price="9.99",
            category=self.electronics,
        )
        self.seed_product(
            source_id="reco-delisted",
            title="Delisted Reco Product",
            price="19.99",
            category=self.electronics,
            status=Spu.Status.INACTIVE,
        )
        result = recommendation_documents(market=self.market, page=1)
        titles = [item["title"] for item in result["items"]]
        self.assertEqual(titles, ["Active Reco Product"])
        self.assertEqual(result["items"][0]["spu_public_id"], str(active.spu.public_id))

    def test_recommendations_page_param_is_validated(self):
        with self.assertRaises(SearchParamsInvalid):
            recommendation_documents(market=self.market, page=0)

    def test_recommendations_endpoint_returns_envelope(self):
        self.seed_product(
            source_id="reco-api",
            title="API Reco Product",
            price="5.00",
            category=self.electronics,
        )
        response = self.client.get("/api/v1/recommendations", {"page": "1"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["page"], 1)
        self.assertEqual(payload["page_size"], 24)
        self.assertEqual(len(payload["items"]), 1)
        item = payload["items"][0]
        self.assertEqual(item["title"], "API Reco Product")
        self.assertIn("display_currency_symbol", payload)

    def test_recommendations_endpoint_items_carry_retail_price(self):
        """频道页【精选好物】走同一序列化：接口项含 retail_price（null 时为 null）。"""

        priced = self.seed_product(
            source_id="reco-retail",
            title="Reco Retail Priced",
            price="10.00",
            category=self.electronics,
        )
        self.seed_product(
            source_id="reco-retail-null",
            title="Reco Retail Null",
            price="7.00",
            category=self.electronics,
        )
        priced.spu.retail_price = Decimal("19.99")
        priced.spu.save(update_fields=["retail_price"])

        response = self.client.get("/api/v1/recommendations", {"page": "1"})
        self.assertEqual(response.status_code, 200)
        items = {item["title"]: item for item in response.json()["items"]}
        self.assertEqual(items["Reco Retail Priced"]["retail_price"], "19.9900")
        self.assertEqual(items["Reco Retail Priced"]["price_min"], "10.0000")
        self.assertIsNone(items["Reco Retail Null"]["retail_price"])

    def test_recommendations_endpoint_rejects_bad_page(self):
        response = self.client.get("/api/v1/recommendations", {"page": "not-a-number"})
        self.assertEqual(response.status_code, 200)
        response = self.client.get("/api/v1/recommendations", {"page": "0"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "SEARCH_PARAMS_INVALID")

    def _seed_mixed_category_pool(self, other):
        """两棵子树各若干件：phones 2 件 + electronics 直挂 1 件 + other 1 件。"""
        self.seed_product(
            source_id="cat-a",
            title="Phone Pool A",
            price="10.00",
            category=self.phones,
        )
        self.seed_product(
            source_id="cat-b",
            title="Phone Pool B",
            price="11.00",
            category=self.phones,
        )
        self.seed_product(
            source_id="cat-c",
            title="Electronics Pool C",
            price="12.00",
            category=self.electronics,
        )
        self.seed_product(
            source_id="cat-d",
            title="Other Pool D",
            price="13.00",
            category=other,
        )

    def test_recommendations_category_limits_pool_to_subtree(self):
        """13.4：category=<slug> 只取该类目子树的 ACTIVE 商品。"""
        other = create_local_category(name="Other", slug="other", parent=None, sort_order=2)
        self._seed_mixed_category_pool(other)

        subtree = recommendation_documents(market=self.market, page=1, category=self.electronics)
        self.assertEqual(subtree["total"], 3)
        titles = {item["title"] for item in subtree["items"]}
        self.assertEqual(titles, {"Phone Pool A", "Phone Pool B", "Electronics Pool C"})

        # 二级类目只圈自己的叶子。
        phones = recommendation_documents(market=self.market, page=1, category=self.phones)
        self.assertEqual(phones["total"], 2)
        self.assertEqual(
            {item["title"] for item in phones["items"]},
            {"Phone Pool A", "Phone Pool B"},
        )

    def test_recommendations_cycle_wraps_pool_from_the_start(self):
        """13.4 第 4 步：页号超池后取模循环（cycle=True），内容与首批一致。"""
        for index in range(30):
            self.seed_product(
                source_id=f"cycle-{index}",
                title=f"Cycle Product {index:02d}",
                price=f"{10 + index}.00",
                category=self.electronics,
            )
        first = recommendation_documents(market=self.market, page=1)

        # 不带 cycle：页号被夹到最后一页（现网行为不变）。
        clamped = recommendation_documents(market=self.market, page=5)
        self.assertEqual(clamped["page"], 2)
        self.assertEqual(len(clamped["items"]), 6)

        # 带 cycle：page=5 → ((5-1) % 2) + 1 = 1，回到第 1 页。
        wrapped = recommendation_documents(market=self.market, page=5, cycle=True)
        self.assertEqual(wrapped["page"], 1)
        self.assertEqual(
            [item["spu_public_id"] for item in wrapped["items"]],
            [item["spu_public_id"] for item in first["items"]],
        )
        # 循环响应里 total/total_pages 仍是池子真实大小。
        self.assertEqual(wrapped["total"], 30)
        self.assertEqual(wrapped["total_pages"], 2)

        # page=3 → ((3-1) % 2) + 1 = 1；page=4 → 第 2 页。
        wrapped_three = recommendation_documents(market=self.market, page=3, cycle=True)
        self.assertEqual(wrapped_three["page"], 1)
        wrapped_four = recommendation_documents(market=self.market, page=4, cycle=True)
        self.assertEqual(wrapped_four["page"], 2)

    def test_recommendations_endpoint_category_and_cycle_params(self):
        for index in range(3):
            self.seed_product(
                source_id=f"api-cat-{index}",
                title=f"API Category Product {index}",
                price=f"{10 + index}.00",
                category=self.phones,
            )
        self.seed_product(
            source_id="api-cat-other",
            title="API Other Product",
            price="99.00",
            category=self.electronics,
        )

        response = self.client.get("/api/v1/recommendations", {"page": "1", "category": "phones"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 3)
        self.assertTrue(all("API Category Product" in item["title"] for item in payload["items"]))

        # cycle=1：page 超池后回卷，不返回空列表。
        response = self.client.get(
            "/api/v1/recommendations", {"page": "9", "category": "phones", "cycle": "1"}
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["page"], 1)
        self.assertEqual(len(payload["items"]), 3)

        # 未知类目 → 404 CATEGORY_NOT_FOUND。
        response = self.client.get("/api/v1/recommendations", {"category": "no-such-category"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "CATEGORY_NOT_FOUND")

    def test_recommendations_pool_excludes_stale_searchable_docs(self):
        """验收 FAIL-A：is_searchable 是快照，池子必须实时校验 SPU/Offer。

        并发爬虫导入期间 SPU 可能被重新置回 DRAFT、Offer 可能被下架而文档
        标志未刷新；只信快照会让「为您推荐/精选好物」点进 PDP 404。
        """

        active = self.seed_product(
            source_id="stale-active",
            title="Still Purchasable",
            price="10.00",
            category=self.electronics,
        )
        draft_spu = self.seed_product(
            source_id="stale-draft",
            title="Draft Since Reimport",
            price="11.00",
            category=self.electronics,
        ).spu
        no_offer = self.seed_product(
            source_id="stale-no-offer",
            title="Offer Withdrawn",
            price="12.00",
            category=self.electronics,
        ).spu

        # 造脏数据：文档仍 is_searchable=True，但 SPU 已回到 DRAFT。
        draft_spu.status = Spu.Status.DRAFT
        draft_spu.save(update_fields=["status", "updated_at"])
        # 另一件：SPU ACTIVE 但 ACTIVE Offer 被撤下（文档未刷新）。
        Offer.objects.filter(sku__spu=no_offer).update(status=Offer.Status.DRAFT)

        result = recommendation_documents(market=self.market, page=1)
        self.assertEqual(result["total"], 1)
        titles = [item["title"] for item in result["items"]]
        self.assertEqual(titles, ["Still Purchasable"])
        self.assertEqual(result["items"][0]["spu_public_id"], str(active.spu.public_id))

        # 恢复后重新可见（池子跟随实时状态）。
        draft_spu.status = Spu.Status.ACTIVE
        draft_spu.save(update_fields=["status", "updated_at"])
        Offer.objects.filter(sku__spu=no_offer).update(status=Offer.Status.ACTIVE)
        result = recommendation_documents(market=self.market, page=1)
        self.assertEqual(result["total"], 3)


class LocalizedListingTitleTests(SearchFixtureBase):
    """列表卡片标题「读取时本地化」（2026-11-27）。

    搜索索引（``ProductSearchDocument.title``）保持 en-GB 快照不变；接口按
    请求 locale 批量替换本页 ``title``：``SpuMarketContent``(CURRENT) 优先，
    其次 ``SpuTranslation``，没有译文就保留英文，绝不回退 de/fr 等其它语言。
    """

    def setUp(self):
        super().setUp()
        self.zh = Locale.objects.get(code="zh-CN")
        self.en = Locale.objects.get(code="en-GB")

    def add_translation(self, spu, *, locale, title):
        from catalog.models import SpuTranslation

        return SpuTranslation.objects.create(
            spu=spu, locale=locale, title=title, subtitle="", description=""
        )

    def test_zh_locale_title_comes_from_translation(self):
        document = self.seed_product(
            source_id="zh-translated",
            title="Wireless Earbuds Pro",
            price="19.99",
            category=self.phones,
        )
        self.add_translation(document.spu, locale="zh-CN", title="无线耳机 Pro")

        localized = search_documents(
            market=self.market, category=self.phones, localize_locale=self.zh
        )
        self.assertEqual([item["title"] for item in localized["items"]], ["无线耳机 Pro"])
        # 索引本身不动：文档标题仍是英文快照。
        document.refresh_from_db()
        self.assertEqual(document.title, "Wireless Earbuds Pro")
        # 不传 localize_locale 的调用方（内部/后台）行为不变。
        plain = search_documents(market=self.market, category=self.phones)
        self.assertEqual([item["title"] for item in plain["items"]], ["Wireless Earbuds Pro"])

    def test_market_content_current_beats_legacy_translation(self):
        from catalog.models import SpuMarketContent

        current_spu = self.seed_product(
            source_id="market-content",
            title="Smart Watch S2",
            price="39.50",
            category=self.electronics,
        )
        self.add_translation(current_spu.spu, locale="zh-CN", title="旧版译文")
        SpuMarketContent.objects.create(
            spu=current_spu.spu,
            market=self.market,
            locale=self.zh,
            title="智能手表 S2",
            status=SpuMarketContent.Status.CURRENT,
        )
        # STALE 行不参与本地化：该商品回落到 legacy 译文。
        stale_spu = self.seed_product(
            source_id="stale-market-content",
            title="Smart Watch S3",
            price="49.50",
            category=self.electronics,
        )
        self.add_translation(stale_spu.spu, locale="zh-CN", title="旧版译文 S3")
        SpuMarketContent.objects.create(
            spu=stale_spu.spu,
            market=self.market,
            locale=self.zh,
            title="过期市场内容",
            status=SpuMarketContent.Status.STALE,
        )

        localized = search_documents(
            market=self.market, category=self.electronics, localize_locale=self.zh
        )
        titles = {item["spu_public_id"]: item["title"] for item in localized["items"]}
        self.assertEqual(titles[str(current_spu.spu.public_id)], "智能手表 S2")
        self.assertEqual(titles[str(stale_spu.spu.public_id)], "旧版译文 S3")

    def test_missing_zh_translation_keeps_english_and_never_uses_other_languages(self):
        document = self.seed_product(
            source_id="only-german",
            title="USB-C Charging Cable",
            price="4.99",
            category=self.electronics,
        )
        # 只有 de-DE 译文，没有 zh-CN / zh：中文列表必须回退英文原值。
        self.add_translation(document.spu, locale="de-DE", title="USB-C Ladekabel")

        localized = search_documents(
            market=self.market, category=self.electronics, localize_locale=self.zh
        )
        self.assertEqual([item["title"] for item in localized["items"]], ["USB-C Charging Cable"])
        # 请求 de-DE 时才用德语（读取时本地化对其它语言同样生效）。
        german = search_documents(
            market=self.market,
            category=self.electronics,
            localize_locale=Locale.objects.get(code="de-DE"),
        )
        self.assertEqual([item["title"] for item in german["items"]], ["USB-C Ladekabel"])

    def test_en_gb_response_is_unchanged(self):
        document = self.seed_product(
            source_id="en-unchanged",
            title="Retail Priced Product",
            price="10.00",
            category=self.electronics,
        )
        self.add_translation(document.spu, locale="zh-CN", title="中文标题")

        en_items = search_documents(
            market=self.market, category=self.electronics, localize_locale=self.en
        )["items"]
        plain_items = search_documents(market=self.market, category=self.electronics)["items"]
        self.assertEqual([item["title"] for item in en_items], ["Retail Priced Product"])
        self.assertEqual(en_items, plain_items)

        # 请求 locale == 文档 locale 时不做本地化查询（响应逐字节不变）。
        with CaptureQueriesContext(connection) as queries:
            search_documents(market=self.market, category=self.electronics, localize_locale=self.en)
        self.assertLessEqual(len(queries), 5)

    def test_api_localization_adds_at_most_three_queries_per_page(self):
        for index in range(5):
            self.seed_product(
                source_id=f"budget-{index}",
                title=f"Budget Product {index}",
                price=f"{10 + index}.00",
                category=self.electronics,
            )
        # 预热 ContentType/连接等一次性查询，再对比 zh 与 en 的每页查询数。
        self.client.get("/api/v1/search", {"category": "electronics", "locale": "en-GB"})
        self.client.get("/api/v1/search", {"category": "electronics", "locale": "zh-CN"})

        with CaptureQueriesContext(connection) as en_queries:
            response = self.client.get(
                "/api/v1/search", {"category": "electronics", "locale": "en-GB"}
            )
        with CaptureQueriesContext(connection) as zh_queries:
            zh_response = self.client.get(
                "/api/v1/search", {"category": "electronics", "locale": "zh-CN"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(zh_response.status_code, 200)
        self.assertEqual(zh_response.json()["requested_locale"], "zh-CN")
        # zh 路径比 en 多：market 链探测 1 条（既有逻辑）+ 批量本地化 2 条。
        self.assertLessEqual(len(zh_queries) - len(en_queries), 3)
