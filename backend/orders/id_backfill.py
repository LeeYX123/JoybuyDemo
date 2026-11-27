"""阶段 2 存量回填：支付 / 物流（退款因无金额跳过）。

被 ``orders/0008_backfill_payment_shipment`` 数据迁移调用；测试也可以直接
调用（传 ``django.apps.apps``），所以这里只依赖 ``apps.get_model`` 拿到的
历史模型，不 import 当前 ``orders.models``。

规则（2026-11-27 用户拍板）：

* Payment：``order.paid_at`` 非空 → 一条 ``SUCCEEDED``，金额=订单应付总额、
  方式=订单支付方式、``paid_at``=原值，编号日期段取该 ``paid_at``。
* Shipment：``merchant_order.tracking_reference`` 非空 → 一条物流记录；
  ``COMPLETED`` → ``DELIVERED``（送达时间取 node_times[6]/updated_at），
  其余（SHIPPED）→ ``IN_TRANSIT``。
* Refund：两条 RETURN 售后都没有金额字段，**不造 0 元假退款**，直接跳过；
  管理端可走 ``POST /api/v1/admin/refunds`` 手动补录。
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from common.ids import new_public_id

CENT = Decimal("0.01")


def money_2dp(value) -> Decimal:
    return Decimal(str(value or "0")).quantize(CENT, rounding=ROUND_HALF_UP)


def _parse_moment(raw):
    from django.utils.dateparse import parse_datetime

    if not raw:
        return None
    moment = parse_datetime(str(raw).replace(" ", "T"))
    if moment is None:
        return None
    if timezone.is_naive(moment):
        moment = timezone.make_aware(moment, timezone.get_current_timezone())
    return moment


def backfill_payments(apps) -> int:
    Order = apps.get_model("orders", "Order")
    Payment = apps.get_model("orders", "Payment")
    Currency = apps.get_model("offers", "Currency")

    currency_codes = dict(Currency.objects.values_list("pk", "code"))
    already = set(Payment.objects.values_list("order_id", flat=True))

    created = 0
    rows = (
        Order.objects.filter(paid_at__isnull=False)
        .order_by("pk")
        .values("pk", "total", "currency_id", "payment_method", "paid_at")
    )
    for row in rows:
        if row["pk"] in already:
            continue
        Payment.objects.create(
            order_id=row["pk"],
            public_id=new_public_id("payment", at=row["paid_at"]),
            amount=money_2dp(row["total"]),
            currency=currency_codes.get(row["currency_id"], ""),
            method=row["payment_method"] or "",
            status="SUCCEEDED",
            provider_reference="",
            paid_at=row["paid_at"],
        )
        created += 1
    return created


def backfill_shipments(apps) -> int:
    MerchantOrder = apps.get_model("orders", "MerchantOrder")
    Shipment = apps.get_model("orders", "Shipment")

    already = set(
        Shipment.objects.exclude(merchant_order_id=None).values_list("merchant_order_id", flat=True)
    )

    created = 0
    rows = (
        MerchantOrder.objects.exclude(tracking_reference="")
        .order_by("pk")
        .values(
            "pk",
            "order_id",
            "tracking_reference",
            "status",
            "shipped_at",
            "updated_at",
            "node_times",
        )
    )
    for row in rows:
        if row["pk"] in already:
            continue
        shipped_at = row["shipped_at"] or row["updated_at"]
        times = list(row["node_times"] or [])
        delivered_at = None
        if row["status"] == "COMPLETED":
            for index in (6, -1):
                if len(times) > index:
                    delivered_at = _parse_moment(times[index])
                    if delivered_at is not None:
                        break
            delivered_at = delivered_at or row["updated_at"]
        Shipment.objects.create(
            order_id=row["order_id"],
            merchant_order_id=row["pk"],
            public_id=new_public_id("shipment", at=shipped_at),
            carrier="",
            tracking_no=row["tracking_reference"] or "",
            status="DELIVERED" if row["status"] == "COMPLETED" else "IN_TRANSIT",
            shipped_at=shipped_at,
            delivered_at=delivered_at,
        )
        created += 1
    return created


def backfill_refunds(apps) -> int:  # noqa: ARG001 - 迁移签名统一
    """当前没有可确定的退款金额（AfterSale 无金额字段），跳过存量回填。"""

    return 0


def backfill_all(apps) -> dict[str, int]:
    result = {
        "payments": backfill_payments(apps),
        "shipments": backfill_shipments(apps),
        "refunds": backfill_refunds(apps),
    }
    verify_backfill(apps)
    return result


def verify_backfill(apps) -> dict[str, dict[str, int]]:
    """行数 / 去重 / 格式三重校验；不一致直接抛错让迁移失败。"""

    Order = apps.get_model("orders", "Order")
    MerchantOrder = apps.get_model("orders", "MerchantOrder")
    Payment = apps.get_model("orders", "Payment")
    Refund = apps.get_model("orders", "Refund")
    Shipment = apps.get_model("orders", "Shipment")

    expected = {
        "payment": (
            Payment,
            Order.objects.filter(paid_at__isnull=False).count(),
            re.compile(r"^JYPAY\d{8}[0-9A-Z]{6}$"),
        ),
        "shipment": (
            Shipment,
            MerchantOrder.objects.exclude(tracking_reference="").count(),
            re.compile(r"^JYLOG\d{8}[0-9A-Z]{6}$"),
        ),
        "refund": (Refund, None, re.compile(r"^JYR\d{8}[0-9A-Z]{6}$")),
    }
    report = {}
    for name, (model, expected_rows, pattern) in expected.items():
        queryset = model.objects.all()
        total = queryset.count()
        distinct = queryset.values("public_id").distinct().count()
        offenders = [
            value
            for value in queryset.values_list("public_id", flat=True)
            if not pattern.match(value)
        ]
        report[name] = {"rows": total, "distinct": distinct, "invalid": len(offenders)}
        if total != distinct or offenders:
            raise RuntimeError(f"{name} 回填校验失败: {report[name]}")
        if expected_rows is not None and total != expected_rows:
            raise RuntimeError(f"{name} 回填行数不一致: expected={expected_rows} actual={total}")
    return report
