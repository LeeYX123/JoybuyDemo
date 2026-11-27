"""用户端管理【编辑】/【重设密码】（2026-11-27）。

覆盖：
1. 资料编辑（用户名/邮箱/手机号/状态/支付权限）成功并写审计；
2. 邮箱/手机号唯一冲突、非法格式、清空全部标识被拒；
3. 余额编辑走 adjust_buyer_balance 写台账；只给 buyers.manage 的账号不能动余额；
4. 重设密码：旧密码失效、新密码可登录、该账号所有旧会话被撤销、明文不落审计。
"""

import json
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import Client, TestCase
from django.utils import timezone

from accounts_buyers.models import BuyerAccount, BuyerSession, BuyerWalletEntry
from accounts_buyers.services import create_buyer_session, resolve_buyer_session
from accounts_staff.models import (
    PlatformPermission,
    PlatformRole,
    StaffAccount,
    StaffRoleAssignment,
)
from accounts_staff.services import create_staff_session
from audit.models import AuditLog

STAFF_PERMS = ("buyers.manage", "whitelist.manage")
LOGIN_URL = "/api/v1/auth/buyer/login"


class BuyerEditBase(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = self._make_staff("buyer-edit-full@joybuy.test", STAFF_PERMS)
        self._login(self.staff)

        self.buyer = BuyerAccount(email="edit-buyer@joybuy.test", status="ACTIVE")
        self.buyer.set_password("OldPassw0rd!")
        self.buyer.save()

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
            email=email, defaults={"display_name": "测试管理员", "password": "x"}
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

    def edit_url(self, buyer=None):
        buyer = buyer or self.buyer
        return f"/api/v1/admin/buyers/accounts/{buyer.public_id}/edit"

    def reset_url(self, buyer=None):
        buyer = buyer or self.buyer
        return f"/api/v1/admin/buyers/accounts/{buyer.public_id}/reset-password"

    def post_json(self, url, payload=None):
        return self.client.post(
            url, data=json.dumps(payload or {}), content_type="application/json"
        )


class BuyerEditTests(BuyerEditBase):
    def test_edit_profile_fields_and_payment_permission(self):
        response = self.post_json(
            self.edit_url(),
            {
                "display_name": "新用户名",
                "email": "new-edit-buyer@joybuy.test",
                "phone_e164": "+44 7700 900123",
                "payment_enabled": False,
                "note": "客服代改资料",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()["buyer"]
        self.assertEqual(body["display_name"], "新用户名")
        self.assertEqual(body["email"], "new-edit-buyer@joybuy.test")
        self.assertEqual(body["phone"], "+447700900123")
        self.assertFalse(body["payment_enabled"])
        self.assertEqual(body["payment_permission"], "已关闭")

        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.phone_e164, "+447700900123")
        audit = AuditLog.objects.get(action="BUYER_EDIT", target_id=str(self.buyer.public_id))
        self.assertEqual(audit.before_state["email"], "edit-buyer@joybuy.test")
        self.assertEqual(audit.after_state["email"], "new-edit-buyer@joybuy.test")
        self.assertFalse(audit.after_state["payment_enabled"])
        self.assertEqual(audit.reason, "客服代改资料")

    def test_edit_email_duplicate_rejected(self):
        BuyerAccount.objects.create(email="taken@joybuy.test", password="x")
        response = self.post_json(self.edit_url(), {"email": "TAKEN@joybuy.test"})
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"]["code"], "EMAIL_TAKEN")
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.email, "edit-buyer@joybuy.test")

    def test_edit_phone_duplicate_and_invalid_rejected(self):
        BuyerAccount.objects.create(phone_e164="+447700900999", password="x")
        response = self.post_json(self.edit_url(), {"phone_e164": "+44 7700 900999"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "PHONE_TAKEN")

        response = self.post_json(self.edit_url(), {"phone_e164": "07700900999"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "PHONE_INVALID")

    def test_edit_cannot_clear_all_identifiers(self):
        # 只剩邮箱的账号：清空邮箱会被拒（手机号也未提供）。
        response = self.post_json(self.edit_url(), {"email": ""})
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"]["code"], "BUYER_IDENTIFIER_REQUIRED")
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.email, "edit-buyer@joybuy.test")

        # 同时清空邮箱并给手机号则允许（至少保留一个标识）。
        response = self.post_json(self.edit_url(), {"email": "", "phone_e164": "+447700900124"})
        self.assertEqual(response.status_code, 200, response.content)
        self.buyer.refresh_from_db()
        self.assertIsNone(self.buyer.email)
        self.assertEqual(self.buyer.phone_e164, "+447700900124")

    def test_edit_balance_writes_wallet_entry(self):
        response = self.post_json(self.edit_url(), {"balance": "100.00", "note": "补偿余额"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["buyer"]["balance"], "100.00")
        entry = BuyerWalletEntry.objects.get(account=self.buyer)
        self.assertEqual(entry.kind, BuyerWalletEntry.Kind.ADJUSTMENT)
        self.assertEqual(entry.amount, Decimal("100.0000"))
        self.assertEqual(entry.note, "补偿余额")
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.balance, Decimal("100.0000"))

    def test_edit_balance_requires_whitelist_permission(self):
        # 只有 buyers.manage 的账号：改资料可以，动余额/白名单 403。
        limited = self._make_staff("buyer-edit-limited@joybuy.test", ("buyers.manage",))
        limited_client = Client()
        token, _session = create_staff_session(
            staff=limited, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        limited_client.cookies["joybuy_staff_session"] = token

        response = limited_client.post(
            self.edit_url(),
            data=json.dumps({"display_name": "仅资料"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)

        for payload in ({"balance": "10.00"}, {"purchase_whitelisted": False}):
            response = limited_client.post(
                self.edit_url(), data=json.dumps(payload), content_type="application/json"
            )
            self.assertEqual(response.status_code, 403, response.content)

    def test_edit_disable_sets_disabled_at_and_enable_clears(self):
        response = self.post_json(self.edit_url(), {"status": "DISABLED", "note": "违规操作"})
        self.assertEqual(response.status_code, 200, response.content)
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.status, BuyerAccount.Status.DISABLED)
        self.assertIsNotNone(self.buyer.disabled_at)
        self.assertEqual(self.buyer.disabled_reason, "违规操作")

        response = self.post_json(self.edit_url(), {"status": "ACTIVE"})
        self.assertEqual(response.status_code, 200, response.content)
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.status, BuyerAccount.Status.ACTIVE)
        self.assertIsNone(self.buyer.disabled_at)
        self.assertEqual(self.buyer.disabled_reason, "")

    def test_edit_display_name_too_long_rejected(self):
        response = self.post_json(self.edit_url(), {"display_name": "名" * 33})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "DISPLAY_NAME_TOO_LONG")


class BuyerResetPasswordTests(BuyerEditBase):
    def test_reset_password_invalidates_old_password_and_sessions(self):
        token, session = create_buyer_session(
            account=self.buyer, ip_address="127.0.0.1", user_agent="test"
        )
        self.assertIsNotNone(resolve_buyer_session(token))

        response = self.post_json(
            self.reset_url(), {"password": "BrandNewPass9", "note": "用户忘记密码"}
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(response.json()["generated_password"])
        self.assertEqual(response.json()["revoked_sessions"], 1)

        self.buyer.refresh_from_db()
        self.assertFalse(self.buyer.check_password("OldPassw0rd!"))
        self.assertTrue(self.buyer.check_password("BrandNewPass9"))
        session.refresh_from_db()
        self.assertIsNotNone(session.revoked_at)
        # 旧 cookie token 立即失效（resolve 要求 revoked_at 为空）。
        self.assertIsNone(resolve_buyer_session(token))
        self.assertEqual(
            BuyerSession.objects.filter(account=self.buyer, revoked_at__isnull=True).count(),
            0,
        )

        # 端到端：旧密码登录 401，新密码登录 200。
        buyer_client = Client()
        old_login = buyer_client.post(
            LOGIN_URL,
            data=json.dumps({"identifier": "edit-buyer@joybuy.test", "password": "OldPassw0rd!"}),
            content_type="application/json",
        )
        self.assertEqual(old_login.status_code, 401, old_login.content)
        new_login = buyer_client.post(
            LOGIN_URL,
            data=json.dumps({"identifier": "edit-buyer@joybuy.test", "password": "BrandNewPass9"}),
            content_type="application/json",
        )
        self.assertEqual(new_login.status_code, 200, new_login.content)

        audit = AuditLog.objects.get(
            action="BUYER_RESET_PASSWORD", target_id=str(self.buyer.public_id)
        )
        self.assertTrue(audit.after_state["password_reset"])
        self.assertEqual(audit.after_state["revoked_sessions"], 1)
        self.assertNotIn("BrandNewPass9", json.dumps(audit.after_state))

    def test_reset_password_generate_returns_plaintext_once(self):
        response = self.post_json(self.reset_url(), {"generate": True})
        self.assertEqual(response.status_code, 200, response.content)
        generated = response.json()["generated_password"]
        self.assertTrue(generated)
        self.assertGreaterEqual(len(generated), 8)
        self.buyer.refresh_from_db()
        self.assertTrue(self.buyer.check_password(generated))
        # 审计里只有「已重设」标记，不含明文。
        audit = AuditLog.objects.get(
            action="BUYER_RESET_PASSWORD", target_id=str(self.buyer.public_id)
        )
        self.assertTrue(audit.after_state["generated"])
        self.assertNotIn(generated, json.dumps(audit.after_state))

    def test_reset_password_too_short_rejected(self):
        response = self.post_json(self.reset_url(), {"password": "short"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "PASSWORD_TOO_SHORT")

    def test_reset_password_buyer_not_found(self):
        response = self.post_json(
            "/api/v1/admin/buyers/accounts/JYUNOTEXIST0000/reset-password",
            {"password": "BrandNewPass9"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "BUYER_NOT_FOUND")

    def test_reset_does_not_touch_last_login(self):
        before = timezone.now() - timedelta(days=1)
        BuyerAccount.objects.filter(pk=self.buyer.pk).update(last_login_at=before)
        self.post_json(self.reset_url(), {"password": "BrandNewPass9"})
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.last_login_at, before)
