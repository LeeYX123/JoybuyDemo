# -*- coding: utf-8 -*-
"""营销落地页建页 + 每周甄选换卡（2026-11-27 用户拍板口径）。

4 个 /marketing/<activityId> 页（ActivityPage kind=MARKETING）：
- 结构复刻真站 marketing 页：深蓝装饰 banner（title + subtitle）+ 单一商品网格；
  真站的类目切换 tab 与 Filter 侧栏不复刻；NL 两页可读文字换英文。
- 商品 = 配额选品（Quota Selection）：按指定二级类目从本地库随机选（快照固定，
  随机种子 = activityId，可复现），单网格混排，首屏 20 + 一次【查看更多】 = 40。
- 引用的 DRAFT 商品自动上架（激活 Offer + 重建搜索文档）。

每周甄选：旧 6 张真站外链卡全部下线，换 4 张新卡（真站每周甄选原图，
href → 本地 /marketing/<id>）。

幂等：重跑 = 重选一批评选（种子固定 → 选品不变）+ 重建楼层位次 + 换卡。
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

from catalog.models import LocalCategory, Sku, Spu  # noqa: E402
from offers.models import Offer  # noqa: E402
from content.models import (  # noqa: E402
    ActivityPage,
    ActivitySection,
    ActivitySectionProduct,
    HomeCampaignCard,
)

TOTAL = 40

# (activityId, 英文标题, 中文标题, 英文副标题, 源站 URL, [(类目 slug, 配额)...])
PAGES = [
    (
        "21210005",
        "Winter wellness deals",
        "冬季健康好物优惠",
        "Feel good this winter",
        "https://www.joybuy.co.uk/marketing?activityId=21210005&tagId=2123737757661806601",
        [
            ("nutrition-supplements", 5),
            ("sports-nutrition-performance", 5),
            ("weight-management", 5),
            ("electronic-therapy", 5),
            ("health-monitors", 4),
            ("pharmacy-health", 4),
            ("period-products-intimate-care", 4),
            ("sexual-wellbeing-family-planning", 4),
            ("massage-relaxation", 4),
        ],
    ),
    (
        "26890013",
        "Smart homes bigger savings",
        "智能家居 限时钜惠",
        "Upgrade for less today",
        "https://www.joybuy.co.uk/marketing?activityId=26890013&tagId=2123739232249069577",
        [
            ("coffee-machines", 8),
            ("toothbrushes-flossers", 8),
            ("male-grooming", 8),
            ("female-hair-removal", 8),
            ("air-fryers", 8),
        ],
    ),
    (
        "19370009",
        "A world of toys and gaming",
        "玩具与游戏世界来啦！",
        "Up to 50% off",
        "https://www.joybuy.nl/marketing?activityId=19370009&tagId=2120496052382158856",
        [
            ("dress-up-imaginative-play", 10),
            ("construction-toys", 10),
            ("lego-sets", 10),
            ("learning-discovery-science", 10),
        ],
    ),
    (
        "16330021",
        "Hydrate & glow this autumn",
        "秋日补水合集",
        "Nourish your skin through the changing season.",
        "https://www.joybuy.nl/marketing?activityId=16330021&tagId=2107397802862456834",
        [("skincare", 40)],
    ),
]

WEEKLY_CARDS = [
    # (sort_order, 英文标题, 中文标题, 副标题, 图, href)
    (1, "Winter wellness deals", "冬季健康好物优惠", "Feel good this winter",
     "/images/weekly/card-winter-wellness.webp", "/marketing/21210005"),
    (2, "Smart homes bigger savings", "智能家居 限时钜惠", "Upgrade for less today",
     "/images/weekly/card-smart-homes.webp", "/marketing/26890013"),
    (3, "A world of toys and gaming", "玩具与游戏世界来啦！", "Up to 50% off",
     "/images/weekly/card-toys-gaming.webp", "/marketing/19370009"),
    (4, "Hydrate & glow this autumn", "秋日补水合集", "Nourish your skin through the changing season.",
     "/images/weekly/card-hydrate-glow.webp", "/marketing/16330021"),
]

BANNER = "/images/marketing/banner-bg.webp"


def select_for_page(activity_id: str, quotas) -> list[int]:
    """按类目配额随机选品（种子固定可复现），随机混排。"""

    rng = random.Random(f"marketing-{activity_id}")
    chosen: list[int] = []
    report = []
    for slug, count in quotas:
        cat = LocalCategory.objects.filter(slug=slug).first()
        if cat is None:
            report.append((slug, 0, "类目不存在"))
            continue
        pool = list(
            Spu.objects.filter(status=Spu.Status.ACTIVE, local_category=cat)
            .filter(skus__offers__status=Offer.Status.ACTIVE)
            .values_list("pk", flat=True)
            .distinct()
        )
        take = min(count, len(pool))
        picked = rng.sample(pool, take) if take else []
        chosen.extend(picked)
        report.append((slug, take, f"池{len(pool)}"))
    # 单网格混排：再以同一 rng 洗牌，保证每个类目都有货但顺序随机。
    rng.shuffle(chosen)
    for slug, take, extra in report:
        print(f"    {slug:34s} {take:2d}  ({extra})")
    return chosen


def build_page(spec) -> dict:
    activity_id, title, title_zh, subtitle, source_url, quotas = spec
    print(f"== /marketing/{activity_id} {title!r}")
    chosen = select_for_page(activity_id, quotas)
    with __import__("django").db.transaction.atomic():
        page, _ = ActivityPage.objects.update_or_create(
            kind=ActivityPage.Kind.MARKETING,
            external_id=activity_id,
            defaults={
                "title": title,
                "title_zh": title_zh,
                "subtitle": subtitle,
                "hero_image": BANNER,
                "source_url": source_url,
                "enabled": True,
            },
        )
        page.sections.all().delete()
        section = ActivitySection.objects.create(
            page=page,
            kind=ActivitySection.Kind.PRODUCTS,
            title="",
            columns=5,
            show_more=True,
            extra={"marketing": True, "first_batch": 20},
            sort_order=1,
        )
        ActivitySectionProduct.objects.bulk_create(
            ActivitySectionProduct(section=section, spu_id=spu_pk, sort_order=i)
            for i, spu_pk in enumerate(chosen)
        )
    result = publish_referenced(activity_id)
    print(f"    items={len(chosen)} published={result['published']} failures={len(result['failures'])}")
    return {"external_id": activity_id, "items": len(chosen), "published": result}


def publish_referenced(external_id: str) -> dict:
    """楼层引用的 DRAFT 商品上架（激活 Offer + 重建搜索文档）。"""

    from django.db import transaction

    from catalog.search_services import refresh_spu_search_documents
    from offers.models import Offer as _Offer

    referenced = list(
        ActivitySectionProduct.objects.filter(
            section__page__external_id=external_id
        ).values_list("spu_id", flat=True)
    )
    drafts = list(Spu.objects.filter(pk__in=referenced, status=Spu.Status.DRAFT))
    published = 0
    activated = 0
    failures: list[str] = []
    for spu in drafts:
        try:
            with transaction.atomic():
                spu.status = Spu.Status.ACTIVE
                spu.save(update_fields=["status", "updated_at"])
                Sku.objects.filter(spu=spu).exclude(status="ACTIVE").update(status="ACTIVE")
                activated += _Offer.objects.filter(sku__spu=spu).exclude(
                    status=_Offer.Status.ACTIVE
                ).update(status=_Offer.Status.ACTIVE, removed_by_platform=False)
            refresh_spu_search_documents(spu)
            published += 1
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{spu.pk}: {exc}")
    return {"published": published, "activated": activated, "failures": failures}


def swap_weekly_cards() -> None:
    """旧 6 张真站外链卡下线，4 张新卡指向本地营销页。"""

    old = HomeCampaignCard.objects.filter(section="weekly", enabled=True).exclude(
        href__startswith="/marketing/"
    )
    disabled = old.update(enabled=False)
    created = 0
    for sort_order, title, title_zh, subtitle, image, href in WEEKLY_CARDS:
        _, was_created = HomeCampaignCard.objects.update_or_create(
            section="weekly",
            sort_order=sort_order,
            defaults={
                "title": title,
                "title_zh": title_zh,
                "subtitle": subtitle,
                "image_url": image,
                "href": href,
                "enabled": True,
            },
        )
        created += int(was_created)
    print(f"weekly cards: disabled={disabled} created={created} upserted=4")


def main() -> None:
    summary = [build_page(spec) for spec in PAGES]
    swap_weekly_cards()
    out = Path(__file__).resolve().parents[1] / "var" / "home_modules_20261125" / "marketing_build_report.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print("report:", out)


if __name__ == "__main__":
    main()
