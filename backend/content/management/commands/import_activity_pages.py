"""Import activity/store pages from a bundle produced by export_activity_pages.

The bundle is keyed by source identity (``joybuy_uk:<source_id>``), so each
environment resolves its own SPUs/SKUs. Items whose product is not present in
the target catalog are skipped and reported — deploy the goods first, then
re-run this command to backfill.

Default is DRY RUN. Usage (repo root):
    .venv/Scripts/python.exe backend/manage.py import_activity_pages --bundle /abs/path/activity_pages.json
    .venv/Scripts/python.exe backend/manage.py import_activity_pages --bundle /abs/path/activity_pages.json --apply
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import SkuSourceIdentity, SpuSourceIdentity
from content.models import ActivityPage, ActivitySection, ActivitySectionProduct, HomeCampaignCard

SOURCE_SYSTEM = "joybuy_uk"


class Command(BaseCommand):
    help = "Import activity pages (sections/products resolved by source identity)."

    def add_arguments(self, parser):
        parser.add_argument("--bundle", required=True, help="Bundle JSON path")
        parser.add_argument("--apply", action="store_true", help="Write to the database")
        parser.add_argument(
            "--skip-cards",
            action="store_true",
            help="Do not touch home campaign cards",
        )

    def handle(self, *args, **options):
        path = Path(options["bundle"]).expanduser().resolve()
        if not path.exists():
            raise CommandError(f"bundle not found: {path}")
        bundle = json.loads(path.read_text(encoding="utf-8"))
        apply = bool(options["apply"])

        pages = bundle.get("pages") or []
        spu_ids = {
            item["spu_source_id"]
            for page in pages
            for section in page.get("sections", [])
            for item in section.get("items", [])
            if item.get("spu_source_id")
        }
        sku_ids = {
            item["sku_source_id"]
            for page in pages
            for section in page.get("sections", [])
            for item in section.get("items", [])
            if item.get("sku_source_id")
        }

        spu_map: dict[str, int] = {}
        for row in SpuSourceIdentity.objects.filter(
            source_system=SOURCE_SYSTEM, source_id__in=spu_ids
        ):
            spu_map.setdefault(row.source_id, row.spu_id)
        sku_map: dict[str, int] = {}
        for row in SkuSourceIdentity.objects.filter(
            source_system=SOURCE_SYSTEM, source_id__in=sku_ids
        ):
            sku_map.setdefault(row.source_id, row.sku_id)

        missing_spu = sorted(spu_ids - set(spu_map))
        self.stdout.write(
            f"bundle pages={len(pages)} | resolved spu={len(spu_map)}/{len(spu_ids)} "
            f"sku={len(sku_map)}/{len(sku_ids)} | missing_spu={len(missing_spu)}"
        )
        if not apply:
            self.stdout.write("DRY RUN (no writes). Use --apply to import.")

        total_items = 0
        skipped_items = 0
        for page_row in pages:
            page_kind = page_row["kind"]
            external_id = page_row["external_id"]
            page_defaults = {
                key: page_row[key]
                for key in (
                    "title",
                    "title_zh",
                    "store_name",
                    "logo_image",
                    "source_url",
                    "hero_image",
                    "background_color",
                    "enabled",
                    "sort_order",
                )
                if key in page_row
            }
            sections = page_row.get("sections") or []
            resolved_sections = []
            for section in sections:
                items = []
                for item in section.get("items", []):
                    spu_pk = spu_map.get(item.get("spu_source_id", ""))
                    if not spu_pk:
                        skipped_items += 1
                        continue
                    sku_pk = sku_map.get(item.get("sku_source_id") or "") if item.get("sku_source_id") else None
                    items.append((spu_pk, sku_pk, item.get("sort_order", 0)))
                resolved_sections.append((section, items))
                total_items += len(items)

            self.stdout.write(
                f"  {page_kind:8s} {external_id} sections={len(sections)} items={sum(len(i) for _, i in resolved_sections)}"
            )
            if not apply:
                continue

            with transaction.atomic():
                page, _created = ActivityPage.objects.update_or_create(
                    kind=page_kind, external_id=external_id, defaults=page_defaults
                )
                page.sections.all().delete()
                for section, items in resolved_sections:
                    created = ActivitySection.objects.create(
                        page=page,
                        kind=section["kind"],
                        title=section.get("title", ""),
                        title_zh=section.get("title_zh", ""),
                        title_color=section.get("title_color", ""),
                        title_background=section.get("title_background", ""),
                        image_url=section.get("image_url", ""),
                        href=section.get("href", ""),
                        columns=section.get("columns", 5),
                        show_more=section.get("show_more", False),
                        extra=section.get("extra") or {},
                        sort_order=section.get("sort_order", 0),
                    )
                    seen = set()
                    rows = []
                    for spu_pk, sku_pk, order in items:
                        key = (spu_pk, sku_pk)
                        if key in seen:
                            continue
                        seen.add(key)
                        rows.append(
                            ActivitySectionProduct(
                                section=created, spu_id=spu_pk, sku_id=sku_pk, sort_order=order
                            )
                        )
                    ActivitySectionProduct.objects.bulk_create(rows)

        if apply and not options["skip_cards"]:
            cards = bundle.get("home_cards") or []
            updated = 0
            created = 0
            for card in cards:
                section = card.get("section", "campaign")
                row = (
                    HomeCampaignCard.objects.filter(
                        section=section, sort_order=card["sort_order"]
                    )
                    .order_by("pk")
                    .first()
                )
                if row is None:
                    HomeCampaignCard.objects.create(
                        section=section,
                        sort_order=card["sort_order"],
                        title=card.get("title", ""),
                        title_zh=card.get("title_zh", ""),
                        subtitle=card.get("subtitle", ""),
                        subtitle_zh=card.get("subtitle_zh", ""),
                        image_url=card.get("image_url", ""),
                        href=card.get("href", ""),
                        enabled=card.get("enabled", True),
                    )
                    created += 1
                    continue
                row.title = card.get("title", row.title)
                row.title_zh = card.get("title_zh", row.title_zh)
                row.subtitle = card.get("subtitle", row.subtitle)
                row.subtitle_zh = card.get("subtitle_zh", row.subtitle_zh)
                row.image_url = card.get("image_url", row.image_url)
                row.href = card.get("href", row.href)
                row.enabled = card.get("enabled", row.enabled)
                row.save()
                updated += 1
            self.stdout.write(f"home cards updated: {updated}, created: {created}")

        self.stdout.write(
            f"{'IMPORTED' if apply else 'WOULD IMPORT'} items={total_items} skipped={skipped_items}"
        )
        if missing_spu:
            preview = ", ".join(missing_spu[:10])
            self.stdout.write(
                f"WARNING: {len(missing_spu)} source products are absent from this catalog; "
                f"those slots were skipped. Preview: {preview}"
            )
            self.stdout.write("Run the goods sync/crawl first, then re-run this command.")
