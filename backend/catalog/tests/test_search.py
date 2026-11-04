import unittest
from decimal import Decimal

from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from merchants.services import get_import_fallback_merchant
from offers.models import Currency, Market, Offer
from offers.services import import_offer_from_source
from reviews.services import upsert_source_review

from catalog.models import ProductSearchDocument, Spu
from catalog.product_services import (
    get_or_create_sku_from_source,
    get_or_create_spu_from_source,
)
from catalog.search_services import (
    SearchParamsInvalid,
    rebuild_search_document,
    search_documents,
)
from catalog.services import create_local_category


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
        self.assertIn("psd_market_cat_price_idx", plan_dict.get("possible_keys") or "")
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

    def test_no_match_returns_clean_empty_state(self):
        empty = search_documents(market=self.market, query="nothing-matches-this")
        self.assertEqual(empty["total"], 0)
        self.assertEqual(empty["items"], [])
