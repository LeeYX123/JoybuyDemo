import json
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts_buyers.models import BuyerAccount, BuyerSession, VerificationCode

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
