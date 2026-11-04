import json

from accounts_buyers.models import BuyerAccount
from accounts_staff.models import (
    PlatformPermission,
    PlatformRole,
    StaffAccount,
    StaffRoleAssignment,
)
from accounts_staff.services import create_staff_session
from catalog.product_services import get_or_create_spu_from_source
from django.test import TestCase
from django.urls import reverse


class AdminApiTestBase(TestCase):
    def setUp(self):
        permission, _ = PlatformPermission.objects.get_or_create(
            code="catalog.products.manage",
            defaults={"name": "Manage products"},
        )
        PlatformPermission.objects.get_or_create(
            code="staff.roles.manage", defaults={"name": "Manage staff"}
        )
        PlatformPermission.objects.get_or_create(
            code="crawler.jobs.manage", defaults={"name": "Manage crawlers"}
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
        self.spu, _ = get_or_create_spu_from_source(
            source_system="joybuy", source_id="admin-spu", title="Admin product"
        )
        from catalog.models import Spu

        Spu.objects.filter(pk=self.spu.pk).update(status=Spu.Status.ACTIVE)


class AdminApiTests(AdminApiTestBase):
    def test_search_documents_listing(self):
        response = self.client.get(reverse("admin-search-documents"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("items", response.json())

    def test_unauthenticated_admin_requests_are_401(self):
        self.client.cookies.clear()
        response = self.client.get(reverse("admin-search-documents"))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "STAFF_AUTH_REQUIRED")

    def test_override_diff_roundtrip(self):
        url = reverse("admin-override-diff", kwargs={"spu_public_id": self.spu.public_id})
        diffs = self.client.get(url).json()["diffs"]
        self.assertTrue(any(item["field"] == "title" for item in diffs))

        propose = self.client.post(
            url,
            data=json.dumps(
                {
                    "action": "propose",
                    "field": "title",
                    "value": "Admin title",
                    "reason": "Editorial fix",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(propose.status_code, 200)
        self.assertEqual(propose.json()["status"], "PENDING")

        approve = self.client.post(
            url,
            data=json.dumps(
                {
                    "action": "approve",
                    "field": "title",
                    "decision": "APPROVED",
                    "reason": "Looks good",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(approve.json()["status"], "APPROVED")

        diffs = self.client.get(url).json()["diffs"]
        title_diff = next(item for item in diffs if item["field"] == "title")
        self.assertEqual(title_diff["effective"], "Admin title")
        self.assertTrue(title_diff["differs"])

    def test_unknown_product_override_returns_404(self):
        response = self.client.get(
            reverse(
                "admin-override-diff",
                kwargs={"spu_public_id": "00000000-0000-0000-0000-000000000000"},
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_reviews_listing_and_soft_delete(self):
        from reviews.import_services import import_sampled_reviews

        import_sampled_reviews(
            self.spu,
            [{"source_id": "adm-rev-1", "rating": 4, "reviewer_name": "Guest"}],
            source_system="joybuy",
        )
        listing = self.client.get(reverse("admin-reviews")).json()
        self.assertEqual(listing["items"][0]["status"], "ACTIVE")

        review_public_id = listing["items"][0]["public_id"]
        removed = self.client.post(
            reverse("admin-reviews"),
            data=json.dumps({"review_public_id": review_public_id, "reason": "Spam"}),
            content_type="application/json",
        )
        self.assertEqual(removed.json()["status"], "DELETED")


class BuyerAndOrderAdminTests(AdminApiTestBase):
    def setUp(self):
        super().setUp()
        self.buyer, _ = BuyerAccount.objects.get_or_create(
            email="buyer-x@joybuy.test", defaults={"status": BuyerAccount.Status.ACTIVE}
        )

    def test_buyer_disable_and_enable_never_delete(self):
        response = self.client.post(
            reverse("admin-buyers"),
            data=json.dumps(
                {
                    "buyer_public_id": str(self.buyer.public_id),
                    "action": "disable",
                    "reason": "Abuse report",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.json()["status"], "DISABLED")
        self.assertTrue(BuyerAccount.objects.filter(pk=self.buyer.pk).exists())

        enabled = self.client.post(
            reverse("admin-buyers"),
            data=json.dumps(
                {
                    "buyer_public_id": str(self.buyer.public_id),
                    "action": "enable",
                    "reason": "Appeal accepted",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(enabled.json()["status"], "ACTIVE")

    def test_order_listing_filters_by_status(self):
        listing = self.client.get(reverse("admin-orders")).json()
        self.assertEqual(listing["items"], [])
        pending = self.client.get(reverse("admin-orders"), {"status": "PENDING_PAYMENT"}).json()
        self.assertEqual(pending["items"], [])
