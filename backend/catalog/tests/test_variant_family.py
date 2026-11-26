"""批次 DB：同款族（VariantFamily）建族、搜索去重、商家页去重、PDP 族/商家契约。

覆盖：

1. ``variant_family_services`` 纯函数：Hypershell 这对标题落在 0.85–0.90 档
   （任务书初稿的 0.90 覆盖不到）、词级公共前缀、代表选取优先级；
2. 建族命令：同 slug（含跨商家）建族；Q8 价差 >3x 不建；成员按
   (spu, sku, offer) 展开、``is_representative`` 标在代表行上；
3. 搜索文档族字段回填 + ``search_documents`` 只出代表卡 + 卡片价 =
   ``family_max_price``；
4. 商家页：同族只出一张卡，卡片带 ``offer_id``（PDP 默认选中该商家，Q10）；
5. 详情接口：未合并族返回 ``variant_family``（成员/规格/商家），每个 SKU 带
   ``offers`` 列表。
"""

import json
import tempfile
from collections import Counter
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from offers.models import Currency, Market
from offers.services import import_offer_from_source

from catalog.models import (
    ProductSearchDocument,
    Spu,
    SpuSourceIdentity,
    SpuTranslation,
    VariantFamily,
    VariantFamilyMember,
)
from catalog.product_services import get_or_create_sku_from_source, get_or_create_spu_from_source
from catalog.search_services import rebuild_search_document, search_documents
from catalog.variant_family_services import (
    common_prefix_len,
    cosine,
    normalize_tokens,
    plan_families,
    representative_sort_key,
)

TITLE_A = (
    "【IFA 2026 Featured Model】Hypershell X Ultra S AI-Powered Exoskeleton, "
    "1000W Leg Assist, Dual Batteries, Up to 60 km Total Range, 12 Intelligent Modes, "
    "Premium Wearable Exoskeleton for Hiking & Extreme Outdoor Adventures"
)
TITLE_B = (
    "【IFA 2026 Featured Model】Hypershell X Max S AI-Powered Exoskeleton, "
    "1000W Leg Assist, 30 km Range, 10 Intelligent Modes, "
    "Smart Wearable Exoskeleton for Hiking, Walking & All-Terrain Adventures"
)


def _make_spu(public_suffix, title, *, status=Spu.Status.ACTIVE):
    spu, _ = get_or_create_spu_from_source(
        source_system="joybuy", source_id=f"db-{public_suffix}", title=title
    )
    Spu.objects.filter(pk=spu.pk).update(status=status)
    spu.refresh_from_db()
    SpuTranslation.objects.update_or_create(spu=spu, locale="en-GB", defaults={"title": title})
    return spu


def _make_sku(spu, suffix, specification):
    sku, _ = get_or_create_sku_from_source(
        spu=spu,
        source_system="joybuy",
        source_id=f"db-sku-{suffix}",
        specification=specification,
        skip_attribute_validation=True,
    )
    return sku


def _make_offer(sku, suffix, price, merchant, market, currency, source_system="joybuy"):
    from offers.models import Offer

    offer, _ = import_offer_from_source(
        sku=sku,
        merchant=merchant,
        market=market,
        currency=currency,
        source_system=source_system,
        source_id=f"db-offer-{suffix}",
        current_price=price,
    )
    # 导入默认是 DRAFT（等商家上架）；列表/搜索/族计算只认 ACTIVE。
    Offer.objects.filter(pk=offer.pk).update(status=Offer.Status.ACTIVE)
    offer.refresh_from_db()
    return offer


class TitleSimilarityTests(TestCase):
    """Hypershell 这对标题是 0.85 档的典型：任务书的 0.90 覆盖不到。"""

    def test_char_ratio_cannot_reach_spec_threshold(self):
        """任务书初稿的「归一化相似度 ≥0.90」覆盖不到这对标题（实测 0.8101）。

        真实语料上的 IDF 加权余弦是 0.8531（`var/variant_family_db_20261127/`
        的预览脚本里有完整审计），所以 high 档实际取 0.85 + 强身份。
        这里只断言与语料无关的确定性事实：字符级相似度 < 0.90、标题头一致。
        """

        counter_a = Counter(normalize_tokens(TITLE_A))
        counter_b = Counter(normalize_tokens(TITLE_B))
        # 均匀权重（等价于普通余弦）也低于 0.90
        self.assertLess(cosine(counter_a, counter_b, {}, 1.0), 0.90)
        from difflib import SequenceMatcher

        self.assertLess(SequenceMatcher(None, TITLE_A.lower(), TITLE_B.lower()).ratio(), 0.90)

    def test_common_prefix_counts_tokens_without_numbers(self):
        left = normalize_tokens(TITLE_A)
        right = normalize_tokens(TITLE_B)
        self.assertGreaterEqual(common_prefix_len(left, right), 4)


class RepresentativePickerTests(TestCase):
    def test_sort_key_prefers_merged_keep_then_cards(self):
        keep = {"pk": 1, "status": "ACTIVE", "created_at": "2026-01-01"}
        normal = {"pk": 2, "status": "ACTIVE", "created_at": "2025-01-01"}
        key_keep = representative_sort_key(keep, sellable={1, 2}, doc_spu_ids={1, 2}, keep_ids={1})
        key_normal = representative_sort_key(
            normal, sellable={1, 2}, doc_spu_ids={1, 2}, keep_ids={1}
        )
        self.assertLess(key_keep, key_normal)

        no_doc = {"pk": 3, "status": "ACTIVE", "created_at": "2024-01-01"}
        key_no_doc = representative_sort_key(
            no_doc, sellable={1, 2, 3}, doc_spu_ids={1, 2}, keep_ids={1}
        )
        self.assertGreater(key_no_doc, key_normal)


class VariantFamilyFlowTests(TestCase):
    """真实链路：建族 → 回填搜索文档 → 列表/商家页/PDP 都按族去重。"""

    def setUp(self):
        from merchants.models import Merchant

        self.merchant, _ = Merchant.objects.get_or_create(
            slug="db-test-seller",
            defaults={
                "display_name": "DB Test Seller",
                "onboarding_status": Merchant.OnboardingStatus.ACTIVE,
                "merchant_type": Merchant.Type.STANDARD,
            },
        )
        self.market = Market.objects.get(code="GB")
        self.currency = Currency.objects.get(code="GBP")

    def _build(self):
        report = Path(tempfile.mkdtemp()) / "build.json"
        call_command(
            "build_variant_families",
            "--apply",
            "--market",
            "GB",
            "--locale",
            "en-GB",
            "--report",
            str(report),
            stdout=StringIO(),
        )
        backfill = Path(tempfile.mkdtemp()) / "backfill.json"
        call_command(
            "backfill_family_search_fields",
            "--apply",
            "--report",
            str(backfill),
            stdout=StringIO(),
        )
        return json.loads(report.read_text(encoding="utf-8"))

    def _same_slug_family(self, slug, prices=("10.00", "12.00"), suffix="slug"):
        spus = []
        for index, price in enumerate(prices):
            spu = _make_spu(f"{suffix}-{index}", f"Family Product {suffix} {index}")
            sku = _make_sku(spu, f"{suffix}-{index}", {"Size": f"{index + 1} Pack"})
            _make_offer(
                sku,
                f"{suffix}-{index}",
                price,
                self.merchant,
                self.market,
                self.currency,
            )
            SpuSourceIdentity.objects.update_or_create(
                spu=spu,
                source_system="joybuy_uk",
                source_id=f"src-{suffix}-{index}",
                defaults={
                    "source_url": f"https://www.joybuy.co.uk/dp/{slug}/{index}",
                    "first_seen_at": spu.created_at,
                    "last_seen_at": spu.created_at,
                },
            )
            spus.append(spu)
        return spus

    def test_build_creates_family_members_and_skips_big_price_spread(self):
        cheap, other = self._same_slug_family("flow-slug", prices=("10.00", "12.00"))
        self._same_slug_family("spread-slug", prices=("10.00", "400.00"), suffix="spread")

        plan = plan_families(market_code="GB")
        self.assertIn(
            "slug:spread-slug", {item["family_key"] for item in plan.excluded_price_spread}
        )

        payload = self._build()
        self.assertTrue(payload["applied"])
        self.assertNotIn(
            "slug:spread-slug", set(VariantFamily.objects.values_list("family_key", flat=True))
        )

        family = VariantFamily.objects.get(family_key="slug:flow-slug")
        self.assertEqual(family.kind, VariantFamily.Kind.SLUG)
        self.assertEqual(family.member_count, 2)
        self.assertEqual(family.representative_spu_id, cheap.pk)  # 创建最早 → 代表
        members = list(family.members.all())
        self.assertEqual({member.spu_id for member in members}, {cheap.pk, other.pk})
        self.assertTrue(all(member.offer_id for member in members))
        self.assertTrue(all(member.merchant_label for member in members))
        self.assertEqual(
            {member.spu_id for member in members if member.is_representative}, {cheap.pk}
        )

    def test_search_documents_only_show_representative_with_family_max_price(self):
        cheap, other = self._same_slug_family("search-slug", prices=("10.00", "30.00"))
        self._build()
        for spu in (cheap, other):
            rebuild_search_document(spu, market=self.market)

        documents = ProductSearchDocument.objects.filter(market=self.market)
        representative = documents.filter(is_family_representative=True)
        self.assertEqual(representative.count(), 1)
        document = representative.get()
        self.assertEqual(document.spu_id, cheap.pk)
        self.assertEqual(document.family_key, "slug:search-slug")
        self.assertEqual(str(document.family_max_price), "30.0000")
        self.assertEqual(documents.filter(is_family_representative=False).count(), 1)

        result = search_documents(market=self.market)
        self.assertEqual(result["total"], 1)
        item = result["items"][0]
        self.assertEqual(item["family_key"], "slug:search-slug")
        self.assertEqual(item["family_max_price"], "30.0000")

    def test_detail_returns_variant_family_and_all_seller_offers(self):
        left, right = self._same_slug_family("detail-slug", prices=("10.00", "12.00"))
        self._build()
        response = self.client.get(
            reverse("product-detail", args=[left.public_id]), {"market": "GB"}
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        family = payload["variant_family"]
        self.assertIsNotNone(family)
        self.assertEqual(family["family_key"], "slug:detail-slug")
        self.assertEqual(
            {member["spu_public_id"] for member in family["members"]},
            {str(left.public_id), str(right.public_id)},
        )
        self.assertEqual(sum(1 for member in family["members"] if member["is_current"]), 1)
        self.assertTrue(all(member["skus"] for member in family["members"]))
        self.assertTrue(all("offers" in sku for sku in payload["skus"]))
        self.assertEqual(payload["skus"][0]["offers"][0]["merchant"]["slug"], self.merchant.slug)

    def test_merged_style_family_returns_no_variant_family(self):
        """单 SPU 多 SKU（合并族）不返回 variant_family，仍走 DA 的 ?sku= 档案。"""
        spu = _make_spu("merged-only", "Merged Only Product")
        sku_a = _make_sku(spu, "merged-a", {"Size": "140g"})
        sku_b = _make_sku(spu, "merged-b", {"Size": "300g"})
        _make_offer(sku_a, "merged-a", "10.00", self.merchant, self.market, self.currency)
        _make_offer(sku_b, "merged-b", "12.00", self.merchant, self.market, self.currency)
        response = self.client.get(
            reverse("product-detail", args=[spu.public_id]), {"market": "GB"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["variant_family"])

    def test_merchant_page_dedupes_family_cards(self):
        left, right = self._same_slug_family("shop-slug", prices=("10.00", "12.00"))
        self._build()
        response = self.client.get(reverse("merchant-public-detail", args=[self.merchant.slug]))
        self.assertEqual(response.status_code, 200)
        products = response.json()["merchant"]["products"]
        family_cards = [
            product for product in products if product["family_key"] == "slug:shop-slug"
        ]
        self.assertEqual(len(family_cards), 1)
        card = family_cards[0]
        self.assertTrue(card["offer_id"])
        self.assertIn(card["product_id"], {str(left.public_id), str(right.public_id)})

    def test_rebuild_search_document_keeps_family_fields(self):
        """爬虫重导刷新文档时不能把族键/代表标记冲掉（否则列表又会出重复卡）。"""
        left, _right = self._same_slug_family("rebuild-slug", prices=("10.00", "12.00"))
        self._build()
        document = rebuild_search_document(left, market=self.market)
        self.assertEqual(document.family_key, "slug:rebuild-slug")
        self.assertTrue(document.is_family_representative)
        self.assertEqual(str(document.family_max_price), "12.0000")
        self.assertTrue(VariantFamilyMember.objects.filter(spu=left).exists())
