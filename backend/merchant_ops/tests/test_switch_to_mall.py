"""商家端 → 购物端 handoff 契约测试。

1. POST /api/v1/merchant/switch-to-mall：商家会话 → 同邮箱买家账号 + 短期
   一次性 handoff token（不再 Set-Cookie）；
2. POST /api/v1/auth/buyer/merchant-handoff：购物端用自己的 host 兑换 token，
   成功后种 host-only buyer session cookie；token 用后即删（60 秒 TTL）。
"""

import json

from django.core.cache import cache
from django.test import TestCase, override_settings

from accounts_buyers.models import BuyerAccount
from accounts_buyers.services import (
    MERCHANT_HANDOFF_CACHE_PREFIX,
    issue_merchant_handoff_token,
)
from accounts_staff.models import StaffAccount
from accounts_staff.services import create_staff_session

SWITCH_URL = "/api/v1/merchant/switch-to-mall"
HANDOFF_URL = "/api/v1/auth/buyer/merchant-handoff"
BUYER_SESSION_URL = "/api/v1/auth/buyer/session"
STAFF_PASSWORD = "Seller#2026pass"
BUYER_PASSWORD = "BuyerOwn#2026pass"
COOKIE_NAME = "joybuy_buyer_session"


def _cache_key(token: str) -> str:
    return f"{MERCHANT_HANDOFF_CACHE_PREFIX}{token}"


class MerchantHandoffTestBase(TestCase):
    def setUp(self):
        self.client.cookies.clear()
        self._issued_tokens: list[str] = []

    def tearDown(self):
        # token 存在 redis（不是测试库），用不完的要显式删掉，避免污染开发缓存。
        for token in self._issued_tokens:
            cache.delete(_cache_key(token))

    def _make_staff(self, email="switch-seller@joybuy.test", password=STAFF_PASSWORD):
        staff = StaffAccount.objects.create(email=email, display_name="切换商家")
        staff.set_password(password)
        staff.save()
        return staff

    def _login(self, staff):
        token, _session = create_staff_session(
            staff=staff, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token

    def _switch(self, origin="http://localhost:5174"):
        extra = {"HTTP_ORIGIN": origin} if origin else {}
        response = self.client.post(
            SWITCH_URL, data=json.dumps({}), content_type="application/json", **extra
        )
        token = response.json().get("handoff_token") if response.status_code == 200 else None
        if token:
            self._issued_tokens.append(token)
        return response

    def _issue_for(self, buyer):
        token = issue_merchant_handoff_token(buyer_id=buyer.public_id)
        self._issued_tokens.append(token)
        return token

    def _exchange(self, token):
        return self.client.post(
            HANDOFF_URL,
            data=json.dumps({"token": token}),
            content_type="application/json",
        )

    def _use_buyer_cookie(self, response):
        value = response.cookies[COOKIE_NAME].value
        self.client.cookies[COOKIE_NAME] = value
        return value


class SwitchToMallTests(MerchantHandoffTestBase):
    # ------------------------------------------------------------------
    # 鉴权 / 参数
    # ------------------------------------------------------------------
    def test_requires_staff_login(self):
        response = self._switch()

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "MERCHANT_AUTH_REQUIRED")

    def test_staff_without_email_is_rejected(self):
        staff = self._make_staff(email="")
        self._login(staff)

        response = self._switch()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "STAFF_EMAIL_REQUIRED")
        self.assertFalse(BuyerAccount.objects.filter(email="").exists())

    # ------------------------------------------------------------------
    # 首次 / 再次切换：账号口径不变，但只发 token 不写 cookie
    # ------------------------------------------------------------------
    def test_first_switch_creates_buyer_and_returns_handoff_payload(self):
        staff = self._make_staff()
        self._login(staff)

        response = self._switch()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(set(payload), {"handoff_token", "redirect_url"})
        self.assertTrue(payload["handoff_token"])
        self.assertEqual(
            payload["redirect_url"],
            "http://localhost:3000/auth/merchant-handoff?token=" + payload["handoff_token"],
        )
        # 新方案不再由商家端写 buyer cookie（跨 host cookie 会被浏览器拒绝）。
        self.assertNotIn(COOKIE_NAME, response.cookies)
        buyer = BuyerAccount.objects.get(email=staff.email)
        self.assertEqual(buyer.status, BuyerAccount.Status.ACTIVE)
        self.assertEqual(buyer.auth_provider, BuyerAccount.AuthProvider.EMAIL)
        self.assertTrue(buyer.check_password(STAFF_PASSWORD))
        self.assertEqual(buyer.password, staff.password)
        self.assertEqual(
            cache.get(_cache_key(payload["handoff_token"])),
            {"buyer_id": str(buyer.public_id)},
        )

    def test_second_switch_reuses_buyer_and_keeps_password(self):
        staff = self._make_staff()
        self._login(staff)
        self._switch()
        buyer = BuyerAccount.objects.get(email=staff.email)
        password_before = buyer.password

        response = self._switch()

        self.assertEqual(response.status_code, 200)
        buyer.refresh_from_db()
        self.assertEqual(buyer.password, password_before)
        self.assertEqual(BuyerAccount.objects.filter(email=staff.email).count(), 1)

    def test_existing_buyer_password_is_not_overwritten(self):
        staff = self._make_staff()
        buyer = BuyerAccount(email=staff.email, password="x")
        buyer.set_password(BUYER_PASSWORD)
        buyer.save()
        self._login(staff)

        response = self._switch()

        self.assertEqual(response.status_code, 200)
        buyer.refresh_from_db()
        self.assertTrue(buyer.check_password(BUYER_PASSWORD))
        self.assertFalse(buyer.check_password(STAFF_PASSWORD))

    @override_settings(STOREFRONT_BASE_URL="https://shop.joybuy.test")
    def test_redirect_url_uses_configured_storefront_base(self):
        staff = self._make_staff()
        self._login(staff)

        response = self._switch(origin="http://m.localhost:5174")

        token = response.json()["handoff_token"]
        self.assertEqual(
            response.json()["redirect_url"],
            f"https://shop.joybuy.test/auth/merchant-handoff?token={token}",
        )


class MerchantHandoffExchangeTests(MerchantHandoffTestBase):
    def setUp(self):
        super().setUp()
        self.buyer = BuyerAccount.objects.create(
            email="handoff-buyer@joybuy.test",
            password="x",
            status=BuyerAccount.Status.ACTIVE,
            auth_provider=BuyerAccount.AuthProvider.EMAIL,
        )

    # ------------------------------------------------------------------
    # 兑换成功
    # ------------------------------------------------------------------
    def test_exchange_creates_host_only_buyer_session(self):
        token = self._issue_for(self.buyer)

        response = self._exchange(token)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"email": self.buyer.email})
        cookie = response.cookies[COOKIE_NAME]
        self.assertEqual(cookie["path"], "/")
        self.assertEqual(cookie.get("domain", ""), "")
        self.assertTrue(cookie["httponly"])

    def test_exchange_requires_no_login_and_authenticates_session(self):
        token = self._issue_for(self.buyer)

        response = self._exchange(token)
        self._use_buyer_cookie(response)

        session = self.client.get(BUYER_SESSION_URL)
        self.assertEqual(session.status_code, 200)
        payload = session.json()
        self.assertTrue(payload["authenticated"])
        self.assertEqual(payload["account"]["email"], self.buyer.email)

    def test_full_switch_then_exchange_round_trip(self):
        staff = self._make_staff(email="round-trip@joybuy.test")
        self._login(staff)
        switch = self._switch()
        token = switch.json()["handoff_token"]
        # 商家端不获得 buyer cookie；兑换发生在购物端。
        self.client.cookies.pop(COOKIE_NAME, None)

        exchange = self._exchange(token)
        self._use_buyer_cookie(exchange)

        payload = self.client.get(BUYER_SESSION_URL).json()
        self.assertTrue(payload["authenticated"])
        self.assertEqual(payload["account"]["email"], staff.email)

    # ------------------------------------------------------------------
    # 一次性 / 过期 / 无效
    # ------------------------------------------------------------------
    def test_token_is_one_time(self):
        token = self._issue_for(self.buyer)
        first = self._exchange(token)
        self.assertEqual(first.status_code, 200)

        second = self._exchange(token)

        self.assertEqual(second.status_code, 400)
        self.assertEqual(second.json()["error"]["code"], "HANDOFF_TOKEN_INVALID")
        self.assertNotIn(COOKIE_NAME, second.cookies)

    def test_expired_token_is_rejected(self):
        token = self._issue_for(self.buyer)
        cache.delete(_cache_key(token))  # 模拟 60 秒 TTL 已过

        response = self._exchange(token)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "HANDOFF_TOKEN_INVALID")
        self.assertIn("登录凭证已过期", response.json()["error"]["message"])

    def test_unknown_token_is_rejected(self):
        response = self._exchange("not-a-real-token")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "HANDOFF_TOKEN_INVALID")

    def test_missing_token_is_rejected(self):
        response = self.client.post(
            HANDOFF_URL, data=json.dumps({}), content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "HANDOFF_TOKEN_INVALID")

    def test_inactive_buyer_token_is_rejected(self):
        self.buyer.status = BuyerAccount.Status.DISABLED
        self.buyer.save(update_fields=["status"])
        token = self._issue_for(self.buyer)

        response = self._exchange(token)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "HANDOFF_TOKEN_INVALID")
