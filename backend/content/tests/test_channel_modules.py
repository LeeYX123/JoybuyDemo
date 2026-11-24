"""频道页商品楼层（批次 H）测试：公开接口/服务/管理端更新。

红线：
1. 楼层只返回 enabled，按 sort_order；商品按楼层内顺序、与搜索 item 同构；
2. 标题按请求语言取 title_zh/title_en；【更多】落 /c/<一级 slug>；
3. 管理端更新可改标题/顺序/开关并整体替换商品清单，非法输入 400；
4. 2026-11-24 起位次可按 SKU 展开：同 SPU 不同 SKU 各一张卡，接口带
   ``sku_public_id`` / ``specification``，价格取该 SKU 的报价；老数据
   ``sku=NULL`` 渲染与旧版一致（两个新字段为 null）。
5. 2026-11-24 起 ``retail_price`` 带归属判据：按 SKU 展开的卡若「零售价低于
   本卡报价」或「零售价恰好是兄弟 SKU 的报价」，输出 null（前端回退
   ``price_min``）；``sku=NULL`` 老位次仍原样输出。
"""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import (
    CategoryMapping,
    LocalCategory,
    ProductSearchDocument,
    Sku,
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
from merchants.services import get_import_fallback_merchant
from offers.models import Currency, Market, Offer

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
        retail_prices = [Decimal("19.9900"), None]
        for index, title in enumerate(["Fino Shampoo", "La Mer Lip"]):
            spu = Spu.objects.create(
                status=Spu.Status.ACTIVE,
                local_category=self.root,
                retail_price=retail_prices[index],
            )
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

    def make_sku(
        self,
        spu,
        size: str,
        *,
        price: str,
        offer_status=Offer.Status.ACTIVE,
        sku_status=Sku.Status.ACTIVE,
    ) -> Sku:
        sku = Sku.objects.create(
            spu=spu,
            specification={"Size": size},
            specification_signature=f"sig-{spu.pk}-{size}",
            status=sku_status,
        )
        if offer_status is not None:
            Offer.objects.create(
                merchant=get_import_fallback_merchant(),
                sku=sku,
                market=self.market,
                currency=Currency.objects.get(code="GBP"),
                current_price=Decimal(price),
                status=offer_status,
            )
        return sku

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

    def test_products_carry_retail_price(self):
        """频道楼层商品带后台零售价（只新增字段，price_min/price_max 语义不变）。"""

        data = public_modules(
            BEAUTY_CODE, market=self.market, locale_code="en-GB", language_code="en"
        )
        products = {item["spu_public_id"]: item for item in data["modules"][0]["products"]}
        priced = products[str(self.spus[0].public_id)]
        self.assertEqual(priced["retail_price"], "19.9900")  # 4 位小数，与 price_min 同口径
        self.assertEqual(priced["price_min"], "9.9900")
        self.assertEqual(priced["price_max"], "9.9900")
        self.assertIsNone(products[str(self.spus[1].public_id)]["retail_price"])

    def test_fallback_product_carries_retail_price(self):
        """没有搜索文档的兜底序列化同样带 retail_price。"""

        spu = Spu.objects.create(
            status=Spu.Status.ACTIVE,
            local_category=self.root,
            retail_price=Decimal("5.5000"),
        )
        SpuTranslation.objects.create(spu=spu, locale="en-GB", title="Fallback item")
        ChannelModuleProduct.objects.create(module=self.module, spu=spu, sort_order=2)

        data = public_modules(
            BEAUTY_CODE, market=self.market, locale_code="en-GB", language_code="en"
        )
        product = data["modules"][0]["products"][2]
        self.assertEqual(product["spu_public_id"], str(spu.public_id))
        self.assertEqual(product["retail_price"], "5.5000")
        self.assertIsNone(product["price_min"])

    def test_same_spu_different_skus_each_get_a_card(self):
        """同 SPU 的不同尺码各占一张卡（真站母婴 17 张卡只有 5 个 SPU）。"""

        spu = self.spus[0]  # Fino Shampoo，文档价 9.99，零售价 19.99
        small = self.make_sku(spu, "100ml", price="9.99")
        large = self.make_sku(spu, "500ml", price="12.50")
        ChannelModuleProduct.objects.create(module=self.module, spu=spu, sku=small, sort_order=3)
        ChannelModuleProduct.objects.create(module=self.module, spu=spu, sku=large, sort_order=4)

        data = public_modules(
            BEAUTY_CODE, market=self.market, locale_code="en-GB", language_code="en"
        )
        products = data["modules"][0]["products"][2:]
        self.assertEqual(
            [item["sku_public_id"] for item in products],
            [str(small.public_id), str(large.public_id)],
        )
        # 价格取该 SKU 自己的报价（不是文档里的 SPU 最低价）。
        self.assertEqual([item["price_min"] for item in products], ["9.9900", "12.5000"])
        self.assertEqual([item["price_max"] for item in products], ["9.9900", "12.5000"])
        self.assertEqual(
            [item["specification"] for item in products],
            [{"Size": "100ml"}, {"Size": "500ml"}],
        )
        # 标题/品牌/零售价仍取 SPU。
        self.assertEqual({item["title"] for item in products}, {"Fino Shampoo"})
        self.assertEqual({item["retail_price"] for item in products}, {"19.9900"})
        self.assertEqual({item["spu_public_id"] for item in products}, {str(spu.public_id)})

    def test_api_items_expose_sku_public_id_and_sku_price(self):
        """接口契约：item 带 sku_public_id/specification，价格来自该 SKU。"""

        spu = self.spus[0]
        cheap = self.make_sku(spu, "cheap", price="10.0000")
        dear = self.make_sku(spu, "dear", price="20.0000")
        ChannelModuleProduct.objects.create(module=self.module, spu=spu, sku=cheap, sort_order=3)
        ChannelModuleProduct.objects.create(module=self.module, spu=spu, sku=dear, sort_order=4)

        response = self.client.get(
            reverse("storefront-channel-modules", kwargs={"code": BEAUTY_CODE})
        )

        self.assertEqual(response.status_code, 200)
        products = response.json()["modules"][0]["products"][2:]
        self.assertEqual(
            [(item["sku_public_id"], item["price_min"]) for item in products],
            [(str(cheap.public_id), "10.0000"), (str(dear.public_id), "20.0000")],
        )
        self.assertEqual(products[0]["specification"], {"Size": "cheap"})
        self.assertEqual(products[0]["spu_public_id"], str(spu.public_id))
        self.assertEqual(products[0]["retail_price"], "19.9900")

    def test_spu_level_rows_keep_old_shape_with_null_sku_fields(self):
        """回归：老数据 ``sku=NULL`` 仍按 SPU 渲染，两个新字段为 null。"""

        data = public_modules(
            BEAUTY_CODE, market=self.market, locale_code="en-GB", language_code="en"
        )
        products = data["modules"][0]["products"]
        self.assertEqual([item["sku_public_id"] for item in products], [None, None])
        self.assertEqual([item["specification"] for item in products], [None, None])
        self.assertEqual([item["price_min"] for item in products], ["9.9900", "9.9900"])

    def test_sku_without_active_offer_keeps_document_price(self):
        """SKU 没有 ACTIVE 报价时保留文档价格，不把卡片打成空价。"""

        spu = self.spus[0]
        sku = self.make_sku(spu, "no-offer", price="9.99", offer_status=None)
        ChannelModuleProduct.objects.create(module=self.module, spu=spu, sku=sku, sort_order=3)

        data = public_modules(
            BEAUTY_CODE, market=self.market, locale_code="en-GB", language_code="en"
        )
        product = data["modules"][0]["products"][2]
        self.assertEqual(product["sku_public_id"], str(sku.public_id))
        self.assertEqual(product["price_min"], "9.9900")
        self.assertEqual(product["specification"], {"Size": "no-offer"})

    def test_update_module_without_product_list_keeps_sku_rows(self):
        """管理端只改标题（不带清单）时不能被同 SPU 多行顶成 400。"""

        spu = self.spus[0]
        small = self.make_sku(spu, "100ml", price="9.99")
        large = self.make_sku(spu, "500ml", price="12.50")
        ChannelModuleProduct.objects.create(module=self.module, spu=spu, sku=small, sort_order=3)
        ChannelModuleProduct.objects.create(module=self.module, spu=spu, sku=large, sort_order=4)

        updated = update_module(self.module.public_id, {"title_en": "Best sellers"})

        self.assertEqual(updated.title_en, "Best sellers")
        pairs = list(updated.items.order_by("sort_order").values_list("spu_id", "sku_id"))
        self.assertEqual(
            pairs,
            [
                (self.spus[1].pk, None),
                # 该 SPU 的 SPU 级旧行被 SKU 明细取代（否则同一商品两张卡）。
                (spu.pk, small.pk),
                (spu.pk, large.pk),
            ],
        )

    def test_update_module_reorders_spus_and_keeps_their_sku_rows(self):
        spu = self.spus[0]
        small = self.make_sku(spu, "s", price="9.99")
        large = self.make_sku(spu, "l", price="12.50")
        ChannelModuleProduct.objects.create(module=self.module, spu=spu, sku=small, sort_order=3)
        ChannelModuleProduct.objects.create(module=self.module, spu=spu, sku=large, sort_order=4)

        updated = update_module(
            self.module.public_id,
            {
                "title_en": "Best sellers",
                "product_public_ids": [
                    str(self.spus[0].public_id),
                    str(self.spus[1].public_id),
                ],
            },
        )

        self.assertEqual(
            list(updated.items.order_by("sort_order").values_list("spu_id", "sku_id")),
            [(spu.pk, small.pk), (spu.pk, large.pk), (self.spus[1].pk, None)],
        )

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
        # 回归：楼层载荷的 retail_price 取值不变（与 price_min 同口径，null 仍是 null）。
        products = {item["spu_public_id"]: item for item in payload["modules"][0]["products"]}
        self.assertEqual(products[str(self.spus[0].public_id)]["retail_price"], "19.9900")
        self.assertIsNone(products[str(self.spus[1].public_id)]["retail_price"])

    def test_retail_price_is_null_when_retail_below_card_price(self):
        """零售价低于本卡报价 → 零售价属于更便宜的变体，输出 null。

        真实案例：Bc Babycare 卡是 30 packs、SKU 报价 25.90，而零售价 3.79 来自
        「4 packs」变体。
        """

        spu = self.spus[0]
        spu.retail_price = Decimal("3.7900")
        spu.save(update_fields=["retail_price"])
        card = self.make_sku(spu, "30 packs", price="25.9000")
        ChannelModuleProduct.objects.create(module=self.module, spu=spu, sku=card, sort_order=3)

        data = public_modules(
            BEAUTY_CODE, market=self.market, locale_code="en-GB", language_code="en"
        )
        product = data["modules"][0]["products"][2]
        self.assertEqual(product["sku_public_id"], str(card.public_id))
        self.assertEqual(product["price_min"], "25.9000")
        self.assertIsNone(product["retail_price"])

    def test_retail_price_is_null_when_it_matches_a_sibling_sku_price(self):
        """零售价恰好等于兄弟 SKU 的报价、且本卡报价不同 → null；兄弟价那张卡保留。

        真实案例：啤酒零售价 42.99 来自 24 听装，1 听卡报价 2.09 不能显示 42.99。
        """

        spu = self.spus[0]
        spu.retail_price = Decimal("42.9900")
        spu.save(update_fields=["retail_price"])
        single = self.make_sku(spu, "1 can", price="2.0900")
        pack24 = self.make_sku(spu, "24 cans", price="42.9900")
        ChannelModuleProduct.objects.create(module=self.module, spu=spu, sku=single, sort_order=3)
        ChannelModuleProduct.objects.create(module=self.module, spu=spu, sku=pack24, sort_order=4)

        products = public_modules(
            BEAUTY_CODE, market=self.market, locale_code="en-GB", language_code="en"
        )["modules"][0]["products"][2:]
        self.assertEqual(
            [(item["specification"], item["price_min"]) for item in products],
            [({"Size": "1 can"}, "2.0900"), ({"Size": "24 cans"}, "42.9900")],
        )
        self.assertIsNone(products[0]["retail_price"])
        # 本卡报价 == 零售价（24 听装自己就是零售价的来源）→ 照常输出。
        self.assertEqual(products[1]["retail_price"], "42.9900")

    def test_retail_price_kept_when_it_is_a_genuine_original_price(self):
        """原价 > 折后价且无兄弟 SKU 匹配（真实折扣场景）→ 保留零售价。"""

        spu = self.spus[0]
        spu.retail_price = Decimal("21.9900")
        spu.save(update_fields=["retail_price"])
        card = self.make_sku(spu, "each", price="3.9700")
        ChannelModuleProduct.objects.create(module=self.module, spu=spu, sku=card, sort_order=3)

        product = public_modules(
            BEAUTY_CODE, market=self.market, locale_code="en-GB", language_code="en"
        )["modules"][0]["products"][2]
        self.assertEqual(product["price_min"], "3.9700")
        self.assertEqual(product["retail_price"], "21.9900")

    def test_retail_price_on_spu_level_row_is_unchanged(self):
        """老位次（``sku=NULL``）不做归属判据：即使 SPU 下有贵 SKU，仍原样输出零售价。"""

        spu = self.spus[0]
        spu.retail_price = Decimal("3.7900")
        spu.save(update_fields=["retail_price"])
        self.make_sku(spu, "30 packs", price="25.9000")  # 不进楼层，只存在于 SPU 下

        products = public_modules(
            BEAUTY_CODE, market=self.market, locale_code="en-GB", language_code="en"
        )["modules"][0]["products"]
        row = {item["spu_public_id"]: item for item in products}[str(spu.public_id)]
        self.assertIsNone(row["sku_public_id"])
        self.assertEqual(row["price_min"], "9.9900")  # 仍是文档价（SPU 口径）
        self.assertEqual(row["retail_price"], "3.7900")

    def test_query_count_does_not_grow_with_item_count(self):
        """20 个 item / 5 个 SPU 的楼层 SQL 次数与 1 个 item 相同（无 N+1）。"""

        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        ChannelModuleProduct.objects.filter(module=self.module, sku__isnull=False).delete()
        pairs: list[tuple[Spu, Sku]] = []
        for index in range(5):
            spu = Spu.objects.create(
                status=Spu.Status.ACTIVE,
                local_category=self.root,
                retail_price=Decimal("19.9900"),
            )
            SpuTranslation.objects.create(spu=spu, locale="en-GB", title=f"Bulk {index}")
            ProductSearchDocument.objects.create(
                spu=spu,
                market=self.market,
                locale_code="en-GB",
                title=f"Bulk {index}",
                local_category=self.root,
                min_price=Decimal("9.99"),
                max_price=Decimal("9.99"),
                currency_code="GBP",
                is_searchable=True,
            )
            for variant in range(4):
                pairs.append((spu, self.make_sku(spu, f"v{variant}", price="9.9900")))

        def measure(positions: int) -> int:
            ChannelModuleProduct.objects.filter(module=self.module, sku__isnull=False).delete()
            ChannelModuleProduct.objects.bulk_create(
                [
                    ChannelModuleProduct(
                        module=self.module, spu=spu, sku=sku, sort_order=10 + index
                    )
                    for index, (spu, sku) in enumerate(pairs[:positions])
                ]
            )
            with CaptureQueriesContext(connection) as queries:
                data = public_modules(
                    BEAUTY_CODE, market=self.market, locale_code="en-GB", language_code="en"
                )
            self.assertEqual(len(data["modules"][0]["products"]), positions + 2)
            return len(queries)

        self.assertEqual(measure(1), measure(20))

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
