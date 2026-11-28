"""管理端可搜索下拉框（2026-11-28）的后端搜索测试。

覆盖两件事：
1. 各实体选择框数据源的 ``q`` 同时匹配名称与编号（JYM/JYU 整号或部分号，
   商品为 SPU UUID 整号/部分号）——这是「按 ID 和名称都能查」的契约；
2. 新增的 ``GET /api/v1/admin/offers`` 报价搜索端点（库存调整表单数据源）。
"""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts_buyers.models import BuyerAccount
from accounts_staff.models import (
    PlatformPermission,
    PlatformRole,
    StaffAccount,
    StaffRoleAssignment,
)
from accounts_staff.services import create_staff_session
from catalog.models import Spu, SpuTranslation
from merchant_ops.models import AfterSale, SupportConversation
from merchants.models import Merchant
from offers.models import Currency, Market, Offer
from orders.models import MerchantOrder, Order

PICKER_PERMISSIONS = (
    "merchants.view",
    "merchants.growth.view",
    "buyers.view",
    "whitelist.view",
    "catalog.pool.view",
    "catalog.listings.view",
    "notifications.view",
    "finance.view",
    "deposits.view",
    "orders.view",
    "offers.manage",
    "support.view",
    "aftersales.view",
)


class PickerSearchTestBase(TestCase):
    def setUp(self):
        self.currency = Currency.objects.get(code="GBP")
        self.market = Market.objects.get(code="GB")
        role, _ = PlatformRole.objects.update_or_create(
            code="role-picker-search",
            defaults={"name": "Picker test role", "is_system": False},
        )
        permissions = []
        for code in PICKER_PERMISSIONS:
            permission, _ = PlatformPermission.objects.get_or_create(
                code=code, defaults={"name": code}
            )
            permissions.append(permission)
        role.permissions.set(permissions)
        self.staff, _ = StaffAccount.objects.get_or_create(
            email="picker@joybuy.test",
            defaults={
                "display_name": "搜索测试管理员",
                "password": "x",
                "status": StaffAccount.Status.ACTIVE,
            },
        )
        StaffRoleAssignment.objects.get_or_create(staff=self.staff, role=role)
        token, _session = create_staff_session(
            staff=self.staff, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token

        # 固定编号商家，便于断言「部分编号命中」。
        self.merchant = Merchant.objects.create(
            slug="picker-demo-store",
            display_name="演示杂货铺",
            public_id="JYMPICKER100",
            onboarding_status=Merchant.OnboardingStatus.ACTIVE,
        )

    def make_spu(self, title="演示商品"):
        spu = Spu.objects.create(status=Spu.Status.ACTIVE, retail_price=Decimal("20.00"))
        SpuTranslation.objects.create(spu=spu, locale="zh-CN", title=title)
        return spu

    def make_offer(self, spu, *, status=Offer.Status.ACTIVE):
        sku = spu.skus.create(specification={"颜色": "黑"}, specification_signature="color-black")
        return Offer.objects.create(
            merchant=self.merchant,
            sku=sku,
            market=self.market,
            currency=self.currency,
            current_price=Decimal("20.00"),
            local_inventory=100,
            status=status,
            listed_at=timezone.now(),
        )


class MerchantPickerSearchTests(PickerSearchTestBase):
    def test_merchants_list_q_matches_partial_public_id(self):
        response = self.client.get("/api/v1/admin/merchants?q=PICKER10")
        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.json()["items"]]
        self.assertIn("JYMPICKER100", ids)

    def test_merchants_list_q_matches_full_public_id_case_insensitive(self):
        response = self.client.get("/api/v1/admin/merchants?q=jympicker100")
        self.assertEqual(response.status_code, 200)
        self.assertIn("JYMPICKER100", [item["id"] for item in response.json()["items"]])

    def test_merchant_options_q_matches_public_id(self):
        response = self.client.get("/api/v1/admin/merchant-options?q=PICKER10")
        self.assertEqual(response.status_code, 200)
        self.assertIn("JYMPICKER100", [item["id"] for item in response.json()["items"]])

    def test_finance_merchants_q_matches_public_id(self):
        response = self.client.get("/api/v1/admin/finance/merchants?q=PICKER10")
        self.assertEqual(response.status_code, 200)
        self.assertIn("JYMPICKER100", [item["id"] for item in response.json()["items"]])

    def test_deposits_q_matches_public_id(self):
        self.merchant.deposit_enabled = True
        self.merchant.save()
        response = self.client.get("/api/v1/admin/deposits?q=PICKER10")
        self.assertEqual(response.status_code, 200)
        self.assertIn("JYMPICKER100", [item["id"] for item in response.json()["items"]])

    def test_growth_q_matches_public_id(self):
        response = self.client.get("/api/v1/admin/growth?q=PICKER10")
        self.assertEqual(response.status_code, 200)
        self.assertIn("JYMPICKER100", [item["id"] for item in response.json()["items"]])


class BuyerPickerSearchTests(PickerSearchTestBase):
    def test_buyers_q_matches_partial_public_id(self):
        buyer = BuyerAccount.objects.create(
            email="picker-buyer@joybuy.test", password="x", public_id="JYUPICKER100"
        )
        response = self.client.get("/api/v1/admin/buyers/accounts?q=PICKER10")
        self.assertEqual(response.status_code, 200)
        self.assertIn(str(buyer.public_id), [item["id"] for item in response.json()["items"]])


class ProductPickerSearchTests(PickerSearchTestBase):
    def test_product_pool_q_matches_partial_uuid(self):
        spu = self.make_spu(title="Picker 演示商品")
        prefix = str(spu.public_id)[:8]
        response = self.client.get(f"/api/v1/admin/products?q={prefix}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(str(spu.public_id), [item["id"] for item in response.json()["items"]])

    def test_auto_order_options_q_matches_partial_spu_uuid(self):
        spu = self.make_spu(title="Auto 演示商品")
        self.make_offer(spu)
        prefix = str(spu.public_id)[:8]
        response = self.client.get(
            f"/api/v1/admin/auto-orders/options?merchant_id=JYMPICKER100&q={prefix}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(str(spu.public_id), [item["id"] for item in response.json()["items"]])

    def test_offer_search_q_matches_partial_uuid(self):
        spu = self.make_spu(title="Offer 演示商品")
        offer = self.make_offer(spu)
        prefix = str(offer.public_id)[:8]
        response = self.client.get(f"/api/v1/admin/offers?q={prefix}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn(str(offer.public_id), [item["id"] for item in payload["items"]])
        row = next(item for item in payload["items"] if item["id"] == str(offer.public_id))
        self.assertEqual(row["product"]["id"], str(spu.public_id))
        self.assertEqual(row["merchant"]["id"], "JYMPICKER100")
        # 分页元数据存在（AppPicker「加载更多」依赖 has_next）。
        self.assertIn("has_next", payload)

    def test_offer_search_q_matches_merchant_name_and_id(self):
        spu = self.make_spu(title="Offer 演示商品二")
        offer = self.make_offer(spu)
        by_name = self.client.get("/api/v1/admin/offers?q=演示杂货铺")
        self.assertIn(
            str(offer.public_id), [item["id"] for item in by_name.json()["items"]]
        )
        by_id = self.client.get("/api/v1/admin/offers?q=PICKER10")
        self.assertIn(
            str(offer.public_id), [item["id"] for item in by_id.json()["items"]]
        )

    def test_offer_search_requires_permission(self):
        role, _ = PlatformRole.objects.update_or_create(
            code="role-picker-nobody", defaults={"name": "Nobody", "is_system": False}
        )
        role.permissions.set([])
        staff, _ = StaffAccount.objects.get_or_create(
            email="picker-nobody@joybuy.test",
            defaults={
                "display_name": "无权限",
                "password": "x",
                "status": StaffAccount.Status.ACTIVE,
            },
        )
        StaffRoleAssignment.objects.get_or_create(staff=staff, role=role)
        token, _session = create_staff_session(
            staff=staff, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token
        response = self.client.get("/api/v1/admin/offers")
        self.assertEqual(response.status_code, 403)


class OrderPickerSearchTests(PickerSearchTestBase):
    def _make_completed_order(self):
        spu = self.make_spu(title="订单演示商品")
        self.make_offer(spu)
        buyer = BuyerAccount.objects.create(email="order-buyer@joybuy.test", password="x")
        order = Order.objects.create(
            account=buyer,
            currency=self.currency,
            items_subtotal=Decimal("20.00"),
            shipping_cost=Decimal("0"),
            total=Decimal("20.00"),
            shipping_address={"region": "London"},
            payment_expires_at=timezone.now() + timedelta(hours=1),
        )
        merchant_order = MerchantOrder.objects.create(
            order=order,
            merchant=self.merchant,
            currency=self.currency.code,
            items_total=Decimal("20.00"),
            cost_total=Decimal("10.00"),
            status=MerchantOrder.Status.COMPLETED,
            settled_at=timezone.now(),
        )
        return merchant_order

    def test_notification_orders_q_matches_partial_uuid(self):
        merchant_order = self._make_completed_order()
        prefix = str(merchant_order.public_id)[:8]
        response = self.client.get(
            f"/api/v1/admin/notifications/orders?merchant_id=JYMPICKER100&q={prefix}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            str(merchant_order.public_id), [item["id"] for item in response.json()["items"]]
        )

    def test_auto_orders_list_q_matches_merchant_public_id(self):
        from orders.models import AutoOrderTask

        buyer = BuyerAccount.objects.create(email="auto-buyer@joybuy.test", password="x")
        spu = self.make_spu(title="Auto 列表演示商品")
        offer = self.make_offer(spu)
        AutoOrderTask.objects.create(
            account=buyer,
            merchant=self.merchant,
            offer=offer,
            product_title="Auto 列表演示商品",
            quantity=1,
            trigger_at=timezone.now() + timedelta(hours=1),
        )
        response = self.client.get("/api/v1/admin/auto-orders?q=PICKER10")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["items"])

    def test_after_sales_q_matches_merchant_public_id(self):
        buyer = BuyerAccount.objects.create(email="as-buyer@joybuy.test", password="x")
        order = Order.objects.create(
            account=buyer,
            currency=self.currency,
            items_subtotal=Decimal("20.00"),
            shipping_cost=Decimal("0"),
            total=Decimal("20.00"),
            shipping_address={"region": "London"},
            payment_expires_at=timezone.now() + timedelta(hours=1),
        )
        AfterSale.objects.create(
            merchant=self.merchant,
            order=order,
            kind=AfterSale.Kind.COMPLAINT,
            state=AfterSale.State.PENDING,
            issue="测试投诉",
        )
        response = self.client.get("/api/v1/admin/after-sales?q=PICKER10")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["items"])

    def test_support_conversations_q_matches_merchant_public_id(self):
        SupportConversation.objects.create(
            merchant=self.merchant,
            kind=SupportConversation.Kind.PLATFORM_SUPPORT,
            state=SupportConversation.State.PENDING,
        )
        response = self.client.get("/api/v1/admin/support/conversations?q=PICKER10")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["items"])


class NotificationsMerchantPickerTests(PickerSearchTestBase):
    def test_notification_merchants_q_matches_public_id(self):
        response = self.client.get("/api/v1/admin/notifications/merchants?q=PICKER10")
        self.assertEqual(response.status_code, 200)
        self.assertIn("JYMPICKER100", [item["id"] for item in response.json()["items"]])

    def test_notification_merchants_exclude_import_fallback_and_draft(self):
        Merchant.objects.create(
            slug="fallback-store",
            display_name="兜底店铺",
            public_id="JYMFALLBACK1",
            merchant_type=Merchant.Type.IMPORT_FALLBACK,
        )
        Merchant.objects.create(
            slug="draft-store",
            display_name="草稿店铺",
            public_id="JYMDRAFT0001",
            onboarding_status=Merchant.OnboardingStatus.DRAFT,
        )
        response = self.client.get("/api/v1/admin/notifications/merchants?q=FALL")
        ids = [item["id"] for item in response.json()["items"]]
        self.assertNotIn("JYMFALLBACK1", ids)
        response = self.client.get("/api/v1/admin/notifications/merchants?q=DRAFT00")
        ids = [item["id"] for item in response.json()["items"]]
        self.assertNotIn("JYMDRAFT0001", ids)
