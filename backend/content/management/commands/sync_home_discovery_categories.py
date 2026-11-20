"""Align the homepage category-discovery tiles with the top navigation.

Batch H acceptance fix (2026-11-19): the tiles used a hard-coded 6-card demo
fixture, so renamed roots still showed their old labels and a nav-hidden root
(Clothing & Accessories) was still visible.

This command keeps the existing card rows (images/admin config are preserved)
and, for every visible navigation root, ensures one enabled card exists in the
navigation order. Missing cards are created with the first child category's
local tile image (``/images/categories/<slug>.webp``). Hidden-root cards are
left untouched in the database — the storefront filters them by the backend
``NAV_HIDDEN_ROOT_SLUGS`` flag, so display and data stay separate.
"""

import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import LocalCategory
from catalog.search_views import NAV_HIDDEN_ROOT_SLUGS
from content.models import HomeCampaignCard

CATEGORY_PATTERNS = (
    re.compile(r"[?&]category=([^&#]+)"),
    re.compile(r"^/c/([^/?#]+)"),
)
IMAGE_DIR = Path(settings.REPOSITORY_ROOT) / "storefront" / "public" / "images" / "categories"


def category_slug(href: str) -> str:
    for pattern in CATEGORY_PATTERNS:
        match = pattern.search(href or "")
        if match:
            return match.group(1)
    return ""


class Command(BaseCommand):
    help = "Align homepage discovery tiles with the visible navigation roots."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        roots = list(
            LocalCategory.objects.filter(depth=0, status=LocalCategory.Status.ACTIVE)
            .exclude(slug__in=NAV_HIDDEN_ROOT_SLUGS)
            .order_by("sort_order", "path", "pk")
        )
        cards = list(
            HomeCampaignCard.objects.filter(section=HomeCampaignCard.Section.DISCOVERY).order_by(
                "sort_order", "pk"
            )
        )
        by_slug = {}
        for card in cards:
            slug = category_slug(card.href)
            by_slug.setdefault(slug, card)

        created = updated = 0
        with transaction.atomic():
            for index, root in enumerate(roots):
                card = by_slug.get(root.slug)
                if card is None:
                    image = self.child_image(root)
                    if dry_run:
                        created += 1
                        continue
                    HomeCampaignCard.objects.create(
                        section=HomeCampaignCard.Section.DISCOVERY,
                        title=root.name_en or root.name,
                        title_zh=root.name_zh,
                        image_url=image,
                        href=f"/s?category={root.slug}",
                        sort_order=index,
                        enabled=True,
                    )
                    created += 1
                    continue
                changed = False
                if card.sort_order != index:
                    card.sort_order = index
                    changed = True
                if not card.enabled:
                    card.enabled = True
                    changed = True
                if card.title != (root.name_en or root.name):
                    card.title = root.name_en or root.name
                    changed = True
                if card.title_zh != root.name_zh:
                    card.title_zh = root.name_zh
                    changed = True
                if changed and not dry_run:
                    card.save(
                        update_fields=["sort_order", "enabled", "title", "title_zh", "updated_at"]
                    )
                if changed:
                    updated += 1
        mode = "DRY RUN" if dry_run else "synced"
        self.stdout.write(
            self.style.SUCCESS(
                f"Home discovery {mode}: visible roots={len(roots)}, cards created={created}, "
                f"updated={updated}, hidden-root cards kept untouched."
            )
        )

    def child_image(self, root: LocalCategory) -> str:
        for child in root.children.order_by("sort_order", "path", "pk"):
            path = IMAGE_DIR / f"{child.slug}.webp"
            if path.is_file():
                return f"/images/categories/{child.slug}.webp"
        return ""
