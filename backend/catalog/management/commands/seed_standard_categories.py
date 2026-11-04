"""Seed the 11 standard storefront categories (docs/12 global convention #1).

The 11 first-level categories and their Chinese/English display names are a
fixed product decision (功能需求清单 #1-1). Every surface that shows a category
list (header category row, Categories panel, bestseller tabs) must use this
list, in this order. The command is idempotent: existing rows are updated,
missing rows are created, and legacy ACTIVE root categories that are not part
of the standard list are hidden so the storefront shows exactly these 11.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import LocalCategory
from catalog.services import create_local_category

# Demo-inventory keyword rules: (child slug, title keywords, lowercase).
# Anything unmatched falls back to groceries (the demo inventory is mostly food).
DEMO_KEYWORD_RULES = [
    (
        "kitchen-appliances",
        (
            "air fryer",
            "blender",
            "espresso",
            "rice cooker",
            "stand mixer",
            "kettle",
            "dough maker",
            "cooker",
            "pressure",
        ),
    ),
    ("electronics", ("earbuds", "smart watch", "usb-c", "cable", "charger")),
    ("cleaning-supplies", ("toilet", "tissue", "wet wipes", "wipe")),
]
DEMO_FALLBACK_SLUG = "groceries-food"

# (slug, name_en, name_zh, [(child slug, child en, child zh), ...])
STANDARD_CATEGORIES = [
    (
        "home-living",
        "Home & Living",
        "家居生活",
        [
            ("kitchen-essentials", "Kitchen Essentials", "厨房用品"),
            ("home-storage", "Home Storage", "家居收纳"),
            ("bedding-textiles", "Bedding & Textiles", "床品家纺"),
            ("cleaning-supplies", "Cleaning Supplies", "清洁用品"),
            ("groceries-food", "Groceries & Food", "食品杂货"),
        ],
    ),
    (
        "electronics",
        "Electronics",
        "电子产品",
        [
            ("tv-audio", "TV & Audio", "电视与影音"),
            ("phones-tablets", "Phones & Tablets", "手机与平板"),
            ("cameras-photo", "Cameras & Photo", "影像拍摄"),
            ("smart-home", "Smart Home", "智能家居"),
        ],
    ),
    (
        "beauty-personal-care",
        "Beauty & Personal Care",
        "美妆个人护理",
        [
            ("skincare", "Skincare", "护肤"),
            ("makeup", "Makeup", "彩妆"),
            ("body-hair-care", "Body & Hair Care", "个护洗护"),
            ("fragrance", "Fragrance", "香水"),
        ],
    ),
    (
        "small-home-appliances",
        "Small Home Appliances",
        "小家电",
        [
            ("kitchen-appliances", "Kitchen Appliances", "厨房小电"),
            ("personal-care-appliances", "Personal Care Appliances", "个护小电"),
            ("cleaning-appliances", "Cleaning Appliances", "清洁小电"),
        ],
    ),
    (
        "health-wellness",
        "Health & Wellness",
        "健康与保健",
        [
            ("nutrition-supplements", "Nutrition & Supplements", "保健营养"),
            ("health-monitors", "Health Monitors", "健康监测"),
            ("massage-relaxation", "Massage & Relaxation", "按摩放松"),
        ],
    ),
    (
        "computers-accessories",
        "Computers & Accessories",
        "计算机与配件",
        [
            ("laptops-desktops", "Laptops & Desktops", "笔记本与台式机"),
            ("pc-components", "PC Components", "电脑配件"),
            ("peripherals", "Peripherals", "电脑外设"),
            ("networking", "Networking", "网络设备"),
        ],
    ),
    (
        "clothing-accessories",
        "Clothing & Accessories",
        "服装与配饰",
        [
            ("womens-clothing", "Women's Clothing", "女装"),
            ("mens-clothing", "Men's Clothing", "男装"),
            ("jewellery", "Jewellery", "珠宝首饰"),
            ("watches", "Watches", "手表"),
            ("bags-luggage", "Bags & Luggage", "箱包"),
            ("shoes-boots", "Shoes & Boots", "鞋靴"),
        ],
    ),
    (
        "outdoor-sports",
        "Outdoor & Sports",
        "户外运动",
        [
            ("fitness-training", "Fitness & Training", "运动健身"),
            ("outdoor-gear", "Outdoor Gear", "户外装备"),
            ("cycling", "Cycling", "骑行"),
            ("water-sports", "Water Sports", "水上运动"),
        ],
    ),
    (
        "pet-supplies",
        "Pet Supplies",
        "宠物用品",
        [
            ("pet-food", "Pet Food", "宠物食品"),
            ("pet-toys", "Pet Toys", "宠物玩具"),
            ("pet-grooming", "Pet Grooming", "宠物护理"),
        ],
    ),
    (
        "baby-toddler",
        "Baby & Toddler",
        "婴幼儿用品",
        [
            ("baby-feeding", "Baby Feeding", "婴儿喂养"),
            ("diapers-wipes", "Diapers & Wipes", "纸尿裤湿巾"),
            ("toys-early-learning", "Toys & Early Learning", "玩具早教"),
        ],
    ),
    (
        "games-accessories",
        "Games & Accessories",
        "游戏及配件",
        [
            ("consoles", "Consoles", "游戏主机"),
            ("gaming-accessories", "Gaming Accessories", "游戏配件"),
            ("board-card-games", "Board & Card Games", "桌游棋牌"),
        ],
    ),
]


class Command(BaseCommand):
    help = "Seed the 11 standard bilingual categories and hide legacy roots."

    def add_arguments(self, parser):
        parser.add_argument(
            "--assign-demo-products",
            action="store_true",
            help="Map demo SPUs to the standard categories by title keywords "
            "and refresh their search documents.",
        )

    def handle(self, *args, **options):
        created_roots = 0
        created_children = 0
        standard_slugs = {entry[0] for entry in STANDARD_CATEGORIES}
        with transaction.atomic():
            for index, (slug, name_en, name_zh, children) in enumerate(STANDARD_CATEGORIES):
                root, root_created = self._upsert(
                    slug=slug, name_en=name_en, name_zh=name_zh, sort_order=index
                )
                if root_created:
                    created_roots += 1
                for child_index, (child_slug, child_en, child_zh) in enumerate(children):
                    child, child_created = self._upsert(
                        slug=child_slug,
                        name_en=child_en,
                        name_zh=child_zh,
                        sort_order=child_index,
                        parent=root,
                    )
                    if child_created:
                        created_children += 1
            hidden = 0
            for legacy in LocalCategory.objects.filter(
                status=LocalCategory.Status.ACTIVE, parent__isnull=True
            ).exclude(slug__in=standard_slugs):
                legacy.status = LocalCategory.Status.HIDDEN
                legacy.save(update_fields=["status", "updated_at"])
                hidden += 1
            assigned = 0
            if options["assign_demo_products"]:
                assigned = self._assign_demo_products()
        self.stdout.write(
            self.style.SUCCESS(
                f"Standard categories seeded: roots created={created_roots}, "
                f"children created={created_children}, legacy roots hidden={hidden}, "
                f"demo products assigned={assigned}."
            )
        )

    def _assign_demo_products(self) -> int:
        from catalog.models import Spu
        from catalog.search_services import rebuild_search_document
        from offers.models import Market

        market = Market.objects.filter(code="GB", is_active=True).first()
        if market is None:
            self.stdout.write(self.style.WARNING("GB market missing; skipped demo assignment."))
            return 0
        fallback = LocalCategory.objects.get(slug=DEMO_FALLBACK_SLUG)
        assigned = 0
        for spu in Spu.objects.all():
            translation = spu.translations.order_by("pk").first()
            title = (translation.title if translation else "").lower()
            category = None
            for slug, keywords in DEMO_KEYWORD_RULES:
                if any(keyword in title for keyword in keywords):
                    category = LocalCategory.objects.filter(slug=slug).first()
                    break
            if category is None:
                category = fallback
            if spu.local_category_id != category.pk:
                spu.local_category = category
                spu.save(update_fields=["local_category", "updated_at"])
                assigned += 1
            rebuild_search_document(spu, market=market)
        return assigned

    def _upsert(self, *, slug, name_en, name_zh, sort_order, parent=None):
        category = LocalCategory.objects.filter(slug=slug).first()
        created = category is None
        if created:
            category = create_local_category(
                name=name_en, slug=slug, parent=parent, sort_order=sort_order
            )
        category.name_en = name_en
        category.name_zh = name_zh
        category.name = name_en
        category.sort_order = sort_order
        category.status = LocalCategory.Status.ACTIVE
        category.save(
            update_fields=["name", "name_en", "name_zh", "sort_order", "status", "updated_at"]
        )
        return category, created
