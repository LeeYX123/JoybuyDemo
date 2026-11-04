from catalog.models import Spu
from django.db.models import Avg, Count
from django.http import JsonResponse
from media.views import asset_urls

from reviews.models import Review, ReviewMedia

PAGE_SIZE = 10
MAX_PAGE = 200


def product_reviews(request, public_id):
    """Paginated ACTIVE source reviews for one product with rating facets."""

    spu = Spu.objects.filter(public_id=public_id).first()
    if spu is None:
        return JsonResponse(
            {
                "error": {"code": "PRODUCT_NOT_AVAILABLE", "message": "Product not available."},
                "request_id": getattr(request, "request_id", None),
            },
            status=404,
        )

    try:
        page = int(request.GET.get("page", "1"))
    except ValueError:
        page = 1
    page = max(1, min(page, MAX_PAGE))
    rating_filter = request.GET.get("rating", "").strip()

    queryset = Review.objects.filter(spu=spu, status=Review.Status.ACTIVE)
    if rating_filter:
        if rating_filter not in {"1", "2", "3", "4", "5"}:
            return JsonResponse(
                {
                    "error": {"code": "REVIEW_FILTER_INVALID", "message": "rating must be 1-5."},
                    "request_id": getattr(request, "request_id", None),
                },
                status=400,
            )
        queryset = queryset.filter(rating=int(rating_filter))

    facets = (
        Review.objects.filter(spu=spu, status=Review.Status.ACTIVE)
        .values("rating")
        .annotate(count=Count("pk"))
    )
    distribution = {str(star): 0 for star in range(1, 6)}
    for row in facets:
        distribution[str(row["rating"])] = row["count"]
    overall = Review.objects.filter(spu=spu, status=Review.Status.ACTIVE).aggregate(
        average=Avg("rating"), count=Count("pk")
    )

    total = queryset.count()
    offset = (page - 1) * PAGE_SIZE
    reviews = []
    for review in queryset.order_by("-source_reviewed_at", "-pk")[
        offset : offset + PAGE_SIZE
    ].select_related("reviewer"):
        media_items = []
        for media in ReviewMedia.objects.filter(review=review).select_related("asset"):
            urls = asset_urls(media.asset)
            media_items.append(
                {
                    "kind": media.media_kind,
                    "url": urls["url"],
                    "variants": urls["variants"],
                }
            )
        display_name = (
            review.reviewer.display_name if review.reviewer else review.guest_display_name
        )
        reviews.append(
            {
                "public_id": str(review.public_id),
                "rating": review.rating,
                "title": review.title,
                "body": review.body,
                "display_name": display_name or "Verified buyer",
                "variant_text": review.variant_text,
                "likes_count": review.likes_count,
                "reviewed_at": (
                    review.source_reviewed_at.isoformat() if review.source_reviewed_at else None
                ),
                "media": media_items,
            }
        )

    return JsonResponse(
        {
            "average": str(overall["average"]) if overall["average"] is not None else None,
            "count": overall["count"] or 0,
            "distribution": distribution,
            "page": page,
            "page_size": PAGE_SIZE,
            "filtered_total": total,
            "total_pages": (total + PAGE_SIZE - 1) // PAGE_SIZE,
            "items": reviews,
        }
    )
