"""迭代02 第 1 轮：购物端确认收货端点（= 后台一键完成全部节点）。"""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts_buyers.models import BuyerAccount
from merchant_ops.models import MerchantWalletEntry
from merchants.models import Merchant
from orders.models import MerchantOrder, Order


class ConfirmReceiptTests(TestCase):
    def setUp(self):
        self.buyer = BuyerAccount.objects.create(
            email="confirm-receipt@joybuy.test", password="x", status="ACTIVE"
        )
        self.other = BuyerAccount.objects.create(
            email="other-buyer@joybuy.test", password="x", status="ACTIVE"
        )
        self.shop = Merchant.objects.create(
            slug="confirm-shop", display_name="确认收货店", onboarding_status="ACTIVE"
        )
        self.order = Order.objects.create(
            account=self.buyer,
            currency_id=self._currency().pk,
            items_subtotal=Decimal("20.00"),
            shipping_cost=0,
            total=Decimal("20.00"),
            payment_expires_at=timezone.now() + timedelta(hours=1),
            status=Order.Status.PAID,
            payment_method="CARD",
            paid_at=timezone.now(),
        )
        self.suborder = MerchantOrder.objects.create(
            order=self.order,
            merchant=self.shop,
            currency="CNY",
            items_total=Decimal("20.00"),
            cost_total=Decimal("12.00"),
        )

    def _currency(self):
        from offers.models import Currency as CurrencyModel

        currency, _ = CurrencyModel.objects.get_or_create(
            code="CNY", defaults={"name": "Chinese Yuan", "symbol": "¥"}
        )
        return currency

    def _client_with_session(self, account):
        from django.test import Client

        from accounts_buyers.services import create_buyer_session

        token, _session = create_buyer_session(
            account=account, ip_address="127.0.0.1", user_agent="test"
        )
        client = Client()
        client.cookies["joybuy_buyer_session"] = token
        return client

    def _post(self, account, public_id):

        client = self._client_with_session(account)
        # CSRF：测试客户端 enforce_csrf_checks 默认 False，可直接 POST。
        return client.post(f"/api/v1/orders/{public_id}/confirm-receipt")

    def test_confirm_receipt_completes_and_settles(self):
        response = self._post(self.buyer, self.order.public_id)
        self.assertEqual(response.status_code, 200, response.content)
        self.suborder.refresh_from_db()
        self.assertEqual(self.suborder.status, MerchantOrder.Status.COMPLETED)
        self.assertEqual(self.suborder.progress, 7)
        self.assertTrue(self.suborder.settled)
        self.assertTrue(
            MerchantWalletEntry.objects.filter(
                order=self.suborder, kind=MerchantWalletEntry.Kind.ORDER_SETTLEMENT
            ).exists()
        )

    def test_confirm_receipt_requires_owner(self):
        response = self._post(self.other, self.order.public_id)
        self.assertEqual(response.status_code, 404)

    def test_confirm_receipt_requires_paid(self):
        Order.objects.filter(pk=self.order.pk).update(status=Order.Status.PENDING_PAYMENT)
        response = self._post(self.buyer, self.order.public_id)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "ORDER_NOT_PAID")
