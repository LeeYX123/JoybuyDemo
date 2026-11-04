"""Storefront search and category listing (WP-22).

Reads only the flattened ``ProductSearchDocument`` table so every list
query is fully indexed (docs/03 §5). Text search uses MySQL FULLTEXT with
a fallback to prefix LIKE for short queries; sorting and pagination are
stable (price/rating tiebreak on spu id) and depth-capped.
"""

from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.utils import timezone

from catalog.models import ProductSearchDocument

SORT_CHOICES = (
    "relevance",
    "price_asc",
    "price_desc",
    "rating_desc",
    "newest",
)

MAX_PAGE = 50
PAGE_SIZE = 24


class SearchParamsInvalid(Exception):
    pass


def _parse_decimal(value):
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    return parsed


def rebuild_search_documents(*, market, full: bool = True) -> int:
    """Rebuild search documents for one market from live catalog data.

    Full rebuild: refresh every SPU with an ACTIVE offer. Returns the
    number of documents written. Incremental per-SPU refresh is done by
    ``rebuild_search_document(spu, market)`` called by import flows.
    """

    from offers.models import Offer

    from catalog.models import Spu

    del full
    spu_ids = set(
        Offer.objects.filter(
            market=market, status=Offer.Status.ACTIVE, sku__spu__status=Spu.Status.ACTIVE
        ).values_list("sku__spu_id", flat=True)
    )
    for spu in Spu.objects.filter(pk__in=spu_ids):
        rebuild_search_document(spu, market=market)
    return len(spu_ids)


def rebuild_search_document(spu, *, market) -> ProductSearchDocument:
    """Refresh the search document of one SPU from its ACTIVE offers."""

    from django.db.models import Avg, Count
    from offers.models import Offer
    from reviews.models import Review

    from catalog.models import Spu

    active_offers = list(
        Offer.objects.filter(
            sku__spu=spu, market=market, status=Offer.Status.ACTIVE
        ).select_related("currency")
    )
    translation = spu.translations.order_by("pk").first()
    review_stats = Review.objects.filter(spu=spu, status=Review.Status.ACTIVE).aggregate(
        average=Avg("rating"), count=Count("pk")
    )
    has_offer = bool(active_offers)
    prices = [offer.current_price for offer in active_offers] or [None]
    document, _ = ProductSearchDocument.objects.update_or_create(
        spu=spu,
        market=market,
        defaults={
            "title": (translation.title if translation else "")[:500],
            "brand_name": spu.brand.name if spu.brand else "",
            "local_category": spu.local_category,
            "min_price": min(prices),
            "max_price": max(prices),
            "currency_code": active_offers[0].currency.code if active_offers else "",
            "rating_average": review_stats["average"],
            "rating_count": review_stats["count"] or 0,
            "is_searchable": has_offer and spu.status == Spu.Status.ACTIVE,
            "published_at": timezone.now() if has_offer else None,
        },
    )
    return document


def search_documents(
    *,
    market,
    query: str = "",
    category=None,
    brand: str = "",
    min_price=None,
    max_price=None,
    sort: str = "relevance",
    page: int = 1,
) -> dict:
    """Query search documents; returns a serializable result envelope."""

    if sort not in SORT_CHOICES:
        raise SearchParamsInvalid(f"Unknown sort: {sort}.")
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        raise SearchParamsInvalid("page must be a positive integer.")
    page = min(page, MAX_PAGE)

    queryset = ProductSearchDocument.objects.filter(market=market, is_searchable=True)
    query = (query or "").strip()
    if query:
        cleaned = " ".join(query.split())[:100]
        from django.db import connection
        from django.db.models.expressions import RawSQL

        if connection.vendor == "mysql":
            boolean = " ".join(f"+{term}*" for term in cleaned.split() if term)
            if boolean:
                relevance = RawSQL(
                    "(MATCH(title) AGAINST (%s IN BOOLEAN MODE)"
                    " + MATCH(brand_name) AGAINST (%s IN BOOLEAN MODE))",
                    (boolean, boolean),
                )
                queryset = queryset.alias(relevance=relevance).filter(relevance__gt=0)
                if sort == "relevance":
                    queryset = queryset.order_by("-relevance", "pk")
        else:
            # Non-MySQL backends (local SQLite checks) fall back to contains.
            queryset = queryset.filter(
                Q(title__icontains=cleaned) | Q(brand_name__icontains=cleaned)
            )
    if category is not None:
        from catalog.services import local_category_descendants

        category_ids = {
            category.pk,
            *local_category_descendants(category).values_list("pk", flat=True),
        }
        queryset = queryset.filter(local_category_id__in=category_ids)
    if brand.strip():
        queryset = queryset.filter(brand_name__iexact=brand.strip())
    parsed_min = _parse_decimal(min_price)
    parsed_max = _parse_decimal(max_price)
    if parsed_min is not None:
        queryset = queryset.filter(max_price__gte=parsed_min)
    if parsed_max is not None:
        queryset = queryset.filter(min_price__lte=parsed_max)

    orderings = {
        "relevance": ("title", "pk"),
        "price_asc": ("min_price", "pk"),
        "price_desc": ("-min_price", "pk"),
        "rating_desc": ("-rating_average", "-rating_count", "pk"),
        "newest": ("-published_at", "-pk"),
    }
    queryset = queryset.order_by(*orderings[sort])

    total = queryset.count()
    offset = (page - 1) * PAGE_SIZE
    rows = list(queryset[offset : offset + PAGE_SIZE])
    return {
        "query": query,
        "page": page,
        "page_size": PAGE_SIZE,
        "total": total,
        "total_pages": (total + PAGE_SIZE - 1) // PAGE_SIZE,
        "sort": sort,
        "items": [serialize_search_row(row) for row in rows],
    }


def serialize_search_row(row: ProductSearchDocument) -> dict:
    return {
        "spu_public_id": str(row.spu.public_id),
        "title": row.title,
        "brand": row.brand_name,
        "category_slug": row.local_category.slug if row.local_category else None,
        "price_min": str(row.min_price) if row.min_price is not None else None,
        "price_max": str(row.max_price) if row.max_price is not None else None,
        "currency": row.currency_code,
        "rating_average": str(row.rating_average) if row.rating_average is not None else None,
        "rating_count": row.rating_count,
    }
