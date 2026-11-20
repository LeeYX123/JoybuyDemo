"""首页活动卡片（搜索框下方 10 宫格）的接口与同步测试。

三条不能破的线：
1. storefront_home 输出的 campaign_grid 必须来自独立表（enabled、按序），
   覆盖快照里写死的内容；独立表为空时回退快照；
2. 顺序可调：上移/下移与相邻交换，不能越界；
3. 上限 10 张、href 白名单（/ 或 http(s)），非法输入 400 而不是 500。
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
from catalog.models import LocalCategory
from content.campaign_services import campaign_payload, import_from_published_snapshot
from content.models import CmsModule, CmsPage, HomeCampaignCard


class CampaignCardTestBase(TestCase):
    def setUp(self):
        role, _ = PlatformRole.objects.update_or_create(
            code="campaign-role", defaults={"name": "Campaign", "is_system": False}
        )
        role.permissions.set(
            [
                PlatformPermission.objects.get_or_create(code=code, defaults={"name": code})[0]
                for code in ("cms.campaign.manage", "cms.campaign.view")
            ]
        )
        self.staff = StaffAccount.objects.create(
            email="campaign@joybuy.test", display_name="运营", status="ACTIVE"
        )
        StaffRoleAssignment.objects.create(staff=self.staff, role=role)
        token, _session = create_staff_session(
            staff=self.staff, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token

    def post(self, path, payload=None):
        return self.client.post(
            path, data=json.dumps(payload or {}), content_type="application/json"
        )

    def patch(self, path, payload=None):
        return self.client.patch(
            path, data=json.dumps(payload or {}), content_type="application/json"
        )

    def make_card(
        self, title="测试卡片", *, sort_order=1, enabled=True, section="campaign", **kwargs
    ):
        return HomeCampaignCard.objects.create(
            section=section,
            title=title,
            subtitle=kwargs.get("subtitle", ""),
            image_url=kwargs.get("image_url", "/media/cms/original/aa/bb/x.webp"),
            href=kwargs.get("href", "/c/electronics"),
            sort_order=sort_order,
            enabled=enabled,
        )


class CampaignCardCrudTests(CampaignCardTestBase):
    def test_create_and_list(self):
        response = self.post(
            "/api/v1/admin/campaign-cards",
            {
                "title": "新卡片",
                "subtitle": "副标题",
                "href": "/c/home",
                "image_url": "/media/cms/a.webp",
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        card = HomeCampaignCard.objects.get(title="新卡片")
        # 新卡排到末尾，不打乱现有顺序
        self.assertEqual(
            card.sort_order, HomeCampaignCard.objects.order_by("-sort_order").first().sort_order
        )

        listing = self.client.get("/api/v1/admin/campaign-cards")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["total"], 1)

    def test_create_requires_title(self):
        response = self.post("/api/v1/admin/campaign-cards", {"title": "  "})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "FIELD_REQUIRED")

    def test_create_rejects_bad_href(self):
        response = self.post(
            "/api/v1/admin/campaign-cards", {"title": "x", "href": "javascript:alert(1)"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "HREF_INVALID")

    def test_full_links_stored_verbatim_per_13_8(self):
        """13.8：http(s)://、//、www. 开头的全链接原样保存，不改写。"""
        for href in (
            "https://www.example.com/x",
            "//cdn.example.com/x",
            "www.example.com/x",
        ):
            response = self.post(
                "/api/v1/admin/campaign-cards", {"title": "x", "href": href}
            )
            self.assertEqual(response.status_code, 201, response.content)
            self.assertEqual(response.json()["card"]["href"], href)

    def test_card_cap_is_ten(self):
        for index in range(10):
            self.make_card(f"卡{index}", sort_order=index + 1)
        response = self.post("/api/v1/admin/campaign-cards", {"title": "第11张"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "TOO_MANY_CARDS")

    def test_update_and_delete(self):
        card = self.make_card()
        updated = self.patch(
            f"/api/v1/admin/campaign-cards/{card.public_id}",
            {"title": "改过", "enabled": False},
        )
        self.assertEqual(updated.status_code, 200)
        card.refresh_from_db()
        self.assertEqual(card.title, "改过")
        self.assertFalse(card.enabled)

        deleted = self.client.delete(f"/api/v1/admin/campaign-cards/{card.public_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(HomeCampaignCard.objects.count(), 0)


class CampaignCardOrderingTests(CampaignCardTestBase):
    def test_move_down_swaps_neighbours(self):
        first = self.make_card("A", sort_order=1)
        second = self.make_card("B", sort_order=2)

        response = self.post(
            f"/api/v1/admin/campaign-cards/{first.public_id}/actions",
            {"action": "move", "direction": "down"},
        )
        self.assertEqual(response.status_code, 200, response.content)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.sort_order, second.sort_order), (2, 1))

    def test_move_up_at_top_is_rejected(self):
        card = self.make_card("A", sort_order=1)
        response = self.post(
            f"/api/v1/admin/campaign-cards/{card.public_id}/actions",
            {"action": "move", "direction": "up"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "MOVE_AT_EDGE")

    def test_move_compacts_duplicate_sort_orders(self):
        """历史数据 sort_order 可能重复（如全部 0），移动前先压实再换位。"""
        first = self.make_card("A", sort_order=0)
        second = self.make_card("B", sort_order=0)
        response = self.post(
            f"/api/v1/admin/campaign-cards/{first.public_id}/actions",
            {"action": "move", "direction": "down"},
        )
        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertLess(second.sort_order, first.sort_order)


class StorefrontSyncTests(CampaignCardTestBase):
    def _publish_home_with_campaign_snapshot(self):
        page = CmsPage.objects.create(
            page_key="home",
            title="home",
            version=1,
            status=CmsPage.Status.PUBLISHED,
            published_at=timezone.now(),
        )
        CmsModule.objects.create(
            page=page,
            position=1,
            module_type="campaign_grid",
            payload={"items": [{"title": "快照旧卡片", "subtitle": "snapshot"}]},
        )
        return page

    def test_storefront_uses_independent_table_over_snapshot(self):
        self._publish_home_with_campaign_snapshot()
        self.make_card("独立表卡片", sort_order=1, href="/c/electronics")

        response = self.client.get("/api/v1/storefront/home")
        self.assertEqual(response.status_code, 200)
        modules = response.json()["modules"]
        grid = next(m for m in modules if m["type"] == "campaign_grid")
        titles = [item["title"] for item in grid["payload"]["items"]]
        self.assertEqual(titles, ["独立表卡片"])
        # 快照里的旧卡片不能再出现
        self.assertNotIn("快照旧卡片", titles)

    def test_disabled_cards_are_excluded(self):
        self._publish_home_with_campaign_snapshot()
        self.make_card("启用", sort_order=1, enabled=True)
        self.make_card("停用", sort_order=2, enabled=False)
        response = self.client.get("/api/v1/storefront/home")
        grid = next(m for m in response.json()["modules"] if m["type"] == "campaign_grid")
        titles = [item["title"] for item in grid["payload"]["items"]]
        self.assertEqual(titles, ["启用"])

    def test_empty_table_falls_back_to_snapshot(self):
        page = self._publish_home_with_campaign_snapshot()
        # 独立表为空：回退快照，页面不能白屏
        response = self.client.get("/api/v1/storefront/home")
        self.assertEqual(response.status_code, 200)
        grid = next(m for m in response.json()["modules"] if m["type"] == "campaign_grid")
        self.assertEqual(grid["payload"]["items"][0]["title"], "快照旧卡片")
        self.assertIsNotNone(page)

    def test_snapshot_import_backfills_ten_cards(self):
        # 单独建页（version 更高），避免 helper 里那个 1 卡快照干扰
        # 「取最新版本页面」的导入口径。
        page = CmsPage.objects.create(
            page_key="home",
            title="home",
            version=3,
            status=CmsPage.Status.PUBLISHED,
            published_at=timezone.now(),
        )
        CmsModule.objects.create(
            page=page,
            position=1,
            module_type="campaign_grid",
            payload={
                "items": [
                    {"title": f"卡{i}", "subtitle": "s", "image_path": "/media/cms/a.webp"}
                    for i in range(1, 11)
                ]
            },
        )
        created = import_from_published_snapshot()
        self.assertEqual(created, 10)
        self.assertEqual(HomeCampaignCard.objects.count(), 10)
        self.assertEqual(HomeCampaignCard.objects.order_by("sort_order").first().title, "卡1")
        # 幂等：再导一次不重复
        self.assertEqual(import_from_published_snapshot(), 0)
        self.assertIsNotNone(page)


class DiscoverySectionTests(CampaignCardTestBase):
    def test_list_filters_by_section(self):
        self.make_card("活动卡", sort_order=1)
        self.make_card("发现卡", sort_order=1, section="discovery")
        campaign = self.client.get("/api/v1/admin/campaign-cards?section=campaign")
        discovery = self.client.get("/api/v1/admin/campaign-cards?section=discovery")
        self.assertEqual([i["title"] for i in campaign.json()["items"]], ["活动卡"])
        self.assertEqual([i["title"] for i in discovery.json()["items"]], ["发现卡"])
        self.assertEqual(campaign.json()["max_cards"], 10)
        self.assertEqual(discovery.json()["max_cards"], 12)

    def test_create_in_discovery_section(self):
        response = self.post(
            "/api/v1/admin/campaign-cards",
            {
                "section": "discovery",
                "title": "新品类",
                "title_zh": "中文",
                "href": "/s?category=toys",
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        card = HomeCampaignCard.objects.get(title="新品类")
        self.assertEqual(card.section, "discovery")
        # discovery 不使用副标题字段
        self.assertEqual(card.subtitle, "")

    def test_section_must_be_valid(self):
        response = self.post("/api/v1/admin/campaign-cards", {"section": "hack", "title": "x"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "SECTION_INVALID")
        listing = self.client.get("/api/v1/admin/campaign-cards?section=hack")
        self.assertEqual(listing.status_code, 400)

    def test_move_stays_within_section(self):
        first = self.make_card("发现A", sort_order=1, section="discovery")
        second = self.make_card("发现B", sort_order=2, section="discovery")
        # campaign 区的另一张卡不应参与 discovery 排序
        self.make_card("活动A", sort_order=1, section="campaign")

        response = self.post(
            f"/api/v1/admin/campaign-cards/{first.public_id}/actions",
            {"action": "move", "direction": "down"},
        )
        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertLess(second.sort_order, first.sort_order)
        # campaign 区的卡片不受影响
        campaign_card = HomeCampaignCard.objects.get(title="活动A")
        self.assertEqual(campaign_card.sort_order, 1)

    def test_discovery_filters_hidden_roots_and_uses_category_names(self):
        """批次 H 验收修复：tiles 与顶部导航同口径（改名 + 不显示隐藏品类）。"""

        LocalCategory.objects.create(
            name="Beauty",
            name_en="Beauty",
            name_zh="美妆",
            slug="beauty-personal-care",
            path="/bh/",
            depth=0,
        )
        self.make_card(
            "旧美妆", sort_order=1, section="discovery", href="/s?category=beauty-personal-care"
        )
        self.make_card(
            "服装", sort_order=2, section="discovery", href="/s?category=clothing-accessories"
        )

        payload = campaign_payload("discovery")
        self.assertEqual(len(payload["items"]), 1)
        item = payload["items"][0]
        self.assertEqual(item["label"], "Beauty")
        self.assertEqual(item["label_zh"], "美妆")
        self.assertEqual(item["href"], "/s?category=beauty-personal-care")

    def test_discovery_hides_batch_o_roots_and_caps_six(self):
        """14.1：宠物/母婴童玩/游戏不展示，模块固定 6 张。"""

        slugs = [
            "home-living",
            "electronics",
            "beauty-personal-care",
            "small-home-appliances",
            "health-wellness",
            "outdoor-sports",
            "pet-supplies",
            "baby-toddler",
            "games-accessories",
        ]
        for order, slug in enumerate(slugs, start=1):
            self.make_card(slug, sort_order=order, section="discovery", href=f"/s?category={slug}")
        payload = campaign_payload("discovery")
        hrefs = [item["href"] for item in payload["items"]]
        self.assertEqual(len(hrefs), 6)
        for hidden in ("pet-supplies", "baby-toddler", "games-accessories"):
            self.assertNotIn(f"/s?category={hidden}", hrefs)

    def test_storefront_keeps_brand_logos_when_injecting_discovery(self):
        """14.4：品类发现注入不能连带删除心选品牌（同为 link_grid）。"""

        page = CmsPage.objects.create(
            page_key="home",
            title="home",
            version=1,
            status=CmsPage.Status.PUBLISHED,
            published_at=timezone.now(),
        )
        CmsModule.objects.create(
            page=page,
            position=1,
            module_type="link_grid",
            payload={
                "variant": "tiles",
                "title": "Category discovery",
                "items": [{"label": "快照旧品类"}],
            },
        )
        CmsModule.objects.create(
            page=page,
            position=2,
            module_type="link_grid",
            payload={
                "variant": "brand_logos",
                "title": "Brands we love",
                "items": [{"label": "Midea", "icon_path": "/media/brands/midea.webp"}],
            },
        )
        self.make_card("独立品类", sort_order=1, section="discovery", href="/s?category=toys")

        modules = self.client.get("/api/v1/storefront/home").json()["modules"]
        brands = [
            m
            for m in modules
            if m["type"] == "link_grid" and m["payload"].get("variant") == "brand_logos"
        ]
        self.assertEqual(len(brands), 1)
        self.assertEqual(brands[0]["payload"]["items"][0]["label"], "Midea")
        tiles = [
            m
            for m in modules
            if m["type"] == "link_grid" and m["payload"].get("variant") == "tiles"
        ]
        self.assertEqual([i["label"] for i in tiles[0]["payload"]["items"]], ["独立品类"])

    def test_storefront_injects_discovery_tiles(self):
        page = CmsPage.objects.create(
            page_key="home",
            title="home",
            version=1,
            status=CmsPage.Status.PUBLISHED,
            published_at=timezone.now(),
        )
        CmsModule.objects.create(
            page=page,
            position=1,
            module_type="link_grid",
            payload={
                "variant": "tiles",
                "title": "Category discovery",
                "items": [{"label": "快照旧品类", "icon_path": "/media/cms/x.webp"}],
            },
        )
        self.make_card("独立品类", sort_order=1, section="discovery", href="/s?category=toys")

        response = self.client.get("/api/v1/storefront/home")
        self.assertEqual(response.status_code, 200)
        grid = next(
            m
            for m in response.json()["modules"]
            if m["type"] == "link_grid" and m["payload"].get("variant") == "tiles"
        )
        self.assertEqual(grid["payload"]["title_zh"], "品类发现")
        items = grid["payload"]["items"]
        self.assertEqual(len(items), 1)
        # discovery 的 item 用 label/icon_path 字段名
        self.assertEqual(items[0]["label"], "独立品类")
        self.assertEqual(items[0]["href"], "/s?category=toys")
        self.assertNotIn("快照旧品类", [i["label"] for i in items])
        # campaign 无数据时不注入 campaign_grid（本页快照也没有）
        self.assertFalse(any(m["type"] == "campaign_grid" for m in response.json()["modules"]))


class WeeklySectionTests(CampaignCardTestBase):
    def test_weekly_section_admin_cap_is_six(self):
        listing = self.client.get("/api/v1/admin/campaign-cards?section=weekly")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["max_cards"], 6)
        for index in range(6):
            self.make_card(f"周{index}", sort_order=index + 1, section="weekly")
        response = self.post(
            "/api/v1/admin/campaign-cards", {"section": "weekly", "title": "第7张"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "TOO_MANY_CARDS")

    def test_weekly_cards_payload_and_storefront_injection(self):
        """14.2：每周甄选 6 张 CMS 卡片，注入 weekly_picks 模块。"""

        page = CmsPage.objects.create(
            page_key="home",
            title="home",
            version=1,
            status=CmsPage.Status.PUBLISHED,
            published_at=timezone.now(),
        )
        CmsModule.objects.create(
            page=page,
            position=1,
            module_type="link_grid",
            payload={
                "variant": "brand_logos",
                "title": "Brands we love",
                "items": [{"label": "Midea"}],
            },
        )
        for index in range(6):
            self.make_card(
                f"活动{index}",
                sort_order=index + 1,
                section="weekly",
                href=f"/marketing?activityId=2005002{index}",
                image_url=f"/images/weekly-picks/{index}.webp",
            )

        payload = campaign_payload("weekly")
        self.assertEqual(payload["title"], "Weekly picks")
        self.assertEqual(payload["title_zh"], "每周甄选")
        self.assertEqual(len(payload["items"]), 6)

        modules = self.client.get("/api/v1/storefront/home").json()["modules"]
        weekly = next(m for m in modules if m["type"] == "weekly_picks")
        self.assertEqual(len(weekly["payload"]["items"]), 6)
        self.assertEqual(weekly["payload"]["items"][0]["href"], "/marketing?activityId=20050020")
        # 真站顺序：心选品牌（快照）→ 每周甄选（注入追加在后）。
        types = [m["type"] for m in modules]
        self.assertLess(types.index("link_grid"), types.index("weekly_picks"))
