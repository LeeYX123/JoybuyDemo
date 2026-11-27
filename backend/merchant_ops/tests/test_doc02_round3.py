"""迭代02 第 3 轮：一键下单任务（创建校验/到点执行/取消）+ 时区展示。"""

import json
from datetime import timedelta
from decimal import Decimal

from django.test import Client, TestCase
from django.utils import timezone

from accounts_buyers.models import BuyerAccount
from accounts_staff.models import PlatformRole, StaffAccount, StaffRoleAssignment
from catalog.models import Sku, Spu, SpuTranslation
from checkout.models import Address
from merchants.models import Merchant
from offers.models import Currency, Market, Offer
from orders.models import AutoOrderTask, MerchantOrder, Order


class AutoOrderBase(TestCase):
    def setUp(self):
        self.staff = StaffAccount.objects.create(
            email="r3-admin@joybuy.test", display_name="R3 Admin", status="ACTIVE"
        )
        self.staff.set_password("R3#Admin2026")
        self.staff.save()
        StaffRoleAssignment.objects.get_or_create(
            staff=self.staff, defaults={"role": PlatformRole.objects.get(code="platform_admin")}
        )
        from accounts_staff.services import create_staff_session

        token, _session = create_staff_session(
            staff=self.staff, ip_address="127.0.0.1", user_agent="t", totp_verified=True
        )
        self.client = Client()
        self.client.cookies["joybuy_staff_session"] = token

        self.buyer = BuyerAccount.objects.create(
            email="r3-buyer@joybuy.test",
            password="x",
            status="ACTIVE",
            balance=Decimal("500.00"),
            purchase_whitelisted=True,
        )
        self.address = Address.objects.create(
            account=self.buyer,
            full_name="R3",
            phone="+447000000008",
            line1="1 Auto Street",
            city="London",
            postcode="SW1A 1AA",
        )
        self.shop = Merchant.objects.create(
            slug="r3-shop", display_name="R3 店", onboarding_status="ACTIVE"
        )
        self.currency, _ = Currency.objects.get_or_create(
            code="GBP", defaults={"name": "Pound", "symbol": "£"}
        )
        self.market, _ = Market.objects.get_or_create(
            code="G3",
            defaults={
                "name": "R3 Market",
                "default_locale": "en-GB",
                "time_zone": "UTC",
                "default_currency": self.currency,
            },
        )
        self.spu = Spu.objects.create(status=Spu.Status.ACTIVE)
        SpuTranslation.objects.create(spu=self.spu, locale="zh-CN", title="R3 定时商品")
        self.sku = Sku.objects.create(
            spu=self.spu,
            specification={"颜色": "黑"},
            specification_signature="r3",
        )
        self.offer = Offer.objects.create(
            merchant=self.shop,
            sku=self.sku,
            market=self.market,
            currency=self.currency,
            current_price=Decimal("20.00"),
            list_price=Decimal("20.00"),
            cost_price=Decimal("8.00"),
            local_inventory=50,
            status=Offer.Status.ACTIVE,
            listed_at=timezone.now(),
        )

    def _create(self, *, quantity=1, trigger_minutes=1, account=None, offer=None, balance=None):
        account = account or self.buyer
        offer = offer or self.offer
        if balance is not None:
            BuyerAccount.objects.filter(pk=account.pk).update(balance=Decimal(str(balance)))
            account.refresh_from_db()
        trigger = timezone.now() + timedelta(minutes=trigger_minutes)
        return self.client.post(
            "/api/v1/admin/auto-orders",
            data=json.dumps(
                {
                    "account_id": str(account.public_id),
                    "merchant_id": str(self.shop.public_id),
                    "offer_id": str(offer.public_id),
                    "quantity": quantity,
                    "trigger_at": trigger.isoformat(),
                }
            ),
            content_type="application/json",
        )


class AutoOrderCreateTests(AutoOrderBase):
    def test_create_task_rejected_when_balance_insufficient(self):
        # 迭代02 反馈：创建时余额不足直接拒绝并提醒，不生成任务。
        response = self._create(quantity=1, balance="5.00")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"]["code"], "BALANCE_INSUFFICIENT")
        self.assertIn("余额不足", response.json()["error"]["message"])
        self.assertFalse(AutoOrderTask.objects.exists())

    def test_create_rejects_non_whitelisted(self):
        BuyerAccount.objects.filter(pk=self.buyer.pk).update(purchase_whitelisted=False)
        response = self._create()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "ACCOUNT_NOT_WHITELISTED")

    def test_create_rejects_payment_disabled(self):
        # 2026-11-27 管理端编辑关闭支付权限：不能创建自动下单任务。
        BuyerAccount.objects.filter(pk=self.buyer.pk).update(payment_enabled=False)
        response = self._create()
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"]["code"], "PAYMENT_DISABLED")
        self.assertFalse(AutoOrderTask.objects.exists())

    def test_create_rejects_invalid_offer(self):
        Offer.objects.filter(pk=self.offer.pk).update(status=Offer.Status.INACTIVE)
        response = self._create()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "OFFER_INVALID")
        self.assertIn("失效", response.json()["error"]["message"])

    def test_options_only_show_active_products(self):
        response = self.client.get(
            f"/api/v1/admin/auto-orders/options?merchant_id={self.shop.public_id}"
        )
        self.assertEqual(response.status_code, 200, response.content)
        items = response.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["offers"][0]["specification"], {"颜色": "黑"})

        # 平台下架后不再展示
        Spu.objects.filter(pk=self.spu.pk).update(status=Spu.Status.INACTIVE)
        response = self.client.get(
            f"/api/v1/admin/auto-orders/options?merchant_id={self.shop.public_id}"
        )
        self.assertEqual(response.json()["items"], [])


class AutoOrderExecuteTests(AutoOrderBase):
    def test_due_task_places_order_and_deducts_balance(self):
        trigger = timezone.now() - timedelta(minutes=1)
        task = AutoOrderTask.objects.create(
            account=self.buyer,
            merchant=self.shop,
            offer=self.offer,
            product_title="R3 定时商品",
            specification={"颜色": "黑"},
            quantity=2,
            unit_price=Decimal("20.00"),
            trigger_at=trigger,
        )
        from orders.auto_order_services import execute_due_auto_orders

        result = execute_due_auto_orders()
        self.assertEqual(result["executed"], 1)
        task.refresh_from_db()
        self.assertEqual(task.status, AutoOrderTask.Status.EXECUTED)
        self.assertIsNotNone(task.executed_order)
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.balance, Decimal("460.00"))
        # 商家端正常生成待处理子单
        self.assertTrue(
            MerchantOrder.objects.filter(order=task.executed_order, merchant=self.shop).exists()
        )

    def test_task_fails_when_offer_invalid_at_trigger(self):
        trigger = timezone.now() - timedelta(minutes=1)
        task = AutoOrderTask.objects.create(
            account=self.buyer,
            merchant=self.shop,
            offer=self.offer,
            quantity=1,
            trigger_at=trigger,
        )
        Offer.objects.filter(pk=self.offer.pk).update(status=Offer.Status.INACTIVE)
        from orders.auto_order_services import execute_due_auto_orders

        execute_due_auto_orders()
        task.refresh_from_db()
        self.assertEqual(task.status, AutoOrderTask.Status.FAILED)
        self.assertIn("失效", task.failure_reason)

    def test_task_fails_when_balance_insufficient(self):
        trigger = timezone.now() - timedelta(minutes=1)
        task = AutoOrderTask.objects.create(
            account=self.buyer,
            merchant=self.shop,
            offer=self.offer,
            quantity=1,
            trigger_at=trigger,
        )
        BuyerAccount.objects.filter(pk=self.buyer.pk).update(balance=Decimal("1.00"))
        from orders.auto_order_services import execute_due_auto_orders

        execute_due_auto_orders()
        task.refresh_from_db()
        self.assertEqual(task.status, AutoOrderTask.Status.FAILED)
        self.assertIn("余额不足", task.failure_reason)
        # 没有生成订单
        self.assertFalse(Order.objects.filter(auto_order_tasks=task).exists())

    def test_task_fails_when_payment_disabled_at_trigger(self):
        trigger = timezone.now() - timedelta(minutes=1)
        task = AutoOrderTask.objects.create(
            account=self.buyer,
            merchant=self.shop,
            offer=self.offer,
            quantity=1,
            trigger_at=trigger,
        )
        BuyerAccount.objects.filter(pk=self.buyer.pk).update(payment_enabled=False)
        from orders.auto_order_services import execute_due_auto_orders

        execute_due_auto_orders()
        task.refresh_from_db()
        self.assertEqual(task.status, AutoOrderTask.Status.FAILED)
        self.assertIn("支付权限", task.failure_reason)
        self.assertFalse(Order.objects.filter(auto_order_tasks=task).exists())

    def test_task_fails_without_address(self):
        trigger = timezone.now() - timedelta(minutes=1)
        task = AutoOrderTask.objects.create(
            account=self.buyer,
            merchant=self.shop,
            offer=self.offer,
            quantity=1,
            trigger_at=trigger,
        )
        Address.objects.all().delete()
        from orders.auto_order_services import execute_due_auto_orders

        execute_due_auto_orders()
        task.refresh_from_db()
        self.assertEqual(task.status, AutoOrderTask.Status.FAILED)
        self.assertIn("地址", task.failure_reason)

    def test_cancel_pending_task(self):
        task = AutoOrderTask.objects.create(
            account=self.buyer,
            merchant=self.shop,
            offer=self.offer,
            quantity=1,
            trigger_at=timezone.now() + timedelta(hours=1),
        )
        response = self.client.post(
            f"/api/v1/admin/auto-orders/{task.public_id}/actions",
            data=json.dumps({"action": "cancel"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        task.refresh_from_db()
        self.assertEqual(task.status, AutoOrderTask.Status.CANCELED)

    def test_future_task_not_executed_early(self):
        AutoOrderTask.objects.create(
            account=self.buyer,
            merchant=self.shop,
            offer=self.offer,
            quantity=1,
            trigger_at=timezone.now() + timedelta(hours=1),
        )
        from orders.auto_order_services import execute_due_auto_orders

        result = execute_due_auto_orders()
        self.assertEqual(result["executed"], 0)


class TimezoneDisplayTests(TestCase):
    def test_iso_uses_client_timezone_header(self):
        from datetime import datetime
        from datetime import timezone as dt_timezone

        from common.client_timezone import set_client_timezone
        from merchant_ops.api_utils import iso

        value = datetime(2026, 11, 7, 12, 0, 0, tzinfo=dt_timezone.utc)
        set_client_timezone(None)
        default = iso(value)
        set_client_timezone("Asia/Shanghai")
        shanghai = iso(value)
        set_client_timezone("America/New_York")
        new_york = iso(value)
        set_client_timezone(None)
        self.assertIn("+08:00", shanghai)
        self.assertIn("20:00", shanghai)
        self.assertIn("-05:00", new_york)
        self.assertIn("07:00", new_york)
        self.assertNotEqual(default, shanghai)
