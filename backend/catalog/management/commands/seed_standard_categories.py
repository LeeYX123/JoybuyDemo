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
# Anything unmatched falls back to rice/pasta/noodles (the demo inventory is
# mostly ambient food). 2026-11-11 one-to-one taxonomy: the old
# groceries-food bucket was split into 24 Joybuy-aligned children, so the
# fallback now targets rice-pasta-pulses.
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
DEMO_FALLBACK_SLUG = "rice-pasta-pulses"

# (slug, name_en, name_zh, [(child slug, child en, child zh), ...])
# 2026-11-11 one-to-one taxonomy: children are the legacy base nodes whose
# slugs/names are aligned with the Joybuy menu (sync_local_categories_from_joybuy
# owns the full Joybuy set and Joybuy sort orders; children sort_order is only
# set on creation so re-running seed never fights the sync ordering).
STANDARD_CATEGORIES = [
    (
        "home-living",
        "Home & Living",
        "家居生活",
        [
            ("kitchen-essentials", "Kitchen & Dining", "厨房与餐厅用品"),
            ("home-storage", "Storage & Organisation", "整理收纳"),
            ("bedding-textiles", "Bedding", "床上用品"),
            ("cleaning-supplies", "Cleaning", "清洁用品"),
            ("rice-pasta-pulses", "Rice, Pasta & Pulses", "米面杂粮"),
        ],
    ),
    (
        "electronics",
        "Electronics",
        "电子产品",
        [
            ("mobile-phones", "Phones", "手机"),
            ("tablets", "Tablets", "平板电脑"),
            ("soundbars-home-cinema", "Soundbars & Home Cinema", "音响 & 家庭影院"),
            ("cameras-photo", "Camera & Photo", "摄影摄像"),
            ("smart-home", "Smart Home", "智能家居"),
        ],
    ),
    (
        "beauty-personal-care",
        "Beauty & Personal Care",
        "美妆个人护理",
        [
            ("skincare", "Face Care", "面部护肤"),
            ("makeup", "Makeup", "彩妆"),
            ("body-hair-care", "Body", "身体护理"),
            ("fragrance", "Fragrance", "香水"),
        ],
    ),
    (
        "small-home-appliances",
        "Small Home Appliances",
        "小家电",
        [
            ("kitchen-appliances", "Oven & Hobs", "厨房电器"),
            ("cleaning-appliances", "Floorcare", "地板清洁电器"),
        ],
    ),
    (
        "health-wellness",
        "Health & Wellness",
        "健康与保健",
        [
            ("nutrition-supplements", "Vitamins & Supplements", "维生素 & 补充剂"),
            ("health-monitors", "Healthcare devices", "电子健康检测"),
            ("massage-relaxation", "Massage & Relaxation", "按摩与舒缓"),
        ],
    ),
    (
        "computers-accessories",
        "Computers & Accessories",
        "计算机与配件",
        [
            ("laptops", "Laptops", "笔记本电脑"),
            ("desktop-pcs", "Desktop PCs", "台式电脑"),
            ("peripherals", "Mouse, Keyboard & Accessories", "键盘、鼠标及输入设备"),
        ],
    ),
    (
        "clothing-accessories",
        "Clothing & Accessories",
        "服装与配饰",
        [
            ("womens-clothing", "Women's Clothing & Accessories", "女装 & 配饰"),
            ("mens-clothing", "Men's Clothing & Accessories", "男装 & 配饰"),
            ("jewellery", "Jewellery", "珠宝"),
            ("watches", "Watches", "手表"),
            ("bags-luggage", "Bags & Luggage", "箱包手袋"),
            ("shoes-boots", "Footwear", "时尚鞋靴"),
        ],
    ),
    (
        "outdoor-sports",
        "Outdoor & Sports",
        "户外运动",
        [
            ("fitness-training", "Sports & Leisure", "体育与休闲"),
            ("outdoor-gear", "Outdoors", "户外"),
        ],
    ),
    (
        "pet-supplies",
        "Pet Supplies",
        "宠物用品",
        [
            ("dog-food", "Dog Food", "狗粮"),
            ("cat-food", "Cat Food", "猫粮"),
            ("cat-toys", "Cat Toys", "猫玩具"),
            ("pet-grooming", "Pet Grooming", "宠物美容护理"),
        ],
    ),
    (
        "baby-toddler",
        "Baby & Toddler",
        "婴幼儿用品",
        [
            ("baby-feeding", "Nursing & Feeding", "婴儿哺育喂养"),
            ("diapers-wipes", "Nappies & Pants", "婴幼儿纸尿裤"),
            ("infant-pre-school-toys", "Infant & Pre-school Toys", "婴幼儿学前玩具"),
        ],
    ),
    (
        "games-accessories",
        "Games & Accessories",
        "游戏及配件",
        [
            ("consoles", "Consoles", "游戏机"),
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
                        update_sort=False,
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

    def _upsert(self, *, slug, name_en, name_zh, sort_order, parent=None, update_sort=True):
        category = LocalCategory.objects.filter(slug=slug).first()
        created = category is None
        if created:
            category = create_local_category(
                name=name_en, slug=slug, parent=parent, sort_order=sort_order
            )
        category.name_en = name_en
        category.name_zh = name_zh
        category.name = name_en
        # Children keep their existing sort_order: the Joybuy sync owns the
        # Joybuy menu ordering; overwriting it here would fight that sync.
        if update_sort or created:
            category.sort_order = sort_order
        category.status = LocalCategory.Status.ACTIVE
        fields = ["name", "name_en", "name_zh", "status", "updated_at"]
        if update_sort or created:
            fields.append("sort_order")
        category.save(update_fields=fields)
        return category, created
