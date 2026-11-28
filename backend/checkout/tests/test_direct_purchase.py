"""立即购买（Buy now）直购上下文：quote + place_order（2026-11-28）。

口径：
- 直购 = ?offer=<offer_public_id>&qty=<n> 的独立结账上下文，不读写购物车；
- quote 直购返回与购物车同形的 items（title/price/merchant/issue 判定同口径）；
- place_order 直购不写 cart 行、不把任何购物车标成 CHECKED_OUT（隔离）；
- 未带 offer_public_id 的请求走原购物车路径（回归由 orders 流程用例覆盖）。
"""

import json

from django.test import RequestFactory, TestCase
from django.urls import reverse

from accounts_buyers.models import BuyerAccount
from accounts_buyers.services import create_buyer_session
from cart.models import Cart
from cart.services import add_item, resolve_cart_context, serialize_cart
from catalog.models import Spu
from catalog.product_services import get_or_create_sku_from_source, get_or_create_spu_from_source
from checkout.checkout_views import serialize_direct_purchase
from checkout.models import Address
from merchants.services import get_import_fallback_merchant
from offers.models import Market, Offer
from offers.services import import_offer_from_source
from orders.models import Order
from orders.order_services import OrderError, place_order


class DirectPurchaseTestBase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.merchant = get_import_fallback_merchant()
        self.market = Market.objects.get(code="GB")
        self.spu, _ = get_or_create_spu_from_source(
            source_system="joybuy", source_id="direct-spu", title="Direct buy product"
        )
        Spu.objects.filter(pk=self.spu.pk).update(status=Spu.Status.ACTIVE)
        self.sku, _ = get_or_create_sku_from_source(
            spu=self.spu,
            source_system="joybuy",
            source_id="direct-sku",
            specification={},
            skip_attribute_validation=True,
        )
        self.offer, _ = import_offer_from_source(
            sku=self.sku,
            merchant=self.merchant,
            market=self.market,
            currency=self.market.default_currency,
            source_system="joybuy",
            source_id="direct-offer",
            current_price="30.00",
        )
        Offer.objects.filter(pk=self.offer.pk).update(
            status=Offer.Status.ACTIVE, local_inventory=5, cost_price="21.00"
        )
        self.offer.refresh_from_db()

        self.account, _ = BuyerAccount.objects.get_or_create(
            email="direct@joybuy.test", defaults={"status": BuyerAccount.Status.ACTIVE}
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

    def quote(self, payload, with_session=True):
        if not with_session:
            self.client.cookies.pop("joybuy_buyer_session", None)
        return self.client.post(
            reverse("checkout-quote"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def add_cart_item(self, offer, quantity=1):
        context = resolve_cart_context(self.factory.get("/"))
        context.account = self.account
        add_item(context, offer_public_id=str(offer.public_id), quantity=quantity)
        return Cart.objects.get(account=self.account, status=Cart.Status.OPEN)


class DirectQuoteTests(DirectPurchaseTestBase):
    def test_direct_quote_returns_single_item_with_shipping(self):
        response = self.quote(
            {
                "address_public_id": str(self.address.public_id),
                "offer_public_id": str(self.offer.public_id),
                "quantity": 2,
            }
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["items"]), 1)
        item = data["items"][0]
        self.assertEqual(item["offer_public_id"], str(self.offer.public_id))
        self.assertEqual(item["title"], "Direct buy product")
        self.assertEqual(item["quantity"], 2)
        self.assertEqual(item["price"], "30.0000")
        self.assertIsNone(item["issue"])
        self.assertTrue(item["is_valid"])
        self.assertEqual(data["subtotal"], "60.0000")
        self.assertEqual(data["shipping_method"], "FREE")
        self.assertEqual(data["total"], "60.0000")

    def test_direct_quote_below_threshold_charges_standard_shipping(self):
        Offer.objects.filter(pk=self.offer.pk).update(current_price="10.00")
        self.offer.refresh_from_db()
        data = self.quote(
            {
                "address_public_id": str(self.address.public_id),
                "offer_public_id": str(self.offer.public_id),
                "quantity": 1,
            }
        ).json()
        self.assertEqual(data["subtotal"], "10.0000")
        # 2026-11-28 全站免邮：直购同样运费 0。
        self.assertEqual(data["shipping_method"], "FREE")
        self.assertEqual(data["total"], "10.0000")

    def test_direct_quote_default_quantity_is_one(self):
        data = self.quote(
            {
                "address_public_id": str(self.address.public_id),
                "offer_public_id": str(self.offer.public_id),
            }
        ).json()
        self.assertEqual(data["items"][0]["quantity"], 1)

    def test_direct_quote_invalid_quantity_rejected(self):
        response = self.quote(
            {
                "address_public_id": str(self.address.public_id),
                "offer_public_id": str(self.offer.public_id),
                "quantity": 0,
            }
        )
        self.assertEqual(response.status_code, 400)

    def test_direct_quote_unknown_offer_404(self):
        response = self.quote(
            {
                "address_public_id": str(self.address.public_id),
                "offer_public_id": "00000000-0000-0000-0000-000000000000",
            }
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "SKU_NOT_AVAILABLE")

    def test_direct_quote_inactive_offer_flags_attention(self):
        Offer.objects.filter(pk=self.offer.pk).update(status=Offer.Status.INACTIVE)
        data = self.quote(
            {
                "address_public_id": str(self.address.public_id),
                "offer_public_id": str(self.offer.public_id),
                "quantity": 1,
            }
        ).json()
        self.assertEqual(data["error"]["code"], "CART_INVALID")

    def test_direct_quote_quantity_over_inventory_flags_attention(self):
        data = self.quote(
            {
                "address_public_id": str(self.address.public_id),
                "offer_public_id": str(self.offer.public_id),
                "quantity": 6,
            }
        ).json()
        self.assertEqual(data["error"]["code"], "CART_INVALID")

    def test_direct_quote_requires_signin(self):
        response = self.quote(
            {
                "address_public_id": str(self.address.public_id),
                "offer_public_id": str(self.offer.public_id),
            },
            with_session=False,
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "AUTH_REQUIRED")

    def test_serialize_direct_purchase_matches_cart_row_shape(self):
        snapshot = serialize_direct_purchase(self.offer, 2)
        cart = self.add_cart_item(self.offer, 2)
        cart_snapshot = serialize_cart(cart)
        item, cart_item = snapshot["items"][0], cart_snapshot["items"][0]
        self.assertEqual(
            [
                "offer_public_id",
                "spu_public_id",
                "title",
                "quantity",
                "price",
                "currency",
                "inventory_display",
                "merchant",
                "is_valid",
                "issue",
            ],
            [key for key in cart_item if key != "public_id"],
        )
        self.assertEqual(item["title"], cart_item["title"])
        self.assertEqual(item["price"], cart_item["price"])
        self.assertEqual(item["merchant"], cart_item["merchant"])
        # 直购快照不指向任何购物车行。
        self.assertEqual(snapshot["public_id"], "")
        self.assertEqual(item["public_id"], "")


class DirectPlaceOrderTests(DirectPurchaseTestBase):
    def _place(self, quantity=2, payment_method="CARD", offer=None):
        return place_order(
            account=self.account,
            cart_snapshot=None,
            address_snapshot={"public_id": str(self.address.public_id)},
            payment_method=payment_method,
            offer_public_id=str((offer or self.offer).public_id),
            quantity=quantity,
        )

    def test_direct_place_order_creates_paid_order_without_touching_cart(self):
        # 购物车里已有商品 A（独立 SKU 的另一个 offer）——直购 B 不得影响它。
        # 注意：import_offer_from_source 按 (sku, merchant, market) 归并，同 SKU
        # 只会改价复用原 offer，必须造独立 SKU 才是真正的第二个商品。
        other_sku, _ = get_or_create_sku_from_source(
            spu=self.spu,
            source_system="joybuy",
            source_id="direct-sku-a",
            specification={"colour": "a"},
            skip_attribute_validation=True,
        )
        other_offer, _ = import_offer_from_source(
            sku=other_sku,
            merchant=self.merchant,
            market=self.market,
            currency=self.market.default_currency,
            source_system="joybuy",
            source_id="direct-offer-a",
            current_price="12.00",
        )
        Offer.objects.filter(pk=other_offer.pk).update(status=Offer.Status.ACTIVE, local_inventory=5)
        cart = self.add_cart_item(other_offer, 1)

        order = self._place(quantity=2)

        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.items.count(), 1)
        item = order.items.get()
        self.assertEqual(item.offer_id, self.offer.pk)
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.title, "Direct buy product")
        self.assertEqual(str(order.total), "60.0000")
        # 购物车隔离：A 仍在 OPEN 购物车里，购物车未被标 CHECKED_OUT。
        cart.refresh_from_db()
        self.assertEqual(cart.status, Cart.Status.OPEN)
        self.assertEqual(cart.items.count(), 1)
        self.assertEqual(cart.items.get().offer_id, other_offer.pk)

    def test_direct_place_order_insufficient_stock_rejected(self):
        with self.assertRaises(OrderError) as raised:
            self._place(quantity=6)
        # 快照预检先于事务锁行：与购物车路径同口径返回 CART_INVALID（needs_attention）。
        self.assertEqual(raised.exception.code, "CART_INVALID")
        self.assertFalse(Order.objects.exists())

    def test_direct_place_order_inactive_offer_rejected(self):
        Offer.objects.filter(pk=self.offer.pk).update(status=Offer.Status.INACTIVE)
        with self.assertRaises(OrderError) as raised:
            self._place(quantity=1)
        self.assertEqual(raised.exception.code, "CART_INVALID")
        self.assertFalse(Order.objects.exists())

    def test_direct_place_order_non_whitelisted_rejected(self):
        BuyerAccount.objects.filter(pk=self.account.pk).update(purchase_whitelisted=False)
        self.account.refresh_from_db()
        with self.assertRaises(OrderError) as raised:
            self._place(quantity=1)
        self.assertEqual(raised.exception.code, "NOT_WHITELISTED")
        self.assertFalse(Order.objects.exists())

    def test_direct_place_order_payment_disabled_rejected(self):
        BuyerAccount.objects.filter(pk=self.account.pk).update(payment_enabled=False)
        self.account.refresh_from_db()
        with self.assertRaises(OrderError) as raised:
            self._place(quantity=1)
        self.assertEqual(raised.exception.code, "PAYMENT_DISABLED")
        self.assertFalse(Order.objects.exists())

    def test_direct_place_order_invalid_quantity_rejected(self):
        with self.assertRaises(OrderError) as raised:
            place_order(
                account=self.account,
                cart_snapshot=None,
                address_snapshot={"public_id": str(self.address.public_id)},
                payment_method="CARD",
                offer_public_id=str(self.offer.public_id),
                quantity=0,
            )
        self.assertEqual(raised.exception.code, "CART_INVALID")
        self.assertFalse(Order.objects.exists())

    def test_direct_place_order_via_api_and_cart_checkout_path_untouched(self):
        response = self.client.post(
            reverse("orders"),
            data=json.dumps(
                {
                    "address": {"public_id": str(self.address.public_id)},
                    "payment_method": "CARD",
                    "offer_public_id": str(self.offer.public_id),
                    "quantity": 2,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], Order.Status.PAID)
        self.assertFalse(Cart.objects.filter(account=self.account).exists())
