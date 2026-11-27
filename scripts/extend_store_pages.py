# -*- coding: utf-8 -*-
"""店铺页扩容（2026-11-27 用户口径）：在真站商品之外按二级类目配额补货并打乱。

Toy (100003512)：+乐高套装 10 / 拼装玩具 10 / 角色扮演道具&想象游戏 10；
Baby (100003468)：+婴儿哺育喂养 10 / 婴儿车手推车及旅行配件 10 / 婴儿洗护用品 10。

规则：现有真站位次保持在前（快照），配额商品从本地库 ACTIVE+有报价随机选
（种子=店铺 id 可复现），排除已在楼层的商品；**整体打乱**后重写位次；
新引用的 DRAFT 商品自动上架（Offer + 搜索文档）。
"""

import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from django.db import transaction  # noqa: E402

from catalog.models import LocalCategory, Sku, Spu  # noqa: E402
from catalog.search_services import refresh_spu_search_documents  # noqa: E402
from content.models import (  # noqa: E402
    ActivityPage,
    ActivitySection,
    ActivitySectionProduct,
)
from offers.models import Offer  # noqa: E402

STORES = {
    "100003512": [
        ("lego-sets", 10),
        ("construction-toys", 10),
        ("dress-up-imaginative-play", 10),
    ],
    "100003468": [
        ("baby-feeding", 10),
        ("strollers-travel", 10),
        ("baby-toiletries", 10),
    ],
}


def quota_pick(activity_id: str, quotas, exclude: set[int]) -> list[int]:
    rng = random.Random(f"store-{activity_id}")
    picked: list[int] = []
    for slug, count in quotas:
        cat = LocalCategory.objects.filter(slug=slug).first()
        pool = list(
            Spu.objects.filter(status=Spu.Status.ACTIVE, local_category=cat)
            .filter(skus__offers__status=Offer.Status.ACTIVE)
            .exclude(pk__in=exclude)
            .values_list("pk", flat=True)
            .distinct()
        )
        take = min(count, len(pool))
        picked.extend(rng.sample(pool, take) if take else [])
        print(f"    {slug:30s} {take}/{count} (池 {len(pool)})")
    return picked


def publish(spu_ids: list[int]) -> dict:
    drafts = list(Spu.objects.filter(pk__in=spu_ids, status=Spu.Status.DRAFT))
    published = 0
    failures = []
    for spu in drafts:
        try:
            with transaction.atomic():
                spu.status = Spu.Status.ACTIVE
                spu.save(update_fields=["status", "updated_at"])
                Sku.objects.filter(spu=spu).exclude(status="ACTIVE").update(status="ACTIVE")
                Offer.objects.filter(sku__spu=spu).exclude(status="ACTIVE").update(
                    status=Offer.Status.ACTIVE, removed_by_platform=False
                )
            refresh_spu_search_documents(spu)
            published += 1
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{spu.pk}: {exc}")
    return {"published": published, "failures": failures}


def main() -> None:
    for ext, quotas in STORES.items():
        print(f"== /store/{ext}")
        page = ActivityPage.objects.filter(kind="STORE", external_id=ext).first()
        section = page.sections.filter(kind="PRODUCTS").order_by("sort_order").first()
        existing_rows = list(section.items.order_by("sort_order"))
        existing_spus = [row.spu_id for row in existing_rows]
        print(f"    现有 {len(existing_rows)} 件（真站快照，保持在前）")
        extra = quota_pick(ext, quotas, set(existing_spus))
        print(f"    补充 {len(extra)} 件")
        # 打乱整层（快照在前只是采集来源口径，展示顺序用户要求打乱）
        combined = existing_spus + extra
        rng = random.Random(f"store-shuffle-{ext}")
        rng.shuffle(combined)
        section.items.all().delete()
        ActivitySectionProduct.objects.bulk_create(
            ActivitySectionProduct(section=section, spu_id=spu_pk, sort_order=i)
            for i, spu_pk in enumerate(combined)
        )
        result = publish(extra)
        print(f"    总计 {len(combined)} 件 | published={result['published']} failures={len(result['failures'])}")


if __name__ == "__main__":
    main()
