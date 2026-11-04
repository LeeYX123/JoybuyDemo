import json
from datetime import timedelta

from accounts_buyers.models import BuyerAccount
from accounts_buyers.services import create_buyer_session
from cart.models import Cart
from cart.services import add_item, resolve_cart_context, serialize_cart
from catalog.models import Spu
from catalog.product_services import get_or_create_sku_from_source, get_or_create_spu_from_source
from checkout.models import Address
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from merchants.services import get_import_fallback_merchant
from offers.models import InventoryLedger, Market, Offer
from offers.services import import_offer_from_source

from orders.models import InventoryReservation, Order
from orders.order_services import cancel_expired_orders, cancel_order, place_order
from orders.order_views import _error  # noqa: F401  (kept for parity)


class CheckoutOrderTestBase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.merchant = get_import_fallback_merchant()
        self.market = Market.objects.get(code="GB")
        self.spu, _ = get_or_create_spu_from_source(
            source_system="joybuy", source_id="order-spu", title="Ordered product"
        )
        Spu.objects.filter(pk=self.spu.pk).update(status=Spu.Status.ACTIVE)
        self.sku, _ = get_or_create_sku_from_source(
            spu=self.spu,
            source_system="joybuy",
            source_id="order-sku",
            specification={},
            skip_attribute_validation=True,
        )
        self.offer, _ = import_offer_from_source(
            sku=self.sku,
            merchant=self.merchant,
            market=self.market,
            currency=self.market.default_currency,
            source_system="joybuy",
            source_id="order-offer",
            current_price="25.00",
        )
        Offer.objects.filter(pk=self.offer.pk).update(status=Offer.Status.ACTIVE)

        self.account, _ = BuyerAccount.objects.get_or_create(
            email="order@joybuy.test", defaults={"status": BuyerAccount.Status.ACTIVE}
        )
        token, _session = create_buyer_session(
            account=self.account, ip_address="127.0.0.1", user_agent="test"
        )
        self.client.cookies["joybuy_buyer_session"] = token
        self.address = Address.objects.create(
            account=self.account,
            full_name="Test Buyer",
            phone="+447000000000",
            line1="1 High Street",
            city="London",
            postcode="SW1A 1AA",
        )

    def add_to_cart(self, quantity=1, price="25.00"):
        context = resolve_cart_context(self.factory.get("/"))
        context.account = self.account
        Offer.objects.filter(pk=self.offer.pk).update(current_price=price)
        self.offer.refresh_from_db()
        add_item(context, offer_public_id=str(self.offer.public_id), quantity=quantity)
        return serialize_cart(Cart.objects.get(account=self.account, status=Cart.Status.OPEN))


class CheckoutQuoteTests(CheckoutOrderTestBase):
    def test_quote_computes_subtotal_shipping_and_total(self):
        self.add_to_cart(quantity=1)
        response = self.client.post(
            reverse("checkout-quote"),
            data=json.dumps({"address_public_id": str(self.address.public_id)}),
            content_type="application/json",
        )
        data = response.json()
        self.assertEqual(data["subtotal"], "25.0000")
        self.assertEqual(data["shipping_cost"], "0.0000", "Free shipping over £20.")
        self.assertEqual(data["total"], "25.0000")
        self.assertEqual(data["shipping_method"], "FREE")

    def test_quote_below_threshold_charges_standard_shipping(self):
        self.add_to_cart(quantity=1, price="10.00")
        data = self.client.post(
            reverse("checkout-quote"),
            data=json.dumps({"address_public_id": str(self.address.public_id)}),
            content_type="application/json",
        ).json()
        self.assertIn(data["shipping_cost"], {"3.9900", "3.99"})
        self.assertEqual(data["total"], "13.9900")

    def test_unserviceable_and_unknown_addresses_are_rejected(self):
        self.add_to_cart()
        overseas = Address.objects.create(
            account=self.account,
            full_name="X",
            phone="1",
            line1="2",
            city="Paris",
            postcode="75001",
            country_code="FR",
        )
        response = self.client.post(
            reverse("checkout-quote"),
            data=json.dumps({"address_public_id": str(overseas.public_id)}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "ADDRESS_UNSUPPORTED")

        missing = self.client.post(
            reverse("checkout-quote"),
            data=json.dumps({"address_public_id": "00000000-0000-0000-0000-000000000000"}),
            content_type="application/json",
        )
        self.assertEqual(missing.status_code, 404)


class OrderPlacementTests(CheckoutOrderTestBase):
    def place(self, quantity=1, price="25.00"):
        snapshot = self.add_to_cart(quantity=quantity, price=price)
        return place_order(
            account=self.account,
            cart_snapshot=snapshot,
            address_snapshot={"public_id": str(self.address.public_id)},
        )

    def test_order_creation_decrements_inventory_with_ledger(self):
        order = self.place(quantity=2)
        self.assertEqual(order.status, Order.Status.PENDING_PAYMENT)
        self.assertEqual(str(order.total), "50.0000")
        self.assertLess(
            abs((order.payment_expires_at - order.created_at).total_seconds() - 3600), 5
        )
        self.assertEqual(len(order.items.all()), 1)
        self.assertEqual(str(order.items.get().unit_price), "25.0000")
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.local_inventory, 9997)
        reservation = InventoryReservation.objects.get(order=order)
        self.assertEqual(reservation.quantity, 2)
        self.assertFalse(reservation.released)
        ledger = InventoryLedger.objects.get(
            idempotency_key=f"order-reserve:{order.public_id}:{self.offer.public_id}"
        )
        self.assertEqual(ledger.reason, InventoryLedger.Reason.RESERVATION)

        # Cart checked out and closed.
        self.assertEqual(Cart.objects.get(account=self.account).status, Cart.Status.CHECKED_OUT)

    def test_insufficient_stock_at_place_time_raises_without_state_change(self):
        snapshot = self.add_to_cart(quantity=1)
        Offer.objects.filter(pk=self.offer.pk).update(local_inventory=0)
        self.offer.refresh_from_db()
        with self.assertRaises(Exception) as raised:
            place_order(
                account=self.account,
                cart_snapshot=snapshot,
                address_snapshot={"public_id": str(self.address.public_id)},
            )
        self.assertEqual(raised.exception.code, "INSUFFICIENT_STOCK")
        self.assertFalse(Order.objects.exists())
        self.assertEqual(InventoryReservation.objects.count(), 0)

    def test_payment_attempt_returns_region_unsupported(self):
        order = self.place()
        response = self.client.post(
            reverse("payment-attempt", kwargs={"public_id": order.public_id})
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "PAYMENT_REGION_UNSUPPORTED")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING_PAYMENT)

    def test_cancel_releases_inventory_once_and_is_idempotent(self):
        order = self.place(quantity=3)
        self.assertTrue(cancel_order(order, reason="PAYMENT_WINDOW_EXPIRED"))
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.local_inventory, 9999)
        self.assertTrue(InventoryReservation.objects.get(order=order).released)

        # Second cancel is a no-op: no double release.
        self.assertFalse(cancel_order(order, reason="PAYMENT_WINDOW_EXPIRED"))
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.local_inventory, 9999)
        self.assertEqual(
            InventoryLedger.objects.filter(
                idempotency_key=f"order-release:{order.public_id}:{self.offer.public_id}"
            ).count(),
            1,
        )

    def test_expired_sweep_cancels_and_releases_only_expired_orders(self):
        fresh = self.place(quantity=1)
        expired = self.place(quantity=1)
        Order.objects.filter(pk=expired.pk).update(
            payment_expires_at=timezone.now() - timedelta(minutes=1)
        )

        result = cancel_expired_orders()
        self.assertEqual(result["canceled"], 1)
        expired.refresh_from_db()
        fresh.refresh_from_db()
        self.assertEqual(expired.status, Order.Status.CANCELED)
        self.assertEqual(fresh.status, Order.Status.PENDING_PAYMENT)

        # Re-running the sweep is idempotent.
        self.assertEqual(cancel_expired_orders()["canceled"], 0)

    def test_buyer_order_listing_and_detail_states(self):
        order = self.place()
        listing = self.client.get(reverse("orders")).json()
        self.assertEqual(listing["orders"][0]["status"], "PENDING_PAYMENT")

        detail = self.client.get(
            reverse("order-detail", kwargs={"public_id": order.public_id})
        ).json()
        self.assertEqual(detail["items"][0]["title"], "Ordered product")
        self.assertEqual(detail["shipping_address"]["postcode"], "SW1A 1AA")

        cancel_order(order, reason="PAYMENT_WINDOW_EXPIRED")
        canceled_listing = self.client.get(reverse("orders")).json()
        self.assertEqual(canceled_listing["orders"][0]["status"], "CANCELED")
