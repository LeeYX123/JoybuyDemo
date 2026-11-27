"""重建活动页 2dawKz7FDU6oYukbjAiHPmssXb1Q（2026-11-27 真站对齐）。

真站当前结构（var/campaign_2dawKz7_20261127.html 实测）：
- 页面标题 Discover our range（Digestive Health）
- hero banner（消化系统健康）
- 单个商品楼层，无楼层标题，28 件商品按真站顺序，首屏 5 件 + 【查看更多】

旧版 5 个子楼层（Digestive Enzymes 等）是此前抓到的旧页面结构，全部删除。
商品清单顺序以真站 materialData 为准（var/campaign_2dawKz7_items.json），
缺失商品由 PAGE_SET 任务补采入库后映射。
"""

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

from catalog.models import SkuSourceIdentity  # noqa: E402
from content.models import ActivityPage, ActivitySection, ActivitySectionProduct  # noqa: E402

EXT = "2dawKz7FDU6oYukbjAiHPmssXb1Q"
HERO = f"/images/activity/pages/{EXT}/hero.png"
ITEMS_JSON = ROOT / "var" / "campaign_2dawKz7_items.json"


def main() -> int:
    page = ActivityPage.objects.filter(external_id=EXT).first()
    if page is None:
        print("!! page not found")
        return 1

    items = json.loads(ITEMS_JSON.read_text(encoding="utf-8"))
    print(f"real items: {len(items)}")

    page.hero_image = HERO
    page.save(update_fields=["hero_image", "updated_at"])

    # 旧分区清掉（5 个子楼层是旧版结构）
    deleted = ActivitySection.objects.filter(page=page).delete()
    print("old sections deleted:", deleted)

    section = ActivitySection.objects.create(
        page=page,
        kind=ActivitySection.Kind.PRODUCTS,
        title="",
        title_zh="",
        columns=5,
        show_more=len(items) > 5,
        sort_order=1,
    )

    missing = []
    created = 0
    for order, item in enumerate(items, start=1):
        sid = SkuSourceIdentity.objects.filter(
            source_id=item["sku"], source_system="joybuy_uk"
        ).select_related("sku", "sku__spu").first()
        if sid is None:
            missing.append(item["sku"])
            continue
        ActivitySectionProduct.objects.create(
            section=section,
            spu=sid.sku.spu,
            sku=sid.sku,
            sort_order=order,
        )
        created += 1

    print(f"section created: products={created}, missing={missing}")
    print(f"show_more={section.show_more}")
    return 0 if not missing else 2


if __name__ == "__main__":
    sys.exit(main())
