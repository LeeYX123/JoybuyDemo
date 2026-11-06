"""WP-42：信誉分钳制、曝光日口径、自动封店、公开商家搜索。"""

from datetime import timedelta

from django.test import Client, TestCase
from django.utils import timezone

from merchants.models import Merchant
from merchants.public_views import _listed_offers  # noqa: F401  (确保模块可导入)
from merchants.services import (
    MerchantAdminError,
    add_exposure,
    add_followers,
    auto_suspend_overdue_merchants,
    deduct_credit,
)
from offers.models import Currency, Market, Offer
from orders.models import MerchantOrder, Order


class CreditDeductTests(TestCase):
    def setUp(self):
        self.merchant = Merchant.objects.create(
            slug="credit-shop", display_name="Credit Shop", onboarding_status="ACTIVE"
        )

    def test_deduct_clamps_at_zero(self):
        merchant = deduct_credit(self.merchant, points=150)
        self.assertEqual(merchant.credit_score, 0)

    def test_deduct_partial(self):
        merchant = deduct_credit(self.merchant, points=30)
        self.assertEqual(merchant.credit_score, 70)

    def test_deduct_invalid_points(self):
        with self.assertRaises(MerchantAdminError):
            deduct_credit(self.merchant, points=0)

    def test_deduct_to_zero_does_not_suspend(self):
        merchant = deduct_credit(self.merchant, points=100)
        merchant.refresh_from_db()
        self.assertEqual(merchant.credit_score, 0)
        self.assertEqual(merchant.onboarding_status, Merchant.OnboardingStatus.ACTIVE)


class ExposureDailyTests(TestCase):
    def setUp(self):
        self.merchant = Merchant.objects.create(
            slug="growth-shop", display_name="Growth Shop", onboarding_status="ACTIVE"
        )

    def test_exposure_today_delta_accumulates(self):
        add_exposure(self.merchant, count=50)
        add_exposure(self.merchant, count=100)
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.exposure, 150)
        self.assertEqual(self.merchant.exposure_delta, 150)
        self.assertEqual(self.merchant.exposure_day, timezone.localdate())

    def test_exposure_delta_resets_next_day(self):
        add_exposure(self.merchant, count=50)
        yesterday = timezone.localdate() - timedelta(days=1)
        Merchant.objects.filter(pk=self.merchant.pk).update(exposure_day=yesterday)
        add_exposure(self.merchant, count=70)
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.exposure, 120)
        self.assertEqual(self.merchant.exposure_delta, 70)

    def test_daily_stat_rows_written(self):
        from merchants.models import MerchantDailyStat

        add_exposure(self.merchant, count=50)
        add_followers(self.merchant, count=3)
        row = MerchantDailyStat.objects.get(merchant=self.merchant)
        self.assertEqual(row.exposure_delta, 50)
        self.assertEqual(row.followers_delta, 3)


class AutoSuspendTests(TestCase):
    def setUp(self):
        self.merchant = Merchant.objects.create(
            slug="auto-ban-shop",
            display_name="Auto Ban Shop",
            onboarding_status=Merchant.OnboardingStatus.ACTIVE,
            ban_after_days=4,
        )
        self.buyer_order = Order.objects.create(
            account=self._buyer(),
            currency=self._currency(),
            items_subtotal=0,
            shipping_cost=0,
            total=0,
            payment_expires_at=timezone.now() + timedelta(hours=1),
        )

    def _buyer(self):
        from accounts_buyers.models import BuyerAccount

        account, _ = BuyerAccount.objects.get_or_create(
            email="wp42-buyer@example.test",
            defaults={"status": "ACTIVE", "password": "not-a-real-password"},
        )
        return account

    def _currency(self):
        from offers.models import Currency as CurrencyModel

        currency, _ = CurrencyModel.objects.get_or_create(
            code="CNY",
            defaults={"name": "Chinese Yuan", "symbol": "¥"},
        )
        return currency

    def _make_pending_order(self, *, days_ago):
        created = timezone.now() - timedelta(days=days_ago)
        order = MerchantOrder.objects.create(
            order=self.buyer_order,
            merchant=self.merchant,
            currency="CNY",
            created_at=created,
            updated_at=created,
        )
        # auto_now 会覆盖 created_at，这里显式回写。
        MerchantOrder.objects.filter(pk=order.pk).update(created_at=created)
        return order

    def test_overdue_pending_order_suspends(self):
        self._make_pending_order(days_ago=5)
        suspended = auto_suspend_overdue_merchants()
        self.assertEqual([m.pk for m in suspended], [self.merchant.pk])
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.onboarding_status, Merchant.OnboardingStatus.SUSPENDED)
        self.assertIn("自动封店", self.merchant.suspend_reason)

    def test_within_threshold_not_suspended(self):
        self._make_pending_order(days_ago=2)
        self.assertEqual(auto_suspend_overdue_merchants(), [])
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.onboarding_status, Merchant.OnboardingStatus.ACTIVE)

    def test_null_ban_days_opt_out(self):
        Merchant.objects.filter(pk=self.merchant.pk).update(ban_after_days=None)
        self._make_pending_order(days_ago=30)
        self.assertEqual(auto_suspend_overdue_merchants(), [])

    def test_shipped_orders_do_not_count(self):
        order = self._make_pending_order(days_ago=30)
        MerchantOrder.objects.filter(pk=order.pk).update(status=MerchantOrder.Status.SHIPPED)
        self.assertEqual(auto_suspend_overdue_merchants(), [])


class PublicMerchantApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.merchant = Merchant.objects.create(
            slug="public-shop",
            display_name="海淘优选旗舰店",
            onboarding_status=Merchant.OnboardingStatus.ACTIVE,
            followers=12,
            exposure=88,
        )
        self.currency, _ = Currency.objects.get_or_create(
            code="USD", defaults={"name": "US Dollar", "symbol": "$"}
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
        # 可被搜到的前提：至少有一件在售商品。
        from catalog.models import Spu, SpuTranslation

        spu = Spu.objects.create(status=Spu.Status.ACTIVE)
        SpuTranslation.objects.create(spu=spu, locale="zh-CN", title="默认在售商品")
        self._offer(spu)

    def _offer(self, spu, price="19.90"):
        from catalog.models import Sku

        sku = Sku.objects.create(spu=spu, specification={}, specification_signature="sig")
        return Offer.objects.create(
            merchant=self.merchant,
            sku=sku,
            market=self.market,
            currency=self.currency,
            current_price=price,
            list_price=price,
            status=Offer.Status.ACTIVE,
            listed_at=timezone.now(),
        )

    def test_search_by_name(self):
        response = self.client.get("/api/v1/merchants/search", data={"q": "海淘"})
        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["followers_total"], 12)
        self.assertEqual(items[0]["exposure_total"], 88)

    def test_search_requires_active_offer(self):
        # 没有 ACTIVE Offer 的商家不出现（结果页只展示上架商家）。
        Merchant.objects.create(
            slug="no-offer-shop", display_name="无商品商店", onboarding_status="ACTIVE"
        )
        response = self.client.get("/api/v1/merchants/search", data={"q": "店"})
        self.assertEqual([item["slug"] for item in response.json()["items"]], ["public-shop"])

    def test_detail_returns_products(self):
        from catalog.models import Spu, SpuTranslation

        spu = Spu.objects.create(status=Spu.Status.ACTIVE)
        SpuTranslation.objects.create(spu=spu, locale="zh-CN", title="测试水壶")
        self._offer(spu)
        response = self.client.get("/api/v1/merchants/public-shop")
        self.assertEqual(response.status_code, 200)
        payload = response.json()["merchant"]
        self.assertEqual(payload["name"], "海淘优选旗舰店")
        self.assertEqual(len(payload["products"]), 2)
        names = {product["name"] for product in payload["products"]}
        self.assertIn("测试水壶", names)

    def test_detail_404(self):
        response = self.client.get("/api/v1/merchants/missing-shop")
        self.assertEqual(response.status_code, 404)
