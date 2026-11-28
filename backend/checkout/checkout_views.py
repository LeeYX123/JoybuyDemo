"""Checkout quote (WP-28): server-side pricing, UK shipping rules.

The server is the single source of truth for the payable amount: the cart's
live prices, the serviceability of the chosen address and the configurable
shipping rule all feed one quote. No discount stacking in phase 1.
"""

import json
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse

from cart.models import MAX_QTY_PER_ITEM
from cart.services import get_or_create_cart, resolve_cart_context, serialize_cart
from checkout.models import Address, is_supported_postcode
from offers.market_services import resolve_market_context
from offers.models import Offer

FREE_SHIPPING_THRESHOLD = getattr(settings, "CHECKOUT_FREE_SHIPPING_THRESHOLD", None) or Decimal(
    "20.00"
)
STANDARD_SHIPPING = Decimal("3.99")


def compute_shipping(subtotal, currency: str) -> tuple[str, str]:
    # 2026-11-28 用户拍板：全站免邮——任意金额运费一律 0（原满额免邮/3.99
    # 标准运费档位作废）。保留 UNAVAILABLE 分支以兼容非 GBP 演示币种。
    if currency != "GBP" or subtotal is None:
        return "0.0000", "UNAVAILABLE"
    return "0.0000", "FREE"


def _parse_direct_quantity(value) -> int | None:
    """直购数量解析：缺省 1；非法（非正整数/超单件上限）返回 None。"""

    if value in (None, ""):
        return 1
    if isinstance(value, bool):
        return None
    try:
        quantity = int(value)
    except (TypeError, ValueError):
        return None
    if quantity < 1 or quantity > MAX_QTY_PER_ITEM:
        return None
    return quantity


def serialize_direct_purchase(offer: Offer, quantity: int, *, market=None, locale=None) -> dict:
    """立即购买（Buy now）的独立直购快照（2026-11-28）。

    与 ``serialize_cart`` 同形（items/subtotal/currency/needs_attention），
    但不读写购物车：快照行只有一个 offer，行级 ``is_valid`` / ``issue`` /
    ``needs_attention`` 判定与购物车行完全同口径（offer 非 ACTIVE / 无库存 /
    UNAVAILABLE → SKU_NOT_AVAILABLE；quantity 超 local_inventory →
    INSUFFICIENT_STOCK 并钳到库存）。额外带 ``total``（小计 + 运费）供
    place_order 直购路径做余额校验/扣款；购物车快照路径维持现状不动。

    ``market``/``locale``：结账页请求上下文，行标题与购物车同源本地化
    （2026-11-28 修复中文站仍显示英文商品名）；不传的调用方（订单快照）
    保持旧的「第一条译文」口径。
    """

    from cart.services import merchant_entry, resolve_item_title

    entry = {
        "public_id": "",
        "offer_public_id": str(offer.public_id),
        "spu_public_id": str(offer.sku.spu.public_id),
        "title": resolve_item_title(offer.sku.spu, market, locale),
        "quantity": quantity,
        "price": str(offer.current_price),
        "currency": offer.currency.code,
        "inventory_display": offer.display_inventory,
        "merchant": merchant_entry(offer),
        "is_valid": (
            offer.status == Offer.Status.ACTIVE
            and offer.local_inventory > 0
            and offer.source_availability != Offer.SourceAvailability.UNAVAILABLE
        ),
        "issue": None,
    }
    changed = False
    if not entry["is_valid"]:
        entry["issue"] = "SKU_NOT_AVAILABLE"
        changed = True
    elif entry["quantity"] > offer.local_inventory:
        entry["issue"] = "INSUFFICIENT_STOCK"
        entry["quantity"] = offer.local_inventory
        changed = True

    if entry["is_valid"]:
        subtotal = offer.current_price * entry["quantity"]
        shipping_cost, _method = compute_shipping(subtotal, entry["currency"])
        total = subtotal + Decimal(shipping_cost)
    else:
        subtotal = None
        total = None
    return {
        "public_id": "",
        "items": [entry],
        "subtotal": str(subtotal) if subtotal is not None else None,
        "currency": entry["currency"] if entry["is_valid"] else "",
        "needs_attention": changed,
        "total": str(total) if total is not None else None,
    }


def _error(request, code, message, status=400):
    return JsonResponse(
        {
            "error": {"code": code, "message": message, "details": None},
            "request_id": getattr(request, "request_id", None),
        },
        status=status,
    )


def _serialize_address(address):
    return {
        "public_id": str(address.public_id),
        **address.as_snapshot(),
        "is_default": address.is_default,
        "is_serviceable": address.is_serviceable,
    }


def _clean_address_body(body):
    """Validate the editable address fields.

    Returns ``(values, None)`` on success or ``(None, (code, message))`` on
    failure. The storefront always submits the full form, so PATCH uses the
    same required-field rules as POST.
    """

    # 2026-11-28 澄清：Address Line 1* 必填保留（删的是真站的 Address 查找框）。
    # line1 恢复必填；城市由前端兜底 London。
    required = ("full_name", "phone", "line1", "city", "postcode")
    missing = [field for field in required if not str(body.get(field) or "").strip()]
    if missing:
        return None, ("ADDRESS_INCOMPLETE", f"Missing: {', '.join(missing)}.")
    # 2026-11-28 用户拍板：邮编格式校验放开（任意内容，仅非空）；
    # 大写规范化保留，长度按模型上限截断。
    postcode = str(body.get("postcode") or "").strip().upper()[:10]
    return (
        {
            "full_name": str(body["full_name"]).strip()[:160],
            "phone": str(body["phone"]).strip()[:32],
            "line1": str(body["line1"]).strip()[:200],
            "line2": str(body.get("line2") or "").strip()[:200],
            "city": str(body["city"]).strip()[:100],
            "county": str(body.get("county") or "").strip()[:100],
            "postcode": postcode,
            "country_code": "GB",
        },
        None,
    )


def _promote_default(account, *, exclude_pk=None):
    """Guarantee one default address when the account still has any."""

    queryset = account.addresses.all()
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    if not queryset.filter(is_default=True).exists():
        candidate = queryset.order_by("created_at", "pk").first()
        if candidate is not None:
            candidate.is_default = True
            candidate.save(update_fields=["is_default", "updated_at"])


def address_list(request):
    if request.method == "GET":
        account = getattr(request, "buyer_account", None)
        if account is None:
            return _error(request, "AUTH_REQUIRED", "Sign in required.", 401)
        addresses = [
            _serialize_address(address)
            for address in account.addresses.order_by("-is_default", "-updated_at")
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
        values, validation_error = _clean_address_body(body)
        if validation_error is not None:
            code, message = validation_error
            return _error(request, code, message)
        with transaction.atomic():
            make_default = bool(body.get("is_default")) or not account.addresses.exists()
            if make_default:
                account.addresses.update(is_default=False)
            address = Address.objects.create(
                account=account,
                is_default=make_default,
                **values,
            )
        return JsonResponse(_serialize_address(address), status=201)

    if request.method == "PATCH":
        account = getattr(request, "buyer_account", None)
        if account is None:
            return _error(request, "AUTH_REQUIRED", "Sign in required.", 401)
        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return _error(request, "BAD_REQUEST", "Invalid JSON.")
        public_id = str(body.get("public_id") or "").strip()
        address = account.addresses.filter(public_id=public_id).first() if public_id else None
        if address is None:
            return _error(request, "ADDRESS_NOT_FOUND", "Address not found.", 404)
        # A default-only PATCH (the "set as default" button) skips field checks.
        default_only = set(body.keys()) <= {"public_id", "is_default"}
        if default_only:
            with transaction.atomic():
                if body.get("is_default"):
                    account.addresses.exclude(pk=address.pk).update(is_default=False)
                    address.is_default = True
                    address.save(update_fields=["is_default", "updated_at"])
                elif address.is_default and account.addresses.exclude(pk=address.pk).exists():
                    address.is_default = False
                    address.save(update_fields=["is_default", "updated_at"])
                    _promote_default(account)
            return JsonResponse(_serialize_address(address))

        values, validation_error = _clean_address_body(body)
        if validation_error is not None:
            code, message = validation_error
            return _error(request, code, message)
        with transaction.atomic():
            for field, value in values.items():
                setattr(address, field, value)
            make_default = bool(body.get("is_default"))
            if make_default:
                account.addresses.exclude(pk=address.pk).update(is_default=False)
                address.is_default = True
            elif address.is_default and "is_default" in body:
                # Turning the switch off on the current default hands the badge
                # to the oldest other address; a sole address stays default.
                others = account.addresses.exclude(pk=address.pk)
                if others.exists():
                    address.is_default = False
                    successor = others.order_by("created_at", "pk").first()
                    successor.is_default = True
                    successor.save(update_fields=["is_default", "updated_at"])
            address.save()
            _promote_default(account)
        return JsonResponse(_serialize_address(address))

    if request.method == "DELETE":
        account = getattr(request, "buyer_account", None)
        if account is None:
            return _error(request, "AUTH_REQUIRED", "Sign in required.", 401)
        public_id = str(request.GET.get("public_id") or "").strip()
        if not public_id:
            try:
                body = json.loads(request.body or b"{}")
            except json.JSONDecodeError:
                body = {}
            public_id = str(body.get("public_id") or "").strip()
        address = account.addresses.filter(public_id=public_id).first() if public_id else None
        if address is None:
            return _error(request, "ADDRESS_NOT_FOUND", "Address not found.", 404)
        was_default = address.is_default
        with transaction.atomic():
            address.delete()
            if was_default:
                _promote_default(account)
        return JsonResponse({"removed": True})

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

    # 立即购买（2026-11-28）：请求带 offer_public_id 时走「独立直购上下文」——
    # 不读写购物车，快照只有一个 offer（与购物车行同口径的 issue/needs_attention
    # 判定）；不带时保持原购物车快照路径，行为不变。
    # 请求市场/语言只用于行标题本地化（与 PDP/购物车同源口径）。
    market_context = resolve_market_context(request)
    market = market_context.market if market_context else None
    locale = market_context.locale if market_context else None
    offer_public_id = str(body.get("offer_public_id") or "").strip()
    if offer_public_id:
        quantity = _parse_direct_quantity(body.get("quantity"))
        if quantity is None:
            return _error(request, "BAD_REQUEST", "Quantity must be a positive integer.")
        direct_offer = (
            Offer.objects.select_related("currency", "sku__spu", "merchant")
            .filter(public_id=offer_public_id)
            .first()
        )
        if direct_offer is None:
            return _error(request, "SKU_NOT_AVAILABLE", "This item is no longer available.", 404)
        snapshot = serialize_direct_purchase(direct_offer, quantity, market=market, locale=locale)
    else:
        context = resolve_cart_context(request)
        cart = get_or_create_cart(context)
        snapshot = serialize_cart(cart, market=market, locale=locale)
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
