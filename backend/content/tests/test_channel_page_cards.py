"""频道页活动卡片（13.2【品类页卡片展示】）的接口测试。

红线：
1. 管理端 CRUD / 排序 / 上下线，频道维度隔离；
2. 非法 channel_code、非 /media/ 图片一律 400；
3. ``link_url`` 按 13.8 存原值不限制不改写（外链/站内路径/空都原样保存）；
4. 公开接口 ``GET /api/v1/cms/channel-page-cards?channel=<code>`` 只返回该频道
   is_active 且按 ``group_index`` + ``sort_order`` 升序的条目，契约固定为
   ``{channel,layout,groups:[{group_index,layout,count}],
   items:[{id,group_index,image_url,link_url,sort_order,layout}],total}``；
   没配置返回空数组。
5. ``layout`` 是**组级**属性：任意一张卡写入 layout 后，只有同频道同组
   （同 ``group_index``）的卡片同步为同一值，其它组不受影响。
"""

import importlib
import json

from django.apps import apps
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
            group_index=kwargs.get("group_index", 0),
            image_url=kwargs.get("image_url", "/media/cms/original/aa/bb/card.webp"),
            link_url=kwargs.get("link_url", "/c/kitchen"),
            sort_order=sort_order,
            is_active=is_active,
            layout=kwargs.get("layout", "row3"),
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


class ChannelPageCardLayoutTests(ChannelPageCardTestBase):
    """``layout`` 是**组级**属性（13.2 布局能力）：非法值拒绝 + 只同步本组。"""

    def test_rejects_invalid_layout_on_create_and_update(self):
        bad = self.post(
            "/api/v1/admin/channel-page-cards",
            {
                "channel_code": HOME_CODE,
                "image_url": "/media/cms/a.webp",
                "layout": "carousel",
            },
        )
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.json()["error"]["code"], "LAYOUT_INVALID")
        self.assertIn("row2", bad.json()["error"]["message"])
        self.assertFalse(ChannelPageCard.objects.exists())

        card = self.make_card()
        patched = self.patch(
            f"/api/v1/admin/channel-page-cards/{card.public_id}", {"layout": "grid3"}
        )
        self.assertEqual(patched.status_code, 400)
        self.assertEqual(patched.json()["error"]["code"], "LAYOUT_INVALID")
        card.refresh_from_db()
        self.assertEqual(card.layout, "row3")

    def test_update_layout_syncs_every_card_of_that_group_only(self):
        self.make_card(sort_order=1)
        second = self.make_card(sort_order=2)
        self.make_card(sort_order=3)
        other_group = self.make_card(sort_order=1, group_index=1, layout="row2")
        other_channel = self.make_card(channel_code=BEAUTY_CODE, sort_order=1)

        patched = self.patch(
            f"/api/v1/admin/channel-page-cards/{second.public_id}",
            {"layout": "row3_scroll"},
        )
        self.assertEqual(patched.status_code, 200, patched.content)
        self.assertEqual(patched.json()["card"]["layout"], "row3_scroll")
        group_layouts = set(
            ChannelPageCard.objects.filter(channel_code=HOME_CODE, group_index=0).values_list(
                "layout", flat=True
            )
        )
        self.assertEqual(group_layouts, {"row3_scroll"})
        other_group.refresh_from_db()
        self.assertEqual(other_group.layout, "row2")
        other_channel.refresh_from_db()
        self.assertEqual(other_channel.layout, "row3")

        listing = self.client.get(
            "/api/v1/admin/channel-page-cards?channel_code=" + HOME_CODE
        ).json()
        by_group = {}
        for item in listing["items"]:
            by_group.setdefault(item["group_index"], set()).add(item["layout"])
        self.assertEqual(by_group, {0: {"row3_scroll"}, 1: {"row2"}})
        detail = self.client.get(f"/api/v1/admin/channel-page-cards/{second.public_id}")
        self.assertEqual(detail.json()["card"]["layout"], "row3_scroll")

    def test_create_with_group_index_and_layout_syncs_only_that_group(self):
        self.make_card(sort_order=1)
        self.make_card(sort_order=2)

        created = self.post(
            "/api/v1/admin/channel-page-cards",
            {
                "channel_code": HOME_CODE,
                "group_index": 1,
                "image_url": "/media/cms/new.webp",
                "layout": "row2",
            },
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["card"]["group_index"], 1)
        self.assertEqual(created.json()["card"]["layout"], "row2")
        self.assertEqual(created.json()["card"]["sort_order"], 1)  # 组内追加，不跨组算
        layouts = set(
            ChannelPageCard.objects.filter(channel_code=HOME_CODE, group_index=0).values_list(
                "layout", flat=True
            )
        )
        self.assertEqual(layouts, {"row3"})

    def test_rejects_invalid_group_index(self):
        card = self.make_card()
        patched = self.patch(
            f"/api/v1/admin/channel-page-cards/{card.public_id}", {"group_index": -1}
        )
        self.assertEqual(patched.status_code, 400)
        self.assertEqual(patched.json()["error"]["code"], "GROUP_INDEX_INVALID")

    def test_move_card_stays_inside_its_group(self):
        first = self.make_card(sort_order=1, group_index=0)
        second = self.make_card(sort_order=2, group_index=0)
        other = self.make_card(sort_order=1, group_index=1, layout="row2")

        moved = self.post(
            f"/api/v1/admin/channel-page-cards/{second.public_id}/actions",
            {"action": "move", "direction": "up"},
        )
        self.assertEqual(moved.status_code, 200, moved.content)
        first.refresh_from_db()
        second.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual((first.sort_order, second.sort_order), (2, 1))
        self.assertEqual(other.sort_order, 1)

        at_edge = self.post(
            f"/api/v1/admin/channel-page-cards/{second.public_id}/actions",
            {"action": "move", "direction": "up"},
        )
        self.assertEqual(at_edge.status_code, 400)
        self.assertEqual(at_edge.json()["error"]["code"], "MOVE_AT_EDGE")

    def test_create_with_layout_syncs_existing_cards(self):
        self.make_card(sort_order=1)
        self.make_card(sort_order=2)

        created = self.post(
            "/api/v1/admin/channel-page-cards",
            {
                "channel_code": HOME_CODE,
                "image_url": "/media/cms/new.webp",
                "layout": "grid2x2",
            },
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["card"]["layout"], "grid2x2")
        layouts = set(
            ChannelPageCard.objects.filter(channel_code=HOME_CODE).values_list("layout", flat=True)
        )
        self.assertEqual(layouts, {"grid2x2"})

    def test_new_card_without_layout_inherits_group_layout(self):
        self.make_card(sort_order=1, layout="row3_scroll")
        created = self.post(
            "/api/v1/admin/channel-page-cards",
            {"channel_code": HOME_CODE, "image_url": "/media/cms/new.webp"},
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["card"]["layout"], "row3_scroll")

    def test_new_card_in_new_group_defaults_to_row3(self):
        self.make_card(sort_order=1, layout="row3_scroll")
        created = self.post(
            "/api/v1/admin/channel-page-cards",
            {"channel_code": HOME_CODE, "group_index": 1, "image_url": "/media/cms/new.webp"},
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["card"]["layout"], "row3")

    def test_card_moved_to_another_channel_adopts_target_layout(self):
        self.make_card(channel_code=BEAUTY_CODE, sort_order=1, layout="grid2x2")
        card = self.make_card(sort_order=1, layout="row3")

        patched = self.patch(
            f"/api/v1/admin/channel-page-cards/{card.public_id}",
            {"channel_code": BEAUTY_CODE},
        )
        self.assertEqual(patched.status_code, 200, patched.content)
        card.refresh_from_db()
        self.assertEqual(card.layout, "grid2x2")
        self.assertEqual(patched.json()["card"]["layout"], "grid2x2")

    def test_card_moved_to_another_group_adopts_that_group_layout(self):
        self.make_card(sort_order=1, group_index=1, layout="row2")
        card = self.make_card(sort_order=1, group_index=0, layout="row3")

        patched = self.patch(
            f"/api/v1/admin/channel-page-cards/{card.public_id}",
            {"group_index": 1},
        )
        self.assertEqual(patched.status_code, 200, patched.content)
        card.refresh_from_db()
        self.assertEqual((card.group_index, card.layout), (1, "row2"))

    def test_data_migration_writes_channel_defaults_idempotently(self):
        health = "UK-Mini-HP-Health-and-Wellness"
        baby = "UK-Mini-HP-Toys-Baby-and-Kids"
        for position in range(1, 7):
            self.make_card(channel_code=health, sort_order=position)
        for position in range(1, 5):
            self.make_card(channel_code=baby, sort_order=position)
        self.make_card(channel_code=HOME_CODE, sort_order=1)

        migration = importlib.import_module(
            "content.migrations.0016_seed_channel_page_card_layouts"
        )

        def layouts(channel_code):
            return set(
                ChannelPageCard.objects.filter(channel_code=channel_code).values_list(
                    "layout", flat=True
                )
            )

        migration.apply_channel_layouts(apps, None)
        self.assertEqual(layouts(health), {"row3_scroll"})
        self.assertEqual(layouts(baby), {"grid2x2"})
        self.assertEqual(layouts(HOME_CODE), {"row3"})

        total = ChannelPageCard.objects.count()
        migration.apply_channel_layouts(apps, None)  # 重复跑不炸、不新增行
        self.assertEqual(ChannelPageCard.objects.count(), total)
        self.assertEqual(layouts(health), {"row3_scroll"})

        migration.revert_channel_layouts(apps, None)
        self.assertEqual(set(ChannelPageCard.objects.values_list("layout", flat=True)), {"row3"})


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
        # 契约字段固定：id/group_index/image_url/link_url/sort_order/layout，不混入其他键
        self.assertEqual(
            set(payload["items"][0].keys()),
            {"id", "group_index", "image_url", "link_url", "sort_order", "layout"},
        )
        self.assertEqual(payload["layout"], "row3")
        self.assertEqual(payload["groups"], [{"group_index": 0, "layout": "row3", "count": 2}])

    def test_public_orders_items_by_group_then_sort(self):
        self.make_card(sort_order=1, group_index=1, layout="row2", link_url="/c/g1")
        self.make_card(sort_order=2, group_index=0, link_url="/c/g0b")
        self.make_card(sort_order=1, group_index=0, link_url="/c/g0a")

        payload = self.client.get(f"/api/v1/cms/channel-page-cards?channel={HOME_CODE}").json()
        self.assertEqual(
            [(item["group_index"], item["sort_order"]) for item in payload["items"]],
            [(0, 1), (0, 2), (1, 1)],
        )
        self.assertEqual(
            payload["groups"],
            [
                {"group_index": 0, "layout": "row3", "count": 2},
                {"group_index": 1, "layout": "row2", "count": 1},
            ],
        )

    def test_public_groups_follow_multi_group_channels(self):
        """宠物 2 组（截断后只保留第一组前 3 张）、母婴豁免不截断、游戏空组。"""

        setup = {
            "UK-Mini-HP-Pets": [(0, "row3_scroll", 4), (1, "row2", 2)],
            "UK-Mini-HP-Toys-Baby-and-Kids": [(0, "row2", 2), (1, "row2", 2)],
        }
        for channel_code, groups in setup.items():
            for group_index, layout, count in groups:
                for position in range(1, count + 1):
                    self.make_card(
                        channel_code=channel_code,
                        group_index=group_index,
                        sort_order=position,
                        layout=layout,
                    )
        # 游戏：组 #1 是品牌卡，不保留任何组（行存在但全部下线）。
        for position in range(1, 4):
            self.make_card(channel_code="UK-Mini-HP-Gaming", sort_order=position, is_active=False)

        pets = self.client.get("/api/v1/cms/channel-page-cards?channel=UK-Mini-HP-Pets").json()
        # ADR-0002：上限 3 → 组#0 只留前 3 张，组#1 整组不出现。
        self.assertEqual(
            pets["groups"],
            [{"group_index": 0, "layout": "row3_scroll", "count": 3}],
        )
        self.assertEqual(pets["total"], 3)
        self.assertEqual(pets["layout"], "row3_scroll")

        baby = self.client.get(
            "/api/v1/cms/channel-page-cards?channel=UK-Mini-HP-Toys-Baby-and-Kids"
        ).json()
        # 母婴童玩豁免（0027 种子行 max_cards=NULL）→ 4 张全保留。
        self.assertEqual(
            baby["groups"],
            [
                {"group_index": 0, "layout": "row2", "count": 2},
                {"group_index": 1, "layout": "row2", "count": 2},
            ],
        )
        self.assertEqual(baby["total"], 4)

        gaming = self.client.get("/api/v1/cms/channel-page-cards?channel=UK-Mini-HP-Gaming").json()
        self.assertEqual(gaming["groups"], [])
        self.assertEqual(gaming["items"], [])
        self.assertEqual(gaming["layout"], "row3")

    def test_public_returns_channel_level_layout(self):
        self.make_card(sort_order=1, layout="row3_scroll")
        self.make_card(sort_order=2, layout="row3_scroll")
        self.make_card(sort_order=3, is_active=False, layout="row3_scroll")

        payload = self.client.get(f"/api/v1/cms/channel-page-cards?channel={HOME_CODE}").json()
        self.assertEqual(payload["layout"], "row3_scroll")
        self.assertEqual([item["layout"] for item in payload["items"]], ["row3_scroll"] * 2)

    def test_public_layout_defaults_to_row3_when_channel_unconfigured(self):
        payload = self.client.get(f"/api/v1/cms/channel-page-cards?channel={HOME_CODE}").json()
        self.assertEqual(payload["layout"], "row3")
        self.assertEqual(payload["groups"], [])

    def test_public_returns_empty_list_when_unconfigured(self):
        response = self.client.get(f"/api/v1/cms/channel-page-cards?channel={HOME_CODE}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])
        self.assertEqual(response.json()["total"], 0)

    def test_public_requires_channel_param(self):
        response = self.client.get("/api/v1/cms/channel-page-cards")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "CHANNEL_REQUIRED")


class ChannelPageCardGroupMigrationTests(ChannelPageCardTestBase):
    """0018 数据迁移：把已有行纠正到「每频道多组」之前的最终基线状态。"""

    CHANNELS = {
        "UK-Mini-HP-Home-Living": "row3",
        "UK-Mini-HP-Electronics": "row3",
        "UK-Mini-HP-Beauty": "row3",
        "UK-Mini-HP-Home-Appliances": "row3",
        "UK-Mini-HP-Health-and-Wellness": "row3_scroll",
        "mini-hp-nl-sports-outdoor": "row3",
        "UK-Mini-HP-Pets": "row3_scroll",
        "UK-Mini-HP-Toys-Baby-and-Kids": "row2",
        "UK-Mini-HP-Gaming": "row3",
    }

    def _seed(self):
        # 故意用历史值：母婴 grid2x2、健康 row3_scroll、其余 row3；游戏是 active。
        for channel_code in self.CHANNELS:
            layout = "grid2x2" if channel_code.endswith("Toys-Baby-and-Kids") else "row3"
            if channel_code.endswith("Health-and-Wellness"):
                layout = "row3_scroll"
            self.make_card(channel_code=channel_code, sort_order=1, layout=layout)

    def _layouts(self, channel_code):
        return set(
            ChannelPageCard.objects.filter(channel_code=channel_code).values_list(
                "layout", flat=True
            )
        )

    def test_migration_sets_final_layouts_and_groups(self):
        migration = importlib.import_module(
            "content.migrations.0018_channelpagecard_group_defaults"
        )
        self._seed()
        total = ChannelPageCard.objects.count()

        migration.apply_final_state(apps, None)
        for channel_code, layout in self.CHANNELS.items():
            self.assertEqual(self._layouts(channel_code), {layout}, channel_code)
        self.assertEqual(set(ChannelPageCard.objects.values_list("group_index", flat=True)), {0})
        gaming = ChannelPageCard.objects.filter(channel_code="UK-Mini-HP-Gaming")
        self.assertEqual(gaming.count(), 1)  # 行保留不删
        self.assertFalse(gaming.filter(is_active=True).exists())
        self.assertEqual(
            ChannelPageCard.objects.exclude(channel_code="UK-Mini-HP-Gaming")
            .filter(is_active=False)
            .count(),
            0,
        )

        migration.apply_final_state(apps, None)  # 幂等
        self.assertEqual(ChannelPageCard.objects.count(), total)
        for channel_code, layout in self.CHANNELS.items():
            self.assertEqual(self._layouts(channel_code), {layout}, channel_code)

    def test_migration_revert_restores_0016_state(self):
        migration = importlib.import_module(
            "content.migrations.0018_channelpagecard_group_defaults"
        )
        self._seed()
        migration.apply_final_state(apps, None)
        migration.revert_final_state(apps, None)
        self.assertEqual(self._layouts("UK-Mini-HP-Toys-Baby-and-Kids"), {"grid2x2"})
        self.assertEqual(self._layouts("UK-Mini-HP-Health-and-Wellness"), {"row3_scroll"})
        self.assertEqual(self._layouts("UK-Mini-HP-Pets"), {"row3"})
        self.assertEqual(self._layouts("UK-Mini-HP-Gaming"), {"row3"})
        self.assertEqual(set(ChannelPageCard.objects.values_list("is_active", flat=True)), {True})


class ChannelCardPageBindingTests(ChannelPageCardTestBase):
    """ADR-0002（2026-11-26）：卡片绑定落地页 + 去重 + store 优先 + 频道级上限。"""

    def _make_page(self, *, kind="ACTIVITY", external_id="41xQpuBGBQ37QRh44nrYLBbUh4cR", enabled=True):
        from content.models import ActivityPage

        return ActivityPage.objects.create(
            kind=kind,
            external_id=external_id,
            title="Channel card page",
            source_url="https://www.joybuy.co.uk/campaign/active/" + external_id,
            enabled=enabled,
        )

    def test_bound_card_jumps_to_local_page_and_unbound_keeps_link_url(self):
        page = self._make_page()
        bound = self.make_card(sort_order=1)
        bound.activity_page = page
        bound.save()
        unbound = self.make_card(sort_order=2, link_url="/c/kitchen")

        payload = self.client.get(f"/api/v1/cms/channel-page-cards?channel={HOME_CODE}").json()
        self.assertEqual([item["link_url"] for item in payload["items"]], ["/active/" + page.external_id, "/c/kitchen"])

    def test_disabled_bound_page_falls_back_to_channel_page(self):
        page = self._make_page(enabled=False)
        card = self.make_card(sort_order=1)
        card.activity_page = page
        card.save()

        payload = self.client.get(f"/api/v1/cms/channel-page-cards?channel={HOME_CODE}").json()
        self.assertEqual(payload["items"][0]["link_url"], "/minihome/" + HOME_CODE)

    def test_duplicate_page_rows_are_deduped(self):
        page = self._make_page()
        first = self.make_card(sort_order=1)
        first.activity_page = page
        first.save()
        second = self.make_card(sort_order=2, link_url="https://m.joybuy.co.uk/campaign/active/" + page.external_id)
        second.activity_page = page
        second.save()

        payload = self.client.get(f"/api/v1/cms/channel-page-cards?channel={HOME_CODE}").json()
        self.assertEqual(payload["total"], 1)

    def test_store_page_cards_win_the_cap_over_activity_cards(self):
        store = self._make_page(kind="STORE", external_id="100004093")
        store_card = self.make_card(sort_order=3, link_url="https://www.joybuy.co.uk/store/100004093/products")
        store_card.activity_page = store
        store_card.save()
        # 两张活动卡：sort_order 更小的一张与 store 卡竞争 3 个名额之外的位置。
        self.make_card(sort_order=1, link_url="/c/a")
        self.make_card(sort_order=2, link_url="/c/b")
        self.make_card(sort_order=4, link_url="/c/d")

        payload = self.client.get(f"/api/v1/cms/channel-page-cards?channel={HOME_CODE}").json()
        # 上限 3：store 卡必须保留；其余按组序号 + sort_order 取前 2。
        self.assertEqual(payload["total"], 3)
        hrefs = [item["link_url"] for item in payload["items"]]
        self.assertIn("/store/100004093", hrefs)
        self.assertNotIn("/c/d", hrefs)
        # 展示顺序仍按 sort_order，不因 store 优先而重排。
        self.assertEqual(hrefs, ["/c/a", "/c/b", "/store/100004093"])

    def test_channel_setting_overrides_default_limit(self):
        from content.models import ChannelCardSetting

        for position in range(1, 6):
            self.make_card(sort_order=position, link_url=f"/c/{position}")
        ChannelCardSetting.objects.update_or_create(
            channel_code=HOME_CODE, defaults={"max_cards": 5}
        )
        payload = self.client.get(f"/api/v1/cms/channel-page-cards?channel={HOME_CODE}").json()
        self.assertEqual(payload["total"], 5)
        ChannelCardSetting.objects.update_or_create(
            channel_code=HOME_CODE, defaults={"max_cards": None}
        )
        self.make_card(sort_order=6, link_url="/c/6")
        payload = self.client.get(f"/api/v1/cms/channel-page-cards?channel={HOME_CODE}").json()
        self.assertEqual(payload["total"], 6)

    def test_admin_bind_and_unbind_activity_page(self):
        page = self._make_page()
        created = self.post(
            "/api/v1/admin/channel-page-cards",
            {
                "channel_code": HOME_CODE,
                "image_url": "/media/cms/bound.webp",
                "link_url": "https://www.joybuy.co.uk/campaign/active/" + page.external_id,
                "activity_page": str(page.public_id),
            },
        )
        self.assertEqual(created.status_code, 201, created.content)
        card = created.json()["card"]
        self.assertEqual(card["activity_page"]["external_id"], page.external_id)
        self.assertEqual(card["activity_page"]["local_path"], "/active/" + page.external_id)

        unbound = self.patch(
            f"/api/v1/admin/channel-page-cards/{card['id']}", {"activity_page": ""}
        )
        self.assertEqual(unbound.status_code, 200, unbound.content)
        self.assertIsNone(unbound.json()["card"]["activity_page"])

        invalid = self.patch(
            f"/api/v1/admin/channel-page-cards/{card['id']}",
            {"activity_page": "00000000-0000-0000-0000-000000000000"},
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json()["error"]["code"], "ACTIVITY_PAGE_INVALID")

    def test_activity_page_options_endpoint(self):
        page = self._make_page()
        listing = self.client.get("/api/v1/admin/activity-pages/options")
        self.assertEqual(listing.status_code, 200, listing.content)
        items = listing.json()["items"]
        match = next(item for item in items if item["id"] == str(page.public_id))
        self.assertEqual(match["kind"], "ACTIVITY")
        self.assertEqual(match["external_id"], page.external_id)
        self.assertTrue(match["enabled"])
