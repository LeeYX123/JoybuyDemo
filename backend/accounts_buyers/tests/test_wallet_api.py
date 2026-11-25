import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts_buyers.models import BuyerAccount, BuyerWalletEntry
from accounts_buyers.services import create_buyer_session


class BuyerWalletApiTests(TestCase):
    """GET /api/v1/buyer/wallet：只读余额 + 流水（充值仍在管理端，买家侧无写路径）。"""

    def setUp(self):
        self.account, _ = BuyerAccount.objects.get_or_create(
            email="wallet@joybuy.test",
            defaults={"status": BuyerAccount.Status.ACTIVE, "balance": "88.50"},
        )
        token, _session = create_buyer_session(
            account=self.account, ip_address="127.0.0.1", user_agent="test-agent"
        )
        self.client.cookies["joybuy_buyer_session"] = token
        self.url = reverse("buyer-wallet")

    def _add_entry(self, kind, amount, occurred_at=None, note=""):
        return BuyerWalletEntry.objects.create(
            account=self.account,
            kind=kind,
            amount=amount,
            balance_before="0",
            balance_after=amount,
            occurred_at=occurred_at or timezone.now(),
            note=note,
        )

    def test_returns_balance_and_entries_newest_first(self):
        old = self._add_entry(
            BuyerWalletEntry.Kind.RECHARGE,
            "100.00",
            occurred_at=timezone.now() - datetime.timedelta(days=2),
            note="充值",
        )
        new = self._add_entry(BuyerWalletEntry.Kind.PURCHASE, "-11.50")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["balance"], "88.5000")
        self.assertEqual(payload["total"], 2)
        self.assertEqual([entry["public_id"] for entry in payload["entries"]], [
            str(new.public_id),
            str(old.public_id),
        ])
        self.assertEqual(payload["entries"][0]["amount"], "-11.5000")
        self.assertEqual(payload["entries"][0]["kind"], BuyerWalletEntry.Kind.PURCHASE)

    def test_pagination(self):
        for index in range(25):
            self._add_entry(
                BuyerWalletEntry.Kind.RECHARGE,
                "1.00",
                occurred_at=timezone.now() - datetime.timedelta(minutes=index),
            )
        page_one = self.client.get(self.url).json()
        self.assertEqual(page_one["total"], 25)
        self.assertEqual(page_one["total_pages"], 2)
        self.assertEqual(len(page_one["entries"]), 20)
        page_two = self.client.get(f"{self.url}?page=2").json()
        self.assertEqual(len(page_two["entries"]), 5)

    def test_anonymous_requests_require_sign_in(self):
        self.client.cookies.clear()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "AUTH_REQUIRED")

    def test_post_is_rejected(self):
        response = self.client.post(self.url, data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 405)
