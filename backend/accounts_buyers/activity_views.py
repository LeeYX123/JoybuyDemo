import json

from django.http import JsonResponse
from django.utils import timezone

from accounts_buyers.models import Favourite, RecentlyViewed
from catalog.models import ProductSearchDocument, Spu
from offers.models import Market

PAGE_SIZE = 12
MAX_PAGE = 100


def _require_buyer(request):
    account = getattr(request, "buyer_account", None)
    if account is None:
        return None, JsonResponse(
            {
                "error": {"code": "AUTH_REQUIRED", "message": "Sign in required."},
                "request_id": getattr(request, "request_id", None),
            },
            status=401,
        )
    return account, None


def _serialize_cards(rows):
    market = Market.objects.filter(code="GB", is_active=True).first()
    cards = []
    for row in rows:
        document = (
            ProductSearchDocument.objects.filter(spu=row.spu, market=market, is_searchable=True)
            .select_related("spu", "local_category")
            .first()
        )
        translation = row.spu.translations.order_by("pk").first()
        title = document.title if document else (translation.title if translation else "")
        cards.append(
            {
                "spu_public_id": str(row.spu.public_id),
                "title": title,
                "price_min": str(document.min_price) if document and document.min_price else None,
                "currency": document.currency_code if document else "GBP",
                "rating_average": (
                    str(document.rating_average)
                    if document and document.rating_average is not None
                    else None
                ),
                "rating_count": document.rating_count if document else 0,
                "added_at": (
                    row.created_at.isoformat()
                    if getattr(row, "created_at", None)
                    else row.viewed_at.isoformat()
                ),
            }
        )
    return cards


def favourites(request):
    account, denied = _require_buyer(request)
    if denied:
        return denied

    if request.method == "GET":
        try:
            page = max(1, min(int(request.GET.get("page", "1")), MAX_PAGE))
        except ValueError:
            page = 1
        queryset = Favourite.objects.filter(account=account).select_related("spu")
        total = queryset.count()
        offset = (page - 1) * PAGE_SIZE
        rows = list(queryset[offset : offset + PAGE_SIZE])
        return JsonResponse(
            {
                "page": page,
                "page_size": PAGE_SIZE,
                "total": total,
                "total_pages": (total + PAGE_SIZE - 1) // PAGE_SIZE,
                "items": _serialize_cards(rows),
            }
        )

    if request.method == "POST":
        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return JsonResponse(
                {
                    "error": {"code": "BAD_REQUEST", "message": "Invalid JSON."},
                    "request_id": getattr(request, "request_id", None),
                },
                status=400,
            )
        spu_public_id = str(body.get("spu_public_id") or "").strip()
        spu = Spu.objects.filter(public_id=spu_public_id).first() if spu_public_id else None
        if spu is None:
            return JsonResponse(
                {
                    "error": {"code": "PRODUCT_NOT_AVAILABLE", "message": "Unknown product."},
                    "request_id": getattr(request, "request_id", None),
                },
                status=404,
            )
        _, created = Favourite.objects.get_or_create(account=account, spu=spu)
        return JsonResponse({"added": created}, status=201 if created else 200)

    if request.method == "DELETE":
        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            body = {}
        spu_public_id = str(body.get("spu_public_id") or "").strip()
        deleted, _ = Favourite.objects.filter(
            account=account, spu__public_id=spu_public_id
        ).delete()
        return JsonResponse({"removed": bool(deleted)})

    return JsonResponse(
        {
            "error": {"code": "METHOD_NOT_ALLOWED", "message": "Unsupported method."},
            "request_id": getattr(request, "request_id", None),
        },
        status=405,
    )


def recently_viewed(request):
    account, denied = _require_buyer(request)
    if denied:
        return denied

    if request.method == "GET":
        try:
            page = max(1, min(int(request.GET.get("page", "1")), MAX_PAGE))
        except ValueError:
            page = 1
        queryset = RecentlyViewed.objects.filter(account=account).select_related("spu")
        total = queryset.count()
        offset = (page - 1) * PAGE_SIZE
        rows = list(queryset[offset : offset + PAGE_SIZE])
        cards = _serialize_cards(rows)
        for card, row in zip(cards, rows):
            card["viewed_at"] = row.viewed_at.isoformat()
        return JsonResponse(
            {
                "page": page,
                "page_size": PAGE_SIZE,
                "total": total,
                "total_pages": (total + PAGE_SIZE - 1) // PAGE_SIZE,
                "items": cards,
            }
        )

    if request.method == "DELETE":
        spu_public_id = request.GET.get("spu_public_id", "").strip()
        if spu_public_id:
            deleted, _ = RecentlyViewed.objects.filter(
                account=account, spu__public_id=spu_public_id
            ).delete()
            return JsonResponse({"removed": bool(deleted)})
        deleted, _ = RecentlyViewed.objects.filter(account=account).delete()
        return JsonResponse({"cleared": True, "removed": deleted})

    return JsonResponse(
        {
            "error": {"code": "METHOD_NOT_ALLOWED", "message": "Unsupported method."},
            "request_id": getattr(request, "request_id", None),
        },
        status=405,
    )


def record_view(spu, account):
    """Bump the recently-viewed marker; called from the detail view."""

    RecentlyViewed.objects.update_or_create(
        account=account,
        spu=spu,
        defaults={"viewed_at": timezone.now()},
    )
