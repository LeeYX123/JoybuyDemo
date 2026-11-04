import json

from django.http import JsonResponse

from cart.services import (
    CartError,
    add_item,
    get_or_create_cart,
    merge_anonymous_cart,
    remove_item,
    resolve_cart_context,
    serialize_cart,
    update_item,
)


def _cart_response(request, *, status=200):
    context = resolve_cart_context(request)
    cart = get_or_create_cart(context)
    response = JsonResponse(serialize_cart(cart), status=status)
    from cart.services import _apply_anonymous_cookie

    _apply_anonymous_cookie(response, context)
    return response


def _error(request, exc: CartError, status=400):
    return JsonResponse(
        {
            "error": {"code": exc.code, "message": exc.message, "details": None},
            "request_id": getattr(request, "request_id", None),
        },
        status=status,
    )


def cart_detail(request):
    if request.method == "GET":
        return _cart_response(request)
    return JsonResponse(
        {
            "error": {"code": "METHOD_NOT_ALLOWED", "message": "Unsupported method."},
            "request_id": getattr(request, "request_id", None),
        },
        status=405,
    )


def cart_items(request):
    if request.method != "POST":
        return JsonResponse(
            {
                "error": {"code": "METHOD_NOT_ALLOWED", "message": "Unsupported method."},
                "request_id": getattr(request, "request_id", None),
            },
            status=405,
        )
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
    context = resolve_cart_context(request)
    try:
        add_item(
            context,
            offer_public_id=str(body.get("offer_public_id") or ""),
            quantity=body.get("quantity", 1),
        )
    except CartError as exc:
        return _error(request, exc)
    response = JsonResponse({"added": True}, status=201)
    from cart.services import _apply_anonymous_cookie

    _apply_anonymous_cookie(response, context)
    return response


def cart_item_detail(request, item_public_id):
    if request.method not in {"PATCH", "PUT", "DELETE"}:
        return JsonResponse(
            {
                "error": {"code": "METHOD_NOT_ALLOWED", "message": "Unsupported method."},
                "request_id": getattr(request, "request_id", None),
            },
            status=405,
        )
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        body = {}
    context = resolve_cart_context(request)
    try:
        if request.method == "DELETE":
            remove_item(context, item_public_id=str(item_public_id))
        else:
            update_item(
                context,
                item_public_id=str(item_public_id),
                quantity=body.get("quantity"),
            )
    except CartError as exc:
        status = 404 if "no longer exists" in exc.message else 400
        return _error(request, exc, status)
    return _cart_response(request)


def cart_merge(request):
    if request.method != "POST":
        return JsonResponse(
            {
                "error": {"code": "METHOD_NOT_ALLOWED", "message": "Unsupported method."},
                "request_id": getattr(request, "request_id", None),
            },
            status=405,
        )
    context = resolve_cart_context(request)
    try:
        result = merge_anonymous_cart(context)
    except CartError as exc:
        return _error(request, exc, 401)
    response = JsonResponse(result)
    from cart.services import _apply_anonymous_cookie

    _apply_anonymous_cookie(response, context)
    return response
