"""一键下单（自动化下单任务）管理端接口（迭代02）。

创建向导的数据源：
- 白名单用户：复用 ``/admin/buyers/accounts?whitelisted=1``；
- 商家：复用 ``/admin/merchants``；
- 商品与规格：``GET /admin/auto-orders/options?merchant_id=&q=``（只列可售商品，
  已下架商品不展示——doc02 拍板）。
"""

import uuid

from django.db.models import Q
from django.utils import timezone
from rest_framework.response import Response

from accounts_staff.api_exceptions import StaffApiError
from accounts_staff.permissions import StaffRbacPermission
from audit.services import record_audit
from merchant_ops.api_utils import OpsAPIView, iso, money_str, paginate
from orders.auto_order_services import (
    AutoOrderError,
    cancel_auto_order_task,
    check_account_balance,
    create_auto_order_task,
    execute_due_auto_orders,
)
from orders.models import AutoOrderTask


def _task_payload(task: AutoOrderTask) -> dict:
    return {
        "id": str(task.public_id),
        "buyer": {
            "id": str(task.account.public_id),
            "name": task.account.email or task.account.phone_e164 or "买家",
            "balance": money_str(task.account.balance),
        },
        "merchant": {"id": str(task.merchant.public_id), "name": task.merchant.display_name},
        "product_title": task.product_title,
        "specification": task.specification or {},
        "quantity": task.quantity,
        "unit_price": money_str(task.unit_price) if task.unit_price is not None else None,
        "trigger_at": iso(task.trigger_at),
        "status": task.status,
        "failure_reason": task.failure_reason,
        "executed_order_id": str(task.executed_order.public_id)
        if task.executed_order_id
        else None,
        "executed_at": iso(task.executed_at),
        "created_at": iso(task.created_at),
    }


def _run_due_lazily() -> None:
    """开发环境无调度器的兜底：管理端列表页读取时顺手执行到点任务。

    生产环境由 ``run_order_sweeps``（cron）承担，见 docs/08。
    """

    try:
        execute_due_auto_orders()
    except Exception:  # pragma: no cover - 清扫失败不阻塞列表读取
        pass


class AdminAutoOrdersView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["orders.manage"]
    view_permissions = ["orders.view"]

    def get(self, request):
        _run_due_lazily()
        queryset = AutoOrderTask.objects.select_related(
            "account", "merchant", "executed_order"
        )
        status = (request.query_params.get("status") or "").strip().upper()
        if status and status != "ALL" and status in AutoOrderTask.Status.values:
            queryset = queryset.filter(status=status)
        query = (request.query_params.get("q") or "").strip()
        if query:
            queryset = queryset.filter(
                Q(product_title__icontains=query)
                | Q(account__email__icontains=query)
                | Q(merchant__display_name__icontains=query)
            )
        rows, meta = paginate(queryset, request)
        return Response({"items": [_task_payload(row) for row in rows], **meta})

    def post(self, request):
        from accounts_buyers.models import BuyerAccount
        from merchants.models import Merchant
        from offers.models import Offer

        payload = request.data or {}

        def _uuid(value, label):
            try:
                return uuid.UUID(str(value))
            except (ValueError, AttributeError, TypeError) as exc:
                raise StaffApiError(
                    business_code="ID_INVALID", message=f"{label} 格式不正确。", status_code=400
                ) from exc

        # 2026-11-27 全站编号改造：买家号是 JYU+10 位字符串，不再按 UUID 解析。
        account_id = str(payload.get("account_id") or "").strip()
        account = (
            BuyerAccount.objects.filter(public_id__iexact=account_id).first()
            if account_id
            else None
        )
        # 商家 ID 是 JYM+10 位字符串，按字符串精确匹配。
        merchant_id = str(payload.get("merchant_id") or "").strip()
        if not merchant_id:
            raise StaffApiError(
                business_code="ID_INVALID", message="商家 格式不正确。", status_code=400
            )
        merchant = Merchant.objects.filter(public_id__iexact=merchant_id).first()
        # 商品规格（Offer）仍是 UUID，保持原解析。
        offer = Offer.objects.select_related("sku__spu").filter(
            public_id=_uuid(payload.get("offer_id"), "商品规格")
        ).first()
        try:
            quantity = int(payload.get("quantity") or 1)
        except (TypeError, ValueError) as exc:
            raise StaffApiError(
                business_code="QUANTITY_INVALID", message="数量必须是正整数。", status_code=400
            ) from exc
        trigger_raw = payload.get("trigger_at")
        trigger_at = None
        if trigger_raw:
            from django.utils.dateparse import parse_datetime

            trigger_at = parse_datetime(str(trigger_raw))
            if trigger_at is None:
                raise StaffApiError(
                    business_code="TRIGGER_TIME_INVALID", message="触发时间格式不正确。", status_code=400
                )
            if timezone.is_naive(trigger_at):
                trigger_at = timezone.make_aware(trigger_at)

        if account is None:
            raise StaffApiError(
                business_code="ACCOUNT_NOT_FOUND", message="买家账号不存在。", status_code=404
            )
        if merchant is None:
            raise StaffApiError(
                business_code="MERCHANT_NOT_FOUND", message="商家不存在。", status_code=404
            )
        # 迭代02 反馈：创建时余额不足直接拒绝并提醒（触发时还会再校验一次）。
        # 注意在 create_auto_order_task 之前校验，避免拒绝后残留任务。
        balance_warning = check_account_balance(account, offer, quantity)
        if balance_warning:
            raise StaffApiError(
                business_code="BALANCE_INSUFFICIENT",
                message=balance_warning,
                status_code=400,
            )
        try:
            task = create_auto_order_task(
                account=account,
                merchant=merchant,
                offer=offer,
                quantity=quantity,
                trigger_at=trigger_at,
                created_by=request.staff_account,
            )
        except AutoOrderError as exc:
            raise StaffApiError(
                business_code=exc.code, message=exc.message, status_code=400
            ) from exc

        record_audit(
            request=request,
            actor=request.staff_account,
            action="AUTO_ORDER_TASK_CREATED",
            target_type="auto_order_task",
            target_id=str(task.public_id),
            reason="",
            before_state={},
            after_state={
                "buyer": str(account.public_id),
                "merchant": str(merchant.public_id),
                "offer": str(offer.public_id),
                "quantity": quantity,
                "trigger_at": iso(task.trigger_at),
                "balance_warning": balance_warning,
            },
        )
        return Response({"task": _task_payload(task)}, status=201)


class AdminAutoOrderActionsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["orders.manage"]
    view_permissions = ["orders.view"]

    def post(self, request, public_id):
        task = AutoOrderTask.objects.filter(public_id=public_id).first()
        if task is None:
            raise StaffApiError(
                business_code="TASK_NOT_FOUND", message="任务不存在。", status_code=404
            )
        action = ((request.data or {}).get("action") or "").strip().lower()
        if action != "cancel":
            raise StaffApiError(
                business_code="ACTION_UNSUPPORTED", message="不支持的操作。", status_code=400
            )
        try:
            task = cancel_auto_order_task(task, actor=request.staff_account)
        except AutoOrderError as exc:
            raise StaffApiError(
                business_code=exc.code, message=exc.message, status_code=409
            ) from exc
        record_audit(
            request=request,
            actor=request.staff_account,
            action="AUTO_ORDER_TASK_CANCELED",
            target_type="auto_order_task",
            target_id=str(task.public_id),
            reason="",
            before_state={"status": "PENDING"},
            after_state={"status": task.status},
        )
        return Response({"task": _task_payload(task)})


class AdminAutoOrderOptionsView(OpsAPIView):
    """向导第 3/4 步数据源：某商家的可售商品 + 规格（已下架商品不展示）。"""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["orders.manage"]
    view_permissions = ["orders.view"]

    def get(self, request):
        from catalog.models import Spu
        from merchants.models import Merchant
        from offers.models import Offer

        merchant_id = (request.query_params.get("merchant_id") or "").strip()
        merchant = (
            Merchant.objects.filter(public_id=merchant_id).first() if merchant_id else None
        )
        if merchant is None:
            raise StaffApiError(
                business_code="MERCHANT_NOT_FOUND", message="商家不存在。", status_code=404
            )
        query = (request.query_params.get("q") or "").strip()
        offers = (
            Offer.objects.filter(
                merchant=merchant,
                status=Offer.Status.ACTIVE,
                sku__spu__status=Spu.Status.ACTIVE,
                source_availability__in=[Offer.SourceAvailability.IN_STOCK, Offer.SourceAvailability.UNKNOWN],
            )
            .select_related("sku__spu", "currency")
            .prefetch_related("sku__spu__translations")
        )
        items = []
        seen = {}
        for offer in offers:
            spu = offer.sku.spu
            if query and query.lower() not in _spu_title(spu).lower():
                continue
            entry = seen.setdefault(
                spu.pk,
                {
                    "id": str(spu.public_id),
                    "title": _spu_title(spu),
                    "image": (spu.image_urls or [""])[0],
                    "price": money_str(offer.current_price),
                    "currency": offer.currency.code,
                    "offers": [],
                },
            )
            entry["offers"].append(
                {
                    "offer_id": str(offer.public_id),
                    "specification": offer.sku.specification or {},
                    "price": money_str(offer.current_price),
                    "inventory": offer.local_inventory,
                }
            )
        items = list(seen.values())[:30]
        return Response({"items": items})


def _spu_title(spu) -> str:
    for translation in spu.translations.all():
        if translation.title:
            return translation.title
    return f"SPU {str(spu.public_id)[:8]}"
