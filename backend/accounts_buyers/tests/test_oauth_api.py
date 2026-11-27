"""三方登录（Google / Facebook）API 测试。

出网一律 mock（``accounts_buyers.oauth._http_json``），测试绝不真连 Google / Facebook。
重点覆盖 docs/16 里的硬约束：
- 无邮箱的 Facebook 账号能建号并拿到会话（identity_bound 满足 buyer_account_has_identifier）；
- state 一次性 + 渠道绑定；
- 只有 Google 的已验证邮箱允许合并，Facebook 同邮箱不合并；
- 禁用账号、未配置渠道、非法 next 的失败路径。
"""

import urllib.parse
from unittest import mock

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings

from accounts_buyers import oauth
from accounts_buyers.models import BuyerAccount, BuyerIdentity

PROVIDERS_URL = "/api/v1/auth/buyer/oauth/providers"
SESSION_URL = "/api/v1/auth/buyer/session"
COOKIE_NAME = "joybuy_buyer_session"

GOOGLE_ONLY = dict(
    GOOGLE_OAUTH_CLIENT_ID="google-client-id",
    GOOGLE_OAUTH_CLIENT_SECRET="google-client-secret",
    FACEBOOK_OAUTH_APP_ID="",
    FACEBOOK_OAUTH_APP_SECRET="",
    OAUTH_REDIRECT_BASE_URL="http://localhost:3000",
    STOREFRONT_BASE_URL="http://localhost:3000",
)
BOTH_PROVIDERS = dict(
    GOOGLE_ONLY,
    FACEBOOK_OAUTH_APP_ID="facebook-app-id",
    FACEBOOK_OAUTH_APP_SECRET="facebook-app-secret",
)

GOOGLE_PROFILE = {
    "sub": "google-sub-1",
    "email": "Buyer@Example.Test",
    "email_verified": True,
    "name": "Buyer One",
    "picture": "http://localhost/media/avatar.png",
}
FACEBOOK_PROFILE = {"id": "fb-app-scoped-1", "name": "FB Buyer"}


def _fake_http_factory(profile):
    """按 URL 分发：token 端点返回 access_token，profile 端点返回给定 profile。"""

    def fake_http(url, data=None, headers=None):
        if "/token" in url and "graph.facebook.com" not in url:
            assert data["code"] == "auth-code", data
            assert data["grant_type"] == "authorization_code"
            return {"access_token": "access-token-1"}
        if "oauth/access_token" in url:
            assert data["code"] == "auth-code"
            return {"access_token": "access-token-1"}
        if "openidconnect.googleapis.com" in url:
            assert headers and headers["Authorization"] == "Bearer access-token-1"
            return profile
        if "graph.facebook.com" in url:
            assert "access_token=access-token-1" in url
            return profile
        raise AssertionError(f"unexpected url {url}")

    return fake_http


class OAuthApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()

    def start(self, provider="google", next_path="/account"):
        url = f"/api/v1/auth/buyer/oauth/{provider}/start"
        if next_path is not None:
            url = f"{url}?{urllib.parse.urlencode({'next': next_path})}"
        return self.client.get(url)

    def state_from(self, response):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(response["Location"]).query)
        return query["state"][0]

    def login(self, provider, profile, *, state=None, next_path="/account"):
        started = self.start(provider, next_path)
        self.assertEqual(started.status_code, 302)
        state = state or self.state_from(started)
        url = f"/api/v1/auth/buyer/oauth/{provider}/callback"
        with mock.patch.object(oauth, "_http_json", side_effect=_fake_http_factory(profile)):
            return self.client.get(
                f"{url}?{urllib.parse.urlencode({'code': 'auth-code', 'state': state})}"
            )

    def session_payload(self):
        return self.client.get(SESSION_URL).json()

    # ------------------------------------------------------------------ 配置

    @override_settings(**GOOGLE_ONLY)
    def test_providers_lists_all_channels_with_enabled_flag(self):
        """未配置的渠道也要返回（enabled=false）：登录页要求两个按钮并排显示。"""

        payload = self.client.get(PROVIDERS_URL).json()

        self.assertEqual(
            payload["providers"],
            [
                {
                    "provider": "google",
                    "enabled": True,
                    "start_url": "/api/v1/auth/buyer/oauth/google/start",
                },
                {
                    "provider": "facebook",
                    "enabled": False,
                    "start_url": "/api/v1/auth/buyer/oauth/facebook/start",
                },
            ],
        )

    @override_settings(**BOTH_PROVIDERS)
    def test_providers_lists_both_channels_when_configured(self):
        payload = self.client.get(PROVIDERS_URL).json()
        self.assertEqual(
            [item["provider"] for item in payload["providers"]], ["google", "facebook"]
        )

    @override_settings(**GOOGLE_ONLY)
    def test_start_redirects_to_google_with_state_and_pkce(self):
        response = self.start()
        self.assertEqual(response.status_code, 302)
        location = response["Location"]
        self.assertTrue(location.startswith("https://accounts.google.com/o/oauth2/v2/auth?"))
        query = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
        self.assertEqual(query["client_id"], ["google-client-id"])
        self.assertEqual(
            query["redirect_uri"],
            ["http://localhost:3000/api/v1/auth/buyer/oauth/google/callback"],
        )
        self.assertEqual(query["scope"], ["openid email profile"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertTrue(query["code_challenge"][0])
        self.assertTrue(query["state"][0])
        # state 落 cache：签发的 provider 与 next 都要能取回
        cached = cache.get(f"{oauth.STATE_CACHE_PREFIX}{query['state'][0]}")
        self.assertEqual(cached["provider"], "google")
        self.assertEqual(cached["next"], "/account")

    @override_settings(**GOOGLE_ONLY)
    def test_start_with_unconfigured_provider_redirects_with_error(self):
        response = self.client.get("/api/v1/auth/buyer/oauth/facebook/start")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            "http://localhost:3000/auth/login?oauth_error=provider_unavailable",
        )

    @override_settings(**BOTH_PROVIDERS)
    def test_start_uses_comma_scope_for_facebook(self):
        response = self.start("facebook")
        query = urllib.parse.parse_qs(urllib.parse.urlparse(response["Location"]).query)
        self.assertEqual(query["scope"], ["email,public_profile"])
        self.assertNotIn("code_challenge", query)

    # ------------------------------------------------------------------ 成功路径

    @override_settings(**GOOGLE_ONLY)
    def test_google_callback_creates_account_identity_and_session(self):
        response = self.login("google", GOOGLE_PROFILE)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "http://localhost:3000/account")
        self.assertIn(COOKIE_NAME, response.cookies)

        account = BuyerAccount.objects.get(email="buyer@example.test")
        self.assertEqual(account.auth_provider, BuyerAccount.AuthProvider.GOOGLE)
        self.assertTrue(account.identity_bound)
        self.assertIsNotNone(account.email_verified_at)
        self.assertFalse(account.check_password("anything"))
        self.assertRegex(account.display_name, r"^user\d{4}[a-z]{4}$")

        identity = BuyerIdentity.objects.get(
            provider=BuyerIdentity.Provider.GOOGLE, subject="google-sub-1"
        )
        self.assertEqual(identity.account_id, account.pk)
        self.assertEqual(identity.email_snapshot, "buyer@example.test")

        session = self.session_payload()
        self.assertTrue(session["authenticated"])
        self.assertEqual(session["account"]["email"], "buyer@example.test")
        self.assertEqual(session["account"]["auth_provider"], "GOOGLE")

    @override_settings(**BOTH_PROVIDERS)
    def test_facebook_without_email_creates_account_and_can_sign_in(self):
        response = self.login("facebook", FACEBOOK_PROFILE)

        self.assertEqual(response.status_code, 302)
        self.assertIn(COOKIE_NAME, response.cookies)

        account = BuyerAccount.objects.get(
            identities__provider=BuyerIdentity.Provider.FACEBOOK,
            identities__subject="fb-app-scoped-1",
        )
        # 核心需求：没有邮箱也要能建号、能登录；批次 CA 起新号默认不进购买白名单
        # （后台「用户管理」可手动加入；历史账号不受影响）。
        self.assertIsNone(account.email)
        self.assertIsNone(account.phone_e164)
        self.assertTrue(account.identity_bound)
        self.assertEqual(account.auth_provider, BuyerAccount.AuthProvider.FACEBOOK)
        self.assertFalse(account.purchase_whitelisted)
        self.assertRegex(account.display_name, r"^user\d{4}[a-z]{4}$")

        session = self.session_payload()
        self.assertTrue(session["authenticated"])
        self.assertIsNone(session["account"]["email"])
        self.assertEqual(session["account"]["auth_provider"], "FACEBOOK")

    @override_settings(**BOTH_PROVIDERS)
    def test_second_facebook_login_reuses_same_account(self):
        self.login("facebook", FACEBOOK_PROFILE)
        first = BuyerAccount.objects.count()

        second = self.login("facebook", FACEBOOK_PROFILE)

        self.assertEqual(second.status_code, 302)
        self.assertEqual(BuyerAccount.objects.count(), first)
        self.assertEqual(
            BuyerIdentity.objects.filter(
                provider=BuyerIdentity.Provider.FACEBOOK, subject="fb-app-scoped-1"
            ).count(),
            1,
        )

    @override_settings(**GOOGLE_ONLY)
    def test_google_verified_email_links_existing_account_without_overwriting(self):
        existing = BuyerAccount(email="buyer@example.test", display_name="Alice")
        existing.set_password("StrongPass!234")
        existing.save()

        response = self.login("google", GOOGLE_PROFILE)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(BuyerAccount.objects.count(), 1)
        existing.refresh_from_db()
        # 合并只加身份，不改首次来源 / 展示名 / 密码
        self.assertEqual(existing.auth_provider, BuyerAccount.AuthProvider.EMAIL)
        self.assertEqual(existing.display_name, "Alice")
        self.assertTrue(existing.check_password("StrongPass!234"))
        self.assertEqual(existing.identities.count(), 1)

    @override_settings(**GOOGLE_ONLY)
    def test_invalid_next_falls_back_to_account_page(self):
        response = self.login("google", GOOGLE_PROFILE, next_path="//evil.example.com")
        self.assertEqual(response["Location"], "http://localhost:3000/account")

    # ------------------------------------------------------------------ 失败路径

    @override_settings(**GOOGLE_ONLY)
    def test_state_is_single_use(self):
        started = self.start()
        state = self.state_from(started)
        url = "/api/v1/auth/buyer/oauth/google/callback"
        with mock.patch.object(oauth, "_http_json", side_effect=_fake_http_factory(GOOGLE_PROFILE)):
            first = self.client.get(f"{url}?code=auth-code&state={state}")
            second = self.client.get(f"{url}?code=auth-code&state={state}")

        self.assertEqual(first.status_code, 302)
        self.assertEqual(
            second["Location"], "http://localhost:3000/auth/login?oauth_error=state_invalid"
        )

    @override_settings(**BOTH_PROVIDERS)
    def test_state_issued_for_one_provider_is_rejected_by_another(self):
        state = self.state_from(self.start("google"))
        response = self.client.get(
            f"/api/v1/auth/buyer/oauth/facebook/callback?code=auth-code&state={state}"
        )
        self.assertEqual(
            response["Location"], "http://localhost:3000/auth/login?oauth_error=state_invalid"
        )

    @override_settings(**GOOGLE_ONLY)
    def test_callback_without_code_reports_denied(self):
        state = self.state_from(self.start())
        response = self.client.get(f"/api/v1/auth/buyer/oauth/google/callback?state={state}")
        self.assertEqual(
            response["Location"], "http://localhost:3000/auth/login?oauth_error=denied"
        )

    @override_settings(**BOTH_PROVIDERS)
    def test_facebook_email_belonging_to_existing_account_is_not_merged(self):
        BuyerAccount.objects.create(email="dup@example.test", password="x", identity_bound=False)

        response = self.login(
            "facebook", {"id": "fb-dup", "name": "Dup", "email": "Dup@Example.Test"}
        )

        self.assertEqual(
            response["Location"],
            "http://localhost:3000/auth/login?oauth_error=email_exists",
        )
        self.assertEqual(BuyerAccount.objects.count(), 1)
        self.assertFalse(BuyerIdentity.objects.filter(subject="fb-dup").exists())

    @override_settings(**GOOGLE_ONLY)
    def test_disabled_account_cannot_login(self):
        account = BuyerAccount(
            email="buyer@example.test",
            status=BuyerAccount.Status.DISABLED,
            identity_bound=True,
            auth_provider=BuyerAccount.AuthProvider.GOOGLE,
        )
        account.set_password("StrongPass!234")
        account.save()
        BuyerIdentity.objects.create(
            account=account,
            provider=BuyerIdentity.Provider.GOOGLE,
            subject="google-sub-1",
        )

        response = self.login("google", GOOGLE_PROFILE)

        self.assertEqual(
            response["Location"], "http://localhost:3000/auth/login?oauth_error=disabled"
        )
        self.assertNotIn(COOKIE_NAME, response.cookies)


class BuyerAccountIdentifierConstraintTests(TestCase):
    """无邮箱账号必须靠 identity_bound 才建得出来（约束放宽后的不变量）。"""

    def test_account_without_identifier_and_without_identity_is_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BuyerAccount.objects.create(
                    email=None, phone_e164=None, password="x", identity_bound=False
                )

    def test_account_with_identity_bound_flag_is_accepted(self):
        account = BuyerAccount.objects.create(
            email=None, phone_e164=None, password="x", identity_bound=True
        )
        self.assertIsNone(account.email)
        self.assertTrue(account.identity_bound)


class SanitizeNextTests(TestCase):
    def test_accepts_only_site_relative_paths(self):
        self.assertEqual(oauth.sanitize_next("/account/orders"), "/account/orders")
        self.assertEqual(oauth.sanitize_next("//evil.example.com"), "/account")
        self.assertEqual(oauth.sanitize_next("https://evil.example.com"), "/account")
        self.assertEqual(oauth.sanitize_next("/\\evil"), "/account")
        self.assertEqual(oauth.sanitize_next(None), "/account")


class ProviderPayloadParsingTests(TestCase):
    """profile 解析：Google 用 Bearer，Facebook 用 query token；FB 邮箱永不置为已验证。"""

    @override_settings(**GOOGLE_ONLY)
    def test_google_profile_normalizes_email_and_verified_flag(self):
        config = oauth.get_provider("google")
        with mock.patch.object(
            oauth,
            "_http_json",
            return_value={"sub": "s1", "email": "A@B.Test", "email_verified": True},
        ):
            profile = oauth.fetch_profile(config, "token")
        self.assertEqual(profile.email, "a@b.test")
        self.assertTrue(profile.email_verified)

    @override_settings(**BOTH_PROVIDERS)
    def test_facebook_profile_never_marks_email_verified(self):
        config = oauth.get_provider("facebook")
        with mock.patch.object(oauth, "_http_json", return_value={"id": "1", "email": "a@b.test"}):
            profile = oauth.fetch_profile(config, "token")
        self.assertEqual(profile.subject, "1")
        self.assertFalse(profile.email_verified)
