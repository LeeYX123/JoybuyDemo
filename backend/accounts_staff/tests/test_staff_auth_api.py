import json
import uuid

from audit.models import AuditLog
from django.conf import settings
from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from accounts_staff.models import (
    PlatformRole,
    StaffAccount,
    StaffRoleAssignment,
    StaffSession,
)
from accounts_staff.services import (
    create_staff_session,
    current_totp_code,
    provision_totp_device,
)

SESSION_URL = "/api/v1/admin/auth/session"
LOGIN_URL = "/api/v1/admin/auth/login"
LOGOUT_URL = "/api/v1/admin/auth/logout"
ME_URL = "/api/v1/admin/rbac/me"
BUYER_SESSION_URL = "/api/v1/auth/buyer/session"


class StaffAuthApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(enforce_csrf_checks=True)
        self.csrf_token = self.client.get(SESSION_URL).json()["csrf_token"]

    def request_json(
        self,
        method,
        url,
        payload,
        *,
        client=None,
        include_csrf=True,
        request_id=None,
    ):
        request_client = client or self.client
        headers = {}
        if include_csrf:
            headers["HTTP_X_CSRFTOKEN"] = self.csrf_token
        if request_id:
            headers["HTTP_X_REQUEST_ID"] = request_id
        return getattr(request_client, method)(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            **headers,
        )

    def create_staff(
        self,
        *,
        email="staff@example.test",
        password="StrongPass!234",
        status=StaffAccount.Status.ACTIVE,
        role_code=None,
    ):
        staff = StaffAccount(email=email, display_name="Test Staff", status=status)
        staff.set_password(password)
        staff.save()
        if role_code:
            StaffRoleAssignment.objects.create(
                staff=staff,
                role=PlatformRole.objects.get(code=role_code),
            )
        return staff

    def login(self, staff, *, secret=None, code=None):
        payload = {"email": staff.email, "password": "StrongPass!234"}
        if code is not None:
            payload["totp_code"] = code
        elif secret is not None:
            payload["totp_code"] = current_totp_code(secret)
        return self.request_json("post", LOGIN_URL, payload)

    def test_platform_admin_requires_enrolled_totp_and_current_code(self):
        staff = self.create_staff(role_code="platform_admin")

        not_enrolled = self.login(staff)
        self.assertEqual(not_enrolled.status_code, 403)
        self.assertEqual(not_enrolled.json()["error"]["code"], "STAFF_TOTP_NOT_ENROLLED")

        device, secret, _ = provision_totp_device(staff)
        missing_code = self.login(staff)
        self.assertEqual(missing_code.status_code, 401)
        self.assertEqual(missing_code.json()["error"]["code"], "STAFF_TOTP_REQUIRED")

        invalid_code = "000000"
        if invalid_code == current_totp_code(secret):
            invalid_code = "000001"
        invalid = self.login(staff, code=invalid_code)
        self.assertEqual(invalid.status_code, 401)
        self.assertEqual(invalid.json()["error"]["code"], "INVALID_STAFF_TOTP")

        response = self.login(staff, secret=secret)
        self.assertEqual(response.status_code, 200)
        self.assertIn(settings.STAFF_SESSION_COOKIE_NAME, response.cookies)
        self.assertNotIn(settings.BUYER_SESSION_COOKIE_NAME, response.cookies)
        self.assertTrue(response.cookies[settings.STAFF_SESSION_COOKIE_NAME]["httponly"])
        self.assertTrue(response.json()["staff"]["totp_required"])
        self.assertEqual(self.client.get(ME_URL).status_code, 200)

        device.refresh_from_db()
        self.assertNotIn(secret, device.secret_ciphertext)
        self.assertIsNotNone(device.last_verified_counter)

    def test_totp_code_cannot_be_replayed(self):
        staff = self.create_staff(role_code="platform_admin")
        _, secret, _ = provision_totp_device(staff)
        code = current_totp_code(secret)

        first = self.login(staff, code=code)
        second = self.login(staff, code=code)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 401)
        self.assertEqual(second.json()["error"]["code"], "STAFF_TOTP_REPLAYED")

    def test_non_admin_without_totp_can_login_but_cannot_manage_roles(self):
        limited_role = PlatformRole.objects.create(code="catalog_viewer", name="Catalog viewer")
        staff = self.create_staff()
        StaffRoleAssignment.objects.create(staff=staff, role=limited_role)
        target = self.create_staff(email="target@example.test")

        login_response = self.login(staff)
        role_response = self.request_json(
            "put",
            f"/api/v1/admin/staff/{target.public_id}/roles",
            {"role_codes": ["platform_auditor"], "reason": "Job responsibility change"},
        )

        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(role_response.status_code, 403)
        self.assertEqual(role_response.json()["error"]["code"], "STAFF_PERMISSION_DENIED")
        self.assertFalse(AuditLog.objects.exists())

    def test_existing_session_is_blocked_after_platform_admin_role_is_assigned(self):
        staff = self.create_staff()
        token, _ = create_staff_session(
            staff=staff,
            ip_address="127.0.0.1",
            user_agent="test",
            totp_verified=False,
        )
        self.client.cookies[settings.STAFF_SESSION_COOKIE_NAME] = token
        StaffRoleAssignment.objects.create(
            staff=staff,
            role=PlatformRole.objects.get(code="platform_admin"),
        )

        response = self.client.get(ME_URL)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "STAFF_TOTP_REQUIRED")

    def test_role_assignment_records_actor_request_and_change_details(self):
        admin = self.create_staff(role_code="platform_admin")
        _, secret, _ = provision_totp_device(admin)
        self.assertEqual(self.login(admin, secret=secret).status_code, 200)
        target = self.create_staff(email="target@example.test", role_code="platform_auditor")
        request_id = str(uuid.uuid4())

        response = self.request_json(
            "put",
            f"/api/v1/admin/staff/{target.public_id}/roles",
            {"role_codes": ["platform_admin"], "reason": "Approved duty escalation"},
            request_id=request_id,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["staff"]["roles"], ["platform_admin"])
        audit = AuditLog.objects.get()
        self.assertEqual(audit.actor, admin)
        self.assertEqual(str(audit.request_id), request_id)
        self.assertEqual(audit.ip_address, "127.0.0.1")
        self.assertEqual(audit.reason, "Approved duty escalation")
        self.assertEqual(audit.before_state, {"roles": ["platform_auditor"]})
        self.assertEqual(audit.after_state, {"roles": ["platform_admin"]})
        self.assertEqual(audit.target_id, str(target.public_id))

    def test_anonymous_admin_api_returns_auth_required(self):
        response = self.client.get(ME_URL)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "STAFF_AUTH_REQUIRED")

    def test_disabled_staff_account_cannot_login(self):
        staff = self.create_staff(status=StaffAccount.Status.DISABLED)

        response = self.login(staff)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "STAFF_ACCOUNT_DISABLED")

    @override_settings(STAFF_LOGIN_FAILURE_LIMIT=2)
    def test_failed_staff_logins_are_rate_limited(self):
        staff = self.create_staff()
        payload = {"email": staff.email, "password": "wrong-password"}

        first = self.request_json("post", LOGIN_URL, payload)
        second = self.request_json("post", LOGIN_URL, payload)
        third = self.request_json("post", LOGIN_URL, payload)

        self.assertEqual(first.status_code, 401)
        self.assertEqual(second.status_code, 401)
        self.assertEqual(third.status_code, 429)
        self.assertEqual(third.json()["error"]["code"], "STAFF_LOGIN_RATE_LIMITED")

    def test_staff_and_buyer_sessions_are_isolated_and_logout_revokes_staff_session(self):
        staff = self.create_staff()
        self.assertEqual(self.login(staff).status_code, 200)
        self.assertFalse(self.client.get(BUYER_SESSION_URL).json()["authenticated"])

        logout = self.request_json("post", LOGOUT_URL, {})

        self.assertEqual(logout.status_code, 204)
        self.assertFalse(self.client.get(SESSION_URL).json()["authenticated"])
        self.assertIsNotNone(StaffSession.objects.get(staff=staff).revoked_at)

    def test_staff_writes_require_csrf(self):
        response = self.request_json(
            "post",
            LOGIN_URL,
            {"email": "staff@example.test", "password": "StrongPass!234"},
            include_csrf=False,
        )

        self.assertEqual(response.status_code, 403)

    def test_staff_session_cookie_is_not_a_django_or_buyer_cookie(self):
        self.assertNotEqual(settings.STAFF_SESSION_COOKIE_NAME, settings.SESSION_COOKIE_NAME)
        self.assertNotEqual(settings.STAFF_SESSION_COOKIE_NAME, settings.BUYER_SESSION_COOKIE_NAME)
