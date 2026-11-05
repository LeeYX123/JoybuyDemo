"""商家端 M04 订单管理与订单详情。

数据来自 ``orders.MerchantOrder``（按商家拆分的履约子单）：状态只有
待处理/已发货/已完成三种，物流 8 节点是履约进度而不是第 4 种状态。
发货与本店钱包扣成本走同一事务，回款由节点 7 触发且只入账一次。
"""

from django.db.models import Q
from django.utils import timezone
from rest_framework.response import Response

from accounts_staff.api_exceptions import StaffApiError
from audit.services import record_audit
from merchant_ops.api_utils import csv_response, iso, money_str, paginate
from merchant_ops.merchant_context import MerchantAPIView
from merchant_ops.services import MerchantOpsError, ship_merchant_order
from orders.models import MerchantOrder

STATUS_TABS = (
    MerchantOrder.Status.PENDING,
    MerchantOrder.Status.SHIPPED,
    MerchantOrder.Status.COMPLETED,
)


def _order_payload(order: MerchantOrder, *, detail: bool = False) -> dict:
    payload = {
        "id": str(order.public_id),
        "order_id": str(order.order.public_id),
        "currency": order.currency,
        "status": order.status,
        "progress": order.progress,
        "node_times": list(order.node_times or []),
        "node_labels": list(MerchantOrder.NODE_LABELS),
        "items_total": money_str(order.items_total),
        "cost_total": money_str(order.cost_total),
        "profit": money_str(order.items_total - order.cost_total),
        "payment_method": order.payment_method,
        "recipient_region": order.recipient_region,
        "tracking_reference": order.tracking_reference,
        "settled": order.settled,
        "settled_at": iso(order.settled_at),
        "shipped_at": iso(order.shipped_at),
        "created_at": iso(order.created_at),
        "can_ship": order.status == MerchantOrder.Status.PENDING,
    }
    if detail:
        items = list(order.items.select_related("offer")[:20])
        payload["items"] = [
            {
                "title": item.title,
                "quantity": item.quantity,
                "unit_price": money_str(item.unit_price),
                "unit_cost": money_str(item.unit_cost) if item.unit_cost is not None else None,
                "amount": money_str(item.unit_price * item.quantity),
                "cost_amount": money_str((item.unit_cost or 0) * item.quantity),
            }
            for item in items
        ]
        payload["title"] = items[0].title if items else ""
    else:
        first = order.items.first()
        payload["title"] = first.title if first else ""
        payload["quantity"] = first.quantity if first else 0
    return payload


def _filtered_queryset(request):
    queryset = MerchantOrder.objects.select_related("order", "merchant").filter(
        merchant=request.merchant
    )
    status = (request.query_params.get("status") or "").strip().upper()
    if status and status != "ALL" and status in STATUS_TABS:
        queryset = queryset.filter(status=status)
    query = (request.query_params.get("q") or "").strip()
    if query:
        condition = Q(items__title__icontains=query) | Q(tracking_reference__icontains=query)
        try:
            import uuid as uuid_module

            condition |= Q(public_id=uuid_module.UUID(query))
            condition |= Q(order__public_id=uuid_module.UUID(query))
        except ValueError:
            pass
        queryset = queryset.filter(condition).distinct()
    start = (request.query_params.get("start") or "").strip()
    end = (request.query_params.get("end") or "").strip()
    if start:
        queryset = queryset.filter(created_at__date__gte=start[:10])
    if end:
        queryset = queryset.filter(created_at__date__lte=end[:10])
    return queryset.order_by("-created_at", "-pk")


def _resolve_order(request, public_id) -> MerchantOrder:
    order = (
        MerchantOrder.objects.select_related("order", "merchant")
        .filter(merchant=request.merchant, public_id=public_id)
        .first()
    )
    if order is None:
        raise StaffApiError(
            business_code="ORDER_NOT_FOUND", message="订单不存在或不属于当前店铺。", status_code=404
        )
    return order


class MerchantOrdersView(MerchantAPIView):
    permission_any = ("merchant.orders.manage",)

    def get(self, request):
        rows, meta = paginate(_filtered_queryset(request), request)
        counts = {
            key: MerchantOrder.objects.filter(merchant=request.merchant, status=key).count()
            for key in STATUS_TABS
        }
        counts["ALL"] = MerchantOrder.objects.filter(merchant=request.merchant).count()
        return Response(
            {"items": [_order_payload(order) for order in rows], "counts": counts, **meta}
        )


class MerchantOrderDetailView(MerchantAPIView):
    permission_any = ("merchant.orders.manage",)

    def get(self, request, public_id):
        order = _resolve_order(request, public_id)
        return Response({"order": _order_payload(order, detail=True)})


class MerchantOrderShipView(MerchantAPIView):
    permission_any = ("merchant.orders.manage",)

    def post(self, request, public_id):
        order = _resolve_order(request, public_id)
        reference = str((request.data or {}).get("reference") or "").strip()
        try:
            order = ship_merchant_order(order, actor=request.staff_account, reference=reference)
        except MerchantOpsError as exc:
            # 余额不足、重复发货等业务错误按域层码返回，前端可直接提示。
            raise StaffApiError(
                business_code=exc.code, message=exc.message, status_code=exc.status_code
            ) from exc
        record_audit(
            request=request,
            actor=request.staff_account,
            action="MERCHANT_ORDER_SHIPPED",
            target_type="merchant_order",
            target_id=str(order.public_id),
            reason="",
            before_state={},
            after_state={
                "status": order.status,
                "cost_total": str(order.cost_total),
                "tracking_reference": order.tracking_reference,
            },
            tenant_type="MERCHANT",
            tenant_id=str(request.merchant.public_id),
        )
        return Response({"order": _order_payload(order, detail=True)})


class MerchantOrdersExportView(MerchantAPIView):
    permission_any = ("merchant.orders.manage",)

    def get(self, request):
        orders = list(_filtered_queryset(request)[:5000])
        rows = [
            [
                str(order.public_id),
                str(order.order.public_id),
                order.status,
                money_str(order.items_total),
                money_str(order.cost_total),
                money_str(order.items_total - order.cost_total),
                order.payment_method,
                timezone.localtime(order.created_at).strftime("%Y-%m-%d %H:%M"),
            ]
            for order in orders
        ]
        return csv_response(
            "merchant-orders.csv",
            ["订单号", "父订单号", "状态", "订单金额", "发货成本", "收益", "支付方式", "下单时间"],
            rows,
        )
