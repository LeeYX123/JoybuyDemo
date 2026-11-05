"""HTTP-level tests for the crawl job create API (source_id identity).

The UI bug caught on 2026-11-05: the create API looked SourceCategory up
by a ``public_id`` column that does not exist; these tests exercise the
real HTTP path so serializer/URL wiring mistakes surface here.
"""

import json

from catalog.models import SourceCategory
from crawler_control.models import CrawlJob, CrawlJobSourceSelection
from crawler_control.tests.test_crawler_control_domain import CrawlerControlTestBase


class CrawlJobCreateApiTests(CrawlerControlTestBase):
    def setUp(self):
        super().setUp()
        from accounts_staff.models import (
            PlatformPermission,
            PlatformRole,
            StaffAccount,
            StaffRoleAssignment,
        )
        from accounts_staff.services import create_staff_session

        permission, _ = PlatformPermission.objects.get_or_create(
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
            staff=self.staff, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token
        self.staff_account = self.staff

    def post_json(self, url, payload):
        return self.client.post(url, data=json.dumps(payload), content_type="application/json")

    def test_create_job_by_source_id_over_http(self):
        from django.utils import timezone

        from catalog.models import SourceCategoryTreeVersion
        from catalog.services import save_source_category_version

        version = save_source_category_version(
            source_system="joybuy_uk",
            version_key="uk-test-tree",
            captured_at=timezone.now(),
            nodes=[
                {"source_id": "l2:1405", "name": "Kettles & Toasters", "parent_source_id": None}
            ],
        )
        version.status = SourceCategoryTreeVersion.Status.PUBLISHED
        version.published_at = timezone.now()
        version.save(update_fields=["status", "published_at"])
        uk_catalog = version.catalog
        now_category = SourceCategory.objects.get(catalog=uk_catalog, source_id="l2:1405")

        response = self.post_json(
            "/api/v1/admin/crawlers/jobs",
            {
                "name": "HTTP 建任务",
                "product_limit": 5,
                "source_ids": ["l2:1405"],
                "include_subcategories": False,
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        job = CrawlJob.objects.get(public_id=response.json()["public_id"])
        self.assertEqual(job.source_category.source_id, "l2:1405")
        self.assertEqual(job.source_selections.count(), 1)
        selection = CrawlJobSourceSelection.objects.get(job=job)
        self.assertEqual(selection.source_category, now_category)
        self.assertFalse(selection.include_descendants)
        self.assertEqual(job.status, "READY")

    def test_create_job_rejects_unknown_source_id(self):
        response = self.post_json(
            "/api/v1/admin/crawlers/jobs",
            {"name": "坏类目", "product_limit": 5, "source_ids": ["l2:does-not-exist"]},
        )
        self.assertEqual(response.status_code, 404)
