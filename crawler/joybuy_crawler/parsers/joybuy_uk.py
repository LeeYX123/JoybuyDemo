"""Joybuy UK (joybuy.co.uk) parsers — structure version 2 (2026-11-05 rebuild).

Field rule (user requirement #4): every crawled field keeps its Joybuy
source name. The detail payload carries the native block under
``"joybuy"`` (verbatim camelCase source fields) and mirrors the values
into the legacy normalized top-level keys that the staging → quality
gate → import chain consumes.

Price rule (unchanged, HANDOFF 2026-11-03): only ORIGINAL prices are
crawled — the visible original price (``crossOffPrice``) wins over the
discounted ``mainPrice``; ``list_price`` stays None.

Review rule (2026-11-05, user requirement): review *content* is never
crawled. Only the aggregate rating is kept — the 1/2/3/4/5-star counts,
the average score and the total review count — plus the AI-written
summary block ("内容由人工智能总结自用户评价") **when the page renders
one**. A page without the block yields no summary field at all rather
than an empty placeholder.

Category rule (2026-11-05, user requirement): the breadcrumb trail is
cut to the first two category levels after the generic home crumb, so a
product nested five levels deep is recorded as ``一级/二级`` only. The
dropped levels remain available inside the archived raw response if a
deeper mapping is ever needed.

Detail pages are extracted in three tolerant layers (first hit wins):
1. embedded Next.js flight JSON (``self.__next_f`` chunks) — richest;
2. JSON-LD ``Product`` blocks;
3. DOM selectors from docs/11 §6 (breadcrumb, gallery, seller, tabs).

Any layer that fails simply reports missing fields; the quality gates
decide what may still be imported, and risk-control pages are never
parsed (callers must check :func:`joybuy_crawler.render.detect_risk_control`).
"""

import json
import re
from dataclasses import dataclass, field

from parsel import Selector

UK_STRUCTURE_VERSION = 2
UK_PRODUCT_URL_PATTERN = re.compile(r"/dp/[^/]+/(\w+)")

_PRICE_PATTERN = re.compile(r"[-+]?\d+(?:\.\d{1,2})?(?![\d])")

REQUIRED_FIELDS = ("source_id", "title", "currency", "current_price", "skus")

#: How many category levels (after the generic home crumb) are recorded.
BREADCRUMB_DEPTH = 2
#: Breadcrumb labels that are a site root, not a category level.
HOME_CRUMB_LABELS = {"home", "首页", "主页", "首頁"}

#: Labels the page prints above the AI review summary. Used by the DOM
#: fallback to recognise the block; the flight JSON carries it as
#: ``aiSummary`` without any label.
AI_SUMMARY_LABELS = (
    "内容由人工智能总结自用户评价",
    "由人工智能总结自用户评价",
    "人工智能总结",
    "ai-generated summary",
    "ai summary",
    "summarized from customer reviews",
)

#: Star buckets, in the order the source exposes them.
STAR_LEVELS = (1, 2, 3, 4, 5)


@dataclass
class UkListingEntry:
    source_url: str
    rank: int
    title: str
    original_price: str | None = None
    image_url: str = ""


@dataclass
class UkProduct:
    """Parsed product detail with Joybuy-native fields preserved."""

    source_id: str
    title: str
    currency: str
    current_price: str | None  # original price (crossOffPrice rule)
    list_price: str | None  # always None: the discount is never kept
    main_price: str | None  # the discounted display price, kept verbatim
    promotion_label: str
    availability: str
    brand: str
    breadcrumbs: list[dict]
    skus: list[dict]
    gallery: list[str]
    description: str
    detail_images: list[str]
    seller_name: str
    seller_url: str
    rating_average: str | None
    rating_count: int | None
    source_url: str
    #: Star counts keyed "1".."5" (review *content* is never crawled).
    rating_distribution: dict[str, int] = field(default_factory=dict)
    #: Where the rating came from: ``flight`` (page JSON) or ``dom``.
    rating_source: str = ""
    #: AI-written review summary text; empty when the page has no block.
    ai_summary: str = ""
    #: Heading the page prints above the summary, e.g.
    #: "内容由人工智能总结自用户评价".
    ai_summary_title: str = ""
    #: AI review tags ("aiTagList"), empty when absent.
    ai_summary_tags: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)

    def to_payload(self) -> dict:
        """Joybuy-native block + legacy staging keys in one payload."""

        native = {
            "productId": self.source_id,
            "title": self.title,
            "brand": self.brand,
            "breadcrumbs": self.breadcrumbs,
            "priceInfo": {
                "currency": self.currency,
                "crossOffPrice": self.current_price,
                "mainPrice": self.main_price,
            },
            "skus": [
                {
                    "skuId": sku["source_id"],
                    "price": sku["price"],
                    "availability": sku["availability"],
                    "specs": sku["specs"],
                }
                for sku in self.skus
            ],
            "gallery": self.gallery,
            "description": self.description,
            "detailImages": self.detail_images,
            "seller": {"name": self.seller_name, "storeUrl": self.seller_url},
            "rating": {
                "average": self.rating_average,
                "count": self.rating_count,
                "distribution": self.rating_distribution,
            },
            "promotionLabel": self.promotion_label,
            "availability": self.availability,
            "sourceUrl": self.source_url,
        }
        # The AI summary block only exists when the page rendered one.
        if self.ai_summary:
            native["aiReviewSummary"] = {
                "title": self.ai_summary_title,
                "text": self.ai_summary,
                "tags": self.ai_summary_tags,
            }
        return {
            "joybuy": native,
            "source_id": self.source_id,
            "title": self.title,
            "currency": self.currency,
            "current_price": self.current_price,
            "list_price": self.list_price,
            "promotion_label": self.promotion_label,
            "availability": self.availability,
            "brand": self.brand,
            "source_category_id": (self.breadcrumbs or [{}])[-1].get("cid", ""),
            "source_seller_id": self.seller_name,
            "source_seller_name": self.seller_name,
            "description": self.description,
            "rating_count": self.rating_count,
            "rating_average": self.rating_average,
            "rating_distribution": self.rating_distribution,
            "rating_source": self.rating_source,
            "ai_summary": self.ai_summary,
            "ai_summary_title": self.ai_summary_title,
            "ai_summary_tags": self.ai_summary_tags,
            "skus": self.skus,
            "image_urls": self.gallery,
            "detail_image_urls": self.detail_images,
            "missing_fields": self.missing_fields,
        }


def _price(raw: str | None) -> str | None:
    if not raw:
        return None
    text = raw.replace(",", "")
    # The listing cards render a price as several text nodes ("£ 32 . 33"),
    # so a plain regex would stop at "32". Join decimals first.
    text = re.sub(r"(?<=\d)\s*\.\s*(?=\d)", ".", text)
    match = _PRICE_PATTERN.search(text)
    return match.group(0) if match else None


_FLIGHT_CHUNK = re.compile(r"self\.__next_f\.push\(\[1,\"(.*?)\"\]\)", re.DOTALL)
#: One JSON value as it appears after ``"key":`` — object, array, string or scalar.
_FLIGHT_VALUE = (
    r'(\{[^{}]*\}|\[[^\[\]]*\]|"(?:[^"\\]|\\.)*"|null|true|false|-?\d+(?:\.\d+)?)'
)


def _flight_text(html: str) -> str:
    """Decode every ``self.__next_f`` chunk into one searchable string.

    Next.js serialises the server payload into JS string literals, so the
    embedded JSON arrives escaped (``\\"``). Decoding through ``json``
    keeps multi-byte text intact, which a ``unicode_escape`` round-trip
    would mangle.
    """

    parts = []
    for match in _FLIGHT_CHUNK.finditer(html):
        raw = match.group(1)
        try:
            parts.append(json.loads(f'"{raw}"'))
        except json.JSONDecodeError:
            parts.append(
                raw.encode("utf-8", "ignore").decode("unicode_escape", errors="ignore")
            )
    return "\n".join(parts)


def _flight_ref(text: str, value):
    """Follow a Next.js dedupe reference (``"$19c"``) to its slot value.

    The flight stream replaces repeated objects with ``<id>:<value>``
    slots and points at them with ``"$<id>"``, so the rating block is
    usually one hop away from where it is referenced.
    """

    seen = set()
    while isinstance(value, str) and value.startswith("$") and len(value) > 1:
        reference = value[1:]
        if reference in seen:
            return None
        seen.add(reference)
        slot = re.search(rf'(?<![\w"])({re.escape(reference)}):{_FLIGHT_VALUE}', text)
        if not slot:
            return None
        try:
            value = json.loads(slot.group(2))
        except json.JSONDecodeError:
            return None
    return value


def _extract_flight_review(html: str) -> dict:
    """Aggregate rating + AI summary from the embedded flight JSON.

    The review block is a flat object that carries ``ratingInfo`` as a
    reference; anchoring on ``"ratingInfo"`` inside a brace pair avoids
    picking up the unrelated i18n strings that also mention ``aiSummary``.
    """

    text = _flight_text(html)
    if not text:
        return {}
    container = re.search(r'\{[^{}]*"ratingInfo"[^{}]*\}', text)
    block = {}
    if container:
        try:
            block = json.loads(container.group(0))
        except json.JSONDecodeError:
            block = {}
    rating_info = _flight_ref(text, block.get("ratingInfo")) or {}
    if not isinstance(rating_info, dict):
        rating_info = {}

    distribution = {}
    for level in STAR_LEVELS:
        raw = rating_info.get(f"score{level}Count")
        try:
            distribution[str(level)] = int(raw) if raw is not None else 0
        except (TypeError, ValueError):
            distribution[str(level)] = 0

    count = block.get("totalCommentCount")
    if count is None:
        count = rating_info.get("commentCount")
    try:
        count = int(count) if count is not None else None
    except (TypeError, ValueError):
        count = None

    # ``star`` is the displayed product rating; ``averageScore`` defaults
    # to 5 on products with no reviews, so it is only trusted when there
    # is at least one review to average.
    average = None
    for candidate in (block.get("star"), block.get("starShow")):
        if candidate in (None, "", "0", "0.0"):
            continue
        if _price(str(candidate)):
            average = _price(str(candidate))
            break
    if average is None and count:
        average = _price(str(rating_info.get("averageScore") or ""))

    summary = block.get("aiSummary")
    summary = summary.strip() if isinstance(summary, str) else ""
    tags = _flight_ref(text, block.get("aiTagList"))
    tags = (
        [str(tag).strip() for tag in tags if str(tag).strip()]
        if isinstance(tags, list)
        else []
    )
    title = block.get("aiTagTitle")
    title = title.strip() if isinstance(title, str) else ""

    has_data = bool(rating_info) or count is not None or bool(summary)
    if not has_data:
        return {}
    return {
        "average": average,
        "count": count,
        "distribution": distribution if rating_info else {},
        "summary": summary,
        "summary_title": title,
        "summary_tags": tags,
        "source": "flight",
    }


def _extract_dom_review(selector) -> dict:
    """Fallback: read the AI summary block straight out of the DOM.

    Only the summary is attempted here. The star counts live in a
    canvas/bar widget whose text is not reliably present in the rendered
    HTML, so a DOM guess would invent numbers — better to report nothing
    than a wrong distribution.
    """

    for node in selector.css(
        '[class*="aiSummary"], [class*="ai-summary"], [class*="summaryContent"]'
    ):
        text = " ".join(" ".join(node.css("::text").getall()).split())
        for label in AI_SUMMARY_LABELS:
            if text.casefold().startswith(label.casefold()):
                text = text[len(label) :].strip(" :：")
        if len(text) >= 20:
            return {
                "average": None,
                "count": None,
                "distribution": {},
                "summary": text,
                "summary_title": "",
                "summary_tags": [],
                "source": "dom",
            }
    return {}


def _extract_flight_product(html: str) -> dict | None:
    """Search Next.js flight chunks for an embedded product JSON object."""

    text = _flight_text(html)
    if not text:
        return None
    for json_match in re.finditer(r"\{[^{}]*\"crossOffPrice\"[^{}]*\}", text):
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            continue
    return None


def _parse_json_ld(selector) -> dict:
    for block in selector.xpath(
        '//script[@type="application/ld+json"]/text()'
    ).getall():
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            json_type = item.get("@type")
            types = json_type if isinstance(json_type, list) else [json_type]
            if "Product" in types:
                return item
    return {}


def truncate_breadcrumbs(
    crumbs: list[dict], depth: int = BREADCRUMB_DEPTH
) -> list[dict]:
    """Keep only the first ``depth`` category levels after the home crumb.

    ``首页 / 母婴用品 / 健康护理 / 湿巾及配件 / 湿巾 / 商品`` becomes
    ``母婴用品 / 健康护理`` — the deeper levels are meaningful on the
    source site but only add noise to our own two-level catalog.
    """

    kept = [crumb for crumb in (crumbs or []) if (crumb.get("name") or "").strip()]
    if kept and kept[0]["name"].strip().casefold() in HOME_CRUMB_LABELS:
        kept = kept[1:]
    return kept[:depth]


def _rating_from_dom(selector, html: str = "") -> tuple[str | None, int | None]:
    """Last-resort rating read from the visible rating chip.

    Only used when the page JSON carried no ``ratingInfo``; the first
    number in the rating block is the average, the second the count.
    """

    average = None
    count = None
    for part in selector.css('[class*="rating"] ::text').getall():
        number = _price(part)
        if number is None:
            continue
        if average is None:
            average = number
        elif count is None:
            count = int(float(number))
    if average is None and html:
        # "rated 4.8 out of 5 based on 6 reviews"
        match = re.search(
            r"rated ([\d.]+) out of 5.*?([\d,]+)\s+reviews", html[:60000], re.IGNORECASE
        )
        if match:
            average = match.group(1)
            count = int(match.group(2).replace(",", ""))
    return average, count


def _absolute_url(href: str) -> str:
    if href.startswith("//"):
        return f"https:{href}"
    if href.startswith("/"):
        return f"https://www.joybuy.co.uk{href}"
    return href


def _image_url(src: str) -> str:
    if src.startswith("//"):
        return f"https:{src}"
    return src if src.startswith("http") else ""


def _text(node) -> str:
    return " ".join(" ".join(node.css("::text").getall()).split())


def parse_uk_listing(html: str) -> list[UkListingEntry]:
    """Product cards from a listing / bestseller page.

    Two layouts exist in the wild (both live 2026-11-05):

    * **card layout** — ``div[class*="product_card"]`` wraps an image anchor
      plus ``title`` / ``brandName`` / ``crossOffPrice`` / ``mainPriceText``
      nodes. The image anchor itself carries no text, which is why a purely
      anchor-based parser produced titleless cards.
    * **anchor layout** — the older one where the card *is* an
      ``a[href*="/dp/"]`` with the title and price inside it (still used by
      bestseller pages and by the parser fixtures).

    Cards are scanned first; when the page has none the anchor path runs, so
    a layout change in either direction keeps working. Raises when nothing
    matches — a structure change must surface as a signal, never as an empty
    page.
    """

    selector = Selector(text=html)
    entries: list[UkListingEntry] = []
    seen_urls: set[str] = set()

    for card in selector.css('[class*="product_card"]'):
        anchor = card.css('a[href*="/dp/"]')
        if not anchor:
            continue
        href = _absolute_url((anchor[0].attrib.get("href") or "").strip())
        if "/dp/" not in href or href in seen_urls:
            continue
        seen_urls.add(href)
        title = (
            _text(card.css('[class*="style_title"]')[0])
            if card.css('[class*="style_title"]')
            else ""
        )
        if len(title) < 5:
            # Fall back to the image alt text, which carries the full title.
            title = " ".join(
                (anchor[0].css("img::attr(alt)").get() or "").split()
            ).strip()
        original = (
            _price(_text(card.css('[class*="crossOffPrice"]')[0]))
            if card.css('[class*="crossOffPrice"]')
            else None
        )
        if original is None and card.css('[class*="mainPriceText"]'):
            original = _price(_text(card.css('[class*="mainPriceText"]')[0]))
        if original is None and card.css('[class*="mainPrice"]'):
            original = _price(_text(card.css('[class*="mainPrice"]')[0]))
        image = anchor[0].css("img::attr(src)").get() or ""
        entries.append(
            UkListingEntry(
                source_url=href,
                rank=len(entries) + 1,
                title=title,
                original_price=original,
                image_url=_image_url(image),
            )
        )

    if not entries:
        # Older/anchor layout (bestseller pages, fixtures).
        for anchor in selector.css('a[href*="/dp/"]'):
            href = _absolute_url((anchor.attrib.get("href") or "").strip())
            if not href or "/dp/" not in href or href in seen_urls:
                continue
            seen_urls.add(href)
            # Prefer an explicit title node; then the anchor's own text; only
            # then everything inside it (which would also swallow the price).
            title = (
                _text(anchor.css('[class*="title"]')[0])
                if anchor.css('[class*="title"]')
                else ""
            )
            if not title:
                title = " ".join(
                    part.strip()
                    for part in anchor.xpath("./text()").getall()
                    if part.strip()
                )
            if not title:
                title = _text(anchor)
            original = (
                _price(_text(anchor.css('[class*="crossOffPrice"]')[0]))
                if anchor.css('[class*="crossOffPrice"]')
                else None
            )
            if original is None and anchor.css('[class*="mainPrice"]'):
                original = _price(_text(anchor.css('[class*="mainPrice"]')[0]))
            image = anchor.css("img::attr(src)").get() or ""
            entries.append(
                UkListingEntry(
                    source_url=href,
                    rank=len(entries) + 1,
                    title=title,
                    original_price=original,
                    image_url=_image_url(image),
                )
            )

    if not entries:
        raise RuntimeError("Joybuy UK listing page has no /dp/ product cards.")
    return entries


def parse_uk_product_detail(html: str, *, source_url: str = "") -> UkProduct:
    selector = Selector(text=html)

    flight = _extract_flight_product(html) or {}
    json_ld = _parse_json_ld(selector)

    title = (
        (selector.css("h1::text").get() or "").strip()
        or (json_ld.get("name") or "").strip()
        or str(flight.get("title") or "").strip()
    )
    source_id = ""
    for url in (source_url, json_ld.get("url") or ""):
        match = UK_PRODUCT_URL_PATTERN.search(url or "")
        if match:
            source_id = match.group(1)
            break
    if not source_id:
        source_id = str(flight.get("productId") or json_ld.get("sku") or "").strip()

    brand = (
        (selector.css('[class*="brand"] ::text').get() or "").strip()
        or (
            json_ld.get("brand", {}).get("name", "").strip()
            if isinstance(json_ld.get("brand"), dict)
            else str(json_ld.get("brand") or "").strip()
        )
        or str(flight.get("brand") or "").strip()
    )

    # Original-price rule: crossOffPrice (visible original) > JSON-LD (only
    # when it must be the original) > mainPrice last resort.
    cross_price = (
        _price(
            selector.css('[class*="crossOffPrice"] ::text').get()
            or selector.css('[class*="crossOffPrice"]::text').get()
        )
        or str(flight.get("crossOffPrice") or "").strip()
        or None
    )
    main_price = (
        _price(
            selector.css('[class*="mainPrice"] ::text').get()
            or selector.css('[class*="mainPrice"]::text').get()
        )
        or str(flight.get("mainPrice") or "").strip()
        or None
    )
    json_ld_price = None
    offers = json_ld.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    json_ld_price = _price(str(offers.get("price") or "")) if offers else None
    current_price = cross_price or json_ld_price or main_price
    list_price = None  # discounts are never kept (business rule)
    currency = str(offers.get("priceCurrency") or "").strip().upper() or (
        "GBP" if "£" in (html[:20000] or "") else ""
    )

    gallery = []
    for image in selector.css(
        'img[src*="joy-sourcing.com"]::attr(src), '
        'link[rel=preload][href*="joy-sourcing.com"]::attr(href)'
    ).getall():
        # Joybuy serves protocol-relative srcs; preload links point at the
        # hi-res variants (s1248x1248 seen live 2026-11-05).
        if image.startswith("//"):
            url = f"https:{image}"
        elif image.startswith("http"):
            url = image
        else:
            url = f"https://{image.lstrip('/')}"
        if "/product/" in url and url not in gallery:
            gallery.append(url)
    json_ld_images = json_ld.get("image") or []
    if isinstance(json_ld_images, str):
        json_ld_images = [json_ld_images]
    for image in json_ld_images:
        url = image if isinstance(image, str) else image.get("url", "")
        if url and "/product/" in url and url not in gallery:
            gallery.insert(0, url)

    breadcrumbs = []
    for crumb in selector.css('nav[class*="breadcrumb"] a, [class*="breadcrumb"] a'):
        name = " ".join(crumb.css("::text").getall()).strip()
        href = crumb.attrib.get("href") or ""
        cid_match = re.search(r"(?:l1|cid[1-4]|firstcid)=(\d+)", href)
        breadcrumbs.append(
            {"name": name, "cid": f"l1:{cid_match.group(1)}" if cid_match else ""}
        )
    # Two-level catalog rule (2026-11-05): deeper levels are dropped here so
    # every downstream consumer sees the same trail length.
    breadcrumbs = truncate_breadcrumbs(breadcrumbs)

    skus = []
    for item in selector.css('[class*="sku"] [data-sku-id], [data-sku-id]'):
        sku_id = (item.attrib.get("data-sku-id") or "").strip()
        if not sku_id:
            continue
        sku_price = _price(item.attrib.get("data-price", "")) or current_price
        skus.append(
            {
                "source_id": sku_id,
                "price": sku_price,
                "availability": (
                    item.attrib.get("data-availability") or "UNKNOWN"
                ).upper(),
                "specs": [],
            }
        )
    if not skus and source_id:
        # Single-variant product: Joybuy detail pages without a SKU list
        # still expose one implicit SKU identified by the product id.
        flight_sku = str(flight.get("skuId") or "").strip()
        skus.append(
            {
                "source_id": flight_sku or source_id,
                "price": current_price,
                "availability": str(flight.get("availability") or "UNKNOWN").upper(),
                "specs": [],
            }
        )

    description_parts = [
        part.strip()
        for part in selector.css(
            '[class*="description"] ::text, [id*="description"] ::text'
        ).getall()
        if part.strip()
    ]
    description = "\n".join(description_parts)
    detail_images = []
    for image in selector.css(
        '[class*="description"] img::attr(src), [id*="description"] img::attr(src)'
    ).getall():
        if image.startswith("//"):
            detail_images.append(f"https:{image}")
        elif image.startswith("http"):
            detail_images.append(image)

    seller_anchor = selector.css('a[href*="/store/"]')
    seller_name = ""
    if seller_anchor:
        # The store card shows the seller name next to a "View store"
        # link; the link text alone is not the seller.
        raw = " ".join(seller_anchor[0].xpath("..").css("::text").getall())
        raw = " ".join(raw.split()).replace("View store", "").strip(" |·")
        seller_name = raw or str(flight.get("sellerName") or "").strip()
    seller_name = seller_name or str(flight.get("sellerName") or "").strip()
    seller_url = seller_anchor[0].attrib.get("href", "") if seller_anchor else ""
    if seller_url.startswith("/"):
        seller_url = f"https://www.joybuy.co.uk{seller_url}"

    # Review data (2026-11-05): aggregates only, never review content.
    # The flight JSON is authoritative; the visible chip is a fallback.
    review = _extract_flight_review(html) or _extract_dom_review(selector)
    rating_average = review.get("average")
    rating_count = review.get("count")
    rating_distribution = review.get("distribution") or {}
    rating_source = review.get("source", "")
    ai_summary = review.get("summary", "")
    ai_summary_title = review.get("summary_title", "")
    ai_summary_tags = review.get("summary_tags", [])

    if rating_average is None or rating_count is None:
        dom_average, dom_count = _rating_from_dom(selector, html)
        rating_average = rating_average or dom_average
        if rating_count is None:
            rating_count = dom_count

    parsed = UkProduct(
        source_id=source_id,
        title=title,
        currency=currency,
        current_price=current_price,
        list_price=list_price,
        main_price=main_price,
        promotion_label="",
        availability=str(flight.get("availability") or "UNKNOWN").upper(),
        brand=brand,
        breadcrumbs=breadcrumbs,
        skus=skus,
        gallery=gallery,
        description=description,
        detail_images=detail_images,
        seller_name=seller_name,
        seller_url=seller_url,
        rating_average=rating_average,
        rating_count=rating_count,
        source_url=source_url,
        rating_distribution=rating_distribution,
        rating_source=rating_source,
        ai_summary=ai_summary,
        ai_summary_title=ai_summary_title,
        ai_summary_tags=ai_summary_tags,
    )
    parsed.missing_fields = [
        name
        for name in (
            "source_id",
            "title",
            "currency",
            "current_price",
            "skus",
        )
        if not getattr(parsed, name)
    ]
    return parsed
