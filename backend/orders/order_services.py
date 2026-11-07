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
    cart_snapshot: dict,
    address_snapshot: dict,
    payment_method: str = "",
) -> Order:
    """Create a PAID order from a validated cart snapshot and split it into
    per-merchant fulfilment sub-orders.

    WP-42（文档 M01 §1 / 购物端）：白名单账户结账页选择任一支付方式后点
    【下单】即判定支付成功（演示性质，不对接真实支付网关），因此下单直接
    置 PAID 并记录支付方式；同时按 offer.merchant 拆出 MerchantOrder
    （成本快照取 offer.cost_price）。

    Raises OrderError (CART_INVALID / INSUFFICIENT_STOCK / NOT_WHITELISTED /
    PAYMENT_METHOD_INVALID) without touching any state when validation fails.
    """

    from cart.models import Cart
    from checkout.models import Address

    # 白名单后端打通（文档拍板 7）：后端标识驱动，未拿到标识按不可购买处理。
    if account is None or not account.purchase_whitelisted:
        raise OrderError("NOT_WHITELISTED", "当前账号不在购买白名单内，无法下单。")

    if payment_method:
        from orders.models import Order as OrderModel

        if payment_method not in OrderModel.PAYMENT_METHODS:
            raise OrderError("PAYMENT_METHOD_INVALID", "不支持的支付方式。")

    # 迭代02 拍板：余额支付真扣 BuyerAccount.balance。先读快照做前置校验，
    # 实际扣款在下单事务内（同事务回滚，不会出现扣了钱没下单）。
    balance_payment = payment_method == "BALANCE"
    if balance_payment:
        from decimal import Decimal

        if account.balance < Decimal(str(cart_snapshot.get("total") or "0")):
            raise OrderError("NOT_ENOUGH_BALANCE", "您当前可使用余额不足，请充值或更换支付方式。")

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
        # 迭代02：余额支付真扣买家余额（与下单同事务，失败即整体回滚）。
        if balance_payment:
            from accounts_buyers.models import BuyerAccount

            locked_buyer = (
                BuyerAccount.objects.select_for_update().filter(pk=account.pk).first()
            )
            total_due = Decimal(str(cart_snapshot.get("total") or "0"))
            if locked_buyer is None or locked_buyer.balance < total_due:
                raise OrderError("NOT_ENOUGH_BALANCE", "您当前可使用余额不足，请充值或更换支付方式。")
            balance_before = locked_buyer.balance
            locked_buyer.balance = balance_before - total_due
            locked_buyer.save(update_fields=["balance", "updated_at"])
            # 买家余额流水（PURCHASE 负向），幂等键防重复扣。
            from accounts_buyers.models import BuyerWalletEntry

            BuyerWalletEntry.objects.create(
                account=locked_buyer,
                kind=BuyerWalletEntry.Kind.PURCHASE,
                amount=-total_due,
                balance_before=balance_before,
                balance_after=locked_buyer.balance,
                currency=currency.code,
                order=order,
                note="商城消费（余额支付）",
                idempotency_key=f"order-pay:{order.public_id}",
                occurred_at=timezone.now(),
            )
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
