"""导出活动页楼层商品的评分/已售快照（用于同步到服务器）。

导出内容：所有 ACTIVITY/STORE 页楼层涉及商品的 source_id → SpuDetail
关键字段（rating_average / rating_count / sale_amount）+ SPU status。

用法：.venv/Scripts/python.exe scripts/export_product_ratings.py --out var/deploy/product_ratings_20261128.json
"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from catalog.models import Spu, SpuDetail, SpuSourceIdentity  # noqa: E402
from content.models import ActivityPage, ActivitySectionProduct  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    options = parser.parse_args()

    pages = ActivityPage.objects.filter(kind__in=["ACTIVITY", "STORE"])
    spu_pks: set[int] = set()
    page_map: dict[int, list[str]] = {}
    for page in pages:
        for item in ActivitySectionProduct.objects.filter(section__page=page):
            if item.spu_id:
                spu_pks.add(item.spu_id)
                page_map.setdefault(item.spu_id, []).append(page.external_id[:14])

    idents = {
        row.spu_id: row.source_id
        for row in SpuSourceIdentity.objects.filter(spu_id__in=spu_pks)
    }
    details = {
        row.spu_id: row
        for row in SpuDetail.objects.filter(spu_id__in=spu_pks).only(
            "spu_id", "rating_average", "rating_count", "sale_amount"
        )
    }
    spus = {spu.pk: spu for spu in Spu.objects.filter(pk__in=spu_pks).only("pk", "status")}

    records = []
    for spu_pk in sorted(spu_pks):
        detail = details.get(spu_pk)
        spu = spus.get(spu_pk)
        records.append(
            {
                "source_id": idents.get(spu_pk, ""),
                "spu_public_id": str(spu.public_id) if spu else "",
                "status": spu.status if spu else "",
                "rating_average": str(detail.rating_average) if detail and detail.rating_average is not None else None,
                "rating_count": detail.rating_count if detail else 0,
                "sale_amount": detail.sale_amount if detail else None,
                "pages": page_map.get(spu_pk, []),
            }
        )

    missing_ident = sum(1 for r in records if not r["source_id"])
    payload = {
        "exported_at": __import__("django.utils.timezone", fromlist=["timezone"]).now().isoformat(),
        "spu_total": len(records),
        "missing_source_id": missing_ident,
        "records": records,
    }
    Path(options.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    with_rating = sum(1 for r in records if r["rating_average"] is not None)
    print(f"exported spu={len(records)} 有评分={with_rating} 无评分={len(records) - with_rating} 缺source_id={missing_ident}")
    print(f"written: {options.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
