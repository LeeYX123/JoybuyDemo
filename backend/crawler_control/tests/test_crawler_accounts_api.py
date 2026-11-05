"""Admin crawler-account API tests (2026-11-05 round 2).

Covers: create/list, disable/enable, logout expiry, verify marking an
expired session, and the login spawn path (mocked subprocess — the real
headed window is a manual flow). Passwords are never part of any payload
(docs/05 §7.1); permission gate = ``crawler.accounts.manage``.
"""

import sys
import uuid
from importlib.util import find_spec
from pathlib import Path
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from accounts_staff.models import (
    PlatformPermission,
    PlatformRole,
    StaffAccount,
    StaffRoleAssignment,
)
from accounts_staff.services import create_staff_session
from crawler_control.models import CrawlerAccount
from crawler_control.services import create_crawler_account

CRAWLER_DIR = Path(__file__).resolve().parents[3] / "crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

DRITION_AVAILABLE = find_spec("DrissionPage") is not None


class CrawlerAccountsApiTestBase(TestCase):
    def setUp(self):
        permission, _ = PlatformPermission.objects.get_or_create(
            code="crawler.accounts.manage",
            defaults={"name": "Manage crawler accounts"},
        )
        role, _ = PlatformRole.objects.get_or_create(
            code="platform_admin", defaults={"name": "Platform admin", "is_platform_admin": True}
        )
        role.permissions.add(permission)
        self.staff, _ = StaffAccount.objects.get_or_create(
            email="ops@joybuy.test",
            defaults={"display_name": "Ops", "password": "x", "status": StaffAccount.Status.ACTIVE},
        )
        StaffRoleAssignment.objects.get_or_create(staff=self.staff, role=role)
        token, _session = create_staff_session(
            staff=self.staff,
            ip_address="127.0.0.1",
            user_agent="test",
            totp_verified=True,
        )
        self.client.cookies["joybuy_staff_session"] = token

    def post_json(self, url, payload):
        import json

        return self.client.post(url, data=json.dumps(payload), content_type="application/json")


class CrawlerAccountCrudTests(CrawlerAccountsApiTestBase):
    def test_create_and_list_accounts(self):
        response = self.post_json(
            reverse("admin-crawl-accounts"),
            {"label": "FB 主账号", "account_group": "default", "note": "运营专用"},
        )
        self.assertEqual(response.status_code, 201)
        public_id = response.json()["public_id"]

        listing = self.client.get(reverse("admin-crawl-accounts"))
        self.assertEqual(listing.status_code, 200)
        rows = listing.json()["items"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["public_id"], public_id)
        self.assertEqual(rows[0]["label"], "FB 主账号")
        self.assertEqual(rows[0]["session_status"], "UNKNOWN")
        # The API must never expose the encrypted session blob.
        self.assertNotIn("session_cipher", rows[0])

    def test_create_requires_label(self):
        response = self.post_json(reverse("admin-crawl-accounts"), {"label": "  "})
        self.assertEqual(response.status_code, 400)

    def test_disable_then_enable_account(self):
        account = create_crawler_account(label="Toggle", account_group="default")
        url = reverse("admin-crawl-account-actions", args=[account.public_id])
        self.assertEqual(self.post_json(url, {"action": "disable"}).json()["status"], "DISABLED")
        account.refresh_from_db()
        self.assertEqual(account.status, CrawlerAccount.Status.DISABLED)
        self.assertEqual(self.post_json(url, {"action": "enable"}).json()["status"], "ACTIVE")

    def test_risk_paused_account_cannot_be_enabled_directly(self):
        from crawler_control.services import flag_account_risk_control

        account = create_crawler_account(label="Risky", account_group="default")
        flag_account_risk_control(account, reason="wall")
        url = reverse("admin-crawl-account-actions", args=[account.public_id])
        response = self.post_json(url, {"action": "enable"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.post_json(url, {"action": "reactivate"}).json()["status"], "ACTIVE")

    def test_logout_expires_session(self):
        from crawler_control.services import record_account_session

        account = create_crawler_account(label="Sess", account_group="default")
        record_account_session(account, {"cookies": [{"name": "a", "value": "b"}]})
        url = reverse("admin-crawl-account-actions", args=[account.public_id])
        self.assertEqual(self.post_json(url, {"action": "logout"}).json()["status"], "EXPIRED")
        account.refresh_from_db()
        self.assertEqual(account.session_status, CrawlerAccount.SessionStatus.EXPIRED)
        self.assertEqual(account.session_cipher, "")

    def test_verify_marks_session_valid_without_browser(self):
        """verify with mocked render: signed-in homepage keeps the session."""

        from crawler_control.services import record_account_session

        account = create_crawler_account(label="Verify", account_group="default")
        record_account_session(
            account,
            {"cookies": [{"name": "joybuy_session", "value": "x", "domain": ".joybuy.co.uk"}]},
        )
        url = reverse("admin-crawl-account-actions", args=[account.public_id])

        page = mock.MagicMock()
        page.error = ""
        page.risk_control = False
        page.html = "<html><head><title>Joybuy</title></head><body>" + "x" * 3000 + "</body></html>"
        with mock.patch("joybuy_crawler.render.render_page", return_value=page) as render_mock:
            with mock.patch("joybuy_crawler.render._visible_text", return_value="a" * 2500):
                response = self.post_json(url, {"action": "verify"})
        self.assertTrue(response.json()["verified"])
        account.refresh_from_db()
        self.assertEqual(account.session_status, CrawlerAccount.SessionStatus.VALID)
        self.assertIsNotNone(account.last_verified_at)
        render_mock.assert_called_once()

    def test_verify_marks_expired_when_sign_in_visible(self):
        from crawler_control.services import record_account_session

        account = create_crawler_account(label="Verify2", account_group="default")
        record_account_session(
            account,
            {"cookies": [{"name": "joybuy_session", "value": "x", "domain": ".joybuy.co.uk"}]},
        )
        url = reverse("admin-crawl-account-actions", args=[account.public_id])

        page = mock.MagicMock()
        page.error = ""
        page.risk_control = False
        page.html = "<html><body>Sign in Joybuy homepage " + "x" * 3000 + "</body></html>"
        with mock.patch("joybuy_crawler.render.render_page", return_value=page):
            with mock.patch(
                "joybuy_crawler.render._visible_text",
                return_value="Sign in Joybuy homepage " + "y" * 2500,
            ):
                response = self.post_json(url, {"action": "verify"})
        self.assertFalse(response.json()["verified"])
        self.assertEqual(response.json()["reason"], "SESSION_EXPIRED")
        account.refresh_from_db()
        self.assertEqual(account.session_status, CrawlerAccount.SessionStatus.EXPIRED)

    def test_verify_without_session_reports_no_session(self):
        account = create_crawler_account(label="NoSess", account_group="default")
        url = reverse("admin-crawl-account-actions", args=[account.public_id])
        response = self.post_json(url, {"action": "verify"})
        self.assertFalse(response.json()["verified"])
        self.assertEqual(response.json()["reason"], "NO_SESSION")

    def test_login_spawns_detached_process(self):
        account = create_crawler_account(label="LoginWin", account_group="default")
        url = reverse("admin-crawl-account-actions", args=[account.public_id])
        with mock.patch(
            "common.admin_views.AdminCrawlerAccountActionsView._spawn_login_window",
            return_value={"status": "LOGIN_PENDING"},
        ) as spawn_mock:
            response = self.post_json(url, {"action": "login"})
        self.assertEqual(response.json()["status"], "LOGIN_PENDING")
        spawn_mock.assert_called_once()

    def test_actions_require_manage_permission(self):
        other, _ = StaffAccount.objects.get_or_create(
            email="noperm@joybuy.test",
            defaults={"display_name": "NoPerm", "password": "x", "status": "ACTIVE"},
        )
        limited_role, _ = PlatformRole.objects.get_or_create(
            code="platform_auditor", defaults={"name": "Auditor"}
        )
        StaffRoleAssignment.objects.get_or_create(staff=other, role=limited_role)
        token, _session = create_staff_session(
            staff=other, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        client_no_perm = self.client_class()
        client_no_perm.cookies["joybuy_staff_session"] = token

        response = client_no_perm.get(reverse("admin-crawl-accounts"))
        self.assertEqual(response.status_code, 403)

    def test_unknown_account_404(self):
        url = reverse("admin-crawl-account-actions", args=[uuid.uuid4()])
        response = self.post_json(url, {"action": "verify"})
        self.assertEqual(response.status_code, 404)


class CrawlerAccountManagementTests(CrawlerAccountsApiTestBase):
    """Groups are real rows; accounts are editable and soft-deletable."""

    def put_json(self, url, payload):
        import json

        return self.client.put(url, data=json.dumps(payload), content_type="application/json")

    def test_groups_are_seeded_and_listable(self):
        response = self.client.get(reverse("admin-crawl-account-groups"))
        self.assertEqual(response.status_code, 200)
        names = [item["name"] for item in response.json()["items"]]
        self.assertIn("default", names)

    def test_create_group_then_use_it_for_an_account(self):
        created = self.post_json(
            reverse("admin-crawl-account-groups"), {"name": "轮换池A", "note": "轮换用"}
        )
        self.assertEqual(created.status_code, 201, created.content)

        account = create_crawler_account(label="A1", account_group="轮换池A")
        self.assertEqual(account.account_group, "轮换池A")

        groups = {
            item["name"]: item
            for item in self.client.get(reverse("admin-crawl-account-groups")).json()["items"]
        }
        self.assertEqual(groups["轮换池A"]["account_count"], 1)

    def test_duplicate_group_is_rejected(self):
        url = reverse("admin-crawl-account-groups")
        self.assertEqual(self.post_json(url, {"name": "重复组"}).status_code, 201)
        self.assertEqual(self.post_json(url, {"name": "重复组"}).status_code, 400)

    def test_group_name_is_required(self):
        response = self.post_json(reverse("admin-crawl-account-groups"), {"name": "  "})
        self.assertEqual(response.status_code, 400)

    def test_edit_label_group_and_note(self):
        create_crawler_account(label="改名前", account_group="default")
        account = CrawlerAccount.objects.get(label="改名前")
        response = self.put_json(
            reverse("admin-crawl-account-detail", args=[account.public_id]),
            {"label": "改名后", "account_group": "轮换池B", "note": "挪组"},
        )
        self.assertEqual(response.status_code, 200, response.content)
        account.refresh_from_db()
        self.assertEqual(account.label, "改名后")
        self.assertEqual(account.account_group, "轮换池B")
        self.assertEqual(account.note, "挪组")

    def test_edit_rejects_blank_label(self):
        create_crawler_account(label="空名测试", account_group="default")
        account = CrawlerAccount.objects.get(label="空名测试")
        response = self.put_json(
            reverse("admin-crawl-account-detail", args=[account.public_id]),
            {"label": "   "},
        )
        self.assertEqual(response.status_code, 400)

    def test_delete_hides_the_account_and_destroys_the_session(self):
        from crawler_control.services import record_account_session

        account = create_crawler_account(label="待删除", account_group="default")
        record_account_session(
            account, {"cookies": [{"name": "pinId", "value": "x", "domain": ".joybuy.co.uk"}]}
        )
        response = self.client.delete(
            reverse("admin-crawl-account-detail", args=[account.public_id])
        )
        self.assertEqual(response.status_code, 200, response.content)

        account.refresh_from_db()
        # 软删除：行还在（历史运行仍能显示账号名），但凭据已销毁。
        self.assertIsNotNone(account.deleted_at)
        self.assertEqual(account.session_cipher, "")
        self.assertEqual(account.session_status, CrawlerAccount.SessionStatus.UNKNOWN)
        self.assertEqual(account.status, CrawlerAccount.Status.DISABLED)

        listing = self.client.get(reverse("admin-crawl-accounts")).json()["items"]
        self.assertNotIn(account.public_id, [row["public_id"] for row in listing])

    def test_deleted_account_cannot_be_edited_or_actioned(self):
        account = create_crawler_account(label="已删除", account_group="default")
        self.client.delete(reverse("admin-crawl-account-detail", args=[account.public_id]))
        self.assertEqual(
            self.put_json(
                reverse("admin-crawl-account-detail", args=[account.public_id]),
                {"label": "想改"},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.post_json(
                reverse("admin-crawl-account-actions", args=[account.public_id]),
                {"action": "enable"},
            ).status_code,
            404,
        )
