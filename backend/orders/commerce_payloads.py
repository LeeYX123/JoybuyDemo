"""支付 / 退款 / 物流的最小只读序列化（阶段 2）。

三张表不单独做 CRUD 前端，只在既有订单/售后 payload 里内嵌数组；管理端另有
三个只读列表（退款多一个手动创建）。这里统一字段，避免四个视图各写一份。
``iso_fn`` 允许调用方沿用各自的时区展示口径（购物端 ``_local_iso``、管理端
``iso``），默认按服务器业务时区。
"""

from __future__ import annotations

from django.utils import timezone


def _default_iso(value) -> str | None:
    if not value:
        return None
    return timezone.localtime(value).isoformat()


def payment_payload(payment, *, iso_fn=_default_iso) -> dict:
    return {
        "public_id": payment.public_id,
        "status": payment.status,
        "amount": str(payment.amount),
        "currency": payment.currency,
        "method": payment.method,
        "provider_reference": payment.provider_reference,
        "paid_at": iso_fn(payment.paid_at),
        "created_at": iso_fn(payment.created_at),
    }


def refund_payload(refund, *, iso_fn=_default_iso) -> dict:
    return {
        "public_id": refund.public_id,
        "status": refund.status,
        "amount": str(refund.amount),
        "currency": refund.currency,
        "reason": refund.reason,
        "payment_public_id": refund.payment.public_id if refund.payment_id else None,
        "after_sale_public_id": (refund.after_sale.public_id if refund.after_sale_id else None),
        "processed_at": iso_fn(refund.processed_at),
        "created_at": iso_fn(refund.created_at),
    }


def shipment_payload(shipment, *, iso_fn=_default_iso) -> dict:
    return {
        "public_id": shipment.public_id,
        "status": shipment.status,
        "carrier": shipment.carrier,
        "tracking_no": shipment.tracking_no,
        "merchant_order_public_id": (
            shipment.merchant_order.public_id if shipment.merchant_order_id else None
        ),
        "shipped_at": iso_fn(shipment.shipped_at),
        "delivered_at": iso_fn(shipment.delivered_at),
        "created_at": iso_fn(shipment.created_at),
    }


def payment_payloads(queryset, *, iso_fn=_default_iso) -> list[dict]:
    return [payment_payload(row, iso_fn=iso_fn) for row in queryset]


def refund_payloads(queryset, *, iso_fn=_default_iso) -> list[dict]:
    return [refund_payload(row, iso_fn=iso_fn) for row in queryset]


def shipment_payloads(queryset, *, iso_fn=_default_iso) -> list[dict]:
    return [shipment_payload(row, iso_fn=iso_fn) for row in queryset]
