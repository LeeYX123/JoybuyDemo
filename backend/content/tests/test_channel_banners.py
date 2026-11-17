"""频道页 banner（``/minihome/<code>`` 顶部轮播图）的接口测试。

红线：
1. 管理端 CRUD / 排序 / 上下线，频道维度隔离；
2. 非法 channel_code、非 /media/ 图片、外链 href 一律 400；
3. 公开接口只返回该频道 enabled 且按 sort_order；没配置返回空数组。
"""

import json

from django.test import TestCase
from django.utils import timezone

from accounts_staff.models import (
    PlatformPermission,
    PlatformRole,
    StaffAccount,
    StaffRoleAssignment,
)
from accounts_staff.services import create_staff_session
from catalog.models import CategoryMapping, LocalCategory, SourceCatalog, SourceCategory
from content.models import ChannelBanner

HOME_CODE = "UK-Mini-HP-Home-Living"
BEAUTY_CODE = "UK-Mini-HP-Beauty"


def _make_channel_source(source_id: str) -> SourceCategory:
    catalog, _ = SourceCatalog.objects.get_or_create(
        source_system="joybuy", defaults={"display_name": "Joybuy UK"}
    )
    now = timezone.now()
    return SourceCategory.objects.create(
        catalog=catalog,
        source_id=source_id,
        first_seen_at=now,
        last_seen_at=now,
    )


class ChannelBannerTestBase(TestCase):
    def setUp(self):
        role, _ = PlatformRole.objects.update_or_create(
            code="channel-banner-role", defaults={"name": "Channel banner", "is_system": False}
        )
        role.permissions.set(
            [
                PlatformPermission.objects.get_or_create(code=code, defaults={"name": code})[0]
                for code in ("cms.channel_banners.manage", "cms.channel_banners.view")
            ]
        )
        self.staff = StaffAccount.objects.create(
            email="channel-banner@joybuy.test", display_name="运营", status="ACTIVE"
        )
        StaffRoleAssignment.objects.create(staff=self.staff, role=role)
        token, _session = create_staff_session(
            staff=self.staff, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token

        self.home = LocalCategory.objects.create(
            name="Home & Living",
            name_en="Home & Living",
            name_zh="家居生活",
            slug="home-living-cb",
            path="home-living-cb",
            depth=0,
        )
        self.beauty = LocalCategory.objects.create(
            name="Beauty",
            name_en="Beauty",
            name_zh="美妆",
            slug="beauty-cb",
            path="beauty-cb",
            depth=0,
        )
        for category, source_id in ((self.home, HOME_CODE), (self.beauty, BEAUTY_CODE)):
            CategoryMapping.objects.create(
                local_category=category,
                source_category=_make_channel_source(f"minihome:{source_id}"),
                is_primary=True,
            )

    def post(self, path, payload=None):
        return self.client.post(
            path, data=json.dumps(payload or {}), content_type="application/json"
        )

    def patch(self, path, payload=None):
        return self.client.patch(
            path, data=json.dumps(payload or {}), content_type="application/json"
        )

    def make_banner(self, *, channel_code=HOME_CODE, sort_order=1, enabled=True, **kwargs):
        return ChannelBanner.objects.create(
            channel_code=channel_code,
            image_url=kwargs.get("image_url", "/media/cms/original/aa/bb/banner.webp"),
            href=kwargs.get("href", "/c/mobile-phones"),
            sort_order=sort_order,
            enabled=enabled,
        )


class ChannelBannerAdminCrudTests(ChannelBannerTestBase):
    def test_create_and_list_by_channel(self):
        response = self.post(
            "/api/v1/admin/channel-banners",
            {
                "channel_code": HOME_CODE,
                "image_url": "/media/cms/home.webp",
                "href": "/c/kitchen",
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        banner = ChannelBanner.objects.get()
        self.assertEqual(banner.channel_code, HOME_CODE)
        self.assertEqual(banner.sort_order, 1)  # 未指定排序 → 追加到末尾

        self.make_banner(channel_code=BEAUTY_CODE, sort_order=1)
        listing = self.client.get(
            f"/api/v1/admin/channel-banners?channel_code={HOME_CODE}"
        )
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["total"], 1)
        self.assertEqual(listing.json()["items"][0]["channel_code"], HOME_CODE)

    def test_update_toggle_move_and_delete(self):
        first = self.make_banner(sort_order=1)
        second = self.make_banner(sort_order=2, href="/c/beauty")

        moved = self.post(
            f"/api/v1/admin/channel-banners/{second.public_id}/actions",
            {"action": "move", "direction": "up"},
        )
        self.assertEqual(moved.status_code, 200, moved.content)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.sort_order, second.sort_order), (2, 1))

        toggled = self.post(
            f"/api/v1/admin/channel-banners/{second.public_id}/actions", {"action": "toggle"}
        )
        self.assertEqual(toggled.status_code, 200)
        self.assertFalse(toggled.json()["banner"]["enabled"])

        patched = self.patch(
            f"/api/v1/admin/channel-banners/{first.public_id}",
            {"href": "/c/new-target", "sort_order": 7},
        )
        self.assertEqual(patched.status_code, 200, patched.content)
        first.refresh_from_db()
        self.assertEqual(first.href, "/c/new-target")
        self.assertEqual(first.sort_order, 7)

        deleted = self.client.delete(f"/api/v1/admin/channel-banners/{first.public_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(ChannelBanner.objects.filter(pk=first.pk).exists())

    def test_rejects_unknown_channel_code(self):
        response = self.post(
            "/api/v1/admin/channel-banners",
            {"channel_code": "UK-Mini-HP-Nowhere", "image_url": "/media/cms/a.webp"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "CHANNEL_CODE_INVALID")

    def test_rejects_external_image_url(self):
        response = self.post(
            "/api/v1/admin/channel-banners",
            {"channel_code": HOME_CODE, "image_url": "https://cdn.example.com/a.png"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "IMAGE_URL_INVALID")

    def test_rejects_external_href(self):
        response = self.post(
            "/api/v1/admin/channel-banners",
            {
                "channel_code": HOME_CODE,
                "image_url": "/media/cms/a.webp",
                "href": "https://example.com/out",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "HREF_INVALID")

    def test_channels_endpoint_lists_mapped_roots(self):
        response = self.client.get("/api/v1/admin/channel-banners/channels")
        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertEqual(
            {item["channel_code"] for item in items}, {HOME_CODE, BEAUTY_CODE}
        )
        home = next(item for item in items if item["channel_code"] == HOME_CODE)
        self.assertEqual(home["name_zh"], "家居生活")


class ChannelBannerPublicTests(ChannelBannerTestBase):
    def test_public_returns_only_enabled_in_sort_order(self):
        self.make_banner(sort_order=2, image_url="/media/cms/second.webp")
        self.make_banner(sort_order=1, image_url="/media/cms/first.webp")
        self.make_banner(sort_order=3, enabled=False)
        self.make_banner(channel_code=BEAUTY_CODE, sort_order=1)

        response = self.client.get(f"/api/v1/channel-banners?channel_code={HOME_CODE}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["channel_code"], HOME_CODE)
        self.assertEqual(payload["total"], 2)
        self.assertEqual(
            [item["image_url"] for item in payload["items"]],
            ["/media/cms/first.webp", "/media/cms/second.webp"],
        )

    def test_public_returns_empty_list_when_unconfigured(self):
        response = self.client.get(f"/api/v1/channel-banners?channel_code={HOME_CODE}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])
        self.assertEqual(response.json()["total"], 0)

    def test_public_requires_channel_code(self):
        response = self.client.get("/api/v1/channel-banners")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "CHANNEL_CODE_REQUIRED")
