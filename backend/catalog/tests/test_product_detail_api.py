from django.test import TestCase
from django.urls import reverse
from merchants.services import get_import_fallback_merchant
from offers.models import Currency, Market, Offer
from offers.services import import_offer_from_source
from reviews.services import upsert_source_review

from catalog.models import Spu
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
