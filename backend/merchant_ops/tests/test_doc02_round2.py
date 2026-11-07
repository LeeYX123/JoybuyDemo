"""迭代02 第 2 轮：活动曝光/到期、返佣成本价基数、好评订单关联、余额真扣、登录渠道。"""

import json
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts_buyers.models import BuyerAccount
from accounts_staff.models import PlatformRole, StaffAccount, StaffRoleAssignment
from catalog.models import Sku, Spu, SpuTranslation
from merchant_ops.models import (
    MerchantActivity,
    MerchantActivityParticipation,
    MerchantReferral,
    ReferralCommission,
)
from merchants.models import Merchant, MerchantMembership, MerchantRole
from offers.models import Currency, Market, Offer
from orders.models import MerchantOrder, Order


class Doc02Round2Base(TestCase):
    def setUp(self):
        self.staff = StaffAccount.objects.create(
            email="doc02r2@joybuy.test", display_name="Doc02 R2", status="ACTIVE"
        )
        self.staff.set_password("Doc02#R2pass")
        self.staff.save()
        StaffRoleAssignment.objects.get_or_create(
            staff=self.staff, defaults={"role": PlatformRole.objects.get(code="platform_admin")}
        )
        token, _session = create_session(self.staff)
        self.client.cookies["joybuy_staff_session"] = token
        self.shop = Merchant.objects.create(
            slug="doc02r2-shop", display_name="迭代R2店", onboarding_status="ACTIVE"
        )
        MerchantMembership.objects.create(
            merchant=self.shop,
            staff=self.staff,
            role=MerchantRole.objects.get(code="merchant_owner"),
            status="ACTIVE",
        )
        self.currency, _ = Currency.objects.get_or_create(
            code="CNY", defaults={"name": "Chinese Yuan", "symbol": "¥"}
        )
        self.market, _ = Market.objects.get_or_create(
            code="G2",
            defaults={
                "name": "R2 Market",
                "default_locale": "en-GB",
                "time_zone": "UTC",
                "default_currency": self.currency,
            },
        )

    def _make_completed_suborder(self, *, items="200.00", cost="150.00", shipped=True):
        buyer, _ = BuyerAccount.objects.get_or_create(
            email="doc02r2-buyer@joybuy.test", defaults={"status": "ACTIVE", "password": "x"}
        )
        order = Order.objects.create(
            account=buyer,
            currency=self.currency,
            items_subtotal=Decimal(items),
            shipping_cost=0,
            total=Decimal(items),
            shipping_address={"full_name": "R2"},
            payment_expires_at=timezone.now() + timedelta(hours=1),
            status=Order.Status.PAID,
        )
        suborder = MerchantOrder.objects.create(
            order=order,
            merchant=self.shop,
            currency="CNY",
            items_total=Decimal(items),
            cost_total=Decimal(cost),
            status=MerchantOrder.Status.PENDING,
        )
        if shipped:
            shipped_at = timezone.now()
            MerchantOrder.objects.filter(pk=suborder.pk).update(
                status=MerchantOrder.Status.COMPLETED,
                progress=7,
                shipped_at=shipped_at,
                settled=True,
                settled_at=shipped_at,
                node_times=[shipped_at.isoformat()] + [None] * 7,
            )
        return suborder


def create_session(staff):
    from accounts_staff.services import create_staff_session

    return create_staff_session(staff=staff, ip_address="127.0.0.1", user_agent="t", totp_verified=True)


class ActivityTests(Doc02Round2Base):
    def test_permanent_activity_created_without_dates_and_hides_time(self):
        response = self.client.post(
            "/api/v1/admin/activities",
            data=json.dumps({"title": "长期补贴", "kind": "PERMANENT"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        payload = response.json()["activity"]
        self.assertIsNone(payload["start"])
        self.assertIsNone(payload["end"])

    def test_limited_activity_requires_dates_and_expires(self):
        response = self.client.post(
            "/api/v1/admin/activities",
            data=json.dumps({"title": "限时秒杀", "kind": "LIMITED"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

        past_end = (timezone.localdate() - timedelta(days=1)).isoformat()
        past_start = (timezone.localdate() - timedelta(days=10)).isoformat()
        response = self.client.post(
            "/api/v1/admin/activities",
            data=json.dumps(
                {"title": "过期活动", "kind": "LIMITED", "start": past_start, "end": past_end}
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        activity = MerchantActivity.objects.get(title="过期活动")
        self.assertEqual(activity.state, "ONGOING")

        # 商家端列表惰性到期 → ENDED 且不再展示
        response = self.client.get(
            "/api/v1/merchant/activities", HTTP_X_MERCHANT_ID=str(self.shop.public_id)
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 0)
        activity.refresh_from_db()
        self.assertEqual(activity.state, "ENDED")

    def test_join_adds_exposure_and_records(self):
        activity = MerchantActivity.objects.create(
            title="曝光活动",
            kind=MerchantActivity.Kind.PERMANENT,
            start_date=timezone.localdate(),
        )
        self.shop.exposure = 5
        self.shop.save(update_fields=["exposure"])
        response = self.client.post(
            f"/api/v1/merchant/activities/{activity.public_id}/join",
            data="{}",
            content_type="application/json",
            HTTP_X_MERCHANT_ID=str(self.shop.public_id),
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["exposure_added"], 1)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.exposure, 6)
        self.assertEqual(self.shop.exposure_delta, 1)
        participation = MerchantActivityParticipation.objects.get(
            activity=activity, merchant=self.shop
        )
        self.assertEqual(participation.exposure_added, 1)
        # 重复参与不重复加曝光
        self.client.post(
            f"/api/v1/merchant/activities/{activity.public_id}/join",
            data="{}",
            content_type="application/json",
            HTTP_X_MERCHANT_ID=str(self.shop.public_id),
        )
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.exposure, 6)


class ReferralTests(Doc02Round2Base):
    def test_commission_basis_is_cost_total(self):
        referrer = Merchant.objects.create(
            slug="doc02r2-referrer", display_name="邀请人店", onboarding_status="ACTIVE"
        )
        referee = Merchant.objects.create(
            slug="doc02r2-referee", display_name="被邀请店", onboarding_status="ACTIVE"
        )
        MerchantReferral.objects.create(referrer=referrer, referee=referee, code_used="R2CODE")
        # 被邀请店入驻时间与推荐关系回填 65 天前：核算月（上月）在返佣有效期内。
        from merchants.models import Merchant as _M

        _M.objects.filter(pk=referee.pk).update(created_at=timezone.now() - timedelta(days=65))
        MerchantReferral.objects.filter(pk=MerchantReferral.objects.get(referee=referee).pk).update(
            created_at=timezone.now() - timedelta(days=65)
        )
        # 上月发货成功订单（挂在被邀请店）：零售 200 / 成本 150 → 计佣基数应为 150
        suborder = self._make_completed_suborder(items="200.00", cost="150.00")
        last_month = (timezone.now() - timedelta(days=35)).strftime("%Y-%m")
        started = timezone.now() - timedelta(days=35)
        MerchantOrder.objects.filter(pk=suborder.pk).update(merchant=referee, shipped_at=started)

        from merchant_ops.services import calculate_commissions

        created = calculate_commissions(last_month)
        self.assertEqual(len(created), 1)
        commission = ReferralCommission.objects.get(referral__referee=referee, period=last_month)
        self.assertEqual(commission.shipped_amount, Decimal("150.00"))
        expected_rate = (
            Decimal("3.00")
            if Decimal("150.00") >= Decimal("50000")
            else Decimal("2.00")
            if Decimal("150.00") >= Decimal("10000")
            else Decimal("1.00")
        )
        self.assertEqual(commission.rate, expected_rate)
        self.assertEqual(commission.state, ReferralCommission.State.PENDING_PAY)

    def test_create_merchant_binds_referral_by_code(self):
        referrer = Merchant.objects.create(
            slug="doc02r2-inviter", display_name="邀请者", onboarding_status="ACTIVE"
        )
        from merchants.services import create_merchant, ensure_referral_code

        code = ensure_referral_code(referrer)
        new_merchant = create_merchant(
            display_name="受邀新店", admission_approved=True, referrer_code=code
        )
        binding = MerchantReferral.objects.filter(referee=new_merchant).first()
        self.assertIsNotNone(binding)
        self.assertEqual(binding.referrer_id, referrer.pk)
        self.assertEqual(binding.code_used, code)

    def test_invalid_referral_code_does_not_block(self):
        from merchants.services import create_merchant

        new_merchant = create_merchant(
            display_name="无效码新店", admission_approved=True, referrer_code="NOPE123"
        )
        self.assertFalse(MerchantReferral.objects.filter(referee=new_merchant).exists())


class ReviewNotificationTests(Doc02Round2Base):
    def _completed_suborder(self):
        return self._make_completed_suborder()

    def test_review_push_requires_completed_unreviewed_order(self):
        suborder = self._completed_suborder()
        payload = {
            "kind": "REVIEW",
            "merchant_id": str(self.shop.public_id),
            "order_id": str(suborder.public_id),
            "title": "您收到一个商品好评",
            "content": "宝贝非常好！",
            "rating": 5,
        }
        response = self.client.post(
            "/api/v1/admin/notifications", data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()["notifications"][0]
        self.assertEqual(body["order"]["order_no"], str(suborder.public_id)[:8].upper())

        # 未评价过滤：同一订单不能再推
        again = self.client.post(
            "/api/v1/admin/notifications", data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.json()["error"]["code"], "ORDER_ALREADY_REVIEWED")

        # 订单下拉不再包含该订单
        listing = self.client.get(
            f"/api/v1/admin/notifications/orders?merchant_id={self.shop.public_id}"
        ).json()["items"]
        self.assertEqual([item["id"] for item in listing].count(str(suborder.public_id)), 0)

    def test_review_push_rejects_pending_order(self):
        suborder = self._make_completed_suborder(shipped=False)
        payload = {
            "kind": "REVIEW",
            "merchant_id": str(self.shop.public_id),
            "order_id": str(suborder.public_id),
            "title": "t",
            "content": "c",
        }
        response = self.client.post(
            "/api/v1/admin/notifications", data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "ORDER_NOT_COMPLETED")


class BuyerBalanceTests(Doc02Round2Base):
    def test_balance_payment_deducts_buyer_balance(self):
        from orders.order_services import OrderError, place_order

        buyer = BuyerAccount.objects.create(
            email="r2-balance@joybuy.test",
            password="x",
            status="ACTIVE",
            balance=Decimal("100.00"),
            purchase_whitelisted=True,
        )
        snapshot = {
            "items": [],
            "subtotal": "30.00",
            "total": "30.00",
            "currency": "CNY",
            "needs_attention": False,
        }
        # place_order 需要 items 非空 + 真实 offer —— 这里直接绕过 cart 构造完整快照
        spu = Spu.objects.create(status=Spu.Status.ACTIVE)
        SpuTranslation.objects.create(spu=spu, locale="zh-CN", title="R2 余额商品")
        sku = Sku.objects.create(spu=spu, specification={}, specification_signature="r2bal")
        offer = Offer.objects.create(
            merchant=self.shop,
            sku=sku,
            market=self.market,
            currency=self.currency,
            current_price=Decimal("30.00"),
            list_price=Decimal("30.00"),
            cost_price=Decimal("12.00"),
            local_inventory=99,
            status=Offer.Status.ACTIVE,
            listed_at=timezone.now(),
        )
        snapshot["items"] = [{"offer_public_id": str(offer.public_id), "quantity": 1}]
        from checkout.models import Address

        address = Address.objects.create(
            account=buyer,
            full_name="R2",
            phone="+447000000009",
            line1="9 Balance Road",
            city="London",
            postcode="SW1A 1AA",
        )
        order = place_order(
            account=buyer,
            cart_snapshot=snapshot,
            address_snapshot={"public_id": str(address.public_id)},
            payment_method="BALANCE",
        )
        self.assertEqual(order.status, Order.Status.PAID)
        buyer.refresh_from_db()
        self.assertEqual(buyer.balance, Decimal("70.00"))
        entry = buyer.wallet_entries.order_by("-pk").first()
        self.assertEqual(entry.kind, "PURCHASE")
        self.assertEqual(entry.amount, Decimal("-30.00"))

        # 余额不足拒单
        BuyerAccount.objects.filter(pk=buyer.pk).update(balance=Decimal("1.00"))
        buyer.refresh_from_db()
        with self.assertRaises(OrderError) as raised:
            place_order(
                account=buyer,
                cart_snapshot=snapshot,
                address_snapshot={"public_id": str(address.public_id)},
                payment_method="BALANCE",
            )
        self.assertEqual(raised.exception.code, "NOT_ENOUGH_BALANCE")
