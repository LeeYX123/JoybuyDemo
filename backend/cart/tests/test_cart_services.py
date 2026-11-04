from accounts_buyers.models import BuyerAccount
from catalog.product_services import get_or_create_sku_from_source, get_or_create_spu_from_source
from django.test import RequestFactory, TestCase
from merchants.services import get_import_fallback_merchant
from offers.models import Market, Offer
from offers.services import import_offer_from_source

from cart.models import Cart, CartItem
from cart.services import (
    CartError,
    add_item,
    merge_anonymous_cart,
    remove_item,
    resolve_cart_context,
    serialize_cart,
    update_item,
)


class CartTestBase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.merchant = get_import_fallback_merchant()
        self.market = Market.objects.get(code="GB")
        self.currency = self.market.default_currency
        self.spu, _ = get_or_create_spu_from_source(
            source_system="joybuy", source_id="cart-spu", title="Carted product"
        )
        from catalog.models import Spu

        Spu.objects.filter(pk=self.spu.pk).update(status=Spu.Status.ACTIVE)
        self.spu.refresh_from_db()
        self.sku, _ = get_or_create_sku_from_source(
            spu=self.spu,
            source_system="joybuy",
            source_id="cart-sku",
            specification={},
            skip_attribute_validation=True,
        )
        self.offer, _ = import_offer_from_source(
            sku=self.sku,
            merchant=self.merchant,
            market=self.market,
            currency=self.currency,
            source_system="joybuy",
            source_id="cart-offer",
            current_price="12.50",
        )
        Offer.objects.filter(pk=self.offer.pk).update(status=Offer.Status.ACTIVE)
        self.offer.refresh_from_db()

    def anonymous_context(self, token=""):
        request = self.factory.get("/")
        request.COOKIES = {"joybuy_cart_token": token} if token else {}
        return resolve_cart_context(request)

    def buyer_context(self, email="cart@joybuy.test", token=""):
        account, _ = BuyerAccount.objects.get_or_create(
            email=email, defaults={"status": BuyerAccount.Status.ACTIVE}
        )
        request = self.factory.get("/")
        request.COOKIES = {"joybuy_cart_token": token} if token else {}
        context = resolve_cart_context(request)
        context.account = account
        return context


class CartServiceTests(CartTestBase):
    def test_anonymous_add_is_idempotent_per_offer_and_caps_quantity(self):
        context = self.anonymous_context()
        add_item(context, offer_public_id=str(self.offer.public_id), quantity=2)
        add_item(context, offer_public_id=str(self.offer.public_id), quantity=3)

        cart = Cart.objects.get(
            anonymous_token=context.new_anonymous_token or context.anonymous_token
        )
        self.assertEqual(cart.items.count(), 1)
        self.assertEqual(cart.items.get().quantity, 5)

        with self.assertRaises(CartError) as raised:
            add_item(context, offer_public_id=str(self.offer.public_id), quantity=99)
        self.assertEqual(raised.exception.code, "QUANTITY_LIMIT")

    def test_adding_to_cart_never_checks_out_the_cart(self):
        # Adding items keeps the cart OPEN; checkout status arrives with WP-29.
        context = self.anonymous_context()
        add_item(context, offer_public_id=str(self.offer.public_id), quantity=1)
        cart = Cart.objects.get(
            anonymous_token=context.new_anonymous_token or context.anonymous_token
        )
        self.assertEqual(cart.status, Cart.Status.OPEN)

    def test_unavailable_offers_and_stock_are_rejected(self):
        Offer.objects.filter(pk=self.offer.pk).update(status=Offer.Status.DRAFT)
        with self.assertRaises(CartError) as raised:
            add_item(
                self.anonymous_context(), offer_public_id=str(self.offer.public_id), quantity=1
            )
        self.assertEqual(raised.exception.code, "SKU_NOT_AVAILABLE")

        Offer.objects.filter(pk=self.offer.pk).update(status=Offer.Status.ACTIVE, local_inventory=1)
        with self.assertRaises(CartError) as raised:
            add_item(
                self.anonymous_context(), offer_public_id=str(self.offer.public_id), quantity=2
            )
        self.assertEqual(raised.exception.code, "INSUFFICIENT_STOCK")

    def test_update_and_remove_items(self):
        context = self.anonymous_context(token="tok-update")
        add_item(context, offer_public_id=str(self.offer.public_id), quantity=1)
        item = CartItem.objects.get(cart__anonymous_token="tok-update")

        update_item(context, item_public_id=str(item.public_id), quantity=4)
        self.assertEqual(CartItem.objects.get(pk=item.pk).quantity, 4)
        remove_item(context, item_public_id=str(item.public_id))
        self.assertEqual(CartItem.objects.count(), 0)

        with self.assertRaises(CartError):
            update_item(context, item_public_id=str(item.public_id), quantity=2)

    def test_serialize_flags_price_and_availability_changes_without_dropping(self):
        context = self.anonymous_context(token="tok-serialize")
        add_item(context, offer_public_id=str(self.offer.public_id), quantity=2)
        snapshot = serialize_cart(Cart.objects.get(anonymous_token="tok-serialize"))
        self.assertFalse(snapshot["needs_attention"])
        self.assertEqual(snapshot["subtotal"], "25.0000")

        # Price changes are picked up live on the next read.
        Offer.objects.filter(pk=self.offer.pk).update(current_price="15.00")
        snapshot = serialize_cart(Cart.objects.get(anonymous_token="tok-serialize"))
        self.assertEqual(snapshot["subtotal"], "30.0000")

        # Unavailable offer: row is flagged, not dropped.
        Offer.objects.filter(pk=self.offer.pk).update(source_availability="UNAVAILABLE")
        snapshot = serialize_cart(Cart.objects.get(anonymous_token="tok-serialize"))
        self.assertTrue(snapshot["needs_attention"])
        self.assertEqual(snapshot["items"][0]["issue"], "SKU_NOT_AVAILABLE")
        self.assertEqual(snapshot["subtotal"], None)

    def test_merge_folds_anonymous_cart_into_buyer_cart(self):
        anonymous_context = self.anonymous_context(token="tok-merge")
        add_item(anonymous_context, offer_public_id=str(self.offer.public_id), quantity=2)

        buyer_context = self.buyer_context(token="tok-merge")
        result = merge_anonymous_cart(buyer_context)
        self.assertEqual(result["merged_items"], 1)

        buyer_cart = Cart.objects.get(account=buyer_context.account, status=Cart.Status.OPEN)
        self.assertEqual(buyer_cart.items.get().quantity, 2)
        anonymous_cart = Cart.objects.get(anonymous_token="tok-merge")
        self.assertEqual(anonymous_cart.status, Cart.Status.MERGED)

        # Signed-in adds continue on the buyer cart.
        add_item(buyer_context, offer_public_id=str(self.offer.public_id), quantity=1)
        self.assertEqual(buyer_cart.items.get().quantity, 3)

    def test_single_open_cart_per_buyer(self):
        context = self.buyer_context()
        add_item(context, offer_public_id=str(self.offer.public_id), quantity=1)
        add_item(context, offer_public_id=str(self.offer.public_id), quantity=1)
        self.assertEqual(Cart.objects.filter(account=context.account).count(), 1)
        self.assertEqual(CartItem.objects.count(), 1)
