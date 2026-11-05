"""商家端 M05 钱包管理 / M06 保证金管理。

钱包沿用 ``merchant_wallet_entry`` 统一资金明细（充值、提现、订单发货、
订单回款、推荐返佣、余额调整都在同一张表），保证金余额存在
``merchant.deposit_balance``，流水在 ``merchant_deposit_entry``。

提现不能自己加余额（充值必须联系客服），商家只能提现、改密码、看明细。
"""

from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework.response import Response

from accounts_staff.api_exceptions import StaffApiError
from audit.services import record_audit
from merchant_ops.api_utils import csv_response, iso, money_str, paginate
from merchant_ops.merchant_context import MerchantAPIView
from merchant_ops.models import (
    MerchantDepositEntry,
    MerchantWalletEntry,
    MerchantWithdrawal,
)
from merchant_ops.services import MerchantOpsError, request_withdrawal, set_wallet_password

LEDGER_KINDS = (
    MerchantWalletEntry.Kind.RECHARGE,
    MerchantWalletEntry.Kind.WITHDRAWAL,
    MerchantWalletEntry.Kind.ORDER_SHIPPING,
    MerchantWalletEntry.Kind.ORDER_SETTLEMENT,
    MerchantWalletEntry.Kind.REFERRAL_COMMISSION,
    MerchantWalletEntry.Kind.ADJUSTMENT,
)


def _order_snapshot(entry: MerchantWalletEntry) -> dict | None:
    """订单类流水带上商品财务快照，商家能对上「这笔钱怎么算出来的」。"""

    if not entry.order_id:
        return None
    order = entry.order
    item = order.items.first()
    return {
        "order_id": str(order.public_id),
        "title": item.title if item else "",
        "quantity": item.quantity if item else 0,
        "unit_cost": money_str(item.unit_cost) if item and item.unit_cost is not None else None,
        "unit_price": money_str(item.unit_price) if item else None,
        "cost_total": money_str(order.cost_total),
        "items_total": money_str(order.items_total),
        "profit": money_str(order.items_total - order.cost_total),
        # 发货时是预估，回款后才是真实盈利。
        "profit_label": (
            "回款后预估盈利" if entry.kind == MerchantWalletEntry.Kind.ORDER_SHIPPING else "盈利"
        ),
    }


def _ledger_payload(entry: MerchantWalletEntry) -> dict:
    return {
        "id": str(entry.public_id),
        "kind": entry.kind,
        "state": entry.state,
        "currency": entry.currency,
        "amount": money_str(entry.amount),
        "balance_before": money_str(entry.balance_before),
        "balance_after": money_str(entry.balance_after),
        "order_id": str(entry.order.public_id) if entry.order_id else None,
        "withdrawal_id": str(entry.withdrawal.public_id) if entry.withdrawal_id else None,
        "note": entry.note,
        "occurred_at": iso(entry.occurred_at),
        "order_snapshot": _order_snapshot(entry),
    }


def _withdrawal_payload(withdrawal: MerchantWithdrawal) -> dict:
    return {
        "id": str(withdrawal.public_id),
        "method": withdrawal.method,
        "currency": withdrawal.currency,
        "amount": money_str(withdrawal.amount),
        "fee": money_str(withdrawal.fee),
        "net_amount": money_str(withdrawal.net_amount or (withdrawal.amount - withdrawal.fee)),
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
        "history": _withdrawal_history(withdrawal),
    }


def _withdrawal_history(withdrawal: MerchantWithdrawal) -> list:
    """处理过程：提交 → 审核 → 转账 → 到账，只列已发生的动作。"""

    events = [{"action": "提交申请", "at": iso(withdrawal.created_at), "note": ""}]
    if withdrawal.approved_at:
        events.append({"action": "审核通过", "at": iso(withdrawal.approved_at), "note": ""})
    if withdrawal.state == MerchantWithdrawal.State.TRANSFERRING:
        events.append(
            {"action": "转账中", "at": iso(withdrawal.updated_at), "note": withdrawal.reference}
        )
    if withdrawal.state == MerchantWithdrawal.State.PAID:
        events.append(
            {
                "action": "已到账",
                "at": iso(withdrawal.paid_at or withdrawal.updated_at),
                "note": withdrawal.reference,
            }
        )
    if withdrawal.state in (MerchantWithdrawal.State.REJECTED, MerchantWithdrawal.State.FAILED):
        events.append(
            {
                "action": "已打回"
                if withdrawal.state == MerchantWithdrawal.State.REJECTED
                else "转账失败",
                "at": iso(withdrawal.updated_at),
                "note": withdrawal.reason,
            }
        )
    return events


def _ledger_queryset(request):
    queryset = MerchantWalletEntry.objects.select_related("order", "withdrawal").filter(
        merchant=request.merchant
    )
    kind = (request.query_params.get("kind") or "").strip().upper()
    if kind and kind != "ALL" and kind in LEDGER_KINDS:
        queryset = queryset.filter(kind=kind)
    start = (request.query_params.get("start") or "").strip()
    end = (request.query_params.get("end") or "").strip()
    if start:
        queryset = queryset.filter(occurred_at__date__gte=start[:10])
    if end:
        queryset = queryset.filter(occurred_at__date__lte=end[:10])
    return queryset.order_by("-occurred_at", "-pk")


class MerchantWalletView(MerchantAPIView):
    permission_any = ("merchant.wallet.manage",)

    def get(self, request):
        merchant = request.merchant
        entries, meta = paginate(_ledger_queryset(request), request)
        withdrawals = MerchantWithdrawal.objects.filter(merchant=merchant).order_by("-created_at")[
            :5
        ]
        totals = _ledger_queryset(request).aggregate(
            income=Sum("amount", filter=Q(amount__gt=0)),
            expense=Sum("amount", filter=Q(amount__lt=0)),
        )
        return Response(
            {
                "balance": money_str(merchant.wallet_balance),
                "deposit_balance": money_str(merchant.deposit_balance),
                "currency": merchant.currency,
                "wallet_password_configured": bool(merchant.wallet_password_hash),
                "wallet_password_locked_until": iso(merchant.wallet_password_locked_until),
                "totals": {
                    "income": money_str(totals["income"]),
                    # 支出合计按绝对值展示，符号由明细行的正负表达。
                    "expense": money_str(abs(totals["expense"] or 0)),
                },
                "entries": [_ledger_payload(entry) for entry in entries],
                "withdrawals": [_withdrawal_payload(item) for item in withdrawals],
                **meta,
            }
        )


class MerchantWalletEntriesView(MerchantAPIView):
    permission_any = ("merchant.wallet.manage",)

    def get(self, request):
        rows, meta = paginate(_ledger_queryset(request), request)
        return Response({"items": [_ledger_payload(entry) for entry in rows], **meta})


class MerchantWalletExportView(MerchantAPIView):
    permission_any = ("merchant.wallet.manage",)

    def get(self, request):
        entries = list(_ledger_queryset(request)[:5000])
        rows = [
            [
                str(entry.public_id),
                timezone.localtime(entry.occurred_at).strftime("%Y-%m-%d %H:%M"),
                entry.get_kind_display(),
                money_str(entry.amount),
                money_str(entry.balance_before),
                money_str(entry.balance_after),
                str(entry.order.public_id) if entry.order_id else "",
                entry.note,
            ]
            for entry in entries
        ]
        return csv_response(
            "merchant-wallet.csv",
            [
                "业务单号",
                "发生时间",
                "业务类型",
                "金额",
                "变动前余额",
                "变动后余额",
                "关联订单",
                "说明",
            ],
            rows,
        )


class MerchantWalletPasswordView(MerchantAPIView):
    permission_any = ("merchant.wallet.manage",)

    def post(self, request):
        payload = request.data or {}
        try:
            merchant = set_wallet_password(
                request.merchant,
                new_password=payload.get("new_password"),
                confirm_password=payload.get("confirm_password"),
                old_password=payload.get("old_password"),
            )
        except MerchantOpsError as exc:
            raise StaffApiError(
                business_code=exc.code, message=exc.message, status_code=exc.status_code
            ) from exc
        record_audit(
            request=request,
            actor=request.staff_account,
            action="MERCHANT_WALLET_PASSWORD_SET",
            target_type="merchant",
            target_id=str(merchant.public_id),
            reason="",
            before_state={},
            after_state={"configured": True},
            tenant_type="MERCHANT",
            tenant_id=str(merchant.public_id),
        )
        return Response({"wallet_password_configured": True})


class MerchantWithdrawalsView(MerchantAPIView):
    permission_any = ("merchant.wallet.manage",)

    def get(self, request):
        queryset = MerchantWithdrawal.objects.filter(merchant=request.merchant).order_by(
            "-created_at", "-pk"
        )
        rows, meta = paginate(queryset, request)
        return Response({"items": [_withdrawal_payload(item) for item in rows], **meta})

    def post(self, request):
        payload = request.data or {}
        try:
            withdrawal = request_withdrawal(
                request.merchant,
                method=str(payload.get("method") or "").strip().upper(),
                amount=payload.get("amount"),
                wallet_password=payload.get("wallet_password"),
                bank=payload.get("bank") if isinstance(payload.get("bank"), dict) else None,
                chain=payload.get("chain") if isinstance(payload.get("chain"), dict) else None,
                actor=request.staff_account,
            )
        except MerchantOpsError as exc:
            raise StaffApiError(
                business_code=exc.code, message=exc.message, status_code=exc.status_code
            ) from exc
        record_audit(
            request=request,
            actor=request.staff_account,
            action="MERCHANT_WITHDRAWAL_REQUESTED",
            target_type="merchant_withdrawal",
            target_id=str(withdrawal.public_id),
            reason="",
            before_state={},
            after_state={"amount": str(withdrawal.amount), "method": withdrawal.method},
            tenant_type="MERCHANT",
            tenant_id=str(request.merchant.public_id),
        )
        return Response({"withdrawal": _withdrawal_payload(withdrawal)}, status=201)


class MerchantWithdrawalDetailView(MerchantAPIView):
    permission_any = ("merchant.wallet.manage",)

    def get(self, request, public_id):
        withdrawal = MerchantWithdrawal.objects.filter(
            merchant=request.merchant, public_id=public_id
        ).first()
        if withdrawal is None:
            raise StaffApiError(
                business_code="WITHDRAWAL_NOT_FOUND", message="提现申请不存在。", status_code=404
            )
        return Response({"withdrawal": _withdrawal_payload(withdrawal)})


# --------------------------------------------------------------------------
# M06 保证金
# --------------------------------------------------------------------------


def _deposit_payload(merchant) -> dict:
    required = merchant.deposit_required or 0
    balance = merchant.deposit_balance
    pending = max(required - balance, 0) if merchant.deposit_enabled else 0
    return {
        "enabled": merchant.deposit_enabled,
        "required": money_str(required),
        "balance": money_str(balance),
        "pending": money_str(pending),
        "initial_paid": merchant.deposit_initial_paid,
        "status": "PAID" if pending <= 0 else "PENDING",
        "currency": merchant.currency,
    }


class MerchantDepositView(MerchantAPIView):
    permission_any = ("merchant.deposit.view",)

    def get(self, request):
        merchant = request.merchant
        if not merchant.deposit_enabled:
            # 未启用保证金的商家看不到这个模块，直接返回空结构而不是 403，
            # 避免前端菜单刚隐藏时旧页面报错。
            return Response(
                {
                    "deposit": {
                        "enabled": False,
                        "required": "0.00",
                        "balance": "0.00",
                        "pending": "0.00",
                        "initial_paid": True,
                        "status": "EXEMPT",
                        "currency": merchant.currency,
                    },
                    "items": [],
                    "total": 0,
                }
            )
        entries = MerchantDepositEntry.objects.filter(merchant=merchant).order_by(
            "-occurred_at", "-pk"
        )
        rows, meta = paginate(entries, request)
        return Response(
            {
                "deposit": _deposit_payload(merchant),
                "items": [
                    {
                        "id": str(entry.public_id),
                        "kind": entry.kind,
                        "kind_label": entry.get_kind_display(),
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
