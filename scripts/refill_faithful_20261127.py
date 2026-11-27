"""缺口回填（2026-11-27 用户拍板口径）。

审计结论：活动页楼层缺口 613 件里，只有 1 件是真正没入库的；其余是
「真站该层本来就少」和「建页时页内去重把跨楼层重复商品挤掉了」。

用户决策：
1. 真站 DOM 实锤确认同一商品会跨楼层重复展示 → 仅对 5 个验证过的
   保健品「Discover our range」页放开跨层重复（同层内仍按 (spu, sku) 去重），
   楼层商品严格按真站清单顺序 = 忠实复刻，不做关键词补位。
2. 真站本来就少的层 → 保持实有数量（本脚本不补位）。
3. INACTIVE 商品（9 件，食品下架批次误伤）→ 按豁免口径恢复：
   SPU/SKU/Offer → ACTIVE、removed_by_platform=False，**不重建搜索文档**
   （仅活动页可见，搜索/分类页仍看不到）。
"""

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from catalog.models import Sku, SkuSourceIdentity, Spu, SpuSourceIdentity  # noqa: E402
from content.models import ActivityPage, ActivitySectionProduct  # noqa: E402
from crawler_control.models import CrawlPageManifest  # noqa: E402
from offers.models import Offer  # noqa: E402

FLOOR_CAP = 25
SOURCE_SYSTEM = "joybuy_uk"

# 真站 DOM 实锤跨楼层重复的 5 个页面（全部楼层重建）
REBUILD_PAGES = [
    "2dawKz7FDU6o", "31CyuPpBx7L9", "3sQw3r9uY6MZ", "uFx9zbR4hmgR", "uXqcuMAJBtVC",
]
# 首批页 254vg 只重填灯串层（等 job#384 重跑导入缺的那 1 件后执行；先按现有白名单重建）
SINGLE_FLOOR = {"254vgVWftm": 3}

restored = []


def restore_inactive(spu_pk: int) -> bool:
    """豁免口径恢复：不动搜索文档。返回是否发生恢复。"""

    spu = Spu.objects.filter(pk=spu_pk).first()
    if spu is None or spu.status == "ACTIVE":
        return False
    spu.status = Spu.Status.ACTIVE
    spu.save(update_fields=["status", "updated_at"])
    Sku.objects.filter(spu=spu).exclude(status="ACTIVE").update(status="ACTIVE")
    Offer.objects.filter(sku__spu=spu).exclude(status="ACTIVE").update(
        status="ACTIVE", removed_by_platform=False
    )
    restored.append((spu.pk, spu.local_category_id))
    return True


def sid(url: str) -> str:
    return url.split("/dp/")[-1].split("?")[0].split("/")[-1]


def manifest_for(ext: str):
    return CrawlPageManifest.objects.filter(page_url__icontains=ext).order_by("pk").last()


def rebuild(page_short: str, only_floor: int | None = None) -> None:
    page = ActivityPage.objects.filter(external_id__startswith=page_short).first()
    if page is None:
        print(f"!! page not found: {page_short}")
        return
    m = manifest_for(page.external_id)
    if m is None:
        print(f"!! manifest not found: {page_short}")
        return
    blocks = [b for b in (m.data.get("blocks") or []) if b.get("type") == "floor"]
    secs = list(page.sections.filter(kind="PRODUCTS").order_by("sort_order"))
    if len(blocks) != len(secs):
        print(f"!! {page_short} 块/楼层数不一致 blocks={len(blocks)} secs={len(secs)}，跳过")
        return

    all_ids = [sid(p["url"]) for b in blocks for p in (b.get("products") or [])]
    spu_map = dict(
        SpuSourceIdentity.objects.filter(source_system=SOURCE_SYSTEM, source_id__in=all_ids)
        .values_list("source_id", "spu_id")
    )
    sku_map: dict[str, tuple[int, int]] = {}
    for row in SkuSourceIdentity.objects.filter(
        source_system=SOURCE_SYSTEM,
        source_id__in=[x for x in all_ids if x not in spu_map],
    ).select_related("sku"):
        sku_map.setdefault(row.source_id, (row.sku.spu_id, row.sku_id))

    print(f"\n== {page.external_id[:10]} {page.title[:26]!r}")
    for idx, (b, sec) in enumerate(zip(blocks, secs), start=1):
        if only_floor is not None and idx != only_floor:
            continue
        before = sec.items.count()
        picked: list[tuple[int, int | None]] = []
        seen: set[tuple[int, int | None]] = set()
        for p in b.get("products") or []:
            x = sid(p["url"])
            spu_pk = spu_map.get(x)
            sku_pk = None
            if spu_pk is None:
                pair = sku_map.get(x)
                if pair is None:
                    continue
                spu_pk, sku_pk = pair
            restore_inactive(spu_pk)
            key = (spu_pk, sku_pk)
            if key in seen or len(picked) >= FLOOR_CAP:
                continue
            seen.add(key)
            picked.append(key)
        sec.items.all().delete()
        ActivitySectionProduct.objects.bulk_create(
            ActivitySectionProduct(section=sec, spu_id=s, sku_id=k, sort_order=i)
            for i, (s, k) in enumerate(picked)
        )
        print(f"   #{sec.sort_order} {sec.title[:26]!r:28s} {before} -> {len(picked)}")


def main() -> None:
    for short in REBUILD_PAGES:
        rebuild(short)
    for short, floor in SINGLE_FLOOR.items():
        rebuild(short, only_floor=floor)
    print(f"\n恢复 INACTIVE SPU: {len(restored)} 件")
    for spu_pk, cat in restored:
        print(f"   spu={spu_pk} cat={cat} -> ACTIVE")


if __name__ == "__main__":
    main()
