"""图片上传接口测试（管理端 /admin/media、商家端 /merchant/media）。

重点：真实文件落盘 + URL 可回读、去重、格式白名单、大小与像素上限、
以及「谁有权传哪类图」的权限边界。
"""

import io
import shutil
import tempfile
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from accounts_staff.models import (
    PlatformPermission,
    PlatformRole,
    StaffAccount,
    StaffRoleAssignment,
)
from accounts_staff.services import create_staff_session
from media.models import MediaAsset
from merchants.models import Merchant, MerchantMembership, MerchantRole


def image_bytes(fmt="PNG", size=(200, 150), color=(220, 40, 60)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


class UploadTestBase(TestCase):
    def setUp(self):
        # 上传会真的写文件，测试必须用临时 MEDIA_ROOT，不能污染本地媒体库。
        self.media_root = tempfile.mkdtemp(prefix="joybuy-media-")
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)

    def temp_root(self):
        return override_settings(MEDIA_ROOT=self.media_root)


class AdminUploadTests(UploadTestBase):
    def setUp(self):
        super().setUp()
        role, _ = PlatformRole.objects.update_or_create(
            code="media-role", defaults={"name": "Media", "is_system": False}
        )
        role.permissions.set(
            [
                PlatformPermission.objects.get_or_create(code=code, defaults={"name": code})[0]
                for code in (
                    "catalog.pool.manage",
                    "cms.banners.manage",
                    "notifications.manage",
                    "merchants.manage",
                )
            ]
        )
        staff = StaffAccount.objects.create(
            email="media@joybuy.test", display_name="媒体测试", status="ACTIVE"
        )
        StaffRoleAssignment.objects.create(staff=staff, role=role)
        token, _session = create_staff_session(
            staff=staff, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token

    def upload(self, data, *, purpose="product", name="a.png"):
        return self.client.post(
            "/api/v1/admin/media",
            {"file": SimpleUploadedFile(name, data, content_type="image/png"), "purpose": purpose},
        )

    def test_upload_writes_file_and_returns_readable_url(self):
        payload = image_bytes()
        with self.temp_root():
            response = self.upload(payload)
            self.assertEqual(response.status_code, 201, response.content)
            media = response.json()["media"]
            self.assertTrue(media["url"].startswith("/media/products/original/"))
            self.assertFalse(media["deduplicated"])
            self.assertEqual((media["width"], media["height"]), (200, 150))

            asset = MediaAsset.objects.get(sha256=media["sha256"])
            self.assertEqual(asset.kind, MediaAsset.Kind.PRODUCT)
            self.assertEqual(asset.mime_type, "image/png")

            # 文件必须真的落在 MEDIA_ROOT 里，而不只是写了数据库行
            from media.storage import resolve_media_path

            stored = resolve_media_path(asset.relative_path)
            self.assertTrue(stored.is_file())
            self.assertTrue(str(stored).startswith(self.media_root))

            # 落盘内容与上传字节完全一致（同一张图能被 <img> 直接渲染）
            self.assertEqual(stored.read_bytes(), payload)
            self.assertEqual(Image.open(io.BytesIO(stored.read_bytes())).format, "PNG")

            # /media/ 的路由只在 DEBUG 下注册（生产由 Nginx 服务），
            # 所以这里直接验 URL 形状，回读放在浏览器实测里做。
            self.assertTrue(media["url"].startswith("/media/"))

    def test_identical_bytes_are_deduplicated(self):
        with self.temp_root():
            first = self.upload(image_bytes())
            second = self.upload(image_bytes(), name="copy.png")
            self.assertEqual(second.status_code, 201)
            self.assertEqual(first.json()["media"]["url"], second.json()["media"]["url"])
            self.assertTrue(second.json()["media"]["deduplicated"])
            self.assertEqual(MediaAsset.objects.count(), 1)

    def test_rejects_non_image(self):
        with self.temp_root():
            response = self.upload(b"#!/bin/sh\nrm -rf /", name="evil.png")
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["error"]["code"], "FILE_NOT_IMAGE")
            self.assertEqual(MediaAsset.objects.count(), 0)

    def test_rejects_format_outside_whitelist(self):
        with self.temp_root():
            response = self.upload(image_bytes(fmt="GIF"), name="a.gif")
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["error"]["code"], "IMAGE_FORMAT_UNSUPPORTED")

    def test_rejects_oversized_file(self):
        with self.temp_root():
            # 噪声图必然超过 1MB
            import os

            big = Image.frombytes("RGB", (900, 900), os.urandom(900 * 900 * 3))
            buffer = io.BytesIO()
            big.save(buffer, format="PNG")
            response = self.upload(buffer.getvalue(), name="big.png")
            self.assertEqual(response.status_code, 413)
            self.assertEqual(response.json()["error"]["code"], "FILE_TOO_LARGE")

    def test_rejects_too_many_pixels(self):
        with self.temp_root():
            buffer = io.BytesIO()
            Image.new("RGB", (7000, 6000), (1, 2, 3)).save(buffer, format="PNG")
            response = self.upload(buffer.getvalue(), purpose="banner", name="huge.png")
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["error"]["code"], "IMAGE_TOO_LARGE_PIXELS")

    def test_rejects_unknown_purpose(self):
        with self.temp_root():
            response = self.upload(image_bytes(), purpose="hack")
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["error"]["code"], "UPLOAD_PURPOSE_INVALID")

    def test_requires_file(self):
        with self.temp_root():
            response = self.client.post("/api/v1/admin/media", {"purpose": "product"})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["error"]["code"], "FILE_REQUIRED")

    def test_purpose_needs_matching_permission(self):
        """只有商品池权限的账号不能传轮播图——按模块校验，不能互相顶替。"""
        limited_role, _ = PlatformRole.objects.update_or_create(
            code="pool-only", defaults={"name": "Only pool", "is_system": False}
        )
        limited_role.permissions.set(
            [
                PlatformPermission.objects.get_or_create(
                    code="catalog.pool.manage", defaults={"name": "x"}
                )[0]
            ]
        )
        staff = StaffAccount.objects.create(
            email="pool-only@joybuy.test", display_name="只商品", status="ACTIVE"
        )
        StaffRoleAssignment.objects.create(staff=staff, role=limited_role)
        token, _session = create_staff_session(
            staff=staff, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token

        with self.temp_root():
            allowed = self.upload(image_bytes(), purpose="product")
            self.assertEqual(allowed.status_code, 201)
            denied = self.upload(image_bytes(), purpose="banner")
            self.assertEqual(denied.status_code, 403)
            self.assertEqual(denied.json()["error"]["code"], "STAFF_PERMISSION_DENIED")


class MerchantUploadTests(UploadTestBase):
    def setUp(self):
        super().setUp()
        self.staff = StaffAccount.objects.create(
            email="media-seller@joybuy.test", display_name="卖家", status="ACTIVE"
        )
        self.shop = Merchant.objects.create(
            slug="media-shop",
            display_name="上传测试店",
            onboarding_status=Merchant.OnboardingStatus.ACTIVE,
            admission_approved=True,
            deposit_initial_paid=True,
        )
        self.owner_role = MerchantRole.objects.get(code="merchant_owner")
        MerchantMembership.objects.create(
            merchant=self.shop, staff=self.staff, role=self.owner_role, status="ACTIVE"
        )
        token, _session = create_staff_session(
            staff=self.staff, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token

    def upload(self, data, *, purpose="product"):
        return self.client.post(
            "/api/v1/merchant/media",
            {
                "file": SimpleUploadedFile("a.png", data, content_type="image/png"),
                "purpose": purpose,
            },
            HTTP_X_MERCHANT_ID=str(self.shop.public_id),
        )

    def test_avatar_upload_lands_in_merchant_bucket(self):
        with self.temp_root():
            response = self.upload(image_bytes(), purpose="avatar")
            self.assertEqual(response.status_code, 201, response.content)
            url = response.json()["media"]["url"]
            self.assertTrue(url.startswith("/media/merchants/original/"))
            asset = MediaAsset.objects.get(sha256=response.json()["media"]["sha256"])
            self.assertEqual(asset.kind, MediaAsset.Kind.MERCHANT)

    def test_banner_purpose_is_not_available_to_merchant(self):
        with self.temp_root():
            response = self.upload(image_bytes(), purpose="banner")
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["error"]["code"], "UPLOAD_PURPOSE_INVALID")

    def test_role_without_listing_permission_cannot_upload_product(self):
        staff_role = MerchantRole.objects.get(code="merchant_staff")
        MerchantMembership.objects.filter(merchant=self.shop, staff=self.staff).update(
            role=staff_role
        )
        # 店铺运营角色没有 merchant.store.manage，头像上传应被拒
        with self.temp_root():
            response = self.upload(image_bytes(), purpose="avatar")
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["error"]["code"], "MERCHANT_PERMISSION_DENIED")
            allowed = self.upload(image_bytes(), purpose="product")
            self.assertEqual(allowed.status_code, 201)


class AfterSaleProofTests(UploadTestBase):
    def test_proof_accepts_media_url_only(self):
        from django.utils import timezone

        from accounts_buyers.models import BuyerAccount
        from merchant_ops.models import AfterSale
        from offers.models import Currency
        from orders.models import MerchantOrder, Order

        staff = StaffAccount.objects.create(
            email="proof-seller@joybuy.test", display_name="卖家", status="ACTIVE"
        )
        shop = Merchant.objects.create(
            slug="proof-shop",
            display_name="凭证店",
            onboarding_status=Merchant.OnboardingStatus.ACTIVE,
            admission_approved=True,
            deposit_initial_paid=True,
        )
        MerchantMembership.objects.create(
            merchant=shop,
            staff=staff,
            role=MerchantRole.objects.get(code="merchant_owner"),
            status="ACTIVE",
        )
        buyer = BuyerAccount.objects.create(email="proof-buyer@joybuy.test")
        order = Order.objects.create(
            account=buyer,
            currency=Currency.objects.get(code="GBP"),
            items_subtotal=Decimal("10.00"),
            shipping_cost=Decimal("0.00"),
            total=Decimal("10.00"),
            shipping_address={"region": "London"},
            payment_expires_at=timezone.now(),
        )
        merchant_order = MerchantOrder.objects.create(
            order=order, merchant=shop, currency="GBP", items_total=Decimal("10.00")
        )
        record = AfterSale.objects.create(
            merchant=shop,
            order=order,
            merchant_order=merchant_order,
            kind=AfterSale.Kind.RETURN,
            issue="破损",
        )
        token, _session = create_staff_session(
            staff=staff, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token

        headers = {"HTTP_X_MERCHANT_ID": str(shop.public_id)}
        import json

        ok = self.client.post(
            f"/api/v1/merchant/after-sales/{record.public_id}/actions",
            data=json.dumps({"action": "proof", "images": ["/media/reviews/original/x.png"]}),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(ok.status_code, 200, ok.content)
        record.refresh_from_db()
        self.assertEqual(record.proof, ["/media/reviews/original/x.png"])

        bad = self.client.post(
            f"/api/v1/merchant/after-sales/{record.public_id}/actions",
            data=json.dumps({"action": "proof", "images": ["javascript:alert(1)"]}),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.json()["error"]["code"], "PROOF_URL_INVALID")
