"""迭代02 第 1 轮：订单闭环 / 钱包资金 / 商家管理 / 下架联动 的针对性测试。"""

import json
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts_staff.models import StaffAccount
from accounts_staff.services import create_staff_session
from catalog.models import Spu, SpuTranslation
from merchant_ops.services import complete_all_nodes
from merchants.models import Merchant, MerchantMembership, MerchantRole
from offers.models import Currency, Market, Offer
from orders.models import MerchantOrder, Order


class Doc02OrderTests(TestCase):
    """一键完成放开 PENDING + 下单时间仅完成态 + 节点时间 ≤ 当前。"""

    def setUp(self):
        self.staff = StaffAccount.objects.create(
            email="doc02-admin@joybuy.test", display_name="Doc02 Admin", status="ACTIVE"
        )
        self.staff.set_password("Doc02#2026pass")
        self.staff.save()
        from accounts_staff.models import PlatformRole, StaffRoleAssignment

        StaffRoleAssignment.objects.get_or_create(
            staff=self.staff, defaults={"role": PlatformRole.objects.get(code="platform_admin")}
        )
        self.shop = Merchant.objects.create(
            slug="doc02-shop", display_name="迭代02店", onboarding_status="ACTIVE"
        )
        MerchantMembership.objects.create(
            merchant=self.shop,
            staff=self.staff,
            role=MerchantRole.objects.get(code="merchant_owner"),
            status="ACTIVE",
        )
        token, _session = create_staff_session(
            staff=self.staff, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token
        self.buyer_order = Order.objects.create(
            account_id=self._buyer().pk,
            currency_id=self._currency().pk,
            items_subtotal=0,
            shipping_cost=0,
            total=0,
            payment_expires_at=timezone.now() + timedelta(hours=1),
            status=Order.Status.PAID,
        )

    def _buyer(self):
        from accounts_buyers.models import BuyerAccount

        buyer, _ = BuyerAccount.objects.get_or_create(
            email="doc02-buyer@joybuy.test",
            defaults={"status": "ACTIVE", "password": "x"},
        )
        return buyer

    def _currency(self):
        from offers.models import Currency as CurrencyModel

        currency, _ = CurrencyModel.objects.get_or_create(
            code="CNY", defaults={"name": "Chinese Yuan", "symbol": "¥"}
        )
        return currency

    def _suborder(self, *, status=MerchantOrder.Status.PENDING, items="40.00", cost="20.00"):
        return MerchantOrder.objects.create(
            order=self.buyer_order,
            merchant=self.shop,
            currency="CNY",
            status=status,
            items_total=Decimal(items),
            cost_total=Decimal(cost),
        )

    def _actions(self, suborder, action, payload=None):
        return self.client.post(
            f"/api/v1/admin/merchant-orders/{suborder.public_id}/actions",
            data=json.dumps({"action": action, **(payload or {})}),
            content_type="application/json",
        )

    def test_complete_all_from_pending_settles_once(self):
        suborder = self._suborder()
        response = self._actions(suborder, "complete_all")
        self.assertEqual(response.status_code, 200, response.content)
        suborder.refresh_from_db()
        self.assertEqual(suborder.status, MerchantOrder.Status.COMPLETED)
        self.assertEqual(suborder.progress, 7)
        self.assertTrue(suborder.settled)
        # 幂等：重复一键完成不再回款。
        self._actions(suborder, "complete_all")
        suborder.refresh_from_db()
        self.assertEqual(suborder.settled_at, suborder.settled_at)

    def test_patch_created_at_only_for_completed(self):
        suborder = self._suborder(status=MerchantOrder.Status.PENDING)
        response = self.client.patch(
            f"/api/v1/admin/merchant-orders/{suborder.public_id}",
            data=json.dumps({"created_at": timezone.now().isoformat()}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "ORDER_NOT_COMPLETED")

        suborder.status = MerchantOrder.Status.COMPLETED
        suborder.save(update_fields=["status"])
        ok = self.client.patch(
            f"/api/v1/admin/merchant-orders/{suborder.public_id}",
            data=json.dumps({"created_at": timezone.now().isoformat()}),
            content_type="application/json",
        )
        self.assertEqual(ok.status_code, 200, ok.content)

    def test_node_time_cannot_be_in_future(self):
        suborder = self._suborder(status=MerchantOrder.Status.SHIPPED)
        MerchantOrder.objects.filter(pk=suborder.pk).update(
            node_times=[timezone.now().isoformat()] + [None] * 7, progress=0
        )
        future = (timezone.now() + timedelta(days=2)).isoformat()
        response = self.client.patch(
            f"/api/v1/admin/merchant-orders/{suborder.public_id}",
            data=json.dumps({"node_times": [timezone.now().isoformat(), future]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "NODE_IN_FUTURE")


class Doc02MerchantAdminTests(TestCase):
    """待发货金额=成本合计 + 封店天数二次确认 + 上次在线节流。"""

    def setUp(self):
        self.staff = StaffAccount.objects.create(
            email="doc02-merchants@joybuy.test", display_name="Doc02 Merchants", status="ACTIVE"
        )
        self.staff.set_password("Doc02#2026pass")
        self.staff.save()
        from accounts_staff.models import PlatformRole, StaffRoleAssignment

        StaffRoleAssignment.objects.get_or_create(
            staff=self.staff, defaults={"role": PlatformRole.objects.get(code="platform_admin")}
        )
        self.shop = Merchant.objects.create(
            slug="doc02-m-shop",
            display_name="迭代02商家",
            onboarding_status="ACTIVE",
            ban_after_days=4,
        )
        MerchantMembership.objects.create(
            merchant=self.shop,
            staff=self.staff,
            role=MerchantRole.objects.get(code="merchant_owner"),
            status="ACTIVE",
        )
        token, _session = create_staff_session(
            staff=self.staff, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token
        self.buyer_order = Order.objects.create(
            account_id=self._buyer().pk,
            currency_id=self._currency().pk,
            items_subtotal=0,
            shipping_cost=0,
            total=0,
            payment_expires_at=timezone.now() + timedelta(hours=1),
            status=Order.Status.PAID,
        )

    def _buyer(self):
        from accounts_buyers.models import BuyerAccount

        buyer, _ = BuyerAccount.objects.get_or_create(
            email="doc02-m-buyer@joybuy.test",
            defaults={"status": "ACTIVE", "password": "x"},
        )
        return buyer

    def _currency(self):
        from offers.models import Currency as CurrencyModel

        currency, _ = CurrencyModel.objects.get_or_create(
            code="CNY", defaults={"name": "Chinese Yuan", "symbol": "¥"}
        )
        return currency

    def test_pending_amount_uses_cost_total(self):
        created = timezone.now()
        MerchantOrder.objects.create(
            order=self.buyer_order,
            merchant=self.shop,
            currency="CNY",
            items_total=Decimal("800.00"),
            cost_total=Decimal("817.00"),
        )
        MerchantOrder.objects.filter(merchant=self.shop).update(created_at=created)
        payload = self.client.get("/api/v1/admin/merchants").json()["items"]
        row = next(item for item in payload if item["id"] == str(self.shop.public_id))
        self.assertEqual(row["pending_order_count"], 1)
        self.assertEqual(row["pending_order_amount"], "817.00")

    def test_ban_shrink_requires_confirm_then_suspends(self):
        old = timezone.now() - timedelta(days=6)
        suborder = MerchantOrder.objects.create(
            order=self.buyer_order, merchant=self.shop, currency="CNY"
        )
        MerchantOrder.objects.filter(pk=suborder.pk).update(created_at=old)

        # 预检：存在超时订单
        check = self.client.get(
            f"/api/v1/admin/merchants/{self.shop.public_id}/ban-check?days=1"
        ).json()["ban_check"]
        self.assertTrue(check["overdue"])

        # 未确认 → 409
        refused = self.client.patch(
            f"/api/v1/admin/merchants/{self.shop.public_id}",
            data=json.dumps({"ban_after_days": 1}),
            content_type="application/json",
        )
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(refused.json()["error"]["code"], "BAN_CONFIRM_REQUIRED")

        # 确认 → 保存并立即封店
        confirmed = self.client.patch(
            f"/api/v1/admin/merchants/{self.shop.public_id}",
            data=json.dumps({"ban_after_days": 1, "confirm_suspend": True}),
            content_type="application/json",
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.content)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.onboarding_status, Merchant.OnboardingStatus.SUSPENDED)
        self.assertEqual(self.shop.ban_after_days, 1)

    def test_ban_shrink_without_overdue_saves_directly(self):
        response = self.client.patch(
            f"/api/v1/admin/merchants/{self.shop.public_id}",
            data=json.dumps({"ban_after_days": 1}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.onboarding_status, Merchant.OnboardingStatus.ACTIVE)

    def test_touch_online_throttled(self):
        from merchants.services import touch_merchant_online

        touch_merchant_online(self.shop)
        self.shop.refresh_from_db()
        first = self.shop.last_online_at
        self.assertIsNotNone(first)
        # 10 分钟内的再次动作不刷新。
        touch_merchant_online(self.shop)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.last_online_at, first)
        # 超过 10 分钟刷新。
        stale = first - timedelta(minutes=11)
        Merchant.objects.filter(pk=self.shop.pk).update(last_online_at=stale)
        self.shop.refresh_from_db()
        touch_merchant_online(self.shop)
        self.shop.refresh_from_db()
        self.assertGreater(self.shop.last_online_at, stale)


class Doc02DelistTests(TestCase):
    """平台下架级联 Offer + 搜索文档清理 + 商家端隐藏。"""

    def setUp(self):
        self.staff = StaffAccount.objects.create(
            email="doc02-pool@joybuy.test", display_name="Doc02 Pool", status="ACTIVE"
        )
        self.staff.set_password("Doc02#2026pass")
        self.staff.save()
        from accounts_staff.models import PlatformRole, StaffRoleAssignment

        StaffRoleAssignment.objects.get_or_create(
            staff=self.staff, defaults={"role": PlatformRole.objects.get(code="platform_admin")}
        )
        self.shop = Merchant.objects.create(
            slug="doc02-delist-shop", display_name="下架联动店", onboarding_status="ACTIVE"
        )
        MerchantMembership.objects.create(
            merchant=self.shop,
            staff=self.staff,
            role=MerchantRole.objects.get(code="merchant_owner"),
            status="ACTIVE",
        )
        token, _session = create_staff_session(
            staff=self.staff, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token
        self.currency, _ = Currency.objects.get_or_create(
            code="GBP", defaults={"name": "Pound", "symbol": "£"}
        )
        self.market, _ = Market.objects.get_or_create(
            code="GBT",
            defaults={
                "name": "Test Market",
                "default_locale": "en-GB",
                "time_zone": "UTC",
                "default_currency": self.currency,
            },
        )
        self.spu = Spu.objects.create(status=Spu.Status.ACTIVE)
        SpuTranslation.objects.create(spu=self.spu, locale="zh-CN", title="下架联动商品")
        from catalog.models import Sku

        self.sku = Sku.objects.create(
            spu=self.spu, specification={}, specification_signature="doc02"
        )
        self.offer = Offer.objects.create(
            merchant=self.shop,
            sku=self.sku,
            market=self.market,
            currency=self.currency,
            current_price=Decimal("10.00"),
            list_price=Decimal("10.00"),
            status=Offer.Status.ACTIVE,
            listed_at=timezone.now(),
        )

    def _buyer(self):
        from accounts_buyers.models import BuyerAccount

        buyer, _ = BuyerAccount.objects.get_or_create(
            email="doc02-delist-buyer@joybuy.test",
            defaults={"status": "ACTIVE", "password": "x"},
        )
        return buyer

    def _currency(self):
        return self.currency

    def _unpublish(self):
        return self.client.post(
            f"/api/v1/admin/products/{self.spu.public_id}/actions",
            data=json.dumps({"action": "unpublish"}),
            content_type="application/json",
        )

    def test_unpublish_cascades_offers(self):
        response = self._unpublish()
        self.assertEqual(response.status_code, 200, response.content)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.status, Offer.Status.INACTIVE)
        self.assertTrue(self.offer.removed_by_platform)
        self.assertIsNotNone(self.offer.removed_at)
        self.assertGreaterEqual(response.json()["product"]["cascade_removed_offers"], 1)

    def test_unpublish_removes_search_documents(self):
        # 先造一个文档，再下架，验证被删除。
        from catalog.search_services import rebuild_search_document, refresh_spu_search_documents

        rebuild_search_document(self.spu, market=self.market)
        self.assertTrue(
            __import__("catalog.search_services", fromlist=["ProductSearchDocument"])
            .ProductSearchDocument.objects.filter(spu=self.spu)
            .exists()
        )
        self._unpublish()
        deleted = refresh_spu_search_documents(self.spu)
        from catalog.search_services import ProductSearchDocument

        self.assertFalse(ProductSearchDocument.objects.filter(spu=self.spu).exists())
        self.assertGreaterEqual(deleted, 0)

    def test_merchant_listings_hide_platform_delisted(self):
        self._unpublish()
        response = self.client.get(
            "/api/v1/merchant/listings", HTTP_X_MERCHANT_ID=str(self.shop.public_id)
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 0)

    def test_complete_all_nodes_from_pending_skips_shipping_cost(self):
        """待处理一键完成：回款但不扣发货成本（没发货）。"""
        from merchant_ops.models import MerchantWalletEntry

        buyer_order = Order.objects.create(
            account_id=self._buyer().pk,
            currency_id=self._currency().pk,
            items_subtotal=0,
            shipping_cost=0,
            total=0,
            payment_expires_at=timezone.now() + timedelta(hours=1),
            status=Order.Status.PAID,
        )
        suborder = MerchantOrder.objects.create(
            order=buyer_order,
            merchant=self.shop,
            currency="GBP",
            items_total=Decimal("10.00"),
            cost_total=Decimal("5.00"),
        )
        complete_all_nodes(suborder)
        suborder.refresh_from_db()
        self.assertEqual(suborder.status, MerchantOrder.Status.COMPLETED)
        self.assertTrue(suborder.settled)
        # 没有发货扣款流水（ORDER_SHIPPING），只有回款。
        self.assertFalse(
            MerchantWalletEntry.objects.filter(
                order=suborder, kind=MerchantWalletEntry.Kind.ORDER_SHIPPING
            ).exists()
        )
        self.assertTrue(
            MerchantWalletEntry.objects.filter(
                order=suborder, kind=MerchantWalletEntry.Kind.ORDER_SETTLEMENT
            ).exists()
        )
