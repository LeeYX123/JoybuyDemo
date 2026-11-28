"""WP-42：信誉分钳制、曝光日口径、自动封店、公开商家搜索。"""

import shutil
import tempfile
from datetime import timedelta

from django.test import Client, TestCase, override_settings
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

    def test_canceled_parent_order_not_counted(self):
        """2026-11-29：父单已取消的子单不算商家超时（自动封店 + 封店预检同口径）。"""

        from merchant_ops.views_merchants import _overdue_pending_info

        self._make_pending_order(days_ago=30)
        Order.objects.filter(pk=self.buyer_order.pk).update(status=Order.Status.CANCELED)

        info = _overdue_pending_info(self.merchant, 4)
        self.assertFalse(info["overdue"])
        self.assertIsNone(info["overdue_days"])
        self.assertEqual(auto_suspend_overdue_merchants(), [])
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.onboarding_status, Merchant.OnboardingStatus.ACTIVE)


class PublicMerchantApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.media_root = tempfile.mkdtemp(prefix="joybuy-merchant-media-")
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        media_override = override_settings(MEDIA_ROOT=self.media_root)
        media_override.enable()
        self.addCleanup(media_override.disable)
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

    def test_detail_hides_offers_whose_spu_is_not_sellable(self):
        """缺陷 12：商家页只返回可售商品（Offer ACTIVE + SPU ACTIVE），DRAFT 不列。"""

        from catalog.models import Spu, SpuTranslation

        draft = Spu.objects.create(status=Spu.Status.DRAFT, image_urls=[])
        SpuTranslation.objects.create(spu=draft, locale="zh-CN", title="未上架商品")
        draft_offer = self._offer(draft)
        Offer.objects.filter(pk=draft_offer.pk).update(
            listed_at=timezone.now() + timedelta(days=1)
        )

        products = self.client.get("/api/v1/merchants/public-shop").json()["merchant"]["products"]
        names = {product["name"] for product in products}
        self.assertNotIn("未上架商品", names)
        self.assertNotIn(str(draft_offer.public_id), {p["offer_id"] for p in products})
        self.assertIn("默认在售商品", names)

    def _media_asset(self, path):
        from media.models import MediaAsset

        now = timezone.now()
        return MediaAsset.objects.create(
            sha256=path.replace("/", "").ljust(64, "0")[:64],
            kind=MediaAsset.Kind.PRODUCT,
            relative_path=path,
            mime_type="image/webp",
            extension="webp",
            byte_size=12,
            first_seen_at=now,
            last_seen_at=now,
            download_status=MediaAsset.DownloadStatus.DOWNLOADED,
        )

    def _write_media_file(self, path):
        from media.storage import resolve_media_path

        target = resolve_media_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"fake-webp-bytes")

    def _gallery_usage(self, spu, path, sort_order=0, exists=True):
        from catalog.models import Spu
        from django.contrib.contenttypes.models import ContentType
        from media.models import MediaUsage

        if exists:
            self._write_media_file(path)
        MediaUsage.objects.create(
            asset=self._media_asset(path),
            content_type=ContentType.objects.get_for_model(Spu),
            object_id=spu.pk,
            role="gallery",
            sort_order=sort_order,
        )

    def test_detail_falls_back_to_first_gallery_image(self):
        """需求 20.2：image_urls 为空时回退到本地图库首图。"""

        from catalog.models import Spu, SpuTranslation

        spu = Spu.objects.create(status=Spu.Status.ACTIVE, image_urls=[])
        SpuTranslation.objects.create(spu=spu, locale="zh-CN", title="无封面图商品")
        self._offer(spu)
        self._gallery_usage(spu, "products/original/bb/bb/fallback.webp", sort_order=3)
        self._gallery_usage(spu, "products/original/aa/aa/second.webp", sort_order=9)

        response = self.client.get("/api/v1/merchants/public-shop")
        products = response.json()["merchant"]["products"]
        product = next(item for item in products if item["name"] == "无封面图商品")
        self.assertEqual(product["image"], "/media/products/original/bb/bb/fallback.webp")

    def test_detail_skips_gallery_rows_whose_files_are_missing(self):
        """DB 行存在但本地文件已缺失（S3 时代遗留）→ 用下一张存在的图，不返回 404 路径。"""

        from catalog.models import Spu, SpuTranslation

        from merchants.public_views import PRODUCT_PLACEHOLDER_IMAGE

        recovered = Spu.objects.create(status=Spu.Status.ACTIVE, image_urls=[])
        SpuTranslation.objects.create(spu=recovered, locale="zh-CN", title="缺首图商品")
        self._offer(recovered)
        self._gallery_usage(recovered, "products/original/dd/dd/gone.webp", sort_order=0, exists=False)
        self._gallery_usage(recovered, "products/original/dd/dd/next.webp", sort_order=1)

        gone = Spu.objects.create(status=Spu.Status.ACTIVE, image_urls=[])
        SpuTranslation.objects.create(spu=gone, locale="zh-CN", title="图全丢失商品")
        self._offer(gone)
        self._gallery_usage(gone, "products/original/ee/ee/gone.webp", exists=False)

        products = self.client.get("/api/v1/merchants/public-shop").json()["merchant"]["products"]
        by_name = {item["name"]: item for item in products}
        self.assertEqual(by_name["缺首图商品"]["image"], "/media/products/original/dd/dd/next.webp")
        self.assertEqual(by_name["图全丢失商品"]["image"], PRODUCT_PLACEHOLDER_IMAGE)

    def test_detail_uses_placeholder_when_no_image_at_all(self):
        """需求 20.2：连图库都没有时不得返回空字符串。"""

        from catalog.models import Spu, SpuTranslation

        from merchants.public_views import PRODUCT_PLACEHOLDER_IMAGE

        spu = Spu.objects.create(status=Spu.Status.ACTIVE, image_urls=[])
        SpuTranslation.objects.create(spu=spu, locale="zh-CN", title="完全无图商品")
        self._offer(spu)

        response = self.client.get("/api/v1/merchants/public-shop")
        products = response.json()["merchant"]["products"]
        product = next(item for item in products if item["name"] == "完全无图商品")
        self.assertEqual(product["image"], PRODUCT_PLACEHOLDER_IMAGE)
        self.assertNotEqual(product["image"], "")

    def test_detail_gallery_lookup_is_not_n_plus_one(self):
        """图片回退只做一次批量查询：商品数增加不增加 media_usage 查询数。"""

        from catalog.models import Spu, SpuTranslation
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def add_product(name):
            spu = Spu.objects.create(status=Spu.Status.ACTIVE, image_urls=[])
            SpuTranslation.objects.create(spu=spu, locale="zh-CN", title=name)
            self._offer(spu)
            self._gallery_usage(spu, f"products/original/cc/{name}.webp")
            return spu

        def media_usage_queries():
            with CaptureQueriesContext(connection) as queries:
                self.client.get("/api/v1/merchants/public-shop")
            return [q["sql"] for q in queries.captured_queries if "media_usage" in q["sql"]]

        add_product("one")
        self.assertEqual(len(media_usage_queries()), 1)

        for name in ("two", "three", "four"):
            add_product(name)
        self.assertEqual(len(media_usage_queries()), 1)
