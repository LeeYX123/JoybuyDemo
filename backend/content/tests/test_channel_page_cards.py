"""频道页活动卡片（13.2【品类页卡片展示】）的接口测试。

红线：
1. 管理端 CRUD / 排序 / 上下线，频道维度隔离；
2. 非法 channel_code、非 /media/ 图片一律 400；
3. ``link_url`` 按 13.8 存原值不限制不改写（外链/站内路径/空都原样保存）；
4. 公开接口 ``GET /api/v1/cms/channel-page-cards?channel=<code>`` 只返回该频道
   is_active 且按 sort_order 升序的条目，契约固定为
   ``{items:[{id,image_url,link_url,sort_order}]}``；没配置返回空数组。
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
from content.models import ChannelPageCard

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


class ChannelPageCardTestBase(TestCase):
    def setUp(self):
        role, _ = PlatformRole.objects.update_or_create(
            code="channel-page-card-role",
            defaults={"name": "Channel page card", "is_system": False},
        )
        role.permissions.set(
            [
                PlatformPermission.objects.get_or_create(code=code, defaults={"name": code})[0]
                for code in ("cms.channel_page_cards.manage", "cms.channel_page_cards.view")
            ]
        )
        self.staff = StaffAccount.objects.create(
            email="channel-page-card@joybuy.test", display_name="运营", status="ACTIVE"
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
            slug="home-living-cpc",
            path="home-living-cpc",
            depth=0,
        )
        self.beauty = LocalCategory.objects.create(
            name="Beauty",
            name_en="Beauty",
            name_zh="美妆",
            slug="beauty-cpc",
            path="beauty-cpc",
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

    def make_card(self, *, channel_code=HOME_CODE, sort_order=1, is_active=True, **kwargs):
        return ChannelPageCard.objects.create(
            channel_code=channel_code,
            image_url=kwargs.get("image_url", "/media/cms/original/aa/bb/card.webp"),
            link_url=kwargs.get("link_url", "/c/kitchen"),
            sort_order=sort_order,
            is_active=is_active,
        )


class ChannelPageCardAdminCrudTests(ChannelPageCardTestBase):
    def test_create_and_list_by_channel(self):
        response = self.post(
            "/api/v1/admin/channel-page-cards",
            {
                "channel_code": HOME_CODE,
                "image_url": "/media/cms/card1.webp",
                "link_url": "/c/kitchen",
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        card = ChannelPageCard.objects.get()
        self.assertEqual(card.channel_code, HOME_CODE)
        self.assertEqual(card.sort_order, 1)  # 未指定排序 → 追加到末尾
        self.assertEqual(card.link_url, "/c/kitchen")
        self.assertTrue(card.is_active)

        self.make_card(channel_code=BEAUTY_CODE, sort_order=1)
        listing = self.client.get("/api/v1/admin/channel-page-cards?channel_code=" + HOME_CODE)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["total"], 1)
        self.assertEqual(listing.json()["items"][0]["channel_code"], HOME_CODE)

    def test_update_toggle_move_and_delete(self):
        first = self.make_card(sort_order=1)
        second = self.make_card(sort_order=2, link_url="/c/beauty")

        moved = self.post(
            f"/api/v1/admin/channel-page-cards/{second.public_id}/actions",
            {"action": "move", "direction": "up"},
        )
        self.assertEqual(moved.status_code, 200, moved.content)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.sort_order, second.sort_order), (2, 1))

        toggled = self.post(
            f"/api/v1/admin/channel-page-cards/{second.public_id}/actions",
            {"action": "toggle"},
        )
        self.assertEqual(toggled.status_code, 200)
        self.assertFalse(toggled.json()["card"]["is_active"])

        patched = self.patch(
            f"/api/v1/admin/channel-page-cards/{first.public_id}",
            {"link_url": "/c/new-target", "sort_order": 7},
        )
        self.assertEqual(patched.status_code, 200, patched.content)
        first.refresh_from_db()
        self.assertEqual(first.link_url, "/c/new-target")
        self.assertEqual(first.sort_order, 7)

        deleted = self.client.delete(f"/api/v1/admin/channel-page-cards/{first.public_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(ChannelPageCard.objects.filter(pk=first.pk).exists())

    def test_rejects_unknown_channel_code(self):
        response = self.post(
            "/api/v1/admin/channel-page-cards",
            {"channel_code": "UK-Mini-HP-Nowhere", "image_url": "/media/cms/a.webp"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "CHANNEL_CODE_INVALID")

    def test_rejects_external_image_url(self):
        response = self.post(
            "/api/v1/admin/channel-page-cards",
            {"channel_code": HOME_CODE, "image_url": "https://cdn.example.com/a.png"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "IMAGE_URL_INVALID")

    def test_link_url_stored_verbatim_per_13_8(self):
        """13.8：外链全链接与站内路径都原样存储，不改写不限制。"""
        cases = [
            "https://www.example.com/x",
            "http://www.example.com/x",
            "https://www.joybuy.com/minihome/UK-Mini-HP-Home-Living",
            "www.example.com/x",
            "//cdn.example.com/x",
            "/pages/contact-us",
            "/c/electronics",
        ]
        for link in cases:
            response = self.post(
                "/api/v1/admin/channel-page-cards",
                {
                    "channel_code": HOME_CODE,
                    "image_url": "/media/cms/a.webp",
                    "link_url": link,
                },
            )
            self.assertEqual(response.status_code, 201, response.content)
            self.assertEqual(response.json()["card"]["link_url"], link)
        listing = self.client.get("/api/v1/admin/channel-page-cards?channel_code=" + HOME_CODE)
        self.assertEqual(listing.json()["total"], len(cases))

    def test_channels_endpoint_lists_mapped_roots(self):
        response = self.client.get("/api/v1/admin/channel-page-cards/channels")
        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertEqual({item["channel_code"] for item in items}, {HOME_CODE, BEAUTY_CODE})
        home = next(item for item in items if item["channel_code"] == HOME_CODE)
        self.assertEqual(home["name_zh"], "家居生活")

    def test_channels_endpoint_hides_nav_hidden_roots(self):
        """13.1②：隐藏品类的频道不出现在活动卡片的频道下拉里。"""
        from catalog.search_views import NAV_HIDDEN_ROOT_SLUGS

        hidden_slug = next(iter(NAV_HIDDEN_ROOT_SLUGS))
        hidden = LocalCategory.objects.create(
            name="Hidden Root",
            name_en="Hidden Root",
            name_zh="隐藏品类",
            slug=hidden_slug,
            path=hidden_slug,
            depth=0,
        )
        CategoryMapping.objects.create(
            local_category=hidden,
            source_category=_make_channel_source(f"minihome:UK-Mini-HP-{hidden_slug}"),
            is_primary=True,
        )
        response = self.client.get("/api/v1/admin/channel-page-cards/channels")
        self.assertEqual(response.status_code, 200)
        codes = {item["channel_code"] for item in response.json()["items"]}
        self.assertNotIn(f"UK-Mini-HP-{hidden_slug}", codes)
        self.assertIn(HOME_CODE, codes)

    def test_view_only_staff_cannot_write(self):
        viewer_role, _ = PlatformRole.objects.update_or_create(
            code="channel-page-card-viewer",
            defaults={"name": "Channel page card viewer", "is_system": False},
        )
        viewer_role.permissions.set(
            [
                PlatformPermission.objects.get_or_create(
                    code="cms.channel_page_cards.view", defaults={"name": "view"}
                )[0]
            ]
        )
        viewer = StaffAccount.objects.create(
            email="channel-page-card-viewer@joybuy.test", display_name="只读", status="ACTIVE"
        )
        StaffRoleAssignment.objects.create(staff=viewer, role=viewer_role)
        token, _session = create_staff_session(
            staff=viewer, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )

        self.client.cookies["joybuy_staff_session"] = token
        listing = self.client.get("/api/v1/admin/channel-page-cards")
        self.assertEqual(listing.status_code, 200)
        write = self.post(
            "/api/v1/admin/channel-page-cards",
            {"channel_code": HOME_CODE, "image_url": "/media/cms/a.webp"},
        )
        self.assertEqual(write.status_code, 403)
        self.client.cookies["joybuy_staff_session"] = "invalid-token"
        anon = self.client.get("/api/v1/admin/channel-page-cards")
        self.assertEqual(anon.status_code, 401)


class ChannelPageCardPublicTests(ChannelPageCardTestBase):
    def test_public_contract_sorted_ascending_active_only(self):
        self.make_card(sort_order=2, image_url="/media/cms/second.webp", link_url="/c/b")
        self.make_card(sort_order=1, image_url="/media/cms/first.webp", link_url="/c/a")
        self.make_card(sort_order=3, is_active=False, link_url="/c/off")
        self.make_card(channel_code=BEAUTY_CODE, sort_order=1, link_url="/c/beauty")

        response = self.client.get(f"/api/v1/cms/channel-page-cards?channel={HOME_CODE}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["channel"], HOME_CODE)
        self.assertEqual(payload["total"], 2)
        self.assertEqual([item["sort_order"] for item in payload["items"]], [1, 2])
        self.assertEqual([item["link_url"] for item in payload["items"]], ["/c/a", "/c/b"])
        # 契约字段固定：id/image_url/link_url/sort_order，不混入其他键
        self.assertEqual(
            set(payload["items"][0].keys()), {"id", "image_url", "link_url", "sort_order"}
        )

    def test_public_returns_empty_list_when_unconfigured(self):
        response = self.client.get(f"/api/v1/cms/channel-page-cards?channel={HOME_CODE}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])
        self.assertEqual(response.json()["total"], 0)

    def test_public_requires_channel_param(self):
        response = self.client.get("/api/v1/cms/channel-page-cards")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "CHANNEL_REQUIRED")
