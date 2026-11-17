"""用 Joybuy 频道菜单对齐本地 11 个一级类目的二级类目（2026-11-11 一对一口径）。

读取已发布（PUBLISHED）的 Joybuy 类目树，按 ``joybuy_menu_crosswalk`` 的
口径做三件事：

1. **一对一**：每个 Joybuy 二级 → 恰好一个本地二级（改名复用基座 slug 或
   新建），二级集合与 Joybuy 一模一样，没有多对一桶；
2. **名称**：本地二级显示名按 Joybuy 原名更新（跨频道重名二级按
   ``NAME_OVERRIDES`` 消歧）；
3. **映射**：为每个 Joybuy 菜单节点写 ``CategoryMapping``（一对一），
   以后任务/商品来源类目可以解析到本地类目。

命令幂等：重复执行只会更新名称/排序/映射，不会重复建节点。汽车类保持
未映射，报告里会单独列出。被拆开的旧桶与不在 Joybuy 菜单里的基座二级
（``RETIRED_LOCAL_SLUGS``）在**无商品/无子类目/无商品类目/无搜索文档**
引用时删除，否则保留并警告，绝不级联删数据。

用法::

    python backend/manage.py sync_local_categories_from_joybuy --dry-run \
        --report var/category-sync-report.json
    python backend/manage.py sync_local_categories_from_joybuy
"""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.joybuy_menu_crosswalk import (
    ACTIVITY_LOCAL_SLUGS,
    CHANNEL_PARENT,
    RETIRED_LOCAL_SLUGS,
    resolve_node,
)
from catalog.models import (
    CategoryMapping,
    LocalCategory,
    SourceCategoryTreeVersion,
)
from catalog.services import create_local_category

SOURCE_SYSTEM = "joybuy_uk"
CONFIDENCE = Decimal("1.0000")


class Command(BaseCommand):
    help = "按 Joybuy 菜单树一对一补齐 11 个一级类目的二级类目并建立 CategoryMapping。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--tree-version",
            default="",
            help="指定 SourceCategoryTreeVersion.version_key；默认取最新 PUBLISHED。",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="只输出将要做的变更，不写数据库。",
        )
        parser.add_argument(
            "--report",
            default="",
            help="把完整映射报告写到指定 JSON 文件。",
        )

    def handle(self, *args, **options):
        version = self._tree_version(options["tree_version"])
        snapshots = list(
            version.snapshots.select_related("category", "parent").order_by(
                "depth", "sort_order", "pk"
            )
        )
        rows = self._resolve_rows(snapshots)
        dry_run = bool(options["dry_run"])

        with transaction.atomic():
            summary = self._apply(rows, dry_run=dry_run)
            summary["pruned"] = self._prune_retired_categories(dry_run=dry_run)

        report = {
            "tree_version": version.version_key,
            "source_system": SOURCE_SYSTEM,
            "generated_at": datetime.now(UTC).isoformat(),
            "dry_run": dry_run,
            "summary": summary,
            "rows": rows,
        }
        report_path = options["report"].strip()
        if report_path:
            path = Path(report_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            self.stdout.write(f"完整报告已写入：{path}")

        self._print_summary(summary)
        self._print_unmapped(rows)

    # -- resolve --------------------------------------------------------

    def _tree_version(self, version_key: str) -> SourceCategoryTreeVersion:
        queryset = SourceCategoryTreeVersion.objects.filter(catalog__source_system=SOURCE_SYSTEM)
        if version_key:
            version = queryset.filter(version_key=version_key).first()
        else:
            version = queryset.filter(status="PUBLISHED").order_by("-published_at", "-pk").first()
        if version is None:
            raise CommandError(
                f"找不到 {SOURCE_SYSTEM} 的类目树版本"
                + (f" {version_key}" if version_key else "（无 PUBLISHED 版本）")
            )
        return version

    def _resolve_rows(self, snapshots) -> list[dict]:
        channels = {
            snapshot.category.source_id: snapshot for snapshot in snapshots if snapshot.depth == 0
        }
        local_parent_slugs = set(
            LocalCategory.objects.filter(depth=0).values_list("slug", flat=True)
        )
        rows = []
        for snapshot in snapshots:
            if snapshot.depth != 1:
                continue
            channel_id = snapshot.parent.category.source_id if snapshot.parent is not None else ""
            channel = channels.get(channel_id)
            mapping = resolve_node(
                source_id=snapshot.category.source_id,
                channel_id=channel_id,
                name_zh=snapshot.name_zh,
                name_en=snapshot.name,
                sort_order=snapshot.sort_order,
            )
            parent_exists = bool(mapping and mapping["parent_slug"] in local_parent_slugs)
            rows.append(
                {
                    "source_id": snapshot.category.source_id,
                    "source_name_zh": snapshot.name_zh,
                    "source_name_en": snapshot.name,
                    "channel_id": channel_id,
                    "channel_name_zh": channel.name_zh if channel else "",
                    "parent_slug": mapping["parent_slug"] if mapping else "",
                    "child_slug": mapping["child_slug"] if mapping else "",
                    "action": mapping["action"] if mapping else "unmapped",
                    "name_zh": mapping["name_zh"] if mapping else "",
                    "name_en": mapping["name_en"] if mapping else "",
                    "sort_order": mapping["sort_order"] if mapping else 0,
                    "parent_exists": parent_exists,
                    "status": "unmapped" if mapping is None else "planned",
                }
            )
        return rows

    # -- apply ----------------------------------------------------------

    def _apply(self, rows: list[dict], *, dry_run: bool) -> dict:
        local_parents = {
            category.slug: category for category in LocalCategory.objects.filter(depth=0)
        }
        summary = {
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "mappings": 0,
            "channel_mappings": 0,
            "activity": 0,
            "unmapped": 0,
            "errors": 0,
            "pruned": [],
        }

        for row in rows:
            if row["action"] == "activity":
                # 活动商品不是类目：不建本地二级，导入时写 Spu.is_activity。
                row["status"] = "activity"
                summary["activity"] += 1
                continue
            if not row["parent_slug"]:
                summary["unmapped"] += 1
                continue
            parent = local_parents.get(row["parent_slug"])
            if parent is None:
                row["status"] = "error"
                row["error"] = f"本地一级类目不存在：{row['parent_slug']}"
                summary["errors"] += 1
                continue

            child = LocalCategory.objects.filter(slug=row["child_slug"]).first()
            if child is not None and child.parent_id != parent.pk:
                row["status"] = "error"
                row["error"] = (
                    f"slug {row['child_slug']} 已挂在 "
                    f"{child.parent.slug if child.parent else '根'} 下"
                )
                summary["errors"] += 1
                continue

            values = {
                "name": row["name_en"] or row["name_zh"],
                "name_en": row["name_en"],
                "name_zh": row["name_zh"],
                "sort_order": row["sort_order"],
                "status": LocalCategory.Status.ACTIVE,
            }
            if child is None:
                row["status"] = "would_create" if dry_run else "created"
                summary["created"] += 1
                if not dry_run:
                    child = create_local_category(
                        name=values["name"],
                        slug=row["child_slug"],
                        parent=parent,
                        sort_order=values["sort_order"],
                    )
                    child.name_en = values["name_en"]
                    child.name_zh = values["name_zh"]
                    child.save(update_fields=["name_en", "name_zh", "updated_at"])
            else:
                changed = any(getattr(child, field) != value for field, value in values.items())
                if changed:
                    summary["updated"] += 1
                    row["status"] = "would_update" if dry_run else "updated"
                    if not dry_run:
                        for field, value in values.items():
                            setattr(child, field, value)
                        child.save(update_fields=[*values.keys(), "updated_at"])
                else:
                    summary["unchanged"] += 1
                    row["status"] = "unchanged"

            summary["mappings"] += 1
            if not dry_run and child is not None:
                self._upsert_mapping(row["source_id"], child)

        # 频道（一级）也映射到本地一级：任务选频道时可解析到本地父类目。
        channels = {row["channel_id"] for row in rows if row["channel_id"]}
        for channel_id in channels:
            parent_slug = CHANNEL_PARENT.get(channel_id)
            if not parent_slug:
                continue
            parent = local_parents.get(parent_slug)
            if parent is None:
                continue
            if not dry_run:
                self._upsert_mapping(channel_id, parent)
            summary["channel_mappings"] += 1

        return summary

    def _prune_retired_categories(self, *, dry_run: bool) -> list[dict]:
        """清理退役本地二级：被拆开的旧桶 + 历史「活动商品」类目。

        只有在没有子类目、商品、商品类目引用、搜索文档引用时才删除
        （先删残留 CategoryMapping）；否则保留并在报告里提示先迁移数据，
        绝不级联删数据。
        """

        pruned = []
        for slug in sorted(ACTIVITY_LOCAL_SLUGS | RETIRED_LOCAL_SLUGS):
            category = LocalCategory.objects.filter(slug=slug).first()
            if category is None:
                continue
            reasons = []
            if category.children.exists():
                reasons.append("有子类目")
            if category.spus.exists():
                reasons.append("有商品")
            if category.product_categories.exists():
                reasons.append("被商品类目引用")
            if category.search_documents.exists():
                reasons.append("被搜索文档引用")
            if reasons:
                pruned.append({"slug": slug, "status": "kept", "reason": "、".join(reasons)})
                continue
            if not dry_run:
                CategoryMapping.objects.filter(local_category=category).delete()
                category.delete()
            pruned.append({"slug": slug, "status": "would_remove" if dry_run else "removed"})
        return pruned

    def _upsert_mapping(self, source_id: str, local_category: LocalCategory) -> None:
        from catalog.models import SourceCategory

        source_category = SourceCategory.objects.filter(
            catalog__source_system=SOURCE_SYSTEM, source_id=source_id
        ).first()
        if source_category is None:
            return
        CategoryMapping.objects.filter(source_category=source_category).exclude(
            local_category=local_category
        ).delete()
        CategoryMapping.objects.update_or_create(
            local_category=local_category,
            source_category=source_category,
            defaults={"is_primary": True, "confidence": CONFIDENCE},
        )

    # -- output ---------------------------------------------------------

    def _print_summary(self, summary: dict) -> None:
        pruned = summary.get("pruned") or []
        removed = [item for item in pruned if item["status"] not in {"kept"}]
        kept = [item for item in pruned if item["status"] == "kept"]
        self.stdout.write(
            "同步完成："
            f"新建 {summary['created']}，"
            f"更新 {summary['updated']}，"
            f"未变化 {summary['unchanged']}，"
            f"二级映射 {summary['mappings']}，"
            f"频道映射 {summary['channel_mappings']}，"
            f"活动商品节点 {summary['activity']}，"
            f"清理退役/活动类目 {len(removed)}，"
            f"未映射 {summary['unmapped']}，"
            f"错误 {summary['errors']}"
        )
        for item in kept:
            self.stdout.write(
                f"  保留待迁移类目 {item['slug']}：{item['reason']}，先迁移数据再重跑"
            )

    def _print_unmapped(self, rows: list[dict]) -> None:
        unmapped = [row for row in rows if row["status"] == "unmapped"]
        if not unmapped:
            return
        self.stdout.write("未映射节点：")
        for row in unmapped:
            self.stdout.write(
                f"  {row['source_id']} {row['source_name_zh'] or row['source_name_en']}"
            )
