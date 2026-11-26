"""批次 DA：变体档案（SpuVariantArchive）回填与 ``?sku=`` 详情契约。

覆盖：

1. ``classify_share_metadata`` 纯规则：纯尺码 → True，颜色/型号词 → False，
   不确定 → True（保守）；
2. 回填命令：从备份 JSON 还原来源 SPU / 画廊 / 评分/已售/标题快照，幂等；
3. 详情接口 ``?sku=``：命中档案返回 ``variant_archive``，无参数/无档案时
   为 null，且既有顶层字段不变。
"""

import json
import tempfile
from decimal import Decimal
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from media.models import MediaAsset
from merchants.services import get_import_fallback_merchant
from offers.models import Currency, Market
from offers.services import import_offer_from_source

from catalog.models import Spu, SpuDetail, SpuVariantArchive
from catalog.product_services import get_or_create_sku_from_source, get_or_create_spu_from_source
from catalog.variant_archive_services import classify_share_metadata


class ClassifyShareMetadataTests(SimpleTestCase):
    def test_pure_size_labels_share_metadata(self):
        for axis, labels in (
            ("Size", ["140g", "300g", "600g"]),
            ("Style", ["XXL", "S", "XXXL", "L", "M", "XL"]),
            ("Pack", ["2 x Med", "1 x Large"]),
            (
                "Style",
                [
                    "Large 9-Pack Multicoloured",
                    "Small 2-Pack Multicoloured",
                    "Small 1 Pack-Small Size",
                    "Large 3-Pack Multicoloured",
                ],
            ),
        ):
            share, reason = classify_share_metadata(axis, labels)
            self.assertTrue(share, f"{axis} {labels} -> {reason}")
            self.assertEqual(reason, "size_like")

    def test_colour_or_model_labels_switch_metadata(self):
        for axis, labels in (
            ("Colour", ["M Grey", "M Brown", "S White"]),
            ("Colour", ["Pink", "Black", "Purple"]),
            ("Style", ["Flamingo", "Jungle", "Cloudy Sky"]),
            ("Style", ["Treat Bone", "Treat Mat", "Snuffle Ball"]),
        ):
            share, reason = classify_share_metadata(axis, labels)
            self.assertFalse(share, f"{axis} {labels} -> {reason}")
            self.assertIn(reason, {"colour_word", "axis_text"})

    def test_uncertain_labels_stay_shared(self):
        share, reason = classify_share_metadata("Pack", ["Day 5x 14", "Night 5x 10"])
        self.assertTrue(share)
        self.assertEqual(reason, "uncertain_default")


def _make_spu(source_id, title):
    spu, _ = get_or_create_spu_from_source(source_system="joybuy", source_id=source_id, title=title)
    Spu.objects.filter(pk=spu.pk).update(status=Spu.Status.ACTIVE)
    spu.refresh_from_db()
    return spu


def _make_sku(spu, source_id, label, axis="Size"):
    sku, _ = get_or_create_sku_from_source(
        spu=spu,
        source_system="joybuy",
        source_id=source_id,
        specification={axis: label},
        skip_attribute_validation=True,
    )
    return sku


class BackfillVariantArchiveTests(TestCase):
    def setUp(self):
        self.asset = MediaAsset.objects.create(
            sha256="a" * 64,
            kind=MediaAsset.Kind.PRODUCT,
            relative_path="products/original/aa/aa.webp",
            first_seen_at=timezone.now(),
            last_seen_at=timezone.now(),
        )
        self.groups = []
        self.archived = []
        # G1：纯尺码（share_metadata=True）；G2：颜色（False）。
        for index, (group_id, axis, labels) in enumerate(
            (
                ("DA-T1", "Size", ["300g", "140g"]),
                ("DA-T2", "Colour", ["Black", "Grey"]),
            )
        ):
            keep = _make_spu(f"da-keep-{index}", f"Product {index}")
            archived = _make_spu(f"da-arch-{index}", f"Product {index} {labels[1]}")
            keep_sku = _make_sku(keep, f"da-keep-sku-{index}", labels[0], axis)
            archived_sku = _make_sku(archived, f"da-arch-sku-{index}", labels[1], axis)
            # 合并后：成员 SKU / 画廊都改挂保留 SPU（与真实库一致）。
            archived_sku.spu = keep
            archived_sku.specification_merge_managed = True
            archived_sku.save(update_fields=["spu", "specification_merge_managed", "updated_at"])
            archived.status = Spu.Status.INACTIVE
            archived.save(update_fields=["status", "updated_at"])
            SpuDetail.objects.create(
                spu=archived,
                content_sections=[{"title": f"archived detail {index}"}],
                rating_average=Decimal("4.29"),
                rating_count=352,
                rating_distribution={"5": 300, "4": 52},
                sale_amount="1.5k+",
                comment_count_display="80+",
            )
            SpuDetail.objects.create(spu=keep, sale_amount="5.9k+")
            self.groups.append(
                {
                    "group_id": group_id,
                    "axis": axis,
                    "labels": " | ".join(labels),
                    "keep_public_id": str(keep.public_id),
                    "keep_spu_id": keep.pk,
                    "merged": [{"public_id": str(archived.public_id), "spu_id": archived.pk}],
                    "skus": [
                        {
                            "public_id": str(keep_sku.public_id),
                            "spu_public_id": str(keep.public_id),
                        },
                        {
                            "public_id": str(archived_sku.public_id),
                            "spu_public_id": str(archived.public_id),
                        },
                    ],
                    "media_usages": [
                        {
                            "id": 1,
                            "asset_id": self.asset.pk,
                            "object_id": archived.pk,
                            "role": "gallery",
                            "sort_order": 0,
                            "deleted_duplicate": False,
                        }
                    ],
                }
            )
            self.archived.append((keep, archived, keep_sku, archived_sku))

    def _run(self, temp_dir):
        backup = Path(temp_dir) / "backup.json"
        backup.write_text(json.dumps({"groups": self.groups}), encoding="utf-8")
        report = Path(temp_dir) / "report.json"
        out = StringIO()
        call_command(
            "backfill_variant_archive",
            backup=str(backup),
            report=str(report),
            apply=True,
            stdout=out,
        )
        return out.getvalue(), report

    def test_backfill_restores_archive_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output, report_path = self._run(temp_dir)
            self.assertIn("created=4", output)
            self.assertEqual(SpuVariantArchive.objects.count(), 4)
            self.assertTrue(report_path.exists())

            keep, archived, keep_sku, archived_sku = self.archived[0]
            archived_row = SpuVariantArchive.objects.get(spu=keep, sku=archived_sku)
            self.assertEqual(str(archived_row.source_spu_public_id), str(archived.public_id))
            self.assertEqual(archived_row.detail_spu_id, archived.pk)
            self.assertEqual(archived_row.gallery_manifest, [self.asset.relative_path])
            self.assertEqual(archived_row.axis_label, "140g")
            self.assertTrue(archived_row.share_metadata)
            self.assertEqual(archived_row.share_metadata_reason, "size_like")
            self.assertEqual(archived_row.rating_snapshot["average"], "4.29")
            self.assertEqual(archived_row.rating_snapshot["count"], 352)
            self.assertEqual(archived_row.sold_snapshot["sale_amount"], "1.5k+")
            self.assertTrue(archived_row.title_snapshots["en-GB"].endswith("140g"))

            keep_row = SpuVariantArchive.objects.get(spu=keep, sku=keep_sku)
            self.assertEqual(str(keep_row.source_spu_public_id), str(keep.public_id))
            self.assertIsNone(keep_row.detail_spu_id)
            self.assertEqual(keep_row.gallery_manifest, [])

            colour_row = SpuVariantArchive.objects.get(
                spu=self.archived[1][0], sku=self.archived[1][3]
            )
            self.assertFalse(colour_row.share_metadata)
            self.assertEqual(colour_row.share_metadata_reason, "colour_word")

            output, _ = self._run(temp_dir)
            self.assertIn("created=0", output)
            self.assertIn("updated=0", output)
            self.assertIn("unchanged=4", output)
            self.assertEqual(SpuVariantArchive.objects.count(), 4)

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            backup = Path(temp_dir) / "backup.json"
            backup.write_text(json.dumps({"groups": self.groups}), encoding="utf-8")
            out = StringIO()
            call_command(
                "backfill_variant_archive",
                backup=str(backup),
                report=str(Path(temp_dir) / "report.json"),
                stdout=out,
            )
            self.assertIn("dry_run", out.getvalue())
            self.assertEqual(SpuVariantArchive.objects.count(), 0)


class VariantArchiveDetailApiTests(TestCase):
    def setUp(self):
        self.merchant = get_import_fallback_merchant()
        self.market = Market.objects.get(code="GB")
        self.currency = Currency.objects.get(code="GBP")
        self.keep = _make_spu("api-keep", "Collagen Powder")
        self.archived = _make_spu("api-archived", "Collagen Powder 140g")
        self.keep_sku = _make_sku(self.keep, "api-keep-sku", "300g")
        self.archived_sku = _make_sku(self.archived, "api-arch-sku", "140g")
        for sku, source_id, price in (
            (self.keep_sku, "api-keep-offer", "22.99"),
            (self.archived_sku, "api-arch-offer", "14.99"),
        ):
            import_offer_from_source(
                sku=sku,
                merchant=self.merchant,
                market=self.market,
                currency=self.currency,
                source_system="joybuy",
                source_id=source_id,
                current_price=price,
            )
        self.archived_sku.spu = self.keep
        self.archived_sku.save(update_fields=["spu", "updated_at"])
        self.archived.status = Spu.Status.INACTIVE
        self.archived.save(update_fields=["status", "updated_at"])
        SpuDetail.objects.create(
            spu=self.archived,
            content_sections=[{"title": "archived detail"}],
            specification_tables=[{"title": "spec", "rows": [{"name": "Size", "value": "140g"}]}],
            ai_summary="archived ai",
            rating_average=Decimal("4.41"),
            rating_count=249,
            rating_distribution={"5": 200, "4": 49},
            sale_amount="6.9k+",
        )
        SpuDetail.objects.create(
            spu=self.keep,
            content_sections=[{"title": "keep detail"}],
            rating_average=Decimal("4.32"),
            rating_count=516,
            sale_amount="1.5k+",
        )
        self.asset = MediaAsset.objects.create(
            sha256="b" * 64,
            kind=MediaAsset.Kind.PRODUCT,
            relative_path="products/original/bb/bb.webp",
            first_seen_at=timezone.now(),
            last_seen_at=timezone.now(),
        )
        SpuVariantArchive.objects.create(
            spu=self.keep,
            sku=self.archived_sku,
            source_spu_public_id=self.archived.public_id,
            axis_label="140g",
            gallery_manifest=[self.asset.relative_path],
            detail_spu=self.archived,
            rating_snapshot={
                "average": "4.41",
                "count": 249,
                "distribution": {"5": 200, "4": 49},
            },
            sold_snapshot={"sale_amount": "6.9k+", "comment_count_display": "80+"},
            title_snapshots={"en-GB": "Collagen Powder 140g"},
            share_metadata=False,
            share_metadata_reason="colour_word",
        )
        SpuVariantArchive.objects.create(
            spu=self.keep,
            sku=self.keep_sku,
            source_spu_public_id=self.keep.public_id,
            axis_label="300g",
            gallery_manifest=[],
            detail_spu=None,
            rating_snapshot={"average": "4.32", "count": 516, "distribution": {}},
            sold_snapshot={"sale_amount": "1.5k+"},
            title_snapshots={"en-GB": "Collagen Powder"},
            share_metadata=False,
            share_metadata_reason="colour_word",
        )

    def _get(self, **params):
        return self.client.get(
            reverse("product-detail", kwargs={"public_id": self.keep.public_id}), params
        )

    def test_sku_param_returns_variant_archive_without_breaking_base_fields(self):
        response = self._get(sku=str(self.archived_sku.public_id))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # 既有字段保持 SPU 级（不因 ?sku= 改变）。
        self.assertEqual(data["title"], "Collagen Powder")
        self.assertEqual(data["sale_amount"], "1.5k+")
        self.assertEqual(data["content_sections"], [{"title": "keep detail"}])

        archive = data["variant_archive"]
        self.assertIsNotNone(archive)
        self.assertEqual(archive["sku"], str(self.archived_sku.public_id))
        self.assertEqual(archive["source_spu_public_id"], str(self.archived.public_id))
        self.assertEqual(archive["axis_label"], "140g")
        self.assertFalse(archive["share_metadata"])
        self.assertEqual(archive["title"], "Collagen Powder 140g")
        self.assertEqual(len(archive["gallery"]), 1)
        self.assertEqual(archive["gallery"][0]["url"], f"/media/{self.asset.relative_path}")
        self.assertEqual(archive["review_summary"]["source"], "variant_archive")
        self.assertEqual(archive["review_summary"]["count"], 249)
        self.assertEqual(archive["sale_amount"], "6.9k+")
        self.assertEqual(archive["detail"]["content_sections"], [{"title": "archived detail"}])
        self.assertEqual(archive["detail"]["ai_summary"], "archived ai")

    def test_keep_origin_sku_has_empty_gallery_and_null_detail(self):
        archive = self._get(sku=str(self.keep_sku.public_id)).json()["variant_archive"]
        self.assertEqual(archive["gallery"], [])
        self.assertIsNone(archive["detail"])
        self.assertEqual(archive["title"], "Collagen Powder")

    def test_missing_or_unknown_sku_returns_null(self):
        self.assertIsNone(self._get().json()["variant_archive"])
        self.assertIsNone(self._get(sku=str(self.archived.public_id)).json()["variant_archive"])
        self.assertIsNone(self._get(sku="not-a-uuid").json()["variant_archive"])

    def test_share_metadata_true_family_still_exposes_archive(self):
        SpuVariantArchive.objects.filter(sku=self.archived_sku).update(
            share_metadata=True, share_metadata_reason="size_like"
        )
        archive = self._get(sku=str(self.archived_sku.public_id)).json()["variant_archive"]
        self.assertTrue(archive["share_metadata"])
        self.assertEqual(archive["share_metadata_reason"], "size_like")

    def test_alias_lookup_with_sku_param(self):
        from catalog.models import SpuAlias

        SpuAlias.objects.create(
            old_public_id=self.archived.public_id,
            spu=self.keep,
            reason="DA/test",
        )
        response = self.client.get(
            reverse("product-detail", kwargs={"public_id": self.archived.public_id}),
            {"sku": str(self.archived_sku.public_id)},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["canonical_public_id"], str(self.keep.public_id))
        self.assertEqual(data["variant_archive"]["axis_label"], "140g")
