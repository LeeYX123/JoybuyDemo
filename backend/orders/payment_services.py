"""支付 / 物流记录的写入助手（全站编号改造阶段 2）。

设计原则：**只记录，不改变任何既有业务判定**。

* 支付：下单即付（``place_order`` 里 ``paid_now`` 分支）原本就会把订单置
  ``PAID`` 并写 ``paid_at``，这里在同一个事务里顺手写一条 ``SUCCEEDED`` 的
  ``Payment``。``attempt_payment`` 仍然按原样抛
  ``PAYMENT_REGION_UNSUPPORTED``，绝不因为有了 Payment 模型就“变成支付成功”。
* 物流：商家发货（``ship_merchant_order``）成功时写一条 ``Shipment``，
  ``tracking_no`` 就是商家在发货接口里填的 ``reference``（当前没有承运商输入，
  ``carrier`` 留空）。
* 退款：当前业务流没有真实打款动作，本模块不自动造退款；只用
  ``record_refund`` 给管理端手动补录使用。
"""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from orders.models import Payment, Refund, Shipment

CENT = Decimal("0.01")


def money_2dp(value) -> Decimal:
    """金额统一到分（Payment/Refund 字段是 Decimal(12,2)）。"""

    return Decimal(str(value or "0")).quantize(CENT, rounding=ROUND_HALF_UP)


def record_payment_for_order(
    order, *, paid_at: datetime | None = None, method: str | None = None
) -> Payment | None:
    """为已支付订单写一条 ``SUCCEEDED`` 支付记录（幂等，同一订单只记一条）。

    只有订单本身就是 ``PAID``（或显式给了 ``paid_at``）才写；未支付订单返回
    ``None``，调用方不需要额外判断。
    """

    paid_at = paid_at or order.paid_at
    if paid_at is None:
        return None

    existing = order.payments.filter(status=Payment.Status.SUCCEEDED).first()
    if existing is not None:
        return existing

    currency = order.currency
    return Payment.objects.create(
        order=order,
        amount=money_2dp(order.total),
        currency=currency.code if hasattr(currency, "code") else str(currency),
        method=(order.payment_method if method is None else method) or "",
        status=Payment.Status.SUCCEEDED,
        paid_at=paid_at,
    )


def record_shipment_for_merchant_order(
    merchant_order,
    *,
    reference: str = "",
    at: datetime | None = None,
    carrier: str = "",
    order=None,
) -> Shipment | None:
    """商家发货时写一条物流记录（幂等：同一子单只建一条）。

    状态取 ``IN_TRANSIT``（发货即交给承运商）；后续节点推进/完成时由
    :func:`sync_shipments_delivered` 改为 ``DELIVERED``。
    """

    if merchant_order.shipments.exists():
        return None

    shipped_at = at or merchant_order.shipped_at or timezone.now()
    tracking_no = (reference or merchant_order.tracking_reference or "").strip()
    return Shipment.objects.create(
        order=order or merchant_order.order,
        merchant_order=merchant_order,
        carrier=carrier or "",
        tracking_no=tracking_no,
        status=Shipment.Status.IN_TRANSIT,
        shipped_at=shipped_at,
    )


def sync_shipments_delivered(merchant_order, *, at: datetime | None = None) -> int:
    """子单到达「已签收」及之后时，把未送达的物流记录置为 ``DELIVERED``。"""

    delivered_at = at or timezone.now()
    return merchant_order.shipments.exclude(status=Shipment.Status.DELIVERED).update(
        status=Shipment.Status.DELIVERED,
        delivered_at=delivered_at,
    )


def record_refund(
    *,
    order,
    amount,
    currency: str = "",
    status: str = Refund.Status.PENDING,
    payment=None,
    after_sale=None,
    reason: str = "",
    processed_at=None,
) -> Refund:
    """手动补录一条退款（管理端接口调用；当前业务流不会自动触发）。"""

    return Refund.objects.create(
        order=order,
        payment=payment,
        after_sale=after_sale,
        amount=money_2dp(amount),
        currency=currency or order.currency.code,
        status=status,
        reason=reason or "",
        processed_at=processed_at,
    )
