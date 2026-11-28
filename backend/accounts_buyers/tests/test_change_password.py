"""POST /api/v1/account/change-password：EMAIL 买家改密 + 全会话撤销重签（2026-11-28）。"""

import json

from django.conf import settings
from django.test import Client, TestCase

from accounts_buyers.models import BuyerAccount, BuyerSession

CHANGE_URL = "/api/v1/account/change-password"
SESSION_URL = "/api/v1/auth/buyer/session"
LOGIN_URL = "/api/v1/auth/buyer/login"


class BuyerChangePasswordApiTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.csrf_token = self.client.get(SESSION_URL).json()["csrf_token"]
        self.account = BuyerAccount(
            email="changepwd@joybuy.test", status=BuyerAccount.Status.ACTIVE
        )
        self.account.set_password("OldPassword1!")
        self.account.save()
        # 用 services 建真实会话（token 摘要存库）。
        from accounts_buyers.services import create_buyer_session

        self.session_token, self.session = create_buyer_session(
            account=self.account, ip_address="127.0.0.1", user_agent="test"
        )
        self.client.cookies[settings.BUYER_SESSION_COOKIE_NAME] = self.session_token

    def post_json(self, payload):
        return self.client.post(
            CHANGE_URL,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )

    def _csrf_from_cookie_jar(self, client):
        return client.get(SESSION_URL).json()["csrf_token"]

    def test_success_changes_password_revokes_all_sessions_and_stays_signed_in(self):
        # 先造第二个会话，模拟「其他设备」：改密后必须一并被撤销。
        from accounts_buyers.services import create_buyer_session

        _other_token, other_session = create_buyer_session(
            account=self.account, ip_address="127.0.0.1", user_agent="other-device"
        )

        response = self.post_json(
            {
                "old_password": "OldPassword1!",
                "new_password": "NewPassword2!",
                "confirm_password": "NewPassword2!",
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["password_changed"])
        self.account.refresh_from_db()
        self.assertTrue(self.account.check_password("NewPassword2!"))
        # 全部旧会话（含当前与其他设备）被撤销。
        other_session.refresh_from_db()
        self.assertIsNotNone(other_session.revoked_at)
        self.session.refresh_from_db()
        self.assertIsNotNone(self.session.revoked_at)
        # 当前浏览器拿到新会话 cookie 且仍处于登录态（不被踢出）。
        new_cookie = response.cookies[settings.BUYER_SESSION_COOKIE_NAME].value
        new_session = BuyerSession.objects.filter(
            token_digest__isnull=False, revoked_at__isnull=True
        ).order_by("-pk")
        self.assertTrue(new_session.exists())
        # 用新 cookie 访问 session 接口 → authenticated。
        fresh = Client()
        fresh.cookies[settings.BUYER_SESSION_COOKIE_NAME] = new_cookie
        data = fresh.get(SESSION_URL).json()
        self.assertTrue(data["authenticated"])
        self.assertEqual(data["account"]["id"], str(self.account.public_id))

    def test_old_password_wrong_rejected(self):
        response = self.post_json(
            {
                "old_password": "WrongOld!",
                "new_password": "NewPassword2!",
                "confirm_password": "NewPassword2!",
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "INVALID_CREDENTIALS")
        self.account.refresh_from_db()
        self.assertTrue(self.account.check_password("OldPassword1!"))

    def test_new_password_too_short_rejected(self):
        response = self.post_json(
            {
                "old_password": "OldPassword1!",
                "new_password": "short7!",
                "confirm_password": "short7!",
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "PASSWORD_TOO_SHORT")

    def test_confirm_mismatch_rejected(self):
        response = self.post_json(
            {
                "old_password": "OldPassword1!",
                "new_password": "NewPassword2!",
                "confirm_password": "Different3!",
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "PASSWORD_MISMATCH")

    def test_oauth_account_rejected(self):
        self.account.auth_provider = BuyerAccount.AuthProvider.GOOGLE
        self.account.save(update_fields=["auth_provider"])
        response = self.post_json(
            {
                "old_password": "OldPassword1!",
                "new_password": "NewPassword2!",
                "confirm_password": "NewPassword2!",
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "OAUTH_ACCOUNT")

    def test_requires_signin(self):
        anonymous = Client(enforce_csrf_checks=True)
        csrf = anonymous.get(SESSION_URL).json()["csrf_token"]
        response = anonymous.post(
            CHANGE_URL,
            data=json.dumps(
                {
                    "old_password": "OldPassword1!",
                    "new_password": "NewPassword2!",
                    "confirm_password": "NewPassword2!",
                }
            ),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "AUTH_REQUIRED")

    def test_login_with_old_password_fails_after_change(self):
        self.post_json(
            {
                "old_password": "OldPassword1!",
                "new_password": "NewPassword2!",
                "confirm_password": "NewPassword2!",
            }
        )
        login_client = Client(enforce_csrf_checks=True)
        csrf = login_client.get(SESSION_URL).json()["csrf_token"]
        stale = login_client.post(
            LOGIN_URL,
            data=json.dumps({"identifier": "changepwd@joybuy.test", "password": "OldPassword1!"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(stale.status_code, 401)
        fresh_csrf = login_client.get(SESSION_URL).json()["csrf_token"]
        ok = login_client.post(
            LOGIN_URL,
            data=json.dumps({"identifier": "changepwd@joybuy.test", "password": "NewPassword2!"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=fresh_csrf,
        )
        self.assertEqual(ok.status_code, 200)
