from django.http import JsonResponse

from content.services import get_published_page, serialize_page


def storefront_home(request):
    """Published home page modules for the SSR renderer (no auth, read-only)."""

    page = get_published_page("home")
    if page is None:
        return JsonResponse(
            {
                "error": {"code": "CMS_PAGE_NOT_PUBLISHED", "message": "Home page not published."},
                "request_id": getattr(request, "request_id", None),
            },
            status=503,
        )
    return JsonResponse(serialize_page(page))
