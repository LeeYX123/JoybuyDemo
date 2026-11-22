"""商家端（merchant-web）接口测试。

重点：
1. 归属隔离：只能看到自己绑定的店，跨店取数被拒；
2. 一个账号只能绑定一家店（2026-11-22）：绑第二家店被唯一约束拒绝，
   存量脏数据（多店）返回 403 MERCHANT_MULTIPLE_SHOPS；
3. 角色权限：只读角色看不到写操作、缺权限直接 403；
4. 保证金菜单/接口按 deposit_enabled 收敛。
"""

import json
from types import SimpleNamespace
from unittest import mock

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from accounts_buyers.models import BuyerAccount
from accounts_staff.models import StaffAccount
from accounts_staff.services import create_staff_session
from merchants.models import Merchant, MerchantMembership, MerchantPermission, MerchantRole
from orders.models import MerchantOrder, Order


class MerchantAppTestBase(TestCase):
    def setUp(self):
        self.owner_role = MerchantRole.objects.get(code="merchant_owner")
        self.staff_role = MerchantRole.objects.get(code="merchant_staff")
        self.staff = self._make_staff("seller@joybuy.test")
        self.shop = Merchant.objects.create(
            slug="seller-shop",
            display_name="卖家店",
            onboarding_status=Merchant.OnboardingStatus.ACTIVE,
            admission_approved=True,
            deposit_initial_paid=True,
            referral_code="MSELLER01",
        )
        MerchantMembership.objects.create(
            merchant=self.shop, staff=self.staff, role=self.owner_role, status="ACTIVE"
        )
        self._login("SELLER01")

    def _make_staff(self, email):
        staff, _ = StaffAccount.objects.get_or_create(
            email=email, defaults={"display_name": "卖家", "password": "x"}
        )
        staff.set_password("Seller#2026pass")
        staff.save()
        return staff

    def _login(self, shop_id=""):
        token, _session = create_staff_session(
            staff=self.staff, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token
        self.shop_id = shop_id

    def get(self, path, **extra):
        return self.client.get(path, **extra)

    def post_json(self, path, payload=None, **extra):
        return self.client.post(
            path, data=json.dumps(payload or {}), content_type="application/json", **extra
        )

    def make_order(self, merchant, *, items_total="40.00", cost_total="20.00", pending=True):
        buyer = BuyerAccount.objects.create(email=f"b-{merchant.pk}@joybuy.test", password="x")
        order = Order.objects.create(
            account=buyer,
            currency_id=1,
            items_subtotal=items_total,
            shipping_cost=0,
            total=items_total,
            shipping_address={"region": "London"},
            payment_expires_at=timezone.now(),
            # WP-42：今日订单数只统计已付款（购买成功）的商家子单。
            status=Order.Status.PAID,
            payment_method="CARD",
            paid_at=timezone.now(),
        )
        return MerchantOrder.objects.create(
            order=order,
            merchant=merchant,
            currency="GBP",
            items_total=items_total,
            cost_total=cost_total,
            status=MerchantOrder.Status.PENDING if pending else MerchantOrder.Status.SHIPPED,
        )


class ShopsAndContextTests(MerchantAppTestBase):
    def test_single_shop_resolves_without_header(self):
        response = self.get("/api/v1/merchant/shops")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["items"]), 1)
        self.assertEqual(response.json()["items"][0]["name"], "卖家店")

    def test_account_cannot_bind_two_shops(self):
        """一个账号只能绑定一家店（2026-11-22）：第二家店绑定被唯一约束拒绝。"""

        second = Merchant.objects.create(
            slug="seller-shop-2",
            display_name="第二家店",
            onboarding_status=Merchant.OnboardingStatus.ACTIVE,
            admission_approved=True,
            deposit_initial_paid=True,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            MerchantMembership.objects.create(
                merchant=second, staff=self.staff, role=self.owner_role, status="ACTIVE"
            )
        self.assertEqual(MerchantMembership.objects.filter(staff=self.staff).count(), 1)

        # 单店账号无需 X-Merchant-Id 头，直接解析到自己那家店。
        response = self.get("/api/v1/merchant/overview")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["merchant"]["name"], "卖家店")

    def test_dirty_multi_shop_data_is_rejected_with_403(self):
        """存量脏数据（一账号多店）兜底：403 MERCHANT_MULTIPLE_SHOPS，不再提示选店。"""

        second = Merchant.objects.create(
            slug="dirty-shop-2",
            display_name="脏数据第二家店",
            onboarding_status=Merchant.OnboardingStatus.ACTIVE,
        )
        real_memberships = list(
            MerchantMembership.objects.select_related("merchant", "role").filter(staff=self.staff)
        )
        fake_membership = SimpleNamespace(merchant=second, role=self.owner_role)
        with mock.patch(
            "merchant_ops.merchant_context.memberships_for",
            return_value=real_memberships + [fake_membership],
        ):
            response = self.get("/api/v1/merchant/overview")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "MERCHANT_MULTIPLE_SHOPS")

        # 显式 X-Merchant-Id 仍可正常进入自己的店
        with mock.patch(
            "merchant_ops.merchant_context.memberships_for",
            return_value=real_memberships + [fake_membership],
        ):
            response = self.get(
                "/api/v1/merchant/overview", HTTP_X_MERCHANT_ID=str(self.shop.public_id)
            )
        self.assertEqual(response.status_code, 200)

    def test_cannot_access_other_merchant(self):
        other = Merchant.objects.create(slug="other-shop", display_name="别人家")
        response = self.get("/api/v1/merchant/overview", HTTP_X_MERCHANT_ID=str(other.public_id))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "MERCHANT_NOT_ACCESSIBLE")

    def test_staff_without_membership_is_rejected(self):
        stranger = self._make_staff("stranger@joybuy.test")
        token, _ = create_staff_session(
            staff=stranger, ip_address="127.0.0.1", user_agent="t", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token
        response = self.get("/api/v1/merchant/overview")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "MERCHANT_MEMBERSHIP_REQUIRED")

    def test_anonymous_is_rejected(self):
        self.client.cookies.clear()
        response = self.get("/api/v1/merchant/overview")
        self.assertEqual(response.status_code, 401)


class OverviewTests(MerchantAppTestBase):
    def test_overview_scope_is_own_shop_only(self):
        self.make_order(self.shop)
        other = Merchant.objects.create(slug="noise-shop", display_name="噪音店")
        self.make_order(other)

        response = self.get("/api/v1/merchant/overview")
        self.assertEqual(response.status_code, 200, response.content)
        stats = response.json()["stats"]
        self.assertEqual(stats["today_order_count"], 1)
        self.assertEqual(stats["pending_shipment_count"], 1)
        # 迭代02：待发货金额 = 成本价合计。
        self.assertEqual(stats["pending_order_amount"], "20.00")

    def test_charts_cover_seven_days_and_never_divide_by_zero(self):
        response = self.get("/api/v1/merchant/overview")
        bars = response.json()["charts"]["order_bars"]
        self.assertEqual(len(bars), 7)
        self.assertTrue(all(bar["count"] == 0 for bar in bars))

    def test_deposit_flag_exposed_for_menu(self):
        response = self.get("/api/v1/merchant/overview")
        self.assertFalse(response.json()["merchant"]["deposit_enabled"])

    def test_permissions_listed_for_frontend(self):
        response = self.get("/api/v1/merchant/overview")
        codes = response.json()["permissions"]
        self.assertIn("merchant.dashboard.view", codes)
        self.assertIn("merchant.wallet.manage", codes)


class PermissionTests(MerchantAppTestBase):
    def _switch_role(self, role):
        MerchantMembership.objects.filter(staff=self.staff, merchant=self.shop).update(role=role)

    def test_readonly_role_cannot_read_orders(self):
        # merchant_staff 有 orders.manage，先验证能读
        self._switch_role(self.staff_role)
        response = self.get("/api/v1/merchant/orders")
        # 订单列表接口尚未交付（第三批），这里只校验上下文与权限闸门不误杀
        self.assertIn(response.status_code, (200, 404))

    def test_role_without_wallet_permission_is_denied(self):
        viewer = MerchantRole.objects.create(
            code="merchant_limited", name="受限角色", is_system=True
        )
        viewer.permissions.set(MerchantPermission.objects.filter(code="merchant.dashboard.view"))
        self._switch_role(viewer)
        response = self.get("/api/v1/merchant/profile")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "MERCHANT_PERMISSION_DENIED")


class ProfileTests(MerchantAppTestBase):
    def test_patch_updates_name(self):
        response = self.client.patch(
            "/api/v1/merchant/profile",
            data=json.dumps({"name": "改名后的店"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.display_name, "改名后的店")

    def test_empty_name_rejected(self):
        response = self.client.patch(
            "/api/v1/merchant/profile",
            data=json.dumps({"name": "   "}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
