"""商家经营域（平台管理后台 A02–A09）的接口级测试。

重点覆盖三条不能被破坏的红线：
1. 余额与流水同事务、余额不能为负；
2. 回款/返佣/提现退回都只发生一次（幂等）；
3. 权限码缺失时接口一律 403，不靠前端隐藏菜单。
"""

import json
import shutil
import tempfile
import uuid
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from accounts_buyers.models import BuyerAccount
from accounts_staff.models import (
    PlatformPermission,
    PlatformRole,
    StaffAccount,
    StaffRoleAssignment,
)
from accounts_staff.services import create_staff_session
from catalog.models import (
    LocalCategory,
    ProductCategory,
    SkuSourceIdentity,
    SourceCatalog,
    Spu,
    SpuDetail,
    SpuTranslation,
    SpuVideo,
)
from media.models import MediaAsset
from media.storage import store_bytes
from merchant_ops.models import (
    AfterSale,
    MerchantActivity,
    MerchantDepositEntry,
    MerchantReferral,
    MerchantWalletEntry,
    MerchantWithdrawal,
    ReferralCommission,
    ReferralProgram,
)
from merchant_ops.services import MerchantOpsError, record_wallet_entry, ship_merchant_order
from merchants.models import Merchant
from offers.models import Currency, Market, Offer
from orders.models import MerchantOrder, Order, OrderItem

ALL_PERMISSIONS = (
    "merchants.manage",
    "catalog.pool.manage",
    "catalog.listings.manage",
    "orders.manage",
    "finance.manage",
    "deposits.manage",
    "aftersales.manage",
    "activities.manage",
)


class CommerceTestBase(TestCase):
    def setUp(self):
        self.currency = Currency.objects.get(code="GBP")
        self.market = Market.objects.get(code="GB")
        self.staff = self._make_staff(ALL_PERMISSIONS, email="commerce@joybuy.test")
        token, _session = create_staff_session(
            staff=self.staff, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token

        self.merchant = Merchant.objects.create(
            slug="demo-store",
            display_name="演示店铺",
            onboarding_status=Merchant.OnboardingStatus.ACTIVE,
            admission_approved=True,
            deposit_initial_paid=True,
            referral_code="MTEST0001",
        )
        self.category = LocalCategory.objects.create(
            name="Kitchen", name_en="Kitchen", name_zh="厨房", slug="kitchen", path="kitchen"
        )

    def _make_staff(self, codes, email):
        role, _ = PlatformRole.objects.update_or_create(
            code=f"role-{email.split('@')[0]}",
            defaults={"name": "Test role", "is_system": False},
        )
        permissions = []
        for code in codes:
            permission, _ = PlatformPermission.objects.get_or_create(
                code=code, defaults={"name": code}
            )
            permissions.append(permission)
        role.permissions.set(permissions)
        staff, _ = StaffAccount.objects.get_or_create(
            email=email,
            defaults={
                "display_name": "测试管理员",
                "password": "x",
                "status": StaffAccount.Status.ACTIVE,
            },
        )
        staff.set_password("Passw0rd!demo")
        staff.save()
        StaffRoleAssignment.objects.get_or_create(staff=staff, role=role)
        return staff

    def make_staff_without_permissions(self):
        staff = self._make_staff((), email="nobody@joybuy.test")
        token, _session = create_staff_session(
            staff=staff, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token
        return staff

    def post_json(self, url, payload=None):
        return self.client.post(
            url, data=json.dumps(payload or {}), content_type="application/json"
        )

    def patch_json(self, url, payload=None):
        return self.client.patch(
            url, data=json.dumps(payload or {}), content_type="application/json"
        )

    def make_product(self, *, cost="10.00", price="20.00"):
        spu = Spu.objects.create(
            local_category=self.category,
            status=Spu.Status.ACTIVE,
            cost_price=Decimal(cost),
            retail_price=Decimal(price),
            description="演示商品",
            image_urls=["/media/demo.webp"],
            specs=[{"name": "颜色", "value": "黑色"}],
        )
        SpuTranslation.objects.create(spu=spu, locale="zh-CN", title="演示商品")
        return spu

    def make_offer(self, spu, *, cost="10.00", price="20.00", status=Offer.Status.ACTIVE):
        sku = spu.skus.create(specification={}, specification_signature="default")
        return Offer.objects.create(
            merchant=self.merchant,
            sku=sku,
            market=self.market,
            currency=self.currency,
            current_price=Decimal(price),
            cost_price=Decimal(cost),
            local_inventory=100,
            status=status,
            listed_at=timezone.now(),
        )

    def make_merchant_order(self, *, quantity=2, unit_price="20.00", unit_cost="10.00"):
        spu = self.make_product()
        offer = self.make_offer(spu, cost=unit_cost, price=unit_price)
        buyer = BuyerAccount.objects.create(email="buyer@joybuy.test", password="x")
        order = Order.objects.create(
            account=buyer,
            currency=self.currency,
            items_subtotal=Decimal(unit_price) * quantity,
            shipping_cost=Decimal("0"),
            total=Decimal(unit_price) * quantity,
            shipping_address={"region": "London"},
            payment_expires_at=timezone.now() + timedelta(hours=1),
        )
        merchant_order = MerchantOrder.objects.create(
            order=order,
            merchant=self.merchant,
            currency=self.currency.code,
            items_total=Decimal(unit_price) * quantity,
            cost_total=Decimal(unit_cost) * quantity,
        )
        OrderItem.objects.create(
            order=order,
            merchant_order=merchant_order,
            offer=offer,
            spu_public_id=str(spu.public_id),
            title="演示商品",
            quantity=quantity,
            unit_price=Decimal(unit_price),
            unit_cost=Decimal(unit_cost),
            currency=self.currency.code,
        )
        return merchant_order


class MerchantAdminApiTests(CommerceTestBase):
    def test_list_merchants_includes_pending_order_aggregate(self):
        self.make_merchant_order()
        response = self.client.get("/api/v1/admin/merchants")
        self.assertEqual(response.status_code, 200)
        row = next(
            item for item in response.json()["items"] if item["id"] == str(self.merchant.public_id)
        )
        self.assertEqual(row["pending_order_count"], 1)
        # 迭代02：待发货金额 = 成本价合计（不是零售额）。
        self.assertEqual(row["pending_order_amount"], "20.00")

    def test_review_with_deposit_moves_to_pending_deposit_then_active(self):
        merchant = Merchant.objects.create(slug="new-store", display_name="新店铺")
        url = f"/api/v1/admin/merchants/{merchant.public_id}/actions"

        response = self.post_json(
            url,
            {
                "action": "review",
                "approved": True,
                "require_deposit": True,
                "deposit_required": "500.00",
                "ban_after_days": 3,
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["merchant"]["status"], "PENDING_DEPOSIT")

        # 缴纳保证金达到应缴额后自动开店
        response = self.post_json(
            f"/api/v1/admin/deposits/{merchant.public_id}/actions",
            {"action": "recharge", "amount": "500.00"},
        )
        self.assertEqual(response.status_code, 200, response.content)
        merchant.refresh_from_db()
        self.assertEqual(merchant.onboarding_status, Merchant.OnboardingStatus.ACTIVE)
        self.assertTrue(merchant.deposit_initial_paid)

    def test_review_is_locked_after_first_decision(self):
        merchant = Merchant.objects.create(slug="locked-store", display_name="锁定店铺")
        url = f"/api/v1/admin/merchants/{merchant.public_id}/actions"
        self.post_json(url, {"action": "review", "approved": True, "ban_after_days": 4})
        response = self.post_json(url, {"action": "review", "approved": True, "ban_after_days": 9})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "ADMISSION_LOCKED")

    def test_wallet_adjustment_rejects_negative_target(self):
        response = self.patch_json(
            f"/api/v1/admin/merchants/{self.merchant.public_id}",
            {"wallet_balance": "-1.00"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "BALANCE_NEGATIVE")

    def test_credit_deduction_clamps_at_zero(self):
        # WP-42 拍板：超额扣减按 0 钳制，不再报 CREDIT_EXCEEDS_CURRENT。
        url = f"/api/v1/admin/merchants/{self.merchant.public_id}/actions"
        response = self.post_json(url, {"action": "deduct_credit", "points": "101"})
        self.assertEqual(response.status_code, 200)
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.credit_score, 0)

    def test_suspend_and_unsuspend_reset_fulfillment_clock(self):
        order = self.make_merchant_order()
        url = f"/api/v1/admin/merchants/{self.merchant.public_id}/actions"
        self.assertEqual(self.post_json(url, {"action": "suspend"}).status_code, 200)
        self.assertEqual(
            self.post_json(url, {"action": "unsuspend"}).status_code,
            200,
        )
        order.refresh_from_db()
        self.assertIsNotNone(order.fulfillment_reset_at)

    def test_missing_permission_returns_403(self):
        self.make_staff_without_permissions()
        response = self.client.get("/api/v1/admin/merchants")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "STAFF_PERMISSION_DENIED")

    def test_discount_change_reprices_listed_offers(self):
        """改折扣后已上架商品的成本价要重算（基数=零售价），顾客价保持不变。"""
        spu = self.make_product(cost="100.00", price="200.00")
        offer = self.make_offer(spu, cost="100.00", price="200.00")

        response = self.patch_json(
            f"/api/v1/admin/merchants/{self.merchant.public_id}", {"discount_rate": "20"}
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["merchant"]["repriced_offers"], 1)
        offer.refresh_from_db()
        # 2026-11-10 口径：成本价 = 零售价 × (1 - 20%) = 160.00（不是平台成本价 100 的 80.00）。
        self.assertEqual(offer.cost_price, Decimal("160.00"))
        self.assertEqual(offer.current_price, Decimal("200.00"))

        # 再设活动折扣并把商品标成活动商品 → 按活动折扣 30% 重算：200 × 70% = 140.00。
        Spu.objects.filter(pk=spu.pk).update(is_activity=True)
        response = self.patch_json(
            f"/api/v1/admin/merchants/{self.merchant.public_id}",
            {"discount_rate": "20", "activity_discount_rate": "30"},
        )
        self.assertEqual(response.status_code, 200, response.content)
        offer.refresh_from_db()
        self.assertEqual(offer.cost_price, Decimal("140.00"))

    def test_clearing_discount_resets_cost_to_retail_price(self):
        """清空折扣 = 减免 0% → 成本价 = 零售价（不再是商品池成本价）。"""
        spu = self.make_product(cost="50.00", price="90.00")
        offer = self.make_offer(spu, cost="40.00", price="90.00")
        response = self.patch_json(
            f"/api/v1/admin/merchants/{self.merchant.public_id}", {"discount_rate": ""}
        )
        self.assertEqual(response.status_code, 200, response.content)
        offer.refresh_from_db()
        self.assertEqual(offer.cost_price, Decimal("90.00"))


class ProductPoolApiTests(CommerceTestBase):
    def test_create_and_list_product(self):
        response = self.post_json(
            "/api/v1/admin/products",
            {
                "name": "测试炒锅",
                "category": str(self.category.public_id),
                "cost": "30.00",
                "price": "59.00",
                "description": "不粘锅",
                "images": ["/media/a.webp"],
                "specs": [{"name": "容量", "value": "28cm"}],
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        product = response.json()["product"]
        self.assertEqual(product["name"], "测试炒锅")

        listing = self.client.get("/api/v1/admin/products")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["total"], 1)

    def test_price_below_cost_is_rejected(self):
        response = self.post_json(
            "/api/v1/admin/products",
            {"name": "亏本商品", "cost": "50.00", "price": "20.00"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "PRICE_BELOW_COST")

    def test_listing_remove_is_idempotent(self):
        spu = self.make_product()
        offer = self.make_offer(spu)
        url = f"/api/v1/admin/merchant-listings/{offer.public_id}/actions"
        first = self.post_json(url, {"action": "remove"})
        self.assertEqual(first.status_code, 200)
        second = self.post_json(url, {"action": "remove"})
        self.assertEqual(second.status_code, 200)
        offer.refresh_from_db()
        self.assertEqual(offer.status, Offer.Status.INACTIVE)
        self.assertTrue(offer.removed_by_platform)

    def test_category_filter_includes_child_categories(self):
        """筛选只选父类目时，必须同时命中挂在其子类目上的商品。"""
        parent = LocalCategory.objects.create(
            name="Home & Living", name_zh="家居生活", slug="home-living", path="/2/", depth=0
        )
        child = LocalCategory.objects.create(
            parent=parent,
            name="Kitchen Essentials",
            name_zh="厨房用品",
            slug="kitchen-essentials",
            path="/2/3/",
            depth=1,
        )
        other_parent = LocalCategory.objects.create(
            name="Electronics", name_zh="电子产品", slug="electronics", path="/1/", depth=0
        )

        def make_spu(category, title):
            spu = Spu.objects.create(
                local_category=category,
                status=Spu.Status.ACTIVE,
                cost_price=Decimal("10.00"),
                retail_price=Decimal("20.00"),
            )
            SpuTranslation.objects.create(spu=spu, locale="zh-CN", title=title)
            return spu

        make_spu(parent, "父类目商品")
        make_spu(child, "子类目商品")
        make_spu(other_parent, "其它类目商品")

        response = self.client.get(f"/api/v1/admin/products?category={parent.public_id}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 2)
        self.assertEqual({item["name"] for item in payload["items"]}, {"父类目商品", "子类目商品"})

        sibling = self.client.get(f"/api/v1/admin/products?category={other_parent.public_id}")
        self.assertEqual(sibling.json()["total"], 1)
        self.assertEqual([item["name"] for item in sibling.json()["items"]], ["其它类目商品"])

    def test_categories_endpoint_exposes_depth_and_sort_order(self):
        """筛选下拉靠 depth/sort_order 只展示并按既定顺序排列父类目。"""
        parent = LocalCategory.objects.create(
            name="Home & Living", name_zh="家居生活", slug="home-living", path="/2/", depth=0
        )
        LocalCategory.objects.create(
            parent=parent,
            name="Cookware",
            name_zh="锅具",
            slug="cookware",
            path="/2/3/",
            depth=1,
            sort_order=1,
        )
        response = self.client.get("/api/v1/admin/categories")
        self.assertEqual(response.status_code, 200)
        items = {item["path"]: item for item in response.json()["items"]}
        self.assertEqual(items["/2/"]["depth"], 0)
        self.assertIn("sort_order", items["/2/"])
        self.assertEqual(items["/2/3/"]["depth"], 1)
        # 编辑表单的父子联动靠这两个字段：父类目带商家端品类映射，子类目带 parent_id。
        self.assertEqual(items["/2/"]["merchant_category"], "HOME")
        self.assertEqual(items["/2/3/"]["parent_id"], items["/2/"]["id"])

    def test_create_product_persists_merchant_category(self):
        response = self.post_json(
            "/api/v1/admin/products",
            {
                "name": "父品类商品",
                "cost": "10.00",
                "price": "20.00",
                "merchant_category": "home",
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        spu = Spu.objects.get(public_id=response.json()["product"]["id"])
        self.assertEqual(spu.merchant_category, "HOME")

    def test_update_product_refreshes_search_document(self):
        """改品类后购物端类目页要跟着变：搜索文档必须同步重建。"""
        from catalog.models import ProductSearchDocument
        from catalog.search_services import rebuild_search_document

        spu = self.make_product()
        self.make_offer(spu)
        rebuild_search_document(spu, market=self.market)
        document = ProductSearchDocument.objects.get(spu=spu)
        self.assertEqual(document.local_category_id, self.category.pk)

        parent = LocalCategory.objects.create(
            name="Home & Living", name_zh="家居生活", slug="home-living", path="/2/", depth=0
        )
        response = self.patch_json(
            f"/api/v1/admin/products/{spu.public_id}", {"category": str(parent.public_id)}
        )
        self.assertEqual(response.status_code, 200, response.content)
        document.refresh_from_db()
        self.assertEqual(document.local_category_id, parent.pk)


class ProductPoolPublishTests(CommerceTestBase):
    """管理端上架即可售（2026-11-10）：激活商家报价并重建搜索文档。

    购物端搜索只认 `ProductSearchDocument`，文档又要求 SPU 与 Offer 都 ACTIVE。
    此前管理端「上架」只改 SPU 状态，导入留下的 DRAFT Offer 不激活，
    商品在购物端永远搜不到。
    """

    def make_draft_product(self, *, price="200.00"):
        spu = Spu.objects.create(
            local_category=self.category,
            status=Spu.Status.DRAFT,
            cost_price=None,
            retail_price=Decimal(price) if price is not None else None,
        )
        SpuTranslation.objects.create(spu=spu, locale="zh-CN", title="待上架商品")
        return spu

    def make_draft_offer(self, spu, *, price="200.00"):
        sku = spu.skus.create(specification={}, specification_signature="default")
        return Offer.objects.create(
            merchant=self.merchant,
            sku=sku,
            market=self.market,
            currency=self.currency,
            current_price=Decimal(price),
            cost_price=None,
            local_inventory=10,
            status=Offer.Status.DRAFT,
        )

    def publish(self, spu):
        return self.post_json(
            f"/api/v1/admin/products/{spu.public_id}/actions", {"action": "publish"}
        )

    def test_publish_activates_draft_offer_and_indexes_product(self):
        from catalog.models import ProductSearchDocument

        Merchant.objects.filter(pk=self.merchant.pk).update(discount_rate=Decimal("20.00"))
        spu = self.make_draft_product(price="200.00")
        offer = self.make_draft_offer(spu)

        response = self.publish(spu)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["product"]["activated_offers"], 1)
        spu.refresh_from_db()
        offer.refresh_from_db()
        self.assertEqual(spu.status, Spu.Status.ACTIVE)
        self.assertEqual(offer.status, Offer.Status.ACTIVE)
        self.assertEqual(offer.cost_price, Decimal("160.00"))
        self.assertEqual(offer.current_price, Decimal("200.00"))
        self.assertIsNotNone(offer.listed_at)
        document = ProductSearchDocument.objects.get(spu=spu)
        self.assertTrue(document.is_searchable)

    def test_republish_after_platform_unpublish_restores_visibility(self):
        from catalog.models import ProductSearchDocument

        spu = self.make_product(price="20.00")
        offer = self.make_offer(spu, price="20.00")

        response = self.post_json(
            f"/api/v1/admin/products/{spu.public_id}/actions", {"action": "unpublish"}
        )
        self.assertEqual(response.status_code, 200, response.content)
        offer.refresh_from_db()
        self.assertEqual(offer.status, Offer.Status.INACTIVE)
        self.assertTrue(offer.removed_by_platform)
        self.assertFalse(ProductSearchDocument.objects.filter(spu=spu).exists())

        response = self.publish(spu)
        self.assertEqual(response.status_code, 200, response.content)
        offer.refresh_from_db()
        self.assertEqual(offer.status, Offer.Status.ACTIVE)
        self.assertFalse(offer.removed_by_platform)
        self.assertTrue(ProductSearchDocument.objects.filter(spu=spu, is_searchable=True).exists())

    def test_publish_without_offers_is_rejected(self):
        spu = self.make_draft_product()
        response = self.publish(spu)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"]["code"], "PRODUCT_OFFER_MISSING")
        spu.refresh_from_db()
        self.assertEqual(spu.status, Spu.Status.DRAFT)

    def test_publish_without_retail_price_is_rejected(self):
        spu = self.make_draft_product(price=None)
        offer = self.make_draft_offer(spu, price="0.00")
        response = self.publish(spu)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"]["code"], "PRODUCT_PRICE_MISSING")
        spu.refresh_from_db()
        offer.refresh_from_db()
        self.assertEqual(spu.status, Spu.Status.DRAFT)
        self.assertEqual(offer.status, Offer.Status.DRAFT)

    def test_publish_activates_crawled_merchant_without_admission_review(self):
        """爬虫导入的商家常未走完入驻审核，平台主动上架不受这些自查条件限制。"""
        Merchant.objects.filter(pk=self.merchant.pk).update(admission_approved=False)
        spu = self.make_draft_product()
        offer = self.make_draft_offer(spu)
        response = self.publish(spu)
        self.assertEqual(response.status_code, 200, response.content)
        offer.refresh_from_db()
        self.assertEqual(offer.status, Offer.Status.ACTIVE)

    def test_publish_skips_suspended_merchant(self):
        Merchant.objects.filter(pk=self.merchant.pk).update(
            onboarding_status=Merchant.OnboardingStatus.SUSPENDED
        )
        spu = self.make_draft_product()
        offer = self.make_draft_offer(spu)
        response = self.publish(spu)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"]["code"], "PRODUCT_OFFER_MISSING")
        offer.refresh_from_db()
        self.assertEqual(offer.status, Offer.Status.DRAFT)

    def test_merchant_unlisted_offer_is_not_revived(self):
        """商家自己下架（removed_by_platform=False）的报价不随平台上架复活。"""
        spu = self.make_draft_product()
        offer = self.make_draft_offer(spu)
        Offer.objects.filter(pk=offer.pk).update(
            status=Offer.Status.INACTIVE, removed_by_platform=False
        )
        response = self.publish(spu)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"]["code"], "PRODUCT_OFFER_MISSING")
        offer.refresh_from_db()
        self.assertEqual(offer.status, Offer.Status.INACTIVE)


class ProductPoolCrawledDetailTests(CommerceTestBase):
    """商品池管理端暴露爬虫详情（2026-11-09）。

    列表只带轻量摘要（has_detail / 区块数 / 规格表数 / 视频数 / AI 预览），
    详情接口返回完整 content_sections / specification_tables / spec_options /
    videos / ai_summary 与爬到的商品类目，供详情抽屉只读展示。
    """

    def setUp(self):
        super().setUp()
        self.media_root = tempfile.mkdtemp(prefix="joybuy-admin-pool-media-")
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media_root)
        override.enable()
        self.addCleanup(override.disable)

    def _make_crawled_product(self):
        spu = self.make_product()
        sku = spu.skus.create(
            specification={"系列": "256GB"}, specification_signature="series-256gb"
        )
        SkuSourceIdentity.objects.create(
            sku=sku,
            source_system="joybuy",
            source_id="src-sku-1",
            first_seen_at=timezone.now(),
            last_seen_at=timezone.now(),
        )
        SpuDetail.objects.create(
            spu=spu,
            content_sections=[
                {
                    "title": "商品详情",
                    "blocks": [
                        {"type": "heading", "text": "终极 Pro 相机系统"},
                        {"type": "paragraph", "text": "三个先进的 4800 万像素后置摄像头。"},
                    ],
                    "text": "终极 Pro 相机系统\n三个先进的 4800 万像素后置摄像头。",
                    "images": ["/media/products/original/aa/bb/section.png"],
                }
            ],
            specification_tables=[
                {
                    "title": "技术规格",
                    "columns": ["属性", "值"],
                    "rows": [{"name": "型号", "value": "A3101"}],
                }
            ],
            specifications=[{"group": "技术规格", "name": "型号", "value": "A3101"}],
            spec_options=[
                {
                    "name": "系列",
                    "values": [
                        {
                            "value": "256GB",
                            "image_url": "/media/products/original/cc/dd/spec.png",
                            "sku_ids": ["src-sku-1"],
                        }
                    ],
                }
            ],
            ai_summary="用户普遍认可画质与续航，性价比评价很高。" * 5,
            ai_summary_title="内容由人工智能总结自用户评价",
            ai_summary_tags=["画质好", "续航强"],
        )
        video, _ = store_bytes(
            b"fake-mp4-bytes",
            kind=MediaAsset.Kind.VIDEO,
            mime_type="video/mp4",
            source_url="https://cdn.test/v.mp4",
        )
        poster, _ = store_bytes(
            b"fake-poster-bytes",
            kind=MediaAsset.Kind.PRODUCT,
            mime_type="image/png",
            source_url="https://cdn.test/cover.png",
        )
        SpuVideo.objects.create(
            spu=spu,
            video=video,
            poster=poster,
            duration_ms=23000,
            source_video_id="vid-1",
            source_url="https://cdn.test/v.mp4",
            sort_order=0,
        )
        return spu, sku

    def test_detail_payload_includes_crawled_detail(self):
        spu, sku = self._make_crawled_product()

        response = self.client.get(f"/api/v1/admin/products/{spu.public_id}")

        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()["product"]
        # 摘要字段。
        self.assertTrue(data["has_detail"])
        self.assertEqual(data["section_count"], 1)
        self.assertEqual(data["spec_table_count"], 1)
        self.assertEqual(data["video_count"], 1)
        self.assertTrue(data["source_updated_at"])
        # 详情接口返回完整 AI 摘要（截断预览只在列表摘要里）。
        self.assertEqual(len(data["ai_summary"]), 100)
        # 完整结构化详情。
        self.assertEqual(data["content_sections"][0]["blocks"][0]["type"], "heading")
        self.assertEqual(
            data["content_sections"][0]["images"], ["/media/products/original/aa/bb/section.png"]
        )
        self.assertEqual(data["specification_tables"][0]["rows"][0]["name"], "型号")
        self.assertEqual(data["specifications"][0]["group"], "技术规格")
        # spec_options 的 sku_ids 与购物端一致：映射为 Sku.public_id。
        self.assertEqual(data["spec_options"][0]["name"], "系列")
        self.assertEqual(data["spec_options"][0]["values"][0]["sku_ids"], [str(sku.public_id)])
        # 视频：本地 /media 可播放 URL + 封面 + 时长。
        self.assertEqual(len(data["videos"]), 1)
        self.assertTrue(data["videos"][0]["url"].startswith("/media/videos/original/"))
        self.assertTrue(data["videos"][0]["poster"].startswith("/media/products/original/"))
        self.assertEqual(data["videos"][0]["duration_ms"], 23000)
        self.assertEqual(data["videos"][0]["duration"], 23.0)
        self.assertEqual(data["videos"][0]["sort_order"], 0)
        # AI 摘要。
        self.assertEqual(data["ai_summary_title"], "内容由人工智能总结自用户评价")
        self.assertEqual(data["ai_summary_tags"], ["画质好", "续航强"])
        # 旧契约字段全部保留（skus 等）。
        for field in ("id", "name", "images", "specs", "description", "skus", "status"):
            self.assertIn(field, data)

    def test_list_payload_summary_fields(self):
        spu, _sku = self._make_crawled_product()
        plain = self.make_product()

        response = self.client.get("/api/v1/admin/products")

        self.assertEqual(response.status_code, 200, response.content)
        rows = {item["id"]: item for item in response.json()["items"]}
        row = rows[str(spu.public_id)]
        self.assertTrue(row["has_detail"])
        self.assertEqual(row["section_count"], 1)
        self.assertEqual(row["spec_table_count"], 1)
        self.assertEqual(row["video_count"], 1)
        self.assertTrue(row["source_updated_at"])
        self.assertLessEqual(len(row["ai_summary"]), 81)
        # 没有爬虫详情的商品：摘要为空结构，不报错。
        plain_row = rows[str(plain.public_id)]
        self.assertFalse(plain_row["has_detail"])
        self.assertEqual(plain_row["section_count"], 0)
        self.assertEqual(plain_row["spec_table_count"], 0)
        self.assertEqual(plain_row["video_count"], 0)
        self.assertEqual(plain_row["ai_summary"], "")
        self.assertIsNone(plain_row["source_updated_at"])

    def test_detail_payload_without_detail_returns_empty_structures(self):
        spu = self.make_product()

        response = self.client.get(f"/api/v1/admin/products/{spu.public_id}")

        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()["product"]
        self.assertFalse(data["has_detail"])
        self.assertEqual(data["content_sections"], [])
        self.assertEqual(data["specification_tables"], [])
        self.assertEqual(data["specifications"], [])
        self.assertEqual(data["spec_options"], [])
        self.assertEqual(data["videos"], [])
        self.assertEqual(data["ai_summary"], "")
        self.assertEqual(data["ai_summary_tags"], [])
        self.assertEqual(data["product_category"], [])
        # 没有媒体库画廊时回退手工 image_urls。
        self.assertEqual(data["gallery"], ["/media/demo.webp"])

    def test_detail_payload_exposes_crawled_product_category(self):
        spu = self.make_product()
        catalog = SourceCatalog.objects.create(source_system="joybuy", display_name="Joybuy UK")
        parent = ProductCategory.objects.create(
            catalog=catalog, source_id="288", name="厨具餐具", depth=0, path="288"
        )
        child = ProductCategory.objects.create(
            catalog=catalog, source_id="361", name="锅具", depth=1, parent=parent, path="288/361"
        )
        spu.product_category = child
        spu.save(update_fields=["product_category"])

        response = self.client.get(f"/api/v1/admin/products/{spu.public_id}")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.json()["product"]["product_category"],
            [
                {"id": "288", "name": "厨具餐具", "depth": 0},
                {"id": "361", "name": "锅具", "depth": 1},
            ],
        )


class ProductPoolDetailContentTests(CommerceTestBase):
    """图文详情人工编辑 + 成本价可选（2026-11-10）。

    PATCH ``content_sections`` 保存进 SpuDetail 并置 ``content_source=manual``；
    图片只接受本地 ``/media/...``；成本价在 POST/PATCH 里可留空（爬虫商品
    本来就没有成本价），零售价仍必填。
    """

    def _content_sections(self):
        return [
            {
                "title": "商品详情",
                "blocks": [
                    {"type": "heading", "text": "终极 Pro 相机系统"},
                    {"type": "paragraph", "text": "三个先进的 4800 万像素后置摄像头。"},
                ],
                "images": ["/media/products/original/aa/bb/section.png"],
            }
        ]

    def test_patch_content_creates_detail_and_marks_manual(self):
        spu = self.make_product()
        self.assertFalse(SpuDetail.objects.filter(spu=spu).exists())

        response = self.patch_json(
            f"/api/v1/admin/products/{spu.public_id}",
            {"content_sections": self._content_sections()},
        )

        self.assertEqual(response.status_code, 200, response.content)
        detail = SpuDetail.objects.get(spu=spu)
        self.assertEqual(detail.content_source, SpuDetail.ContentSource.MANUAL)
        self.assertEqual(detail.content_sections[0]["title"], "商品详情")
        self.assertEqual(detail.content_sections[0]["blocks"][0]["type"], "heading")
        self.assertEqual(
            detail.content_sections[0]["images"], ["/media/products/original/aa/bb/section.png"]
        )
        # 回包带上保存后的区块，前端据此刷新抽屉。
        self.assertEqual(response.json()["product"]["content_sections"], detail.content_sections)
        self.assertEqual(response.json()["product"]["content_source"], "manual")
        # 详情接口能取到人工内容与来源标记。
        data = self.client.get(f"/api/v1/admin/products/{spu.public_id}").json()["product"]
        self.assertEqual(data["content_source"], "manual")
        self.assertEqual(data["section_count"], 1)
        # 审计事件留痕。
        from audit.models import AuditLog

        self.assertTrue(
            AuditLog.objects.filter(
                action="PRODUCT_DETAIL_UPDATED", target_id=str(spu.public_id)
            ).exists()
        )

    def test_patch_content_updates_existing_detail_and_keeps_other_fields(self):
        spu = self.make_product()
        SpuDetail.objects.create(
            spu=spu,
            content_sections=[{"title": "旧区块", "blocks": [], "images": []}],
            specification_tables=[
                {
                    "title": "技术规格",
                    "columns": ["属性", "值"],
                    "rows": [{"name": "型号", "value": "A1"}],
                }
            ],
        )

        response = self.patch_json(
            f"/api/v1/admin/products/{spu.public_id}",
            {"content_sections": self._content_sections()},
        )

        self.assertEqual(response.status_code, 200, response.content)
        detail = SpuDetail.objects.get(spu=spu)
        self.assertEqual(detail.content_source, SpuDetail.ContentSource.MANUAL)
        self.assertEqual(detail.content_sections[0]["title"], "商品详情")
        # 图文区块之外的爬虫字段原样保留。
        self.assertEqual(detail.specification_tables[0]["rows"][0]["name"], "型号")

    def test_patch_content_rejects_external_image_url(self):
        spu = self.make_product()

        response = self.patch_json(
            f"/api/v1/admin/products/{spu.public_id}",
            {
                "content_sections": [
                    {
                        "title": "区块",
                        "blocks": [{"type": "paragraph", "text": "正文"}],
                        "images": ["https://images.joy-sourcing.com/detail.png"],
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "CONTENT_IMAGE_INVALID")
        # 校验失败不落地 SpuDetail。
        self.assertFalse(SpuDetail.objects.filter(spu=spu).exists())

    def test_patch_content_rejects_unknown_block_type(self):
        spu = self.make_product()

        response = self.patch_json(
            f"/api/v1/admin/products/{spu.public_id}",
            {
                "content_sections": [
                    {"title": "区块", "blocks": [{"type": "quote", "text": "引用"}], "images": []}
                ]
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "CONTENT_BLOCK_TYPE_INVALID")

    def test_patch_content_rejects_overlong_text(self):
        spu = self.make_product()

        response = self.patch_json(
            f"/api/v1/admin/products/{spu.public_id}",
            {
                "content_sections": [
                    {
                        "title": "区块",
                        "blocks": [{"type": "paragraph", "text": "长" * 5001}],
                        "images": [],
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "CONTENT_TEXT_TOO_LONG")

    def test_post_without_cost_creates_product_with_null_cost(self):
        response = self.post_json(
            "/api/v1/admin/products",
            {"name": "无成本商品", "price": "20.00"},
        )

        self.assertEqual(response.status_code, 201, response.content)
        product = response.json()["product"]
        self.assertIsNone(product["cost"])
        spu = Spu.objects.get(public_id=product["id"])
        self.assertIsNone(spu.cost_price)
        self.assertEqual(spu.retail_price, Decimal("20.00"))

    def test_post_with_zero_cost_is_rejected(self):
        response = self.post_json(
            "/api/v1/admin/products",
            {"name": "零成本商品", "cost": "0", "price": "20.00"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "PRICE_INVALID")

    def test_patch_without_cost_keeps_existing_value(self):
        spu = self.make_product(cost="10.00", price="20.00")

        response = self.patch_json(f"/api/v1/admin/products/{spu.public_id}", {"name": "改名"})

        self.assertEqual(response.status_code, 200, response.content)
        spu.refresh_from_db()
        self.assertEqual(spu.cost_price, Decimal("10.00"))

    def test_patch_empty_cost_clears_value(self):
        spu = self.make_product(cost="10.00", price="20.00")

        response = self.patch_json(f"/api/v1/admin/products/{spu.public_id}", {"cost": ""})

        self.assertEqual(response.status_code, 200, response.content)
        spu.refresh_from_db()
        self.assertIsNone(spu.cost_price)
        self.assertEqual(spu.retail_price, Decimal("20.00"))

    def test_patch_price_below_cost_is_still_rejected(self):
        spu = self.make_product(cost="10.00", price="20.00")

        response = self.patch_json(
            f"/api/v1/admin/products/{spu.public_id}",
            {"cost": "50.00", "price": "20.00"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "PRICE_BELOW_COST")


class MerchantOrderApiTests(CommerceTestBase):
    def test_ship_deducts_cost_and_complete_settles_once(self):
        record_wallet_entry(
            merchant_id=self.merchant.pk,
            kind=MerchantWalletEntry.Kind.RECHARGE,
            amount=Decimal("100.00"),
            idempotency_key="seed-wallet",
        )
        order = self.make_merchant_order(quantity=2, unit_price="20.00", unit_cost="10.00")

        # 发货是商家端动作（确认发货即扣成本、进度到「待出库」）
        ship_merchant_order(order, actor=self.staff)
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.wallet_balance, Decimal("80.00"))

        url = f"/api/v1/admin/merchant-orders/{order.public_id}/actions"
        self.assertEqual(self.post_json(url, {"action": "complete_all"}).status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, MerchantOrder.Status.COMPLETED)
        self.assertTrue(order.settled)
        self.merchant.refresh_from_db()
        # 100 - 20 成本 + 40 回款
        self.assertEqual(self.merchant.wallet_balance, Decimal("120.00"))

        # 重复完成后不再入账
        self.post_json(url, {"action": "complete_all"})
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.wallet_balance, Decimal("120.00"))
        self.assertEqual(
            MerchantWalletEntry.objects.filter(
                merchant=self.merchant, kind=MerchantWalletEntry.Kind.ORDER_SETTLEMENT
            ).count(),
            1,
        )

    def test_ship_without_enough_balance_is_rejected(self):
        order = self.make_merchant_order()
        with self.assertRaises(MerchantOpsError) as ctx:
            ship_merchant_order(order, actor=self.staff)
        self.assertEqual(ctx.exception.code, "INSUFFICIENT_WALLET_BALANCE")
        order.refresh_from_db()
        self.assertEqual(order.status, MerchantOrder.Status.PENDING)
        self.assertEqual(order.progress, -1)

    def test_progress_cannot_move_backwards(self):
        record_wallet_entry(
            merchant_id=self.merchant.pk,
            kind=MerchantWalletEntry.Kind.RECHARGE,
            amount=Decimal("100.00"),
            idempotency_key="seed-wallet-2",
        )
        order = self.make_merchant_order()
        ship_merchant_order(order, actor=self.staff)
        url = f"/api/v1/admin/merchant-orders/{order.public_id}/actions"
        self.post_json(url, {"action": "advance", "node_index": 3})
        response = self.post_json(url, {"action": "advance", "node_index": 2})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "NODE_NOT_FORWARD")

    def test_created_at_cannot_be_later_than_first_node(self):
        # 迭代02：只有已完成订单能改下单时间 + 节点时间不能晚于当前系统时间。
        order = self.make_merchant_order()
        url = f"/api/v1/admin/merchant-orders/{order.public_id}"
        first_node = timezone.now() - timedelta(hours=2)
        MerchantOrder.objects.filter(pk=order.pk).update(
            status=MerchantOrder.Status.COMPLETED,
            node_times=[first_node.isoformat()] + [None] * 7,
            progress=7,
        )
        order.refresh_from_db()
        response = self.patch_json(
            url, {"created_at": (timezone.now() - timedelta(hours=1)).isoformat()}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "CREATED_AFTER_NODE")

    def test_node_times_must_be_ordered(self):
        order = self.make_merchant_order()
        url = f"/api/v1/admin/merchant-orders/{order.public_id}"
        # 下单时间提前到 3 小时前，避免先触发"早于下单时间"校验。
        MerchantOrder.objects.filter(pk=order.pk).update(
            created_at=timezone.now() - timedelta(hours=3)
        )
        first = (timezone.now() - timedelta(hours=2)).isoformat()
        second = (timezone.now() - timedelta(hours=1)).isoformat()
        response = self.patch_json(url, {"node_times": [second, first]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "NODE_OUT_OF_ORDER")


class FinanceApiTests(CommerceTestBase):
    def _make_withdrawal(self, amount="50.00"):
        record_wallet_entry(
            merchant_id=self.merchant.pk,
            kind=MerchantWalletEntry.Kind.RECHARGE,
            amount=Decimal("100.00"),
            idempotency_key="seed-withdrawal-wallet",
        )
        from merchant_ops.services import reserve_withdrawal

        withdrawal = MerchantWithdrawal.objects.create(
            merchant=self.merchant,
            method=MerchantWithdrawal.Method.BANK,
            amount=Decimal(amount),
            bank_name="招商银行",
            bank_account="6225880212345678",
            bank_holder="张三",
            bank_branch="上海分行",
            bank_code="0012",
        )
        reserve_withdrawal(self.merchant, withdrawal=withdrawal, actor=self.staff)
        self.merchant.refresh_from_db()
        return withdrawal

    def test_reject_returns_balance_only_once(self):
        withdrawal = self._make_withdrawal()
        self.assertEqual(self.merchant.wallet_balance, Decimal("50.00"))
        url = f"/api/v1/admin/finance/withdrawals/{withdrawal.public_id}/actions"
        self.assertEqual(
            self.post_json(url, {"action": "reject", "reason": "资料不符"}).status_code, 200
        )
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.wallet_balance, Decimal("100.00"))

        # 已打回状态再打回被状态机拦住
        response = self.post_json(url, {"action": "reject"})
        self.assertEqual(response.status_code, 409)
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.wallet_balance, Decimal("100.00"))

    def test_approve_transfer_and_pay(self):
        withdrawal = self._make_withdrawal()
        url = f"/api/v1/admin/finance/withdrawals/{withdrawal.public_id}/actions"
        response = self.post_json(url, {"action": "approve", "fee": "2.00"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["withdrawal"]["net_amount"], "48.00")
        # 迭代02：审核通过后直接进入【转账中】（不再需要出款凭证）。
        self.assertEqual(response.json()["withdrawal"]["state"], "TRANSFERRING")

        response = self.post_json(url, {"action": "mark_paid"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["withdrawal"]["state"], "PAID")
        self.merchant.refresh_from_db()
        # 出款不再扣一次可用余额
        self.assertEqual(self.merchant.wallet_balance, Decimal("50.00"))

    def test_approve_then_fail_returns_balance(self):
        """审核通过→转账失败（填原因）→ 立马退回余额。"""
        withdrawal = self._make_withdrawal()
        url = f"/api/v1/admin/finance/withdrawals/{withdrawal.public_id}/actions"
        self.post_json(url, {"action": "approve", "fee": "0"})
        response = self.post_json(url, {"action": "mark_failed", "reason": "卡号输入错误"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["withdrawal"]["state"], "FAILED")
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.wallet_balance, Decimal("100.00"))

    def test_recharge_creates_ledger_entry(self):
        response = self.post_json(
            "/api/v1/admin/finance/recharges",
            {"merchant_id": str(self.merchant.public_id), "amount": "88.80"},
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.wallet_balance, Decimal("88.80"))
        self.assertEqual(
            MerchantWalletEntry.objects.filter(
                merchant=self.merchant, kind=MerchantWalletEntry.Kind.RECHARGE
            ).count(),
            1,
        )


class DepositApiTests(CommerceTestBase):
    def test_deposit_adjust_allows_zero_and_records_delta(self):
        self.merchant.deposit_enabled = True
        self.merchant.deposit_required = Decimal("500.00")
        self.merchant.deposit_balance = Decimal("300.00")
        self.merchant.deposit_initial_paid = False
        self.merchant.save(
            update_fields=[
                "deposit_enabled",
                "deposit_required",
                "deposit_balance",
                "deposit_initial_paid",
            ]
        )
        response = self.post_json(
            f"/api/v1/admin/deposits/{self.merchant.public_id}/actions",
            {"action": "adjust", "balance": "0"},
        )
        self.assertEqual(response.status_code, 200, response.content)
        entry = MerchantDepositEntry.objects.get(merchant=self.merchant)
        self.assertEqual(entry.amount, Decimal("-300.00"))
        self.assertEqual(entry.balance_after, Decimal("0"))

    def test_deposit_recharge_rejected_when_not_enabled(self):
        response = self.post_json(
            f"/api/v1/admin/deposits/{self.merchant.public_id}/actions",
            {"action": "recharge", "amount": "100"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "DEPOSIT_NOT_ENABLED")


class AfterSaleApiTests(CommerceTestBase):
    def test_platform_decision_closes_after_sale(self):
        order = self.make_merchant_order()
        record = AfterSale.objects.create(
            merchant=self.merchant,
            order=order.order,
            merchant_order=order,
            kind=AfterSale.Kind.COMPLAINT,
            issue="包装破损",
        )
        url = f"/api/v1/admin/after-sales/{record.public_id}/actions"
        response = self.post_json(url, {"action": "decide", "decision": "COMPLETE"})
        self.assertEqual(response.status_code, 200, response.content)
        record.refresh_from_db()
        self.assertEqual(record.state, AfterSale.State.COMPLETED)
        self.assertEqual(record.events.count(), 1)

        # 已结束的售后不能重复处理
        response = self.post_json(url, {"action": "decide", "decision": "COMPLETE"})
        self.assertEqual(response.status_code, 409)

    def test_return_completion_blocked_after_order_completed(self):
        order = self.make_merchant_order()
        order.order.status = "COMPLETED"
        order.order.save(update_fields=["status"])
        record = AfterSale.objects.create(
            merchant=self.merchant,
            order=order.order,
            merchant_order=order,
            kind=AfterSale.Kind.RETURN,
            issue="尺码不合适",
        )
        response = self.post_json(
            f"/api/v1/admin/after-sales/{record.public_id}/actions",
            {"action": "decide", "decision": "COMPLETE"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "RETURN_AFTER_RECEIVED")


class ReferralApiTests(CommerceTestBase):
    def test_program_rejects_non_zero_first_tier(self):
        response = self.client.put(
            "/api/v1/admin/referrals/program",
            data=json.dumps({"tiers": [{"min": "100", "rate": "1"}], "valid_months": 12}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "TIER_FIRST_NOT_ZERO")

    def test_commission_calculated_and_paid_once(self):
        program = ReferralProgram.load()
        program.tiers = [
            {"min": "0", "rate": "1"},
            {"min": "10000", "rate": "2"},
            {"min": "50000", "rate": "3"},
        ]
        program.valid_months = 12
        program.save()

        referee = Merchant.objects.create(
            slug="new-referee",
            display_name="新人店铺",
            onboarding_status=Merchant.OnboardingStatus.ACTIVE,
            admission_approved=True,
            deposit_initial_paid=True,
            referral_code="MREFEREE1",
        )
        # 新人必须在上个核算月之前入驻，否则不属于该月返佣范围
        Merchant.objects.filter(pk=referee.pk).update(
            created_at=timezone.now() - timedelta(days=120)
        )
        referee.refresh_from_db()
        MerchantReferral.objects.create(
            referrer=self.merchant, referee=referee, code_used=self.merchant.referral_code
        )

        # 上个月发货 20000，落在 2% 档
        shipped_order = self.make_merchant_order(
            quantity=1000, unit_price="20.00", unit_cost="10.00"
        )
        shipped_order.merchant = referee
        shipped_order.shipped_at = timezone.localtime().replace(day=1).replace(
            hour=0, minute=0, second=0
        ) - timedelta(days=1)
        shipped_order.save(update_fields=["merchant", "shipped_at"])

        response = self.post_json("/api/v1/admin/referrals/calculate", {})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["count"], 1)

        commission = ReferralCommission.objects.get()
        # 迭代02：计佣基数 = 发货成功订单的成本价合计（10000），不是零售额。
        self.assertEqual(commission.rate, Decimal("2.000"))
        self.assertEqual(commission.shipped_amount, Decimal("10000.0000"))
        self.assertEqual(commission.amount, Decimal("200.0000"))

        url = f"/api/v1/admin/referrals/commissions/{commission.public_id}/actions"
        self.assertEqual(self.post_json(url, {"action": "pay"}).status_code, 200)
        self.assertEqual(self.post_json(url, {"action": "pay"}).status_code, 200)
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.wallet_balance, Decimal("200.00"))
        self.assertEqual(
            MerchantWalletEntry.objects.filter(
                merchant=self.merchant,
                kind=MerchantWalletEntry.Kind.REFERRAL_COMMISSION,
            ).count(),
            1,
        )

    def test_only_one_referral_activity_allowed(self):
        payload = {
            "title": "推荐返佣",
            "start": "2026-01-01",
            "is_referral": True,
        }
        first = self.post_json("/api/v1/admin/activities", payload)
        self.assertEqual(first.status_code, 201, first.content)
        second = self.post_json("/api/v1/admin/activities", payload)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["error"]["code"], "REFERRAL_ACTIVITY_EXISTS")
        self.assertEqual(MerchantActivity.objects.filter(is_referral=True).count(), 1)


class WalletServiceTests(CommerceTestBase):
    def test_idempotency_key_prevents_double_entry(self):
        first = record_wallet_entry(
            merchant_id=self.merchant.pk,
            kind=MerchantWalletEntry.Kind.ADJUSTMENT,
            amount=Decimal("10.00"),
            idempotency_key="same-key",
        )
        second = record_wallet_entry(
            merchant_id=self.merchant.pk,
            kind=MerchantWalletEntry.Kind.ADJUSTMENT,
            amount=Decimal("10.00"),
            idempotency_key="same-key",
        )
        self.assertEqual(first.pk, second.pk)
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.wallet_balance, Decimal("10.00"))

    def test_negative_balance_is_rejected(self):
        with self.assertRaises(MerchantOpsError):
            record_wallet_entry(
                merchant_id=self.merchant.pk,
                kind=MerchantWalletEntry.Kind.ADJUSTMENT,
                amount=Decimal("-1.00"),
            )

    def test_unknown_merchant_returns_404(self):
        response = self.client.get(f"/api/v1/admin/merchants/{uuid.uuid4()}")
        self.assertEqual(response.status_code, 404)
