"""Build a Joybuy-look homepage demo from the real Joybuy public homepage.

One polite fetch of ``https://www.joybuy.com/`` (or ``--html`` with a saved
copy), decode the embedded React flight stream, and reuse what the page
publicly exposes:

- bestseller floors (section title + ~10 products each) become CMS
  ``product_pool`` modules backed by real imported catalog rows;
- the marketing campaign tiles ("Offers for you") become a ``campaign_grid``
  module; category discovery is the fixed 6-category ``link_grid`` (docs/12
  requirement 3) and the quick-entry icon row is dropped (requirement 2);
  the brand wall becomes a plain ``link_grid``.

Business rules (2026-11-03): only ORIGINAL prices are taken
(``crossOffPrice``); the discounted ``mainPrice`` and discount labels are
never stored. Images are downloaded into local media storage (``var/media``,
served at ``/media/``) — no third-party CDN references in the storefront.
Imported products are activated immediately (skipping the curation draft
state) because they are live bestsellers on the public source homepage.

Idempotent: re-running refreshes staging, offers and the CMS page version.
"""

import json
import re
import sys
import time
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from catalog.models import SourceCatalog, SourceCategory, Spu
from catalog.search_services import rebuild_search_document
from content.services import publish_page
from crawler_control.import_services import import_staging_product
from crawler_control.models import CrawlJob, CrawlRun
from crawler_control.services import (
    create_crawl_job,
    create_crawler_account,
    mark_job_ready,
    record_account_session,
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

JOYBUY_HOME_URL = "https://www.joybuy.com/"
SAVED_HTML = Path(settings.BASE_DIR).parent / "var" / "joybuy_demo" / "data" / "home_raw.html"
GENERATED_FIXTURE = (
    Path(settings.BASE_DIR).parent / "var" / "joybuy_demo" / "data" / "generated_home_fixture.json"
)
PRODUCT_IMAGE_BASE = "https://images4.joy-sourcing.com/product/s360x360_"
TILE_IMAGE_BASE = "https://images3.joy-sourcing.com/product/s384x384_"
THUMB_IMAGE_BASE = "https://images3.joy-sourcing.com/product/s240x240_"
MAX_CAMPAIGN_TILES = 10
# Full-bleed decorative background behind the campaign tile floor, sampled
# from the live joybuy.co.uk homepage campaign container (2026-11-04).
CAMPAIGN_BG_URL = (
    "https://images1.joy-sourcing.com/joybuyimg/jfsintlpro-000-joybuyimg/"
    "t1/4294967296/6422528/610979661011467/358409/6ad06b28Ec58f91a9/6537a2add40f4668.png"
)
# Category discovery tiles (requirement 3, docs/12 global convention #2):
# fixed 6 categories, bilingual labels, landing on /s?category=<slug>.
CATEGORY_DISCOVERY_TILES = [
    ("home-living", "Home", "家居"),
    ("electronics", "Electronics", "电子产品"),
    ("clothing-accessories", "Clothing & Accessories", "服装以及配饰"),
    ("games-accessories", "Games", "游戏"),
    ("outdoor-sports", "Outdoor & Sports", "户外运动"),
    ("small-home-appliances", "Small Home Appliances", "小家电"),
]
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)
# Real first-level categories documented in docs/09 (brand wall content).
BRANDS = [
    "TCL", "Midea", "Hisense", "CHiQ", "PUMA", "Under Armour", "Dove",
    "Garnier", "L'Oréal Paris", "PlayStation",
]
DEFAULT_SECTIONS = 6
DEFAULT_PRODUCTS_PER_SECTION = 10


class Command(BaseCommand):
    help = "Crawl the public Joybuy homepage once and publish a demo CMS home page."

    def add_arguments(self, parser):
        parser.add_argument(
            "--html",
            default=str(SAVED_HTML),
            help="Path to a saved homepage HTML; fetched from joybuy.com when missing.",
        )
        parser.add_argument("--sections", type=int, default=DEFAULT_SECTIONS)
        parser.add_argument("--per-section", type=int, default=DEFAULT_PRODUCTS_PER_SECTION)
        parser.add_argument(
            "--skip-images",
            action="store_true",
            help="Import without downloading product images.",
        )

    # ------------------------------------------------------------------ #
    # Flight stream decoding                                              #
    # ------------------------------------------------------------------ #

    def decode_flight_chunks(self, html: str) -> dict:
        """Decode self.__next_f.push payloads and parse flight stream rows."""

        pieces = []
        for match in re.finditer(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', html):
            try:
                pieces.append(json.loads(match.group(1)))
            except json.JSONDecodeError:
                continue
        stream = "".join(pieces)

        chunks: dict = {}
        header = re.compile(r"([0-9a-f]+):")
        text_header = re.compile(r"T([0-9a-f]+),")
        pos = 0
        while pos < len(stream):
            row = header.match(stream, pos)
            if not row:
                pos += 1
                continue
            chunk_id = row.group(1)
            pos = row.end()
            text_match = text_header.match(stream, pos)
            if text_match:
                length = int(text_match.group(1), 16)
                start = text_match.end()
                chunks[chunk_id] = {"__text__": stream[start : start + length]}
                pos = start + length
            elif stream[pos] in '{"[':
                end = self._scan_json_end(stream, pos)
                if end is None:
                    break
                try:
                    chunks[chunk_id] = json.loads(stream[pos : end + 1])
                except json.JSONDecodeError:
                    chunks[chunk_id] = None
                pos = end + 1
            else:
                newline = stream.find("\n", pos)
                if newline == -1:
                    break
                pos = newline
            while pos < len(stream) and stream[pos] == "\n":
                pos += 1
        return chunks

    def _scan_json_end(self, stream: str, pos: int):
        depth = 0
        in_string = False
        escape = False
        for scan in range(pos, len(stream)):
            char = stream[scan]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char in "{[":
                depth += 1
            elif char in "}]":
                depth -= 1
                if depth == 0:
                    return scan
        return None

    def resolve_ref(self, chunks: dict, value, depth: int = 0):
        """Resolve ``$id`` flight references (iterative-safe depth cap)."""

        if depth > 12:
            return value
        if isinstance(value, str) and value.startswith("$") and len(value) > 1:
            ref = value[1:].lstrip("L@")
            if ref in chunks:
                return self.resolve_ref(chunks, chunks[ref], depth + 1)
            return value
        if isinstance(value, list):
            return [self.resolve_ref(chunks, item, depth + 1) for item in value]
        if isinstance(value, dict):
            return {key: self.resolve_ref(chunks, item, depth + 1) for key, item in value.items()}
        return value

    # ------------------------------------------------------------------ #
    # Extraction                                                          #
    # ------------------------------------------------------------------ #

    def extract_sections(self, chunks: dict) -> list[dict]:
        """Bestseller floors: dicts with a title plus a resolved skuList."""

        sections = []
        seen_titles = set()
        for value in chunks.values():
            if not isinstance(value, dict):
                continue
            resolved = self.resolve_ref(chunks, value)
            title = resolved.get("title")
            sku_list = resolved.get("skuList")
            if not isinstance(title, str) or not isinstance(sku_list, list) or not sku_list:
                continue
            if title in seen_titles:
                continue
            seen_titles.add(title)
            items = []
            for entry in sku_list:
                record = self.extract_item(entry)
                if record is not None:
                    items.append(record)
            if items:
                sections.append({"title": title.strip(), "items": items})
        return sections

    def extract_item(self, entry) -> dict | None:
        """One card: sku id, title, ORIGINAL price, availability, image."""

        if not isinstance(entry, dict):
            return None
        common = entry.get("itemCommonView") or {}
        title_view = entry.get("itemTitleView") or {}
        price_view = entry.get("itemPriceView") or {}
        image_view = entry.get("itemImageView") or {}
        sku_id = str(common.get("skuId") or "").strip()
        title = str(title_view.get("title") or "").strip()
        price_info = price_view.get("priceInfo") or {}
        # Business rule: crossOffPrice is the original price; mainPrice is
        # the discounted price and is discarded.
        original_price = str(price_info.get("crossOffPrice") or "").strip()
        if not original_price:
            original_price = str(price_info.get("mainPrice") or "").strip()
        try:
            Decimal(original_price)
        except InvalidOperation:
            original_price = ""
        if not sku_id or not title or not original_price:
            return None
        image_path = str(image_view.get("imageUrl") or "").strip()
        return {
            "sku_id": sku_id,
            "title": title,
            "original_price": original_price,
            "in_stock": bool(common.get("inStock")),
            "image_path": image_path,
            "category_id": str((common.get("extMap") or {}).get("categoryId") or "").strip(),
        }

    def product_image_url(self, image_path: str) -> str:
        """CDN URL for the s360 variant; jpg sources get the q70 suffix."""

        if not image_path:
            return ""
        suffix = "!q70.webp" if image_path.lower().endswith(".jpg") else ".webp"
        return f"{PRODUCT_IMAGE_BASE}{image_path}{suffix}"

    def extract_campaign_tiles(self, chunks: dict) -> dict:
        """Marketing tiles ("Offers for you"): floorInfo rows whose eventInfo
        carries title + subTitle + imageUrl (floorType absent)."""

        tiles = []
        heading = ""
        seen_titles = set()
        for value in chunks.values():
            if not isinstance(value, dict):
                continue
            resolved = self.resolve_ref(chunks, value)
            title_view = resolved.get("titleView")
            if isinstance(title_view, dict) and not heading:
                candidate = str(title_view.get("title") or "").strip()
                if candidate:
                    heading = candidate
            floor_info = resolved.get("floorInfo")
            if not isinstance(floor_info, list):
                continue
            for entry in floor_info:
                if not isinstance(entry, dict):
                    continue
                event = entry.get("eventInfo") or {}
                title = str(event.get("title") or "").strip()
                if (
                    not title
                    or title in seen_titles
                    or event.get("floorType") == "icon"
                    or not event.get("subTitle")
                ):
                    continue
                seen_titles.add(title)
                tiles.append(
                    {
                        "title": title,
                        "subtitle": str(event.get("subTitle") or "").strip(),
                        "image_path": str(event.get("imageUrl") or "").strip(),
                        "image_url": "",
                    }
                )
        return {"heading": heading, "tiles": tiles[:MAX_CAMPAIGN_TILES]}

    def localize_cms_image(self, source: str, *, variant: str) -> str:
        """Download a source image (relative path or //host URL) into the
        local CMS media store; returns the public /media URL or ""."""

        if not source:
            return ""
        if source.startswith("//"):
            url = f"https:{source}"
        elif source.startswith("http"):
            url = source
        else:
            base = {"tile": TILE_IMAGE_BASE, "thumb": THUMB_IMAGE_BASE}.get(variant, TILE_IMAGE_BASE)
            suffix = "!q70.webp" if source.lower().endswith(".jpg") else ".webp"
            url = f"{base}{source}{suffix}"
        data = self.download_image(url)
        if data is None:
            return ""
        asset, _created = store_bytes(data, kind="CMS", mime_type="image/webp", source_url=url)
        from media.storage import media_url

        return media_url(asset.relative_path)

    # ------------------------------------------------------------------ #
    # Fetch + download                                                    #
    # ------------------------------------------------------------------ #

    def load_html(self, html_path: Path) -> str:
        if html_path.is_file() and html_path.stat().st_size > 10000:
            self.stdout.write(f"Using saved homepage HTML: {html_path}")
            return html_path.read_text(encoding="utf-8", errors="replace")
        self.stdout.write(f"Fetching {JOYBUY_HOME_URL} (single polite request)...")
        request = urllib.request.Request(JOYBUY_HOME_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")

    def download_image(self, url: str) -> bytes | None:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        for attempt in (1, 2):
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    data = response.read()
                if data:
                    return data
            except Exception:  # noqa: BLE001 - one missing image must not stop the import
                if attempt == 2:
                    return None
                time.sleep(1)
        return None

    # ------------------------------------------------------------------ #
    # Import                                                              #
    # ------------------------------------------------------------------ #

    def ensure_source(self, category_ids: set[str]):
        catalog = SourceCatalog.objects.get_or_create(
            source_system="joybuy",
            defaults={"display_name": "Joybuy"},
        )[0]
        from django.utils import timezone

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
        # start_run selects an account with a valid session from the job's
        # group; the demo import reuses the public homepage, so a marker
        # session blob is enough (no credentials involved).
        from crawler_control.models import CrawlerAccount

        account = CrawlerAccount.objects.filter(account_group="default").first()
        if account is None:
            account = create_crawler_account(label="Joybuy homepage demo", account_group="default")
        if account.session_status != CrawlerAccount.SessionStatus.VALID:
            record_account_session(account, {"joybuy_session": "public-homepage-demo"})
        job = create_crawl_job(
            name="Joybuy homepage demo import",
            market=market,
            source_catalog=catalog,
            source_category=category,
            product_limit=500,
            currency=market.default_currency,
        )
        start_run(mark_job_ready(job))
        return CrawlRun.objects.filter(job=job).order_by("-pk").first()

    def import_products(self, sections, *, market, skip_images: bool) -> tuple[dict, dict, int]:
        category_ids = {
            item["category_id"] for section in sections for item in section["items"]
            if item["category_id"]
        }
        fallback_category = SourceCategory.objects.filter(catalog__source_system="joybuy").first()
        catalog, categories = self.ensure_source(category_ids)
        if fallback_category is None:
            fallback_category = self.ensure_source({"demo"})[1]["demo"]
        run = self.ensure_run(catalog, fallback_category, market)

        spu_by_sku = {}
        image_by_sku = {}
        image_failures = 0
        for section in sections:
            for item in section["items"]:
                payload = {
                    "source_id": item["sku_id"],
                    "title": item["title"],
                    "currency": market.default_currency.code,
                    "current_price": item["original_price"],
                    "list_price": None,
                    "promotion_label": "",
                    "availability": "IN_STOCK" if item["in_stock"] else "OUT_OF_STOCK",
                    "brand": "",
                    "source_category_id": item["category_id"],
                    "source_seller_id": "",
                    "source_seller_name": "",
                    "description": "",
                    "rating_count": None,
                    "rating_average": None,
                    "skus": [
                        {
                            "source_id": item["sku_id"],
                            "price": item["original_price"],
                            "availability": "IN_STOCK" if item["in_stock"] else "OUT_OF_STOCK",
                            "specs": [],
                        }
                    ],
                    "image_urls": [],
                    "missing_fields": [],
                }
                staging = ingest_product_payload(
                    run,
                    payload,
                    source_system="joybuy",
                    source_url=JOYBUY_HOME_URL,
                    parser_version="joybuy-home-demo-1",
                    structure_version=1,
                )
                outcome = import_staging_product(
                    staging,
                    market=market,
                    currency=market.default_currency,
                    locale="en-GB",
                )
                spu = outcome.spu
                spu_by_sku[item["sku_id"]] = spu
                # Demo activation: these items are live bestsellers on the
                # public source homepage, so they skip the curation draft
                # state that a production import would go through.
                if spu.status != Spu.Status.ACTIVE:
                    spu.status = Spu.Status.ACTIVE
                    spu.save(update_fields=["status", "updated_at"])
                for offer in outcome.offers:
                    if offer.status != Offer.Status.ACTIVE:
                        offer.status = Offer.Status.ACTIVE
                        offer.save(update_fields=["status", "updated_at"])
                rebuild_search_document(spu, market=market)

                if not skip_images and item["image_path"]:
                    data = self.download_image(self.product_image_url(item["image_path"]))
                    if data is None:
                        image_failures += 1
                        continue
                    asset, _created = store_bytes(
                        data,
                        kind="PRODUCT",
                        mime_type="image/webp",
                        source_url=self.product_image_url(item["image_path"]),
                    )
                    spu_type = ContentType.objects.get_for_model(Spu)
                    MediaUsage.objects.get_or_create(
                        asset=asset,
                        content_type=spu_type,
                        object_id=spu.pk,
                        role="gallery",
                        defaults={"sort_order": 0},
                    )
                    from media.storage import media_url

                    image_by_sku[item["sku_id"]] = media_url(asset.relative_path)
        return spu_by_sku, image_by_sku, image_failures

    # ------------------------------------------------------------------ #
    # CMS page                                                            #
    # ------------------------------------------------------------------ #

    def build_modules(
        self,
        sections,
        spu_by_sku,
        image_by_sku,
        campaign,
        *,
        market,
    ) -> list[dict]:
        modules = []
        # Page order per docs/12 target state: campaign tiles, category
        # discovery, product floors, brand wall. The quick-entry icon row is
        # removed (requirement 2) and the JoyPlus block never existed here.
        if campaign["tiles"]:
            modules.append(
                {
                    "module_type": "campaign_grid",
                    "payload": {
                        "title": campaign["heading"],
                        "title_zh": "为你推荐",
                        # Full-bleed decorative background behind the tiles
                        # (the real floor ships one; "" falls back to a mask).
                        "background_path": campaign.get("background_url", ""),
                        "items": [
                            {
                                "title": tile["title"],
                                "subtitle": tile["subtitle"],
                                "image_path": tile["image_url"],
                                "href": "/search",
                            }
                            for tile in campaign["tiles"]
                        ],
                    },
                }
            )
        # Category discovery is the fixed 6-category list (requirement 3);
        # each tile lands on the /s listing template for its standard category.
        modules.append(
            {
                "module_type": "link_grid",
                "payload": {
                    "title": "Category discovery",
                    "title_zh": "品类发现",
                    "variant": "tiles",
                    "items": [
                        {
                            "label": label_en,
                            "label_zh": label_zh,
                            "href": f"/s?category={slug}",
                        }
                        for slug, label_en, label_zh in CATEGORY_DISCOVERY_TILES
                    ],
                },
            }
        )
        for section in sections:
            products = []
            for item in section["items"]:
                spu = spu_by_sku.get(item["sku_id"])
                if spu is None:
                    continue
                products.append(
                    {
                        "public_id": str(spu.public_id),
                        "title": item["title"],
                        "price": item["original_price"],
                        "currency": market.default_currency.code,
                        "image_path": image_by_sku.get(item["sku_id"], ""),
                        "href": f"/p/{spu.public_id}",
                    }
                )
            if not products:
                continue
            modules.append(
                {
                    "module_type": "product_pool",
                    "payload": {
                        "title": section["title"],
                        "href": "/search",
                        "products": products,
                    },
                }
            )
        modules.append(
            {
                "module_type": "link_grid",
                "payload": {
                    "title": "Brands we love",
                    "items": [{"label": brand} for brand in BRANDS],
                },
            }
        )
        modules.append(
            {
                "module_type": "rich_text",
                "payload": {
                    "heading": "About this study build",
                    "body": (
                        "Product cards, prices and images on this page were crawled from the "
                        "public Joybuy homepage for layout study. Only original prices are "
                        "shown; images are stored locally. Editors and previews arrive with "
                        "WP-34."
                    ),
                },
            }
        )
        return modules

    def handle(self, *args, **options):
        html_path = Path(options["html"])
        section_limit = max(1, options["sections"])
        per_section = max(1, options["per_section"])
        skip_images = options["skip_images"]

        market = Market.objects.filter(code="GB", is_active=True).first()
        if market is None:
            self.stderr.write("Market GB is not configured; aborting.")
            return

        html = self.load_html(html_path)
        chunks = self.decode_flight_chunks(html)
        sections = self.extract_sections(chunks)[:section_limit]
        sections = [
            {
                "title": section["title"],
                "items": section["items"][:per_section],
            }
            for section in sections
        ]
        total = sum(len(section["items"]) for section in sections)
        campaign = self.extract_campaign_tiles(chunks)
        self.stdout.write(
            f"Parsed {len(chunks)} flight chunks; importing {total} products "
            f"from {len(sections)} sections; {len(campaign['tiles'])} campaign tiles."
        )
        if not sections:
            self.stderr.write("No bestseller sections found; aborting.")
            return

        if not skip_images:
            # Localize the marketing visuals before building the page.
            for tile in campaign["tiles"]:
                tile["image_url"] = self.localize_cms_image(tile["image_path"], variant="tile")
            campaign["background_url"] = self.localize_cms_image(CAMPAIGN_BG_URL, variant="tile")

        spu_by_sku, image_by_sku, image_failures = self.import_products(
            sections, market=market, skip_images=skip_images
        )
        modules = self.build_modules(
            sections,
            spu_by_sku,
            image_by_sku,
            campaign,
            market=market,
        )
        page = publish_page(
            page_key="home",
            title="Joybuy | One-Stop Shopping",
            modules=modules,
        )
        GENERATED_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        GENERATED_FIXTURE.write_text(
            json.dumps(
                {"page_key": "home", "title": page.title, "modules": modules},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Published {page.page_key} v{page.version} with {page.modules.count()} modules; "
                f"imported {len(spu_by_sku)} products; image failures: {image_failures}. "
                f"Fixture saved to {GENERATED_FIXTURE}."
            )
        )
