"""建 3 个「品类页频道卡」落地页并快照选品（2026-11-26，ADR-0002 首批）。

页面（UK-Mini-HP-Home-Living 频道卡，真站 ID 一致）：
- 4VQ7 「Christmas for less」：三档价格带楼层（£5 以下 / £5–9.99 / £10–14.99）
- 41xQ 「Find your Christmas style」：4 个圣诞主题楼层
- 254vg 「Make your tree magical」：圣诞树 / 挂饰 / 灯串 / 树顶装饰主题楼层

选品口径（grill 定稿）：
- 真站该层清单（白名单）为主：已入库的商品按清单顺序直接落位；
- 价格带楼层「价格优先」：白名单里价格跑出带外的剔除，再用**全库**带内
  （且圣诞相关）商品补位；主题楼层白名单不足时用关键词补位；
- 每层上限 25 件（真站 13 件的层就 13 件）；同一页内商品不重复；
- 价格用前台展示价（主 SKU）：`spu.retail_price` 优先，否则最低 ACTIVE 报价。

可重跑（幂等）：页面/楼层/位次整页替换；已上架商品不受影响。
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import os  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402
from django.db import transaction  # noqa: E402
from django.db.models import Min  # noqa: E402

django.setup()

from catalog.models import Sku, SkuSourceIdentity, Spu, SpuSourceIdentity, SpuTranslation  # noqa: E402
from content.models import (  # noqa: E402
    ActivityPage,
    ActivitySection,
    ActivitySectionProduct,
    ChannelPageCard,
)
from crawler_control.models import CrawlPageManifest, CrawlRun  # noqa: E402
from merchant_ops.views_catalog import StaffApiError, _activate_offers_on_publish  # noqa: E402

HERE = ROOT / "var" / "home_modules_20261125"
SOURCE_SYSTEM = "joybuy_uk"
FLOOR_CAP = 25
BRICK = "#a33838"  # 真站楼层标题深红（measure 系列实测）

PAGES = [
    {
        "short": "4VQ7",
        "external_id": "4VQ7S5wXyuCEHevKrebXCnt6KmHY",
        "title": "Christmas for less",
        "run": 406,
        # 价格带（左闭右开；9.99 上限含到 9.99）
        "bands": [
            ("£5 & under", None, 5.0),
            ("£5 to £9.99", 5.0, 9.99),
            ("£10 to £14.99", 10.0, 14.99),
        ],
        "fill_keywords": ["christmas", "圣诞", "festive"],
    },
    {
        "short": "41xQ",
        "external_id": "41xQpuBGBQ37QRh44nrYLBbUh4cR",
        "title": "Find your Christmas style",
        "run": 404,
        "fill_keywords": ["christmas", "圣诞", "festive"],
    },
    {
        "short": "254vg",
        "external_id": "254vgVWftmsCmX9cMbbeZ92F7YQj",
        "title": "Make your tree magical",
        "run": 405,
        # 主题楼层补位关键词（按楼层标题匹配）
        "floor_keywords": {
            "tree": ["christmas tree", "圣诞树"],
            "bauble": ["bauble", "ornament", "装饰球", "挂饰"],
            "light": ["light", "灯"],
            "top": ["topper", "skirt", "stocking", "树裙", "袜", "树顶"],
        },
        "fill_keywords": ["christmas", "圣诞"],
    },
]


def floor_keywords(page, title):
    """按楼层标题挑补位关键词（254vg 主题楼层）；其余用页级关键词。"""

    rules = page.get("floor_keywords") or {}
    lowered = title.lower()
    for marker, keywords in rules.items():
        if marker in lowered:
            return keywords
    return page.get("fill_keywords") or []


def band_of(page, title):
    for name, low, high in page.get("bands") or []:
        if name in title:
            return (low, high)
    return None


def in_band(price, band):
    low, high = band
    if price is None:
        return False
    if low is not None and price < low:
        return False
    if high is not None and price > high:
        return False
    return True


def main() -> None:
    import argparse  # noqa: E402

    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="写库（默认干跑）")
    args = parser.parse_args()

    # ---- 全局映射：价格缓存（前台展示价 = retail_price 优先，否则最低 ACTIVE 报价）----
    price_cache: dict[int, float | None] = {}

    def display_price(spu_pk):
        if spu_pk in price_cache:
            return price_cache[spu_pk]
        spu = Spu.objects.filter(pk=spu_pk).first()
        value = float(spu.retail_price) if spu and spu.retail_price is not None else None
        if value is None:
            from offers.models import Offer

            low = Offer.objects.filter(sku__spu_id=spu_pk, status=Offer.Status.ACTIVE).aggregate(
                x=Min("current_price")
            )["x"]
            value = float(low) if low is not None else None
        price_cache[spu_pk] = value
        return value

    def keyword_candidates(keywords):
        """标题命中关键词的 ACTIVE 商品（有 ACTIVE 报价），按 SPU 主键稳定排序。"""

        matched: set[int] = set()
        for keyword in keywords:
            matched |= set(
                SpuTranslation.objects.filter(title__icontains=keyword).values_list("spu_id", flat=True)
            )
        rows = Spu.objects.filter(pk__in=matched, status=Spu.Status.ACTIVE).order_by("-pk")
        return [row.pk for row in rows if display_price(row.pk) is not None]

    keyword_cache: dict[tuple, list[int]] = {}

    def candidates_for(keywords):
        key = tuple(sorted(keywords))
        if key not in keyword_cache:
            keyword_cache[key] = keyword_candidates(keywords)
        return keyword_cache[key]

    used_per_page: dict[str, set[int]] = {}
    report = []

    for page_spec in PAGES:
        short = page_spec["short"]
        run = CrawlRun.objects.get(pk=page_spec["run"])
        manifest = CrawlPageManifest.objects.filter(run=run).order_by("-pk").first()
        floors = [b for b in manifest.data.get("blocks") or [] if b.get("type") == "floor"]
        used_per_page[short] = set()

        built_floors = []
        for index, floor in enumerate(floors, start=1):
            title = floor.get("title", "")
            cap = min(FLOOR_CAP, len(floor.get("products") or []))
            band = band_of(page_spec, title)
            keywords = floor_keywords(page_spec, title)

            picked: list[tuple[int, int | None]] = []
            picked_keys = set()
            missing_whitelist = []
            # 1) 白名单（真站顺序），价格带楼层里跑出带外的剔除
            for product in floor.get("products") or []:
                source_id = product["url"].split("/dp/")[-1].split("?")[0]
                spu_pk = SpuSourceIdentity.objects.filter(
                    source_system=SOURCE_SYSTEM, source_id=source_id
                ).values_list("spu_id", flat=True).first()
                sku_pk = None
                if not spu_pk:
                    sku_row = SkuSourceIdentity.objects.filter(
                        source_system=SOURCE_SYSTEM, source_id=source_id
                    ).select_related("sku").first()
                    if sku_row:
                        spu_pk, sku_pk = sku_row.sku.spu_id, sku_row.sku_id
                if not spu_pk:
                    missing_whitelist.append(source_id)
                    continue
                if band is not None and not in_band(display_price(spu_pk), band):
                    continue  # 价格优先：跑出带外的白名单商品直接剔除
                key = (spu_pk, sku_pk)
                if key in picked_keys or spu_pk in used_per_page[short]:
                    continue
                picked_keys.add(key)
                picked.append(key)
                if len(picked) >= cap:
                    break

            # 2) 白名单不足 → 关键词从全库补位（带内过滤仍生效）
            backfilled = 0
            if len(picked) < cap and keywords:
                pool = candidates_for(keywords)
                for spu_pk in pool:
                    if len(picked) >= cap:
                        break
                    if spu_pk in used_per_page[short]:
                        continue
                    if band is not None and not in_band(display_price(spu_pk), band):
                        continue
                    key = (spu_pk, None)
                    if key in picked_keys:
                        continue
                    picked_keys.add(key)
                    picked.append(key)
                    backfilled += 1

            used_per_page[short].update(spu for spu, _sku in picked)
            built_floors.append(
                {
                    "title": title,
                    "sort_order": index,
                    "show_more": bool(floor.get("more")),
                    "items": picked,
                    "whitelist": len(floor.get("products") or []),
                    "backfilled": backfilled,
                    "missing_whitelist": missing_whitelist,
                }
            )

        report.append(
            {
                "page": short,
                "title": page_spec["title"],
                "floors": [
                    {
                        "title": f["title"],
                        "count": len(f["items"]),
                        "whitelist": f["whitelist"],
                        "backfilled": f["backfilled"],
                        "missing": len(f["missing_whitelist"]),
                    }
                    for f in built_floors
                ],
                "total": sum(len(f["items"]) for f in built_floors),
            }
        )
        page_spec["_built"] = built_floors

        if not args.apply:
            continue

        with transaction.atomic():
            page, _created = ActivityPage.objects.update_or_create(
                kind=ActivityPage.Kind.ACTIVITY,
                external_id=page_spec["external_id"],
                defaults={
                    "title": page_spec["title"],
                    "source_url": "https://www.joybuy.co.uk/campaign/active/" + page_spec["external_id"],
                    "enabled": True,
                },
            )
            page.sections.all().delete()
            for floor in built_floors:
                section = ActivitySection.objects.create(
                    page=page,
                    kind=ActivitySection.Kind.PRODUCTS,
                    title=floor["title"],
                    title_color=BRICK,
                    columns=5,
                    show_more=floor["show_more"],
                    sort_order=floor["sort_order"],
                )
                ActivitySectionProduct.objects.bulk_create(
                    [
                        ActivitySectionProduct(
                            section=section, spu_id=spu, sku_id=sku, sort_order=order
                        )
                        for order, (spu, sku) in enumerate(floor["items"])
                    ]
                )

    print(json.dumps(report, ensure_ascii=False, indent=1))

    if not args.apply:
        print("DRY RUN；加 --apply 写库（页面/楼层/位次 + 绑定频道卡）")
        return

    # ---- 绑定 Home-Living 频道的三张卡（ADR-0002：外键优先于 link_url）----
    bound = []
    for page_spec in PAGES:
        page = ActivityPage.objects.get(
            kind=ActivityPage.Kind.ACTIVITY, external_id=page_spec["external_id"]
        )
        card = ChannelPageCard.objects.filter(
            channel_code="UK-Mini-HP-Home-Living", link_url__icontains=page_spec["external_id"]
        ).first()
        if card is None:
            print(f"[warn] 未找到 {page_spec['short']} 对应的频道卡")
            continue
        card.activity_page = page
        card.save(update_fields=["activity_page", "updated_at"])
        bound.append({"card": str(card.public_id), "page": page_spec["external_id"]})
    print("bound:", json.dumps(bound, ensure_ascii=False))

    # ---- 上架本批新导入且被楼层引用的 DRAFT（激活 Offer + 重建搜索文档）----
    referenced = set(
        ActivitySectionProduct.objects.filter(
            section__page__external_id__in=[p["external_id"] for p in PAGES]
        ).values_list("spu_id", flat=True)
    )
    drafts = list(Spu.objects.filter(pk__in=referenced, status=Spu.Status.DRAFT))
    published, failures, activated = [], [], 0
    for spu in drafts:
        try:
            with transaction.atomic():
                activated += _activate_offers_on_publish(spu)
                spu.status = Spu.Status.ACTIVE
                spu.save(update_fields=["status", "updated_at"])
            published.append(spu.pk)
        except StaffApiError as exc:
            failures.append({"spu": str(spu.public_id), "code": getattr(exc, "business_code", ""), "msg": str(exc)})
        except Exception as exc:  # noqa: BLE001
            failures.append({"spu": str(spu.public_id), "code": "EXCEPTION", "msg": repr(exc)})
    print(f"published={len(published)} activated_offers={activated} failures={len(failures)}")
    for row in failures[:8]:
        print("  fail", row)
    if published:
        import importlib.util  # noqa: E402

        spec = importlib.util.spec_from_file_location(
            "topup_publish_drafts", ROOT / "var" / "topup50_20261125" / "publish_drafts.py"
        )
        pub = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pub)
        pub.refresh_docs(published, label="channel-card-pages")


if __name__ == "__main__":
    main()
