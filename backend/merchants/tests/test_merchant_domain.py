import json

from accounts_staff.models import PlatformRole, StaffAccount
from accounts_staff.services import current_totp_code, provision_totp_device
from django.conf import settings
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.utils import timezone

from merchants.models import (
    Merchant,
    MerchantMembership,
    MerchantRole,
    MerchantSourceMapping,
)
from merchants.services import (
    IMPORT_FALLBACK_NAME,
    IMPORT_FALLBACK_SLUG,
    accessible_merchant_ids,
    get_import_fallback_merchant,
    has_merchant_permission,
    resolve_import_merchant,
)

STAFF_SESSION_URL = "/api/v1/admin/auth/session"
STAFF_LOGIN_URL = "/api/v1/admin/auth/login"


class MerchantDomainTests(TestCase):
    def create_staff(self, email="merchant.staff@example.test"):
        staff = StaffAccount(email=email, display_name="Merchant Staff")
        staff.set_password("StrongPass!234")
        staff.save()
        return staff

    def create_merchant(
        self,
        *,
        slug,
        name,
        status=Merchant.OnboardingStatus.ACTIVE,
        requires_staff_totp=False,
    ):
        return Merchant.objects.create(
            slug=slug,
            display_name=name,
            legal_name=f"{name} Ltd",
            onboarding_status=status,
            requires_staff_totp=requires_staff_totp,
            activated_at=timezone.now() if status == Merchant.OnboardingStatus.ACTIVE else None,
        )

    def add_membership(self, staff, merchant, role_code, status=MerchantMembership.Status.ACTIVE):
        return MerchantMembership.objects.create(
            staff=staff,
            merchant=merchant,
            role=MerchantRole.objects.get(code=role_code),
            status=status,
            joined_at=timezone.now() if status == MerchantMembership.Status.ACTIVE else None,
        )

    def test_staff_can_hold_different_roles_in_multiple_merchants(self):
        staff = self.create_staff()
        merchant_a = self.create_merchant(slug="merchant-a", name="Merchant A")
        merchant_b = self.create_merchant(slug="merchant-b", name="Merchant B")

        owner_membership = self.add_membership(staff, merchant_a, "merchant_owner")
        viewer_membership = self.add_membership(staff, merchant_b, "merchant_viewer")

        self.assertEqual(owner_membership.role.code, "merchant_owner")
        self.assertEqual(viewer_membership.role.code, "merchant_viewer")
        self.assertEqual(staff.merchant_memberships.count(), 2)
        self.assertTrue(
            has_merchant_permission(
                staff=staff,
                merchant=merchant_a,
                permission_code="merchant.catalog.manage",
            )
        )
        self.assertFalse(
            has_merchant_permission(
                staff=staff,
                merchant=merchant_b,
                permission_code="merchant.catalog.manage",
            )
        )
        self.assertEqual(
            list(accessible_merchant_ids(staff, "merchant.catalog.manage")),
            [merchant_a.pk],
        )

    def test_membership_and_merchant_status_enforce_tenant_isolation(self):
        staff = self.create_staff()
        active_merchant = self.create_merchant(slug="active-store", name="Active Store")
        suspended_merchant = self.create_merchant(
            slug="suspended-store",
            name="Suspended Store",
            status=Merchant.OnboardingStatus.SUSPENDED,
        )
        invited_merchant = self.create_merchant(slug="invited-store", name="Invited Store")
        self.add_membership(staff, active_merchant, "merchant_viewer")
        self.add_membership(staff, suspended_merchant, "merchant_owner")
        self.add_membership(
            staff,
            invited_merchant,
            "merchant_owner",
            status=MerchantMembership.Status.INVITED,
        )

        self.assertTrue(
            has_merchant_permission(
                staff=staff,
                merchant=active_merchant,
                permission_code="merchant.orders.view",
            )
        )
        self.assertFalse(
            has_merchant_permission(
                staff=staff,
                merchant=suspended_merchant,
                permission_code="merchant.members.manage",
            )
        )
        self.assertFalse(
            has_merchant_permission(
                staff=staff,
                merchant=invited_merchant,
                permission_code="merchant.members.manage",
            )
        )

    def test_staff_has_only_one_membership_per_merchant(self):
        staff = self.create_staff()
        merchant = self.create_merchant(slug="unique-store", name="Unique Store")
        self.add_membership(staff, merchant, "merchant_owner")

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.add_membership(staff, merchant, "merchant_viewer")

    def test_missing_source_seller_uses_stable_import_fallback(self):
        first = resolve_import_merchant(
            source_system="joybuy",
            source_seller_id=None,
            source_name="",
        )
        second = resolve_import_merchant(
            source_system=" JOYBUY ",
            source_seller_id="   ",
        )

        self.assertEqual(first, second)
        self.assertEqual(first.slug, IMPORT_FALLBACK_SLUG)
        self.assertEqual(first.display_name, IMPORT_FALLBACK_NAME)
        self.assertEqual(first.merchant_type, Merchant.Type.IMPORT_FALLBACK)
        self.assertTrue(first.is_system)
        self.assertTrue(first.is_active)
        self.assertFalse(MerchantSourceMapping.objects.exists())

    def test_source_seller_mapping_is_idempotent_and_preserves_local_name(self):
        first = resolve_import_merchant(
            source_system="Joybuy",
            source_seller_id="seller-42",
            source_name="Original Seller",
            source_url="https://example.test/seller-42",
        )
        second = resolve_import_merchant(
            source_system="joybuy",
            source_seller_id="seller-42",
            source_name="Updated Source Name",
            source_url="https://example.test/new-seller-42",
        )

        self.assertEqual(first, second)
        self.assertEqual(first.display_name, "Original Seller")
        self.assertEqual(first.merchant_type, Merchant.Type.SOURCE_VIRTUAL)
        self.assertEqual(MerchantSourceMapping.objects.count(), 1)
        mapping = MerchantSourceMapping.objects.get()
        self.assertEqual(mapping.source_name, "Updated Source Name")
        self.assertEqual(mapping.source_url, "https://example.test/new-seller-42")

    def test_same_seller_id_from_different_sources_does_not_merge(self):
        joybuy = resolve_import_merchant(
            source_system="joybuy",
            source_seller_id="seller-7",
            source_name="Joybuy Seller",
        )
        other = resolve_import_merchant(
            source_system="other-market",
            source_seller_id="seller-7",
            source_name="Other Seller",
        )

        self.assertNotEqual(joybuy, other)
        self.assertEqual(MerchantSourceMapping.objects.count(), 2)

    def test_merchant_totp_policy_is_enforced_during_staff_login(self):
        staff = self.create_staff()
        merchant = self.create_merchant(
            slug="secure-store",
            name="Secure Store",
            requires_staff_totp=True,
        )
        self.add_membership(staff, merchant, "merchant_owner")
        client = Client(enforce_csrf_checks=True)
        csrf_token = client.get(STAFF_SESSION_URL).json()["csrf_token"]
        payload = {"email": staff.email, "password": "StrongPass!234"}

        missing_device = client.post(
            STAFF_LOGIN_URL,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(missing_device.status_code, 403)
        self.assertEqual(
            missing_device.json()["error"]["code"],
            "STAFF_TOTP_NOT_ENROLLED",
        )

        _, secret, _ = provision_totp_device(staff)
        payload["totp_code"] = current_totp_code(secret)
        authenticated = client.post(
            STAFF_LOGIN_URL,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(authenticated.status_code, 200)
        self.assertIn(settings.STAFF_SESSION_COOKIE_NAME, authenticated.cookies)

    def test_platform_admin_receives_merchant_management_permission(self):
        permission_codes = set(
            PlatformRole.objects.get(code="platform_admin").permissions.values_list(
                "code",
                flat=True,
            )
        )

        self.assertIn("merchants.manage", permission_codes)
        self.assertEqual(get_import_fallback_merchant().display_name, IMPORT_FALLBACK_NAME)
