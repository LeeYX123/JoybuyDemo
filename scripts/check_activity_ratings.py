"""诊断：活动页楼层商品的解析与评分数据覆盖情况（在服务器上跑）。

检查三层依赖是否齐全：
1. 楼层商品的 SPU 解析（SpuSourceIdentity → Spu）；
2. Spu.status 是否 ACTIVE（DRAFT 的卡片整张不渲染）；
3. SpuDetail 的评分/已售快照是否写入。

用法：.venv/Scripts/python.exe scripts/check_activity_ratings.py [external_id ...]
不给参数则检查全部 ACTIVITY 页。
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from catalog.models import Spu, SpuDetail, SpuSourceIdentity, SkuSourceIdentity  # noqa: E402
from content.models import ActivityPage, ActivitySectionProduct  # noqa: E402


def check(external_id: str) -> None:
    page = ActivityPage.objects.filter(external_id=external_id).first()
    if page is None:
        print(f"!! page not found: {external_id}")
        return
    print(f"\n== {external_id[:14]} {page.title[:30]!r}")
    for sec in page.sections.filter(kind="PRODUCTS").order_by("sort_order"):
        rows = list(
            ActivitySectionProduct.objects.filter(section=sec)
            .select_related("spu", "sku")
            .order_by("sort_order")
        )
        no_spu = [r for r in rows if r.spu_id is None]
        inactive = [r for r in rows if r.spu_id and r.spu.status != Spu.Status.ACTIVE]
        no_detail = []
        no_rating = []
        has_rating = []
        for r in rows:
            if not r.spu_id:
                continue
            detail = SpuDetail.objects.filter(spu_id=r.spu_id).first()
            if detail is None:
                no_detail.append(r)
            elif detail.rating_average is None:
                no_rating.append(r)
            else:
                has_rating.append((r, detail))
        print(
            f"  #{sec.sort_order} {sec.title[:28]!r} items={len(rows)} "
            f"无SPU引用={len(no_spu)} 非ACTIVE={len(inactive)} "
            f"无SpuDetail={len(no_detail)} 有Detail无评分={len(no_rating)} 有评分={len(has_rating)}"
        )
        for label, group in (
            ("缺SpuDetail", no_detail),
            ("无评分", no_rating),
        ):
            for r in group[:4]:
                ident = SpuSourceIdentity.objects.filter(spu_id=r.spu_id).first()
                print(f"    [{label}] {ident.source_id if ident else '?'} {str(r.spu.public_id)[:8]}")
        if inactive:
            for r in inactive[:4]:
                print(f"    [非ACTIVE {r.spu.status}] {str(r.spu.public_id)[:8]}")


def main() -> int:
    exts = sys.argv[1:]
    if not exts:
        exts = list(
            ActivityPage.objects.filter(kind="ACTIVITY").values_list("external_id", flat=True)
        )
    for ext in exts:
        check(ext)
    return 0


if __name__ == "__main__":
    sys.exit(main())
