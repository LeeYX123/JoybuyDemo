"""Listing page parser contract (structure version 1).

Parsers only ever run against fixture-verified structures; a page whose
structure no longer matches must fail loudly instead of producing junk
entries (quality gates in WP-19 build on these parsers).
"""

from dataclasses import dataclass

from parsel import Selector

LISTING_STRUCTURE_VERSION = 1
PRODUCT_ITEM_SELECTOR = ".product-list .product-item"
PRODUCT_LINK_SELECTOR = ".product-link::attr(href)"
PRODUCT_TITLE_SELECTOR = ".product-link::text"
POSITION_ATTR = "data-position"


@dataclass(frozen=True)
class ListingEntry:
    """One product slot on a listing page, with its source rank."""

    source_url: str
    rank: int
    title: str


class ListingStructureChanged(RuntimeError):
    """The page no longer matches the fixture-verified structure."""


def _normalize_href(href: str) -> str:
    return href.strip()


def parse_listing_products(html: str) -> list[ListingEntry]:
    """Extract ordered product entries from a listing page.

    Raises :class:`ListingStructureChanged` when no product items are found,
    which callers must treat as a quality-gate signal, not an empty page.
    """

    selector = Selector(text=html)
    items = selector.css(PRODUCT_ITEM_SELECTOR)
    if not items:
        raise ListingStructureChanged(
            "Listing page has no product items; the structure may have changed."
        )
    entries = []
    seen_positions = set()
    for item in items:
        href = item.css(PRODUCT_LINK_SELECTOR).get()
        if not href:
            raise ListingStructureChanged("A product item is missing its link.")
        title = (item.css(PRODUCT_TITLE_SELECTOR).get() or "").strip()
        raw_position = item.attrib.get(POSITION_ATTR, "")
        try:
            rank = int(raw_position)
        except ValueError:
            rank = len(entries) + 1
        if rank in seen_positions:
            raise ListingStructureChanged(f"Duplicate listing position: {rank}.")
        seen_positions.add(rank)
        entries.append(ListingEntry(source_url=_normalize_href(href), rank=rank, title=title))
    entries.sort(key=lambda entry: entry.rank)
    return entries
