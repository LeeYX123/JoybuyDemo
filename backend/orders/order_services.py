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


def place_order(
    *,
    account,
    cart_snapshot: dict | None = None,
    address_snapshot: dict,
    payment_method: str = "",
    offer_public_id: str = "",
    quantity: int = 1,
) -> Order:
    """Create a PAID order from a validated cart snapshot and split it into
    per-merchant fulfilment sub-orders.

    WP-42（文档 M01 §1 / 购物端）：白名单账户结账页选择任一支付方式后点
    【下单】即判定支付成功（演示性质，不对接真实支付网关），因此下单直接
    置 PAID 并记录支付方式；同时按 offer.merchant 拆出 MerchantOrder
    （成本快照取 offer.cost_price）。

    立即购买（2026-11-28）：带 ``offer_public_id`` 时走独立直购上下文——
    不读购物车、不写 cart 行，把单个 offer 构造成与购物车同形的快照后走
    同一条校验/下单管线（白名单、支付权限、余额、库存闸门全部生效）；
    事务内仍对该 offer 做 select_for_update 库存复核。不带时行为与从前
    完全一致（购物车快照路径）。

    Raises OrderError (CART_INVALID / INSUFFICIENT_STOCK / NOT_WHITELISTED /
    PAYMENT_DISABLED / PAYMENT_METHOD_INVALID) without touching any state when
    validation fails.
    """

    from cart.models import MAX_QTY_PER_ITEM, Cart
    from checkout.models import Address

    # 白名单后端打通（文档拍板 7）：后端标识驱动，未拿到标识按不可购买处理。
    if account is None or not account.purchase_whitelisted:
        raise OrderError("NOT_WHITELISTED", "当前账号不在购买白名单内，无法下单。")

    # 管理端【编辑】的支付权限（2026-11-27）：关闭后只拦下单/付款，
    # 不动登录态、购物车与历史订单；与白名单是两条独立闸门。
    if not account.payment_enabled:
        raise OrderError("PAYMENT_DISABLED", "该账号已关闭支付权限，请联系平台客服。")

    if payment_method:
        from orders.models import Order as OrderModel

        if payment_method not in OrderModel.PAYMENT_METHODS:
            raise OrderError("PAYMENT_METHOD_INVALID", "不支持的支付方式。")

    direct_mode = bool(offer_public_id)
    if direct_mode:
        # 立即购买：数量必须为正整数且不超单件上限；offer 缺失按不可购买处理。
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
            raise OrderError("CART_INVALID", "Quantity must be a positive integer.")
        if quantity > MAX_QTY_PER_ITEM:
            raise OrderError("QUANTITY_LIMIT", "Quantity cannot exceed 99 per item.")
        direct_offer = (
            Offer.objects.select_related("currency", "sku__spu", "merchant")
            .filter(public_id=offer_public_id)
            .first()
        )
        if direct_offer is None:
            raise OrderError("SKU_NOT_AVAILABLE", "This item is no longer available.")
        from checkout.checkout_views import serialize_direct_purchase

        cart_snapshot = serialize_direct_purchase(direct_offer, quantity)
    elif cart_snapshot is None:
        raise OrderError("CART_INVALID", "Your cart needs attention before checkout.")

    # 2026-11-28 用户拍板：余额支付不校验余额、不扣款，只记录支付方式
    # （白名单演示口径：订单用于后台统计，另行结算）。
    balance_payment = False

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

        from orders.models import MerchantOrder, Order, OrderItem

        # 演示支付：选任一支付方式点【下单】即支付成功（文档 M01 §1 拍板）。
        paid_now = bool(payment_method)
        order = Order.objects.create(
            account=account,
            currency=currency,
            items_subtotal=subtotal,
            shipping_cost=Decimal(shipping_cost),
            total=subtotal + Decimal(shipping_cost),
            shipping_address=address.as_snapshot(),
            payment_expires_at=timezone.now() + timedelta(minutes=PAYMENT_WINDOW_MINUTES),
            status=Order.Status.PAID if paid_now else Order.Status.PENDING_PAYMENT,
            payment_method=payment_method,
            paid_at=timezone.now() if paid_now else None,
        )
        # 阶段 2：支付成功的订单顺手记一条 Payment（幂等；不改变任何支付判定）。
        if paid_now:
            from orders.payment_services import record_payment_for_order

            record_payment_for_order(order)

        # 2026-11-28：余额支付不再扣款/写流水，仅记录 payment_method。
        from orders.models import InventoryReservation

        # 按商家聚合：商家子单承接发货、进度与回款（WP-42 下单拆单）。
        merchant_orders = {}
        for entry, offer in item_specs:
            translation = offer.sku.spu.translations.order_by("pk").first()
            unit_cost = offer.cost_price or Decimal("0")
            merchant_order = merchant_orders.get(offer.merchant_id)
            if merchant_order is None:
                merchant_order = MerchantOrder.objects.create(
                    order=order,
                    merchant_id=offer.merchant_id,
                    currency=offer.currency.code,
                    items_total=Decimal("0"),
                    cost_total=Decimal("0"),
                    payment_method=payment_method,
                    recipient_region=address.country_code,
                )
                merchant_orders[offer.merchant_id] = merchant_order
            quantity = entry["quantity"]
            merchant_order.items_total += offer.current_price * quantity
            merchant_order.cost_total += unit_cost * quantity
            OrderItem.objects.create(
                order=order,
                merchant_order=merchant_order,
                offer=offer,
                spu_public_id=str(offer.sku.spu.public_id),
                title=translation.title if translation else "",
                quantity=quantity,
                unit_price=offer.current_price,
                unit_cost=unit_cost,
                currency=offer.currency.code,
            )
            InventoryReservation.objects.create(
                order=order, offer=offer, quantity=quantity
            )
            adjust_offer_inventory(
                offer=offer,
                quantity_delta=-quantity,
                reason="RESERVATION",
                idempotency_key=f"order-reserve:{order.public_id}:{offer.public_id}",
                reference_type="order",
                reference_id=str(order.public_id),
            )
        for merchant_order in merchant_orders.values():
            merchant_order.save(update_fields=["items_total", "cost_total", "updated_at"])
            if paid_now:
                from merchants.services import _bump_daily_stat

                _bump_daily_stat(
                    merchant_order.merchant,
                    order_count=1,
                    stat_date=timezone.localdate(),
                )
        # The buyer's OPEN cart becomes CHECKED_OUT; a fresh one opens lazily.
        # 立即购买（直购）不涉及购物车：不标记 CHECKED_OUT，购物车原样保留。
        if not direct_mode:
            from django.db.models import Q

            Cart.objects.filter(
                Q(account=account) | Q(anonymous_token=""),
                status=Cart.Status.OPEN,
            ).filter(
                items__offer__public_id__in=[spec[1].public_id for spec in item_specs]
            ).update(status=Cart.Status.CHECKED_OUT)
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
