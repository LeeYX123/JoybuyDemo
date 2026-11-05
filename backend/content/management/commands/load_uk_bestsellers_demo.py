"""Import the real joybuy.co.uk bestsellers-floor products as demo stock.

The storefront's Bestsellers floor serves its cards from the search API, so
this command imports the products that the live joybuy.co.uk homepage shows
in that floor (crawled with a real browser into
``var/joybuy_demo/data/uk_bestsellers_raw.json`` — 10 UK tabs, transparent
``.png.webp`` product images, £ prices). Unlike the ``load_joybuy_demo``
stock (white-background .com jpg images without a transparent CDN variant),
these images carry alpha so the storefront's #F5F5F5 image area shows
through.

Everything else mirrors ``load_joybuy_demo``: products go through the normal
ingest/staging import and are activated for the demo, images are stored in
the local media library, and search documents are rebuilt. Each UK tab is
mapped onto our 11 standard categories (their subtrees) so the storefront's
standard tabs surface the products; prices stay GBP in storage (the $ symbol
is a display-layer rule only).

Idempotent: source ids are derived from the product title + image url, so
re-runs update in place instead of duplicating.
"""

import hashlib
import json
import re
import sys
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.utils import timezone

from catalog.models import LocalCategory, SourceCatalog, SourceCategory, Spu
from catalog.search_services import rebuild_search_document
from crawler_control.import_services import import_staging_product
from crawler_control.models import CrawlerAccount, CrawlJob, CrawlRun
from crawler_control.services import (
    create_crawl_job,
    create_crawler_account,
    mark_job_ready,
    start_run,
)
from media.models import MediaUsage
from media.storage import store_bytes
from offers.models import Market, Offer

# The staging ingestion lives in the crawler package (repo-root /crawler).
CRAWLER_DIR = Path(settings.BASE_DIR).parent / "crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

from joybuy_crawler.ingest import ingest_product_payload  # noqa: E402

DATA_FILE = (
    Path(settings.BASE_DIR).parent / "var" / "joybuy_demo" / "data" / "uk_bestsellers_raw.json"
)
SOURCE_HOME = "https://www.joybuy.co.uk/"
SOURCE_SYSTEM = "joybuy_uk"

# UK bestseller tab -> our standard child-category slug (requirement 5-1:
# the storefront tabs use the 11 standard categories; these subtrees surface
# the UK products under the matching standard tab).
TAB_CATEGORY_MAP = {
    "Kitchen Roll, Toilet Roll & Tissues": "cleaning-supplies",
    "Food Cupboard": "groceries-food",
    "Frozen Food": "groceries-food",
    "Beverages": "groceries-food",
    "Small Kitchen Appliances": "kitchen-appliances",
    "Softdrinks": "groceries-food",
    "Rice, Pasta & Pulses": "groceries-food",
    "Table Sauces, Condiments & Dressings": "groceries-food",
    "Instant Noodle": "groceries-food",
    "Cooking Ingredients": "groceries-food",
}
FALLBACK_CATEGORY_SLUG = "groceries-food"


class Command(BaseCommand):
    help = "Import joybuy.co.uk bestsellers-floor products (transparent images)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-images",
            action="store_true",
            help="Skip downloading the transparent product images.",
        )

    # ------------------------------------------------------------------ #
    # Source plumbing (same pattern as load_joybuy_demo)                  #
    # ------------------------------------------------------------------ #

    def ensure_source(self, category_ids: set[str]):
        catalog = SourceCatalog.objects.get_or_create(
            source_system=SOURCE_SYSTEM,
            defaults={"display_name": "Joybuy UK"},
        )[0]
        now = timezone.now()
        categories = {}
        for category_id in sorted(category_ids):
            categories[category_id] = SourceCategory.objects.get_or_create(
                catalog=catalog,
                source_id=category_id,
                defaults={"first_seen_at": now, "last_seen_at": now},
            )[0]
        return catalog, categories

    def ensure_run(self, catalog, category, market) -> CrawlRun:
        existing = CrawlRun.objects.filter(job__source_catalog=catalog).order_by("-pk").first()
        if existing is not None and existing.job.status == CrawlJob.Status.RUNNING:
            return existing
        # Fixture import only — it never crawls, so it must not fake a
        # "VALID" session (that made accounts look logged-in with zero
        # cookies; 2026-11-05 login-wall bug). start_run allows runs
        # without an account.
        if not CrawlerAccount.objects.filter(account_group="default").exists():
            create_crawler_account(label="Joybuy UK demo", account_group="default")
        job = create_crawl_job(
            name="Joybuy UK bestsellers demo import",
            market=market,
            source_catalog=catalog,
            source_category=category,
            product_limit=500,
            currency=market.default_currency,
        )
        start_run(mark_job_ready(job))
        return CrawlRun.objects.filter(job=job).order_by("-pk").first()

    # ------------------------------------------------------------------ #
    # Import                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def source_id(item: dict) -> str:
        digest = hashlib.md5(f"{item['title']}|{item['img']}".encode("utf-8")).hexdigest()
        return f"uk-best-{digest[:24]}"

    @staticmethod
    def parse_price(price_text: str) -> str:
        match = re.search(r"\d+(?:\.\d{1,2})?", price_text or "")
        if not match:
            return "9.99"
        try:
            return str(Decimal(match.group(0)))
        except InvalidOperation:
            return "9.99"

    def download_image(self, url: str) -> bytes | None:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.read()
        except Exception:  # noqa: BLE001 - one bad image must not stop us
            return None

    def handle(self, *args, **options):
        skip_images = options["skip_images"]
        if not DATA_FILE.is_file():
            self.stderr.write(f"Data file missing: {DATA_FILE}. Crawl it first.")
            return
        groups = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        market = Market.objects.filter(code="GB", is_active=True).first()
        if market is None:
            self.stderr.write("Market GB is not configured; aborting.")
            return

        category_ids = set(TAB_CATEGORY_MAP.keys())
        catalog, categories = self.ensure_source(category_ids)
        fallback_category = categories.get("Food Cupboard", next(iter(categories.values())))
        run = self.ensure_run(catalog, fallback_category, market)

        imported = 0
        transparent = 0
        image_failures = 0
        for group in groups:
            # SourceCategory (source bookkeeping) vs LocalCategory (the
            # storefront tree the SPU belongs to) are different models; the
            # SPU gets the mapped LocalCategory.
            category = LocalCategory.objects.filter(
                slug=TAB_CATEGORY_MAP.get(group["tab"], FALLBACK_CATEGORY_SLUG)
            ).first()
            for item in group["items"]:
                source_id = self.source_id(item)
                price = self.parse_price(item["price"])
                payload = {
                    "source_id": source_id,
                    "title": item["title"],
                    "currency": market.default_currency.code,
                    "current_price": price,
                    "list_price": None,
                    "promotion_label": "",
                    "availability": "IN_STOCK",
                    "brand": "",
                    "source_category_id": group["tab"],
                    "source_seller_id": "",
                    "source_seller_name": "",
                    "description": "",
                    "rating_count": None,
                    "rating_average": None,
                    "skus": [
                        {
                            "source_id": source_id,
                            "price": price,
                            "availability": "IN_STOCK",
                            "specs": [],
                        }
                    ],
                    "image_urls": [],
                    "missing_fields": [],
                }
                staging = ingest_product_payload(
                    run,
                    payload,
                    source_system=SOURCE_SYSTEM,
                    source_url=SOURCE_HOME,
                    parser_version="joybuy-uk-bestsellers-1",
                    structure_version=1,
                )
                outcome = import_staging_product(
                    staging,
                    market=market,
                    currency=market.default_currency,
                    locale="en-GB",
                )
                spu = outcome.spu
                if spu.status != Spu.Status.ACTIVE:
                    spu.status = Spu.Status.ACTIVE
                    spu.save(update_fields=["status", "updated_at"])
                for offer in outcome.offers:
                    if offer.status != Offer.Status.ACTIVE:
                        offer.status = Offer.Status.ACTIVE
                        offer.save(update_fields=["status", "updated_at"])
                if category is not None and spu.local_category_id != category.pk:
                    spu.local_category = category
                    spu.save(update_fields=["local_category", "updated_at"])
                rebuild_search_document(spu, market=market)
                imported += 1

                if skip_images or not item["img"]:
                    continue
                data = self.download_image(item["img"])
                if data is None:
                    image_failures += 1
                    continue
                transparent += 1
                asset, _created = store_bytes(
                    data,
                    kind="PRODUCT",
                    mime_type="image/webp",
                    source_url=item["img"],
                )
                spu_type = ContentType.objects.get_for_model(Spu)
                MediaUsage.objects.get_or_create(
                    asset=asset,
                    content_type=spu_type,
                    object_id=spu.pk,
                    role="gallery",
                    defaults={"sort_order": 0},
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"UK bestsellers imported: {imported} products "
                f"({transparent} transparent images, {image_failures} image failures)."
            )
        )
