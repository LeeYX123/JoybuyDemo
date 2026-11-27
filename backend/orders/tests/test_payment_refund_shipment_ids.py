"""阶段 2：支付 / 退款 / 物流编号与业务接入测试。

覆盖：

* JYPAY / JYR / JYLOG 格式与唯一性；
* 下单即付创建 Payment（幂等）、未支付订单不创建、``attempt_payment`` 行为不变；
* 商家发货创建 Shipment（带 tracking_no），订单详情/商家详情内嵌编号；
* 存量回填行数与 paid_at / tracking_reference 非空数量一致；
* 管理端退款手动创建返回 JYR 编号，并出现在售后详情与列表里。
"""

import re
from decimal import Decimal

from django.apps import apps
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts_buyers.models import BuyerAccount
from accounts_buyers.services import create_buyer_session
from accounts_staff.models import (
    PlatformPermission,
    PlatformRole,
    StaffAccount,
    StaffRoleAssignment,
)
from accounts_staff.services import create_staff_session
from cart.models import Cart
from cart.services import add_item, resolve_cart_context, serialize_cart
from catalog.models import Spu
from catalog.product_services import get_or_create_sku_from_source, get_or_create_spu_from_source
from checkout.models import Address
from common.ids import new_public_id
from merchant_ops.models import AfterSale
from merchant_ops.services import advance_progress, ship_merchant_order
from merchants.models import Merchant, MerchantMembership, MerchantRole
from merchants.services import get_import_fallback_merchant
from offers.models import Market, Offer
from offers.services import import_offer_from_source
from orders import id_backfill
from orders.models import MerchantOrder, Order, Payment, Refund, Shipment
from orders.order_services import place_order
from orders.payment_services import record_payment_for_order

PAYMENT_RE = re.compile(r"^JYPAY\d{8}[0-9A-Z]{6}$")
REFUND_RE = re.compile(r"^JYR\d{8}[0-9A-Z]{6}$")
SHIPMENT_RE = re.compile(r"^JYLOG\d{8}[0-9A-Z]{6}$")


class OrderFlowTestBase(TestCase):
    def setUp(self):
        from django.test import RequestFactory

        self.factory = RequestFactory()
        self.merchant = get_import_fallback_merchant()
        Merchant.objects.filter(pk=self.merchant.pk).update(wallet_balance=Decimal("100000.00"))
        self.market = Market.objects.get(code="GB")
        self.spu, _ = get_or_create_spu_from_source(
            source_system="joybuy", source_id="phase2-spu", title="Phase2 product"
        )
        Spu.objects.filter(pk=self.spu.pk).update(status=Spu.Status.ACTIVE)
        self.sku, _ = get_or_create_sku_from_source(
            spu=self.spu,
            source_system="joybuy",
            source_id="phase2-sku",
            specification={},
            skip_attribute_validation=True,
        )
        self.offer, _ = import_offer_from_source(
            sku=self.sku,
            merchant=self.merchant,
            market=self.market,
            currency=self.market.default_currency,
            source_system="joybuy",
            source_id="phase2-offer",
            current_price="25.00",
        )
        Offer.objects.filter(pk=self.offer.pk).update(
            status=Offer.Status.ACTIVE, cost_price="10.00"
        )

        self.account, _ = BuyerAccount.objects.get_or_create(
            email="phase2@joybuy.test", defaults={"status": BuyerAccount.Status.ACTIVE}
        )
        token, _session = create_buyer_session(
            account=self.account, ip_address="127.0.0.1", user_agent="test"
        )
        self.client.cookies["joybuy_buyer_session"] = token
        self.address = Address.objects.create(
            account=self.account,
            full_name="Phase Two",
            phone="+447000000001",
            line1="2 High Street",
            city="London",
            postcode="SW1A 1AA",
        )

    def place(self, *, payment_method="CARD", quantity=1):
        context = resolve_cart_context(self.factory.get("/"))
        context.account = self.account
        add_item(context, offer_public_id=str(self.offer.public_id), quantity=quantity)
        snapshot = serialize_cart(Cart.objects.get(account=self.account, status=Cart.Status.OPEN))
        return place_order(
            account=self.account,
            cart_snapshot=snapshot,
            address_snapshot={"public_id": str(self.address.public_id)},
            payment_method=payment_method,
        )


class PublicIdFormatTests(TestCase):
    def test_three_new_prefixes_follow_format_and_are_unique(self):
        for kind, pattern in (
            ("payment", PAYMENT_RE),
            ("refund", REFUND_RE),
            ("shipment", SHIPMENT_RE),
        ):
            with self.subTest(kind=kind):
                values = {new_public_id(kind) for _ in range(200)}
                self.assertEqual(len(values), 200)
                for value in values:
                    self.assertRegex(value, pattern)


class PaymentFlowTests(OrderFlowTestBase):
    def test_paid_order_creates_succeeded_payment_once(self):
        order = self.place(payment_method="KLARNA")
        payment = Payment.objects.get(order=order)
        self.assertRegex(payment.public_id, PAYMENT_RE)
        self.assertEqual(str(payment.amount), "25.00")
        self.assertEqual(payment.currency, "GBP")
        self.assertEqual(payment.method, "KLARNA")
        self.assertEqual(payment.status, Payment.Status.SUCCEEDED)
        self.assertEqual(payment.paid_at, order.paid_at)

        # 重复调用不重复建（幂等）。
        record_payment_for_order(order)
        record_payment_for_order(order)
        self.assertEqual(Payment.objects.filter(order=order).count(), 1)

    def test_unpaid_order_creates_no_payment_and_attempt_still_fails(self):
        order = self.place(payment_method="")
        self.assertEqual(order.status, Order.Status.PENDING_PAYMENT)
        self.assertFalse(Payment.objects.filter(order=order).exists())

        response = self.client.post(
            reverse("payment-attempt", kwargs={"public_id": order.public_id})
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "PAYMENT_REGION_UNSUPPORTED")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING_PAYMENT)
        self.assertFalse(Payment.objects.filter(order=order).exists())

    def test_ship_creates_shipment_and_payloads_embed_ids(self):
        order = self.place(payment_method="CARD")
        merchant_order = MerchantOrder.objects.get(order=order)
        ship_merchant_order(merchant_order, reference="JB-PHASE2-001")

        shipment = Shipment.objects.get(merchant_order=merchant_order)
        self.assertRegex(shipment.public_id, SHIPMENT_RE)
        self.assertEqual(shipment.tracking_no, "JB-PHASE2-001")
        self.assertEqual(shipment.status, Shipment.Status.IN_TRANSIT)
        self.assertIsNotNone(shipment.shipped_at)

        buyer_detail = self.client.get(
            reverse("order-detail", kwargs={"public_id": order.public_id})
        ).json()
        self.assertEqual(buyer_detail["payments"][0]["public_id"], order.payments.get().public_id)
        self.assertEqual(buyer_detail["shipments"][0]["public_id"], shipment.public_id)
        self.assertEqual(buyer_detail["shipments"][0]["tracking_no"], "JB-PHASE2-001")
        self.assertEqual(buyer_detail["refunds"], [])

        # 推进到已签收 → 物流记录转 DELIVERED。
        advance_progress(merchant_order, node_index=6)
        shipment.refresh_from_db()
        self.assertEqual(shipment.status, Shipment.Status.DELIVERED)
        self.assertIsNotNone(shipment.delivered_at)

    def test_merchant_order_detail_embeds_payments_shipments(self):
        order = self.place(payment_method="CARD")
        merchant_order = MerchantOrder.objects.get(order=order)
        ship_merchant_order(merchant_order, reference="JB-MERCHANT-1")

        role = MerchantRole.objects.get(code="merchant_owner")
        staff = StaffAccount.objects.create(
            email="phase2-seller@joybuy.test", display_name="店长", status="ACTIVE"
        )
        staff.set_password("Seller#2026pass")
        staff.save()
        MerchantMembership.objects.create(
            merchant=self.merchant, staff=staff, role=role, status="ACTIVE"
        )
        token, _session = create_staff_session(
            staff=staff, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token

        response = self.client.get(
            f"/api/v1/merchant/orders/{merchant_order.public_id}",
            HTTP_X_MERCHANT_ID=str(self.merchant.public_id),
        )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()["order"]
        self.assertEqual(payload["payments"][0]["public_id"], order.payments.get().public_id)
        self.assertEqual(payload["shipments"][0]["tracking_no"], "JB-MERCHANT-1")
        self.assertEqual(payload["refunds"], [])


class BackfillTests(TestCase):
    def setUp(self):
        self.currency = Market.objects.get(code="GB").default_currency
        self.merchant = get_import_fallback_merchant()
        self.buyer, _ = BuyerAccount.objects.get_or_create(email="backfill@joybuy.test")

    def _order(self, *, paid_at, total, method="CARD"):
        return Order.objects.create(
            account=self.buyer,
            currency=self.currency,
            items_subtotal=total,
            shipping_cost=Decimal("0.00"),
            total=total,
            shipping_address={},
            payment_expires_at=timezone.now(),
            status=Order.Status.PAID,
            payment_method=method,
            paid_at=paid_at,
        )

    def test_backfill_counts_match_source_and_is_idempotent(self):
        paid_one = self._order(paid_at=timezone.now(), total=Decimal("12.34"))
        paid_two = self._order(paid_at=timezone.now(), total=Decimal("56.78"), method="BALANCE")
        unpaid = self._order(paid_at=None, total=Decimal("9.99"))

        shipped = MerchantOrder.objects.create(
            order=paid_one,
            merchant=self.merchant,
            currency="GBP",
            status=MerchantOrder.Status.SHIPPED,
            tracking_reference="JB-BACKFILL-1",
            shipped_at=timezone.now(),
        )
        completed = MerchantOrder.objects.create(
            order=paid_two,
            merchant=self.merchant,
            currency="GBP",
            status=MerchantOrder.Status.COMPLETED,
            tracking_reference="JB-BACKFILL-2",
            shipped_at=timezone.now(),
            node_times=[None] * 6 + [timezone.now().isoformat()],
        )
        MerchantOrder.objects.create(
            order=unpaid,
            merchant=self.merchant,
            currency="GBP",
            status=MerchantOrder.Status.PENDING,
        )

        self.assertEqual(id_backfill.backfill_payments(apps), 2)
        self.assertEqual(id_backfill.backfill_shipments(apps), 2)
        self.assertEqual(id_backfill.backfill_refunds(apps), 0)
        # 幂等：再跑一遍不新增。
        self.assertEqual(id_backfill.backfill_payments(apps), 0)
        self.assertEqual(id_backfill.backfill_shipments(apps), 0)

        report = id_backfill.verify_backfill(apps)
        self.assertEqual(report["payment"]["rows"], 2)
        self.assertEqual(report["shipment"]["rows"], 2)
        self.assertEqual(report["refund"]["rows"], 0)

        payment = Payment.objects.get(order=paid_one)
        self.assertRegex(payment.public_id, PAYMENT_RE)
        expected_date = timezone.localtime(paid_one.paid_at).strftime("%Y%m%d")
        self.assertEqual(payment.public_id[len("JYPAY") : len("JYPAY") + 8], expected_date)
        self.assertEqual(str(payment.amount), "12.34")
        self.assertEqual(payment.paid_at, paid_one.paid_at)
        self.assertEqual(Payment.objects.get(order=paid_two).method, "BALANCE")
        self.assertFalse(Payment.objects.filter(order=unpaid).exists())

        shipped_shipment = Shipment.objects.get(merchant_order=shipped)
        self.assertEqual(shipped_shipment.status, Shipment.Status.IN_TRANSIT)
        self.assertEqual(shipped_shipment.tracking_no, "JB-BACKFILL-1")
        completed_shipment = Shipment.objects.get(merchant_order=completed)
        self.assertEqual(completed_shipment.status, Shipment.Status.DELIVERED)
        self.assertIsNotNone(completed_shipment.delivered_at)
        self.assertRegex(shipped_shipment.public_id, SHIPMENT_RE)


class AdminRefundApiTests(TestCase):
    def setUp(self):
        self.currency = Market.objects.get(code="GB").default_currency
        self.merchant = get_import_fallback_merchant()
        self.buyer, _ = BuyerAccount.objects.get_or_create(email="refund@joybuy.test")
        self.order = Order.objects.create(
            account=self.buyer,
            currency=self.currency,
            items_subtotal=Decimal("40.00"),
            shipping_cost=Decimal("0.00"),
            total=Decimal("40.00"),
            shipping_address={},
            payment_expires_at=timezone.now(),
            status=Order.Status.PAID,
            payment_method="CARD",
            paid_at=timezone.now(),
        )
        record_payment_for_order(self.order)
        self.after_sale = AfterSale.objects.create(
            merchant=self.merchant,
            order=self.order,
            kind=AfterSale.Kind.RETURN,
            state=AfterSale.State.COMPLETED,
            currency="GBP",
        )
        self._login_admin()

    def _login_admin(self):
        role, _ = PlatformRole.objects.update_or_create(
            code="phase2-admin-role", defaults={"name": "Phase2 admin", "is_system": False}
        )
        permissions = [
            PlatformPermission.objects.get_or_create(code=code, defaults={"name": code})[0]
            for code in ("orders.manage", "orders.view", "aftersales.manage", "aftersales.view")
        ]
        role.permissions.set(permissions)
        staff, _ = StaffAccount.objects.get_or_create(
            email="phase2-admin@joybuy.test",
            defaults={
                "display_name": "Phase2 admin",
                "password": "x",
                "status": StaffAccount.Status.ACTIVE,
            },
        )
        StaffRoleAssignment.objects.get_or_create(staff=staff, role=role)
        token, _session = create_staff_session(
            staff=staff, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token

    def test_create_refund_returns_jyr_and_shows_in_lists(self):
        response = self.client.post(
            "/api/v1/admin/refunds",
            data={
                "order_id": str(self.order.public_id),
                "after_sale_id": str(self.after_sale.public_id),
                "amount": "12.50",
                "status": "SUCCEEDED",
                "reason": "退货打款（手动补录）",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        refund_payload = response.json()["refund"]
        self.assertRegex(refund_payload["public_id"], REFUND_RE)
        self.assertEqual(refund_payload["amount"], "12.50")
        self.assertEqual(refund_payload["currency"], "GBP")

        refund = Refund.objects.get(public_id=refund_payload["public_id"])
        self.assertEqual(refund.order_id, self.order.pk)
        self.assertEqual(refund.after_sale_id, self.after_sale.pk)
        self.assertEqual(refund.status, Refund.Status.SUCCEEDED)
        self.assertIsNotNone(refund.processed_at)

        listing = self.client.get("/api/v1/admin/refunds?page=1&page_size=10").json()
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["items"][0]["public_id"], refund.public_id)

        detail = self.client.get(f"/api/v1/admin/after-sales/{self.after_sale.public_id}").json()
        self.assertEqual(detail["after_sale"]["refunds"][0]["public_id"], refund.public_id)

    def test_invalid_amount_is_rejected(self):
        response = self.client.post(
            "/api/v1/admin/refunds",
            data={"order_id": str(self.order.public_id), "amount": "0"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "AMOUNT_INVALID")
        self.assertFalse(Refund.objects.exists())

    def test_payment_and_shipment_lists_are_paginated(self):
        response = self.client.get("/api/v1/admin/payments?page=1&page_size=10")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        self.assertRegex(response.json()["items"][0]["public_id"], PAYMENT_RE)

        response = self.client.get("/api/v1/admin/shipments?page=1&page_size=10")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 0)
