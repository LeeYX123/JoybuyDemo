"""email-first 第一步的账号查询接口（docs/17 §4）。

该接口是登录页「继续」按钮的分流依据，也是本轮唯一新增的账号枚举面，
所以除了功能，还要盯住三件事：限流、恒定耗时、只返回布尔。
"""

import json

from django.core.cache import cache
from django.test import Client, TestCase
from django.utils import timezone

from accounts_buyers.models import BuyerAccount

LOOKUP_URL = "/api/v1/auth/buyer/identifier/lookup"
SESSION_URL = "/api/v1/auth/buyer/session"


class IdentifierLookupApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(enforce_csrf_checks=True)
        self.csrf_token = self.client.get(SESSION_URL).json()["csrf_token"]

    def lookup(self, identifier, client=None):
        request_client = client or self.client
        return request_client.post(
            LOOKUP_URL,
            data=json.dumps({"identifier": identifier}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )

    def create_account(self, *, email="buyer@example.test", phone=None, status="ACTIVE"):
        account = BuyerAccount(
            email=email,
            phone_e164=phone,
            status=status,
            email_verified_at=timezone.now() if email else None,
        )
        account.set_password("StrongPass!234")
        account.save()
        return account

    def test_existing_email_reports_exists_without_leaking_account_fields(self):
        self.create_account()

        response = self.lookup("  Buyer@Example.Test ")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"kind": "EMAIL", "exists": True})

    def test_unknown_email_reports_not_exists(self):
        response = self.lookup("nobody@example.test")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"kind": "EMAIL", "exists": False})

    def test_existing_phone_is_normalized_and_reported(self):
        self.create_account(email=None, phone="+447700900123")

        response = self.lookup("+44 7700-900123")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"kind": "PHONE", "exists": True})

    def test_disabled_account_still_reads_as_exists(self):
        """禁用账号不额外暴露「存在但被禁用」，交给登录接口报禁用。"""

        self.create_account(status=BuyerAccount.Status.DISABLED)

        response = self.lookup("buyer@example.test")

        self.assertEqual(response.json()["exists"], True)

    def test_invalid_identifier_is_rejected(self):
        response = self.lookup("not-an-email-or-phone")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "IDENTIFIER_INVALID")

    def test_lookup_requires_csrf_token(self):
        response = self.client.post(
            LOOKUP_URL,
            data=json.dumps({"identifier": "buyer@example.test"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_lookup_is_rate_limited_even_when_account_exists(self):
        self.create_account()
        for _ in range(5):
            self.assertEqual(self.lookup("buyer@example.test").status_code, 200)

        response = self.lookup("buyer@example.test")

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["error"]["code"], "IDENTIFIER_LOOKUP_RATE_LIMITED")
