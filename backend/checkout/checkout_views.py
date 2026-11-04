"""Checkout quote (WP-28): server-side pricing, UK shipping rules.

The server is the single source of truth for the payable amount: the cart's
live prices, the serviceability of the chosen address and the configurable
shipping rule all feed one quote. No discount stacking in phase 1.
"""

import json
from decimal import Decimal

from cart.services import get_or_create_cart, resolve_cart_context, serialize_cart
from django.conf import settings
from django.http import JsonResponse

from checkout.models import Address

FREE_SHIPPING_THRESHOLD = getattr(settings, "CHECKOUT_FREE_SHIPPING_THRESHOLD", None) or Decimal(
    "20.00"
)
STANDARD_SHIPPING = Decimal("3.99")


def compute_shipping(subtotal, currency: str) -> tuple[str, str]:
    if currency != "GBP" or subtotal is None:
        return "0.0000", "UNAVAILABLE"
    if subtotal >= FREE_SHIPPING_THRESHOLD:
        return "0.0000", "FREE"
    return str(STANDARD_SHIPPING), "STANDARD"


def _error(request, code, message, status=400):
    return JsonResponse(
        {
            "error": {"code": code, "message": message, "details": None},
            "request_id": getattr(request, "request_id", None),
        },
        status=status,
    )


def address_list(request):
    if request.method == "GET":
        account = getattr(request, "buyer_account", None)
        if account is None:
            return _error(request, "AUTH_REQUIRED", "Sign in required.", 401)
        addresses = [
            {
                "public_id": str(address.public_id),
                **address.as_snapshot(),
                "is_default": address.is_default,
                "is_serviceable": address.is_serviceable,
            }
            for address in account.addresses.all()
        ]
        return JsonResponse({"addresses": addresses})

    if request.method == "POST":
        account = getattr(request, "buyer_account", None)
        if account is None:
            return _error(request, "AUTH_REQUIRED", "Sign in required.", 401)
        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return _error(request, "BAD_REQUEST", "Invalid JSON.")
        required = ("full_name", "phone", "line1", "city", "postcode")
        missing = [field for field in required if not str(body.get(field) or "").strip()]
        if missing:
            return _error(request, "ADDRESS_INCOMPLETE", f"Missing: {', '.join(missing)}.")
        from checkout.models import is_supported_postcode

        if not is_supported_postcode(str(body.get("postcode"))):
            return _error(
                request,
                "ADDRESS_UNSUPPORTED",
                "Only UK addresses are supported in this region.",
            )
        address = Address.objects.create(
            account=account,
            full_name=str(body["full_name"]).strip()[:160],
            phone=str(body["phone"]).strip()[:32],
            line1=str(body["line1"]).strip()[:200],
            line2=str(body.get("line2") or "").strip()[:200],
            city=str(body["city"]).strip()[:100],
            county=str(body.get("county") or "").strip()[:100],
            postcode=str(body["postcode"]).strip().upper()[:10],
            is_default=not account.addresses.exists(),
        )
        return JsonResponse(
            {"public_id": str(address.public_id), "is_serviceable": address.is_serviceable},
            status=201,
        )

    return _error(request, "METHOD_NOT_ALLOWED", "Unsupported method.", 405)


def checkout_quote(request):
    """POST {address_public_id} -> server-computed items/shipping/total."""

    if request.method != "POST":
        return _error(request, "METHOD_NOT_ALLOWED", "Unsupported method.", 405)
    account = getattr(request, "buyer_account", None)
    if account is None:
        return _error(request, "AUTH_REQUIRED", "Sign in required.", 401)

    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return _error(request, "BAD_REQUEST", "Invalid JSON.")
    address = Address.objects.filter(
        account=account, public_id=str(body.get("address_public_id") or "")
    ).first()
    if address is None:
        return _error(request, "ADDRESS_NOT_FOUND", "Address not found.", 404)
    if not address.is_serviceable:
        return _error(
            request,
            "ADDRESS_UNSUPPORTED",
            "We do not deliver to this address yet.",
        )

    context = resolve_cart_context(request)
    cart = get_or_create_cart(context)
    snapshot = serialize_cart(cart)
    if snapshot["needs_attention"] or not snapshot["items"]:
        return _error(
            request,
            "CART_INVALID",
            "Your cart needs attention before checkout.",
        )

    from decimal import Decimal

    subtotal = Decimal(snapshot["subtotal"])
    shipping_cost, shipping_method = compute_shipping(subtotal, snapshot["currency"])
    total = subtotal + Decimal(shipping_cost)
    return JsonResponse(
        {
            "currency": snapshot["currency"],
            "items": snapshot["items"],
            "subtotal": str(subtotal),
            "shipping_cost": shipping_cost,
            "shipping_method": shipping_method,
            "total": str(total),
            "address": address.as_snapshot(),
        }
    )
