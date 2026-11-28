import json
from uuid import UUID

from django.http import JsonResponse

from cart.services import get_or_create_cart, resolve_cart_context, serialize_cart
from orders.models import Order
from orders.order_services import OrderError, attempt_payment, cancel_order, place_order


def _local_iso(value) -> str | None:
    """购物端时间展示（迭代02）：按 X-Client-Timezone 转当地时区，只影响展示。"""

    if not value:
        return None
    from django.utils import timezone as dj_tz

    from common.client_timezone import get_client_timezone

    tz_name = get_client_timezone()
    if tz_name:
        try:
            from zoneinfo import ZoneInfo

            return dj_tz.localtime(value, ZoneInfo(tz_name)).isoformat()
        except Exception:
            pass
    return dj_tz.localtime(value).isoformat()


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


def _normalized_public_id(value) -> str | None:
    """商品 public_id 归一化成 32 位小写十六进制（脏值返回 None）。

    ``Spu.public_id`` 是 ``UUIDField``：库里存 32 位无连字符，Python 里
    ``str()`` 是 36 位带连字符。``OrderItem.spu_public_id`` 是字符串快照，
    历史数据写的是 ``str(spu.public_id)``（36 位带连字符）。两边必须归一化后
    再比对，否则订单商品图会丢（2026-11-27 编号改造期间踩过）。
    """

    try:
        return UUID(str(value).strip()).hex
    except (TypeError, ValueError, AttributeError):
        return None


def _order_gallery_images(spu_public_ids):
    """First local gallery image per SPU, one query for a whole order page.

    键统一用归一化后的 32 位十六进制；调用方查表也走
    :func:`_normalized_public_id`，与数据库列形态无关。
    """

    valid_ids = {
        normalized
        for value in spu_public_ids
        if (normalized := _normalized_public_id(value)) is not None
    }
    if not valid_ids:
        return {}

    from django.contrib.contenttypes.models import ContentType

    from catalog.models import Spu
    from media.models import MediaUsage
    from media.storage import media_url

    spus = {spu.public_id.hex: spu.pk for spu in Spu.objects.filter(public_id__in=valid_ids)}
    if not spus:
        return {}
    spu_type = ContentType.objects.get_for_model(Spu)
    usages = (
        MediaUsage.objects.filter(
            content_type=spu_type,
            object_id__in=set(spus.values()),
            role="gallery",
        )
        .select_related("asset")
        .order_by("object_id", "sort_order", "pk")
    )
    first_image = {}
    for usage in usages:
        first_image.setdefault(usage.object_id, media_url(usage.asset.relative_path))
    return {public_id: first_image.get(pk, "") for public_id, pk in spus.items()}


def _order_state(order) -> str:
    """Buyer-facing state for the Joybuy order tabs.

    Joybuy's UK order page groups orders as All / Pending payment / To receive
    / Completed / Canceled. A paid order that has not shipped yet belongs to
    "All" only, which is why PROCESSING is a separate internal state.
    """

    if order.status == Order.Status.CANCELED:
        return "CANCELED"
    if order.status == Order.Status.PENDING_PAYMENT:
        return "PENDING_PAYMENT"
    suborders = list(order.merchant_orders.all())
    if suborders:
        if all(
            suborder.status == "COMPLETED" or suborder.progress >= 7 for suborder in suborders
        ):
            return "COMPLETED"
        if any(suborder.status == "SHIPPED" or suborder.progress >= 1 for suborder in suborders):
            return "SHIPPED"
    return "PROCESSING"


def _order_items_payload(order, images):
    return [
        {
            "title": item.title,
            "quantity": item.quantity,
            "unit_price": str(item.unit_price),
            "currency": item.currency,
            "spu_public_id": item.spu_public_id,
            "image_path": images.get(_normalized_public_id(item.spu_public_id) or "", ""),
        }
        for item in order.items.all()
    ]


def order_list_create(request):
    account = getattr(request, "buyer_account", None)
    if account is None:
        return _error(request, "AUTH_REQUIRED", "Sign in required.", 401)

    if request.method == "POST":
        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return _error(request, "BAD_REQUEST", "Invalid JSON.")
        # 立即购买（2026-11-28）：body 带 offer_public_id 时走独立直购上下文——
        # 不读购物车、不写 cart 行；不带时保持原购物车快照路径。
        offer_public_id = str(body.get("offer_public_id") or "").strip()
        try:
            if offer_public_id:
                order = place_order(
                    account=account,
                    cart_snapshot=None,
                    address_snapshot=body.get("address") or {},
                    payment_method=str(body.get("payment_method") or ""),
                    offer_public_id=offer_public_id,
                    quantity=body.get("quantity", 1),
                )
            else:
                context = resolve_cart_context(request)
                cart = get_or_create_cart(context)
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
                "payment_expires_at": _local_iso(order.payment_expires_at),
            },
            status=201,
        )

    # GET: buyer's orders, newest first (up to 50). The storefront renders the
    # Joybuy card layout (thumbnails, state tabs, totals) from this payload.
    orders = list(
        Order.objects.filter(account=account)
        .prefetch_related("items", "merchant_orders")
        .order_by("-created_at")[:50]
    )
    images = _order_gallery_images(
        item.spu_public_id for order in orders for item in order.items.all()
    )
    return JsonResponse(
        {
            "orders": [
                {
                    "public_id": str(order.public_id),
                    "status": order.status,
                    "state": _order_state(order),
                    "total": str(order.total),
                    "currency": order.currency.code,
                    "created_at": _local_iso(order.created_at),
                    "payment_expires_at": _local_iso(order.payment_expires_at),
                    "payment_method": order.payment_method,
                    "item_count": order.items.count(),
                    "items": _order_items_payload(order, images),
                    "merchant_orders": [
                        {"status": suborder.status, "progress": suborder.progress}
                        for suborder in order.merchant_orders.all()
                    ],
                }
                for order in orders
            ]
        }
    )


def order_detail(request, public_id):
    account = getattr(request, "buyer_account", None)
    if account is None:
        return _error(request, "AUTH_REQUIRED", "Sign in required.", 401)
    order = (
        Order.objects.filter(account=account, public_id=public_id).prefetch_related("items").first()
    )
    if order is None:
        return _error(request, "ORDER_NOT_FOUND", "Order not found.", 404)
    from orders.commerce_payloads import (
        payment_payloads,
        refund_payloads,
        shipment_payloads,
    )

    return JsonResponse(
        {
            "public_id": str(order.public_id),
            "status": order.status,
            "total": str(order.total),
            "currency": order.currency.code,
            "payment_method": order.payment_method,
            "created_at": _local_iso(order.created_at),
            "paid_at": _local_iso(order.paid_at),
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
            "payment_expires_at": _local_iso(order.payment_expires_at),
            "canceled_at": _local_iso(order.canceled_at),
            "cancel_reason": order.cancel_reason,
            # 阶段 2：支付 / 退款 / 物流编号直出（不截断）。
            "payments": payment_payloads(
                order.payments.all().order_by("created_at", "pk"), iso_fn=_local_iso
            ),
            "refunds": refund_payloads(
                order.refunds.select_related("payment", "after_sale").order_by("created_at", "pk"),
                iso_fn=_local_iso,
            ),
            "shipments": shipment_payloads(
                order.shipments.select_related("merchant_order").order_by("created_at", "pk"),
                iso_fn=_local_iso,
            ),
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
