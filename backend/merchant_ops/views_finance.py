"""A06 资金审核 / A07 保证金管理。"""

from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework.response import Response

from accounts_staff.api_exceptions import StaffApiError
from accounts_staff.permissions import StaffRbacPermission
from audit.services import record_audit
from merchant_ops.api_utils import (
    OpsAPIView,
    csv_response,
    iso,
    money_str,
    paginate,
    parse_amount,
    require,
)
from merchant_ops.models import (
    MerchantDepositEntry,
    MerchantWalletEntry,
    MerchantWithdrawal,
)
from merchant_ops.services import (
    adjust_deposit,
    pay_commission,  # noqa: F401  (返佣发放与资金审核共用钱包口径)
    recharge_deposit,
    recharge_wallet,
    return_withdrawal,
)
from merchants.models import Merchant

TRANSITIONS = {
    "PENDING": {"approve", "reject"},
    "APPROVED": {"start_transfer"},
    "TRANSFERRING": {"mark_paid", "mark_failed"},
}


def _withdrawal_payload(withdrawal: MerchantWithdrawal) -> dict:
    return {
        "id": str(withdrawal.public_id),
        "merchant": {
            "id": str(withdrawal.merchant.public_id),
            "name": withdrawal.merchant.display_name,
        },
        "method": withdrawal.method,
        "currency": withdrawal.currency,
        "amount": money_str(withdrawal.amount),
        "fee": money_str(withdrawal.fee),
        "net_amount": money_str(withdrawal.net_amount),
        "state": withdrawal.state,
        "bank": {
            "name": withdrawal.bank_name,
            "account": withdrawal.bank_account,
            "holder": withdrawal.bank_holder,
            "branch": withdrawal.bank_branch,
            "code": withdrawal.bank_code,
        }
        if withdrawal.method == MerchantWithdrawal.Method.BANK
        else None,
        "chain": {
            "coin": withdrawal.coin,
            "network": withdrawal.network,
            "address": withdrawal.chain_address,
        }
        if withdrawal.method == MerchantWithdrawal.Method.CHAIN
        else None,
        "reference": withdrawal.reference,
        "reason": withdrawal.reason,
        "returned": withdrawal.returned,
        "approved_at": iso(withdrawal.approved_at),
        "paid_at": iso(withdrawal.paid_at),
        "created_at": iso(withdrawal.created_at),
    }


def _ledger_payload(entry: MerchantWalletEntry) -> dict:
    return {
        "id": str(entry.public_id),
        "merchant": {
            "id": str(entry.merchant.public_id),
            "name": entry.merchant.display_name,
        },
        "kind": entry.kind,
        "state": entry.state,
        "currency": entry.currency,
        "amount": money_str(entry.amount),
        "balance_before": money_str(entry.balance_before),
        "balance_after": money_str(entry.balance_after),
        "order_id": str(entry.order.public_id) if entry.order_id else None,
        "note": entry.note,
        "occurred_at": iso(entry.occurred_at),
    }


class AdminFinanceSummaryView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["finance.manage"]
    view_permissions = ["finance.view"]

    def get(self, request):
        pending = MerchantWithdrawal.objects.filter(
            state=MerchantWithdrawal.State.PENDING
        ).aggregate(count=Sum("amount", default=0))
        pending_count = MerchantWithdrawal.objects.filter(
            state=MerchantWithdrawal.State.PENDING
        ).count()
        recharge_total = MerchantWalletEntry.objects.filter(
            kind=MerchantWalletEntry.Kind.RECHARGE,
            state=MerchantWalletEntry.State.COMPLETED,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
        withdrawn_total = MerchantWithdrawal.objects.filter(
            state=MerchantWithdrawal.State.PAID
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
        return Response(
            {
                "summary": {
                    "pending_withdrawal_count": pending_count,
                    "pending_withdrawal_amount": money_str(pending["count"]),
                    "recharge_total": money_str(recharge_total),
                    "withdrawal_paid_total": money_str(withdrawn_total),
                }
            }
        )


class AdminWithdrawalsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["finance.manage"]
    view_permissions = ["finance.view"]

    def get(self, request):
        queryset = MerchantWithdrawal.objects.select_related("merchant")
        state = (request.query_params.get("state") or "").strip().upper()
        if state and state != "ALL":
            queryset = queryset.filter(state=state)
        query = (request.query_params.get("q") or "").strip()
        if query:
            queryset = queryset.filter(
                Q(merchant__display_name__icontains=query)
                | Q(bank_holder__icontains=query)
                | Q(bank_account__icontains=query)
            )
        rows, meta = paginate(queryset.order_by("-created_at", "-pk"), request)
        return Response({"items": [_withdrawal_payload(row) for row in rows], **meta})


class AdminWithdrawalActionsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["finance.manage"]
    view_permissions = ["finance.view"]

    def post(self, request, public_id):
        withdrawal = (
            MerchantWithdrawal.objects.select_related("merchant")
            .filter(public_id=public_id)
            .first()
        )
        if withdrawal is None:
            raise StaffApiError(
                business_code="WITHDRAWAL_NOT_FOUND", message="提现申请不存在。", status_code=404
            )
        payload = request.data or {}
        action = (payload.get("action") or "").strip().lower()
        allowed = TRANSITIONS.get(withdrawal.state, set())
        if action not in allowed:
            raise StaffApiError(
                business_code="WITHDRAWAL_STATE_INVALID",
                message="当前提现状态不支持该操作。",
                status_code=409,
            )

        before = {"state": withdrawal.state, "fee": str(withdrawal.fee)}
        now = timezone.now()

        if action == "approve":
            fee = parse_amount(payload.get("fee") or 0, field="手续费")
            if fee < 0:
                raise StaffApiError(
                    business_code="FEE_INVALID", message="手续费不能为负。", status_code=400
                )
            if fee >= withdrawal.amount:
                raise StaffApiError(
                    business_code="FEE_TOO_LARGE",
                    message="手续费必须小于申请金额。",
                    status_code=400,
                )
            withdrawal.state = MerchantWithdrawal.State.APPROVED
            withdrawal.fee = fee
            withdrawal.net_amount = withdrawal.amount - fee
            withdrawal.approved_at = now
            withdrawal.reviewed_by = request.staff_account
            withdrawal.save(
                update_fields=[
                    "state",
                    "fee",
                    "net_amount",
                    "approved_at",
                    "reviewed_by",
                    "updated_at",
                ]
            )
        elif action == "reject":
            withdrawal.state = MerchantWithdrawal.State.REJECTED
            withdrawal.reason = (payload.get("reason") or "").strip()
            withdrawal.reviewed_by = request.staff_account
            withdrawal.save(update_fields=["state", "reason", "reviewed_by", "updated_at"])
            return_withdrawal(withdrawal, actor=request.staff_account, reason=withdrawal.reason)
        elif action == "start_transfer":
            reference = require(payload, "reference", label="出款凭证")
            withdrawal.state = MerchantWithdrawal.State.TRANSFERRING
            withdrawal.reference = reference.strip()
            withdrawal.save(update_fields=["state", "reference", "updated_at"])
        elif action == "mark_paid":
            withdrawal.state = MerchantWithdrawal.State.PAID
            withdrawal.paid_at = now
            if payload.get("reference"):
                withdrawal.reference = payload["reference"].strip()
            withdrawal.save(update_fields=["state", "paid_at", "reference", "updated_at"])
        elif action == "mark_failed":
            withdrawal.state = MerchantWithdrawal.State.FAILED
            withdrawal.reason = (payload.get("reason") or "").strip()
            withdrawal.save(update_fields=["state", "reason", "updated_at"])
            return_withdrawal(withdrawal, actor=request.staff_account, reason=withdrawal.reason)

        withdrawal.refresh_from_db()
        record_audit(
            request=request,
            actor=request.staff_account,
            action=f"WITHDRAWAL_{action.upper()}",
            target_type="merchant_withdrawal",
            target_id=str(withdrawal.public_id),
            reason=(payload.get("reason") or "").strip(),
            before_state=before,
            after_state={"state": withdrawal.state, "fee": str(withdrawal.fee)},
            tenant_type="merchant",
            tenant_id=str(withdrawal.merchant.public_id),
        )
        return Response({"withdrawal": _withdrawal_payload(withdrawal)})


class AdminWalletRechargeView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["finance.manage"]
    view_permissions = ["finance.view"]

    def post(self, request):
        payload = request.data or {}
        merchant = _resolve_merchant(require(payload, "merchant_id", label="商家"))
        amount = parse_amount(require(payload, "amount", label="充值金额"), field="充值金额")
        entry = recharge_wallet(
            merchant,
            amount=amount,
            actor=request.staff_account,
            note=(payload.get("note") or "").strip() or "平台充值",
        )
        record_audit(
            request=request,
            actor=request.staff_account,
            action="WALLET_RECHARGED",
            target_type="merchant",
            target_id=str(merchant.public_id),
            reason="",
            before_state={"wallet_balance": money_str(entry.balance_before)},
            after_state={"wallet_balance": money_str(entry.balance_after)},
            tenant_type="merchant",
            tenant_id=str(merchant.public_id),
        )
        return Response({"entry": _ledger_payload(entry)}, status=201)


class AdminWalletLedgerView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["finance.manage"]
    view_permissions = ["finance.view"]

    def get(self, request):
        queryset = MerchantWalletEntry.objects.select_related("merchant", "order")
        kind = (request.query_params.get("kind") or "").strip().upper()
        if kind and kind != "ALL":
            queryset = queryset.filter(kind=kind)
        merchant_id = (request.query_params.get("merchant") or "").strip()
        if merchant_id:
            queryset = queryset.filter(merchant__public_id=merchant_id)
        rows, meta = paginate(queryset.order_by("-occurred_at", "-pk"), request)
        return Response({"items": [_ledger_payload(row) for row in rows], **meta})


class AdminWalletLedgerExportView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["finance.manage"]
    view_permissions = ["finance.view"]

    def get(self, request):
        queryset = MerchantWalletEntry.objects.select_related("merchant").order_by(
            "-occurred_at", "-pk"
        )[:2000]
        rows = [
            [
                payload["id"],
                payload["merchant"]["name"],
                payload["kind"],
                payload["amount"],
                payload["balance_before"],
                payload["balance_after"],
                payload["note"],
                payload["occurred_at"],
            ]
            for payload in (_ledger_payload(entry) for entry in queryset)
        ]
        return csv_response(
            "wallet-ledger.csv",
            ["业务单号", "商家", "类型", "金额", "变动前", "变动后", "备注", "发生时间"],
            rows,
        )


class AdminMerchantPickerView(OpsAPIView):
    """充值/保证金表单的搜索选择框数据源。"""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["finance.manage"]
    view_permissions = ["finance.view"]

    def get(self, request):
        query = (request.query_params.get("q") or "").strip()
        queryset = Merchant.objects.exclude(onboarding_status=Merchant.OnboardingStatus.DRAFT)
        if query:
            queryset = queryset.filter(Q(display_name__icontains=query) | Q(slug__icontains=query))
        rows = queryset.order_by("-created_at")[:20]
        return Response(
            {
                "items": [
                    {
                        "id": str(merchant.public_id),
                        "name": merchant.display_name,
                        "status": merchant.onboarding_status,
                        "wallet_balance": money_str(merchant.wallet_balance),
                        "deposit_enabled": merchant.deposit_enabled,
                        "deposit_balance": money_str(merchant.deposit_balance),
                    }
                    for merchant in rows
                ]
            }
        )


# --------------------------------------------------------------------------
# A07 保证金
# --------------------------------------------------------------------------


def _deposit_payload(merchant: Merchant) -> dict:
    required = merchant.deposit_required or Decimal("0")
    pending = max(Decimal("0"), required - merchant.deposit_balance)
    return {
        "id": str(merchant.public_id),
        "name": merchant.display_name,
        "status": merchant.onboarding_status,
        "deposit_enabled": merchant.deposit_enabled,
        "required_amount": money_str(required) if merchant.deposit_enabled else None,
        "balance": money_str(merchant.deposit_balance),
        "pending_amount": money_str(pending) if merchant.deposit_enabled else None,
        "initial_paid": merchant.deposit_initial_paid,
    }


class AdminDepositsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["deposits.manage"]
    view_permissions = ["deposits.view"]

    def get(self, request):
        queryset = Merchant.objects.filter(deposit_enabled=True)
        query = (request.query_params.get("q") or "").strip()
        if query:
            queryset = queryset.filter(Q(display_name__icontains=query) | Q(slug__icontains=query))
        rows, meta = paginate(queryset.order_by("-created_at"), request)
        return Response({"items": [_deposit_payload(row) for row in rows], **meta})


class AdminDepositActionsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["deposits.manage"]
    view_permissions = ["deposits.view"]

    def post(self, request, public_id):
        merchant = Merchant.objects.filter(public_id=public_id).first()
        if merchant is None:
            raise StaffApiError(
                business_code="MERCHANT_NOT_FOUND", message="商家不存在。", status_code=404
            )
        payload = request.data or {}
        action = (payload.get("action") or "").strip().lower()
        before = {"deposit_balance": money_str(merchant.deposit_balance)}

        if action == "recharge":
            amount = parse_amount(require(payload, "amount", label="充值金额"), field="充值金额")
            entry = recharge_deposit(merchant, amount=amount, actor=request.staff_account)
        elif action == "adjust":
            target = parse_amount(
                require(payload, "balance", label="调整后保证金余额"), field="保证金余额"
            )
            entry = adjust_deposit(merchant, target_balance=target, actor=request.staff_account)
        else:
            raise StaffApiError(
                business_code="ACTION_UNSUPPORTED", message="不支持的操作。", status_code=400
            )

        merchant.refresh_from_db()
        record_audit(
            request=request,
            actor=request.staff_account,
            action=f"DEPOSIT_{action.upper()}",
            target_type="merchant",
            target_id=str(merchant.public_id),
            reason="",
            before_state=before,
            after_state={"deposit_balance": money_str(merchant.deposit_balance)},
            tenant_type="merchant",
            tenant_id=str(merchant.public_id),
        )
        return Response(
            {
                "deposit": _deposit_payload(merchant),
                "entry": {
                    "id": str(entry.public_id),
                    "kind": entry.kind,
                    "amount": money_str(entry.amount),
                    "balance_after": money_str(entry.balance_after),
                },
            }
        )


class AdminDepositEntriesView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["deposits.manage"]
    view_permissions = ["deposits.view"]

    def get(self, request, public_id):
        merchant = Merchant.objects.filter(public_id=public_id).first()
        if merchant is None:
            raise StaffApiError(
                business_code="MERCHANT_NOT_FOUND", message="商家不存在。", status_code=404
            )
        rows, meta = paginate(
            MerchantDepositEntry.objects.filter(merchant=merchant).order_by("-occurred_at", "-pk"),
            request,
        )
        return Response(
            {
                "items": [
                    {
                        "id": str(entry.public_id),
                        "kind": entry.kind,
                        "amount": money_str(entry.amount),
                        "balance_before": money_str(entry.balance_before),
                        "balance_after": money_str(entry.balance_after),
                        "related_id": entry.related_id,
                        "note": entry.note,
                        "occurred_at": iso(entry.occurred_at),
                    }
                    for entry in rows
                ],
                **meta,
            }
        )


def _resolve_merchant(value) -> Merchant:
    merchant = Merchant.objects.filter(public_id=value).first() if value else None
    if merchant is None:
        raise StaffApiError(
            business_code="MERCHANT_NOT_FOUND", message="商家不存在。", status_code=404
        )
    return merchant
