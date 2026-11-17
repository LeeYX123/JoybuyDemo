"""WP-45 阶段 2：导入链路多 SKU（variants）单测/接口测试（真实 MySQL）。

覆盖：

- 多变体导入建 N SKU + N 身份 + N Offer（同源口径过滤跨商品轴值）；
- 无 price/price_source 不可信的变体只建 SKU 不建 Offer；
- 重导入幂等且不动已有 Offer 归属/状态；
- 老式单 SKU（spec={}）导入再喂 variants payload = 原地升级（同一身份、
  同一 SKU、补 specification、重算签名，其余变体新建）；
- 变体图下载失败不阻断导入（回退无图）；
- 无 variants 的老 payload 行为完全不变（Offer 仍默认 DRAFT）。
"""

import sys
import unittest
from importlib.util import find_spec
from pathlib import Path

CRAWLER_DIR = Path(__file__).resolve().parents[3] / "crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

from catalog.models import Sku, SkuSourceIdentity, Spu  # noqa: E402
from catalog.product_services import canonicalize_source_specification  # noqa: E402
from crawler_control.import_services import import_staging_product  # noqa: E402
from crawler_control.services import start_run  # noqa: E402
from crawler_control.tests.test_crawler_control_domain import CrawlerControlTestBase  # noqa: E402
from offers.models import Offer, OfferSourceIdentity  # noqa: E402

SCRAPY_AVAILABLE = find_spec("scrapy") is not None
FIXTURES_DIR = CRAWLER_DIR / "fixtures"

# 与阶段 1 实抓口径一致的合成 variants（源 sku id / 规格名值对 / price_source）：
# 1001=主变体（is_primary、detail_page）、1002=同源变体（variant_page 带价）、
# 1003=同源变体（价格留空——只建 SKU 不建 Offer）、9999=跨商品轴值（sku_status
# 为空且非主变体 → 兄弟商品，跳过）。
MAIN_SPEC = {"颜色": "黑色", "容量": "128G"}


def _variants_payload():
    from joybuy_crawler.parsers.product_detail import parse_product_detail

    payload = parse_product_detail(
        (FIXTURES_DIR / "product_detail_v1.html").read_text(encoding="utf-8")
    ).to_payload()
    payload["skus"] = [
        {
            "source_id": "1001",
            "price": "29.99",
            "availability": "UNKNOWN",
            "specs": [{"name": "颜色", "value": "黑色"}, {"name": "容量", "value": "128G"}],
        }
    ]
    payload["variants"] = [
        {
            "source_sku_id": "1001",
            "specification": dict(MAIN_SPEC),
            "price": "29.99",
            "currency": "GBP",
            "image_url": "",
            "stock_state": 33,
            "sku_status": "0",
            "is_primary": True,
            "price_source": "detail_page",
        },
        {
            "source_sku_id": "1002",
            "specification": {"颜色": "白色", "容量": "128G"},
            "price": "31.99",
            "currency": "GBP",
            "image_url": "https://fixture.invalid/variant-1002.jpg",
            "stock_state": 33,
            "sku_status": "0",
            "is_primary": False,
            "price_source": "variant_page",
        },
        {
            "source_sku_id": "1003",
            "specification": {"颜色": "蓝色", "容量": "256G"},
            "price": "",
            "currency": "GBP",
            "image_url": "",
            "stock_state": 34,
            "sku_status": "-2",
            "is_primary": False,
            "price_source": "",
        },
        {
            "source_sku_id": "9999",
            "specification": {"容量": "1TB"},
            "price": "99.99",
            "currency": "GBP",
            "image_url": "",
            "stock_state": None,
            "sku_status": None,
            "is_primary": False,
            "price_source": "variant_page",
        },
    ]
    return payload


def _legacy_single_sku_payload():
    from joybuy_crawler.parsers.product_detail import parse_product_detail

    payload = parse_product_detail(
        (FIXTURES_DIR / "product_detail_v1.html").read_text(encoding="utf-8")
    ).to_payload()
    payload["skus"] = [
        {
            "source_id": "1001",
            "price": "29.99",
            "availability": "UNKNOWN",
            "specs": [],
        }
    ]
    payload.pop("variants", None)
    return payload


@unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy (parsel) is not installed")
class VariantImportTests(CrawlerControlTestBase):
    def setUp(self):
        super().setUp()
        self.make_account()
        self.job = self.make_job(name="Variant import job")
        self.run = start_run(self.job)
        from joybuy_crawler.ingest import ingest_product_payload
        from joybuy_crawler.parsers.product_detail import PRODUCT_STRUCTURE_VERSION

        self.ingest = ingest_product_payload
        self.structure_version = PRODUCT_STRUCTURE_VERSION

    def _stage(self, payload):
        return self.ingest(
            self.run,
            payload,
            source_system="joybuy",
            source_url="https://fixture.test/p/1001.html",
            parser_version="product-1",
            structure_version=self.structure_version,
        )

    def _import(self, payload):
        return import_staging_product(
            self._stage(payload),
            market=self.market,
            currency=self.currency,
        )

    def _offer_for(self, spu, source_sku_id):
        return Offer.objects.get(
            sku__spu=spu,
            source_identities__source_id=f"{spu.source_identities.get().source_id}#{source_sku_id}",
        )

    def test_multi_variant_import_creates_skus_identities_and_offers(self):
        outcome = self._import(_variants_payload())
        spu = outcome.spu

        # 同源口径：1001/1002/1003 建 SKU，兄弟商品 9999 被跳过。
        self.assertEqual(Sku.objects.filter(spu=spu).count(), 3)
        identity_ids = set(
            SkuSourceIdentity.objects.filter(sku__spu=spu).values_list("source_id", flat=True)
        )
        self.assertEqual(identity_ids, {"1001", "1002", "1003"})

        # 每个变体 SKU 带真实规格名值对 + 既有签名函数重算的签名。
        sku_1002 = SkuSourceIdentity.objects.get(sku__spu=spu, source_id="1002").sku
        self.assertEqual(sku_1002.specification, {"颜色": "白色", "容量": "128G"})
        expected_signature = canonicalize_source_specification({"颜色": "白色", "容量": "128G"})[1]
        self.assertEqual(sku_1002.specification_signature, expected_signature)

        # Offer：主变体 + 带价变体；无价变体只保留 SKU、不建 Offer。
        self.assertEqual(Offer.objects.filter(sku__spu=spu).count(), 2)
        offer_1002 = self._offer_for(spu, "1002")
        self.assertEqual(str(offer_1002.current_price), "31.9900")
        self.assertEqual(offer_1002.status, Offer.Status.ACTIVE)
        self.assertIsNotNone(offer_1002.listed_at)
        # 主变体 Offer 沿用顶层价格口径，同样 ACTIVE（多变体路径上架即可售）。
        offer_1001 = self._offer_for(spu, "1001")
        self.assertEqual(str(offer_1001.current_price), "29.9900")
        self.assertEqual(offer_1001.status, Offer.Status.ACTIVE)
        self.assertIsNotNone(offer_1001.listed_at)
        self.assertFalse(OfferSourceIdentity.objects.filter(source_id__endswith="#1003").exists())
        self.assertFalse(OfferSourceIdentity.objects.filter(source_id__endswith="#9999").exists())

        # 导入摘要如实记录：kept=3（同源，含主变体）、跨商品跳过 1、无价跳过 1。
        summary = outcome.staging.imported_refs["variants"]
        self.assertEqual(
            summary,
            {
                "kept": 3,
                "skipped_cross_product": 1,
                "skipped_no_spec": 0,
                "skipped_identity_conflict": 0,
                "skus_created": 2,
                "offers_created": 1,
                "offers_skipped_no_price": 1,
                "images_localized": 0,
                "images_failed": 1,  # fixture.invalid 下载失败 → 回退无图不阻断
            },
        )
        # 变体图下载失败不阻断：1002 SKU 仍然存在且 Offer 已建。
        self.assertTrue(SkuSourceIdentity.objects.filter(source_id="1002").exists())

    def test_variant_identity_bound_to_another_product_is_skipped_not_rebound(self):
        # 实抓场景（iPhone 10404455）：同一源 sku（如 10405110）早已作为
        # 「兄弟商品」独立导入过，有自己的 SPU + SkuSourceIdentity。
        # 变体导入遇到这种身份冲突必须跳过该变体，绝不改绑已有身份。
        sibling_payload = _legacy_single_sku_payload()
        sibling_payload["source_id"] = "9999"
        sibling_payload["skus"] = [
            {"source_id": "9999", "price": "99.99", "availability": "UNKNOWN", "specs": []}
        ]
        sibling_outcome = self._import(sibling_payload)
        sibling_spu = sibling_outcome.spu
        sibling_sku = Sku.objects.get(spu=sibling_spu)
        sibling_identity = SkuSourceIdentity.objects.get(sku=sibling_sku)

        outcome_payload = _variants_payload()
        # 9999 必须先过同源口径（sku_status 非空）才会走到身份检查：
        # 模拟源站 skuStatus 声明了它、但它已被独立导入过的场景。
        outcome_payload["variants"][3]["sku_status"] = "0"
        outcome = self._import(outcome_payload)
        spu = outcome.spu
        # 商品 1001 正常导入完成（3 个同源 SKU），9999 变体被跳过。
        self.assertEqual(Sku.objects.filter(spu=spu).count(), 3)
        self.assertFalse(SkuSourceIdentity.objects.filter(sku__spu=spu, source_id="9999").exists())
        # 已有身份原封不动：仍指向兄弟商品 SPU 的老 SKU。
        reloaded = SkuSourceIdentity.objects.get(pk=sibling_identity.pk)
        self.assertEqual(reloaded.sku_id, sibling_sku.pk)
        self.assertEqual(reloaded.sku.spu_id, sibling_spu.pk)
        self.assertEqual(reloaded.sku.specification, {})
        summary = outcome.staging.imported_refs["variants"]
        self.assertEqual(summary["kept"], 4)
        self.assertEqual(summary["skipped_cross_product"], 0)
        self.assertEqual(summary["skipped_identity_conflict"], 1)

    def test_reimport_is_idempotent_and_preserves_offer_state(self):
        first = self._import(_variants_payload())
        spu = first.spu
        offer_1002 = self._offer_for(spu, "1002")
        offer_1002.status = Offer.Status.INACTIVE
        offer_1002.save(update_fields=["status", "updated_at"])

        second = self._import(_variants_payload())

        self.assertEqual(second.spu.pk, spu.pk)
        self.assertEqual(Sku.objects.filter(spu=spu).count(), 3)
        self.assertEqual(SkuSourceIdentity.objects.filter(sku__spu=spu).count(), 3)
        self.assertEqual(Offer.objects.filter(sku__spu=spu).count(), 2)
        # 管理端下架的变体 Offer 不被重导入复活。
        reloaded = Offer.objects.get(pk=offer_1002.pk)
        self.assertEqual(reloaded.status, Offer.Status.INACTIVE)
        # SKU/Offer 主键完全不变（无重复、无重绑）。
        self.assertEqual(
            set(Sku.objects.filter(spu=spu).values_list("pk", flat=True)),
            set(Sku.objects.filter(spu__pk=spu.pk).values_list("pk", flat=True)),
        )
        self.assertEqual(
            Offer.objects.filter(sku__spu=spu, status=Offer.Status.ACTIVE).count(),
            1,
        )

    def test_legacy_single_sku_upgrade_is_in_place(self):
        # 第一步：老式单 SKU 导入（specs 为空、无 variants）——1 SKU、spec={}。
        legacy = self._import(_legacy_single_sku_payload())
        spu = legacy.spu
        self.assertEqual(Sku.objects.filter(spu=spu).count(), 1)
        legacy_sku = Sku.objects.get(spu=spu)
        self.assertEqual(legacy_sku.specification, {})
        legacy_identity = SkuSourceIdentity.objects.get(sku=legacy_sku)
        legacy_offer = Offer.objects.get(sku=legacy_sku)
        self.assertEqual(legacy_offer.status, Offer.Status.DRAFT)  # 无 variants → 原行为

        # 第二步：带 variants 的 payload 重导入同一来源商品 = 原地升级。
        upgraded = self._import(_variants_payload())
        self.assertEqual(upgraded.spu.pk, spu.pk)
        self.assertEqual(Sku.objects.filter(spu=spu).count(), 3)
        identity = SkuSourceIdentity.objects.get(source_id="1001", sku__spu=spu)
        self.assertEqual(identity.pk, legacy_identity.pk)  # 身份原封不动
        upgraded_sku = identity.sku
        self.assertEqual(upgraded_sku.pk, legacy_sku.pk)  # 老 SKU 原地补规格
        self.assertEqual(upgraded_sku.specification, MAIN_SPEC)
        self.assertEqual(
            upgraded_sku.specification_signature,
            canonicalize_source_specification(MAIN_SPEC)[1],
        )
        # 老 Offer 保持归属不变、状态不被触碰（仍是第一次导入的 DRAFT）。
        self.assertEqual(Offer.objects.filter(sku__spu=spu).count(), 2)
        self.assertEqual(Offer.objects.get(pk=legacy_offer.pk).sku_id, legacy_sku.pk)
        self.assertEqual(Offer.objects.get(pk=legacy_offer.pk).status, Offer.Status.DRAFT)
        # 新变体（1002）新建身份/SKU/Offer，新 Offer ACTIVE。
        self.assertTrue(SkuSourceIdentity.objects.filter(source_id="1002").exists())
        self.assertEqual(self._offer_for(spu, "1002").status, Offer.Status.ACTIVE)
        # 无价变体 1003 只建 SKU；兄弟商品 9999 什么都不建。
        self.assertFalse(OfferSourceIdentity.objects.filter(source_id__endswith="#1003").exists())
        self.assertFalse(SkuSourceIdentity.objects.filter(source_id="9999").exists())
        self.assertEqual(Spu.objects.count(), 1)

    def test_payload_without_variants_keeps_legacy_behavior(self):
        from joybuy_crawler.parsers.product_detail import parse_product_detail

        payload = parse_product_detail(
            (FIXTURES_DIR / "product_detail_v1.html").read_text(encoding="utf-8")
        ).to_payload()
        outcome = self._import(payload)
        spu = outcome.spu
        # 3 个 SKU（fixture 自带），Offer 全部保持既有默认 DRAFT。
        self.assertEqual(Sku.objects.filter(spu=spu).count(), 3)
        self.assertEqual(Offer.objects.filter(sku__spu=spu, status=Offer.Status.DRAFT).count(), 3)
        summary = outcome.staging.imported_refs["variants"]
        self.assertEqual(summary["kept"], 0)
        self.assertEqual(summary["skus_created"], 0)
        self.assertEqual(outcome.staging.imported_refs["new_active_offers"], 0)
