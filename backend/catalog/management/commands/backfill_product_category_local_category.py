"""Backfill ``ProductCategory.local_category`` from the 2026-11-23 mapping plan.

Background: the PDP breadcrumb used to resolve the product's source category
by *name only*, so 「配件」 (Electronics > Accessories, source id 1801) landed on
``fashion-accessories`` (Clothing & Accessories > Accessories, 0 products)
instead of ``electronics-accessories``.  The fix reads the mapping stored on
``ProductCategory.local_category``; before this command that column was
0/242 filled.  Analysis: ``var/category_misclass_20261123/findings.md`` §8.3.

Scope (user decision Q9/Q12): fill **206** rows — 67 high-confidence
(root + exact child name) plus 139 「归父级」 (the local tree is coarser than
the source tree) — and leave **34** rows unfilled (22 word-subset guesses,
1 cross-root candidate, 11 with no local counterpart: Automobiles /
Motorcycle).  Those 34 are written to ``review_needed.csv`` for humans.

The 2 orphan rows under ``catalog=joybuy`` (4909 / 4945, 0 SPUs) are out of
scope: only the ``joybuy_uk`` catalog is touched.

Idempotent: rows already pointing at the planned category are counted as
``unchanged``; rows pointing at a *different* category are treated as manual
work and skipped (``conflict``), never overwritten.

DRY_RUN is the default (prints the plan, writes only ``review_needed.csv``);
``--apply`` writes the DB and dumps ``backup_pc_mapping.json`` first.
"""

import csv
import json
from pathlib import Path

from catalog.models import LocalCategory, ProductCategory
from catalog.product_category_mapping_data import (
    LOCAL_CATEGORY_BY_SOURCE_ID,
    REVIEW_NOTES_BY_SOURCE_ID,
    REVIEW_SUGGESTED_SLUG_BY_SOURCE_ID,
)
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

#: 只有这个 catalog 的 source_id 与映射数据对应（joybuy 下 2 行是孤儿）。
SOURCE_CATALOG = "joybuy_uk"
DEFAULT_OUTPUT_DIR = "var/category_misclass_20261123"
BATCH_SIZE = 200


class Command(BaseCommand):
    help = (
        "Backfill ProductCategory.local_category from the 2026-11-23 mapping "
        "plan (206 rows; DRY_RUN by default, --apply to write)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="写库（缺省 DRY_RUN：只打印计划，除 review_needed.csv 外不落盘）。",
        )
        parser.add_argument(
            "--output-dir",
            default=DEFAULT_OUTPUT_DIR,
            help=f"备份/清单输出目录（相对仓库根，默认 {DEFAULT_OUTPUT_DIR}）。",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        output_dir = Path(options["output_dir"])
        if not output_dir.is_absolute():
            output_dir = Path(settings.REPOSITORY_ROOT) / output_dir

        local_by_slug = {category.slug: category for category in LocalCategory.objects.all()}

        rows = list(
            ProductCategory.objects.filter(catalog__source_system=SOURCE_CATALOG)
            .select_related("parent", "local_category")
            .order_by("path")
        )
        if not rows:
            raise CommandError(f"未找到 catalog={SOURCE_CATALOG} 的 ProductCategory。")

        backup = []
        to_fill = []
        unchanged = 0
        conflicts = []
        unplanned = []
        missing_targets = []
        for row in rows:
            before = row.local_category.slug if row.local_category_id else None
            backup.append(
                {
                    "id": row.pk,
                    "source_id": row.source_id,
                    "name": row.name,
                    "depth": row.depth,
                    "path": row.path,
                    "local_category_slug_before": before,
                }
            )
            slug = LOCAL_CATEGORY_BY_SOURCE_ID.get(row.source_id)
            if slug is None:
                if row.source_id not in REVIEW_NOTES_BY_SOURCE_ID:
                    unplanned.append(row.source_id)
                continue
            if before == slug:
                unchanged += 1
                continue
            if before is not None:
                conflicts.append((row, before, slug))
                continue
            target = local_by_slug.get(slug)
            if target is None:
                # 只有「当前存在的商品类目行」需要目标本地类目存在；
                # 缺了就不写，避免半套映射。
                missing_targets.append(f"{row.path} {row.name} -> {slug}")
                continue
            to_fill.append((row, target))

        if missing_targets:
            raise CommandError(
                f"映射目标本地类目缺失（{len(missing_targets)} 条）："
                + "；".join(missing_targets[:10])
            )

        review_rows = [row for row in rows if row.source_id in REVIEW_NOTES_BY_SOURCE_ID]
        review_path = output_dir / "review_needed.csv"
        output_dir.mkdir(parents=True, exist_ok=True)
        self._write_review_csv(review_path, review_rows, rows)

        self.stdout.write(
            f"scope: catalog={SOURCE_CATALOG} rows={len(rows)} "
            f"planned={len(LOCAL_CATEGORY_BY_SOURCE_ID)} review={len(review_rows)}"
        )
        self.stdout.write(
            f"to_fill={len(to_fill)} unchanged={unchanged} "
            f"conflict={len(conflicts)} unplanned={len(unplanned)}"
        )
        if unplanned:
            self.stdout.write(
                self.style.WARNING(
                    f"未在映射也不在待确认清单里的 source_id：{', '.join(unplanned)}"
                )
            )
        for row, before, slug in conflicts[:20]:
            self.stdout.write(
                self.style.WARNING(
                    f"conflict {row.path} {row.name}: {before} -> {slug}（保留现值）"
                )
            )
        if len(conflicts) > 20:
            self.stdout.write(f"... 其余 {len(conflicts) - 20} 条 conflict 省略")
        for row, target in to_fill[:10]:
            self.stdout.write(f"  {row.path} {row.name} -> {target.slug}")
        if len(to_fill) > 10:
            self.stdout.write(f"  ... 其余 {len(to_fill) - 10} 条省略")
        self.stdout.write(f"review_needed.csv: {len(review_rows)} 行 -> {review_path}")

        if not apply:
            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN：未写库。将填 {len(to_fill)} 行；"
                    "写入请加 --apply（会先导出 backup_pc_mapping.json）。"
                )
            )
            return

        backup_path = output_dir / "backup_pc_mapping.json"
        backup_path.write_text(
            json.dumps(
                {
                    "created_at": timezone.now().isoformat(),
                    "catalog": SOURCE_CATALOG,
                    "rows": backup,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self.stdout.write(f"backup_pc_mapping.json: {len(backup)} 行 -> {backup_path}")

        now = timezone.now()
        with transaction.atomic():
            for row, target in to_fill:
                row.local_category = target
                row.updated_at = now
            ProductCategory.objects.bulk_update(
                [row for row, _ in to_fill],
                ["local_category", "updated_at"],
                batch_size=BATCH_SIZE,
            )

        filled = ProductCategory.objects.filter(
            catalog__source_system=SOURCE_CATALOG, local_category__isnull=False
        ).count()
        total = ProductCategory.objects.filter(catalog__source_system=SOURCE_CATALOG).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"backfilled={len(to_fill)} unchanged={unchanged} "
                f"conflict={len(conflicts)}；catalog={SOURCE_CATALOG} "
                f"filled={filled}/{total}（待确认 {len(review_rows)} 行未填）"
            )
        )

    def _write_review_csv(self, path: Path, review_rows, all_rows):
        """输出 34 条待人工确认清单（含当前挂的商品数，便于排优先级）。"""

        spu_counts = self._spu_counts()
        by_pk = {row.pk: row for row in all_rows}
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "source_id",
                    "name",
                    "path",
                    "parent_name",
                    "suggested_local_slug",
                    "reason",
                    "spu_count",
                ]
            )
            for row in sorted(review_rows, key=lambda item: (item.path, item.pk)):
                parent = by_pk.get(row.parent_id)
                writer.writerow(
                    [
                        row.source_id,
                        row.name,
                        row.path,
                        parent.name if parent else "",
                        REVIEW_SUGGESTED_SLUG_BY_SOURCE_ID.get(row.source_id) or "",
                        REVIEW_NOTES_BY_SOURCE_ID.get(row.source_id, ""),
                        spu_counts.get(row.pk, 0),
                    ]
                )

    def _spu_counts(self) -> dict:
        from catalog.models import Spu
        from django.db.models import Count

        return dict(
            Spu.objects.filter(product_category__isnull=False)
            .values_list("product_category")
            .annotate(total=Count("pk"))
        )
