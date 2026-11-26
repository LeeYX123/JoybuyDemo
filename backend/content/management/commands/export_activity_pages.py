"""Export activity/store pages as a portable JSON bundle (deploy helper).

Why: ``ActivityPage`` rows reference catalog SPUs by primary key, and those
PKs differ between the local dev database and the server. This command writes
a bundle keyed by **source identity** (``joybuy_uk:<source_id>``) so the
receiving side can resolve its own SPUs and report anything it cannot find.

Usage (repo root):
    .venv/Scripts/python.exe backend/manage.py export_activity_pages --out var/deploy/activity_pages.json
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from catalog.models import SkuSourceIdentity, SpuSourceIdentity
from content.models import ActivityPage, ActivitySection, HomeCampaignCard

SOURCE_SYSTEM = "joybuy_uk"


class Command(BaseCommand):
    help = "Export activity pages + home campaign cards into a portable JSON bundle."

    def add_arguments(self, parser):
        parser.add_argument("--out", required=True, help="Output JSON path")
        parser.add_argument(
            "--kind",
            default="",
            help="Only export this kind (ACTIVITY / STORE); default: all",
        )

    def handle(self, *args, **options):
        out = Path(options["out"]).resolve()
        kind = (options["kind"] or "").upper()

        pages = ActivityPage.objects.all().order_by("kind", "external_id")
        if kind:
            pages = pages.filter(kind=kind)

        # source_id → spu / sku（导出时把主键换成来源身份）
        spu_source: dict[int, str] = {}
        sku_source: dict[int, str] = {}
        needed_spu: set[int] = set()
        needed_sku: set[int] = set()
        page_rows = []
        static_files: set[str] = set()

        for page in pages.prefetch_related("sections__items"):
            sections = []
            if page.hero_image.startswith("/"):
                static_files.add(page.hero_image)
            if page.logo_image.startswith("/"):
                static_files.add(page.logo_image)
            for section in page.sections.all().order_by("sort_order", "pk"):
                items = list(section.items.all().order_by("sort_order", "pk"))
                needed_spu.update(item.spu_id for item in items)
                needed_sku.update(item.sku_id for item in items if item.sku_id)
                if section.image_url.startswith("/"):
                    static_files.add(section.image_url)
                for value in (section.extra or {}).values():
                    if isinstance(value, str) and value.startswith("/"):
                        static_files.add(value)
                    elif isinstance(value, list):
                        static_files.update(v for v in value if isinstance(v, str) and v.startswith("/"))
                sections.append(
                    {
                        "kind": section.kind,
                        "title": section.title,
                        "title_zh": section.title_zh,
                        "title_color": section.title_color,
                        "title_background": section.title_background,
                        "image_url": section.image_url,
                        "href": section.href,
                        "columns": section.columns,
                        "show_more": section.show_more,
                        "extra": section.extra,
                        "sort_order": section.sort_order,
                        "items": [
                            {"spu_id": item.spu_id, "sku_id": item.sku_id, "sort_order": item.sort_order}
                            for item in items
                        ],
                    }
                )
            page_rows.append(
                {
                    "kind": page.kind,
                    "external_id": page.external_id,
                    "title": page.title,
                    "title_zh": page.title_zh,
                    "store_name": page.store_name,
                    "logo_image": page.logo_image,
                    "source_url": page.source_url,
                    "hero_image": page.hero_image,
                    "background_color": page.background_color,
                    "enabled": page.enabled,
                    "sort_order": page.sort_order,
                    "sections": sections,
                }
            )

        for row in SpuSourceIdentity.objects.filter(
            source_system=SOURCE_SYSTEM, spu_id__in=needed_spu
        ):
            spu_source.setdefault(row.spu_id, row.source_id)
        for row in SkuSourceIdentity.objects.filter(
            source_system=SOURCE_SYSTEM, sku_id__in={s for s in needed_sku if s}
        ):
            sku_source.setdefault(row.sku_id, row.source_id)

        unresolved: list[dict] = []
        for page in page_rows:
            for section in page["sections"]:
                converted = []
                for item in section.pop("items"):
                    spu_source_id = spu_source.get(item["spu_id"])
                    sku_source_id = sku_source.get(item["sku_id"]) if item["sku_id"] else None
                    if not spu_source_id:
                        unresolved.append(
                            {"external_id": page["external_id"], "spu_pk": item["spu_id"], "sku_pk": item["sku_id"]}
                        )
                        continue
                    converted.append(
                        {
                            "spu_source_id": spu_source_id,
                            "sku_source_id": sku_source_id,
                            "sort_order": item["sort_order"],
                        }
                    )
                section["items"] = converted

        cards = [
            {
                "section": card.section,
                "sort_order": card.sort_order,
                "title": card.title,
                "title_zh": card.title_zh,
                "subtitle": card.subtitle,
                "subtitle_zh": card.subtitle_zh,
                "image_url": card.image_url,
                "href": card.href,
                "enabled": card.enabled,
            }
            for card in HomeCampaignCard.objects.filter(section="campaign").order_by("sort_order")
        ]
        for card in cards:
            if card["image_url"].startswith("/"):
                static_files.add(card["image_url"])

        bundle = {
            "generated_at": timezone.now().isoformat(),
            "source_system": SOURCE_SYSTEM,
            "pages": page_rows,
            "home_cards": cards,
            "static_files": sorted(static_files),
            "unresolved_items": unresolved,
        }
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(bundle, ensure_ascii=False, indent=1), encoding="utf-8")

        total_items = sum(len(s["items"]) for p in page_rows for s in p["sections"])
        self.stdout.write(
            f"pages={len(page_rows)} sections={sum(len(p['sections']) for p in page_rows)} "
            f"items={total_items} cards={len(cards)} static={len(static_files)} "
            f"unresolved={len(unresolved)}"
        )
        self.stdout.write(f"written: {out}")
