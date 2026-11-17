"""购物端「申请店铺」：买家提交/查询 + 管理端审核全流程。

重点：
1. 买家接口鉴权与提交校验（401 / 400 / 409，错误码稳定）；2026-11-17
   起表单为 7 项：店铺logo、用户名字、店铺名、手机号码、邀请码（选填）、
   个人证件（类型三选一 + 照片）、个人居住地址；
2. 管理端列表可见 + 待审计数，回包带全部新字段（含两张图 URL）；
3. approve：开店（logo 回填 Merchant.avatar_url、邀请码按 WP-42 绑定）
   + StaffAccount 密码哈希直复（买家密码可登录商家端）
   + merchant_owner membership + review_admission 状态机 + 回填申请单；
4. reject：原因必填，买家重新申请回到 PENDING；
5. 邮箱冲突：绑定现有员工账号且不改其密码；
6. 买家侧上传接口 /account/merchant-application/media（purpose 固定）。
"""

import io
import json
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from accounts_buyers.models import BuyerAccount
from accounts_buyers.services import create_buyer_session
from accounts_staff.models import PlatformRole, StaffAccount, StaffRoleAssignment
from accounts_staff.services import create_staff_session
from media.models import MediaAsset
from media.storage import store_bytes
from merchants.models import Merchant, MerchantApplication, MerchantMembership

BUYER_PASSWORD = "Buyer#2026pass"
STAFF_OWN_PASSWORD = "Staff#OwnPass"


def image_bytes(color=(220, 40, 60), size=(200, 150)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


class MerchantApplicationFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.referrer_merchant = Merchant.objects.create(
            slug="referrer-shop",
            display_name="邀请商家店",
            referral_code="MREFERRER01",
        )
        cls.admin = StaffAccount.objects.create(
            email="apply-admin@joybuy.test", display_name="申请审核员", status="ACTIVE"
        )
        cls.admin.set_password("Admin#2026pass")
        cls.admin.save()

    def setUp(self):
        self.client.cookies.clear()
        # 申请里引用的两张图必须对应真实 MediaAsset；store_bytes 会写物理
        # 文件，测试用临时 MEDIA_ROOT，不污染本地媒体库。
        self.media_root = tempfile.mkdtemp(prefix="joybuy-apply-")
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        with override_settings(MEDIA_ROOT=self.media_root):
            self.logo_url = self._store_media(color=(30, 144, 255))
            self.doc_url = self._store_media(color=(255, 165, 0))

    def _store_media(self, *, color):
        asset, _created = store_bytes(
            image_bytes(color=color),
            kind=MediaAsset.Kind.MERCHANT,
            mime_type="image/png",
        )
        return f"/media/{asset.relative_path}"

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _make_buyer(self, email="buyer-apply@joybuy.test", password=BUYER_PASSWORD, **extra):
        buyer = BuyerAccount(email=email, password="x", **extra)
        buyer.set_password(password)
        buyer.save()
        return buyer

    def _login_buyer(self, buyer):
        token, _session = create_buyer_session(
            account=buyer, ip_address="127.0.0.1", user_agent="test"
        )
        self.client.cookies["joybuy_buyer_session"] = token

    def _login_admin(self):
        StaffRoleAssignment.objects.get_or_create(
            staff=self.admin, defaults={"role": PlatformRole.objects.get(code="platform_admin")}
        )
        token, _session = create_staff_session(
            staff=self.admin, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token

    def _post_json(self, path, payload):
        return self.client.post(path, data=json.dumps(payload), content_type="application/json")

    def _submit(self, buyer, **overrides):
        self._login_buyer(buyer)
        payload = {
            "user_name": "王小明",
            "shop_name": "星光电子",
            "phone": "+447700900123",
            "referrer_code": "",
            "id_document_type": "ID_CARD",
            "residential_address": "12 Baker Street, London",
            "logo_image_url": self.logo_url,
            "id_document_image_url": self.doc_url,
        }
        payload.update(overrides)
        return self._post_json("/api/v1/account/merchant-application", payload)

    def _approve(self, application_id, **overrides):
        payload = {
            "application_id": application_id,
            "action": "approve",
            "require_deposit": False,
            "ban_after_days": 4,
        }
        payload.update(overrides)
        return self._post_json("/api/v1/admin/merchant-applications/actions", payload)

    # ------------------------------------------------------------------
    # 买家端
    # ------------------------------------------------------------------
    def test_get_requires_login(self):
        response = self.client.get("/api/v1/account/merchant-application")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "BUYER_AUTH_REQUIRED")

    def test_submit_success_and_payload_echo(self):
        buyer = self._make_buyer()
        response = self._submit(buyer)
        self.assertEqual(response.status_code, 201)
        application = response.json()["application"]
        self.assertEqual(application["status"], "PENDING")
        self.assertEqual(application["user_name"], "王小明")
        self.assertEqual(application["shop_name"], "星光电子")
        self.assertEqual(application["phone"], "+447700900123")
        self.assertEqual(application["referrer_code"], "")
        self.assertEqual(application["id_document_type"], "ID_CARD")
        self.assertEqual(application["residential_address"], "12 Baker Street, London")
        self.assertEqual(application["logo_image_url"], self.logo_url)
        self.assertEqual(application["id_document_image_url"], self.doc_url)
        self.assertIsNone(application["merchant"])
        self.assertIsNone(application["reviewed_at"])
        self.assertTrue(application["submitted_at"])

        response = self.client.get("/api/v1/account/merchant-application")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["application"]["status"], "PENDING")

    def test_duplicate_pending_submission_conflict(self):
        buyer = self._make_buyer()
        self.assertEqual(self._submit(buyer).status_code, 201)
        response = self._submit(buyer, shop_name="再开一家")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "APPLICATION_ALREADY_PENDING")

    def test_user_name_required(self):
        buyer = self._make_buyer()
        response = self._submit(buyer, user_name="   ")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "USER_NAME_REQUIRED")

    def test_shop_name_required(self):
        buyer = self._make_buyer()
        response = self._submit(buyer, shop_name="   ")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "SHOP_NAME_REQUIRED")

    def test_shop_name_too_long(self):
        buyer = self._make_buyer()
        response = self._submit(buyer, shop_name="铺" * 61)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "SHOP_NAME_TOO_LONG")

    def test_phone_required(self):
        buyer = self._make_buyer()
        response = self._submit(buyer, phone="   ")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "PHONE_REQUIRED")

    def test_phone_format(self):
        buyer = self._make_buyer()
        # +44 国际写法、0 开头本地写法、带空格/横线的写法都放行。
        for raw in ("+447700900123", "07700900123", "07700 900-123"):
            response = self._submit(buyer, phone=raw)
            self.assertEqual(response.status_code, 201, raw)
            MerchantApplication.objects.get(buyer=buyer).delete()
        # 字母、过短、过长都拒绝。
        for raw in ("abc123456", "12345", "0" * 25):
            response = self._submit(buyer, phone=raw)
            self.assertEqual(response.status_code, 400, raw)
            self.assertEqual(response.json()["error"]["code"], "PHONE_INVALID")

    def test_residential_address_required(self):
        buyer = self._make_buyer()
        response = self._submit(buyer, residential_address="")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "RESIDENTIAL_ADDRESS_REQUIRED")

    def test_residential_address_too_long(self):
        buyer = self._make_buyer()
        response = self._submit(buyer, residential_address="a" * 256)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "RESIDENTIAL_ADDRESS_TOO_LONG")

    def test_id_document_type_enum(self):
        buyer = self._make_buyer()
        for value in ("PASSPORT", "DRIVER_LICENSE", "id_card"):
            response = self._submit(buyer, id_document_type=value)
            self.assertEqual(response.status_code, 201, value)
            self.assertEqual(
                response.json()["application"]["id_document_type"], value.upper()
            )
            MerchantApplication.objects.get(buyer=buyer).delete()
        response = self._submit(buyer, id_document_type="STUDENT_CARD")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "ID_DOCUMENT_TYPE_INVALID")

    def test_logo_image_url_must_be_local_media(self):
        buyer = self._make_buyer()
        response = self._submit(buyer, logo_image_url="https://cdn.example.com/logo.png")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "LOGO_IMAGE_INVALID")
        response = self._submit(buyer, logo_image_url="/media/not/uploaded.png")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "LOGO_IMAGE_NOT_FOUND")

    def test_id_document_image_url_must_exist(self):
        buyer = self._make_buyer()
        response = self._submit(
            buyer,
            id_document_image_url="/media/merchants/original/aa/bb/missing.png",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "ID_DOCUMENT_IMAGE_NOT_FOUND")
        self.assertFalse(MerchantApplication.objects.filter(buyer=buyer).exists())

    def test_empty_referrer_code_accepted(self):
        buyer = self._make_buyer()
        response = self._submit(buyer, referrer_code="")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["application"]["referrer_code"], "")

    def test_invalid_referrer_code_accepted_at_submit(self):
        """邀请码不在提交时校验有效性（WP-42：approve 才绑定，无效忽略）。"""

        buyer = self._make_buyer()
        response = self._submit(buyer, referrer_code="MNOTEXIST9")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["application"]["referrer_code"], "MNOTEXIST9")

        # approve 时无效码被忽略：开店成功、不产生 MerchantReferral。
        self._login_admin()
        application_id = MerchantApplication.objects.get(buyer=buyer).pk
        response = self._approve(application_id)
        self.assertEqual(response.status_code, 200)
        from merchant_ops.models import MerchantReferral

        self.assertFalse(MerchantReferral.objects.filter(code_used="MNOTEXIST9").exists())

    def test_valid_referrer_code_saved(self):
        buyer = self._make_buyer()
        response = self._submit(buyer, referrer_code="MREFERRER01")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["application"]["referrer_code"], "MREFERRER01")

    def test_buyer_without_email_cannot_apply(self):
        buyer = self._make_buyer(email=None, phone_e164="+447700900123")
        response = self._submit(buyer)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "BUYER_EMAIL_REQUIRED")

    def test_approved_buyer_cannot_reapply(self):
        buyer = self._make_buyer()
        self.assertEqual(self._submit(buyer).status_code, 201)
        self._login_admin()
        application_id = MerchantApplication.objects.get(buyer=buyer).pk
        response = self._approve(application_id)
        self.assertEqual(response.status_code, 200)
        self._login_buyer(buyer)
        response = self._submit(buyer, shop_name="改个名字")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "SHOP_ALREADY_APPROVED")

    # ------------------------------------------------------------------
    # 管理端：列表
    # ------------------------------------------------------------------
    def test_admin_list_and_pending_count(self):
        buyer = self._make_buyer()
        self._submit(buyer)
        self._login_admin()
        response = self.client.get("/api/v1/admin/merchant-applications?status=PENDING")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["pending_count"], 1)
        self.assertEqual(len(payload["items"]), 1)
        row = payload["items"][0]
        self.assertEqual(row["buyer_email"], buyer.email)
        self.assertEqual(row["user_name"], "王小明")
        self.assertEqual(row["shop_name"], "星光电子")
        self.assertEqual(row["phone"], "+447700900123")
        self.assertEqual(row["id_document_type"], "ID_CARD")
        self.assertEqual(row["residential_address"], "12 Baker Street, London")
        self.assertEqual(row["logo_image_url"], self.logo_url)
        self.assertEqual(row["id_document_image_url"], self.doc_url)
        self.assertEqual(row["status"], "PENDING")
        self.assertIsNone(row["merchant"])

    def test_admin_list_status_filter(self):
        buyer = self._make_buyer()
        self._submit(buyer)
        self._login_admin()
        self._approve(MerchantApplication.objects.get(buyer=buyer).pk)
        response = self.client.get("/api/v1/admin/merchant-applications?status=APPROVED")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["items"]), 1)
        self.assertEqual(response.json()["pending_count"], 0)

    # ------------------------------------------------------------------
    # 管理端：approve
    # ------------------------------------------------------------------
    def test_approve_without_deposit_opens_shop_and_links_staff_login(self):
        buyer = self._make_buyer()
        self.assertEqual(self._submit(buyer).status_code, 201)
        self._login_admin()
        application_id = MerchantApplication.objects.get(buyer=buyer).pk
        response = self._approve(application_id)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["staff_account_created"])

        merchant = Merchant.objects.get(pk=MerchantApplication.objects.get(buyer=buyer).merchant.pk)
        self.assertEqual(merchant.onboarding_status, Merchant.OnboardingStatus.ACTIVE)
        self.assertTrue(merchant.admission_approved)
        self.assertFalse(merchant.deposit_enabled)
        self.assertEqual(merchant.display_name, "星光电子")
        # 申请店铺logo 回填 Merchant.avatar_url
        self.assertEqual(merchant.avatar_url, self.logo_url)

        staff = StaffAccount.objects.get(email=buyer.email)
        self.assertEqual(staff.status, StaffAccount.Status.ACTIVE)
        self.assertTrue(staff.check_password(BUYER_PASSWORD))
        self.assertEqual(staff.password, buyer.password)

        membership = MerchantMembership.objects.get(merchant=merchant, staff=staff)
        self.assertEqual(membership.role.code, "merchant_owner")
        self.assertEqual(membership.status, MerchantMembership.Status.ACTIVE)

        application = MerchantApplication.objects.get(buyer=buyer)
        self.assertEqual(application.status, MerchantApplication.Status.APPROVED)
        self.assertEqual(application.reviewed_by, self.admin)
        self.assertIsNotNone(application.reviewed_at)
        self.assertEqual(application.merchant, merchant)

        # 买家邮箱 + 买家密码可直接登录（员工会话端点）
        self.client.cookies.clear()
        response = self._post_json(
            "/api/v1/admin/auth/login", {"email": buyer.email, "password": BUYER_PASSWORD}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["staff"]["email"], buyer.email)
        # 带该会话能查到新店铺
        response = self.client.get("/api/v1/merchant/shops")
        self.assertEqual(response.status_code, 200)
        shop_names = [item["name"] for item in response.json()["items"]]
        self.assertIn("星光电子", shop_names)

    def test_approve_with_deposit_lands_pending_deposit(self):
        buyer = self._make_buyer()
        self.assertEqual(self._submit(buyer).status_code, 201)
        self._login_admin()
        application_id = MerchantApplication.objects.get(buyer=buyer).pk
        response = self._approve(application_id, require_deposit=True, deposit_amount="500.00")
        self.assertEqual(response.status_code, 200)
        merchant = MerchantApplication.objects.get(buyer=buyer).merchant
        self.assertEqual(merchant.onboarding_status, Merchant.OnboardingStatus.PENDING_DEPOSIT)
        self.assertTrue(merchant.deposit_enabled)
        self.assertFalse(merchant.deposit_initial_paid)

    def test_approve_with_referrer_binds_referral(self):
        buyer = self._make_buyer()
        self._submit(buyer, referrer_code="MREFERRER01")
        self._login_admin()
        response = self._approve(MerchantApplication.objects.get(buyer=buyer).pk)
        self.assertEqual(response.status_code, 200)
        from merchant_ops.models import MerchantReferral

        referral = MerchantReferral.objects.get(referrer=self.referrer_merchant)
        self.assertEqual(referral.referee.display_name, "星光电子")
        self.assertEqual(referral.referee.avatar_url, self.logo_url)
        self.assertEqual(referral.code_used, "MREFERRER01")

    def test_duplicate_approve_conflict(self):
        buyer = self._make_buyer()
        self._submit(buyer)
        self._login_admin()
        application_id = MerchantApplication.objects.get(buyer=buyer).pk
        self.assertEqual(self._approve(application_id).status_code, 200)
        response = self._approve(application_id)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "APPLICATION_ALREADY_REVIEWED")

    def test_email_conflict_binds_existing_staff_without_password_change(self):
        existing = StaffAccount.objects.create(
            email="conflict@joybuy.test", display_name="老员工", status="ACTIVE"
        )
        existing.set_password(STAFF_OWN_PASSWORD)
        existing.save()
        old_hash = existing.password

        buyer = self._make_buyer(email="conflict@joybuy.test")
        self._submit(buyer)
        self._login_admin()
        response = self._approve(MerchantApplication.objects.get(buyer=buyer).pk)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["staff_account_created"])

        staff = StaffAccount.objects.get(email="conflict@joybuy.test")
        self.assertEqual(StaffAccount.objects.filter(email="conflict@joybuy.test").count(), 1)
        self.assertEqual(staff.password, old_hash)
        self.assertTrue(staff.check_password(STAFF_OWN_PASSWORD))
        self.assertFalse(staff.check_password(BUYER_PASSWORD))
        merchant = MerchantApplication.objects.get(buyer=buyer).merchant
        membership = MerchantMembership.objects.get(merchant=merchant, staff=staff)
        self.assertEqual(membership.role.code, "merchant_owner")

    # ------------------------------------------------------------------
    # 管理端：reject + 重新申请
    # ------------------------------------------------------------------
    def test_reject_requires_reason(self):
        buyer = self._make_buyer()
        self._submit(buyer)
        self._login_admin()
        response = self._post_json(
            "/api/v1/admin/merchant-applications/actions",
            {"application_id": MerchantApplication.objects.get(buyer=buyer).pk, "action": "reject"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "FIELD_REQUIRED")

    def test_reject_then_reapply_returns_to_pending(self):
        buyer = self._make_buyer()
        self._submit(buyer, shop_name="原名店铺")
        self._login_admin()
        application_id = MerchantApplication.objects.get(buyer=buyer).pk
        response = self._post_json(
            "/api/v1/admin/merchant-applications/actions",
            {
                "application_id": application_id,
                "action": "reject",
                "reason": "店铺名称与已有店铺重复",
            },
        )
        self.assertEqual(response.status_code, 200)
        application = MerchantApplication.objects.get(pk=application_id)
        self.assertEqual(application.status, MerchantApplication.Status.REJECTED)
        self.assertEqual(application.reject_reason, "店铺名称与已有店铺重复")
        self.assertEqual(application.reviewed_by, self.admin)
        self.assertIsNone(application.merchant)

        first_submitted_at = application.submitted_at
        self._login_buyer(buyer)
        response = self._submit(
            buyer,
            user_name="李小红",
            shop_name="新名字店铺",
            phone="07700900999",
            id_document_type="PASSPORT",
            residential_address="9 Rue de la Paix, Paris",
        )
        self.assertEqual(response.status_code, 201)
        application.refresh_from_db()
        self.assertEqual(application.status, MerchantApplication.Status.PENDING)
        self.assertEqual(application.reject_reason, "")
        self.assertEqual(application.user_name, "李小红")
        self.assertEqual(application.shop_name, "新名字店铺")
        self.assertEqual(application.phone, "07700900999")
        self.assertEqual(application.id_document_type, "PASSPORT")
        self.assertEqual(application.residential_address, "9 Rue de la Paix, Paris")
        self.assertIsNone(application.reviewed_at)
        self.assertGreater(application.submitted_at, first_submitted_at)
        # 没有创建任何店铺 / 商家端账号
        self.assertFalse(Merchant.objects.filter(display_name="新名字店铺").exists())
        self.assertFalse(StaffAccount.objects.filter(email=buyer.email).exists())


class BuyerApplicationMediaTests(TestCase):
    """买家侧申请图上传：purpose 固定 shop_application、买家会话鉴权。"""

    def setUp(self):
        self.client.cookies.clear()
        self.media_root = tempfile.mkdtemp(prefix="joybuy-apply-media-")
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        self.buyer = BuyerAccount(email="apply-media@joybuy.test", password="x")
        self.buyer.set_password(BUYER_PASSWORD)
        self.buyer.save()

    def _login(self):
        token, _session = create_buyer_session(
            account=self.buyer, ip_address="127.0.0.1", user_agent="test"
        )
        self.client.cookies["joybuy_buyer_session"] = token

    def _upload(self, data, *, purpose="shop_application", name="logo.png"):
        return self.client.post(
            "/api/v1/account/merchant-application/media",
            {
                "file": SimpleUploadedFile(name, data, content_type="image/png"),
                "purpose": purpose,
            },
        )

    def test_requires_login(self):
        with override_settings(MEDIA_ROOT=self.media_root):
            response = self._upload(image_bytes())
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "BUYER_AUTH_REQUIRED")

    def test_purpose_is_restricted(self):
        self._login()
        with override_settings(MEDIA_ROOT=self.media_root):
            response = self._upload(image_bytes(), purpose="product")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "UPLOAD_PURPOSE_INVALID")

    def test_file_required(self):
        self._login()
        with override_settings(MEDIA_ROOT=self.media_root):
            response = self.client.post(
                "/api/v1/account/merchant-application/media", {"purpose": "shop_application"}
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "FILE_REQUIRED")

    def test_upload_stores_asset_and_returns_media_url(self):
        self._login()
        data = image_bytes(color=(10, 200, 90))
        with override_settings(MEDIA_ROOT=self.media_root):
            response = self._upload(data)
        self.assertEqual(response.status_code, 201, response.content)
        media = response.json()["media"]
        self.assertTrue(media["url"].startswith("/media/merchants/original/"))
        asset = MediaAsset.objects.get(sha256=media["sha256"])
        self.assertEqual(asset.kind, MediaAsset.Kind.MERCHANT)

        # 上传返回的 URL 可以直接进申请表单（过 _validated_media_url 校验）。
        self._login()
        payload = {
            "user_name": "王小明",
            "shop_name": "星光电子",
            "phone": "+447700900123",
            "referrer_code": "",
            "id_document_type": "ID_CARD",
            "residential_address": "12 Baker Street, London",
            "logo_image_url": media["url"],
            "id_document_image_url": media["url"],
        }
        response = self.client.post(
            "/api/v1/account/merchant-application",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)

    def test_not_an_image_rejected(self):
        self._login()
        with override_settings(MEDIA_ROOT=self.media_root):
            response = self._upload(b"definitely not an image", name="fake.png")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "FILE_NOT_IMAGE")
