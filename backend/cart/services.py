from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone
from offers.models import Offer

from cart.models import MAX_QTY_PER_ITEM, Cart, CartItem, generate_anonymous_token

ANONYMOUS_COOKIE_NAME = "joybuy_cart_token"
CART_MAX_AGE_SECONDS = 60 * 60 * 24 * 30  # 30 days


class CartError(Exception):
    """Domain error with a stable business code for the API layer."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class CartItemInvalid(CartError):
    def __init__(self, code="CART_ITEM_INVALID", message="The cart item is not available."):
        super().__init__(code, message)


@dataclass
class CartRequestContext:
    """Resolved cart identity for one request."""

    account = None  # BuyerAccount or None
    anonymous_token: str = ""
    new_anonymous_token: str = ""


def resolve_cart_context(request) -> CartRequestContext:
    context = CartRequestContext()
    context.account = getattr(request, "buyer_account", None)
    context.anonymous_token = request.COOKIES.get(ANONYMOUS_COOKIE_NAME, "")
    if not context.account and not context.anonymous_token:
        context.new_anonymous_token = generate_anonymous_token()
    return context


def _apply_anonymous_cookie(response, context) -> None:
    if context.new_anonymous_token:
        response.set_cookie(
            ANONYMOUS_COOKIE_NAME,
            context.new_anonymous_token,
            max_age=CART_MAX_AGE_SECONDS,
            httponly=True,
            samesite="Lax",
            secure=False,
        )


def get_or_create_cart(context) -> Cart:
    if context.account:
        cart, _ = Cart.objects.get_or_create(account=context.account, status=Cart.Status.OPEN)
        return cart
    token = context.anonymous_token or context.new_anonymous_token
    if not token:
        token = context.new_anonymous_token = generate_anonymous_token()
    cart, _ = Cart.objects.get_or_create(anonymous_token=token, status=Cart.Status.OPEN)
    return cart


def _validate_offer(offer) -> None:
    if (
        offer is None
        or offer.status != Offer.Status.ACTIVE
        or offer.local_inventory < 1
        or offer.source_availability == Offer.SourceAvailability.UNAVAILABLE
    ):
        raise CartItemInvalid("SKU_NOT_AVAILABLE", "This SKU is not available to buy.")


def add_item(context, *, offer_public_id: str, quantity: int) -> Cart:
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        raise CartItemInvalid(message="Quantity must be a positive integer.")
    if quantity > MAX_QTY_PER_ITEM:
        raise CartItemInvalid("QUANTITY_LIMIT", "Quantity cannot exceed 99 per item.")

    with transaction.atomic():
        offer = (
            Offer.objects.select_for_update()
            .select_related("currency")
            .filter(public_id=offer_public_id)
            .first()
        )
        _validate_offer(offer)
        if quantity > offer.local_inventory:
            raise CartItemInvalid("INSUFFICIENT_STOCK", "Not enough stock for this quantity.")

        cart = get_or_create_cart(context)
        item, created = CartItem.objects.get_or_create(
            cart=cart,
            offer=offer,
            defaults={"quantity": quantity},
        )
        if not created:
            new_quantity = item.quantity + quantity
            if new_quantity > 99:
                raise CartItemInvalid("QUANTITY_LIMIT", "Quantity cannot exceed 99 per item.")
            if new_quantity > offer.local_inventory:
                raise CartItemInvalid("INSUFFICIENT_STOCK", "Not enough stock for this quantity.")
            item.quantity = new_quantity
            item.updated_at = timezone.now()
            item.save(update_fields=["quantity", "updated_at"])
    return cart


def update_item(context, *, item_public_id: str, quantity: int) -> Cart:
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        raise CartItemInvalid(message="Quantity must be a positive integer.")
    if quantity > 99:
        raise CartItemInvalid("QUANTITY_LIMIT", "Quantity cannot exceed 99 per item.")
    with transaction.atomic():
        cart = get_or_create_cart(context)
        item = (
            CartItem.objects.select_for_update()
            .select_related("offer")
            .filter(cart=cart, public_id=item_public_id)
            .first()
        )
        if item is None:
            raise CartItemInvalid(message="This cart item no longer exists.")
        if quantity > item.offer.local_inventory:
            raise CartItemInvalid("INSUFFICIENT_STOCK", "Not enough stock for this quantity.")
        item.quantity = quantity
        item.updated_at = timezone.now()
        item.save(update_fields=["quantity", "updated_at"])
    return cart


def remove_item(context, *, item_public_id: str) -> Cart:
    cart = get_or_create_cart(context)
    deleted, _ = CartItem.objects.filter(cart=cart, public_id=item_public_id).delete()
    if not deleted:
        raise CartItemInvalid(message="This cart item no longer exists.")
    return cart


def serialize_cart(cart: Cart) -> dict:
    """Live re-validation: prices come from the current offer, invalid rows
    are flagged instead of silently dropped so the buyer can act on them."""

    items = []
    subtotal = None
    changed = False
    currency_code = ""
    for item in cart.items.select_related("offer", "offer__currency", "offer__sku__spu"):
        offer = item.offer
        translation = offer.sku.spu.translations.order_by("pk").first()
        entry = {
            "public_id": str(item.public_id),
            "offer_public_id": str(offer.public_id),
            "spu_public_id": str(offer.sku.spu.public_id),
            "title": translation.title if translation else "",
            "quantity": item.quantity,
            "price": str(offer.current_price),
            "currency": offer.currency.code,
            "inventory_display": offer.display_inventory,
            "is_valid": offer.status == Offer.Status.ACTIVE
            and offer.local_inventory > 0
            and offer.source_availability != Offer.SourceAvailability.UNAVAILABLE,
            "issue": None,
        }
        if not entry["is_valid"]:
            entry["issue"] = "SKU_NOT_AVAILABLE"
            changed = True
        elif item.quantity > offer.local_inventory:
            entry["issue"] = "INSUFFICIENT_STOCK"
            entry["quantity"] = offer.local_inventory
            changed = True
        if entry["is_valid"]:
            line_total = offer.current_price * entry["quantity"]
            subtotal = line_total if subtotal is None else subtotal + line_total
            currency_code = offer.currency.code
        items.append(entry)
    return {
        "public_id": str(cart.public_id),
        "items": items,
        "subtotal": str(subtotal) if subtotal is not None else None,
        "currency": currency_code,
        "needs_attention": changed,
    }


def merge_anonymous_cart(context) -> dict:
    """Fold the anonymous cart into the buyer's open cart on sign-in."""

    if not context.account:
        raise CartError("AUTH_REQUIRED", "Sign in required to merge carts.")
    token = context.anonymous_token
    if not token:
        return {"merged_items": 0}

    with transaction.atomic():
        anonymous = Cart.objects.filter(anonymous_token=token, status=Cart.Status.OPEN).first()
        if anonymous is None:
            return {"merged_items": 0}
        buyer_cart, _ = Cart.objects.get_or_create(account=context.account, status=Cart.Status.OPEN)
        merged = 0
        for item in anonymous.items.select_for_update().select_related("offer"):
            if item.offer.status != Offer.Status.ACTIVE or item.offer.local_inventory < 1:
                continue
            target, created = CartItem.objects.get_or_create(
                cart=buyer_cart,
                offer=item.offer,
                defaults={"quantity": item.quantity},
            )
            if created:
                merged += 1
            else:
                target.quantity = min(99, target.quantity + item.quantity)
                target.save(update_fields=["quantity", "updated_at"])
                merged += 1
        anonymous.status = Cart.Status.MERGED
        anonymous.save(update_fields=["status", "updated_at"])
        return {"merged_items": merged}
