"""Import compact Joybuy public-page samples for all bestseller tabs.

The checked-in fixture is evidence captured from public pages. Every product
still goes through ``StagingProduct`` and ``import_staging_product``; this
command only activates those live demo rows, maps them to the 11 standard
categories, stores images locally, and rebuilds the GB search documents.
"""

from __future__ import annotations

import json
import mimetypes
import sys
import time
import urllib.request
from pathlib import Path

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from catalog.models import (
    Brand,
    CategoryMapping,
    LocalCategory,
    SourceCatalog,
    SourceCategory,
    Spu,
    SpuTranslation,
    normalize_brand_name,
)
from catalog.override_services import resolve_effective_value
from catalog.search_services import rebuild_search_document
from crawler_control.import_services import import_staging_product
from media.models import MediaAsset, MediaUsage
from media.storage import store_bytes
from offers.models import Market, Offer

CRAWLER_DIR = Path(settings.BASE_DIR).parent / "crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

from joybuy_crawler.ingest import ingest_product_payload  # noqa: E402

DEFAULT_FIXTURE = (
    Path(settings.BASE_DIR) / "catalog" / "fixtures" / "bestseller_demo_2026_11_04.json"
)
EXPECTED_CATEGORIES = {
    "home-living",
    "electronics",
    "beauty-personal-care",
    "small-home-appliances",
    "health-wellness",
    "computers-accessories",
    "clothing-accessories",
    "outdoor-sports",
    "pet-supplies",
    "baby-toddler",
    "games-accessories",
}
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
)


class Command(BaseCommand):
    help = "Import 11-category Joybuy bestseller demo samples through staging."

    def add_arguments(self, parser):
        parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
        parser.add_argument("--per-category", type=int, default=3)
        parser.add_argument("--skip-images", action="store_true")
        parser.add_argument(
            "--only-category",
            choices=sorted(EXPECTED_CATEGORIES),
            help="Retry or refresh one standard category only.",
        )

    def handle(self, *args, **options):
        fixture_path = Path(options["fixture"])
        per_category = options["per_category"]
        if per_category < 1:
            raise CommandError("--per-category must be at least 1.")
        fixture = self._load_fixture(fixture_path)
        market = Market.objects.select_related("default_currency").get(code=fixture["market"])
        groups = fixture["categories"]
        if options["only_category"]:
            groups = [
                group for group in groups if group["local_category"] == options["only_category"]
            ]
        catalog, source_categories = self._ensure_sources(groups)
        del catalog

        imported = 0
        created = 0
        image_failures = 0
        for group in groups:
            local_category = LocalCategory.objects.get(slug=group["local_category"])
            source_category = source_categories[group["local_category"]]
            CategoryMapping.objects.update_or_create(
                local_category=local_category,
                source_category=source_category,
                defaults={"is_primary": True, "confidence": "1.0000"},
            )
            for product in group["products"][:per_category]:
                outcome = self._import_product(
                    product,
                    group=group,
                    market=market,
                    local_category=local_category,
                )
                imported += 1
                created += int(outcome.created_spu)
                if not options["skip_images"] and product.get("image_url"):
                    if not self._attach_image(outcome.spu, product["image_url"]):
                        image_failures += 1
                rebuild_search_document(outcome.spu, market=market)

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {imported} bestseller samples across {len(groups)} categories "
                f"({created} new SPUs, {image_failures} image failures)."
            )
        )

    def _load_fixture(self, path: Path) -> dict:
        if not path.is_file():
            raise CommandError(f"Fixture does not exist: {path}")
        try:
            fixture = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Cannot read fixture: {exc}") from exc
        groups = fixture.get("categories") or []
        slugs = {group.get("local_category") for group in groups}
        if slugs != EXPECTED_CATEGORIES:
            missing = sorted(EXPECTED_CATEGORIES - slugs)
            extra = sorted(slugs - EXPECTED_CATEGORIES)
            raise CommandError(f"Fixture categories mismatch; missing={missing}, extra={extra}.")
        for group in groups:
            if not group.get("source_list_url") or not group.get("products"):
                raise CommandError(f"Incomplete category group: {group.get('local_category')}")
            for product in group["products"]:
                required = {"sku", "title", "source_url", "original_price", "availability"}
                missing = sorted(field for field in required if not product.get(field))
                if missing:
                    raise CommandError(
                        f"Product {product.get('sku', '<unknown>')} is missing {missing}."
                    )
        return fixture

    def _ensure_sources(self, groups: list[dict]):
        catalog, _ = SourceCatalog.objects.get_or_create(
            source_system="joybuy", defaults={"display_name": "Joybuy"}
        )
        now = timezone.now()
        categories = {}
        for group in groups:
            slug = group["local_category"]
            source_id = f"bestseller:{slug}"
            category, _ = SourceCategory.objects.get_or_create(
                catalog=catalog,
                source_id=source_id,
                defaults={"first_seen_at": now, "last_seen_at": now},
            )
            category.is_active = True
            category.last_seen_at = now
            category.save(update_fields=["is_active", "last_seen_at", "updated_at"])
            categories[slug] = category
        return catalog, categories

    def _import_product(self, product, *, group, market, local_category):
        availability = product["availability"]
        payload = {
            "source_id": str(product["sku"]),
            "title": product["title"],
            "currency": market.default_currency.code,
            # Business rule: the fixture stores the crossed-off original price
            # (or the sole visible price when no crossed-off price exists).
            "current_price": product["original_price"],
            "list_price": None,
            "promotion_label": "",
            "availability": availability,
            "brand": product.get("brand") or "",
            "source_category_id": f"bestseller:{group['local_category']}",
            "source_seller_id": "",
            "source_seller_name": "",
            "description": "",
            "skus": [
                {
                    "source_id": str(product["sku"]),
                    "price": product["original_price"],
                    "availability": availability,
                    "specs": [],
                }
            ],
            "image_urls": [product["image_url"]] if product.get("image_url") else [],
            "missing_fields": [],
        }
        staging = ingest_product_payload(
            None,
            payload,
            source_system="joybuy",
            source_url=product["source_url"],
            parser_version="joybuy-bestseller-demo-1",
            structure_version=1,
        )
        locale = group.get("source_locale") or "en-GB"
        outcome = import_staging_product(
            staging,
            market=market,
            currency=market.default_currency,
            locale=locale,
        )
        spu = outcome.spu
        update_fields = []
        if spu.local_category_id != local_category.pk:
            spu.local_category = local_category
            update_fields.append("local_category")
        brand_name = (product.get("brand") or "").strip()
        if brand_name:
            brand = Brand.objects.filter(normalized_name=normalize_brand_name(brand_name)).first()
            if brand is not None and spu.brand_id != brand.pk:
                spu.brand = brand
                update_fields.append("brand")
        if spu.status != Spu.Status.ACTIVE:
            spu.status = Spu.Status.ACTIVE
            update_fields.append("status")
        if update_fields:
            spu.save(update_fields=[*update_fields, "updated_at"])
        for offer in outcome.offers:
            if offer.status != Offer.Status.ACTIVE:
                offer.status = Offer.Status.ACTIVE
                offer.save(update_fields=["status", "updated_at"])

        # The source-value layer is authoritative unless a reviewed local
        # override exists. Materialise that effective value for the current
        # search index, which still reads the translation table directly.
        translation = SpuTranslation.objects.get(spu=spu, locale=locale)
        effective_title = resolve_effective_value(translation, "title")["effective"]
        if effective_title and translation.title != effective_title:
            translation.title = effective_title
            translation.save(update_fields=["title", "updated_at"])
        return outcome

    def _attach_image(self, spu: Spu, url: str) -> bool:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        for attempt in (1, 2):
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    data = response.read()
                    mime_type = (response.headers.get_content_type() or "").lower()
                if not data:
                    raise ValueError("empty image response")
                if not mime_type.startswith("image/"):
                    mime_type = mimetypes.guess_type(url.split("!", 1)[0])[0] or "image/webp"
                asset, _ = store_bytes(
                    data,
                    kind=MediaAsset.Kind.PRODUCT,
                    mime_type=mime_type,
                    source_url=url,
                )
                MediaUsage.objects.get_or_create(
                    asset=asset,
                    content_type=ContentType.objects.get_for_model(Spu),
                    object_id=spu.pk,
                    role="gallery",
                    defaults={"sort_order": 0},
                )
                return True
            except Exception:  # noqa: BLE001 - one image must not abort all 11 tabs
                if attempt == 2:
                    return False
                time.sleep(1)
        return False
