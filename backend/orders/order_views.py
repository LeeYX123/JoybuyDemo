import json

from django.http import JsonResponse

from cart.services import get_or_create_cart, resolve_cart_context, serialize_cart
from orders.models import Order
from orders.order_services import OrderError, attempt_payment, cancel_order, place_order


def _error(request, exc_or_code, message=None, status=400):
    if isinstance(exc_or_code, OrderError):
        code, message = exc_or_code.code, exc_or_code.message
    else:
        code, message = exc_or_code, message
    return JsonResponse(
        {
            "error": {"code": code, "message": message, "details": None},
            "request_id": getattr(request, "request_id", None),
        },
        status=status,
    )


def order_list_create(request):
    account = getattr(request, "buyer_account", None)
    if account is None:
        return _error(request, "AUTH_REQUIRED", "Sign in required.", 401)

    if request.method == "POST":
        context = resolve_cart_context(request)
        cart = get_or_create_cart(context)
        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return _error(request, "BAD_REQUEST", "Invalid JSON.")
        try:
            order = place_order(
                account=account,
                cart_snapshot=serialize_cart(cart),
                address_snapshot=body.get("address") or {},
                payment_method=str(body.get("payment_method") or ""),
            )
        except OrderError as exc:
            status = 404 if exc.code == "ADDRESS_UNSUPPORTED" else 400
            return _error(request, exc, message=None, status=status)
        return JsonResponse(
            {
                "public_id": str(order.public_id),
                "status": order.status,
                "total": str(order.total),
                "currency": order.currency.code,
                "payment_method": order.payment_method,
                "payment_expires_at": order.payment_expires_at.isoformat(),
            },
            status=201,
        )

    # GET: buyer's pending and canceled orders (phase 1 states only).
    orders = [
        {
            "public_id": str(order.public_id),
            "status": order.status,
            "total": str(order.total),
            "currency": order.currency.code,
            "created_at": order.created_at.isoformat(),
            "payment_expires_at": order.payment_expires_at.isoformat(),
            "item_count": order.items.count(),
        }
        for order in Order.objects.filter(account=account).order_by("-created_at")[:50]
    ]
    return JsonResponse({"orders": orders})


def order_detail(request, public_id):
    account = getattr(request, "buyer_account", None)
    if account is None:
        return _error(request, "AUTH_REQUIRED", "Sign in required.", 401)
    order = (
        Order.objects.filter(account=account, public_id=public_id).prefetch_related("items").first()
    )
    if order is None:
        return _error(request, "ORDER_NOT_FOUND", "Order not found.", 404)
    return JsonResponse(
        {
            "public_id": str(order.public_id),
            "status": order.status,
            "total": str(order.total),
            "currency": order.currency.code,
            "payment_method": order.payment_method,
            "created_at": order.created_at.isoformat(),
            "paid_at": order.paid_at.isoformat() if order.paid_at else None,
            "items": [
                {
                    "title": item.title,
                    "quantity": item.quantity,
                    "unit_price": str(item.unit_price),
                    "currency": item.currency,
                }
                for item in order.items.all()
            ],
            "shipping_address": order.shipping_address,
            "payment_expires_at": order.payment_expires_at.isoformat(),
            "canceled_at": order.canceled_at.isoformat() if order.canceled_at else None,
            "cancel_reason": order.cancel_reason,
            # 商家子单进度（确认收货按钮据此判断是否还有未完成的子单）。
            "merchant_orders": [
                {
                    "id": str(sub.public_id),
                    "status": sub.status,
                    "progress": sub.progress,
                    "items_total": str(sub.items_total),
                }
                for sub in order.merchant_orders.all()
            ],
        }
    )


def order_confirm_receipt(request, public_id):
    """购物端【确认收货】：与后台"一键完成全部节点"完全同源（迭代02）。

    该订单的全部商家子单一次性走到【用户确认收货】节点：状态完成、
    回款入商家钱包（settle 幂等，只入账一次）。正常自动流转不受影响。
    """

    from django.db import transaction

    from merchant_ops.services import complete_all_nodes

    if request.method != "POST":
        return _error(request, "METHOD_NOT_ALLOWED", "Unsupported method.", 405)
    account = getattr(request, "buyer_account", None)
    if account is None:
        return _error(request, "AUTH_REQUIRED", "Sign in required.", 401)
    order = Order.objects.filter(account=account, public_id=public_id).first()
    if order is None:
        return _error(request, "ORDER_NOT_FOUND", "Order not found.", 404)
    if order.status != Order.Status.PAID:
        return _error(request, "ORDER_NOT_PAID", "Order is not paid yet.", 400)

    completed = 0
    with transaction.atomic():
        suborders = list(order.merchant_orders.select_for_update())
        for suborder in suborders:
            complete_all_nodes(suborder)
            completed += 1
    return JsonResponse(
        {
            "public_id": str(order.public_id),
            "status": Order.objects.get(pk=order.pk).status,
            "completed_merchant_orders": completed,
        }
    )


def payment_attempt(request, public_id):
    if request.method != "POST":
        return _error(request, "METHOD_NOT_ALLOWED", "Unsupported method.", 405)
    account = getattr(request, "buyer_account", None)
    if account is None:
        return _error(request, "AUTH_REQUIRED", "Sign in required.", 401)
    order = Order.objects.filter(account=account, public_id=public_id).first()
    if order is None:
        return _error(request, "ORDER_NOT_FOUND", "Order not found.", 404)
    try:
        attempt_payment(order)
    except OrderError as exc:
        status = 422 if exc.code == "PAYMENT_REGION_UNSUPPORTED" else 400
        return _error(request, exc, message=None, status=status)
    return JsonResponse({"ok": True})


def admin_cancel(request, public_id):
    """Ops hook for the timeout sweep (used by tests and maintenance)."""
    account = getattr(request, "buyer_account", None)
    order = Order.objects.filter(public_id=public_id).first()
    if order is None or (account and order.account_id != account.pk):
        return _error(request, "ORDER_NOT_FOUND", "Order not found.", 404)
    changed = cancel_order(order, reason="PAYMENT_WINDOW_EXPIRED")
    return JsonResponse({"canceled": changed})
