"""商家经营域（平台管理后台 A02–A09）的接口级测试。

重点覆盖三条不能被破坏的红线：
1. 余额与流水同事务、余额不能为负；
2. 回款/返佣/提现退回都只发生一次（幂等）；
3. 权限码缺失时接口一律 403，不靠前端隐藏菜单。
"""

import json
import uuid
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts_buyers.models import BuyerAccount
from accounts_staff.models import (
    PlatformPermission,
    PlatformRole,
    StaffAccount,
    StaffRoleAssignment,
)
from accounts_staff.services import create_staff_session
from catalog.models import LocalCategory, Spu, SpuTranslation
from merchant_ops.models import (
    AfterSale,
    MerchantActivity,
    MerchantDepositEntry,
    MerchantReferral,
    MerchantWalletEntry,
    MerchantWithdrawal,
    ReferralCommission,
    ReferralProgram,
)
from merchant_ops.services import MerchantOpsError, record_wallet_entry, ship_merchant_order
from merchants.models import Merchant
from offers.models import Currency, Market, Offer
from orders.models import MerchantOrder, Order, OrderItem

ALL_PERMISSIONS = (
    "merchants.manage",
    "catalog.pool.manage",
    "catalog.listings.manage",
    "orders.manage",
    "finance.manage",
    "deposits.manage",
    "aftersales.manage",
    "activities.manage",
)


class CommerceTestBase(TestCase):
    def setUp(self):
        self.currency = Currency.objects.get(code="GBP")
        self.market = Market.objects.get(code="GB")
        self.staff = self._make_staff(ALL_PERMISSIONS, email="commerce@joybuy.test")
        token, _session = create_staff_session(
            staff=self.staff, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token

        self.merchant = Merchant.objects.create(
            slug="demo-store",
            display_name="演示店铺",
            onboarding_status=Merchant.OnboardingStatus.ACTIVE,
            admission_approved=True,
            deposit_initial_paid=True,
            referral_code="MTEST0001",
        )
        self.category = LocalCategory.objects.create(
            name="Kitchen", name_en="Kitchen", name_zh="厨房", slug="kitchen", path="kitchen"
        )

    def _make_staff(self, codes, email):
        role, _ = PlatformRole.objects.update_or_create(
            code=f"role-{email.split('@')[0]}",
            defaults={"name": "Test role", "is_system": False},
        )
        permissions = []
        for code in codes:
            permission, _ = PlatformPermission.objects.get_or_create(
                code=code, defaults={"name": code}
            )
            permissions.append(permission)
        role.permissions.set(permissions)
        staff, _ = StaffAccount.objects.get_or_create(
            email=email,
            defaults={
                "display_name": "测试管理员",
                "password": "x",
                "status": StaffAccount.Status.ACTIVE,
            },
        )
        staff.set_password("Passw0rd!demo")
        staff.save()
        StaffRoleAssignment.objects.get_or_create(staff=staff, role=role)
        return staff

    def make_staff_without_permissions(self):
        staff = self._make_staff((), email="nobody@joybuy.test")
        token, _session = create_staff_session(
            staff=staff, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token
        return staff

    def post_json(self, url, payload=None):
        return self.client.post(
            url, data=json.dumps(payload or {}), content_type="application/json"
        )

    def patch_json(self, url, payload=None):
        return self.client.patch(
            url, data=json.dumps(payload or {}), content_type="application/json"
        )

    def make_product(self, *, cost="10.00", price="20.00"):
        spu = Spu.objects.create(
            local_category=self.category,
            status=Spu.Status.ACTIVE,
            cost_price=Decimal(cost),
            retail_price=Decimal(price),
            description="演示商品",
            image_urls=["/media/demo.webp"],
            specs=[{"name": "颜色", "value": "黑色"}],
        )
        SpuTranslation.objects.create(spu=spu, locale="zh-CN", title="演示商品")
        return spu

    def make_offer(self, spu, *, cost="10.00", price="20.00", status=Offer.Status.ACTIVE):
        sku = spu.skus.create(specification={}, specification_signature="default")
        return Offer.objects.create(
            merchant=self.merchant,
            sku=sku,
            market=self.market,
            currency=self.currency,
            current_price=Decimal(price),
            cost_price=Decimal(cost),
            local_inventory=100,
            status=status,
            listed_at=timezone.now(),
        )

    def make_merchant_order(self, *, quantity=2, unit_price="20.00", unit_cost="10.00"):
        spu = self.make_product()
        offer = self.make_offer(spu, cost=unit_cost, price=unit_price)
        buyer = BuyerAccount.objects.create(email="buyer@joybuy.test", password="x")
        order = Order.objects.create(
            account=buyer,
            currency=self.currency,
            items_subtotal=Decimal(unit_price) * quantity,
            shipping_cost=Decimal("0"),
            total=Decimal(unit_price) * quantity,
            shipping_address={"region": "London"},
            payment_expires_at=timezone.now() + timedelta(hours=1),
        )
        merchant_order = MerchantOrder.objects.create(
            order=order,
            merchant=self.merchant,
            currency=self.currency.code,
            items_total=Decimal(unit_price) * quantity,
            cost_total=Decimal(unit_cost) * quantity,
        )
        OrderItem.objects.create(
            order=order,
            merchant_order=merchant_order,
            offer=offer,
            spu_public_id=str(spu.public_id),
            title="演示商品",
            quantity=quantity,
            unit_price=Decimal(unit_price),
            unit_cost=Decimal(unit_cost),
            currency=self.currency.code,
        )
        return merchant_order


class MerchantAdminApiTests(CommerceTestBase):
    def test_list_merchants_includes_pending_order_aggregate(self):
        self.make_merchant_order()
        response = self.client.get("/api/v1/admin/merchants")
        self.assertEqual(response.status_code, 200)
        row = next(
            item for item in response.json()["items"] if item["id"] == str(self.merchant.public_id)
        )
        self.assertEqual(row["pending_order_count"], 1)
        self.assertEqual(row["pending_order_amount"], "40.00")

    def test_review_with_deposit_moves_to_pending_deposit_then_active(self):
        merchant = Merchant.objects.create(slug="new-store", display_name="新店铺")
        url = f"/api/v1/admin/merchants/{merchant.public_id}/actions"

        response = self.post_json(
            url,
            {
                "action": "review",
                "approved": True,
                "require_deposit": True,
                "deposit_required": "500.00",
                "ban_after_days": 3,
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["merchant"]["status"], "PENDING_DEPOSIT")

        # 缴纳保证金达到应缴额后自动开店
        response = self.post_json(
            f"/api/v1/admin/deposits/{merchant.public_id}/actions",
            {"action": "recharge", "amount": "500.00"},
        )
        self.assertEqual(response.status_code, 200, response.content)
        merchant.refresh_from_db()
        self.assertEqual(merchant.onboarding_status, Merchant.OnboardingStatus.ACTIVE)
        self.assertTrue(merchant.deposit_initial_paid)

    def test_review_is_locked_after_first_decision(self):
        merchant = Merchant.objects.create(slug="locked-store", display_name="锁定店铺")
        url = f"/api/v1/admin/merchants/{merchant.public_id}/actions"
        self.post_json(url, {"action": "review", "approved": True, "ban_after_days": 4})
        response = self.post_json(url, {"action": "review", "approved": True, "ban_after_days": 9})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "ADMISSION_LOCKED")

    def test_wallet_adjustment_rejects_negative_target(self):
        response = self.patch_json(
            f"/api/v1/admin/merchants/{self.merchant.public_id}",
            {"wallet_balance": "-1.00"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "BALANCE_NEGATIVE")

    def test_credit_deduction_cannot_exceed_current_score(self):
        url = f"/api/v1/admin/merchants/{self.merchant.public_id}/actions"
        response = self.post_json(url, {"action": "deduct_credit", "points": "101"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "CREDIT_EXCEEDS_CURRENT")

    def test_suspend_and_unsuspend_reset_fulfillment_clock(self):
        order = self.make_merchant_order()
        url = f"/api/v1/admin/merchants/{self.merchant.public_id}/actions"
        self.assertEqual(self.post_json(url, {"action": "suspend"}).status_code, 200)
        self.assertEqual(
            self.post_json(url, {"action": "unsuspend"}).status_code,
            200,
        )
        order.refresh_from_db()
        self.assertIsNotNone(order.fulfillment_reset_at)

    def test_missing_permission_returns_403(self):
        self.make_staff_without_permissions()
        response = self.client.get("/api/v1/admin/merchants")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "STAFF_PERMISSION_DENIED")


class ProductPoolApiTests(CommerceTestBase):
    def test_create_and_list_product(self):
        response = self.post_json(
            "/api/v1/admin/products",
            {
                "name": "测试炒锅",
                "category": str(self.category.public_id),
                "cost": "30.00",
                "price": "59.00",
                "description": "不粘锅",
                "images": ["/media/a.webp"],
                "specs": [{"name": "容量", "value": "28cm"}],
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        product = response.json()["product"]
        self.assertEqual(product["name"], "测试炒锅")

        listing = self.client.get("/api/v1/admin/products")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["total"], 1)

    def test_price_below_cost_is_rejected(self):
        response = self.post_json(
            "/api/v1/admin/products",
            {"name": "亏本商品", "cost": "50.00", "price": "20.00"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "PRICE_BELOW_COST")

    def test_listing_remove_is_idempotent(self):
        spu = self.make_product()
        offer = self.make_offer(spu)
        url = f"/api/v1/admin/merchant-listings/{offer.public_id}/actions"
        first = self.post_json(url, {"action": "remove"})
        self.assertEqual(first.status_code, 200)
        second = self.post_json(url, {"action": "remove"})
        self.assertEqual(second.status_code, 200)
        offer.refresh_from_db()
        self.assertEqual(offer.status, Offer.Status.INACTIVE)
        self.assertTrue(offer.removed_by_platform)


class MerchantOrderApiTests(CommerceTestBase):
    def test_ship_deducts_cost_and_complete_settles_once(self):
        record_wallet_entry(
            merchant_id=self.merchant.pk,
            kind=MerchantWalletEntry.Kind.RECHARGE,
            amount=Decimal("100.00"),
            idempotency_key="seed-wallet",
        )
        order = self.make_merchant_order(quantity=2, unit_price="20.00", unit_cost="10.00")

        # 发货是商家端动作（确认发货即扣成本、进度到「待出库」）
        ship_merchant_order(order, actor=self.staff)
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.wallet_balance, Decimal("80.00"))

        url = f"/api/v1/admin/merchant-orders/{order.public_id}/actions"
        self.assertEqual(self.post_json(url, {"action": "complete_all"}).status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, MerchantOrder.Status.COMPLETED)
        self.assertTrue(order.settled)
        self.merchant.refresh_from_db()
        # 100 - 20 成本 + 40 回款
        self.assertEqual(self.merchant.wallet_balance, Decimal("120.00"))

        # 重复完成后不再入账
        self.post_json(url, {"action": "complete_all"})
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.wallet_balance, Decimal("120.00"))
        self.assertEqual(
            MerchantWalletEntry.objects.filter(
                merchant=self.merchant, kind=MerchantWalletEntry.Kind.ORDER_SETTLEMENT
            ).count(),
            1,
        )

    def test_ship_without_enough_balance_is_rejected(self):
        order = self.make_merchant_order()
        with self.assertRaises(MerchantOpsError) as ctx:
            ship_merchant_order(order, actor=self.staff)
        self.assertEqual(ctx.exception.code, "INSUFFICIENT_WALLET_BALANCE")
        order.refresh_from_db()
        self.assertEqual(order.status, MerchantOrder.Status.PENDING)
        self.assertEqual(order.progress, -1)

    def test_progress_cannot_move_backwards(self):
        record_wallet_entry(
            merchant_id=self.merchant.pk,
            kind=MerchantWalletEntry.Kind.RECHARGE,
            amount=Decimal("100.00"),
            idempotency_key="seed-wallet-2",
        )
        order = self.make_merchant_order()
        ship_merchant_order(order, actor=self.staff)
        url = f"/api/v1/admin/merchant-orders/{order.public_id}/actions"
        self.post_json(url, {"action": "advance", "node_index": 3})
        response = self.post_json(url, {"action": "advance", "node_index": 2})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "NODE_NOT_FORWARD")

    def test_created_at_cannot_be_later_than_first_node(self):
        order = self.make_merchant_order()
        url = f"/api/v1/admin/merchant-orders/{order.public_id}"
        future_node = (timezone.now() + timedelta(hours=2)).isoformat()
        response = self.patch_json(url, {"node_times": [future_node]})
        self.assertEqual(response.status_code, 200, response.content)
        response = self.patch_json(
            url, {"created_at": (timezone.now() + timedelta(hours=3)).isoformat()}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "CREATED_AFTER_NODE")

    def test_node_times_must_be_ordered(self):
        order = self.make_merchant_order()
        url = f"/api/v1/admin/merchant-orders/{order.public_id}"
        first = (timezone.now() + timedelta(hours=1)).isoformat()
        second = (timezone.now() + timedelta(hours=2)).isoformat()
        response = self.patch_json(url, {"node_times": [second, first]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "NODE_OUT_OF_ORDER")


class FinanceApiTests(CommerceTestBase):
    def _make_withdrawal(self, amount="50.00"):
        record_wallet_entry(
            merchant_id=self.merchant.pk,
            kind=MerchantWalletEntry.Kind.RECHARGE,
            amount=Decimal("100.00"),
            idempotency_key="seed-withdrawal-wallet",
        )
        from merchant_ops.services import reserve_withdrawal

        withdrawal = MerchantWithdrawal.objects.create(
            merchant=self.merchant,
            method=MerchantWithdrawal.Method.BANK,
            amount=Decimal(amount),
            bank_name="招商银行",
            bank_account="6225880212345678",
            bank_holder="张三",
            bank_branch="上海分行",
            bank_code="0012",
        )
        reserve_withdrawal(self.merchant, withdrawal=withdrawal, actor=self.staff)
        self.merchant.refresh_from_db()
        return withdrawal

    def test_reject_returns_balance_only_once(self):
        withdrawal = self._make_withdrawal()
        self.assertEqual(self.merchant.wallet_balance, Decimal("50.00"))
        url = f"/api/v1/admin/finance/withdrawals/{withdrawal.public_id}/actions"
        self.assertEqual(
            self.post_json(url, {"action": "reject", "reason": "资料不符"}).status_code, 200
        )
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.wallet_balance, Decimal("100.00"))

        # 已打回状态再打回被状态机拦住
        response = self.post_json(url, {"action": "reject"})
        self.assertEqual(response.status_code, 409)
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.wallet_balance, Decimal("100.00"))

    def test_approve_transfer_and_pay(self):
        withdrawal = self._make_withdrawal()
        url = f"/api/v1/admin/finance/withdrawals/{withdrawal.public_id}/actions"
        response = self.post_json(url, {"action": "approve", "fee": "2.00"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["withdrawal"]["net_amount"], "48.00")

        response = self.post_json(url, {"action": "start_transfer", "reference": "TX-001"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["withdrawal"]["state"], "TRANSFERRING")

        response = self.post_json(url, {"action": "mark_paid"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["withdrawal"]["state"], "PAID")
        self.merchant.refresh_from_db()
        # 出款不再扣一次可用余额
        self.assertEqual(self.merchant.wallet_balance, Decimal("50.00"))

    def test_start_transfer_requires_reference(self):
        withdrawal = self._make_withdrawal()
        url = f"/api/v1/admin/finance/withdrawals/{withdrawal.public_id}/actions"
        self.post_json(url, {"action": "approve", "fee": "0"})
        response = self.post_json(url, {"action": "start_transfer"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "FIELD_REQUIRED")

    def test_recharge_creates_ledger_entry(self):
        response = self.post_json(
            "/api/v1/admin/finance/recharges",
            {"merchant_id": str(self.merchant.public_id), "amount": "88.80"},
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.wallet_balance, Decimal("88.80"))
        self.assertEqual(
            MerchantWalletEntry.objects.filter(
                merchant=self.merchant, kind=MerchantWalletEntry.Kind.RECHARGE
            ).count(),
            1,
        )


class DepositApiTests(CommerceTestBase):
    def test_deposit_adjust_allows_zero_and_records_delta(self):
        self.merchant.deposit_enabled = True
        self.merchant.deposit_required = Decimal("500.00")
        self.merchant.deposit_balance = Decimal("300.00")
        self.merchant.deposit_initial_paid = False
        self.merchant.save(
            update_fields=[
                "deposit_enabled",
                "deposit_required",
                "deposit_balance",
                "deposit_initial_paid",
            ]
        )
        response = self.post_json(
            f"/api/v1/admin/deposits/{self.merchant.public_id}/actions",
            {"action": "adjust", "balance": "0"},
        )
        self.assertEqual(response.status_code, 200, response.content)
        entry = MerchantDepositEntry.objects.get(merchant=self.merchant)
        self.assertEqual(entry.amount, Decimal("-300.00"))
        self.assertEqual(entry.balance_after, Decimal("0"))

    def test_deposit_recharge_rejected_when_not_enabled(self):
        response = self.post_json(
            f"/api/v1/admin/deposits/{self.merchant.public_id}/actions",
            {"action": "recharge", "amount": "100"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "DEPOSIT_NOT_ENABLED")


class AfterSaleApiTests(CommerceTestBase):
    def test_platform_decision_closes_after_sale(self):
        order = self.make_merchant_order()
        record = AfterSale.objects.create(
            merchant=self.merchant,
            order=order.order,
            merchant_order=order,
            kind=AfterSale.Kind.COMPLAINT,
            issue="包装破损",
        )
        url = f"/api/v1/admin/after-sales/{record.public_id}/actions"
        response = self.post_json(url, {"action": "decide", "decision": "COMPLETE"})
        self.assertEqual(response.status_code, 200, response.content)
        record.refresh_from_db()
        self.assertEqual(record.state, AfterSale.State.COMPLETED)
        self.assertEqual(record.events.count(), 1)

        # 已结束的售后不能重复处理
        response = self.post_json(url, {"action": "decide", "decision": "COMPLETE"})
        self.assertEqual(response.status_code, 409)

    def test_return_completion_blocked_after_order_completed(self):
        order = self.make_merchant_order()
        order.order.status = "COMPLETED"
        order.order.save(update_fields=["status"])
        record = AfterSale.objects.create(
            merchant=self.merchant,
            order=order.order,
            merchant_order=order,
            kind=AfterSale.Kind.RETURN,
            issue="尺码不合适",
        )
        response = self.post_json(
            f"/api/v1/admin/after-sales/{record.public_id}/actions",
            {"action": "decide", "decision": "COMPLETE"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "RETURN_AFTER_RECEIVED")


class ReferralApiTests(CommerceTestBase):
    def test_program_rejects_non_zero_first_tier(self):
        response = self.client.put(
            "/api/v1/admin/referrals/program",
            data=json.dumps({"tiers": [{"min": "100", "rate": "1"}], "valid_months": 12}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "TIER_FIRST_NOT_ZERO")

    def test_commission_calculated_and_paid_once(self):
        program = ReferralProgram.load()
        program.tiers = [
            {"min": "0", "rate": "1"},
            {"min": "10000", "rate": "2"},
            {"min": "50000", "rate": "3"},
        ]
        program.valid_months = 12
        program.save()

        referee = Merchant.objects.create(
            slug="new-referee",
            display_name="新人店铺",
            onboarding_status=Merchant.OnboardingStatus.ACTIVE,
            admission_approved=True,
            deposit_initial_paid=True,
            referral_code="MREFEREE1",
        )
        # 新人必须在上个核算月之前入驻，否则不属于该月返佣范围
        Merchant.objects.filter(pk=referee.pk).update(
            created_at=timezone.now() - timedelta(days=120)
        )
        referee.refresh_from_db()
        MerchantReferral.objects.create(
            referrer=self.merchant, referee=referee, code_used=self.merchant.referral_code
        )

        # 上个月发货 20000，落在 2% 档
        shipped_order = self.make_merchant_order(
            quantity=1000, unit_price="20.00", unit_cost="10.00"
        )
        shipped_order.merchant = referee
        shipped_order.shipped_at = timezone.localtime().replace(day=1).replace(
            hour=0, minute=0, second=0
        ) - timedelta(days=1)
        shipped_order.save(update_fields=["merchant", "shipped_at"])

        response = self.post_json("/api/v1/admin/referrals/calculate", {})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["count"], 1)

        commission = ReferralCommission.objects.get()
        self.assertEqual(commission.rate, Decimal("2.000"))
        self.assertEqual(commission.amount, Decimal("400.0000"))

        url = f"/api/v1/admin/referrals/commissions/{commission.public_id}/actions"
        self.assertEqual(self.post_json(url, {"action": "pay"}).status_code, 200)
        self.assertEqual(self.post_json(url, {"action": "pay"}).status_code, 200)
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.wallet_balance, Decimal("400.00"))
        self.assertEqual(
            MerchantWalletEntry.objects.filter(
                merchant=self.merchant,
                kind=MerchantWalletEntry.Kind.REFERRAL_COMMISSION,
            ).count(),
            1,
        )

    def test_only_one_referral_activity_allowed(self):
        payload = {
            "title": "推荐返佣",
            "start": "2026-01-01",
            "is_referral": True,
        }
        first = self.post_json("/api/v1/admin/activities", payload)
        self.assertEqual(first.status_code, 201, first.content)
        second = self.post_json("/api/v1/admin/activities", payload)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["error"]["code"], "REFERRAL_ACTIVITY_EXISTS")
        self.assertEqual(MerchantActivity.objects.filter(is_referral=True).count(), 1)


class WalletServiceTests(CommerceTestBase):
    def test_idempotency_key_prevents_double_entry(self):
        first = record_wallet_entry(
            merchant_id=self.merchant.pk,
            kind=MerchantWalletEntry.Kind.ADJUSTMENT,
            amount=Decimal("10.00"),
            idempotency_key="same-key",
        )
        second = record_wallet_entry(
            merchant_id=self.merchant.pk,
            kind=MerchantWalletEntry.Kind.ADJUSTMENT,
            amount=Decimal("10.00"),
            idempotency_key="same-key",
        )
        self.assertEqual(first.pk, second.pk)
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.wallet_balance, Decimal("10.00"))

    def test_negative_balance_is_rejected(self):
        with self.assertRaises(MerchantOpsError):
            record_wallet_entry(
                merchant_id=self.merchant.pk,
                kind=MerchantWalletEntry.Kind.ADJUSTMENT,
                amount=Decimal("-1.00"),
            )

    def test_unknown_merchant_returns_404(self):
        response = self.client.get(f"/api/v1/admin/merchants/{uuid.uuid4()}")
        self.assertEqual(response.status_code, 404)
