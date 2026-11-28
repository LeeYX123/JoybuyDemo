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

    def _create(
        self,
        *,
        quantity=1,
        trigger_minutes=1,
        account=None,
        offer=None,
        balance=None,
        payment_method=None,
    ):
        account = account or self.buyer
        offer = offer or self.offer
        if balance is not None:
            BuyerAccount.objects.filter(pk=account.pk).update(balance=Decimal(str(balance)))
            account.refresh_from_db()
        trigger = timezone.now() + timedelta(minutes=trigger_minutes)
        payload = {
            "account_id": str(account.public_id),
            "merchant_id": str(self.shop.public_id),
            "offer_id": str(offer.public_id),
            "quantity": quantity,
            "trigger_at": trigger.isoformat(),
        }
        # 2026-11-29：支付方式可选；None = 不传（走服务层默认余额支付）。
        if payment_method is not None:
            payload["payment_method"] = payment_method
        return self.client.post(
            "/api/v1/admin/auto-orders",
            data=json.dumps(payload),
            content_type="application/json",
        )


class AutoOrderCreateTests(AutoOrderBase):
    def test_create_task_allowed_when_balance_insufficient(self):
        # 2026-11-28 用户拍板「不扣除余额」：余额不足也能创建任务
        # （与 place_order 的 BALANCE 口径一致——只记录支付方式）。
        response = self._create(quantity=1, balance="5.00")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(AutoOrderTask.objects.exists())

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

    def test_options_support_server_side_pagination(self):
        # 2026-11-28 向导【选商品】改版：卡片区服务端分页（不再 30 条截断）。
        for index in range(4):
            spu = Spu.objects.create(status=Spu.Status.ACTIVE)
            SpuTranslation.objects.create(spu=spu, locale="zh-CN", title=f"分页商品 {index}")
            sku = Sku.objects.create(
                spu=spu, specification={"序号": str(index)}, specification_signature=f"pg{index}"
            )
            Offer.objects.create(
                merchant=self.shop,
                sku=sku,
                market=self.market,
                currency=self.currency,
                current_price=Decimal("10.00"),
                cost_price=Decimal("5.00"),
                local_inventory=10,
                status=Offer.Status.ACTIVE,
                listed_at=timezone.now(),
            )
        base = f"/api/v1/admin/auto-orders/options?merchant_id={self.shop.public_id}&page_size=2"
        first = self.client.get(f"{base}&page=1").json()
        second = self.client.get(f"{base}&page=2").json()
        self.assertEqual(first["total"], 5)
        self.assertEqual(len(first["items"]), 2)
        self.assertTrue(first["has_next"])
        self.assertEqual(len(second["items"]), 2)
        self.assertTrue(second["has_next"])
        third = self.client.get(f"{base}&page=3").json()
        self.assertEqual(len(third["items"]), 1)
        self.assertFalse(third["has_next"])

    def test_options_q_filters_by_title_and_partial_uuid(self):
        # 搜索词与卡片列表共用同一数据源：标题与部分 UUID 都能命中。
        by_title = self.client.get(
            f"/api/v1/admin/auto-orders/options?merchant_id={self.shop.public_id}&q=定时商品"
        ).json()
        self.assertEqual(len(by_title["items"]), 1)
        prefix = str(self.spu.public_id)[:8]
        by_uuid = self.client.get(
            f"/api/v1/admin/auto-orders/options?merchant_id={self.shop.public_id}&q={prefix}"
        ).json()
        self.assertEqual(len(by_uuid["items"]), 1)
        self.assertEqual(by_uuid["items"][0]["id"], str(self.spu.public_id))


class AutoOrderPaymentMethodTests(AutoOrderBase):
    """2026-11-29：一键下单新增支付方式（默认余额，可选购物端支持的支付方式）。"""

    def test_create_defaults_to_balance_when_omitted(self):
        # 旧调用方不传 payment_method 时不炸，落库为 BALANCE（与改造前行为一致）。
        response = self._create()
        self.assertEqual(response.status_code, 201, response.content)
        task = AutoOrderTask.objects.get()
        self.assertEqual(task.payment_method, "BALANCE")
        self.assertEqual(response.json()["task"]["payment_method"], "BALANCE")
        self.assertEqual(response.json()["task"]["payment_method_label"], "余额支付")

    def test_create_persists_selected_payment_method(self):
        response = self._create(payment_method="PAYPAL")
        self.assertEqual(response.status_code, 201, response.content)
        task = AutoOrderTask.objects.get()
        self.assertEqual(task.payment_method, "PAYPAL")
        body = response.json()["task"]
        self.assertEqual(body["payment_method"], "PAYPAL")
        self.assertEqual(body["payment_method_label"], "PayPal")
        self.assertEqual(body["payment_method_label_en"], "PayPal")

    def test_create_rejects_invalid_payment_method(self):
        response = self._create(payment_method="BITCOIN")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"]["code"], "PAYMENT_METHOD_INVALID")
        self.assertIn("支付方式", response.json()["error"]["message"])
        self.assertFalse(AutoOrderTask.objects.exists())

    def test_create_accepts_card_brand(self):
        response = self._create(payment_method="unionpay")
        self.assertEqual(response.status_code, 201, response.content)
        task = AutoOrderTask.objects.get()
        # 小写也归一化为枚举大写值。
        self.assertEqual(task.payment_method, "UNIONPAY")
        self.assertEqual(response.json()["task"]["payment_method_label"], "银联")

    def test_list_and_detail_payload_carry_payment_method(self):
        self._create(payment_method="KLARNA")
        listing = self.client.get("/api/v1/admin/auto-orders?status=ALL").json()
        row = listing["items"][0]
        self.assertEqual(row["payment_method"], "KLARNA")
        self.assertEqual(row["payment_method_label"], "Klarna")
        self.assertEqual(row["payment_method_label_en"], "Klarna")

    def test_executed_order_uses_task_payment_method(self):
        # 覆盖 BALANCE / VISA / PAYPAL / KLARNA 四个代表值：
        # 到点执行生成的订单与商家子单都记录任务所选支付方式。
        from orders.auto_order_services import execute_due_auto_orders

        for method in ("BALANCE", "VISA", "PAYPAL", "KLARNA"):
            AutoOrderTask.objects.all().delete()
            task = AutoOrderTask.objects.create(
                account=self.buyer,
                merchant=self.shop,
                offer=self.offer,
                product_title="R3 定时商品",
                specification={"颜色": "黑"},
                quantity=1,
                unit_price=Decimal("20.00"),
                payment_method=method,
                trigger_at=timezone.now() - timedelta(minutes=1),
            )
            result = execute_due_auto_orders()
            self.assertEqual(result["executed"], 1, method)
            task.refresh_from_db()
            self.assertEqual(task.status, AutoOrderTask.Status.EXECUTED, method)
            order = Order.objects.get(auto_order_tasks=task)
            self.assertEqual(order.payment_method, method)
            sub = MerchantOrder.objects.get(order=order)
            self.assertEqual(sub.payment_method, method)
            # 余额支付仍不校验/不扣款（2026-11-28 口径不变）。
            self.buyer.refresh_from_db()
            self.assertEqual(self.buyer.balance, Decimal("500.00"))


class AutoOrderExecuteTests(AutoOrderBase):
    def test_due_task_places_order_without_deducting_balance(self):
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
        # 2026-11-28 用户拍板「不扣除余额」：执行后买家余额不变。
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.balance, Decimal("500.00"))
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

    def test_task_executes_when_balance_insufficient(self):
        # 2026-11-28 用户拍板「不扣除余额」：余额不足不再让任务失败。
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

        result = execute_due_auto_orders()
        self.assertEqual(result["executed"], 1)
        task.refresh_from_db()
        self.assertEqual(task.status, AutoOrderTask.Status.EXECUTED)
        self.assertTrue(Order.objects.filter(auto_order_tasks=task).exists())
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.balance, Decimal("1.00"))

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
