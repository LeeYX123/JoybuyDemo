"""回填同款合并的「变体档案」（批次 DA，2026-11-27）。

数据来源只有一个：``var/variant_merge_20261126/backup_merge.json``（批次 CB2
合并前的快照）。合并后库里已经没有「SKU → 合并前来源 SPU」的映射，成员画廊
``MediaUsage`` 也改挂保留 SPU 并按 asset 去重，所以画廊归属只能从备份还原。

默认 DRY_RUN（只读 + 写报告），``--apply`` 才写 ``SpuVariantArchive``。幂等：
按唯一键 ``(spu, sku)`` upsert，重跑时字段完全一致的行计入 ``unchanged``。

每条档案记录：

- ``source_spu_public_id`` / ``detail_spu``：来源 SPU（归档 SPU 的图文详情仍可读）；
- ``gallery_manifest``：来源 SPU 合并前的画廊相对路径（**包含**被去重的共享图，
  还原原始画廊；保留 SPU 自己的 SKU 无法反拆，留空由前端回退保留 SPU 画廊）；
- ``rating_snapshot`` / ``sold_snapshot`` / ``title_snapshots``：来源 SPU 的
  ``SpuDetail`` 评分/已售与 ``SpuTranslation`` 标题快照；
- ``share_metadata``：纯尺码/数量变体为 True（只切价格/库存/规格），其余为
  False（整套切换）；判定规则见 ``catalog/variant_archive_services.py``。
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

from catalog.models import Sku, Spu, SpuDetail, SpuTranslation, SpuVariantArchive
from catalog.variant_archive_services import classify_share_metadata
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from media.models import MediaAsset

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_BACKUP = REPOSITORY_ROOT / "var" / "variant_merge_20261126" / "backup_merge.json"
DEFAULT_REPORT = REPOSITORY_ROOT / "var" / "variant_archive_20261127" / "backfill_report.json"
SAMPLE_SIZE = 10


def _resolve_path(value: str, default: Path) -> Path:
    path = Path(value) if value else default
    if not path.is_absolute():
        path = REPOSITORY_ROOT / path
    return path


def _spec_label(sku: Sku) -> tuple[str, str]:
    """从合并后 SKU 的 ``{axis: label}`` 取（轴名, 轴值）；异常结构返回空。"""

    specification = sku.specification
    if not isinstance(specification, dict) or len(specification) != 1:
        return "", ""
    axis, label = next(iter(specification.items()))
    return str(axis or ""), str(label or "")


class Command(BaseCommand):
    help = "从 backup_merge.json 回填 SpuVariantArchive（默认 DRY_RUN，--apply 写库）。"

    def add_arguments(self, parser):
        parser.add_argument("--backup", default="", help="backup_merge.json 路径")
        parser.add_argument("--report", default="", help="报告输出路径（JSON）")
        parser.add_argument("--apply", action="store_true", help="实际写库（默认只读）")
        parser.add_argument(
            "--group-id",
            action="append",
            default=[],
            help="只处理指定 group_id（可重复）",
        )

    def handle(self, *args, **options):
        backup_path = _resolve_path(options["backup"], DEFAULT_BACKUP)
        report_path = _resolve_path(options["report"], DEFAULT_REPORT)
        apply_changes = bool(options["apply"])
        only_groups = set(options["group_id"] or [])

        payload = json.loads(backup_path.read_text(encoding="utf-8"))
        groups = payload.get("groups") or []
        if only_groups:
            groups = [group for group in groups if group.get("group_id") in only_groups]

        # --- 批量读取（避免每组 4 次查询） ---
        spu_public_ids = set()
        sku_public_ids = set()
        for group in groups:
            spu_public_ids.add(group["keep_public_id"])
            for member in group.get("merged") or []:
                spu_public_ids.add(member["public_id"])
            for row in group.get("skus") or []:
                sku_public_ids.add(row["public_id"])
                spu_public_ids.add(row["spu_public_id"])
        spus = {str(spu.public_id): spu for spu in Spu.objects.filter(public_id__in=spu_public_ids)}
        skus = {str(sku.public_id): sku for sku in Sku.objects.filter(public_id__in=sku_public_ids)}
        spu_ids = {spu.pk for spu in spus.values()}
        details = {detail.spu_id: detail for detail in SpuDetail.objects.filter(spu_id__in=spu_ids)}
        titles = defaultdict(dict)
        for spu_id, locale, title in SpuTranslation.objects.filter(spu_id__in=spu_ids).values_list(
            "spu_id", "locale", "title"
        ):
            titles[spu_id][locale] = title

        # 备份里 media_usages 的 object_id 是成员 SPU 的 pk；asset_id → 相对路径。
        asset_ids = {
            usage["asset_id"]
            for group in groups
            for usage in group.get("media_usages") or []
            if usage.get("role") == "gallery"
        }
        asset_paths = dict(
            MediaAsset.objects.filter(pk__in=asset_ids).values_list("pk", "relative_path")
        )

        existing = {
            (archive.spu_id, archive.sku_id): archive
            for archive in SpuVariantArchive.objects.filter(spu_id__in=spu_ids)
        }

        stats = Counter()
        reasons = Counter()
        skipped = []
        samples = []
        pending = []
        seen_keys = set()

        for group in groups:
            group_id = group.get("group_id") or "?"
            keep_public_id = group.get("keep_public_id")
            keep = spus.get(str(keep_public_id))
            if keep is None:
                skipped.append({"group_id": group_id, "reason": "keep_missing"})
                stats["groups_skipped"] += 1
                continue
            share_metadata, reason = classify_share_metadata(
                group.get("axis") or "",
                str(group.get("labels") or "").split(" | "),
            )
            reasons[reason] += 1

            gallery_by_spu = defaultdict(list)
            for usage in group.get("media_usages") or []:
                if usage.get("role") != "gallery":
                    continue
                relative_path = asset_paths.get(usage["asset_id"])
                if not relative_path:
                    continue
                gallery_by_spu[usage["object_id"]].append(
                    (usage.get("sort_order") or 0, usage["asset_id"], relative_path)
                )

            for group_skus in group.get("skus") or []:
                source_public_id = str(group_skus["spu_public_id"])
                source_spu = spus.get(source_public_id)
                sku = skus.get(str(group_skus["public_id"]))
                if source_spu is None or sku is None or sku.spu_id != keep.pk:
                    skipped.append(
                        {
                            "group_id": group_id,
                            "sku": str(group_skus["public_id"]),
                            "reason": "sku_or_source_missing",
                        }
                    )
                    stats["skus_skipped"] += 1
                    continue
                key = (keep.pk, sku.pk)
                if key in seen_keys:
                    skipped.append(
                        {
                            "group_id": group_id,
                            "sku": str(sku.public_id),
                            "reason": "duplicate_in_backup",
                        }
                    )
                    stats["skus_skipped"] += 1
                    continue
                seen_keys.add(key)

                axis, label = _spec_label(sku)
                is_keep_origin = source_public_id == str(keep_public_id)
                detail = details.get(source_spu.pk)
                manifest = (
                    []
                    if is_keep_origin
                    else [path for _, _, path in sorted(gallery_by_spu.get(source_spu.pk, []))]
                )
                rating_snapshot = {}
                sold_snapshot = {}
                if detail is not None:
                    if detail.rating_count or detail.rating_average is not None:
                        rating_snapshot = {
                            "average": (
                                str(detail.rating_average)
                                if detail.rating_average is not None
                                else None
                            ),
                            "count": detail.rating_count or 0,
                            "distribution": detail.rating_distribution or {},
                        }
                    sold_snapshot = {
                        "sale_amount": detail.sale_amount or "",
                        "comment_count_display": detail.comment_count_display or "",
                    }

                defaults = {
                    "source_spu_public_id": source_spu.public_id,
                    "axis_label": f"{label}"[:120],
                    "gallery_manifest": manifest,
                    "detail_spu": None if is_keep_origin else source_spu,
                    "rating_snapshot": rating_snapshot,
                    "sold_snapshot": sold_snapshot,
                    "title_snapshots": dict(titles.get(source_spu.pk) or {}),
                    "share_metadata": share_metadata,
                    "share_metadata_reason": reason,
                }

                stats["share_true" if share_metadata else "share_false"] += 1
                current = existing.get(key)
                if current is not None and self._same(current, defaults):
                    stats["unchanged"] += 1
                    continue
                stats["updated" if current is not None else "created"] += 1
                pending.append((keep, sku, defaults))
                if len(samples) < SAMPLE_SIZE:
                    samples.append(
                        {
                            "group_id": group_id,
                            "spu": str(keep.public_id),
                            "sku": str(sku.public_id),
                            "source_spu_public_id": str(source_spu.public_id),
                            "axis": axis,
                            "axis_label": label,
                            "share_metadata": share_metadata,
                            "share_metadata_reason": reason,
                            "gallery_images": len(manifest),
                            "has_detail": detail is not None and not is_keep_origin,
                            "title": (defaults["title_snapshots"].get("en-GB") or "")[:80],
                        }
                    )

        if apply_changes and pending:
            with transaction.atomic():
                for keep, sku, defaults in pending:
                    SpuVariantArchive.objects.update_or_create(
                        spu=keep,
                        sku=sku,
                        defaults=defaults,
                    )

        report = {
            "generated_at": timezone.now().isoformat(),
            "mode": "apply" if apply_changes else "dry_run",
            "backup": str(backup_path),
            "groups": len(groups),
            "skus": sum(len(group.get("skus") or []) for group in groups),
            "created": stats["created"],
            "updated": stats["updated"],
            "unchanged": stats["unchanged"],
            "skipped": stats["skus_skipped"],
            "groups_skipped": stats["groups_skipped"],
            "share_metadata": {
                "true": stats["share_true"],
                "false": stats["share_false"],
                "reasons": dict(reasons),
            },
            "samples": samples,
            "skipped_details": skipped[:50],
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        self.stdout.write(
            f"[{report['mode']}] groups={report['groups']} skus={report['skus']} "
            f"created={report['created']} updated={report['updated']} "
            f"unchanged={report['unchanged']} skipped={report['skipped']} "
            f"share_metadata={report['share_metadata']['true']}T/"
            f"{report['share_metadata']['false']}F"
        )
        self.stdout.write(f"report: {report_path}")
        if not apply_changes:
            self.stdout.write("DRY_RUN：未写库（加 --apply 应用）")

    @staticmethod
    def _same(archive: SpuVariantArchive, defaults: dict) -> bool:
        return (
            str(archive.source_spu_public_id) == str(defaults["source_spu_public_id"])
            and archive.axis_label == defaults["axis_label"]
            and archive.gallery_manifest == defaults["gallery_manifest"]
            and (archive.detail_spu_id or None)
            == (defaults["detail_spu"].pk if defaults["detail_spu"] is not None else None)
            and archive.rating_snapshot == defaults["rating_snapshot"]
            and archive.sold_snapshot == defaults["sold_snapshot"]
            and archive.title_snapshots == defaults["title_snapshots"]
            and archive.share_metadata == defaults["share_metadata"]
            and archive.share_metadata_reason == defaults["share_metadata_reason"]
        )
