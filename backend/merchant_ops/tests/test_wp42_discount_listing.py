"""WP-42：折扣成本价与商家端上架口径。

2026-11-10 最终口径（取代 2026-11-08「平台成本价 × (1 - 折扣%)」等全部旧口径）：
成本价 = 零售价 × (1 - 折扣%)，向上取整到分（ROUND_CEILING）。
折扣是管理端设置的减免百分比；未设置折扣视为减免 0%（成本价 = 零售价）；
基数是 ``Spu.retail_price``，``cost_price`` 不参与公式。
"""

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


def make_spu(*, cost=None, retail="12.10", is_activity=False) -> Spu:
    # cost 默认 None：与爬虫商品基线一致（商品池成本价为空），
    # 也保证默认不撞 DB 约束 spu_retail_not_below_cost（retail >= cost）。
    # 需要证明「基数是零售价不是成本价」的用例才显式传 cost。
    return Spu.objects.create(
        status=Spu.Status.ACTIVE,
        cost_price=Decimal(cost) if cost is not None else None,
        retail_price=Decimal(retail) if retail is not None else None,
        is_activity=is_activity,
    )


class ComputeListingCostTests(TestCase):
    def test_discount_20_on_retail_200(self):
        """零售 200、折扣 20%（减免）→ 200 × 80% = 160.00（2026-11-10 口径）。"""
        merchant = make_merchant(discount_rate=Decimal("20.00"))
        spu = make_spu(cost="100.00", retail="200.00")
        self.assertEqual(compute_listing_cost(merchant, spu), Decimal("160.00"))

    def test_base_is_retail_price_not_cost_price(self):
        """基数是零售价不是商品池成本价：cost 100、retail 200、折扣 20% → 160（不是 80）。"""
        merchant = make_merchant(discount_rate=Decimal("20.00"))
        spu = make_spu(cost="100.00", retail="200.00")
        self.assertEqual(compute_listing_cost(merchant, spu), Decimal("160.00"))

    def test_rounds_up_to_cent(self):
        merchant = make_merchant(discount_rate=Decimal("20.00"))
        # 25.99 × 0.8 = 20.792 → 向上取整到分 = 20.80
        self.assertEqual(compute_listing_cost(merchant, make_spu(retail="25.99")), Decimal("20.80"))
        # 0.46 × 0.8 = 0.368 → 0.37
        self.assertEqual(compute_listing_cost(merchant, make_spu(retail="0.46")), Decimal("0.37"))

    def test_activity_discount_takes_precedence(self):
        """先判断活动商品 → 用活动折扣，否则用普通折扣（文档拍板）。"""
        merchant = make_merchant(
            discount_rate=Decimal("20.00"), activity_discount_rate=Decimal("30.00")
        )
        normal = make_spu(retail="200.00")
        activity = make_spu(retail="200.00", is_activity=True)
        self.assertEqual(compute_listing_cost(merchant, activity), Decimal("140.00"))
        self.assertEqual(compute_listing_cost(merchant, normal), Decimal("160.00"))

    def test_activity_product_without_activity_discount_falls_back_to_normal(self):
        merchant = make_merchant(discount_rate=Decimal("20.00"))
        activity = make_spu(retail="200.00", is_activity=True)
        self.assertEqual(compute_listing_cost(merchant, activity), Decimal("160.00"))

    def test_no_discount_means_cost_equals_retail(self):
        """未设置折扣 = 减免 0%，成本价 = 零售价。"""
        merchant = make_merchant()
        self.assertEqual(
            compute_listing_cost(merchant, make_spu(cost="8.88", retail="25.99")),
            Decimal("25.99"),
        )

    def test_missing_retail_price_returns_none(self):
        merchant = make_merchant(discount_rate=Decimal("20.00"))
        self.assertIsNone(compute_listing_cost(merchant, make_spu(cost="12.00", retail=None)))

    def test_null_cost_price_still_computes_from_retail(self):
        """爬虫商品成本价 NULL：cost_price 不参与公式，零售价在就能算出成本并上架。"""
        merchant = make_merchant(discount_rate=Decimal("20.00"))
        spu = make_spu(cost=None, retail="50.00")
        self.assertEqual(compute_listing_cost(merchant, spu), Decimal("40.00"))


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
