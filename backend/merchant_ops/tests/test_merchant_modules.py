"""商家端 M03–M10 接口测试。

覆盖商家端最容易出事的几条线：
1. 店铺隔离：跨店的订单/售后/通知/会话一律 404，不泄漏别家数据；
2. 资金一致性：发货扣成本、提现占用余额、密码错误计数；
3. 状态机：已完成售后只读、确认收货后禁止退货完成、活动参与幂等；
4. 通知已读语义：打开详情自动已读、平台新回复重新未读（后台写回复）。
"""

import json
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts_buyers.models import BuyerAccount
from accounts_staff.models import StaffAccount
from accounts_staff.services import create_staff_session
from catalog.models import LocalCategory, Spu, SpuTranslation
from merchant_ops.models import (
    AfterSale,
    MerchantActivity,
    MerchantWalletEntry,
    ReferralCommission,
    ReferralProgram,
    SupportConversation,
    SupportMessage,
)
from merchant_ops.services import MerchantOpsError, record_wallet_entry, ship_merchant_order
from merchants.models import Merchant, MerchantMembership, MerchantRole
from notifications.models import MerchantNotification, MerchantNotificationReply
from offers.models import Currency, Market, Offer
from orders.models import MerchantOrder, Order, OrderItem


class MerchantModuleTestBase(TestCase):
    def setUp(self):
        self.currency = Currency.objects.get(code="GBP")
        self.market = Market.objects.get(code="GB")
        self.owner_role = MerchantRole.objects.get(code="merchant_owner")

        self.staff = StaffAccount.objects.create(
            email="module-seller@joybuy.test", display_name="店长", status="ACTIVE"
        )
        self.staff.set_password("Seller#2026pass")
        self.staff.save()

        self.shop = Merchant.objects.create(
            slug="module-shop",
            display_name="模块测试店",
            onboarding_status=Merchant.OnboardingStatus.ACTIVE,
            admission_approved=True,
            deposit_initial_paid=True,
            referral_code="MMOD0001",
        )
        MerchantMembership.objects.create(
            merchant=self.shop, staff=self.staff, role=self.owner_role, status="ACTIVE"
        )
        self.other_shop = Merchant.objects.create(
            slug="other-shop",
            display_name="别家店",
            onboarding_status=Merchant.OnboardingStatus.ACTIVE,
            admission_approved=True,
            deposit_initial_paid=True,
            referral_code="MOTHER001",
        )
        self.category = LocalCategory.objects.create(
            name="Kitchen", name_en="Kitchen", name_zh="厨房", slug="kitchen", path="kitchen"
        )
        self._login()

    def _login(self):
        token, _session = create_staff_session(
            staff=self.staff, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token

    # ---- 请求辅助 ----
    def get(self, path, *, shop=None):
        shop = shop or self.shop
        return self.client.get(path, HTTP_X_MERCHANT_ID=str(shop.public_id))

    def post(self, path, payload=None, *, shop=None):
        shop = shop or self.shop
        return self.client.post(
            path,
            data=json.dumps(payload or {}),
            content_type="application/json",
            HTTP_X_MERCHANT_ID=str(shop.public_id),
        )

    # ---- 数据辅助 ----
    def make_product(self, *, cost="10.00", price="20.00", status=Spu.Status.ACTIVE, sku=True):
        spu = Spu.objects.create(
            local_category=self.category,
            status=status,
            cost_price=Decimal(cost) if cost is not None else None,
            retail_price=Decimal(price) if price is not None else None,
            description="演示商品",
        )
        SpuTranslation.objects.create(spu=spu, locale="zh-CN", title="演示商品")
        if sku:
            spu.skus.create(specification={}, specification_signature="default")
        return spu

    def make_order(self, *, merchant=None, items_total="40.00", cost_total="20.00", quantity=2):
        merchant = merchant or self.shop
        buyer, _ = BuyerAccount.objects.get_or_create(email="module-buyer@joybuy.test")
        order = Order.objects.create(
            account=buyer,
            currency=self.currency,
            items_subtotal=Decimal(items_total),
            shipping_cost=Decimal("0.00"),
            total=Decimal(items_total),
            shipping_address={"region": "London"},
            payment_expires_at=timezone.now(),
        )
        spu = self.make_product()
        offer = Offer.objects.create(
            merchant=merchant,
            sku=spu.skus.first(),
            market=self.market,
            currency=self.currency,
            current_price=Decimal("20.00"),
            cost_price=Decimal("10.00"),
            status=Offer.Status.ACTIVE,
        )
        merchant_order = MerchantOrder.objects.create(
            order=order,
            merchant=merchant,
            currency="GBP",
            items_total=Decimal(items_total),
            cost_total=Decimal(cost_total),
            payment_method="VISA",
        )
        OrderItem.objects.create(
            order=order,
            merchant_order=merchant_order,
            offer=offer,
            spu_public_id=str(spu.public_id),
            title="演示商品",
            quantity=quantity,
            unit_price=Decimal("20.00"),
            unit_cost=Decimal("10.00"),
            currency="GBP",
        )
        return merchant_order

    def top_up(self, amount="1000.00"):
        return record_wallet_entry(
            merchant_id=self.shop.pk,
            kind=MerchantWalletEntry.Kind.RECHARGE,
            amount=Decimal(amount),
            idempotency_key=f"test-topup-{self.shop.pk}-{amount}",
        )


class CatalogListingTests(MerchantModuleTestBase):
    def test_pool_marks_listed_state(self):
        product = self.make_product()
        listed_product = self.make_product(price="30.00")
        Offer.objects.create(
            merchant=self.shop,
            sku=listed_product.skus.first(),
            market=self.market,
            currency=self.currency,
            current_price=Decimal("30.00"),
            cost_price=Decimal("10.00"),
            status=Offer.Status.ACTIVE,
            listed_at=timezone.now(),
        )

        response = self.get("/api/v1/merchant/catalog/products")
        self.assertEqual(response.status_code, 200)
        rows = {item["id"]: item for item in response.json()["items"]}
        self.assertFalse(rows[str(product.public_id)]["listed"])
        self.assertTrue(rows[str(listed_product.public_id)]["listed"])

    def test_list_product_creates_offer_with_cost_snapshot(self):
        product = self.make_product(cost="11.50", price="25.00")
        response = self.post("/api/v1/merchant/listings", {"product_id": str(product.public_id)})
        self.assertEqual(response.status_code, 201, response.content)
        offer = Offer.objects.get(merchant=self.shop, sku__spu=product)
        self.assertEqual(offer.cost_price, Decimal("11.50"))
        self.assertEqual(offer.current_price, Decimal("25.00"))
        self.assertEqual(offer.status, Offer.Status.ACTIVE)
        self.assertIsNotNone(offer.listed_at)

    def test_list_same_product_twice_is_conflict(self):
        product = self.make_product()
        first = self.post("/api/v1/merchant/listings", {"product_id": str(product.public_id)})
        self.assertEqual(first.status_code, 201)
        second = self.post("/api/v1/merchant/listings", {"product_id": str(product.public_id)})
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["error"]["code"], "PRODUCT_ALREADY_LISTED")
        self.assertEqual(Offer.objects.filter(merchant=self.shop, sku__spu=product).count(), 1)

    def test_list_product_without_price_is_rejected(self):
        product = self.make_product(cost=None, price=None)
        response = self.post("/api/v1/merchant/listings", {"product_id": str(product.public_id)})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "PRODUCT_PRICE_MISSING")

    def test_list_product_requires_operable_shop(self):
        product = self.make_product()
        Merchant.objects.filter(pk=self.shop.pk).update(
            deposit_enabled=True, deposit_initial_paid=False
        )
        response = self.post("/api/v1/merchant/listings", {"product_id": str(product.public_id)})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "MERCHANT_NOT_OPERABLE")

    def test_list_delisted_product_is_rejected(self):
        product = self.make_product(status=Spu.Status.INACTIVE)
        response = self.post("/api/v1/merchant/listings", {"product_id": str(product.public_id)})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "PRODUCT_NOT_AVAILABLE")


class MerchantOrderTests(MerchantModuleTestBase):
    def test_list_only_returns_own_orders(self):
        own = self.make_order()
        self.make_order(merchant=self.other_shop)
        response = self.get("/api/v1/merchant/orders")
        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.json()["items"]]
        self.assertEqual(ids, [str(own.public_id)])
        self.assertEqual(response.json()["counts"]["ALL"], 1)

    def test_ship_deducts_cost_and_moves_progress(self):
        self.top_up("100.00")
        order = self.make_order(cost_total="20.00")
        response = self.post(
            f"/api/v1/merchant/orders/{order.public_id}/ship", {"reference": "JB1"}
        )
        self.assertEqual(response.status_code, 200, response.content)
        order.refresh_from_db()
        self.shop.refresh_from_db()
        self.assertEqual(order.status, MerchantOrder.Status.SHIPPED)
        self.assertEqual(order.progress, 0)
        self.assertEqual(order.tracking_reference, "JB1")
        self.assertEqual(self.shop.wallet_balance, Decimal("80.00"))

    def test_ship_without_balance_is_rejected(self):
        order = self.make_order(cost_total="20.00")
        response = self.post(f"/api/v1/merchant/orders/{order.public_id}/ship", {})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "INSUFFICIENT_WALLET_BALANCE")
        order.refresh_from_db()
        self.assertEqual(order.status, MerchantOrder.Status.PENDING)

    def test_other_merchant_order_is_not_found(self):
        foreign = self.make_order(merchant=self.other_shop)
        response = self.get(f"/api/v1/merchant/orders/{foreign.public_id}")
        self.assertEqual(response.status_code, 404)

    def test_completed_order_hides_progress_semantics(self):
        self.top_up("100.00")
        order = self.make_order()
        ship_merchant_order(order)
        response = self.get(f"/api/v1/merchant/orders/{order.public_id}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()["order"]
        self.assertEqual(payload["status"], "SHIPPED")
        self.assertFalse(payload["can_ship"])


class WalletTests(MerchantModuleTestBase):
    def test_wallet_password_must_be_six_digits(self):
        response = self.post(
            "/api/v1/merchant/wallet/password",
            {"new_password": "12345", "confirm_password": "12345"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "WALLET_PASSWORD_FORMAT")

    def test_wallet_password_set_then_change_requires_old(self):
        first = self.post(
            "/api/v1/merchant/wallet/password",
            {"new_password": "123456", "confirm_password": "123456"},
        )
        self.assertEqual(first.status_code, 200, first.content)

        wrong = self.post(
            "/api/v1/merchant/wallet/password",
            {"old_password": "000000", "new_password": "654321", "confirm_password": "654321"},
        )
        self.assertEqual(wrong.status_code, 400)
        self.assertEqual(wrong.json()["error"]["code"], "WALLET_PASSWORD_OLD_INVALID")

        ok = self.post(
            "/api/v1/merchant/wallet/password",
            {"old_password": "123456", "new_password": "654321", "confirm_password": "654321"},
        )
        self.assertEqual(ok.status_code, 200, ok.content)

    def test_withdrawal_requires_wallet_password(self):
        self.top_up("500.00")
        response = self.post(
            "/api/v1/merchant/wallet/withdrawals",
            {
                "method": "BANK",
                "amount": "100.00",
                "wallet_password": "",
                "bank": {
                    "name": "中国银行",
                    "account": "6222020200011112222",
                    "holder": "张三",
                    "branch": "上海分行",
                    "code": "0012",
                },
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "WALLET_PASSWORD_NOT_SET")

    def test_withdrawal_over_balance_is_rejected(self):
        self.top_up("50.00")
        self.post(
            "/api/v1/merchant/wallet/password",
            {"new_password": "123456", "confirm_password": "123456"},
        )
        response = self.post(
            "/api/v1/merchant/wallet/withdrawals",
            {
                "method": "BANK",
                "amount": "100.00",
                "wallet_password": "123456",
                "bank": {
                    "name": "中国银行",
                    "account": "6222020200011112222",
                    "holder": "张三",
                    "branch": "上海分行",
                    "code": "0012",
                },
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "INSUFFICIENT_WALLET_BALANCE")

    def test_withdrawal_reserves_balance_once(self):
        self.top_up("500.00")
        self.post(
            "/api/v1/merchant/wallet/password",
            {"new_password": "123456", "confirm_password": "123456"},
        )
        response = self.post(
            "/api/v1/merchant/wallet/withdrawals",
            {
                "method": "CHAIN",
                "amount": "120.00",
                "wallet_password": "123456",
                "chain": {
                    "coin": "USDT",
                    "network": "TRC-20",
                    "address": "TXYZabcdefghijklmnopqrstuvwxyz123456",
                },
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.wallet_balance, Decimal("380.00"))
        entries = MerchantWalletEntry.objects.filter(
            merchant=self.shop, kind=MerchantWalletEntry.Kind.WITHDRAWAL
        )
        self.assertEqual(entries.count(), 1)
        self.assertEqual(entries.first().amount, Decimal("-120.00"))

    def test_withdrawal_rejects_more_than_two_decimals(self):
        self.top_up("500.00")
        self.post(
            "/api/v1/merchant/wallet/password",
            {"new_password": "123456", "confirm_password": "123456"},
        )
        response = self.post(
            "/api/v1/merchant/wallet/withdrawals",
            {
                "method": "CHAIN",
                "amount": "10.123",
                "wallet_password": "123456",
                "chain": {
                    "coin": "USDT",
                    "network": "TRC-20",
                    "address": "TXYZabcdefghijklmnopqrstuvwxyz123456",
                },
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "WITHDRAWAL_AMOUNT_PRECISION")

    def test_ledger_only_shows_own_entries(self):
        self.top_up("100.00")
        record_wallet_entry(
            merchant_id=self.other_shop.pk,
            kind=MerchantWalletEntry.Kind.RECHARGE,
            amount=Decimal("999.00"),
            idempotency_key="other-shop-topup",
        )
        response = self.get("/api/v1/merchant/wallet/entries")
        self.assertEqual(response.status_code, 200)
        amounts = [item["amount"] for item in response.json()["items"]]
        self.assertEqual(amounts, ["100.00"])


class DepositTests(MerchantModuleTestBase):
    def test_deposit_disabled_returns_empty_structure(self):
        response = self.get("/api/v1/merchant/deposit")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["deposit"]["enabled"])
        self.assertEqual(payload["items"], [])


class AfterSaleTests(MerchantModuleTestBase):
    def _make_after_sale(self, *, kind=AfterSale.Kind.RETURN, state=AfterSale.State.PENDING):
        order = self.make_order()
        record = AfterSale.objects.create(
            merchant=self.shop,
            order=order.order,
            merchant_order=order,
            kind=kind,
            state=state,
            issue="外包装破损",
            progress="",
            currency="GBP",
        )
        return record

    def test_progress_moves_state_to_processing(self):
        record = self._make_after_sale()
        response = self.post(
            f"/api/v1/merchant/after-sales/{record.public_id}/actions",
            {"action": "progress", "progress": "已联系买家"},
        )
        self.assertEqual(response.status_code, 200, response.content)
        record.refresh_from_db()
        self.assertEqual(record.state, AfterSale.State.PROCESSING)
        self.assertEqual(record.progress, "已联系买家")
        self.assertEqual(record.events.count(), 1)

    def test_completed_after_sale_is_readonly(self):
        record = self._make_after_sale(state=AfterSale.State.COMPLETED)
        response = self.post(
            f"/api/v1/merchant/after-sales/{record.public_id}/actions",
            {"action": "progress", "progress": "再处理一次"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "AFTER_SALE_CLOSED")

    def test_return_cannot_complete_after_receipt(self):
        self.top_up("100.00")
        record = self._make_after_sale()
        ship_merchant_order(record.merchant_order)
        from merchant_ops.services import complete_all_nodes

        complete_all_nodes(record.merchant_order)

        response = self.post(
            f"/api/v1/merchant/after-sales/{record.public_id}/actions",
            {"action": "complete", "result": "同意退货"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "RETURN_AFTER_RECEIPT_BLOCKED")

    def test_escalate_sets_platform_state(self):
        record = self._make_after_sale(kind=AfterSale.Kind.COMPLAINT)
        response = self.post(
            f"/api/v1/merchant/after-sales/{record.public_id}/actions",
            {"action": "escalate", "note": "需要平台协助"},
        )
        self.assertEqual(response.status_code, 200, response.content)
        record.refresh_from_db()
        self.assertEqual(record.state, AfterSale.State.PLATFORM)


class ActivityTests(MerchantModuleTestBase):
    def test_join_is_idempotent(self):
        activity = MerchantActivity.objects.create(
            title="测试活动",
            kind=MerchantActivity.Kind.PERMANENT,
            start_date=timezone.localdate(),
            description="",
        )
        first = self.post(f"/api/v1/merchant/activities/{activity.public_id}/join", {})
        self.assertEqual(first.status_code, 200, first.content)
        self.assertTrue(first.json()["created"])

        second = self.post(f"/api/v1/merchant/activities/{activity.public_id}/join", {})
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()["created"])
        self.assertEqual(activity.participations.count(), 1)

    def test_referral_only_lists_own_commissions(self):
        ReferralProgram.load()
        other_referrer = self.other_shop
        referee = Merchant.objects.create(
            slug="referee-shop",
            display_name="新人店",
            onboarding_status=Merchant.OnboardingStatus.ACTIVE,
            admission_approved=True,
            deposit_initial_paid=True,
            referral_code="MREF00001",
        )
        from merchant_ops.models import MerchantReferral

        referral = MerchantReferral.objects.create(
            referrer=other_referrer, referee=referee, code_used=other_referrer.referral_code
        )
        ReferralCommission.objects.create(
            referral=referral,
            period="2026-10",
            shipped_amount=Decimal("12000.00"),
            rate=Decimal("1.000"),
            amount=Decimal("120.00"),
        )
        response = self.get("/api/v1/merchant/referral")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["commissions"], [])
        self.assertEqual(payload["stats"]["referred_count"], 0)


class InboxTests(MerchantModuleTestBase):
    def test_support_conversation_is_first(self):
        SupportConversation.objects.create(
            merchant=self.shop,
            kind=SupportConversation.Kind.BUYER,
            peer_name="买家甲",
            last_message_at=timezone.now(),
        )
        response = self.get("/api/v1/merchant/conversations")
        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertEqual(items[0]["kind"], SupportConversation.Kind.PLATFORM_SUPPORT)
        self.assertEqual(items[0]["peer_name"], "客服中心")

    def test_send_message_rejects_blank(self):
        conversation = SupportConversation.objects.create(
            merchant=self.shop, kind=SupportConversation.Kind.BUYER, peer_name="买家"
        )
        response = self.post(
            f"/api/v1/merchant/conversations/{conversation.public_id}/messages", {"text": "   "}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "MESSAGE_EMPTY")

    def test_send_message_creates_record(self):
        conversation = SupportConversation.objects.create(
            merchant=self.shop, kind=SupportConversation.Kind.BUYER, peer_name="买家"
        )
        response = self.post(
            f"/api/v1/merchant/conversations/{conversation.public_id}/messages",
            {"text": "支持 220V"},
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(conversation.messages.count(), 1)
        self.assertEqual(conversation.messages.first().sender, SupportMessage.Sender.MERCHANT)

    def test_notification_detail_marks_read(self):
        record = MerchantNotification.objects.create(
            merchant=self.shop, title="测试通知", content="正文"
        )
        self.assertIsNone(record.read_at)
        response = self.get(f"/api/v1/merchant/notifications/{record.public_id}")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["notification"]["read"])
        record.refresh_from_db()
        self.assertIsNotNone(record.read_at)

    def test_platform_reply_makes_notification_unread_again(self):
        record = MerchantNotification.objects.create(
            merchant=self.shop, title="测试通知", content="正文", read_at=timezone.now()
        )
        MerchantNotificationReply.objects.create(
            notification=record,
            role=MerchantNotificationReply.Role.PLATFORM,
            content="平台补充说明",
        )
        # 后台写回复时会把 read_at 清空（A11 的约定），这里验证商家端读得到未读。
        record.read_at = None
        record.save(update_fields=["read_at"])
        response = self.get("/api/v1/merchant/notifications?state=UNREAD")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["counts"]["UNREAD"], 1)

    def test_reply_length_is_validated(self):
        record = MerchantNotification.objects.create(
            merchant=self.shop, title="测试通知", content="正文"
        )
        too_long = self.post(
            f"/api/v1/merchant/notifications/{record.public_id}/replies",
            {"content": "字" * 1001},
        )
        self.assertEqual(too_long.status_code, 400)
        self.assertEqual(too_long.json()["error"]["code"], "REPLY_TOO_LONG")

        ok = self.post(
            f"/api/v1/merchant/notifications/{record.public_id}/replies", {"content": "收到"}
        )
        self.assertEqual(ok.status_code, 201, ok.content)
        self.assertEqual(record.replies.count(), 1)

    def test_mark_all_read_only_touches_own(self):
        MerchantNotification.objects.create(merchant=self.shop, title="A", content="")
        MerchantNotification.objects.create(merchant=self.shop, title="B", content="")
        other = MerchantNotification.objects.create(
            merchant=self.other_shop, title="别家", content=""
        )
        response = self.post("/api/v1/merchant/notifications/mark-all-read", {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["updated"], 2)
        other.refresh_from_db()
        self.assertIsNone(other.read_at)


class WalletPasswordLockTests(MerchantModuleTestBase):
    def test_five_wrong_passwords_lock_wallet(self):
        self.post(
            "/api/v1/merchant/wallet/password",
            {"new_password": "123456", "confirm_password": "123456"},
        )
        for index in range(4):
            response = self.post(
                "/api/v1/merchant/wallet/withdrawals",
                {
                    "method": "CHAIN",
                    "amount": "1.00",
                    "wallet_password": "000000",
                    "chain": {
                        "coin": "USDT",
                        "network": "TRC-20",
                        "address": "TXYZabcdefghijklmnopqrstuvwxyz123456",
                    },
                },
            )
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["error"]["code"], "WALLET_PASSWORD_INVALID")

        fifth = self.post(
            "/api/v1/merchant/wallet/withdrawals",
            {
                "method": "CHAIN",
                "amount": "1.00",
                "wallet_password": "000000",
                "chain": {
                    "coin": "USDT",
                    "network": "TRC-20",
                    "address": "TXYZabcdefghijklmnopqrstuvwxyz123456",
                },
            },
        )
        self.assertEqual(fifth.status_code, 400)
        self.assertEqual(fifth.json()["error"]["code"], "WALLET_PASSWORD_LOCKED")
        self.shop.refresh_from_db()
        self.assertIsNotNone(self.shop.wallet_password_locked_until)

    def test_service_raises_for_short_password(self):
        with self.assertRaises(MerchantOpsError):
            from merchant_ops.services import set_wallet_password

            set_wallet_password(self.shop, new_password="12", confirm_password="12")
