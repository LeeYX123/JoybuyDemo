"""管理端只读/补录接口：支付、退款、物流（全站编号改造阶段 2）。

三张表在订单/售后详情里已经内嵌，这里只补「跨订单列表 + 手动补录退款」。
列表统一复用 ``merchant_ops.api_utils.paginate``，返回结构与其它管理端列表一致。
退款手动创建是对当前业务缺口的兜底：售后流程没有真实打款动作，等阶段 3 接入
真实退款时再改成由业务动作自动写入。
"""

from django.db.models import Q
from django.utils import timezone
from rest_framework.response import Response

from accounts_staff.api_exceptions import StaffApiError
from accounts_staff.permissions import StaffRbacPermission
from audit.services import record_audit
from merchant_ops.api_utils import OpsAPIView, iso, paginate, parse_amount, require
from merchant_ops.models import AfterSale
from orders.commerce_payloads import (
    payment_payloads,
    refund_payload,
    refund_payloads,
    shipment_payloads,
)
from orders.models import Order, Payment, Refund, Shipment
from orders.payment_services import record_refund


class AdminPaymentsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["orders.manage"]
    view_permissions = ["orders.view"]

    def get(self, request):
        queryset = Payment.objects.select_related("order")
        status = (request.query_params.get("status") or "").strip().upper()
        if status and status != "ALL":
            queryset = queryset.filter(status=status)
        query = (request.query_params.get("q") or "").strip()
        if query:
            queryset = queryset.filter(
                Q(public_id__iexact=query)
                | Q(order__public_id__iexact=query)
                | Q(provider_reference__icontains=query)
            )
        order_id = (request.query_params.get("order_id") or "").strip()
        if order_id:
            queryset = queryset.filter(order__public_id__iexact=order_id)
        rows, meta = paginate(queryset.order_by("-created_at", "-pk"), request)
        return Response({"items": payment_payloads(rows, iso_fn=iso), **meta})


class AdminShipmentsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["orders.manage"]
    view_permissions = ["orders.view"]

    def get(self, request):
        queryset = Shipment.objects.select_related("order", "merchant_order")
        status = (request.query_params.get("status") or "").strip().upper()
        if status and status != "ALL":
            queryset = queryset.filter(status=status)
        query = (request.query_params.get("q") or "").strip()
        if query:
            queryset = queryset.filter(
                Q(public_id__iexact=query)
                | Q(order__public_id__iexact=query)
                | Q(merchant_order__public_id__iexact=query)
                | Q(tracking_no__icontains=query)
            )
        order_id = (request.query_params.get("order_id") or "").strip()
        if order_id:
            queryset = queryset.filter(order__public_id__iexact=order_id)
        rows, meta = paginate(queryset.order_by("-created_at", "-pk"), request)
        return Response({"items": shipment_payloads(rows, iso_fn=iso), **meta})


def _resolve_order(public_id) -> Order:
    order = Order.objects.filter(public_id=public_id).first()
    if order is None:
        raise StaffApiError(
            business_code="ORDER_NOT_FOUND", message="订单不存在。", status_code=404
        )
    return order


class AdminRefundsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["aftersales.manage"]
    view_permissions = ["aftersales.view"]

    def get(self, request):
        queryset = Refund.objects.select_related("order", "payment", "after_sale")
        status = (request.query_params.get("status") or "").strip().upper()
        if status and status != "ALL":
            queryset = queryset.filter(status=status)
        query = (request.query_params.get("q") or "").strip()
        if query:
            queryset = queryset.filter(
                Q(public_id__iexact=query)
                | Q(order__public_id__iexact=query)
                | Q(after_sale__public_id__iexact=query)
            )
        order_id = (request.query_params.get("order_id") or "").strip()
        if order_id:
            queryset = queryset.filter(order__public_id__iexact=order_id)
        rows, meta = paginate(queryset.order_by("-created_at", "-pk"), request)
        return Response({"items": refund_payloads(rows, iso_fn=iso), **meta})

    def post(self, request):
        payload = request.data or {}
        order = _resolve_order(require(payload, "order_id", label="订单号"))

        payment = None
        payment_id = str(payload.get("payment_id") or "").strip()
        if payment_id:
            payment = order.payments.filter(public_id=payment_id).first()
            if payment is None:
                raise StaffApiError(
                    business_code="PAYMENT_NOT_FOUND",
                    message="支付记录不存在或不属于该订单。",
                    status_code=404,
                )

        after_sale = None
        after_sale_id = str(payload.get("after_sale_id") or "").strip()
        if after_sale_id:
            after_sale = AfterSale.objects.filter(public_id=after_sale_id, order=order).first()
            if after_sale is None:
                raise StaffApiError(
                    business_code="AFTER_SALE_NOT_FOUND",
                    message="售后单不存在或不属于该订单。",
                    status_code=404,
                )

        amount = (
            parse_amount(payload.get("amount"), field="退款金额")
            if payload.get("amount") not in (None, "")
            else order.total
        )
        if amount <= 0:
            raise StaffApiError(
                business_code="AMOUNT_INVALID", message="退款金额必须大于 0。", status_code=400
            )

        status = (payload.get("status") or Refund.Status.PENDING).strip().upper()
        if status not in Refund.Status.values:
            raise StaffApiError(
                business_code="REFUND_STATUS_INVALID",
                message="退款状态不合法。",
                status_code=400,
            )

        currency = str(payload.get("currency") or order.currency.code).strip()[:3]
        now = timezone.now()
        refund = record_refund(
            order=order,
            payment=payment,
            after_sale=after_sale,
            amount=amount,
            currency=currency,
            status=status,
            reason=str(payload.get("reason") or "").strip(),
            processed_at=now if status == Refund.Status.SUCCEEDED else None,
        )
        record_audit(
            request=request,
            actor=request.staff_account,
            action="REFUND_CREATED",
            target_type="refund",
            target_id=str(refund.public_id),
            reason=str(payload.get("reason") or "").strip(),
            before_state={},
            after_state={
                "order_id": str(order.public_id),
                "amount": str(refund.amount),
                "currency": refund.currency,
                "status": refund.status,
            },
            tenant_type="PLATFORM",
            tenant_id="",
        )
        return Response({"refund": refund_payload(refund, iso_fn=iso)}, status=201)
