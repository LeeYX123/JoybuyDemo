from django.http import JsonResponse
from offers.models import Market, Offer
from reviews.models import Review

from catalog.models import Sku, Spu


def _offer_payload(offer: Offer) -> dict:
    return {
        "public_id": str(offer.public_id),
        "price": str(offer.current_price),
        "list_price": str(offer.list_price) if offer.list_price is not None else None,
        "promotion_label": offer.promotion_label,
        "currency": offer.currency.code,
        "inventory_display": offer.display_inventory,
        "source_availability": offer.source_availability,
        "is_purchasable": (
            offer.status == Offer.Status.ACTIVE
            and offer.local_inventory > 0
            and offer.source_availability != Offer.SourceAvailability.UNAVAILABLE
        ),
    }


def product_detail(request, public_id):
    """Storefront product detail: SPU content, ACTIVE SKUs with GB offers,
    review summary and gallery media (empty until WP-18 usages exist)."""

    spu = (
        Spu.objects.filter(public_id=public_id, status=Spu.Status.ACTIVE)
        .select_related("brand", "local_category")
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

    market = Market.objects.filter(code="GB", is_active=True).first()
    buyer_account = getattr(request, "buyer_account", None)
    if buyer_account is not None:
        from accounts_buyers.activity_views import record_view

        record_view(spu, buyer_account)
    translation = spu.translations.order_by("pk").first()
    skus = []
    for sku in Sku.objects.filter(spu=spu, status=Sku.Status.ACTIVE).order_by("pk"):
        offer = (
            Offer.objects.filter(sku=sku, market=market, status=Offer.Status.ACTIVE)
            .select_related("currency")
            .first()
        )
        sku_entry = {
            "public_id": str(sku.public_id),
            "specification": sku.specification,
            "offer": _offer_payload(offer) if offer else None,
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
            "title": translation.title if translation else "",
            "description": translation.description if translation else "",
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
