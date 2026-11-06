from django.http import JsonResponse

from catalog.localization_services import localized_specification, resolve_product_content
from catalog.models import Sku, Spu
from offers.market_services import offer_market_chain, resolve_market_context
from offers.models import Offer
from reviews.models import Review


def _offer_payload(offer: Offer, *, requested_market, price_source_market) -> dict:
    return {
        "public_id": str(offer.public_id),
        "price": str(offer.current_price),
        "list_price": str(offer.list_price) if offer.list_price is not None else None,
        "promotion_label": offer.promotion_label,
        "currency": offer.currency.code,
        "display_currency_symbol": requested_market.display_currency_symbol,
        "price_source_market": price_source_market.code,
        "inventory_display": offer.display_inventory,
        "source_availability": offer.source_availability,
        "is_purchasable": (
            offer.status == Offer.Status.ACTIVE
            and offer.local_inventory > 0
            and offer.source_availability != Offer.SourceAvailability.UNAVAILABLE
        ),
    }


def product_detail(request, public_id):
    """Localized storefront product detail for the requested market and locale."""

    context = resolve_market_context(request)
    if context is None:
        return JsonResponse(
            {
                "error": {"code": "MARKET_UNAVAILABLE", "message": "Market not configured."},
                "request_id": getattr(request, "request_id", None),
            },
            status=503,
        )

    spu = (
        Spu.objects.filter(public_id=public_id, status=Spu.Status.ACTIVE)
        .select_related("brand", "local_category")
        .prefetch_related(
            "translations",
            "market_contents__locale",
            "market_contents__market",
        )
        .first()
    )
    if spu is None:
        return JsonResponse(
            {
                "error": {"code": "PRODUCT_NOT_AVAILABLE", "message": "Product not available."},
                "request_id": getattr(request, "request_id", None),
            },
            status=404,
        )

    market = context.market
    locale = context.locale
    buyer_account = getattr(request, "buyer_account", None)
    if buyer_account is not None:
        from accounts_buyers.activity_views import record_view

        record_view(spu, buyer_account)
    content = resolve_product_content(spu, market, locale)
    skus = []
    sku_queryset = (
        Sku.objects.filter(spu=spu, status=Sku.Status.ACTIVE)
        .prefetch_related("specification_translations__locale")
        .order_by("pk")
    )
    for sku in sku_queryset:
        offer = None
        price_source_market = market
        for candidate_market in offer_market_chain(market):
            offer = (
                Offer.objects.filter(
                    sku=sku,
                    market=candidate_market,
                    status=Offer.Status.ACTIVE,
                )
                .select_related("currency")
                .first()
            )
            if offer:
                price_source_market = candidate_market
                break
        display_specification, specification_translated = localized_specification(sku, locale)
        sku_entry = {
            "public_id": str(sku.public_id),
            "specification": display_specification,
            "canonical_specification": sku.specification,
            "specification_locale": locale.code if specification_translated else None,
            "specification_translated": specification_translated,
            "offer": (
                _offer_payload(
                    offer,
                    requested_market=market,
                    price_source_market=price_source_market,
                )
                if offer
                else None
            ),
        }
        skus.append(sku_entry)

    from django.db.models import Avg, Count

    review_stats = Review.objects.filter(spu=spu, status=Review.Status.ACTIVE).aggregate(
        average=Avg("rating"), count=Count("pk")
    )

    gallery = []
    from django.contrib.contenttypes.models import ContentType

    from media.models import MediaUsage

    spu_usages = MediaUsage.objects.filter(
        content_type=ContentType.objects.get_for_model(Spu), object_id=spu.pk
    ).select_related("asset")
    for usage in spu_usages:
        from media.views import asset_urls

        gallery.append(asset_urls(usage.asset))

    return JsonResponse(
        {
            "public_id": str(spu.public_id),
            "market": market.code,
            "requested_locale": locale.code,
            "content_locale": content.content_locale,
            "content_market": content.content_market,
            "content_origin": content.origin,
            "display_currency_symbol": market.display_currency_symbol,
            "title": content.title,
            "subtitle": content.subtitle,
            "description": content.description,
            "brand": spu.brand.name if spu.brand else None,
            "category_slug": spu.local_category.slug if spu.local_category else None,
            "gallery": gallery,
            "skus": skus,
            "review_summary": {
                "average": str(review_stats["average"]) if review_stats["average"] else None,
                "count": review_stats["count"] or 0,
            },
        }
    )
