from django.test import RequestFactory, TestCase

from accounts_buyers.models import BuyerAccount
from cart.models import Cart, CartItem
from cart.services import (
    CartError,
    add_item,
    merchant_entry,
    merge_anonymous_cart,
    remove_item,
    resolve_cart_context,
    serialize_cart,
    update_item,
)
from catalog.product_services import get_or_create_sku_from_source, get_or_create_spu_from_source
from merchants.models import Merchant
from merchants.services import get_import_fallback_merchant
from offers.models import Market, Offer
from offers.services import import_offer_from_source


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

    def test_add_by_spu_public_id_picks_lowest_price_offer_and_merges(self):
        """列表卡片【+】只传 spu_public_id：按当前市场最低价 ACTIVE Offer 加购。"""

        from catalog.product_services import get_or_create_sku_from_source
        from offers.market_services import resolve_market_context
        from offers.services import import_offer_from_source

        request = self.factory.get("/api/v1/cart/items")
        request.COOKIES = {"joybuy-market": "GB", "joybuy-locale": "en-GB"}
        market_context = resolve_market_context(request)

        # 同 SPU 第二个（更便宜）的 ACTIVE offer。
        second_sku, _ = get_or_create_sku_from_source(
            spu=self.spu,
            source_system="joybuy",
            source_id="cart-sku-second",
            specification={},
            skip_attribute_validation=True,
        )
        cheaper, _ = import_offer_from_source(
            sku=second_sku,
            merchant=self.merchant,
            market=self.market,
            currency=self.currency,
            source_system="joybuy",
            source_id="cart-offer-cheaper",
            current_price="8.00",
        )
        Offer.objects.filter(pk=cheaper.pk).update(status=Offer.Status.ACTIVE)

        context = self.anonymous_context(token="tok-spu-add")
        add_item(
            context,
            spu_public_id=str(self.spu.public_id),
            quantity=1,
            market=market_context.market,
        )
        add_item(
            context,
            spu_public_id=str(self.spu.public_id),
            quantity=2,
            market=market_context.market,
        )
        cart = Cart.objects.get(anonymous_token="tok-spu-add")
        rows = cart.items.select_related("offer")
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.get().offer_id, cheaper.pk)
        self.assertEqual(rows.get().quantity, 3)

    def test_add_by_spu_public_id_rejects_spu_without_active_offer(self):
        from offers.market_services import resolve_market_context

        request = self.factory.get("/api/v1/cart/items")
        request.COOKIES = {"joybuy-market": "GB"}
        market_context = resolve_market_context(request)
        context = self.anonymous_context(token="tok-spu-missing")

        Offer.objects.filter(pk=self.offer.pk).update(status=Offer.Status.INACTIVE)
        with self.assertRaises(CartError) as raised:
            add_item(
                context,
                spu_public_id=str(self.spu.public_id),
                quantity=1,
                market=market_context.market,
            )
        self.assertEqual(raised.exception.code, "SKU_NOT_AVAILABLE")
        with self.assertRaises(CartError):
            add_item(context, quantity=1, market=market_context.market)

    def test_serialize_cart_localizes_title_with_request_locale(self):
        """购物车行标题跟随请求 locale，无译文回退 en-GB（不落其它语言）。"""

        from catalog.models import SpuTranslation
        from offers.market_services import resolve_market_context

        SpuTranslation.objects.update_or_create(
            spu=self.spu, locale="en-GB", defaults={"title": "English title"}
        )
        SpuTranslation.objects.update_or_create(
            spu=self.spu, locale="zh-CN", defaults={"title": "中文标题"}
        )
        SpuTranslation.objects.update_or_create(
            spu=self.spu, locale="de-DE", defaults={"title": "Deutscher Titel"}
        )

        context = self.anonymous_context(token="tok-title")
        add_item(context, offer_public_id=str(self.offer.public_id), quantity=1)
        cart = Cart.objects.get(anonymous_token="tok-title")

        def title_for(locale_code):
            request = self.factory.get("/api/v1/cart")
            request.COOKIES = {"joybuy-market": "GB", "joybuy-locale": locale_code}
            market_context = resolve_market_context(request)
            return serialize_cart(
                cart, market=market_context.market, locale=market_context.locale
            )["items"][0]["title"]

        self.assertEqual(title_for("zh-CN"), "中文标题")
        self.assertEqual(title_for("en-GB"), "English title")
        # ja-JP 没有译文：显式回退 en-GB，绝不落到已存在的 de-DE 行。
        self.assertEqual(title_for("ja-JP"), "English title")
        self.assertEqual(title_for("ko-KR"), "English title")

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

    def test_serialize_cart_attaches_merchant_payload_per_item(self):
        """需求文档03 12.3：每个 item 附 merchant 对象，多商家购物车各自带出。"""
        other_merchant = Merchant.objects.create(
            slug="cart-second-merchant",
            display_name="Second Seller",
            avatar_url="/media/merchants/original/second.png",
        )
        other_offer, _ = import_offer_from_source(
            sku=self.sku,
            merchant=other_merchant,
            market=self.market,
            currency=self.currency,
            source_system="joybuy",
            source_id="cart-offer-second",
            current_price="9.90",
        )
        Offer.objects.filter(pk=other_offer.pk).update(status=Offer.Status.ACTIVE)

        context = self.anonymous_context(token="tok-merchant")
        add_item(context, offer_public_id=str(self.offer.public_id), quantity=1)
        add_item(context, offer_public_id=str(other_offer.public_id), quantity=2)

        snapshot = serialize_cart(Cart.objects.get(anonymous_token="tok-merchant"))
        by_offer = {item["offer_public_id"]: item for item in snapshot["items"]}

        # 自营导入商家对外统一为 Joybuy 官营口径。
        own = by_offer[str(self.offer.public_id)]["merchant"]
        self.assertEqual(own["merchant_name"], "Joybuy")
        self.assertEqual(own["merchant_avatar_url"], "")
        self.assertEqual(own["merchant_id"], str(self.merchant.public_id))

        # 第三方商家透传 display_name / avatar_url。
        other = by_offer[str(other_offer.public_id)]["merchant"]
        self.assertEqual(other["merchant_name"], "Second Seller")
        self.assertEqual(other["merchant_avatar_url"], "/media/merchants/original/second.png")
        self.assertEqual(other["merchant_id"], str(other_merchant.public_id))

        # 既有字段不受增量影响。
        self.assertEqual(by_offer[str(self.offer.public_id)]["price"], "12.5000")
        self.assertEqual(snapshot["subtotal"], "32.3000")

    def test_merchant_entry_falls_back_to_joybuy_without_merchant(self):
        """None 安全：merchant 缺失时回退 Joybuy 官营口径（防御分支）。"""
        from types import SimpleNamespace

        payload = merchant_entry(SimpleNamespace(merchant=None))
        self.assertEqual(payload["merchant_id"], "")
        self.assertEqual(payload["merchant_name"], "Joybuy")
        self.assertEqual(payload["merchant_avatar_url"], "")
