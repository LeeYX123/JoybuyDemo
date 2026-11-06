"""把商品池 SPU 一次性映射到商家端 12 个固定品类（WP-42，文档 M03 §3）。

映射依据 local_category 名称/英文名关键词，未命中的置空（未分类）。
幂等：--all 重算全部；默认只处理 merchant_category 为空的 SPU。
"""

import json

from django.core.management.base import BaseCommand

from catalog.models import LocalCategory, Spu

# 关键词 → 商家端品类。按 local_category 中英文命名的常见词匹配。
KEYWORD_RULES = [
    ("HOME", ["家居", "home", "living", "kitchen", "家具", "furniture", "cleaning", "清洁"]),
    ("ELECTRONICS", ["电子", "electronic", "appliance", "电器", "audio", "tv", "video"]),
    ("BEAUTY", ["美妆", "个护", "beauty", "personal care", "cosmetic", "fragrance", "skin"]),
    ("SMALL_APPLIANCE", ["小家电", "small appliance", "kettle", "toaster", "blender", "吸尘"]),
    ("HEALTH", ["健康", "保健", "health", "wellness", "supplement", "care"]),
    ("COMPUTER", ["计算机", "电脑", "computer", "laptop", "notebook", "tablet", "accessor"]),
    ("APPAREL", ["服装", "配饰", "服饰", "clothing", "apparel", "fashion", "shoes", "jewelry", "watch"]),
    ("OUTDOOR", ["户外", "运动", "outdoor", "sport", "fitness", "camping"]),
    ("PET", ["宠物", "pet"]),
    ("BABY", ["婴", "母婴", "童", "baby", "infant", "kids", "toy"]),
    ("GAMES", ["游戏", "game"]),
]


def match_category(local_category: LocalCategory) -> str:
    haystack = " ".join(
        filter(
            None,
            [local_category.name or "", local_category.name_en or "", local_category.path or ""],
        )
    ).lower()
    for code, keywords in KEYWORD_RULES:
        for keyword in keywords:
            if keyword in haystack:
                return code
    return ""


class Command(BaseCommand):
    help = "按 local_category 关键词把 SPU 映射到商家端 12 固定品类（幂等）"

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="重算全部 SPU（默认只补空的）")
        parser.add_argument("--dry-run", action="store_true", help="只统计不落库")

    def handle(self, *args, **options):
        recalc_all = options["all"]
        spus = Spu.objects.select_related("local_category")
        if not recalc_all:
            spus = spus.filter(merchant_category="")
        category_cache = {
            category.pk: match_category(category)
            for category in LocalCategory.objects.all()
        }
        counts = {}
        unmatched = 0
        updated = 0
        for spu in spus:
            code = category_cache.get(spu.local_category_id, "") if spu.local_category_id else ""
            if not code:
                unmatched += 1
            counts[code or "未分类"] = counts.get(code or "未分类", 0) + 1
            if spu.merchant_category != code:
                if not options["dry_run"]:
                    Spu.objects.filter(pk=spu.pk).update(merchant_category=code)
                updated += 1
        self.stdout.write(
            json.dumps(
                {
                    "scanned": len(counts) and sum(counts.values()),
                    "updated": updated,
                    "unmatched": unmatched,
                    "by_category": counts,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
