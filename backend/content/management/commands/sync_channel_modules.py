"""Sync real-site channel floors into ``ChannelModule`` / ``ChannelModuleProduct``.

用法（先在仓库根目录跑 dry-run，确认无误再去掉 ``--dry-run``）：

    ./.venv/Scripts/python.exe backend/manage.py sync_channel_modules --dry-run
    ./.venv/Scripts/python.exe backend/manage.py sync_channel_modules
    ./.venv/Scripts/python.exe backend/manage.py sync_channel_modules \
        --source var/channel_styles_20261123/floors_live.json --channel UK-Mini-HP-Beauty

输入是另一个抓取任务产出的 ``var/channel_styles_20261123/floors_live.json``：
``[{channel_code, modules: [{title_en, title_zh, sort_order, items: [{skuId, spuId,
title, ...}]}]}]``。本命令只认 ``channel_code`` / ``title_en`` / ``title_zh`` /
``sort_order`` / ``items[].skuId`` / ``items[].spuId``，其余字段（价格、库存、
类目……）一律忽略，缺失字段都有兜底。

关键设计（改代码前先读）：

1. **去重键 = ``(title_en, 有序 skuId 序列)``**（同频道内）。真站 RSC payload
   会把同一楼层重复吐出来约 4 份，不按这个键去重会建出重复楼层；键里带有序
   sku 序列是故意的——两个楼层可以同名但商品不同（例如不同活动的
   "Best sellers"），不能只按标题合并。
2. **楼层匹配**：先按 ``(channel_code, sort_order)`` 找现有楼层（真站改版时
   同一位置的标题会换，位置才是稳定标识）；找不到再按
   ``(channel_code, title_en)`` 兜底（位置会变、标题不变）。命中就更新标题 /
   ``enabled=True`` / ``sort_order``；未命中才新建。
3. **只补不删**：本地有、本次 JSON 里没有的楼层只置 ``enabled=False``，
   **绝不删除** ``ChannelModule`` 行（删除会丢掉标题与配置，真站临时抽风
   就会误删）。楼层内的位次（``ChannelModuleProduct``）在商品序列变化时整层
   重建，这与 seed 命令一致，且在同一事务内完成。
4. **``--dry-run`` 零写操作**：不建楼层、不改字段、不改 ``enabled``、不删/不建
   商品行；每一处写操作前都有 ``dry_run`` 守卫（不是"先写后回滚"）。唯一的
   文件写入是缺失清单 ``missing_skus.json``——dry-run 也必须产出它，方便下一步
   补商品。
5. **可售 = 三条件**：``Offer.status=ACTIVE`` **且** ``Sku.status=ACTIVE``
   **且** ``Spu.status=ACTIVE``。只按 Offer 过滤会把 DRAFT SPU 也算可售，前台
   PDP 直接 404。解析到本地 SPU 但不可售的，不写进位次，按 ``not_sellable``
   进缺失清单。
6. **商品解析顺序**：先 ``SpuSourceIdentity(source_system, spuId)``，再
   ``SkuSourceIdentity(source_system, skuId) → sku.spu``（批次 H 的 PDP 导入把
   SKU 身份挂在变体上，只查 SPU 身份会漏）。JSON 缺 ``spuId`` 就只用 skuId。
   ``source_system`` 由 channel code 的词元推断（``uk``→``joybuy_uk``、
   ``nl``→``joybuy_nl``），推断不出来时先试这两个系统再退回"任意系统命中"。
   ``--source-system`` 可强制指定。同一楼层两个 SKU 解析到同一 SPU 时保序去重
   （唯一约束 ``(module, spu)``）。
7. **幂等**：同一份 JSON 连跑两次，第二次所有楼层都是「未变」、商品序列相同
   时不重建（保留 ``ChannelModuleProduct`` 原行），DB 行数不变。
8. **事务**：每个频道一个 ``transaction.atomic()``；单频道失败只打印原因并
   继续下一个频道。

报告：stdout 打每频道结构化日志（楼层 新增/更新/停用/未变、商品位次写入数、
缺失 SKU 数）+ 总表 + 缺失明细；同时写 ``var/channel_sync_20261123/
missing_skus.json``（``--dry-run`` 也写），字段含 ``skuId`` / ``spuId`` /
``title`` / ``channel_code`` / ``reason``（``spu_not_found`` 或
``not_sellable``）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from catalog.models import Sku, SkuSourceIdentity, Spu, SpuSourceIdentity
from content.models import ChannelModule, ChannelModuleProduct
from offers.models import Offer

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SOURCE = REPOSITORY_ROOT / "var" / "channel_styles_20261123" / "floors_live.json"
DEFAULT_MISSING_REPORT = REPOSITORY_ROOT / "var" / "channel_sync_20261123" / "missing_skus.json"
DEFAULT_SOURCE_SYSTEMS = ("joybuy_uk", "joybuy_nl")
#: channel code 词元 → 真站抓取源（UK 站与 NL 站的 id 可能撞号，先按站点找）。
CHANNEL_SYSTEM_TOKENS = {"uk": "joybuy_uk", "nl": "joybuy_nl"}
ID_CHUNK_SIZE = 500


@dataclass(frozen=True)
class FloorItem:
    sku_id: str
    spu_id: str
    title: str


@dataclass
class Floor:
    title_en: str
    title_zh: str
    sort_order: int
    items: list[FloorItem] = field(default_factory=list)


@dataclass
class PlannedFloor:
    """一个楼层解析后的落库计划（SPU 序列已按 JSON 顺序去重过滤）。"""

    floor: Floor
    resolved_items: list[tuple[FloorItem, int]] = field(default_factory=list)
    spu_ids: list[int] = field(default_factory=list)


def _text(value) -> str:
    """宽松转字符串：None → ""，折叠空白，容忍 int 型 id。"""

    if value is None:
        return ""
    return " ".join(str(value).split())


def _positive_int(value, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return number if number >= 0 else fallback


def _chunks(values: list, size: int = ID_CHUNK_SIZE):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def load_payload(path: Path) -> list[dict]:
    if not path.is_file():
        raise CommandError(f"Source payload not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CommandError(f"Source payload is not valid JSON: {path} ({exc})") from exc
    if isinstance(data, dict):
        # 容错：也接受 {"channels": [...]} 包装。
        data = data.get("channels", [])
    if not isinstance(data, list):
        raise CommandError(f"Source payload must be a JSON array of channels: {path}")
    return [entry for entry in data if isinstance(entry, dict)]


def normalize_channel(entry: dict) -> tuple[str, list[Floor], int]:
    """一个频道 payload → (channel_code, 去重后的楼层, 被丢弃的重复楼层数)。"""

    channel_code = _text(entry.get("channel_code"))
    raw_modules = entry.get("modules") or []
    if not isinstance(raw_modules, list):
        raw_modules = []
    floors: list[Floor] = []
    seen_keys: set[tuple[str, tuple[str, ...]]] = set()
    used_orders: set[int] = set()
    duplicates = 0
    for index, raw in enumerate(raw_modules):
        if not isinstance(raw, dict):
            continue
        title_en = _text(raw.get("title_en")) or _text(raw.get("title_zh"))
        title_en = title_en or f"Floor {index + 1}"
        items: list[FloorItem] = []
        for raw_item in raw.get("items") or []:
            if not isinstance(raw_item, dict):
                continue
            sku_id = _text(raw_item.get("skuId") or raw_item.get("sku_id"))
            if not sku_id:
                continue
            items.append(
                FloorItem(
                    sku_id=sku_id,
                    spu_id=_text(raw_item.get("spuId") or raw_item.get("spu_id")),
                    title=_text(raw_item.get("title")),
                )
            )
        dedupe_key = (title_en, tuple(item.sku_id for item in items))
        if dedupe_key in seen_keys:
            duplicates += 1
            continue
        seen_keys.add(dedupe_key)
        sort_order = _positive_int(raw.get("sort_order"), index)
        while sort_order in used_orders:
            # 同频道 payload 自带重复 sort_order 时顺延，避免 (channel, order) 撞唯一约束。
            sort_order += 1
        used_orders.add(sort_order)
        floors.append(
            Floor(
                title_en=title_en,
                title_zh=_text(raw.get("title_zh")),
                sort_order=sort_order,
                items=items,
            )
        )
    return channel_code, floors, duplicates


def preferred_source_systems(channel_code: str, override: str = "") -> tuple[str, ...]:
    preferred: list[str] = []
    if override:
        preferred.append(override)
    tokens = set(channel_code.lower().replace("_", "-").split("-"))
    for token, system in CHANNEL_SYSTEM_TOKENS.items():
        if token in tokens:
            preferred.append(system)
    preferred.extend(DEFAULT_SOURCE_SYSTEMS)
    deduped: list[str] = []
    for system in preferred:
        if system not in deduped:
            deduped.append(system)
    return tuple(deduped)


class SourceIdentityResolver:
    """(source_system, source_id) → 本地 SPU 的批量解析器（只读）。"""

    def __init__(self, spu_source_ids: set[str], sku_source_ids: set[str]):
        self.spu_by_key: dict[tuple[str, str], int] = {}
        for chunk in _chunks(sorted(spu_source_ids)):
            rows = SpuSourceIdentity.objects.filter(source_id__in=chunk).values_list(
                "source_system", "source_id", "spu_id"
            )
            for source_system, source_id, spu_id in rows:
                self.spu_by_key.setdefault((source_system, source_id), spu_id)
        self.sku_by_key: dict[tuple[str, str], int] = {}
        for chunk in _chunks(sorted(sku_source_ids)):
            rows = SkuSourceIdentity.objects.filter(source_id__in=chunk).values_list(
                "source_system", "source_id", "sku__spu_id"
            )
            for source_system, source_id, spu_id in rows:
                self.sku_by_key.setdefault((source_system, source_id), spu_id)
        self.spu_any: dict[str, int] = {}
        for (_system, source_id), spu_id in self.spu_by_key.items():
            self.spu_any.setdefault(source_id, spu_id)
        self.sku_any: dict[str, int] = {}
        for (_system, source_id), spu_id in self.sku_by_key.items():
            self.sku_any.setdefault(source_id, spu_id)

    def resolve(self, item: FloorItem, preferred: tuple[str, ...]) -> int | None:
        if item.spu_id:
            for source_system in preferred:
                spu_id = self.spu_by_key.get((source_system, item.spu_id))
                if spu_id is not None:
                    return spu_id
        for source_system in preferred:
            spu_id = self.sku_by_key.get((source_system, item.sku_id))
            if spu_id is not None:
                return spu_id
        # 兜底：channel code 推不出站点时，任意 source_system 命中即可。
        if item.spu_id:
            spu_id = self.spu_any.get(item.spu_id)
            if spu_id is not None:
                return spu_id
        return self.sku_any.get(item.sku_id)


def sellable_spu_ids(spu_ids: set[int]) -> set[int]:
    """可售三条件：Offer ACTIVE + Sku ACTIVE + Spu ACTIVE（缺一不可，前台才不 404）。"""

    result: set[int] = set()
    if not spu_ids:
        return result
    for chunk in _chunks(sorted(spu_ids)):
        result.update(
            Offer.objects.filter(
                status=Offer.Status.ACTIVE,
                sku__status=Sku.Status.ACTIVE,
                sku__spu__status=Spu.Status.ACTIVE,
                sku__spu_id__in=chunk,
            ).values_list("sku__spu_id", flat=True)
        )
    return result


def plan_floors(
    channel_code: str,
    floors: list[Floor],
    resolver: SourceIdentityResolver,
    source_system: str,
    missing: list[dict],
) -> list[PlannedFloor]:
    """按 JSON 顺序解析 SPU；解析不到的进缺失清单（不静默丢弃）。"""

    preferred = preferred_source_systems(channel_code, source_system)
    planned: list[PlannedFloor] = []
    for floor in floors:
        floor_plan = PlannedFloor(floor=floor)
        planned.append(floor_plan)
        for item in floor.items:
            spu_id = resolver.resolve(item, preferred)
            if spu_id is None:
                missing.append(
                    {
                        "skuId": item.sku_id,
                        "spuId": item.spu_id,
                        "title": item.title,
                        "channel_code": channel_code,
                        "reason": "spu_not_found",
                    }
                )
                continue
            floor_plan.resolved_items.append((item, spu_id))
    return planned


def apply_sellable_filter(
    channel_code: str,
    planned: list[PlannedFloor],
    sellable: set[int],
    missing: list[dict],
) -> None:
    """把不可售 SPU 从位次里剔除并记入缺失清单；同楼层重复 SPU 保序去重。"""

    for floor_plan in planned:
        kept: list[int] = []
        seen: set[int] = set()
        for item, spu_id in floor_plan.resolved_items:
            if spu_id not in sellable:
                missing.append(
                    {
                        "skuId": item.sku_id,
                        "spuId": item.spu_id,
                        "title": item.title,
                        "channel_code": channel_code,
                        "reason": "not_sellable",
                    }
                )
                continue
            if spu_id in seen:
                continue
            seen.add(spu_id)
            kept.append(spu_id)
        floor_plan.spu_ids = kept


def sync_channel(channel_code: str, planned: list[PlannedFloor], *, dry_run: bool) -> dict:
    """单个频道落库（一个事务）；dry_run 时所有写操作都被跳过。"""

    stats = {
        "modules_created": 0,
        "modules_updated": 0,
        "modules_unchanged": 0,
        "modules_disabled": 0,
        "modules_renumbered": 0,
        "products_written": 0,
        "products_planned": 0,
    }
    with transaction.atomic():
        existing = list(
            ChannelModule.objects.filter(channel_code=channel_code).order_by("sort_order", "pk")
        )
        by_order: dict[int, ChannelModule] = {}
        for module in existing:
            by_order.setdefault(module.sort_order, module)
        by_title: dict[str, ChannelModule] = {}
        for module in existing:
            by_title.setdefault(module.title_en, module)

        claimed: set[int] = set()
        matches: list[tuple[PlannedFloor, ChannelModule | None]] = []
        for floor_plan in planned:
            module = by_order.get(floor_plan.floor.sort_order)
            if module is not None and module.pk in claimed:
                module = None
            if module is None:
                candidate = by_title.get(floor_plan.floor.title_en)
                if candidate is not None and candidate.pk not in claimed:
                    module = candidate
            if module is not None:
                claimed.add(module.pk)
            matches.append((floor_plan, module))

        # 目标 sort_order：JSON 的位置优先；被"本轮不处理的本地楼层"占住时顺延。
        taken_orders = {module.sort_order for module in existing if module.pk not in claimed}
        final_orders: dict[int, int] = {}
        for index, (floor_plan, module) in enumerate(matches):
            order = floor_plan.floor.sort_order
            while order in taken_orders:
                order += 1
            taken_orders.add(order)
            if module is not None and module.sort_order != order:
                stats["modules_renumbered"] += 1
            final_orders[index] = order

        # 先把要换位的楼层挪到临时高位，避免 (channel_code, sort_order) 唯一约束
        # 在"两楼层互换位置"时半路冲突。
        if not dry_run:
            temp_base = (
                max(
                    [module.sort_order for module in existing]
                    + [floor_plan.floor.sort_order for floor_plan, _ in matches]
                    + [0]
                )
                + 1000
            )
            offset = 0
            for index, (_floor_plan, module) in enumerate(matches):
                if module is None or module.sort_order == final_orders[index]:
                    continue
                module.sort_order = temp_base + offset
                offset += 1
                module.save(update_fields=["sort_order", "updated_at"])

        for index, (floor_plan, module) in enumerate(matches):
            floor = floor_plan.floor
            order = final_orders[index]
            spu_ids = floor_plan.spu_ids
            if module is None:
                stats["modules_created"] += 1
                items_changed = bool(spu_ids)
                if not dry_run:
                    module = ChannelModule.objects.create(
                        channel_code=channel_code,
                        title_en=floor.title_en,
                        title_zh=floor.title_zh,
                        sort_order=order,
                        enabled=True,
                    )
            else:
                field_changes: list[str] = []
                if module.title_en != floor.title_en:
                    field_changes.append("title_en")
                if module.title_zh != floor.title_zh:
                    field_changes.append("title_zh")
                if not module.enabled:
                    field_changes.append("enabled")
                if module.sort_order != order:
                    field_changes.append("sort_order")
                existing_ids = list(
                    module.items.order_by("sort_order", "pk").values_list("spu_id", flat=True)
                )
                items_changed = existing_ids != spu_ids
                if not field_changes and not items_changed:
                    stats["modules_unchanged"] += 1
                else:
                    stats["modules_updated"] += 1
                    if not dry_run and field_changes:
                        module.title_en = floor.title_en
                        module.title_zh = floor.title_zh
                        module.enabled = True
                        module.sort_order = order
                        module.save(
                            update_fields=[
                                "title_en",
                                "title_zh",
                                "enabled",
                                "sort_order",
                                "updated_at",
                            ]
                        )
            if not items_changed:
                continue
            if module is None or dry_run:
                # 新建楼层（dry-run 下不存在）或 dry-run 下的既有楼层：只记计划。
                stats["products_planned"] += len(spu_ids)
                continue
            module.items.all().delete()
            if spu_ids:
                ChannelModuleProduct.objects.bulk_create(
                    [
                        ChannelModuleProduct(module=module, spu_id=spu_id, sort_order=position)
                        for position, spu_id in enumerate(spu_ids)
                    ]
                )
            stats["products_written"] += len(spu_ids)

        # 只补不删：本地多余楼层停用，绝不删除。
        for module in existing:
            if module.pk in claimed:
                continue
            if not module.enabled:
                stats["modules_unchanged"] += 1
                continue
            stats["modules_disabled"] += 1
            if not dry_run:
                module.enabled = False
                module.save(update_fields=["enabled", "updated_at"])

    return stats


class Command(BaseCommand):
    help = "Sync real-site channel floors into ChannelModule/ChannelModuleProduct (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default=str(DEFAULT_SOURCE),
            help=f"floors_live.json path (default: {DEFAULT_SOURCE})",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report every planned change without writing to the database.",
        )
        parser.add_argument(
            "--channel",
            action="append",
            default=[],
            metavar="CODE",
            help="Only sync this channel_code; repeatable.",
        )
        parser.add_argument(
            "--source-system",
            default="",
            help="Force the source system for identity lookup (default: infer from channel code).",
        )
        parser.add_argument(
            "--missing-report",
            default=str(DEFAULT_MISSING_REPORT),
            help=f"Where to write the missing-SKU report (default: {DEFAULT_MISSING_REPORT})",
        )

    def handle(self, *args, **options):
        source_path = Path(options["source"])
        missing_path = Path(options["missing_report"])
        dry_run = options["dry_run"]
        selected = set(options["channel"] or [])
        source_system = options["source_system"]

        payload = load_payload(source_path)
        channels: list[tuple[str, list[Floor]]] = []
        duplicates_total = 0
        for entry in payload:
            channel_code, floors, duplicates = normalize_channel(entry)
            if not channel_code:
                self._write("WARNING: payload entry without channel_code skipped.")
                continue
            if selected and channel_code not in selected:
                continue
            channels.append((channel_code, floors))
            duplicates_total += duplicates

        if selected:
            known = {channel_code for channel_code, _ in channels}
            for channel_code in sorted(selected - known):
                self._write(f"WARNING: channel {channel_code} not present in payload.")

        if not channels:
            raise CommandError(f"No channels to sync from {source_path}.")

        # 先做纯读解析，再统一查可售，最后逐频道写库（每频道一个事务）。
        spu_source_ids: set[str] = set()
        sku_source_ids: set[str] = set()
        for _channel_code, floors in channels:
            for floor in floors:
                for item in floor.items:
                    if item.spu_id:
                        spu_source_ids.add(item.spu_id)
                    sku_source_ids.add(item.sku_id)
        resolver = SourceIdentityResolver(spu_source_ids, sku_source_ids)

        missing: list[dict] = []
        plans: dict[str, list[PlannedFloor]] = {}
        resolved_spu_ids: set[int] = set()
        for channel_code, floors in channels:
            planned = plan_floors(channel_code, floors, resolver, source_system, missing)
            plans[channel_code] = planned
            for floor_plan in planned:
                for _item, spu_id in floor_plan.resolved_items:
                    resolved_spu_ids.add(spu_id)

        sellable = sellable_spu_ids(resolved_spu_ids)
        for channel_code, planned in plans.items():
            apply_sellable_filter(channel_code, planned, sellable, missing)

        totals = {
            "modules_created": 0,
            "modules_updated": 0,
            "modules_unchanged": 0,
            "modules_disabled": 0,
            "modules_renumbered": 0,
            "products_written": 0,
            "products_planned": 0,
        }
        summaries: list[dict] = []
        failures: list[dict] = []
        for channel_code, planned in plans.items():
            try:
                stats = sync_channel(channel_code, planned, dry_run=dry_run)
            except Exception as exc:  # noqa: BLE001 - 单频道失败不能拖垮整批
                failures.append(
                    {"channel_code": channel_code, "error": f"{type(exc).__name__}: {exc}"}
                )
                self._write(f"[{channel_code}] FAILED: {type(exc).__name__}: {exc}")
                continue
            channel_missing = [entry for entry in missing if entry["channel_code"] == channel_code]
            summaries.append(
                {
                    "channel_code": channel_code,
                    "floors": len(planned),
                    "missing_skus": len(channel_missing),
                    **stats,
                }
            )
            for key in totals:
                totals[key] += stats[key]
            if dry_run:
                self._write(
                    f"[{channel_code}] floors={len(planned)} "
                    f"new={stats['modules_created']} updated={stats['modules_updated']} "
                    f"unchanged={stats['modules_unchanged']} disabled={stats['modules_disabled']} "
                    f"renumbered={stats['modules_renumbered']} | "
                    f"products planned={stats['products_planned']} | "
                    f"missing skus={len(channel_missing)}"
                )
            else:
                self._write(
                    f"[{channel_code}] floors={len(planned)} "
                    f"new={stats['modules_created']} updated={stats['modules_updated']} "
                    f"unchanged={stats['modules_unchanged']} disabled={stats['modules_disabled']} "
                    f"renumbered={stats['modules_renumbered']} | "
                    f"products written={stats['products_written']} | "
                    f"missing skus={len(channel_missing)}"
                )

        mode = "DRY RUN" if dry_run else "APPLIED"
        self._write(
            f"TOTAL ({mode}) channels={len(summaries)} "
            f"new={totals['modules_created']} updated={totals['modules_updated']} "
            f"unchanged={totals['modules_unchanged']} disabled={totals['modules_disabled']} "
            f"renumbered={totals['modules_renumbered']} | "
            f"products written={totals['products_written']} "
            f"planned={totals['products_planned']} | "
            f"duplicate floors dropped={duplicates_total} | "
            f"missing skus={len(missing)}"
        )
        if failures:
            self._write(
                "FAILED channels: "
                + ", ".join(
                    f"{failure['channel_code']} ({failure['error']})" for failure in failures
                )
            )

        if missing:
            self._write("Missing SKU details (skuId | channel | reason | title):")
            for entry in missing:
                title = entry["title"][:60]
                self._write(
                    f"  {entry['skuId']} | {entry['channel_code']} | {entry['reason']} | {title}"
                )

        report = {
            "generated_at": timezone.now().isoformat(),
            "source": str(source_path),
            "dry_run": dry_run,
            "channels": summaries,
            "failures": failures,
            "total_missing": len(missing),
            "missing": missing,
        }
        missing_path.parent.mkdir(parents=True, exist_ok=True)
        missing_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        self._write(f"Missing report written: {missing_path}")

    def _write(self, message: str) -> None:
        # Windows 控制台 GBK 会对中文标题抛 UnicodeEncodeError（HANDOFF 坑 ⑤）。
        try:
            self.stdout.write(message)
        except UnicodeEncodeError:
            self.stdout.write(message.encode("ascii", "replace").decode("ascii"))
