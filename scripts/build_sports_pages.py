# -*- coding: utf-8 -*-
"""户外运动 3 个落地页建页（2026-11-27 用户要求：三张卡跳活动页且有数据）。

真相：真站 NL 版 3 个活动页存在，但服务端下发的楼层素材是测试占位
（materialData 只有 goodsId1_0/time，渲染「使用测试数据 (4 条记录)」），
任何会话都拿不到真站商品。按营销页同款口径：真站楼层结构（标题真实存在）
+ 本地商品库配额选品（Outdoor & Sports 类目），每层 25 件（首屏 5 + 一次
查看更多，符合全站 >5 件带按钮的规律），打乱混排。

楼层主题按标题语义映射类目/关键词；Hats/Tops/Bottoms 用标题关键词过滤。
"""

import json
import os
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from django.db import transaction  # noqa: E402

from catalog.models import LocalCategory, Sku, Spu, SpuTranslation  # noqa: E402
from catalog.search_services import refresh_spu_search_documents  # noqa: E402
from content.models import (  # noqa: E402
    ActivityPage,
    ActivitySection,
    ActivitySectionProduct,
)
from offers.models import Offer  # noqa: E402

FLOOR_CAP = 25
TITLE_COLOR = "#000000"

# (activity_id, NL 源 URL, 楼层[(标题, 类目 slug 列表, 标题关键词)...])
# 关键词 = [];  表示只按类目随机；有关键词则先关键词命中再类目补足。
PAGES = [
    (
        "2bXHZci942jnxZsP6Wm5wbBwLZL6",
        "https://www.joybuy.nl/campaign/active/2bXHZci942jnxZsP6Wm5wbBwLZL6",
        [
            ("New arrivals", ["fitness-training", "outdoor-gear", "sports-apparel-shoes", "garden", "diy-tools"], []),
            ("Winter must-haves", ["outdoor-gear"], []),
            ("Workout gear", ["fitness-training"], []),
        ],
    ),
    (
        "LP15GX62ND3QzXsUAxarZH33qvc",
        "https://www.joybuy.nl/campaign/active/LP15GX62ND3QzXsUAxarZH33qvc",
        [
            ("Clothing", ["sports-apparel-shoes"], []),
            ("Equipment & Accessories", ["fitness-training", "outdoor-gear"], []),
            ("Recovery", ["fitness-training"], ["massage", "foam roller", "recovery", "relax"]),
        ],
    ),
    (
        "kz6csttxvFiB6LbfLzaBSmkWP1m",
        "https://www.joybuy.nl/campaign/active/kz6csttxvFiB6LbfLzaBSmkWP1m",
        [
            ("Hats", ["sports-apparel-shoes"], ["hat", "cap", "beanie", "headwear"]),
            ("Tops", ["sports-apparel-shoes"], ["t-shirt", "tee", "shirt", "hoodie", "sweater", "jacket", "top"]),
            ("Bottoms", ["sports-apparel-shoes"], ["pants", "trousers", "leggings", "shorts", "joggers"]),
        ],
    ),
]


def pick_floor(rng: random.Random, slugs: list[str], keywords: list[str], exclude: set[int], cap: int) -> list[int]:
    pool_ids = set(
        Spu.objects.filter(
            status=Spu.Status.ACTIVE,
            local_category__slug__in=slugs,
        )
        .filter(skus__offers__status=Offer.Status.ACTIVE)
        .exclude(pk__in=exclude)
        .values_list("pk", flat=True)
        .distinct()
    )
    picked: list[int] = []
    if keywords:
        hit = set(
            SpuTranslation.objects.filter(title__iregex=r"(" + "|".join(re.escape(k) for k in keywords) + ")")
            .values_list("spu_id", flat=True)
        )
        ordered = list(pool_ids & hit)
        rng.shuffle(ordered)
        picked.extend(ordered[:cap])
    if len(picked) < cap:
        rest = list(pool_ids - set(picked))
        rng.shuffle(rest)
        picked.extend(rest[: cap - len(picked)])
    return picked[:cap]


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
    bound = 0
    for ext, source_url, floors in PAGES:
        rng = random.Random(f"sports-{ext}")
        print(f"== /active/{ext[:10]}")
        exclude: set[int] = set()
        built = []
        for title, slugs, keywords in floors:
            picked = pick_floor(rng, slugs, keywords, exclude, FLOOR_CAP)
            exclude.update(picked)
            built.append((title, picked))
            kw_note = f" (关键词 {keywords})" if keywords else ""
            print(f"    {title[:30]:32s} {len(picked)} 件{kw_note}")
        with transaction.atomic():
            page, _ = ActivityPage.objects.update_or_create(
                kind=ActivityPage.Kind.ACTIVITY,
                external_id=ext,
                defaults={
                    "title": "Don't just buy, Joybuy",
                    "source_url": source_url,
                    "enabled": True,
                },
            )
            page.sections.all().delete()
            for i, (title, items) in enumerate(built, start=1):
                section = ActivitySection.objects.create(
                    page=page,
                    kind=ActivitySection.Kind.PRODUCTS,
                    title=title,
                    title_color=TITLE_COLOR,
                    columns=5,
                    show_more=len(items) > 5,
                    extra={"mod": True, "title_size": 16, "title_lh": 40},
                    sort_order=i,
                )
                ActivitySectionProduct.objects.bulk_create(
                    ActivitySectionProduct(section=section, spu_id=spu_pk, sort_order=j)
                    for j, spu_pk in enumerate(items)
                )
        result = publish([s for _, items in built for s in items])
        # 绑卡（含 NL/joyfumi 各行，按 activity_page 外键）
        from content.models import ChannelPageCard

        for card in ChannelPageCard.objects.filter(link_url__icontains=ext[:16]):
            if card.activity_page_id != page.pk:
                card.activity_page = page
                card.save(update_fields=["activity_page", "updated_at"])
                bound += 1
        print(f"    published={result['published']} failures={len(result['failures'])}")
    print(f"绑定卡片: {bound}")


if __name__ == "__main__":
    main()
