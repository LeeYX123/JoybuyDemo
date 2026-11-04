"""Product detail parser contract (structure version 1).

``parse_product_detail`` returns a normalized payload ready for staging and
import; required-field gaps are reported in ``missing_fields`` so the
quality gates (WP-19) can act on them instead of importing junk.

Business rule (2026-11-03): only ORIGINAL prices are crawled. When the
source page shows a discounted price next to a list price, the list price
wins and the discount is discarded — ``current_price`` carries the original
price and every SKU inherits it, so imported offers always present one
original price. ``list_price`` stays ``None`` because no promo split is
kept. Pages without a list price fall back to the only price shown.
"""

import re
from dataclasses import dataclass, field

from parsel import Selector

PRODUCT_STRUCTURE_VERSION = 1
PRODUCT_CONTAINER_SELECTOR = ".product-detail"

REQUIRED_FIELDS = ("source_id", "title", "currency", "current_price", "skus")

_PRICE_PATTERN = re.compile(r"[-+]?\d+(?:\.\d+)?")


@dataclass
class ParsedProduct:
    source_id: str
    title: str
    currency: str
    current_price: str | None
    list_price: str | None
    promotion_label: str
    availability: str
    brand: str
    source_category_id: str
    source_seller_id: str
    source_seller_name: str
    description: str
    rating_count: int | None
    rating_average: str | None
    skus: list[dict] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)

    def to_payload(self) -> dict:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "currency": self.currency,
            "current_price": self.current_price,
            "list_price": self.list_price,
            "promotion_label": self.promotion_label,
            "availability": self.availability,
            "brand": self.brand,
            "source_category_id": self.source_category_id,
            "source_seller_id": self.source_seller_id,
            "source_seller_name": self.source_seller_name,
            "description": self.description,
            "rating_count": self.rating_count,
            "rating_average": self.rating_average,
            "skus": self.skus,
            "image_urls": self.image_urls,
            "missing_fields": self.missing_fields,
        }


def _extract_price(selector) -> str | None:
    raw = selector.attrib.get("data-price") or (selector.get() or "")
    match = _PRICE_PATTERN.search(raw)
    return match.group(0) if match else None


def parse_product_detail(html: str) -> ParsedProduct:
    selector = Selector(text=html)
    container = selector.css(PRODUCT_CONTAINER_SELECTOR)
    if not container:
        raise RuntimeError("Product detail page does not match the expected structure.")

    root = container[0]
    source_id = (root.attrib.get("data-product-id") or "").strip()
    title = (root.css(".product-title::text").get() or "").strip()
    currency = (root.attrib.get("data-currency") or "").strip().upper()
    availability = (root.attrib.get("data-availability") or "UNKNOWN").strip().upper()

    current_el = root.css(".price .current")
    list_el = root.css(".price .list")
    discounted_price = _extract_price(current_el[0]) if current_el else None
    original_price = _extract_price(list_el[0]) if list_el else None
    promotion_label = (root.css(".price .promo::text").get() or "").strip()

    # Business rule: only original prices are crawled. The discounted price
    # is discarded in favour of the original (list) price; per-SKU data-price
    # values are discounted display prices, so every SKU inherits the
    # original price too. Without a list price the only price shown counts
    # as the original price and per-SKU prices are kept.
    current_price = original_price or discounted_price
    list_price = None

    skus = []
    for item in root.css(".sku-list .sku-item"):
        specs = [
            {
                "name": (spec.attrib.get("data-name") or "").strip(),
                "value": (spec.attrib.get("data-value") or "").strip(),
            }
            for spec in item.css(".spec")
        ]
        price_raw = item.attrib.get("data-price") or ""
        price_match = _PRICE_PATTERN.search(price_raw)
        sku_price = price_match.group(0) if price_match else None
        if original_price:
            sku_price = original_price
        skus.append(
            {
                "source_id": (item.attrib.get("data-sku-id") or "").strip(),
                "price": sku_price,
                "availability": (item.attrib.get("data-availability") or "UNKNOWN").upper(),
                "specs": specs,
            }
        )

    rating_el = root.css(".rating")
    rating_count = None
    rating_average = None
    if rating_el:
        count_raw = rating_el[0].attrib.get("data-count")
        average_raw = rating_el[0].attrib.get("data-average")
        rating_count = int(count_raw) if count_raw and count_raw.isdigit() else None
        rating_average = average_raw or None

    parsed = ParsedProduct(
        source_id=source_id,
        title=title,
        currency=currency,
        current_price=current_price,
        list_price=list_price,
        promotion_label=promotion_label,
        availability=availability,
        brand=(root.css(".brand::attr(data-brand)").get() or "").strip(),
        source_category_id=(root.css(".breadcrumb::attr(data-category-id)").get() or "").strip(),
        source_seller_id=(root.css(".seller::attr(data-seller-id)").get() or "").strip(),
        source_seller_name=(root.css(".seller::attr(data-seller-name)").get() or "").strip(),
        description="\n".join(
            part.strip() for part in root.css(".description ::text").getall() if part.strip()
        ),
        rating_count=rating_count,
        rating_average=rating_average,
        skus=skus,
        image_urls=[url for url in root.css(".product-image::attr(src)").getall() if url],
    )
    parsed.missing_fields = [name for name in REQUIRED_FIELDS if not getattr(parsed, name)]
    return parsed
