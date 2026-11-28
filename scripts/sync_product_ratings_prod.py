"""服务器端回填：活动页楼层商品的评分/已售快照 + SPU 豁免激活。

配套 export_product_ratings.py 的导出 JSON。在服务器上执行：

    .venv/Scripts/python.exe scripts/sync_product_ratings_prod.py --bundle <json路径> [--apply]

不加 --apply 预演。行为：
1. 按 SpuSourceIdentity(joybuy_uk:<source_id>) 找 SPU，回填 SpuDetail 的
   rating_average / rating_count / sale_amount（只动这三个字段，不动其他）；
2. status 非 ACTIVE 的 SPU 按活动页豁免口径激活（SPU/SKU/Offer → ACTIVE，
   不重建搜索文档，仅活动页可见口径）；
3. 服务器上找不到 source_id 的商品列出来——那些需要先同步商品目录。
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

from catalog.models import Sku, Spu, SpuDetail, SpuSourceIdentity  # noqa: E402
from offers.models import Offer  # noqa: E402
from decimal import Decimal, InvalidOperation  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--apply", action="store_true")
    options = parser.parse_args()

    bundle = json.loads(Path(options.bundle).read_text(encoding="utf-8"))
    records = bundle.get("records") or []
    print(f"bundle records: {len(records)}")

    idents = {
        row.source_id: row.spu_id
        for row in SpuSourceIdentity.objects.filter(source_system="joybuy_uk")
    }

    updated = activated = missing = 0
    for rec in records:
        source_id = rec.get("source_id") or ""
        spu_id = idents.get(source_id)
        if not spu_id:
            missing += 1
            print(f"[缺SPU] {source_id}（服务器目录无此商品，需先同步商品数据）")
            continue
        spu = Spu.objects.get(pk=spu_id)
        if spu.status != Spu.Status.ACTIVE:
            if options.apply:
                spu.status = Spu.Status.ACTIVE
                spu.save(update_fields=["status", "updated_at"])
                Sku.objects.filter(spu=spu).exclude(status="ACTIVE").update(status="ACTIVE")
                Offer.objects.filter(sku__spu=spu).exclude(status="ACTIVE").update(
                    status="ACTIVE", removed_by_platform=False
                )
            activated += 1

        rating = rec.get("rating_average")
        try:
            rating_dec = Decimal(str(rating)) if rating is not None else None
        except (InvalidOperation, ValueError):
            rating_dec = None
        sale = rec.get("sale_amount")

        if options.apply:
            detail, _ = SpuDetail.objects.get_or_create(spu_id=spu_id)
            detail.rating_average = rating_dec
            detail.rating_count = rec.get("rating_count") or 0
            detail.sale_amount = sale
            detail.save(update_fields=["rating_average", "rating_count", "sale_amount", "updated_at"])
        updated += 1

    mode = "APPLIED" if options.apply else "DRY-RUN"
    print(f"[{mode}] 更新评分/已售={updated} 激活={activated} 服务器缺商品={missing}")
    if missing:
        print("!! 缺商品需先同步商品目录（SPU/SKU/Offer/SpuDetail），活动页楼层会缺卡")
    return 0


if __name__ == "__main__":
    sys.exit(main())
