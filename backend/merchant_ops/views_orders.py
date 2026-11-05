"""A05 订单管理：按商家履约子单维护物流节点与回款。"""

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.response import Response

from accounts_staff.api_exceptions import StaffApiError
from accounts_staff.permissions import StaffRbacPermission
from audit.services import record_audit
from merchant_ops.api_utils import OpsAPIView, csv_response, iso, money_str, paginate
from merchant_ops.services import advance_progress, complete_all_nodes
from orders.models import MerchantOrder

STATUS_TABS = {"PENDING", "SHIPPED", "COMPLETED"}


def _parse_datetime(raw, *, field="时间"):
    if raw in (None, ""):
        return None
    value = parse_datetime(str(raw).replace(" ", "T"))
    if value is None:
        raise StaffApiError(
            business_code="DATETIME_INVALID",
            message=f"{field}格式不正确。",
            status_code=400,
        )
    if timezone.is_naive(value):
        value = timezone.make_aware(value)
    return value


def _payload(order: MerchantOrder, *, detail=False) -> dict:
    items = list(order.items.select_related("offer")[:20]) if detail else []
    payload = {
        "id": str(order.public_id),
        "order_id": str(order.order.public_id),
        "merchant": {
            "id": str(order.merchant.public_id),
            "name": order.merchant.display_name,
        },
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
    }
    if detail:
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
        payload["buyer"] = {
            "id": str(order.order.account.public_id),
            "name": order.order.account.email or order.order.account.phone_e164 or "买家",
        }
    return payload


def _filtered_orders(request):
    queryset = MerchantOrder.objects.select_related("order__account", "merchant")
    status = (request.query_params.get("status") or "").strip().upper()
    if status and status != "ALL" and status in STATUS_TABS:
        queryset = queryset.filter(status=status)
    query = (request.query_params.get("q") or "").strip()
    if query:
        condition = (
            Q(merchant__display_name__icontains=query)
            | Q(items__title__icontains=query)
            | Q(tracking_reference__icontains=query)
        )
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


class AdminMerchantOrdersView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["orders.manage"]
    view_permissions = ["orders.view"]

    def get(self, request):
        rows, meta = paginate(_filtered_orders(request), request)
        return Response({"items": [_payload(order) for order in rows], **meta})


class AdminMerchantOrderDetailView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["orders.manage"]
    view_permissions = ["orders.view"]

    def _get(self, public_id):
        order = (
            MerchantOrder.objects.select_related("order__account", "merchant")
            .filter(public_id=public_id)
            .first()
        )
        if order is None:
            raise StaffApiError(
                business_code="ORDER_NOT_FOUND", message="订单不存在。", status_code=404
            )
        return order

    def get(self, request, public_id):
        return Response({"order": _payload(self._get(public_id), detail=True)})

    def patch(self, request, public_id):
        order = self._get(public_id)
        payload = request.data or {}
        before = {
            "created_at": iso(order.created_at),
            "node_times": list(order.node_times or []),
        }
        changed = []

        if "created_at" in payload:
            created_at = _parse_datetime(payload.get("created_at"), field="下单时间")
            if created_at is None:
                raise StaffApiError(
                    business_code="DATETIME_REQUIRED", message="下单时间不能为空。", status_code=400
                )
            nodes = [value for value in (order.node_times or []) if value]
            if nodes:
                first_node = min(parse_datetime(str(value).replace(" ", "T")) for value in nodes)
                if first_node and created_at > first_node:
                    raise StaffApiError(
                        business_code="CREATED_AFTER_NODE",
                        message="下单时间不能晚于已存在的第一个物流节点时间。",
                        status_code=400,
                    )
            MerchantOrder.objects.filter(pk=order.pk).update(created_at=created_at)
            changed.append("created_at")

        if "node_times" in payload:
            raw_nodes = payload.get("node_times") or []
            if not isinstance(raw_nodes, list) or len(raw_nodes) > 8:
                raise StaffApiError(
                    business_code="NODE_TIMES_INVALID",
                    message="节点时间必须是最多 8 项的数组。",
                    status_code=400,
                )
            nodes = []
            previous = None
            for index, raw in enumerate(raw_nodes):
                value = _parse_datetime(raw, field=f"第 {index + 1} 个节点时间")
                if value is None:
                    nodes.append(None)
                    continue
                if value < order.created_at:
                    raise StaffApiError(
                        business_code="NODE_BEFORE_CREATED",
                        message="节点时间不能早于下单时间。",
                        status_code=400,
                    )
                if previous and value < previous:
                    raise StaffApiError(
                        business_code="NODE_OUT_OF_ORDER",
                        message="节点时间必须按顺序递增。",
                        status_code=400,
                    )
                previous = value
                nodes.append(value.isoformat())
            while len(nodes) < 8:
                nodes.append(None)
            order.node_times = nodes
            order.save(update_fields=["node_times", "updated_at"])
            changed.append("node_times")

        record_audit(
            request=request,
            actor=request.staff_account,
            action="MERCHANT_ORDER_TIME_UPDATED",
            target_type="merchant_order",
            target_id=str(order.public_id),
            reason="",
            before_state=before,
            after_state={
                "created_at": iso(
                    MerchantOrder.objects.filter(pk=order.pk).values_list("created_at", flat=True)[
                        0
                    ]
                ),
                "node_times": list(order.node_times or []),
                "changed": changed,
            },
        )
        order.refresh_from_db()
        return Response({"order": _payload(order, detail=True)})


class AdminMerchantOrderActionsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["orders.manage"]
    view_permissions = ["orders.view"]

    def post(self, request, public_id):
        order = MerchantOrder.objects.filter(public_id=public_id).first()
        if order is None:
            raise StaffApiError(
                business_code="ORDER_NOT_FOUND", message="订单不存在。", status_code=404
            )
        payload = request.data or {}
        action = (payload.get("action") or "").strip().lower()
        before = {
            "status": order.status,
            "progress": order.progress,
            "settled": order.settled,
        }

        if action == "advance":
            try:
                node_index = int(payload.get("node_index"))
            except (TypeError, ValueError):
                raise StaffApiError(
                    business_code="NODE_INVALID", message="请选择要推进的节点。", status_code=400
                ) from None
            order = advance_progress(
                order,
                node_index=node_index,
                actor=request.staff_account,
                reference=(payload.get("reference") or "").strip(),
            )
            audit_action = "MERCHANT_ORDER_NODE_ADVANCED"
        elif action == "complete_all":
            order = complete_all_nodes(order, actor=request.staff_account)
            audit_action = "MERCHANT_ORDER_COMPLETED"
        else:
            raise StaffApiError(
                business_code="ACTION_UNSUPPORTED", message="不支持的操作。", status_code=400
            )

        record_audit(
            request=request,
            actor=request.staff_account,
            action=audit_action,
            target_type="merchant_order",
            target_id=str(order.public_id),
            reason="",
            before_state=before,
            after_state={
                "status": order.status,
                "progress": order.progress,
                "settled": order.settled,
            },
            tenant_type="merchant",
            tenant_id=str(order.merchant_id),
        )
        order.refresh_from_db()
        return Response({"order": _payload(order, detail=True)})


class AdminMerchantOrdersExportView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["orders.manage"]
    view_permissions = ["orders.view"]

    def get(self, request):
        orders = list(_filtered_orders(request)[:2000])
        rows = []
        for order in orders:
            payload = _payload(order)
            rows.append(
                [
                    payload["id"],
                    payload["order_id"],
                    payload["merchant"]["name"],
                    payload["status"],
                    payload["progress"],
                    payload["items_total"],
                    payload["cost_total"],
                    payload["profit"],
                    payload["created_at"],
                    payload["settled_at"],
                ]
            )
        return csv_response(
            "merchant-orders.csv",
            [
                "子单号",
                "订单号",
                "商家",
                "状态",
                "进度节点",
                "成交金额",
                "发货成本",
                "盈利",
                "下单时间",
                "回款时间",
            ],
            rows,
        )
