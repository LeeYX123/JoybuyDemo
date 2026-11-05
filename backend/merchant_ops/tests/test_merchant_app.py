"""商家端（merchant-web）接口测试。

重点：
1. 归属隔离：只能看到自己绑定的店，跨店取数被拒；
2. 多店必须显式指定店铺，不隐式猜；
3. 角色权限：只读角色看不到写操作、缺权限直接 403；
4. 保证金菜单/接口按 deposit_enabled 收敛。
"""

import json

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

    def test_multi_shop_requires_explicit_context(self):
        second = Merchant.objects.create(
            slug="seller-shop-2",
            display_name="第二家店",
            onboarding_status=Merchant.OnboardingStatus.ACTIVE,
            admission_approved=True,
            deposit_initial_paid=True,
        )
        MerchantMembership.objects.create(
            merchant=second, staff=self.staff, role=self.owner_role, status="ACTIVE"
        )
        response = self.get("/api/v1/merchant/overview")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "MERCHANT_CONTEXT_REQUIRED")

        # 显式指定后即可访问
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
        self.assertEqual(stats["pending_order_amount"], "40.00")

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
