from datetime import timedelta
from decimal import Decimal

from accounts_staff.models import PlatformRole
from catalog.domain import ProductSourceIdentityInvalid, SkuSpecificationInvalid
from catalog.models import (
    AttributeDefinition,
    AttributeOption,
    Sku,
    SkuSourceIdentity,
    Spu,
    SpuSourceIdentity,
)
from catalog.product_services import (
    get_or_create_sku_from_source,
    get_or_create_spu_from_source,
)
from django.test import TestCase
from django.utils import timezone
from merchants.models import Merchant
from merchants.services import get_import_fallback_merchant

from offers.domain import (
    InventoryAdjustmentInvalid,
    InventoryIdempotencyConflict,
    MoneyValueInvalid,
    OfferSourceIdentityInvalid,
)
from offers.models import Currency, InventoryLedger, Market, Offer, OfferSourceIdentity
from offers.services import adjust_offer_inventory, import_offer_from_source


class ProductOfferDomainTests(TestCase):
    def setUp(self):
        self.currency = Currency.objects.get(code="GBP")
        self.market = Market.objects.get(code="GB")
        self.merchant = get_import_fallback_merchant()

    def create_spu(self, source_id="product-1"):
        spu, _ = get_or_create_spu_from_source(
            source_system="joybuy",
            source_id=source_id,
            source_url=f"https://example.test/products/{source_id}",
            title=f"Product {source_id}",
        )
        return spu

    def create_sku(self, source_id="sku-1", specification=None):
        spu = self.create_spu(source_id=f"product-for-{source_id}")
        sku, _ = get_or_create_sku_from_source(
            spu=spu,
            source_system="joybuy",
            source_id=source_id,
            specification=specification or {},
        )
        return sku

    def import_offer(
        self,
        *,
        sku=None,
        merchant=None,
        source_id="offer-1",
        current_price="19.99",
        list_price="24.99",
        source_availability=Offer.SourceAvailability.IN_STOCK,
        observed_at=None,
    ):
        return import_offer_from_source(
            sku=sku or self.create_sku(source_id=f"sku-for-{source_id}"),
            merchant=merchant or self.merchant,
            market=self.market,
            currency=self.currency,
            source_system="joybuy",
            source_id=source_id,
            current_price=current_price,
            list_price=list_price,
            source_availability=source_availability,
            source_url=f"https://example.test/offers/{source_id}",
            observed_at=observed_at,
        )

    def test_spu_source_identity_is_idempotent_and_source_scoped(self):
        first, first_created = get_or_create_spu_from_source(
            source_system="Joybuy",
            source_id="spu-42",
            source_url="https://example.test/old",
            title="Original title",
        )
        same, same_created = get_or_create_spu_from_source(
            source_system="joybuy",
            source_id="spu-42",
            source_url="https://example.test/new",
            title="Ignored source refresh title",
        )
        other_source, other_created = get_or_create_spu_from_source(
            source_system="other-market",
            source_id="spu-42",
            title="Other source product",
        )

        self.assertTrue(first_created)
        self.assertFalse(same_created)
        self.assertTrue(other_created)
        self.assertEqual(first, same)
        self.assertNotEqual(first, other_source)
        self.assertEqual(Spu.objects.count(), 2)
        self.assertEqual(SpuSourceIdentity.objects.count(), 2)
        self.assertEqual(
            first.source_identities.get().source_url,
            "https://example.test/new",
        )
        self.assertEqual(first.translations.get().title, "Original title")

    def test_sku_specification_is_canonical_and_unique_within_spu(self):
        colour = AttributeDefinition.objects.create(
            code="colour",
            name="Colour",
            data_type=AttributeDefinition.DataType.CHOICE,
            scope=AttributeDefinition.Scope.SKU,
            is_variant_axis=True,
        )
        AttributeOption.objects.create(attribute=colour, value="red", label="Red")
        AttributeDefinition.objects.create(
            code="size",
            name="Size",
            data_type=AttributeDefinition.DataType.TEXT,
            scope=AttributeDefinition.Scope.SKU,
            is_variant_axis=True,
        )
        spu = self.create_spu("spec-product")

        first, first_created = get_or_create_sku_from_source(
            spu=spu,
            source_system="joybuy",
            source_id="source-sku-a",
            specification={"size": "M", "colour": "red"},
        )
        same_combination, second_created = get_or_create_sku_from_source(
            spu=spu,
            source_system="joybuy",
            source_id="source-sku-b",
            specification={"colour": "red", "size": "M"},
        )

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first, same_combination)
        self.assertEqual(first.specification, {"colour": "red", "size": "M"})
        self.assertEqual(Sku.objects.count(), 1)
        self.assertEqual(SkuSourceIdentity.objects.count(), 2)

    def test_source_sku_identity_cannot_change_product_or_specification(self):
        size = AttributeDefinition.objects.create(
            code="size",
            name="Size",
            data_type=AttributeDefinition.DataType.TEXT,
            scope=AttributeDefinition.Scope.SKU,
        )
        self.assertIsNotNone(size.pk)
        first_spu = self.create_spu("first-product")
        second_spu = self.create_spu("second-product")
        get_or_create_sku_from_source(
            spu=first_spu,
            source_system="joybuy",
            source_id="stable-sku",
            specification={"size": "M"},
        )

        with self.assertRaises(ProductSourceIdentityInvalid):
            get_or_create_sku_from_source(
                spu=second_spu,
                source_system="joybuy",
                source_id="stable-sku",
                specification={"size": "L"},
            )

    def test_invalid_sku_choice_is_rejected(self):
        colour = AttributeDefinition.objects.create(
            code="colour",
            name="Colour",
            data_type=AttributeDefinition.DataType.CHOICE,
            scope=AttributeDefinition.Scope.SKU,
        )
        AttributeOption.objects.create(attribute=colour, value="red", label="Red")

        with self.assertRaises(SkuSpecificationInvalid):
            get_or_create_sku_from_source(
                spu=self.create_spu("invalid-choice-product"),
                source_system="joybuy",
                source_id="invalid-choice-sku",
                specification={"colour": "blue"},
            )

        AttributeDefinition.objects.create(
            code="pack-count",
            name="Pack count",
            data_type=AttributeDefinition.DataType.INTEGER,
            scope=AttributeDefinition.Scope.SKU,
        )
        with self.assertRaises(SkuSpecificationInvalid):
            get_or_create_sku_from_source(
                spu=self.create_spu("invalid-integer-product"),
                source_system="joybuy",
                source_id="invalid-integer-sku",
                specification={"pack-count": Decimal("1.5")},
            )

    def test_offer_belongs_to_merchant_and_defaults_inventory_to_9999(self):
        offer, created = self.import_offer()

        self.assertTrue(created)
        self.assertEqual(offer.merchant, self.merchant)
        self.assertEqual(offer.local_inventory, 9999)
        self.assertEqual(offer.display_inventory, "999+")
        self.assertIsInstance(offer.current_price, Decimal)
        self.assertEqual(offer.current_price, Decimal("19.99"))
        ledger = offer.inventory_ledger.get()
        self.assertEqual(ledger.reason, InventoryLedger.Reason.INITIAL_IMPORT)
        self.assertEqual(ledger.quantity_delta, 9999)
        self.assertEqual(ledger.balance_after, 9999)

    def test_offer_source_identity_is_idempotent_and_prices_are_snapshotted(self):
        sku = self.create_sku("idempotent-offer-sku")
        observed = timezone.now()
        first, first_created = self.import_offer(
            sku=sku,
            source_id="stable-offer",
            observed_at=observed,
        )
        same, same_created = self.import_offer(
            sku=sku,
            source_id="stable-offer",
            observed_at=observed,
        )
        updated, updated_created = self.import_offer(
            sku=sku,
            source_id="stable-offer",
            current_price="17.50",
            list_price="24.99",
            observed_at=observed + timedelta(hours=6),
        )

        self.assertTrue(first_created)
        self.assertFalse(same_created)
        self.assertFalse(updated_created)
        self.assertEqual(first, same)
        self.assertEqual(first, updated)
        self.assertEqual(Offer.objects.count(), 1)
        self.assertEqual(OfferSourceIdentity.objects.count(), 1)
        self.assertEqual(updated.price_snapshots.count(), 2)
        updated.refresh_from_db()
        self.assertEqual(updated.current_price, Decimal("17.5000"))

    def test_offer_source_identity_cannot_move_between_merchants(self):
        sku = self.create_sku("merchant-isolation-sku")
        self.import_offer(sku=sku, source_id="merchant-bound-offer")
        other_merchant = Merchant.objects.create(
            slug="other-offer-merchant",
            display_name="Other Merchant",
            onboarding_status=Merchant.OnboardingStatus.ACTIVE,
        )

        with self.assertRaises(OfferSourceIdentityInvalid):
            self.import_offer(
                sku=sku,
                merchant=other_merchant,
                source_id="merchant-bound-offer",
            )

    def test_money_values_reject_floats_excess_precision_and_invalid_list_price(self):
        sku = self.create_sku("money-sku")
        with self.assertRaises(MoneyValueInvalid):
            self.import_offer(sku=sku, source_id="float-offer", current_price=19.99)
        with self.assertRaises(MoneyValueInvalid):
            self.import_offer(sku=sku, source_id="precision-offer", current_price="19.999")
        with self.assertRaises(MoneyValueInvalid):
            self.import_offer(
                sku=sku,
                source_id="list-price-offer",
                current_price="20.00",
                list_price="19.00",
            )
        self.assertFalse(Offer.objects.exists())

    def test_source_availability_is_separate_from_local_inventory(self):
        offer, _ = self.import_offer(
            source_id="out-of-stock-offer",
            source_availability=Offer.SourceAvailability.OUT_OF_STOCK,
        )

        self.assertEqual(offer.source_availability, Offer.SourceAvailability.OUT_OF_STOCK)
        self.assertEqual(offer.local_inventory, 9999)

    def test_inventory_adjustment_is_atomic_idempotent_and_cannot_go_negative(self):
        offer, _ = self.import_offer(source_id="inventory-offer")
        first = adjust_offer_inventory(
            offer=offer,
            quantity_delta=-10,
            reason=InventoryLedger.Reason.MANUAL_ADJUSTMENT,
            idempotency_key="inventory-adjustment-1",
            note="Cycle count correction",
        )
        repeated = adjust_offer_inventory(
            offer=offer,
            quantity_delta=-10,
            reason=InventoryLedger.Reason.MANUAL_ADJUSTMENT,
            idempotency_key="inventory-adjustment-1",
        )

        offer.refresh_from_db()
        self.assertEqual(first, repeated)
        self.assertEqual(offer.local_inventory, 9989)
        self.assertEqual(offer.inventory_ledger.count(), 2)
        with self.assertRaises(InventoryIdempotencyConflict):
            adjust_offer_inventory(
                offer=offer,
                quantity_delta=-11,
                reason=InventoryLedger.Reason.MANUAL_ADJUSTMENT,
                idempotency_key="inventory-adjustment-1",
            )
        with self.assertRaises(InventoryAdjustmentInvalid):
            adjust_offer_inventory(
                offer=offer,
                quantity_delta=-10000,
                reason=InventoryLedger.Reason.CORRECTION,
                idempotency_key="inventory-adjustment-negative",
            )

    def test_market_currency_and_platform_permissions_are_seeded(self):
        self.assertEqual(self.market.default_currency, self.currency)
        self.assertEqual(self.market.default_locale, "en-GB")
        self.assertEqual(self.market.time_zone, "Europe/London")
        self.assertEqual(self.currency.exponent, 2)
        permission_codes = set(
            PlatformRole.objects.get(code="platform_admin").permissions.values_list(
                "code",
                flat=True,
            )
        )
        self.assertIn("catalog.products.manage", permission_codes)
        self.assertIn("offers.manage", permission_codes)
