"""第二轮（A10–A17）接口测试。

覆盖红线：
1. 只读账号（仅 ``*.view``）能进模块但不能写；
2. 白名单充值/消费幂等，余额不能为负；
3. 商品好评只能推给「该店已上架」的商品；
4. 平台回复通知后商家端重新未读；
5. 超级管理员不能停用自己（防自锁）。
"""

import json
import uuid
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts_buyers.models import BuyerAccount, BuyerWalletEntry
from accounts_buyers.services import recharge_buyer, record_buyer_wallet_entry
from accounts_staff.models import (
    PlatformPermission,
    PlatformRole,
    StaffAccount,
    StaffRoleAssignment,
)
from accounts_staff.services import create_staff_session, get_staff_permission_codes
from catalog.models import LocalCategory, Spu, SpuTranslation
from content.models import HomeBanner
from merchant_ops.models import SupportConversation, SupportMessage
from merchants.models import Merchant
from notifications.models import MerchantNotification
from offers.models import Currency, Market, Offer

FULL = (
    # 只给 manage，view 由 get_staff_permission_codes 隐式补齐
    "cms.banners.manage",
    "notifications.manage",
    "support.manage",
    "buyers.manage",
    "whitelist.manage",
    "merchants.growth.manage",
    "staff.roles.manage",
    "audit.logs.view",
    "audit.logs.export",
)
READ_ONLY = ("cms.banners.view", "notifications.view", "audit.logs.view")


class Round2Base(TestCase):
    def setUp(self):
        self.currency = Currency.objects.get(code="GBP")
        self.market = Market.objects.get(code="GB")
        self.staff = self._make_staff("round2-full@joybuy.test", FULL)
        self._login(self.staff)

        self.merchant = Merchant.objects.create(
            slug="r2-store",
            display_name="第二轮店铺",
            onboarding_status=Merchant.OnboardingStatus.ACTIVE,
            admission_approved=True,
            deposit_initial_paid=True,
            referral_code="MR2STORE1",
        )
        self.category = LocalCategory.objects.create(
            name="Kitchen", name_en="Kitchen", name_zh="厨房", slug="kitchen-r2", path="kitchen-r2"
        )

    def _make_staff(self, email, codes):
        role, _ = PlatformRole.objects.update_or_create(
            code=f"role-{email.split('@')[0]}",
            defaults={"name": f"Role {email}", "is_system": False},
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
            defaults={"display_name": "测试管理员", "password": "x"},
        )
        staff.set_password("Passw0rd!demo")
        staff.status = StaffAccount.Status.ACTIVE
        staff.save()
        StaffRoleAssignment.objects.get_or_create(staff=staff, role=role)
        return staff

    def _login(self, staff):
        token, _session = create_staff_session(
            staff=staff, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token

    def post_json(self, url, payload=None):
        return self.client.post(
            url, data=json.dumps(payload or {}), content_type="application/json"
        )

    def patch_json(self, url, payload=None):
        return self.client.patch(
            url, data=json.dumps(payload or {}), content_type="application/json"
        )

    def make_listed_product(self, *, title="演示商品", price="20.00", cost="10.00"):
        spu = Spu.objects.create(
            local_category=self.category,
            status=Spu.Status.ACTIVE,
            cost_price=Decimal(cost),
            retail_price=Decimal(price),
            image_urls=["/media/demo.webp"],
        )
        SpuTranslation.objects.create(spu=spu, locale="zh-CN", title=title)
        sku = spu.skus.create(specification={}, specification_signature="default")
        Offer.objects.create(
            merchant=self.merchant,
            sku=sku,
            market=self.market,
            currency=self.currency,
            current_price=Decimal(price),
            cost_price=Decimal(cost),
            status=Offer.Status.ACTIVE,
            listed_at=timezone.now(),
        )
        return spu


class ViewVsManageTests(Round2Base):
    def test_manage_permission_implies_view(self):
        codes = get_staff_permission_codes(self.staff)
        self.assertIn("cms.banners.manage", codes)
        self.assertIn("cms.banners.view", codes)

    def test_read_only_can_list_but_cannot_create_banner(self):
        viewer = self._make_staff("round2-viewer@joybuy.test", READ_ONLY)
        self._login(viewer)

        response = self.client.get("/api/v1/admin/banners")
        self.assertEqual(response.status_code, 200)

        response = self.post_json(
            "/api/v1/admin/banners", {"title": "只读不许建", "image": "/media/x.webp"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "STAFF_PERMISSION_DENIED")
        self.assertEqual(HomeBanner.objects.count(), 0)


class BannerApiTests(Round2Base):
    def test_create_requires_image_and_limits_title(self):
        response = self.post_json("/api/v1/admin/banners", {"title": "缺图"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "IMAGE_REQUIRED")

        response = self.post_json(
            "/api/v1/admin/banners", {"title": "字" * 41, "image": "/media/a.webp"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "TITLE_TOO_LONG")

    def test_create_toggle_and_delete(self):
        response = self.post_json(
            "/api/v1/admin/banners",
            {"title": "秋季大促", "description": "全场 8 折", "image": "/media/a.webp", "sort": 1},
        )
        self.assertEqual(response.status_code, 201, response.content)
        banner_id = response.json()["banner"]["id"]
        self.assertTrue(response.json()["banner"]["enabled"])

        response = self.post_json(
            f"/api/v1/admin/banners/{banner_id}/actions", {"action": "disable"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["banner"]["enabled"])

        response = self.client.delete(f"/api/v1/admin/banners/{banner_id}")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(HomeBanner.objects.count(), 0)


class NotificationApiTests(Round2Base):
    def test_normal_notification_to_all_active_merchants(self):
        response = self.post_json(
            "/api/v1/admin/notifications",
            {"kind": "NORMAL", "title": "系统维护", "content": "今晚 23:00 升级"},
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertGreaterEqual(response.json()["count"], 1)
        self.assertTrue(
            MerchantNotification.objects.filter(merchant=self.merchant, title="系统维护").exists()
        )

    def test_review_rejected_when_product_not_listed_by_that_merchant(self):
        other = Merchant.objects.create(
            slug="r2-other",
            display_name="别家店",
            onboarding_status=Merchant.OnboardingStatus.ACTIVE,
            admission_approved=True,
            deposit_initial_paid=True,
        )
        spu = self.make_listed_product()
        response = self.post_json(
            "/api/v1/admin/notifications",
            {
                "kind": "REVIEW",
                "merchant_id": str(other.public_id),
                "product_id": str(spu.public_id),
                "title": "好评推送",
                "content": "很好的商品",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "PRODUCT_NOT_LISTED")

    def test_review_snapshot_and_platform_reply_resets_read(self):
        spu = self.make_listed_product(title="铸铁锅")
        response = self.post_json(
            "/api/v1/admin/notifications",
            {
                "kind": "REVIEW",
                "merchant_id": str(self.merchant.public_id),
                "product_id": str(spu.public_id),
                "title": "好评推送",
                "content": "锅很厚实",
                "rating": 5,
                "images": ["/media/r1.webp"],
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        record = MerchantNotification.objects.get()
        self.assertEqual(record.product_snapshot["name"], "铸铁锅")
        self.assertEqual(record.rating, 5)

        record.read_at = timezone.now()
        record.save(update_fields=["read_at"])

        response = self.post_json(
            f"/api/v1/admin/notifications/{record.public_id}/replies",
            {"content": "感谢支持，欢迎再次选购。"},
        )
        self.assertEqual(response.status_code, 201, response.content)
        record.refresh_from_db()
        self.assertIsNone(record.read_at)
        self.assertEqual(record.replies.count(), 1)


class SupportApiTests(Round2Base):
    def test_create_support_conversation_is_idempotent(self):
        first = self.post_json(
            "/api/v1/admin/support/conversations",
            {"merchant_id": str(self.merchant.public_id)},
        )
        self.assertEqual(first.status_code, 201, first.content)
        second = self.post_json(
            "/api/v1/admin/support/conversations",
            {"merchant_id": str(self.merchant.public_id)},
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            SupportConversation.objects.filter(
                merchant=self.merchant,
                kind=SupportConversation.Kind.PLATFORM_SUPPORT,
            ).count(),
            1,
        )

    def test_reply_moves_state_and_resolve(self):
        conversation = SupportConversation.objects.create(
            merchant=self.merchant,
            kind=SupportConversation.Kind.PLATFORM_SUPPORT,
            peer_name="平台客服",
        )
        SupportMessage.objects.create(
            conversation=conversation,
            sender=SupportMessage.Sender.MERCHANT,
            text="想充值保证金",
        )
        url = f"/api/v1/admin/support/conversations/{conversation.public_id}"
        response = self.post_json(url, {"action": "reply", "text": "已为您登记"})
        self.assertEqual(response.status_code, 201, response.content)
        conversation.refresh_from_db()
        self.assertEqual(conversation.state, SupportConversation.State.PROCESSING)
        self.assertIsNotNone(conversation.last_message_at)

        response = self.post_json(url, {"action": "resolve"})
        self.assertEqual(response.status_code, 200)
        conversation.refresh_from_db()
        self.assertEqual(conversation.state, SupportConversation.State.RESOLVED)

    def test_empty_reply_rejected(self):
        conversation = SupportConversation.objects.create(
            merchant=self.merchant, kind=SupportConversation.Kind.BUYER
        )
        response = self.post_json(
            f"/api/v1/admin/support/conversations/{conversation.public_id}",
            {"action": "reply", "text": "   "},
        )
        self.assertEqual(response.status_code, 400)


class BuyerWhitelistTests(Round2Base):
    def setUp(self):
        super().setUp()
        self.buyer = BuyerAccount.objects.create(
            email="buyer-r2@joybuy.test", password="x", region="GB"
        )

    def test_recharge_and_remove_keeps_balance(self):
        url = f"/api/v1/admin/buyers/accounts/{self.buyer.public_id}/whitelist"
        response = self.post_json(url, {"action": "recharge", "amount": "100.00"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["buyer"]["balance"], "100.00")

        response = self.post_json(url, {"action": "remove"})
        self.assertEqual(response.status_code, 200)
        self.buyer.refresh_from_db()
        self.assertFalse(self.buyer.purchase_whitelisted)
        self.assertEqual(self.buyer.balance, Decimal("100.00"))

    def test_recharge_rejected_after_removed(self):
        self.buyer.purchase_whitelisted = False
        self.buyer.save(update_fields=["purchase_whitelisted"])
        response = self.post_json(
            f"/api/v1/admin/buyers/accounts/{self.buyer.public_id}/whitelist",
            {"action": "recharge", "amount": "10"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "NOT_WHITELISTED")

    def test_balance_cannot_go_negative(self):
        recharge_buyer(self.buyer, amount=Decimal("20.00"))
        with self.assertRaises(Exception) as ctx:
            record_buyer_wallet_entry(
                account=self.buyer,
                kind=BuyerWalletEntry.Kind.PURCHASE,
                amount=Decimal("-30.00"),
            )
        self.assertEqual(getattr(ctx.exception, "code", ""), "INSUFFICIENT_BUYER_BALANCE")
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.balance, Decimal("20.00"))

    def test_idempotency_prevents_double_recharge(self):
        from accounts_buyers.services import record_buyer_wallet_entry as record

        first = record(
            account=self.buyer,
            kind=BuyerWalletEntry.Kind.RECHARGE,
            amount=Decimal("50.00"),
            idempotency_key="r2-same",
        )
        second = record(
            account=self.buyer,
            kind=BuyerWalletEntry.Kind.RECHARGE,
            amount=Decimal("50.00"),
            idempotency_key="r2-same",
        )
        self.assertEqual(first.pk, second.pk)
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.balance, Decimal("50.00"))

    def test_disabled_buyer_cannot_join_whitelist(self):
        self.buyer.status = BuyerAccount.Status.DISABLED
        self.buyer.purchase_whitelisted = False
        self.buyer.save(update_fields=["status", "purchase_whitelisted"])
        response = self.post_json(
            f"/api/v1/admin/buyers/accounts/{self.buyer.public_id}/whitelist",
            {"action": "add"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "BUYER_DISABLED")


class GrowthApiTests(Round2Base):
    def test_add_followers_accumulates_and_sets_day(self):
        url = f"/api/v1/admin/growth/{self.merchant.public_id}/actions"
        response = self.post_json(url, {"action": "add_followers", "count": 30})
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()["merchant"]
        self.assertEqual(body["followers"], 30)
        self.assertEqual(body["follow_delta"], 30)
        self.assertEqual(body["follow_day"], timezone.localdate().isoformat())

        response = self.post_json(url, {"action": "add_exposure", "count": 128})
        self.assertEqual(response.json()["merchant"]["exposure"], 128)

    def test_negative_count_rejected(self):
        response = self.post_json(
            f"/api/v1/admin/growth/{self.merchant.public_id}/actions",
            {"action": "add_followers", "count": 0},
        )
        self.assertEqual(response.status_code, 400)

    def test_records_read_from_audit(self):
        self.post_json(
            f"/api/v1/admin/growth/{self.merchant.public_id}/actions",
            {"action": "add_exposure", "count": 5},
        )
        response = self.client.get("/api/v1/admin/growth/records")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.json()["total"], 1)


class StaffAccountApiTests(Round2Base):
    def test_create_account_requires_module_and_validates_password(self):
        payload = {
            "account": "newops@joybuy.test",
            "name": "新运营",
            "password": "short",
            "modules": {"banners": {"read": True}},
        }
        response = self.post_json("/api/v1/admin/staff/accounts", payload)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "PASSWORD_INVALID")

        payload["password"] = "LongEnough#1"
        payload["modules"] = {}
        response = self.post_json("/api/v1/admin/staff/accounts", payload)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "NO_MODULE")

    def test_create_read_only_account_grants_view_only(self):
        response = self.post_json(
            "/api/v1/admin/staff/accounts",
            {
                "account": "viewer2@joybuy.test",
                "name": "只读运营",
                "password": "LongEnough#1",
                "modules": {"banners": {"read": True}},
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        staff = StaffAccount.objects.get(email="viewer2@joybuy.test")
        codes = get_staff_permission_codes(staff)
        self.assertIn("cms.banners.view", codes)
        self.assertNotIn("cms.banners.manage", codes)

    def test_write_implies_read(self):
        response = self.post_json(
            "/api/v1/admin/staff/accounts",
            {
                "account": "writer2@joybuy.test",
                "name": "写运营",
                "password": "LongEnough#1",
                "modules": {"banners": {"write": True}},
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        staff = StaffAccount.objects.get(email="writer2@joybuy.test")
        codes = get_staff_permission_codes(staff)
        self.assertIn("cms.banners.view", codes)
        self.assertIn("cms.banners.manage", codes)

    def test_protected_admin_cannot_be_disabled_or_stripped(self):
        admin_role = PlatformRole.objects.create(
            code="platform_admin_r2", name="超级管理员", is_platform_admin=True, is_system=True
        )
        target = StaffAccount.objects.create(
            email="super-r2@joybuy.test", display_name="超级", password="x"
        )
        StaffRoleAssignment.objects.create(staff=target, role=admin_role)

        response = self.patch_json(
            f"/api/v1/admin/staff/accounts/{target.public_id}", {"status": "DISABLED"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "PROTECTED_ACCOUNT")

    def test_duplicate_account_rejected(self):
        response = self.post_json(
            "/api/v1/admin/staff/accounts",
            {
                "account": self.staff.email,
                "name": "重复",
                "password": "LongEnough#1",
                "modules": {"banners": {"read": True}},
            },
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "ACCOUNT_EXISTS")

    def test_catalog_lists_modules(self):
        response = self.client.get("/api/v1/admin/staff/permissions")
        self.assertEqual(response.status_code, 200)
        codes = {module["code"] for module in response.json()["modules"]}
        self.assertIn("banners", codes)
        self.assertIn("audit", codes)


class AuditLogApiTests(Round2Base):
    def test_list_and_export(self):
        self.post_json(
            "/api/v1/admin/banners",
            {"title": "审计验证", "image": "/media/a.webp"},
        )
        response = self.client.get("/api/v1/admin/audit-logs?module=home_banner")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertGreaterEqual(response.json()["total"], 1)
        first = response.json()["items"][0]
        self.assertEqual(first["action"], "BANNER_CREATED")
        self.assertEqual(first["operator"], self.staff.display_name)

        export = self.client.get("/api/v1/admin/audit-logs/export?module=home_banner")
        self.assertEqual(export.status_code, 200)
        self.assertIn("text/csv", export["Content-Type"])
        self.assertIn("BANNER_CREATED", export.content.decode("utf-8"))

    def test_unknown_module_returns_404(self):
        response = self.client.get(f"/api/v1/admin/banners/{uuid.uuid4()}")
        self.assertEqual(response.status_code, 404)
