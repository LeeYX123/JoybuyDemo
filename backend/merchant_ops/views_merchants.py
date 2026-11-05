"""A02 商家管理：入驻审核、资金与信誉调整、封店解封。"""

from django.db.models import Count, Q, Sum
from rest_framework.response import Response

from accounts_staff.permissions import StaffRbacPermission
from audit.services import record_audit
from merchant_ops.api_utils import (
    OpsAPIView,
    csv_response,
    date_str,
    iso,
    money_str,
    paginate,
    parse_amount,
    parse_positive_int,
    require,
)
from merchants.models import Merchant
from merchants.services import (
    add_exposure,
    add_followers,
    create_merchant,
    deduct_credit,
    review_admission,
    set_merchant_suspension,
    update_merchant_profile,
)
from orders.models import MerchantOrder

STATUS_TABS = {
    "PENDING_REVIEW",
    "PENDING_DEPOSIT",
    "ACTIVE",
    "SUSPENDED",
    "REJECTED",
    "DRAFT",
}


def _plain_number(value) -> str:
    """信誉分这类小数按需显示 100 / 98.5，不强制两位小数。"""
    number = float(value or 0)
    return str(int(number)) if number == int(number) else f"{number:.2f}"


def _merchant_payload(merchant: Merchant, *, pending=None) -> dict:
    pending = pending or {}
    return {
        "id": str(merchant.public_id),
        "name": merchant.display_name,
        "legal_name": merchant.legal_name,
        "avatar": merchant.avatar_url,
        "status": merchant.onboarding_status,
        "admission_approved": merchant.admission_approved,
        "admission_reviewed_at": iso(merchant.admission_reviewed_at),
        "deposit_enabled": merchant.deposit_enabled,
        "deposit_required": money_str(merchant.deposit_required)
        if merchant.deposit_required is not None
        else None,
        "deposit_balance": money_str(merchant.deposit_balance),
        "deposit_initial_paid": merchant.deposit_initial_paid,
        "wallet_balance": money_str(merchant.wallet_balance),
        "credit_score": _plain_number(merchant.credit_score),
        "ban_after_days": merchant.ban_after_days,
        "suspend_reason": merchant.suspend_reason,
        "followers": merchant.followers,
        "follow_delta": merchant.follow_delta,
        "follow_day": date_str(merchant.follow_day),
        "exposure": merchant.exposure,
        "referral_code": merchant.referral_code,
        "joined": iso(merchant.created_at),
        "last_online_at": iso(merchant.last_online_at),
        "currency": merchant.currency,
        "pending_order_count": pending.get("count", 0),
        "pending_order_amount": money_str(pending.get("amount") or 0),
    }


def _pending_aggregate(merchant_ids) -> dict:
    rows = (
        MerchantOrder.objects.filter(
            merchant_id__in=merchant_ids,
            status=MerchantOrder.Status.PENDING,
        )
        .values("merchant_id")
        .annotate(count=Count("id"), amount=Sum("items_total"))
    )
    return {row["merchant_id"]: {"count": row["count"], "amount": row["amount"]} for row in rows}


def _filtered_queryset(request):
    # 「全部商家」只排除技术性的导入兜底商家（爬虫没有卖家信息时的收纳桶），
    # 爬虫识别出的来源店铺仍然算真实店铺，否则列表在全新库上会一片空白。
    queryset = Merchant.objects.exclude(merchant_type=Merchant.Type.IMPORT_FALLBACK)
    status = (request.query_params.get("status") or "").strip().upper()
    if status and status != "ALL" and status in STATUS_TABS:
        queryset = queryset.filter(onboarding_status=status)
    query = (request.query_params.get("q") or "").strip()
    if query:
        condition = Q(display_name__icontains=query) | Q(slug__icontains=query)
        try:
            import uuid as uuid_module

            condition |= Q(public_id=uuid_module.UUID(query))
        except ValueError:
            pass
        queryset = queryset.filter(condition)
    return queryset.order_by("-created_at", "-pk")


class AdminMerchantsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["merchants.manage"]
    view_permissions = ["merchants.view"]

    def get(self, request):
        rows, meta = paginate(_filtered_queryset(request), request)
        aggregates = _pending_aggregate([merchant.pk for merchant in rows])
        return Response(
            {
                "items": [
                    _merchant_payload(merchant, pending=aggregates.get(merchant.pk))
                    for merchant in rows
                ],
                **meta,
            }
        )

    def post(self, request):
        payload = request.data or {}
        merchant = create_merchant(
            display_name=require(payload, "name", label="店铺名称"),
            legal_name=payload.get("legal_name") or "",
            avatar_url=payload.get("avatar") or "",
            admission_approved=bool(payload.get("admission_approved")),
            require_deposit=bool(payload.get("require_deposit")),
            deposit_required=parse_amount(payload["deposit_required"], field="应缴保证金")
            if payload.get("deposit_required")
            else None,
            ban_after_days=parse_positive_int(
                payload.get("ban_after_days", 4), field="未发货封店天数"
            ),
        )
        record_audit(
            request=request,
            actor=request.staff_account,
            action="MERCHANT_CREATED",
            target_type="merchant",
            target_id=str(merchant.public_id),
            reason="",
            before_state={},
            after_state={"name": merchant.display_name, "status": merchant.onboarding_status},
        )
        return Response({"merchant": _merchant_payload(merchant)}, status=201)


class AdminMerchantDetailView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["merchants.manage"]
    view_permissions = ["merchants.view"]

    def _get(self, public_id):
        merchant = Merchant.objects.filter(public_id=public_id).first()
        if merchant is None:
            from accounts_staff.api_exceptions import StaffApiError

            raise StaffApiError(
                business_code="MERCHANT_NOT_FOUND",
                message="商家不存在。",
                status_code=404,
            )
        return merchant

    def get(self, request, public_id):
        merchant = self._get(public_id)
        aggregates = _pending_aggregate([merchant.pk])
        payload = _merchant_payload(merchant, pending=aggregates.get(merchant.pk))

        from audit.models import AuditLog

        credit_logs = AuditLog.objects.filter(
            target_type="merchant",
            target_id=str(merchant.public_id),
            action="MERCHANT_CREDIT_DEDUCTED",
        )[:10]
        payload["credit_records"] = [
            {
                "id": str(log.pk),
                "occurred_at": iso(log.created_at),
                "operator": log.actor.display_name if log.actor else "系统",
                "before": log.before_state.get("credit_score"),
                "after": log.after_state.get("credit_score"),
            }
            for log in credit_logs
        ]
        return Response({"merchant": payload})

    def patch(self, request, public_id):
        merchant = self._get(public_id)
        payload = request.data or {}
        before = {
            "name": merchant.display_name,
            "avatar": merchant.avatar_url,
            "wallet_balance": money_str(merchant.wallet_balance),
            "credit_score": str(merchant.credit_score),
            "ban_after_days": merchant.ban_after_days,
        }
        merchant = update_merchant_profile(
            merchant,
            display_name=payload.get("name"),
            avatar_url=payload.get("avatar"),
            legal_name=payload.get("legal_name"),
        )

        wallet_entry = None
        if payload.get("wallet_balance") not in (None, ""):
            from merchant_ops.services import adjust_wallet

            target = parse_amount(payload["wallet_balance"], field="钱包余额")
            wallet_entry = adjust_wallet(
                merchant, target_balance=target, actor=request.staff_account
            )
            merchant.refresh_from_db()

        if payload.get("ban_after_days") not in (None, ""):
            days = parse_positive_int(payload["ban_after_days"], field="未发货封店天数")
            merchant.ban_after_days = days
            merchant.save(update_fields=["ban_after_days", "updated_at"])

        record_audit(
            request=request,
            actor=request.staff_account,
            action="MERCHANT_UPDATED",
            target_type="merchant",
            target_id=str(merchant.public_id),
            reason="",
            before_state=before,
            after_state={
                "name": merchant.display_name,
                "avatar": merchant.avatar_url,
                "wallet_balance": money_str(merchant.wallet_balance),
                "credit_score": str(merchant.credit_score),
                "ban_after_days": merchant.ban_after_days,
            },
        )
        payload_out = _merchant_payload(merchant)
        if wallet_entry is not None:
            payload_out["wallet_entry"] = {
                "id": str(wallet_entry.public_id),
                "amount": money_str(wallet_entry.amount),
                "balance_after": money_str(wallet_entry.balance_after),
            }
        return Response({"merchant": payload_out})


class AdminMerchantActionsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["merchants.manage"]
    view_permissions = ["merchants.view"]

    def post(self, request, public_id):
        from accounts_staff.api_exceptions import StaffApiError

        merchant = Merchant.objects.filter(public_id=public_id).first()
        if merchant is None:
            raise StaffApiError(
                business_code="MERCHANT_NOT_FOUND", message="商家不存在。", status_code=404
            )
        payload = request.data or {}
        action = (payload.get("action") or "").strip().lower()
        before = {
            "status": merchant.onboarding_status,
            "credit_score": str(merchant.credit_score),
            "followers": merchant.followers,
            "exposure": merchant.exposure,
        }

        if action == "review":
            approved = bool(payload.get("approved"))
            merchant = review_admission(
                merchant,
                approved=approved,
                require_deposit=bool(payload.get("require_deposit")),
                deposit_required=parse_amount(payload["deposit_required"], field="应缴保证金")
                if payload.get("deposit_required")
                else None,
                ban_after_days=parse_positive_int(
                    payload.get("ban_after_days", merchant.ban_after_days),
                    field="未发货封店天数",
                ),
            )
            audit_action = (
                "MERCHANT_ADMISSION_APPROVED" if approved else "MERCHANT_ADMISSION_REJECTED"
            )
        elif action in {"suspend", "unsuspend"}:
            merchant = set_merchant_suspension(
                merchant,
                suspended=action == "suspend",
                reason=(payload.get("reason") or "").strip(),
            )
            audit_action = "MERCHANT_SUSPENDED" if action == "suspend" else "MERCHANT_UNSUSPENDED"
        elif action == "deduct_credit":
            points = parse_amount(payload.get("points"), field="扣分数")
            merchant = deduct_credit(merchant, points=points)
            audit_action = "MERCHANT_CREDIT_DEDUCTED"
        elif action == "add_followers":
            count = parse_positive_int(payload.get("count"), field="新增关注")
            merchant = add_followers(merchant, count=count)
            audit_action = "MERCHANT_FOLLOWERS_ADDED"
        elif action == "add_exposure":
            count = parse_positive_int(payload.get("count"), field="新增曝光")
            merchant = add_exposure(merchant, count=count)
            audit_action = "MERCHANT_EXPOSURE_ADDED"
        else:
            raise StaffApiError(
                business_code="ACTION_UNSUPPORTED",
                message="不支持的操作。",
                status_code=400,
            )

        record_audit(
            request=request,
            actor=request.staff_account,
            action=audit_action,
            target_type="merchant",
            target_id=str(merchant.public_id),
            reason=(payload.get("reason") or "").strip(),
            before_state=before,
            after_state={
                "status": merchant.onboarding_status,
                "credit_score": str(merchant.credit_score),
                "followers": merchant.followers,
                "exposure": merchant.exposure,
            },
        )
        return Response({"merchant": _merchant_payload(merchant)})


class AdminMerchantsExportView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["merchants.manage"]
    view_permissions = ["merchants.view"]

    def get(self, request):
        merchants = list(_filtered_queryset(request)[:2000])
        aggregates = _pending_aggregate([merchant.pk for merchant in merchants])
        rows = []
        for merchant in merchants:
            payload = _merchant_payload(merchant, pending=aggregates.get(merchant.pk))
            rows.append(
                [
                    payload["id"],
                    payload["name"],
                    payload["status"],
                    payload["pending_order_count"],
                    payload["pending_order_amount"],
                    payload["wallet_balance"],
                    payload["deposit_balance"],
                    payload["credit_score"],
                    payload["joined"],
                ]
            )
        return csv_response(
            "merchants.csv",
            [
                "店铺ID",
                "店铺名称",
                "状态",
                "待发货订单数",
                "待发货金额",
                "钱包余额",
                "保证金余额",
                "信誉分",
                "入驻时间",
            ],
            rows,
        )
