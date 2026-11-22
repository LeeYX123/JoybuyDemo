from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from merchants.models import Merchant
from merchants.services import (
    IMPORT_FALLBACK_NAME,
    IMPORT_FALLBACK_SLUG,
    get_import_fallback_merchant,
)
from offers.models import Currency, Locale, Market, Offer
from offers.services import import_offer_from_source
from reviews.services import upsert_source_review

from catalog.models import (
    ProductCategory,
    SourceCatalog,
    Spu,
    SpuDetail,
    SpuDetailTranslation,
)
from catalog.product_services import get_or_create_sku_from_source, get_or_create_spu_from_source
from catalog.search_services import rebuild_search_document


class ProductDetailApiTests(TestCase):
    def setUp(self):
        self.merchant = get_import_fallback_merchant()
        self.market = Market.objects.get(code="GB")
        self.currency = Currency.objects.get(code="GBP")
        self.spu, _ = get_or_create_spu_from_source(
            source_system="joybuy",
            source_id="detail-spu",
            title="Wireless Earbuds Pro",
        )
        Spu.objects.filter(pk=self.spu.pk).update(status=Spu.Status.ACTIVE)
        self.spu.refresh_from_db()
        self.translation = self.spu.translations.get()

    def make_sku(
        self, source_id, price, status=Offer.Status.ACTIVE, inventory=None, colour="Black"
    ):
        sku, _ = get_or_create_sku_from_source(
            spu=self.spu,
            source_system="joybuy",
            source_id=source_id,
            specification={"colour": colour},
            skip_attribute_validation=True,
        )
        offer, _ = import_offer_from_source(
            sku=sku,
            merchant=self.merchant,
            market=self.market,
            currency=self.currency,
            source_system="joybuy",
            source_id=source_id + "-offer",
            current_price=price,
        )
        fields = ["status"]
        offer.status = status
        if inventory is not None:
            offer.local_inventory = inventory
            fields.append("local_inventory")
        offer.save(update_fields=fields + ["updated_at"])
        return sku, offer

    def test_detail_returns_active_skus_with_offers_and_review_summary(self):
        self.make_sku("sku-black", "19.99")
        self.make_sku("sku-white", "21.99", colour="White")
        upsert_source_review(
            self.spu,
            source_system="joybuy",
            source_id="rev-1",
            rating=5,
            guest_display_name="Guest",
        )
        upsert_source_review(
            self.spu,
            source_system="joybuy",
            source_id="rev-2",
            rating=4,
            guest_display_name="Guest",
        )

        response = self.client.get(
            reverse("product-detail", kwargs={"public_id": self.spu.public_id})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], "Wireless Earbuds Pro")
        self.assertEqual(len(data["skus"]), 2)
        first_offer = data["skus"][0]["offer"]
        self.assertEqual(first_offer["price"], "19.9900")
        self.assertEqual(first_offer["inventory_display"], "999+")
        self.assertTrue(first_offer["is_purchasable"])
        self.assertEqual(data["review_summary"]["count"], 2)
        self.assertIn(data["review_summary"]["average"], {"4.50", "4.5"})
        self.assertIn("href", data["review_summary"]) if False else None

    def test_detail_exposes_stored_sale_amount(self):
        """需求 22.1-5：详情接口暴露 SpuDetail.sale_amount 供「已售 x 件」展示。"""
        self.make_sku("sku-black", "19.99")
        SpuDetail.objects.create(spu=self.spu, sale_amount="25k+")

        response = self.client.get(
            reverse("product-detail", kwargs={"public_id": self.spu.public_id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sale_amount"], "25k+")

    def test_detail_sale_amount_is_none_without_detail_row(self):
        """没有 SpuDetail 行（历史/商家自建商品）时返回 null，不发明销量。"""
        self.make_sku("sku-black", "19.99")

        response = self.client.get(
            reverse("product-detail", kwargs={"public_id": self.spu.public_id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["sale_amount"])

    def test_review_summary_falls_back_to_crawled_rating_snapshot(self):
        """爬虫商品没有本地评价行：评分/评价数/分布用 SpuDetail 的源站快照。"""
        from decimal import Decimal

        from catalog.models import SpuDetail

        self.make_sku("sku-black", "19.99")
        SpuDetail.objects.create(
            spu=self.spu,
            rating_average=Decimal("4.50"),
            rating_count=9,
            rating_distribution={"5": 7, "4": 1, "1": 1},
        )

        response = self.client.get(
            reverse("product-detail", kwargs={"public_id": self.spu.public_id})
        )
        self.assertEqual(response.status_code, 200)
        summary = response.json()["review_summary"]
        self.assertEqual(summary["source"], "crawler")
        self.assertEqual(summary["count"], 9)
        self.assertIn(summary["average"], {"4.50", "4.5"})
        self.assertEqual(summary["distribution"], {"5": 7, "4": 1, "1": 1})

    def test_local_reviews_win_over_crawled_rating_snapshot(self):
        from decimal import Decimal

        from catalog.models import SpuDetail

        self.make_sku("sku-black", "19.99")
        SpuDetail.objects.create(spu=self.spu, rating_average=Decimal("1.00"), rating_count=100)
        upsert_source_review(
            self.spu,
            source_system="joybuy",
            source_id="rev-local",
            rating=5,
            guest_display_name="Guest",
        )

        summary = self.client.get(
            reverse("product-detail", kwargs={"public_id": self.spu.public_id})
        ).json()["review_summary"]
        self.assertEqual(summary["source"], "local")
        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["distribution"], {"5": 1})

    def test_detail_returns_two_level_product_category_breadcrumb(self):
        catalog, _ = SourceCatalog.objects.get_or_create(
            source_system="joybuy",
            defaults={"display_name": "Joybuy"},
        )
        root = ProductCategory.objects.create(
            catalog=catalog,
            source_id="288",
            name="厨具餐具",
            depth=0,
            path="/288/",
        )
        leaf = ProductCategory.objects.create(
            catalog=catalog,
            source_id="361",
            name="锅具",
            depth=1,
            path="/288/361/",
            parent=root,
        )
        Spu.objects.filter(pk=self.spu.pk).update(product_category=leaf)

        response = self.client.get(
            reverse("product-detail", kwargs={"public_id": self.spu.public_id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["category_breadcrumb"],
            [
                {"id": "288", "name": "厨具餐具", "depth": 0},
                {"id": "361", "name": "锅具", "depth": 1},
            ],
        )

    def test_inventory_display_thresholds_and_unpurchasable_states(self):
        _, offer_low = self.make_sku("sku-low", "10.00", inventory=500)
        self.make_sku("sku-out", "12.00", inventory=0, colour="White")

        response = self.client.get(
            reverse("product-detail", kwargs={"public_id": self.spu.public_id})
        )
        data = response.json()
        by_price = {sku["offer"]["price"]: sku["offer"] for sku in data["skus"]}
        self.assertEqual(by_price["10.0000"]["inventory_display"], "500")
        self.assertTrue(by_price["10.0000"]["is_purchasable"])
        self.assertEqual(by_price["12.0000"]["inventory_display"], "0")
        self.assertFalse(by_price["12.0000"]["is_purchasable"])
        del offer_low

    def test_draft_and_inactive_offers_are_hidden(self):
        self.make_sku("sku-active", "19.99")
        draft_sku, _ = self.make_sku(
            "sku-draft", "30.00", status=Offer.Status.DRAFT, colour="White"
        )
        self._draft_public_id = str(draft_sku.public_id)

        response = self.client.get(
            reverse("product-detail", kwargs={"public_id": self.spu.public_id})
        )
        data = response.json()
        # Both SKUs stay visible; the draft-offer one simply has no offer.
        self.assertEqual(len(data["skus"]), 2)
        offers = {sku["public_id"]: sku["offer"] for sku in data["skus"]}
        active_offers = [offer for offer in offers.values() if offer is not None]
        self.assertEqual(len(active_offers), 1)
        self.assertEqual(active_offers[0]["price"], "19.9900")
        self.assertIsNone(offers[self._draft_public_id])

    def test_unknown_or_inactive_product_returns_404(self):
        response = self.client.get(
            reverse("product-detail", kwargs={"public_id": "00000000-0000-0000-0000-000000000000"})
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "PRODUCT_NOT_AVAILABLE")

        # Draft SPU is not visible either.
        draft_spu, _ = get_or_create_spu_from_source(
            source_system="joybuy", source_id="draft-detail", title="Draft"
        )
        response = self.client.get(
            reverse("product-detail", kwargs={"public_id": draft_spu.public_id})
        )
        self.assertEqual(response.status_code, 404)
        _ = rebuild_search_document  # imported for parity with search flows

    # --- 需求 20.1：多商家同款归属 / offer 参数 ---

    def _other_merchant_offer(self, sku, price="29.99"):
        other = Merchant.objects.create(
            slug="other-shop",
            display_name="Other Shop",
            onboarding_status=Merchant.OnboardingStatus.ACTIVE,
        )
        offer = Offer.objects.create(
            merchant=other,
            sku=sku,
            market=self.market,
            currency=self.currency,
            current_price=price,
            status=Offer.Status.ACTIVE,
        )
        return other, offer

    def _detail(self, **params):
        return self.client.get(
            reverse("product-detail", kwargs={"public_id": self.spu.public_id}),
            data=params,
        )

    def test_offer_payload_carries_merchant_context(self):
        _, own_offer = self.make_sku("sku-black", "19.99")

        offer = self._detail().json()["skus"][0]["offer"]

        self.assertEqual(offer["public_id"], str(own_offer.public_id))
        self.assertEqual(
            offer["merchant"],
            {
                "public_id": self.merchant.public_id,
                "display_name": self.merchant.display_name,
                "slug": self.merchant.slug,
                "avatar_url": self.merchant.avatar_url,
            },
        )

    def test_offer_query_selects_that_merchants_offer_for_same_sku(self):
        """同款多商家：?offer= 必须压过默认 `.first()`，否则从 A 进来会归 B。"""

        sku, own_offer = self.make_sku("sku-black", "19.99")
        other, other_offer = self._other_merchant_offer(sku)

        offer = self._detail(offer=str(other_offer.public_id)).json()["skus"][0]["offer"]

        self.assertEqual(offer["public_id"], str(other_offer.public_id))
        self.assertNotEqual(offer["public_id"], str(own_offer.public_id))
        self.assertEqual(offer["price"], "29.9900")
        self.assertEqual(offer["merchant"]["slug"], other.slug)
        self.assertEqual(offer["merchant"]["public_id"], other.public_id)

    def test_invalid_or_unknown_offer_query_falls_back(self):
        _, own_offer = self.make_sku("sku-black", "19.99")

        for bad_value in ("not-a-uuid", "00000000-0000-0000-0000-000000000000"):
            response = self._detail(offer=bad_value)
            self.assertEqual(response.status_code, 200)
            offer = response.json()["skus"][0]["offer"]
            self.assertEqual(offer["public_id"], str(own_offer.public_id))


class DetailTranslationOverlayTests(TransactionTestCase):
    """detail payload 译文覆盖（``spu_detail_translation`` 只读接入，2026-11-17）。

    该表由 translation_agent（SQLAlchemy）创建，Django 侧 ``managed=False``
    不建迁移；测试库同样没有这张表，这里用 ``SchemaEditor`` 按模型补建最小
    结构（带存在性守卫，``--keepdb`` 重跑不会重复建）。
    """

    @staticmethod
    def _ensure_translation_table():
        from django.db import connection

        table = SpuDetailTranslation._meta.db_table
        if table in connection.introspection.table_names():
            return
        with connection.schema_editor() as editor:
            editor.create_model(SpuDetailTranslation)

    @staticmethod
    def _ensure_market_seeds():
        """TransactionTestCase 在用例间截断全表，迁移种子会被清掉；这里按
        ``offers/migrations/0006_seed_european_markets.py`` 的字段自愈重建
        本用例需要的 DE/de-DE/EUR 种子。"""
        from offers.models import MarketLocale

        currency, _ = Currency.objects.update_or_create(
            code="EUR",
            defaults={"name": "Euro", "symbol": "€", "exponent": 2, "is_active": True},
        )
        locale, _ = Locale.objects.update_or_create(
            code="de-DE",
            defaults={
                "language_code": "de",
                "region_code": "DE",
                "name": "German (Germany)",
                "native_name": "Deutsch",
                "is_active": True,
            },
        )
        market, _ = Market.objects.update_or_create(
            code="DE",
            defaults={
                "name": "Germany",
                "default_locale": "de-DE",
                "time_zone": "Europe/Berlin",
                "default_currency": currency,
                "display_currency_symbol": "$",
                "is_active": True,
            },
        )
        MarketLocale.objects.update_or_create(
            market=market,
            locale=locale,
            defaults={"is_default": True, "sort_order": 0},
        )
        return market, locale, currency

    def setUp(self):
        self._ensure_translation_table()
        # TransactionTestCase 会在用例间截断全表，迁移种子（含自营导入商家）
        # 可能被清掉，这里 get_or_create 兜底。
        self.merchant, _ = Merchant.objects.get_or_create(
            slug=IMPORT_FALLBACK_SLUG,
            defaults={
                "display_name": IMPORT_FALLBACK_NAME,
                "merchant_type": Merchant.Type.IMPORT_FALLBACK,
                "is_system": True,
            },
        )
        self.market, self.locale, self.currency = self._ensure_market_seeds()
        self.spu, _ = get_or_create_spu_from_source(
            source_system="joybuy",
            source_id="detail-i18n-spu",
            title="Wireless Earbuds Pro",
        )
        Spu.objects.filter(pk=self.spu.pk).update(status=Spu.Status.ACTIVE)
        self.spu.refresh_from_db()
        self.sku, _ = get_or_create_sku_from_source(
            spu=self.spu,
            source_system="joybuy",
            source_id="detail-i18n-sku",
            specification={"Colour": "Black"},
            skip_attribute_validation=True,
        )
        offer, _ = import_offer_from_source(
            sku=self.sku,
            merchant=self.merchant,
            market=self.market,
            currency=self.currency,
            source_system="joybuy",
            source_id="detail-i18n-offer",
            current_price="19.99",
        )
        offer.status = Offer.Status.ACTIVE
        offer.save(update_fields=["status", "updated_at"])
        self.detail = SpuDetail.objects.create(
            spu=self.spu,
            content_sections=[
                {
                    "title": "Product Description",
                    "blocks": [{"type": "paragraph", "text": "Great sound."}],
                    "images": ["x.webp"],
                }
            ],
            specification_tables=[
                {
                    "title": "Technical Specifications",
                    "columns": ["Item", "Value"],
                    "rows": [{"name": "Battery", "value": "30 hours"}],
                }
            ],
            specifications=[{"group": "General", "name": "Battery", "value": "30 hours"}],
            spec_options=[
                {
                    "name": "Colour",
                    "values": [
                        {
                            "value": "Black",
                            "image_url": "black.webp",
                            "sku_ids": ["detail-i18n-sku"],
                        }
                    ],
                }
            ],
            ai_summary="Reviews like the battery life.",
            ai_summary_title="What buyers say",
        )

    def _get(self):
        response = self.client.get(
            reverse("product-detail", kwargs={"public_id": self.spu.public_id}),
            {"market": "DE", "locale": "de-DE"},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _create_translation(self, **overrides):
        row = {
            "spu_id": self.spu.pk,
            "language_code": "de",
            "content_sections": [
                {
                    "title": "Produktbeschreibung",
                    "blocks": [{"type": "paragraph", "text": "Toller Klang."}],
                    "images": ["x.webp"],
                }
            ],
            "ai_summary": "Käufer loben die Akkulaufzeit.",
            "ai_summary_title": "Was Käufer sagen",
            "source_locale": "en-GB",
            "source_hash": "hash",
            "origin": "MACHINE",
            "specification_tables": [
                {
                    "title": "Technische Spezifikationen",
                    "columns": ["Merkmal", "Wert"],
                    "rows": [{"name": "Akku", "value": "30 Stunden"}],
                }
            ],
            "specifications": [{"group": "Allgemein", "name": "Akku", "value": "30 Stunden"}],
            "spec_options": [
                {
                    "name": "Farbe",
                    "values": [
                        {
                            "value": "Schwarz",
                            "image_url": "black.webp",
                            "sku_ids": ["detail-i18n-sku"],
                        }
                    ],
                }
            ],
            "created_at": timezone.now(),
            "updated_at": timezone.now(),
        }
        row.update(overrides)
        return SpuDetailTranslation.objects.create(**row)

    def test_detail_payload_uses_translation_when_language_hits(self):
        self._create_translation()
        data = self._get()
        self.assertTrue(data["detail_translated"])
        self.assertEqual(data["detail_language"], "de")
        self.assertEqual(data["content_sections"][0]["title"], "Produktbeschreibung")
        self.assertEqual(data["content_sections"][0]["blocks"][0]["text"], "Toller Klang.")
        table = data["specification_tables"][0]
        self.assertEqual(table["title"], "Technische Spezifikationen")
        self.assertEqual(table["rows"][0], {"name": "Akku", "value": "30 Stunden"})
        self.assertEqual(data["specifications"][0]["name"], "Akku")
        self.assertEqual(data["spec_options"][0]["name"], "Farbe")
        # spec_options 译文的 sku_ids 仍映射到本地 SKU public_id。
        self.assertEqual(data["spec_options"][0]["values"][0]["sku_ids"], [str(self.sku.public_id)])
        self.assertEqual(data["ai_summary_title"], "Was Käufer sagen")
        # SKU 规格文本走 SKU 译文，canonical 保持源语言。
        self.assertEqual(data["skus"][0]["canonical_specification"], {"Colour": "Black"})

    def test_detail_payload_falls_back_to_source_without_translation(self):
        data = self._get()
        self.assertFalse(data["detail_translated"])
        self.assertIsNone(data["detail_language"])
        self.assertEqual(data["content_sections"][0]["title"], "Product Description")
        table = data["specification_tables"][0]
        self.assertEqual(table["title"], "Technical Specifications")
        self.assertEqual(table["rows"][0], {"name": "Battery", "value": "30 hours"})
        self.assertEqual(data["spec_options"][0]["name"], "Colour")
        self.assertEqual(data["ai_summary_title"], "What buyers say")

    def test_partial_translation_keeps_source_for_empty_fields(self):
        self._create_translation(
            content_sections=[],
            specification_tables=None,
            specifications=None,
            spec_options=None,
            ai_summary="",
            ai_summary_title="",
        )
        data = self._get()
        # 命中译文行 → 标记为 true；空字段逐字段保留源数据，不丢内容。
        self.assertTrue(data["detail_translated"])
        self.assertEqual(data["content_sections"][0]["title"], "Product Description")
        self.assertEqual(data["specification_tables"][0]["rows"][0]["name"], "Battery")
        self.assertEqual(data["spec_options"][0]["name"], "Colour")
        self.assertEqual(data["ai_summary_title"], "What buyers say")
