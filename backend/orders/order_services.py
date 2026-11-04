"""Order placement and timeout cancellation (WP-29).

Creation happens in one transaction: lock and re-read offers, validate,
create the order + item snapshots, decrement inventory with a RESERVATION
ledger entry, and set the 60-minute payment window. Cancellation is
idempotent: only the first pass releases stock.
"""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from offers.models import Offer
from offers.services import adjust_offer_inventory

from orders.models import Order

PAYMENT_WINDOW_MINUTES = int(getattr(settings, "ORDER_PAYMENT_WINDOW_MINUTES", "60"))


class OrderError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def place_order(*, account, cart_snapshot: dict, address_snapshot: dict) -> Order:
    """Create a PENDING_PAYMENT order from a validated cart snapshot.

    Raises OrderError (CART_INVALID / INSUFFICIENT_STOCK) without touching
    any state when validation fails.
    """

    from cart.models import Cart
    from checkout.models import Address

    if cart_snapshot.get("needs_attention") or not cart_snapshot.get("items"):
        raise OrderError("CART_INVALID", "Your cart needs attention before checkout.")

    address = Address.objects.filter(
        account=account, public_id=str(address_snapshot.get("public_id") or "")
    ).first()
    if address is None or not address.is_serviceable:
        raise OrderError("ADDRESS_UNSUPPORTED", "We do not deliver to this address.")

    item_specs = []
    with transaction.atomic():
        for entry in cart_snapshot["items"]:
            offer = (
                Offer.objects.select_for_update()
                .select_related("currency")
                .filter(public_id=entry["offer_public_id"])
                .first()
            )
            if (
                offer is None
                or offer.status != Offer.Status.ACTIVE
                or offer.local_inventory < entry["quantity"]
                or offer.source_availability == Offer.SourceAvailability.UNAVAILABLE
            ):
                raise OrderError("INSUFFICIENT_STOCK", "An item in your cart just sold out.")
            item_specs.append((entry, offer))

        from decimal import Decimal

        from offers.models import Currency

        currency = Currency.objects.get(code=cart_snapshot["currency"])
        subtotal = Decimal(cart_snapshot["subtotal"])
        from checkout.checkout_views import compute_shipping

        shipping_cost, _method = compute_shipping(subtotal, currency.code)

        from orders.models import Order, OrderItem

        order = Order.objects.create(
            account=account,
            currency=currency,
            items_subtotal=subtotal,
            shipping_cost=Decimal(shipping_cost),
            total=subtotal + Decimal(shipping_cost),
            shipping_address=address.as_snapshot(),
            payment_expires_at=timezone.now() + timedelta(minutes=PAYMENT_WINDOW_MINUTES),
        )
        from orders.models import InventoryReservation

        for entry, offer in item_specs:
            translation = offer.sku.spu.translations.order_by("pk").first()
            OrderItem.objects.create(
                order=order,
                offer=offer,
                spu_public_id=str(offer.sku.spu.public_id),
                title=translation.title if translation else "",
                quantity=entry["quantity"],
                unit_price=offer.current_price,
                currency=offer.currency.code,
            )
            InventoryReservation.objects.create(
                order=order, offer=offer, quantity=entry["quantity"]
            )
            adjust_offer_inventory(
                offer=offer,
                quantity_delta=-entry["quantity"],
                reason="RESERVATION",
                idempotency_key=f"order-reserve:{order.public_id}:{offer.public_id}",
                reference_type="order",
                reference_id=str(order.public_id),
            )
        # The buyer's OPEN cart becomes CHECKED_OUT; a fresh one opens lazily.
        from django.db.models import Q

        Cart.objects.filter(
            Q(account=account) | Q(anonymous_token=""),
            status=Cart.Status.OPEN,
        ).filter(items__offer__public_id__in=[spec[1].public_id for spec in item_specs]).update(
            status=Cart.Status.CHECKED_OUT
        )
        return order


def cancel_order(order, *, reason: str) -> bool:
    """Idempotent cancel: releases reservations exactly once."""

    from orders.models import Order

    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.status == Order.Status.CANCELED:
            return False
        order.status = Order.Status.CANCELED
        order.canceled_at = timezone.now()
        order.cancel_reason = reason[:100]
        order.save(update_fields=["status", "canceled_at", "cancel_reason", "updated_at"])

        for reservation in order.reservations.select_for_update():
            if reservation.released:
                continue
            adjust_offer_inventory(
                offer=reservation.offer,
                quantity_delta=reservation.quantity,
                reason="RELEASE",
                idempotency_key=f"order-release:{order.public_id}:{reservation.offer.public_id}",
                reference_type="order",
                reference_id=str(order.public_id),
            )
            reservation.released = True
            reservation.save(update_fields=["released"])
        return True


def cancel_expired_orders(*, now=None) -> dict:
    """Sweep for Celery beat; every expired PENDING_PAYMENT order cancels."""

    from orders.models import Order

    now = now or timezone.now()
    canceled = 0
    for order in Order.objects.filter(
        status=Order.Status.PENDING_PAYMENT, payment_expires_at__lt=now
    ).order_by("pk"):
        if cancel_order(order, reason="PAYMENT_WINDOW_EXPIRED"):
            canceled += 1
            try:
                from notifications.services import notify_order_canceled

                notify_order_canceled(order)
            except Exception:
                pass
    return {"canceled": canceled}


def attempt_payment(order) -> Order:
    """Phase-1 behaviour: payment is not available in this region."""

    from orders.models import Order

    if order.status != Order.Status.PENDING_PAYMENT:
        raise OrderError("ORDER_EXPIRED", "This order can no longer be paid.")
    raise OrderError("PAYMENT_REGION_UNSUPPORTED", "Payment is not available in your region.")
