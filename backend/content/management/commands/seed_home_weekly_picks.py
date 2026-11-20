"""Seed the home page for batch O (需求文档03 14.1/14.2/14.4).

Idempotent:
- upsert the six 「每周甄选」 cards in ``HomeCampaignCard`` (section=weekly,
  images served from ``storefront/public/images/weekly-picks``);
- point the 电子产品 discovery card at the locally-hosted real-site phone
  image (14.1: it used to show an instant-noodle photo);
- ensure the published home page snapshot carries the static 「心选品牌」
  (brand_logos) module right below 品类发现 (14.4; no admin config needed).

The weekly module itself is injected at request time by ``storefront_home``
from the card table, so no CMS re-publish is needed for card edits.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from content.models import CmsModule, HomeCampaignCard
from content.services import get_published_page, publish_page

WEEKLY_CARDS = [
    {
        "title": "Adventure awaits",
        "title_zh": "户外探险之旅",
        "subtitle": "Discover more, shop with ease",
        "subtitle_zh": "探索更多，畅享无忧",
        "image_url": "/images/weekly-picks/adventure-awaits.webp",
        "href": "/marketing?activityId=20050029",
    },
    {
        "title": "Little beginnings",
        "title_zh": "宝贝成长第一站",
        "subtitle": "Everything for their first steps",
        "subtitle_zh": "陪伴宝贝每一步",
        "image_url": "/images/weekly-picks/little-beginnings.webp",
        "href": "/marketing?activityId=21090013",
    },
    {
        "title": "Robot revolution",
        "title_zh": "智能机器人革命",
        "subtitle": "Smart helpers for modern living",
        "subtitle_zh": "智能生活新体验",
        "image_url": "/images/weekly-picks/robot-revolution.webp",
        "href": "/marketing?activityId=21090021",
    },
    {
        "title": "Happy paws",
        "title_zh": "萌宠乐园",
        "subtitle": "Treats and toys for happy pets",
        "subtitle_zh": "宠爱每一只毛孩子",
        "image_url": "/images/weekly-picks/happy-paws.webp",
        "href": "/marketing?activityId=21050021",
    },
    {
        "title": "Everyday food favourites",
        "title_zh": "日常美食精选",
        "subtitle": "Pantry picks loved every day",
        "subtitle_zh": "每日餐桌好物",
        "image_url": "/images/weekly-picks/food-favourites.webp",
        "href": "/marketing?activityId=20530005",
    },
    {
        "title": "Upgrade your drive",
        "title_zh": "焕新出行",
        "subtitle": "Gear up for the road ahead",
        "subtitle_zh": "为每一程做好准备",
        "image_url": "/images/weekly-picks/upgrade-your-drive.webp",
        "href": "/marketing?activityId=20490005",
    },
]

# 心选品牌（14.4）：真站是静态展示位，不点击、无后台配置；logo 全部
# 本地托管（var/media，由 Django /media 提供）。
FEATURED_BRANDS = [
    ("McCormick", "/media/cms/original/03/b0/03b08f03699f7577671dfded3ac78781c0fb492698a986fa29ed4373d0e4de44.webp"),
    ("Celeplate", "/media/cms/original/8a/a0/8aa087eac32aa99b5b5a1fce35e47eafa039ca5bd3c9683192d385d85fd11889.webp"),
    ("Encona", "/media/cms/original/3d/a2/3da2c16fda1b868fc04de4272b3f0f36f0757e8eb24eafd99c68926e10d1928d.webp"),
    ("eufy", "/media/cms/original/f5/57/f557b696652d70f4e65d9553c17c945fd5aa7d24d22609e6cee067257617cfcf.webp"),
    ("Tapo", "/media/cms/original/d1/aa/d1aa292b81b0ffc06a1bd32a222396239cd7f31fdad05c95ad884d5314015a1a.webp"),
    ("Nando's", "/media/cms/original/06/fb/06fb673bf905a72c9313f4578bbef43c48904e39d09d2a8b8c5ea90a3b72c5ea.webp"),
    ("C&S", "/media/cms/original/58/19/5819b04892950abfc7d3b7308928978bf015e4ee84fd4637964cda77c885cd20.webp"),
    ("TCL", "/media/cms/original/6e/9e/6e9eddbf153636afc7497111703f877e4032c78b692bf23c4b307ad733af80c3.webp"),
    ("CJ", "/media/cms/original/75/a8/75a8ce0fc63383fbc9585364b184d40694684ccd8174b46426d7995fe634379b.webp"),
    ("Bc Babycare", "/media/cms/original/26/9c/269cb1ca89fde738acbce359f624e5608dc1cdd7b4c3403d5aaadde9d5e18710.webp"),
    ("Midea", "/media/cms/original/c4/a8/c4a8127490d85822f32852a52dfc79f05f85df010eb7717c26f4bd821cddc3b1.webp"),
    ("Healthy Boy Brand", "/media/cms/original/20/09/2009b06e5768966aa2fe449445592aba84311844e2a6a1539be7f5bba144f0e9.webp"),
]


class Command(BaseCommand):
    help = "Seed batch O home weekly picks, discovery electronics image and brands module."

    def handle(self, *args, **options):
        created = updated = 0
        with transaction.atomic():
            for order, card in enumerate(WEEKLY_CARDS, start=1):
                row, was_created = HomeCampaignCard.objects.update_or_create(
                    section=HomeCampaignCard.Section.WEEKLY,
                    href=card["href"],
                    defaults={**card, "sort_order": order, "enabled": True},
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

            # 14.1: electronics tile must show an electronics product image.
            electronics = HomeCampaignCard.objects.filter(
                section=HomeCampaignCard.Section.DISCOVERY,
                href="/s?category=electronics",
            ).first()
            if electronics is not None and electronics.image_url != "/images/discovery/electronics.webp":
                electronics.image_url = "/images/discovery/electronics.webp"
                electronics.save(update_fields=["image_url", "updated_at"])

            brands_added = self.ensure_brands_module()

        self.stdout.write(
            self.style.SUCCESS(
                f"Weekly cards: created={created}, updated={updated}; "
                f"brands module {'published' if brands_added else 'already present'}."
            )
        )

    def ensure_brands_module(self) -> bool:
        page = get_published_page("home")
        if page is None:
            self.stderr.write("Home page is not published; skipped brands module.")
            return False
        existing = list(page.modules.all())
        if any(
            module.module_type == CmsModule.Type.LINK_GRID
            and (module.payload or {}).get("variant") == "brand_logos"
            for module in existing
        ):
            return False
        modules = [
            {"module_type": module.module_type, "payload": module.payload} for module in existing
        ]
        brands_module = {
            "module_type": CmsModule.Type.LINK_GRID,
            "payload": {
                "title": "Brands we love",
                "title_zh": "心选品牌",
                "variant": "brand_logos",
                "items": [{"label": name, "icon_path": image} for name, image in FEATURED_BRANDS],
            },
        }
        # Real order: 品类发现 → 心选品牌 → 每周甄选（weekly is injected later,
        # after every snapshot module).
        insert_at = next(
            (
                index + 1
                for index, module in enumerate(existing)
                if module.module_type == CmsModule.Type.LINK_GRID
                and (module.payload or {}).get("variant") == "tiles"
            ),
            len(modules),
        )
        modules.insert(insert_at, brands_module)
        publish_page(page_key="home", title=page.title, modules=modules)
        return True
