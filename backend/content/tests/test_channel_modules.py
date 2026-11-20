"""频道页商品楼层（批次 H）测试：公开接口/服务/管理端更新。

红线：
1. 楼层只返回 enabled，按 sort_order；商品按楼层内顺序、与搜索 item 同构；
2. 标题按请求语言取 title_zh/title_en；【更多】落 /c/<一级 slug>；
3. 管理端更新可改标题/顺序/开关并整体替换商品清单，非法输入 400。
"""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import (
    CategoryMapping,
    LocalCategory,
    ProductSearchDocument,
    SourceCatalog,
    SourceCategory,
    Spu,
    SpuTranslation,
)
from content.channel_module_services import (
    ChannelModuleError,
    public_modules,
    update_module,
)
from content.models import ChannelModule, ChannelModuleProduct
from offers.models import Market

BEAUTY_CODE = "UK-Mini-HP-Beauty"


def _channel_source(source_id: str) -> SourceCategory:
    catalog, _ = SourceCatalog.objects.get_or_create(
        source_system="joybuy_uk", defaults={"display_name": "Joybuy UK"}
    )
    now = timezone.now()
    return SourceCategory.objects.create(
        catalog=catalog, source_id=source_id, first_seen_at=now, last_seen_at=now
    )


class ChannelModuleTests(TestCase):
    def setUp(self):
        self.root = LocalCategory.objects.create(
            name="Beauty",
            name_en="Beauty",
            name_zh="美妆",
            slug="beauty-cm",
            path="beauty-cm",
            depth=0,
        )
        CategoryMapping.objects.create(
            local_category=self.root,
            source_category=_channel_source(f"minihome:{BEAUTY_CODE}"),
            is_primary=True,
        )
        self.market = Market.objects.get(code="GB")
        self.spus = []
        for index, title in enumerate(["Fino Shampoo", "La Mer Lip"]):
            spu = Spu.objects.create(status=Spu.Status.ACTIVE, local_category=self.root)
            SpuTranslation.objects.create(spu=spu, locale="en-GB", title=title)
            ProductSearchDocument.objects.create(
                spu=spu,
                market=self.market,
                locale_code="en-GB",
                title=title,
                local_category=self.root,
                min_price=Decimal("9.99"),
                max_price=Decimal("9.99"),
                currency_code="USD",
                is_searchable=True,
            )
            self.spus.append(spu)
        self.module = ChannelModule.objects.create(
            channel_code=BEAUTY_CODE,
            title_en="Best sellers",
            title_zh="爆品热销",
            sort_order=0,
        )
        ChannelModuleProduct.objects.create(module=self.module, spu=self.spus[1], sort_order=0)
        ChannelModuleProduct.objects.create(module=self.module, spu=self.spus[0], sort_order=1)

    def test_public_modules_orders_products_and_localizes_title(self):
        en = public_modules(
            BEAUTY_CODE, market=self.market, locale_code="en-GB", language_code="en"
        )
        self.assertEqual(en["category_slug"], self.root.slug)
        self.assertEqual(en["modules"][0]["title"], "Best sellers")
        self.assertEqual(en["modules"][0]["href"], f"/c/{self.root.slug}")
        self.assertEqual(
            [item["title"] for item in en["modules"][0]["products"]],
            ["La Mer Lip", "Fino Shampoo"],
        )
        self.assertEqual(
            en["modules"][0]["products"][0]["spu_public_id"], str(self.spus[1].public_id)
        )
        zh = public_modules(
            BEAUTY_CODE, market=self.market, locale_code="en-GB", language_code="zh"
        )
        self.assertEqual(zh["modules"][0]["title"], "爆品热销")

    def test_product_data_does_not_depend_on_request_locale(self):
        """FAIL ①（2026-11-19）：zh-CN 请求也必须拿到默认 locale 的文档数据。

        库里只有 en-GB 搜索文档；按请求 locale 查会退到无价/无图的兜底。
        """

        zh = public_modules(
            BEAUTY_CODE, market=self.market, locale_code="zh-CN", language_code="zh"
        )
        products = zh["modules"][0]["products"]
        self.assertEqual([item["title"] for item in products], ["La Mer Lip", "Fino Shampoo"])
        # 文档里的价格（9.99）出现，说明用的是 en-GB 文档而不是无价 fallback。
        self.assertEqual(products[0]["price_min"], "9.9900")
        self.assertEqual(products[0]["currency"], "USD")

    def test_disabled_module_is_hidden(self):
        self.module.enabled = False
        self.module.save(update_fields=["enabled"])
        data = public_modules(
            BEAUTY_CODE, market=self.market, locale_code="en-GB", language_code="en"
        )
        self.assertEqual(data["modules"], [])

    def test_api_endpoint_returns_modules(self):
        response = self.client.get(
            reverse("storefront-channel-modules", kwargs={"code": BEAUTY_CODE})
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["channel_code"], BEAUTY_CODE)
        self.assertEqual(payload["modules"][0]["title"], "Best sellers")
        self.assertEqual(len(payload["modules"][0]["products"]), 2)

    def test_update_module_replaces_titles_and_products(self):
        updated = update_module(
            self.module.public_id,
            {
                "title_en": "New in & Trending",
                "title_zh": "新品上线",
                "sort_order": 3,
                "enabled": True,
                "product_public_ids": [str(self.spus[0].public_id)],
            },
        )
        self.assertEqual(updated.title_en, "New in & Trending")
        self.assertEqual(updated.title_zh, "新品上线")
        self.assertEqual(updated.sort_order, 3)
        self.assertEqual(list(updated.items.values_list("spu_id", flat=True)), [self.spus[0].pk])

    def test_update_module_rejects_unknown_product(self):
        with self.assertRaises(ChannelModuleError):
            update_module(
                self.module.public_id,
                {
                    "title_en": "X",
                    "product_public_ids": ["00000000-0000-0000-0000-000000000000"],
                },
            )
