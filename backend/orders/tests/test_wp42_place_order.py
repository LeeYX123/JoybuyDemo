"""WP-42：下单即支付成功 + 支付方式记录 + 按商家拆单 + 白名单校验。"""

from datetime import timedelta

from django.test import RequestFactory, TestCase
from django.utils import timezone

from accounts_buyers.models import BuyerAccount
from accounts_buyers.services import create_buyer_session
from cart.models import Cart
from cart.services import add_item, resolve_cart_context, serialize_cart
from catalog.models import Spu
from catalog.product_services import get_or_create_sku_from_source, get_or_create_spu_from_source
from checkout.models import Address
from merchant_ops.services import build_progress_schedule
from merchants.models import Merchant as MerchantForProgress
from merchants.services import get_import_fallback_merchant
from offers.models import Market, Offer
from offers.services import import_offer_from_source
from orders.models import MerchantOrder, Order
from orders.order_services import OrderError, place_order


class PlaceOrderWp42Tests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.merchant = get_import_fallback_merchant()
        self.market = Market.objects.get(code="GB")
        self.spu, _ = get_or_create_spu_from_source(
            source_system="joybuy", source_id="wp42-spu", title="WP42 product"
        )
        Spu.objects.filter(pk=self.spu.pk).update(status=Spu.Status.ACTIVE)
        self.sku, _ = get_or_create_sku_from_source(
            spu=self.spu,
            source_system="joybuy",
            source_id="wp42-sku",
            specification={},
            skip_attribute_validation=True,
        )
        self.offer, _ = import_offer_from_source(
            sku=self.sku,
            merchant=self.merchant,
            market=self.market,
            currency=self.market.default_currency,
            source_system="joybuy",
            source_id="wp42-offer",
            current_price="30.00",
        )
        Offer.objects.filter(pk=self.offer.pk).update(status=Offer.Status.ACTIVE, cost_price="21.00")

        self.account, _ = BuyerAccount.objects.get_or_create(
            email="wp42-flow@joybuy.test", defaults={"status": BuyerAccount.Status.ACTIVE}
        )
        self.address = Address.objects.create(
            account=self.account,
            full_name="Test Buyer",
            phone="+447000000000",
            line1="1 High Street",
            city="London",
            postcode="SW1A 1AA",
        )

    def _snapshot(self, quantity=1):
        context = resolve_cart_context(self.factory.get("/"))
        context.account = self.account
        add_item(context, offer_public_id=str(self.offer.public_id), quantity=quantity)
        return serialize_cart(Cart.objects.get(account=self.account, status=Cart.Status.OPEN))

    def _place(self, payment_method="CARD", quantity=1, snapshot=None):
        return place_order(
            account=self.account,
            cart_snapshot=snapshot or self._snapshot(quantity),
            address_snapshot={"public_id": str(self.address.public_id)},
            payment_method=payment_method,
        )

    def test_paid_order_records_method_and_merchant_suborder(self):
        order = self._place(payment_method="KLARNA", quantity=2)
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.payment_method, "KLARNA")
        self.assertIsNotNone(order.paid_at)

        suborder = MerchantOrder.objects.get(order=order)
        self.assertEqual(suborder.merchant_id, self.merchant.pk)
        self.assertEqual(str(suborder.items_total), "60.0000")
        # 成本快照来自 offer.cost_price（折扣折算后的上架成本）。
        self.assertEqual(str(suborder.cost_total), "42.0000")
        self.assertEqual(suborder.status, MerchantOrder.Status.PENDING)
        self.assertEqual(suborder.payment_method, "KLARNA")
        item = order.items.get()
        self.assertEqual(item.merchant_order_id, suborder.pk)
        self.assertEqual(str(item.unit_cost), "21.0000")

    def test_invalid_payment_method_rejected(self):
        with self.assertRaises(OrderError) as raised:
            self._place(payment_method="BITCOIN")
        self.assertEqual(raised.exception.code, "PAYMENT_METHOD_INVALID")
        self.assertFalse(Order.objects.exists())

    def test_no_payment_method_stays_pending(self):
        order = self._place(payment_method="")
        self.assertEqual(order.status, Order.Status.PENDING_PAYMENT)

    def test_non_whitelisted_account_cannot_place_order(self):
        # 先在白名单状态下生成购物车快照，再移出白名单，验证下单侧拦截。
        snapshot = self._snapshot()
        BuyerAccount.objects.filter(pk=self.account.pk).update(purchase_whitelisted=False)
        self.account.refresh_from_db()
        with self.assertRaises(OrderError) as raised:
            place_order(
                account=self.account,
                cart_snapshot=snapshot,
                address_snapshot={"public_id": str(self.address.public_id)},
                payment_method="CARD",
            )
        self.assertEqual(raised.exception.code, "NOT_WHITELISTED")
        self.assertFalse(Order.objects.exists())

    def test_payment_disabled_account_cannot_place_order(self):
        # 管理端编辑关闭支付权限（与白名单独立）：下单侧抛 PAYMENT_DISABLED。
        snapshot = self._snapshot()
        BuyerAccount.objects.filter(pk=self.account.pk).update(payment_enabled=False)
        self.account.refresh_from_db()
        with self.assertRaises(OrderError) as raised:
            place_order(
                account=self.account,
                cart_snapshot=snapshot,
                address_snapshot={"public_id": str(self.address.public_id)},
                payment_method="CARD",
            )
        self.assertEqual(raised.exception.code, "PAYMENT_DISABLED")
        self.assertIn("关闭支付权限", raised.exception.message)
        self.assertFalse(Order.objects.exists())

    def test_daily_stat_order_count_bumped(self):
        from merchants.models import MerchantDailyStat

        self._place(quantity=2)
        row = MerchantDailyStat.objects.get(merchant=self.merchant)
        self.assertEqual(row.order_count, 1)

    def test_unpaid_order_does_not_count_daily_stat(self):
        from merchants.models import MerchantDailyStat

        self._place(payment_method="")
        self.assertFalse(MerchantDailyStat.objects.filter(merchant=self.merchant).exists())


class CartWhitelistTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.merchant = get_import_fallback_merchant()
        self.market = Market.objects.get(code="GB")
        self.spu, _ = get_or_create_spu_from_source(
            source_system="joybuy", source_id="wp42-cart-spu", title="Cart product"
        )
        Spu.objects.filter(pk=self.spu.pk).update(status=Spu.Status.ACTIVE)
        self.sku, _ = get_or_create_sku_from_source(
            spu=self.spu,
            source_system="joybuy",
            source_id="wp42-cart-sku",
            specification={},
            skip_attribute_validation=True,
        )
        self.offer, _ = import_offer_from_source(
            sku=self.sku,
            merchant=self.merchant,
            market=self.market,
            currency=self.market.default_currency,
            source_system="joybuy",
            source_id="wp42-cart-offer",
            current_price="10.00",
        )
        Offer.objects.filter(pk=self.offer.pk).update(status=Offer.Status.ACTIVE)
        self.account, _ = BuyerAccount.objects.get_or_create(
            email="wp42-cart@joybuy.test", defaults={"status": BuyerAccount.Status.ACTIVE}
        )
        token, _session = create_buyer_session(
            account=self.account, ip_address="127.0.0.1", user_agent="test"
        )
        self.session_token = token

    def test_non_whitelisted_add_item_rejected(self):
        BuyerAccount.objects.filter(pk=self.account.pk).update(purchase_whitelisted=False)
        self.account.refresh_from_db()
        context = resolve_cart_context(self.factory.get("/"))
        context.account = self.account
        from cart.services import CartItemInvalid

        with self.assertRaises(CartItemInvalid) as raised:
            add_item(context, offer_public_id=str(self.offer.public_id), quantity=1)
        self.assertEqual(raised.exception.code, "NOT_WHITELISTED")

    def test_whitelisted_add_item_ok(self):
        self.assertTrue(self.account.purchase_whitelisted)
        context = resolve_cart_context(self.factory.get("/"))
        context.account = self.account
        add_item(context, offer_public_id=str(self.offer.public_id), quantity=1)
        self.assertEqual(context.account.carts.filter(status=Cart.Status.OPEN).count(), 1)


class ProgressAutoAdvanceTests(TestCase):
    """发货随机区间计划 + 自动推进 + 14 天自动确认收货。"""

    def setUp(self):
        self.merchant, _ = MerchantForProgress.objects.get_or_create(
            slug="progress-shop", defaults={"display_name": "Progress Shop"}
        )
        self.buyer = BuyerAccount.objects.create(
            email="progress@joybuy.test", password="x", status="ACTIVE"
        )
        self.order = Order.objects.create(
            account=self.buyer,
            currency_id=self._currency().pk,
            items_subtotal=0,
            shipping_cost=0,
            total=0,
            payment_expires_at=timezone.now() + timedelta(hours=1),
        )

    def _currency(self):
        from offers.models import Currency as CurrencyModel

        currency, _ = CurrencyModel.objects.get_or_create(
            code="CNY", defaults={"name": "Chinese Yuan", "symbol": "¥"}
        )
        return currency

    def _shipped_order(self, *, shipped_hours_ago, planned=None, progress=0):
        shipped_at = timezone.now() - timedelta(hours=shipped_hours_ago)
        suborder = MerchantOrder.objects.create(
            order=self.order,
            merchant=self.merchant,
            currency="CNY",
            status=MerchantOrder.Status.SHIPPED,
            progress=progress,
            node_times=[shipped_at.isoformat()] + [None] * 7,
            shipped_at=shipped_at,
        )
        MerchantOrder.objects.filter(pk=suborder.pk).update(
            created_at=shipped_at,
            planned_node_times=planned
            or [m.isoformat() for m in build_progress_schedule(shipped_at)],
        )
        return suborder

    def test_schedule_random_within_intervals(self):
        from datetime import datetime

        shipped_at = timezone.now()
        planned = build_progress_schedule(shipped_at)
        self.assertEqual(len(planned), 7)
        bounds = [(4, 8), (6, 12), (3, 6), (48, 120), (10, 18), (6, 16)]
        previous = shipped_at
        for index, (low, high) in enumerate(bounds):
            gap = (planned[index] - previous).total_seconds() / 3600
            self.assertGreaterEqual(gap, low - 0.001)
            self.assertLessEqual(gap, high + 0.001)
            previous = planned[index]
        # 已签收 → 14 天自动确认截止。
        self.assertEqual(
            (planned[6] - planned[5]).days, 14
        )
        self.assertIsInstance(planned[0], datetime)

    def test_auto_advance_moves_to_due_node(self):
        from merchant_ops.services import auto_advance_progress

        shipped_at = timezone.now() - timedelta(hours=10)
        # 前 5 小时到位（已出库 planned[0]），planned[1]（已揽收）在未来。
        planned = [
            (shipped_at + timedelta(hours=5)).isoformat(),
            (timezone.now() + timedelta(hours=5)).isoformat(),
        ] + ["2999-01-01T00:00:00+00:00"] * 5
        suborder = self._shipped_order(shipped_hours_ago=10, planned=planned)
        result = auto_advance_progress()
        self.assertEqual(result["advanced"], 1)
        suborder.refresh_from_db()
        self.assertEqual(suborder.progress, 1)
        self.assertEqual(
            suborder.node_times[1],
            (shipped_at + timedelta(hours=5)).isoformat(),
            "node_times 应记录计划扭转时刻",
        )

    def test_auto_confirm_after_14_days_settles(self):
        from merchant_ops.services import auto_advance_progress

        shipped_at = timezone.now() - timedelta(days=30)
        planned = [(shipped_at + timedelta(hours=i + 1)).isoformat() for i in range(6)]
        planned.append((timezone.now() - timedelta(days=1)).isoformat())
        suborder = self._shipped_order(shipped_hours_ago=720, planned=planned, progress=6)
        result = auto_advance_progress()
        self.assertEqual(result["confirmed"], 1)
        suborder.refresh_from_db()
        self.assertEqual(suborder.progress, 7)
        self.assertEqual(suborder.status, MerchantOrder.Status.COMPLETED)
        self.assertTrue(suborder.settled)

    def test_orders_without_plan_are_skipped(self):
        from merchant_ops.services import auto_advance_progress

        shipped_at = timezone.now() - timedelta(days=30)
        MerchantOrder.objects.create(
            order=self.order,
            merchant=self.merchant,
            currency="CNY",
            status=MerchantOrder.Status.SHIPPED,
            progress=0,
            shipped_at=shipped_at,
        )
        result = auto_advance_progress()
        self.assertEqual(result["advanced"], 0)
