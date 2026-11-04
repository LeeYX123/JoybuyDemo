from django.http import JsonResponse

from catalog.models import LocalCategory
from catalog.search_services import SearchParamsInvalid, search_documents
from offers.models import Market

PAGE_SIZE = 24


def serialize_category(category: LocalCategory) -> dict:
    return {
        "public_id": str(category.public_id),
        "name": category.name,
        "name_en": category.name_en,
        "name_zh": category.name_zh,
        "slug": category.slug,
        "depth": category.depth,
    }


def category_tree(request):
    """ACTIVE local navigation tree: roots with their direct children.

    The Categories panel (docs/12 §2) needs parent -> child linkage, so the
    nesting is done server-side; each root only carries one child level. The
    standard category order (docs/12 global convention #1) is ``sort_order``.
    """

    roots = LocalCategory.objects.filter(
        status=LocalCategory.Status.ACTIVE, parent__isnull=True
    ).order_by("sort_order", "path", "pk")
    children = LocalCategory.objects.filter(
        status=LocalCategory.Status.ACTIVE, parent__isnull=False
    ).order_by("sort_order", "path", "pk")
    children_by_parent = {}
    for item in children:
        children_by_parent.setdefault(item.parent_id, []).append(item)
    payload = []
    for root in roots:
        data = serialize_category(root)
        data["children"] = [
            serialize_category(child) for child in children_by_parent.get(root.pk, [])
        ]
        payload.append(data)
    return JsonResponse({"categories": payload})


def storefront_search(request):
    """Search and filter search documents; query params drive everything."""

    market = Market.objects.filter(code="GB", is_active=True).first()
    if market is None:
        return JsonResponse(
            {
                "error": {"code": "MARKET_UNAVAILABLE", "message": "Market not configured."},
                "request_id": getattr(request, "request_id", None),
            },
            status=503,
        )

    category = None
    category_slug = request.GET.get("category", "").strip()
    if category_slug:
        category = LocalCategory.objects.filter(
            slug=category_slug, status=LocalCategory.Status.ACTIVE
        ).first()
        if category is None:
            return JsonResponse(
                {
                    "error": {"code": "CATEGORY_NOT_FOUND", "message": "Unknown category."},
                    "request_id": getattr(request, "request_id", None),
                },
                status=404,
            )

    try:
        page = int(request.GET.get("page", "1"))
    except ValueError:
        page = 1
    try:
        result = search_documents(
            market=market,
            query=request.GET.get("q", ""),
            category=category,
            brand=request.GET.get("brand", ""),
            min_price=request.GET.get("min_price"),
            max_price=request.GET.get("max_price"),
            sort=request.GET.get("sort", "relevance"),
            page=page,
        )
    except SearchParamsInvalid as exc:
        return JsonResponse(
            {
                "error": {"code": "SEARCH_PARAMS_INVALID", "message": str(exc)},
                "request_id": getattr(request, "request_id", None),
            },
            status=400,
        )
    return JsonResponse(result)
