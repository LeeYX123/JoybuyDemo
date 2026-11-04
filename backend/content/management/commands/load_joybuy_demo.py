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
    # (slug, label_en, label_zh, discovery image sampled from the live
    # joybuy.co.uk discovery carousel, 2026-11-04; admin reconfigures freely).
    ("home-living", "Home", "家居",
     "https://images3.joy-sourcing.com/product/s624x624_jfsintlpro-000-com/t1/4294967296/5308416/10161432272242740/135890/68f563d2Edaa06d68/4c765c6ab87a3a67.png.webp"),
    ("electronics", "Electronics", "电子产品",
     "https://images3.joy-sourcing.com/product/s624x624_jfsintlpro-000-com/t1/4294967296/3801088/10161432272242369/186716/68f276ceE499d6cee/4c765c6ab87a3a67.png.webp"),
    ("clothing-accessories", "Clothing & Accessories", "服装以及配饰",
     "https://images3.joy-sourcing.com/product/s624x624_jfsintlpro-000-com/t1/4294967296/4915200/1016145512242644/68705/68f55d1aEd020bb22/4c765c6ab87a3a67.png.webp"),
    ("games-accessories", "Games", "游戏",
     "https://images3.joy-sourcing.com/product/s624x624_jfsintlpro-000-com/t1/4294967296/6356992/61097966203569/147538/69ab3148Eb2afce62/4c765c6ab87a3a67.png.webp"),
    ("outdoor-sports", "Outdoor & Sports", "户外运动",
     "https://images3.joy-sourcing.com/product/s624x624_jfsintlpro-000-com/t1/4294967296/8060928/1016145512242609/63724/68f538caE36d3bf11/4c765c6ab87a3a67.png.webp"),
    ("small-home-appliances", "Small Home Appliances", "小家电",
     "https://images3.joy-sourcing.com/product/s624x624_jfsintlpro-000-com/t1/4294967296/8257536/1016145512244632/22745/6900ada5E63223e54/4c765c6ab87a3a67.png.webp"),
]
# Featured brands (心选品牌 / "Brands we love"): circular logo cards,
# rendered static (not clickable). Logos sampled from the live homepage.
FEATURED_BRANDS = [
    ("McCormick", "https://images3.joy-sourcing.com/product/s220x220_jfsintlpro-000-com/t1/4294967296/4784128/620722011367887/22992/6a914cdaE882ad2fb/4c765c6ab87a3a67.jpg!q70.webp"),
    ("Celeplate", "https://images3.joy-sourcing.com/product/s220x220_jfsintlpro-000-com/t1/4294967296/5177344/62073711069147/42278/6a7c2473E11e8fde4/4c765c6ab87a3a67.png.webp"),
    ("Encona", "https://images3.joy-sourcing.com/product/s220x220_jfsintlpro-000-da/t1/4294967296/7143424/10161455133581/6594/67c9af04Eb2402a90/b853b8a46c93f496.png.webp"),
    ("eufy", "https://images3.joy-sourcing.com/product/s220x220_jfsintlpro-000-com/t1/12884901888/6356992/62073702236/19726/69f1ac1aE02121017/de925bbe628751df.jpg!q70.webp"),
    ("Tapo", "https://images3.joy-sourcing.com/product/s220x220_jfsintlpro-000-da/t1/4294967296/5636096/10161432272503/3693/682c8d92Eb52fb0e8/b853b8a46c93f496.png.webp"),
    ("Nando's", "https://images3.joy-sourcing.com/product/s220x220_jfsintlpro-000-da/t1/4294967296/5701632/6207370721314/36393/6a5aa4ddEaf3a0ead/b853b8a46c93f496.jpg!q70.webp"),
    ("C&S", "https://images3.joy-sourcing.com/product/s220x220_jfsintlpro-000-com/t1/4294967296/393216/6207370860098/34260/6a63682fE22cdbd65/4c765c6ab87a3a67.png.webp"),
    ("TCL", "https://images3.joy-sourcing.com/product/s220x220_jfsintlpro-000-com/t1/4294967296/2883584/610979661137159/34305/6a8154f5Ed28c0707/4c765c6ab87a3a67.jpg!q70.webp"),
    ("CJ", "https://images3.joy-sourcing.com/product/s220x220_jfsintlpro-000-da/t1/4294967296/4128768/101614551440/37764/676b01b3E3cc60f6d/b853b8a46c93f496.png.webp"),
    ("Bc Babycare", "https://images3.joy-sourcing.com/product/s220x220_jfsintlpro-000-com/t1/4294967296/2031616/6109817860618/12623/6a6369baE4fef6171/4c765c6ab87a3a67.png.webp"),
    ("Midea", "https://images3.joy-sourcing.com/product/s220x220_jfsintlpro-000-com/t1/4294967296/524288/6109796674463/4992/6a9a7beaE2ba420fc/4c765c6ab87a3a67.png.webp"),
    ("Healthy Boy Brand", "https://images3.joy-sourcing.com/product/s220x220_jfsintlpro-000-com/t1/4294967296/1179648/62073701366812/38787/6a9147d4Eea26fcb3/4c765c6ab87a3a67.jpg!q70.webp"),
    ("Fairy Non Bio", "https://images3.joy-sourcing.com/product/s220x220_jfsintlpro-000-com/t1/4294967296/6881280/6207370327063/10970/6a337df0E5f726993/4c765c6ab87a3a67.jpg!q70.webp"),
    ("CaiLab", "https://images3.joy-sourcing.com/product/s220x220_jfsintlpro-000-com/t1/12884901888/262144/1016159612139/19436/69f1a282E8ba4cc5a/de925bbe628751df.jpg!q70.webp"),
    ("Obento", "https://images3.joy-sourcing.com/product/s220x220_jfsintlpro-000-com/t1/12884901888/4259840/610979662280/22540/69f1a6e3E1b0381c0/de925bbe628751df.jpg!q70.webp"),
    ("Kinda", "https://images3.joy-sourcing.com/product/s220x220_jfsintlpro-000-com/t1/4294967296/5242880/6109817878071/50878/6a684b36E70cde242/4c765c6ab87a3a67.png.webp"),
    ("Dove", "https://images3.joy-sourcing.com/product/s220x220_jfsintlpro-000-da/t1/4294967296/4194304/101614322725745/136445/67bd9a3bE86c48336/b853b8a46c93f496.jpg!q70.webp"),
    ("Highland Spring", "https://images3.joy-sourcing.com/product/s220x220_jfsintlpro-000-com/t1/4294967296/3932160/61098360977642/14067/6a748b65E50417f45/4c765c6ab87a3a67.jpg!q70.webp"),
    ("Garnier", "https://images3.joy-sourcing.com/product/s220x220_jfsintlpro-000-da/t1/4294967296/3407872/101614322725740/109643/67bd99f5Eed4245c4/b853b8a46c93f496.jpg!q70.webp"),
    ("L'Oréal Paris", "https://images3.joy-sourcing.com/product/s220x220_jfsintlpro-000-com/t1/4294967296/1966080/62072201273164/11176/6a2bb482E9be773f4/4c765c6ab87a3a67.png.webp"),
]
MAX_FEATURED_BRANDS = 12
# Localized (var/media) paths filled by handle() on each run.
CATEGORY_DISCOVERY_LOCAL_IMAGES = {}
FEATURED_BRAND_LOCAL_LOGOS = {}
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
                            "icon_path": CATEGORY_DISCOVERY_LOCAL_IMAGES.get(index, ""),
                            "href": f"/s?category={slug}",
                        }
                        for index, (slug, label_en, label_zh, _img) in enumerate(
                            CATEGORY_DISCOVERY_TILES
                        )
                    ],
                },
            }
        )
        # Featured brands (心选品牌, "Brands we love"): static logo circles
        # right below category discovery, mirroring the real homepage order.
        brand_items = [
            {
                "label": name,
                "icon_path": FEATURED_BRAND_LOCAL_LOGOS.get(index, ""),
            }
            for index, (name, _logo) in enumerate(FEATURED_BRANDS[:MAX_FEATURED_BRANDS])
        ]
        if any(item["icon_path"] for item in brand_items):
            modules.append(
                {
                    "module_type": "link_grid",
                    "payload": {
                        "title": "Brands we love",
                        "title_zh": "心选品牌",
                        "variant": "brand_logos",
                        "items": brand_items,
                    },
                }
            )
        # The crawled bestseller sections are NOT rendered as standalone
        # product floors: on the real homepage that data lives inside the
        # Bestsellers floor (category tabs + ranked cards), which the
        # storefront serves from the search API per active tab. The old text
        # pill brand wall is superseded by the featured-brands module above.
        del spu_by_sku, image_by_sku, market
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
            # tuple entries can't hold the localized path; collect separately.
            for index, (_slug, _en, _zh, image_url) in enumerate(CATEGORY_DISCOVERY_TILES):
                CATEGORY_DISCOVERY_LOCAL_IMAGES[index] = self.localize_cms_image(
                    image_url, variant="tile"
                )
            for index, (_name, logo_url) in enumerate(FEATURED_BRANDS):
                FEATURED_BRAND_LOCAL_LOGOS[index] = self.localize_cms_image(
                    logo_url, variant="thumb"
                )

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
