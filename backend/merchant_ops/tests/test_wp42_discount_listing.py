"""WP-42：折扣成本价（向上取整）与商家端上架口径。"""

from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from catalog.models import Spu
from merchant_ops.views_merchant_catalog import compute_listing_cost
from merchants.models import Merchant


def make_merchant(**kwargs) -> Merchant:
    defaults = {
        "slug": "discount-shop",
        "display_name": "折扣测试店",
        "onboarding_status": Merchant.OnboardingStatus.ACTIVE,
    }
    defaults.update(kwargs)
    return Merchant.objects.create(**defaults)


def make_spu(*, cost="12.10", retail="12.10", is_activity=False) -> Spu:
    return Spu.objects.create(
        status=Spu.Status.ACTIVE,
        cost_price=Decimal(cost) if cost is not None else None,
        retail_price=Decimal(retail) if retail is not None else None,
        is_activity=is_activity,
    )


class ComputeListingCostTests(TestCase):
    def test_ceil_to_integer(self):
        """12.10 与 12.90 取整后都是 13；121.98 → 122（文档 M03 §2 例）。"""
        merchant = make_merchant(discount_rate=Decimal("100.00"))
        self.assertEqual(compute_listing_cost(merchant, make_spu(cost=None, retail="12.10")), 13)
        self.assertEqual(compute_listing_cost(merchant, make_spu(cost=None, retail="12.90")), 13)
        self.assertEqual(compute_listing_cost(merchant, make_spu(cost=None, retail="121.98")), 122)

    def test_discount_percent(self):
        merchant = make_merchant(discount_rate=Decimal("70.00"))
        self.assertEqual(compute_listing_cost(merchant, make_spu(cost=None, retail="100.00")), 70)
        # 非整除也要向上取整：101 × 70% = 70.7 → 71。
        self.assertEqual(compute_listing_cost(merchant, make_spu(cost=None, retail="101.00")), 71)
        merchant.discount_rate = Decimal("60.00")
        self.assertEqual(compute_listing_cost(merchant, make_spu(cost=None, retail="100.00")), 60)
        # 99 × 60% = 59.4 → 60。
        self.assertEqual(compute_listing_cost(merchant, make_spu(cost=None, retail="99.00")), 60)

    def test_activity_discount_takes_precedence(self):
        """先判断活动商品 → 用活动折扣，否则用普通折扣（文档拍板）。"""
        merchant = make_merchant(discount_rate=Decimal("70.00"), activity_discount_rate=Decimal("50.00"))
        normal = make_spu(retail="100.00")
        activity = make_spu(retail="100.00", is_activity=True)
        self.assertEqual(compute_listing_cost(merchant, activity), 50)
        self.assertEqual(compute_listing_cost(merchant, normal), 70)

    def test_activity_product_without_activity_discount_falls_back_to_normal(self):
        merchant = make_merchant(discount_rate=Decimal("70.00"))
        activity = make_spu(retail="100.00", is_activity=True)
        self.assertEqual(compute_listing_cost(merchant, activity), 70)

    def test_no_discount_falls_back_to_pool_cost(self):
        merchant = make_merchant()
        spu = make_spu(cost="8.88", retail="20.00")
        self.assertEqual(compute_listing_cost(merchant, spu), Decimal("8.88"))


class MerchantCategoryChoicesTests(TestCase):
    def test_twelve_categories_excluding_activity(self):
        self.assertEqual(len(Spu.MerchantCategory.values), 11)
        # 「活动商品」是标记不是品类，不在 choices 里。
        self.assertNotIn("ACTIVITY", Spu.MerchantCategory.values)

    def test_label_of_empty_is_unclassified(self):
        self.assertEqual(Spu.merchant_category_label(""), "未分类")


class RunOrderSweepsCommandTests(TestCase):
    def test_command_runs_all_sweeps(self):
        from datetime import timedelta

        from django.utils import timezone

        from accounts_buyers.models import BuyerAccount
        from offers.models import Currency
        from orders.models import MerchantOrder, Order

        merchant = make_merchant(slug="sweep-shop", display_name="清扫店", ban_after_days=1)
        currency, _ = Currency.objects.get_or_create(
            code="CNY", defaults={"name": "Chinese Yuan", "symbol": "¥"}
        )
        buyer = BuyerAccount.objects.create(
            email="sweep@joybuy.test", password="x", status="ACTIVE"
        )
        order = Order.objects.create(
            account=buyer,
            currency=currency,
            items_subtotal=0,
            shipping_cost=0,
            total=0,
            payment_expires_at=timezone.now() + timedelta(hours=1),
        )
        old = timezone.now() - timedelta(days=5)
        MerchantOrder.objects.create(order=order, merchant=merchant, currency="CNY")
        MerchantOrder.objects.filter(merchant=merchant).update(created_at=old)

        call_command("run_order_sweeps", verbosity=0)
        merchant.refresh_from_db()
        self.assertEqual(merchant.onboarding_status, Merchant.OnboardingStatus.SUSPENDED)
