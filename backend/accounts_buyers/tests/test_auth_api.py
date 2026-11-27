import json
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts_buyers.models import BuyerAccount, BuyerSession, VerificationCode
from merchants.models import Merchant, MerchantApplication

VERIFY_URL = "/api/v1/auth/buyer/verification-codes"
REGISTER_URL = "/api/v1/auth/buyer/register"
LOGIN_URL = "/api/v1/auth/buyer/login"
LOGOUT_URL = "/api/v1/auth/buyer/logout"
SESSION_URL = "/api/v1/auth/buyer/session"


class BuyerAuthApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(enforce_csrf_checks=True)
        self.csrf_token = self.client.get(SESSION_URL).json()["csrf_token"]

    def post_json(self, url, payload, client=None, include_csrf=True):
        request_client = client or self.client
        headers = {"HTTP_X_CSRFTOKEN": self.csrf_token} if include_csrf else {}
        return request_client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            **headers,
        )

    def request_code(self, *, channel="email", target="buyer@example.test"):
        response = self.post_json(
            VERIFY_URL,
            {"channel": channel, "target": target, "purpose": "register"},
        )
        self.assertEqual(response.status_code, 202)
        return response.json()["test_code"]

    def create_account(
        self, *, email="buyer@example.test", password="StrongPass!234", status="ACTIVE"
    ):
        account = BuyerAccount(email=email, status=status, email_verified_at=timezone.now())
        account.set_password(password)
        account.save()
        return account

    def test_email_registration_creates_account_and_independent_session_cookie(self):
        code = self.request_code(target="  Buyer@Example.Test ")

        response = self.post_json(
            REGISTER_URL,
            {
                "channel": "email",
                "target": "Buyer@Example.Test",
                "purpose": "register",
                "verification_code": code,
                "password": "StrongPass!234",
            },
        )

        self.assertEqual(response.status_code, 201)
        account = BuyerAccount.objects.get()
        self.assertEqual(account.email, "buyer@example.test")
        self.assertTrue(account.check_password("StrongPass!234"))
        self.assertIsNotNone(account.email_verified_at)
        # 批次 CA：新注册账号默认不进购买白名单。
        self.assertFalse(account.purchase_whitelisted)
        self.assertIn(settings.BUYER_SESSION_COOKIE_NAME, response.cookies)
        self.assertNotIn(settings.SESSION_COOKIE_NAME, response.cookies)
        buyer_cookie = response.cookies[settings.BUYER_SESSION_COOKIE_NAME]
        self.assertTrue(buyer_cookie["httponly"])
        self.assertEqual(buyer_cookie["samesite"], "Lax")
        self.assertNotEqual(settings.BUYER_SESSION_COOKIE_NAME, settings.SESSION_COOKIE_NAME)

        session_response = self.client.get(SESSION_URL)
        self.assertTrue(session_response.json()["authenticated"])
        self.assertEqual(session_response.json()["account"]["email"], "buyer@example.test")

    def test_phone_registration_normalizes_e164_number(self):
        code = self.request_code(channel="phone", target="+44 7700 900123")

        response = self.post_json(
            REGISTER_URL,
            {
                "channel": "phone",
                "target": "+44 (7700) 900123",
                "verification_code": code,
                "password": "StrongPass!234",
            },
        )

        self.assertEqual(response.status_code, 201)
        account = BuyerAccount.objects.get()
        self.assertEqual(account.phone_e164, "+447700900123")
        self.assertIsNotNone(account.phone_verified_at)
        # 批次 CA：手机号注册同样默认非白名单。
        self.assertFalse(account.purchase_whitelisted)

    def test_login_session_restore_and_logout(self):
        account = self.create_account()

        login_response = self.post_json(
            LOGIN_URL,
            {"identifier": "BUYER@example.test", "password": "StrongPass!234"},
        )

        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(
            BuyerSession.objects.filter(account=account, revoked_at__isnull=True).count(), 1
        )
        self.assertTrue(self.client.get(SESSION_URL).json()["authenticated"])

        logout_response = self.post_json(LOGOUT_URL, {})
        self.assertEqual(logout_response.status_code, 204)
        self.assertFalse(self.client.get(SESSION_URL).json()["authenticated"])
        self.assertIsNotNone(BuyerSession.objects.get(account=account).revoked_at)

    def test_disabled_account_cannot_login(self):
        self.create_account(status=BuyerAccount.Status.DISABLED)

        response = self.post_json(
            LOGIN_URL,
            {"identifier": "buyer@example.test", "password": "StrongPass!234"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "BUYER_ACCOUNT_DISABLED")

    def test_expired_verification_code_is_rejected(self):
        code = self.request_code()
        VerificationCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

        response = self.post_json(
            REGISTER_URL,
            {
                "channel": "email",
                "target": "buyer@example.test",
                "verification_code": code,
                "password": "StrongPass!234",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "VERIFICATION_CODE_EXPIRED")
        self.assertFalse(BuyerAccount.objects.exists())

    def test_invalid_verification_code_increments_failure_count(self):
        actual_code = self.request_code()
        wrong_code = "000000" if actual_code != "000000" else "000001"

        response = self.post_json(
            REGISTER_URL,
            {
                "channel": "email",
                "target": "buyer@example.test",
                "verification_code": wrong_code,
                "password": "StrongPass!234",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "VERIFICATION_CODE_INVALID")
        self.assertEqual(VerificationCode.objects.get().failed_attempts, 1)

    @override_settings(VERIFICATION_CODE_SEND_LIMIT=2)
    def test_verification_send_is_rate_limited(self):
        first = self.post_json(VERIFY_URL, {"channel": "email", "target": "buyer@example.test"})
        second = self.post_json(VERIFY_URL, {"channel": "email", "target": "buyer@example.test"})
        third = self.post_json(VERIFY_URL, {"channel": "email", "target": "buyer@example.test"})

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(third.status_code, 429)
        self.assertEqual(third.json()["error"]["code"], "VERIFICATION_CODE_RATE_LIMITED")

    @override_settings(BUYER_LOGIN_FAILURE_LIMIT=2)
    def test_failed_logins_are_rate_limited(self):
        self.create_account()
        payload = {"identifier": "buyer@example.test", "password": "wrong-password"}

        first = self.post_json(LOGIN_URL, payload)
        second = self.post_json(LOGIN_URL, payload)
        third = self.post_json(LOGIN_URL, payload)

        self.assertEqual(first.status_code, 401)
        self.assertEqual(second.status_code, 401)
        self.assertEqual(third.status_code, 429)
        self.assertEqual(third.json()["error"]["code"], "BUYER_LOGIN_RATE_LIMITED")

    def test_staff_cookie_does_not_authenticate_buyer(self):
        isolated_client = Client(enforce_csrf_checks=True)
        isolated_client.cookies[settings.SESSION_COOKIE_NAME] = "staff-session-token"

        response = isolated_client.get(SESSION_URL)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["authenticated"])
        self.assertNotIn(settings.BUYER_SESSION_COOKIE_NAME, response.cookies)

    def test_write_endpoints_require_csrf(self):
        response = self.post_json(
            VERIFY_URL,
            {"channel": "email", "target": "buyer@example.test"},
            include_csrf=False,
        )

        self.assertEqual(response.status_code, 403)


class BuyerSessionMerchantApplicationTests(TestCase):
    """需求 12.2：session payload 随带申请店铺状态（头部入口不再单独发请求）。"""

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    def create_account(self, *, email="shopper@example.test"):
        account = BuyerAccount(email=email, email_verified_at=timezone.now())
        account.set_password("StrongPass!234")
        account.save()
        session_login = self.client.post(
            LOGIN_URL,
            data=json.dumps(
                {"identifier": email, "password": "StrongPass!234"},
            ),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.client.get(SESSION_URL).json()["csrf_token"],
        )
        self.assertEqual(session_login.status_code, 200)
        return account

    def session_account(self):
        payload = self.client.get(SESSION_URL).json()
        self.assertTrue(payload["authenticated"])
        return payload["account"]

    def test_session_without_application_has_null_status_and_merchant(self):
        self.create_account()

        account = self.session_account()

        self.assertIsNone(account["merchant_application_status"])
        self.assertIsNone(account["merchant_id"])

    def test_session_reports_pending_application_without_merchant(self):
        account = self.create_account(email="pending@example.test")
        MerchantApplication.objects.create(buyer=account, shop_name="Pending Shop")

        payload = self.session_account()

        self.assertEqual(payload["merchant_application_status"], "PENDING")
        self.assertIsNone(payload["merchant_id"])

    def test_session_reports_approved_application_with_merchant_id(self):
        account = self.create_account(email="approved@example.test")
        merchant = Merchant.objects.create(slug="approved-shop", display_name="Approved Shop")
        MerchantApplication.objects.create(
            buyer=account,
            shop_name="Approved Shop",
            status=MerchantApplication.Status.APPROVED,
            merchant=merchant,
        )

        payload = self.session_account()

        self.assertEqual(payload["merchant_application_status"], "APPROVED")
        self.assertEqual(payload["merchant_id"], str(merchant.public_id))

    def test_session_response_is_not_cacheable(self):
        """审核通过后前端后台再校验必须拿到新状态：会话响应禁止缓存。"""

        self.create_account(email="no-store@example.test")

        response = self.client.get(SESSION_URL)

        self.assertEqual(response["Cache-Control"], "no-store")

    def test_application_is_one_per_buyer(self):
        """`.first()` 取状态的前提：buyer 是 OneToOne（DB 唯一键）。

        2026-11-27 缺陷排查记录：不存在「同一买家多条申请、`.first()` 取到旧
        REJECTED 行」这种可能——驳回后重申是把原行重置为 PENDING，新增第二条
        会直接违反唯一约束。
        """

        account = self.create_account(email="single-row@example.test")
        MerchantApplication.objects.create(buyer=account, shop_name="First Shop")

        with self.assertRaises(IntegrityError):
            MerchantApplication.objects.create(buyer=account, shop_name="Second Shop")

    def test_session_reflects_approval_immediately(self):
        """同一会话下把申请改成 APPROVED 后，下一次 GET session 立即返回新状态。"""

        account = self.create_account(email="flip@example.test")
        application = MerchantApplication.objects.create(buyer=account, shop_name="Flip Shop")
        self.assertEqual(self.session_account()["merchant_application_status"], "PENDING")

        merchant = Merchant.objects.create(slug="flip-shop", display_name="Flip Shop")
        application.status = MerchantApplication.Status.APPROVED
        application.merchant = merchant
        application.save(update_fields=["status", "merchant"])

        payload = self.session_account()
        self.assertEqual(payload["merchant_application_status"], "APPROVED")
        self.assertEqual(payload["merchant_id"], str(merchant.public_id))


class BuyerDisplayNameTests(TestCase):
    """需求 13.5-6: 未设置用户名显示 `user+数字+字母`（首次生成固定存库）。"""

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    def create_account(self, *, email="named@example.test", display_name=""):
        account = BuyerAccount(
            email=email,
            email_verified_at=timezone.now(),
            display_name=display_name,
        )
        account.set_password("StrongPass!234")
        account.save()
        return account

    def login(self, email):
        session_login = self.client.post(
            LOGIN_URL,
            data=json.dumps({"identifier": email, "password": "StrongPass!234"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.client.get(SESSION_URL).json()["csrf_token"],
        )
        self.assertEqual(session_login.status_code, 200)

    def session_account(self):
        payload = self.client.get(SESSION_URL).json()
        self.assertTrue(payload["authenticated"])
        return payload["account"]

    def test_session_generates_display_name_once_in_real_site_format(self):
        account = self.create_account()
        self.login(account.email)

        first = self.session_account()["display_name"]
        second = self.session_account()["display_name"]

        self.assertRegex(first, r"^user\d{4}[a-z]{4}$")
        self.assertEqual(first, second)
        account.refresh_from_db()
        self.assertEqual(account.display_name, first)

    def test_session_keeps_existing_display_name(self):
        account = self.create_account(display_name="Alice")
        self.login(account.email)

        payload = self.session_account()

        self.assertEqual(payload["display_name"], "Alice")


class BuyerPurchaseWhitelistDefaultTests(TestCase):
    """批次 CA：新注册买家默认 ``purchase_whitelisted=False``，已有账号不受影响。"""

    REGISTER_EMAIL_URL = "/api/v1/auth/buyer/register/email"

    def setUp(self):
        cache.clear()
        self.client = Client(enforce_csrf_checks=True)
        self.csrf_token = self.client.get(SESSION_URL).json()["csrf_token"]

    def test_direct_email_registration_creates_non_whitelisted_account(self):
        response = self.client.post(
            self.REGISTER_EMAIL_URL,
            data=json.dumps({"email": "new-buyer@example.test", "password": "StrongPass!234"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )

        self.assertEqual(response.status_code, 201)
        account = BuyerAccount.objects.get(email="new-buyer@example.test")
        self.assertFalse(account.purchase_whitelisted)
        self.assertFalse(response.json()["account"]["purchase_whitelisted"])

    def test_existing_whitelisted_account_keeps_flag(self):
        """老账号（含后台手工加白）不被注册默认值影响。"""

        account = BuyerAccount(email="old-buyer@example.test", email_verified_at=timezone.now())
        account.set_password("StrongPass!234")
        account.save()

        account.refresh_from_db()
        self.assertTrue(account.purchase_whitelisted)

        # 登录不会重置白名单
        response = self.client.post(
            LOGIN_URL,
            data=json.dumps({"identifier": "old-buyer@example.test", "password": "StrongPass!234"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        self.assertEqual(response.status_code, 200)
        account.refresh_from_db()
        self.assertTrue(account.purchase_whitelisted)
