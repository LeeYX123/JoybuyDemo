"""购物端「进入商家中心」：买家会话换商家端员工会话。

覆盖：
1. 401 未登录 / 400 无申请或未通过；
2. APPROVED 时按买家邮箱找到 approve 时创建的 StaffAccount，签发与商家端
   登录同款的 staff 会话 cookie，并用该 cookie 能打开 /merchant/shops；
3. 跳转 URL = 当前请求 Origin 主机 + 5174，MERCHANT_WEB_URL 可覆盖；
4. 只认买家自己的申请，忽略请求体里的 staff_id / merchant_id；
5. StaffAccount / membership 缺失或停用时的稳定错误码。
"""

import json

from django.test import TestCase, override_settings

from accounts_buyers.models import BuyerAccount
from accounts_buyers.services import create_buyer_session
from accounts_staff.models import PlatformRole, StaffAccount, StaffRoleAssignment, StaffSession
from accounts_staff.services import create_staff_session
from merchants.models import Merchant, MerchantApplication, MerchantMembership, MerchantRole

BUYER_PASSWORD = "Buyer#2026pass"


class MerchantConsoleSessionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = StaffAccount.objects.create(
            email="console-admin@joybuy.test", display_name="审核员", status="ACTIVE"
        )
        cls.admin.set_password("Admin#2026pass")
        cls.admin.save()

    def setUp(self):
        self.client.cookies.clear()

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _make_buyer(self, email="buyer-console@joybuy.test", password=BUYER_PASSWORD):
        buyer = BuyerAccount(email=email, password="x")
        buyer.set_password(password)
        buyer.save()
        return buyer

    def _login_buyer(self, buyer):
        token, _session = create_buyer_session(
            account=buyer, ip_address="127.0.0.1", user_agent="test"
        )
        self.client.cookies["joybuy_buyer_session"] = token

    def _login_admin(self):
        StaffRoleAssignment.objects.get_or_create(
            staff=self.admin, defaults={"role": PlatformRole.objects.get(code="platform_admin")}
        )
        token, _session = create_staff_session(
            staff=self.admin, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token

    def _post_json(self, path, payload, **extra):
        return self.client.post(
            path, data=json.dumps(payload), content_type="application/json", **extra
        )

    def _submit(self, buyer, shop_name="控制台测试店"):
        self._login_buyer(buyer)
        return self._post_json(
            "/api/v1/account/merchant-application", {"shop_name": shop_name}
        )

    def _approve(self, buyer):
        self._login_admin()
        application = MerchantApplication.objects.get(buyer=buyer)
        response = self._post_json(
            "/api/v1/admin/merchant-applications/actions",
            {
                "application_id": str(application.pk),
                "action": "approve",
                "require_deposit": False,
                "ban_after_days": 4,
            },
        )
        self.assertEqual(response.status_code, 200)
        return response

    def _switch(self, payload=None, **extra):
        extra.setdefault("HTTP_ORIGIN", "http://localhost:3000")
        return self._post_json(
            "/api/v1/account/merchant-console-session", payload or {}, **extra
        )

    # ------------------------------------------------------------------
    # 鉴权 / 状态
    # ------------------------------------------------------------------
    def test_requires_buyer_login(self):
        response = self._switch()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "BUYER_AUTH_REQUIRED")

    def test_rejects_buyer_without_application(self):
        self._login_buyer(self._make_buyer())
        response = self._switch()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "APPLICATION_NOT_APPROVED")

    def test_rejects_pending_application(self):
        buyer = self._make_buyer()
        self.assertEqual(self._submit(buyer).status_code, 201)
        self._login_buyer(buyer)
        response = self._switch()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "APPLICATION_NOT_APPROVED")

    def test_rejects_rejected_application(self):
        buyer = self._make_buyer()
        self._submit(buyer)
        self._login_admin()
        application = MerchantApplication.objects.get(buyer=buyer)
        response = self._post_json(
            "/api/v1/admin/merchant-applications/actions",
            {
                "application_id": str(application.pk),
                "action": "reject",
                "reason": "资料不完整",
            },
        )
        self.assertEqual(response.status_code, 200)
        self._login_buyer(buyer)
        response = self._switch()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "APPLICATION_NOT_APPROVED")

    # ------------------------------------------------------------------
    # 成功：签发 staff 会话
    # ------------------------------------------------------------------
    def test_issues_staff_session_for_the_buyers_own_staff_account(self):
        buyer = self._make_buyer()
        self._submit(buyer)
        self._approve(buyer)
        merchant = MerchantApplication.objects.get(buyer=buyer).merchant
        staff = StaffAccount.objects.get(email=buyer.email)
        self.assertEqual(
            StaffSession.objects.filter(staff=staff).count(), 0, "approve 不应创建会话"
        )

        self._login_buyer(buyer)
        response = self._switch()
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["url"], "http://localhost:5174/")
        self.assertEqual(payload["staff"]["email"], buyer.email)
        self.assertEqual(payload["merchant"]["id"], str(merchant.public_id))
        self.assertEqual(payload["expires_in"], 28800)

        cookie = response.cookies.get("joybuy_staff_session")
        self.assertIsNotNone(cookie)
        self.assertEqual(cookie["path"], "/api/v1/")
        self.assertEqual(StaffSession.objects.filter(staff=staff).count(), 1)
        self.assertEqual(StaffSession.objects.filter(staff=self.admin).count(), 1)

        # 用响应里下发的 cookie 直接访问商家端接口，确认不是「假登录」。
        self.client.cookies["joybuy_staff_session"] = cookie.value
        response = self.client.get("/api/v1/merchant/shops")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["name"] for item in response.json()["items"]], ["控制台测试店"])

    def test_uses_configured_merchant_web_url(self):
        buyer = self._make_buyer()
        self._submit(buyer)
        self._approve(buyer)
        self._login_buyer(buyer)
        with override_settings(MERCHANT_WEB_URL="https://seller.joybuy.test"):
            response = self._switch()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["url"], "https://seller.joybuy.test/")

    def test_falls_back_to_request_host_when_origin_missing(self):
        buyer = self._make_buyer()
        self._submit(buyer)
        self._approve(buyer)
        self._login_buyer(buyer)
        with override_settings(MERCHANT_WEB_URL=""):
            response = self._switch(HTTP_ORIGIN="")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["url"], "http://testserver:5174/")

    def test_ignores_client_supplied_staff_or_merchant_ids(self):
        buyer = self._make_buyer()
        self._submit(buyer)
        self._approve(buyer)
        buyer_staff = StaffAccount.objects.get(email=buyer.email)

        other_staff = StaffAccount.objects.create(
            email="other-staff@joybuy.test", display_name="别人", status="ACTIVE"
        )
        other_staff.set_password("Other#2026pass")
        other_staff.save()
        other_merchant = Merchant.objects.create(slug="other-shop", display_name="别人的店")
        MerchantMembership.objects.create(
            merchant=other_merchant,
            staff=other_staff,
            role=MerchantRole.objects.get(code="merchant_owner"),
            status=MerchantMembership.Status.ACTIVE,
        )

        self._login_buyer(buyer)
        response = self._switch(
            {
                "staff_id": str(other_staff.public_id),
                "merchant_id": str(other_merchant.public_id),
                "email": other_staff.email,
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["staff"]["id"], str(buyer_staff.public_id))
        self.assertEqual(StaffSession.objects.filter(staff=other_staff).count(), 0)

    # ------------------------------------------------------------------
    # 数据不一致
    # ------------------------------------------------------------------
    def test_missing_staff_account_conflict(self):
        buyer = self._make_buyer()
        self._submit(buyer)
        self._approve(buyer)
        StaffAccount.objects.get(email=buyer.email).delete()
        self._login_buyer(buyer)
        response = self._switch()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "MERCHANT_ACCOUNT_MISSING")

    def test_disabled_staff_account_conflict(self):
        buyer = self._make_buyer()
        self._submit(buyer)
        self._approve(buyer)
        staff = StaffAccount.objects.get(email=buyer.email)
        staff.status = StaffAccount.Status.DISABLED
        staff.save(update_fields=["status", "updated_at"])
        self._login_buyer(buyer)
        response = self._switch()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "MERCHANT_ACCOUNT_DISABLED")

    def test_missing_membership_conflict(self):
        buyer = self._make_buyer()
        self._submit(buyer)
        self._approve(buyer)
        MerchantMembership.objects.filter(staff__email=buyer.email).delete()
        self._login_buyer(buyer)
        response = self._switch()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "MERCHANT_MEMBERSHIP_MISSING")
