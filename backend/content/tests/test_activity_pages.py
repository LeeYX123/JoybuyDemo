"""活动页/店铺页（2026-11-25）针对性测试：模型服务 + 公开接口。"""

import json

from django.test import Client, TestCase
from django.utils import timezone

from catalog.models import LocalCategory, Spu, SpuSourceIdentity, SpuTranslation
from content.activity_services import (
    ActivityPageError,
    activity_page_payload,
    create_page,
    create_section,
    replace_section_products,
)
from content.models import ActivitySectionProduct


def _spu(public_title: str, *, slug: str) -> Spu:
    category = LocalCategory.objects.create(
        name="Home", slug=slug, path="/", depth=0, sort_order=0, name_en="Home"
    )
    spu = Spu.objects.create(
        local_category=category,
        status=Spu.Status.ACTIVE,
        retail_price="19.99",
    )
    SpuTranslation.objects.create(spu=spu, locale="en-GB", title=public_title)
    now = timezone.now()
    SpuSourceIdentity.objects.create(
        spu=spu,
        source_system="joybuy_uk",
        source_id=f"src-{spu.pk}",
        first_seen_at=now,
        last_seen_at=now,
    )
    return spu


class ActivityPageServiceTests(TestCase):
    def test_create_page_rejects_duplicate_external_id(self):
        create_page({"kind": "ACTIVITY", "external_id": "abc123", "title": "A"})
        with self.assertRaises(ActivityPageError) as ctx:
            create_page({"kind": "ACTIVITY", "external_id": "abc123", "title": "B"})
        self.assertEqual(ctx.exception.code, "PAGE_EXISTS")

    def test_sections_and_products_roundtrip(self):
        page = create_page({"kind": "ACTIVITY", "external_id": "abc123", "title": "A"})
        banner = create_section(
            page, {"kind": "BANNER", "image_url": "/images/activity/a/banner.webp"}
        )
        floor = create_section(
            page, {"kind": "PRODUCTS", "title": "Top deals", "columns": 5, "show_more": True}
        )
        self.assertEqual(banner.sort_order, 0)
        self.assertEqual(floor.sort_order, 1)

        first = _spu("Product one", slug="home-a")
        second = _spu("Product two", slug="home-b")
        count = replace_section_products(floor, [str(second.public_id), str(first.public_id)])
        self.assertEqual(count, 2)
        self.assertEqual(
            list(
                ActivitySectionProduct.objects.filter(section=floor)
                .order_by("sort_order")
                .values_list("spu__public_id", flat=True)
            ),
            [second.public_id, first.public_id],
        )

    def test_public_payload_keeps_order_and_price(self):
        page = create_page(
            {"kind": "STORE", "external_id": "100000744", "title": "Store", "store_name": "Purcotton"}
        )
        floor = create_section(page, {"kind": "PRODUCTS", "title": "All"})
        first = _spu("Product one", slug="store-a")
        second = _spu("Product two", slug="store-b")
        replace_section_products(floor, [str(first.public_id), str(second.public_id)])

        payload = activity_page_payload(page)
        self.assertEqual(payload["store_name"], "Purcotton")
        products = payload["sections"][0]["products"]
        self.assertEqual(
            [item["title"] for item in products], ["Product one", "Product two"]
        )
        # 与搜索/频道楼层同口径：Decimal 原样输出（4 位小数），购物端按 2 位展示。
        self.assertEqual(products[0]["price"], "19.9900")
        self.assertEqual(products[0]["href"], f"/p/{first.public_id}")

    def test_public_api_404_for_unknown_page(self):
        response = Client().get("/api/v1/activity-pages/active/nope")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(json.loads(response.content)["error"]["code"], "PAGE_NOT_FOUND")


class ActivityPageMarketTests(TestCase):
    def test_products_hidden_when_spu_inactive(self):
        page = create_page({"kind": "ACTIVITY", "external_id": "xyz", "title": "T"})
        floor = create_section(page, {"kind": "PRODUCTS", "title": "T"})
        spu = _spu("Live product", slug="mkt-a")
        replace_section_products(floor, [str(spu.public_id)])
        spu.status = Spu.Status.INACTIVE
        spu.save(update_fields=["status", "updated_at"])
        payload = activity_page_payload(page)
        self.assertEqual(payload["sections"][0]["products"], [])
