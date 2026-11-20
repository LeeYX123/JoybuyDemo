"""Align the PDP breadcrumb category with the local outdoor category.

Batch O acceptance follow-up (2026-11-20): two products shown on the
``/marketing`` activity page carried ``local_category=outdoor-gear`` (so the
recommendations API and category filters treat them as Outdoor & Sports) but
their ``product_category`` — the source category rendered by the PDP
breadcrumb — was Cookware / Garden. Result: PDP showed "Cookware" or "Garden"
for an Outdoor product.

This command re-points only those two SPUs' ``product_category`` at a node
under Sports & Outdoor, keeping the two classification axes consistent
without changing product ownership, offers or the activity-page filter.
Idempotent; ``--dry-run`` prints the planned changes.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import ProductCategory, Spu

# public_id -> product-category source_id under Sports & Outdoor.
# 4625 = Camping & Hiking (portable camping stove)
# 1819 = Sports & Outdoor root (patio dining chairs; no closer outdoor node)
PRODUCT_TARGETS = {
    "f0941496-c057-4b79-8dff-92cc59ec26a3": "4625",
    "35b8c0a8-5c7b-4490-9e44-99605e1a45b4": "1819",
}

OUTDOOR_ROOT_SOURCE_ID = "1819"


def _root(category: ProductCategory) -> ProductCategory:
    node = category
    while node.parent_id is not None:
        node = node.parent
    return node


class Command(BaseCommand):
    help = "Align marketing product PDP breadcrumb categories with Outdoor & Sports."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        outdoor_root = ProductCategory.objects.filter(
            source_id=OUTDOOR_ROOT_SOURCE_ID
        ).first()
        if outdoor_root is None:
            raise CommandError("Sports & Outdoor product category is missing.")

        changed = []
        with transaction.atomic():
            for public_id, target_source_id in PRODUCT_TARGETS.items():
                spu = Spu.objects.select_related("local_category", "product_category").filter(
                    public_id=public_id
                ).first()
                if spu is None:
                    self.stderr.write(f"SPU {public_id} not found; skipped.")
                    continue
                if spu.local_category is None or not spu.local_category.slug.startswith(
                    "outdoor"
                ):
                    self.stderr.write(
                        f"SPU {public_id} local_category is not outdoor; skipped."
                    )
                    continue
                target = ProductCategory.objects.filter(source_id=target_source_id).first()
                if target is None:
                    self.stderr.write(
                        f"Product category {target_source_id} not found; skipped {public_id}."
                    )
                    continue
                if _root(target).pk != outdoor_root.pk:
                    self.stderr.write(
                        f"Target {target.name} is not under Sports & Outdoor; skipped."
                    )
                    continue
                if spu.product_category_id == target.pk:
                    continue
                changed.append(
                    (
                        str(spu.public_id),
                        spu.product_category.name if spu.product_category else "—",
                        target.name,
                    )
                )
                if not dry_run:
                    spu.product_category = target
                    spu.save(update_fields=["product_category", "updated_at"])

        for public_id, old, new in changed:
            self.stdout.write(f"{public_id}: {old} -> {new}")
        mode = "DRY RUN" if dry_run else "aligned"
        self.stdout.write(
            self.style.SUCCESS(f"Outdoor PDP categories {mode}: changed={len(changed)}.")
        )
