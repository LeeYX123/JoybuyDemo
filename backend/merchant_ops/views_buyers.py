"""A13 用户端管理 / A14 白名单账号。"""

from django.db.models import Q
from rest_framework.response import Response

from accounts_buyers.models import BuyerAccount, BuyerWalletEntry
from accounts_buyers.services import adjust_buyer_balance, recharge_buyer
from accounts_staff.api_exceptions import StaffApiError
from accounts_staff.permissions import StaffRbacPermission
from audit.services import record_audit
from merchant_ops.api_utils import OpsAPIView, iso, money_str, paginate, parse_amount, require

# 已开放地区（正式应改为可配置的地区策略表；开发期先给默认集合）。
OPEN_REGIONS = {"GB", "CN", "HK", "US"}


def _buyer_payload(account: BuyerAccount) -> dict:
    return {
        "id": str(account.public_id),
        "account": account.email or account.phone_e164 or "",
        "email": account.email,
        "phone": account.phone_e164,
        "name": account.email or account.phone_e164 or "买家",
        "region": account.region,
        "region_open": (account.region or "") in OPEN_REGIONS if account.region else True,
        "enabled": account.status == BuyerAccount.Status.ACTIVE,
        "whitelisted": account.purchase_whitelisted,
        "balance": money_str(account.balance),
        "joined_at": iso(account.created_at),
        "last_online_at": iso(account.last_login_at),
        "checkout_allowed": account.status == BuyerAccount.Status.ACTIVE
        and ((account.region or "") in OPEN_REGIONS or account.purchase_whitelisted),
        "balance_pay_allowed": account.status == BuyerAccount.Status.ACTIVE
        and account.purchase_whitelisted,
    }


def _ledger_payload(entry: BuyerWalletEntry) -> dict:
    return {
        "id": str(entry.public_id),
        "kind": entry.kind,
        "amount": money_str(entry.amount),
        "balance_before": money_str(entry.balance_before),
        "balance_after": money_str(entry.balance_after),
        "order_id": str(entry.order.public_id) if entry.order_id else None,
        "operator": entry.operator_label,
        "note": entry.note,
        "occurred_at": iso(entry.occurred_at),
    }


class AdminBuyersView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["buyers.manage"]
    view_permissions = ["buyers.view", "whitelist.view"]

    def get(self, request):
        queryset = BuyerAccount.objects.all()
        whitelisted = (request.query_params.get("whitelisted") or "").strip()
        if whitelisted in {"1", "true"}:
            queryset = queryset.filter(purchase_whitelisted=True)
        elif whitelisted in {"0", "false"}:
            queryset = queryset.filter(purchase_whitelisted=False)
        status_filter = (request.query_params.get("status") or "").strip().upper()
        if status_filter in {"ACTIVE", "DISABLED"}:
            queryset = queryset.filter(status=status_filter)
        query = (request.query_params.get("q") or "").strip()
        if query:
            condition = Q(email__icontains=query) | Q(phone_e164__icontains=query)
            try:
                import uuid as uuid_module

                condition |= Q(public_id=uuid_module.UUID(query))
            except ValueError:
                pass
            queryset = queryset.filter(condition)
        rows, meta = paginate(queryset.order_by("-created_at", "-pk"), request)
        return Response({"items": [_buyer_payload(row) for row in rows], **meta})


class AdminBuyerDetailView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["buyers.manage"]
    view_permissions = ["buyers.view", "whitelist.view"]

    def _get(self, public_id):
        account = BuyerAccount.objects.filter(public_id=public_id).first()
        if account is None:
            raise StaffApiError(
                business_code="BUYER_NOT_FOUND", message="买家账号不存在。", status_code=404
            )
        return account

    def get(self, request, public_id):
        account = self._get(public_id)
        payload = _buyer_payload(account)
        entries = BuyerWalletEntry.objects.filter(account=account).select_related("order")[:50]
        payload["ledger"] = [_ledger_payload(entry) for entry in entries]
        return Response({"buyer": payload})


class AdminBuyerProfileView(OpsAPIView):
    """启用/停用、改地区——不涉及资金，归「用户端管理」。"""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["buyers.manage"]

    def post(self, request, public_id):
        account = BuyerAccount.objects.filter(public_id=public_id).first()
        if account is None:
            raise StaffApiError(
                business_code="BUYER_NOT_FOUND", message="买家账号不存在。", status_code=404
            )
        payload = request.data or {}
        action = (payload.get("action") or "").strip().lower()
        before = {"status": account.status, "region": account.region}

        if action == "enable":
            account.status = BuyerAccount.Status.ACTIVE
            account.disabled_at = None
            account.disabled_reason = ""
        elif action == "disable":
            account.status = BuyerAccount.Status.DISABLED
            from django.utils import timezone

            account.disabled_at = timezone.now()
            account.disabled_reason = (payload.get("reason") or "").strip()[:255]
        elif action == "set_region":
            account.region = (payload.get("region") or "").strip()[:32]
        else:
            raise StaffApiError(
                business_code="ACTION_UNSUPPORTED", message="不支持的操作。", status_code=400
            )
        account.save()
        record_audit(
            request=request,
            actor=request.staff_account,
            action=f"BUYER_{action.upper()}",
            target_type="buyer_account",
            target_id=str(account.public_id),
            reason=(payload.get("reason") or "")[:255],
            before_state=before,
            after_state={"status": account.status, "region": account.region},
            tenant_type="buyer",
            tenant_id=str(account.public_id),
        )
        return Response({"buyer": _buyer_payload(account)})


class AdminBuyerWhitelistView(OpsAPIView):
    """加入/移出白名单 + 余额充值与调整（A14）。"""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["whitelist.manage"]

    def post(self, request, public_id):
        account = BuyerAccount.objects.filter(public_id=public_id).first()
        if account is None:
            raise StaffApiError(
                business_code="BUYER_NOT_FOUND", message="买家账号不存在。", status_code=404
            )
        payload = request.data or {}
        action = (payload.get("action") or "").strip().lower()
        before = {
            "whitelisted": account.purchase_whitelisted,
            "balance": money_str(account.balance),
        }

        if action == "add":
            if account.status != BuyerAccount.Status.ACTIVE:
                raise StaffApiError(
                    business_code="BUYER_DISABLED",
                    message="账号已停用，不能加入白名单。",
                    status_code=400,
                )
            account.purchase_whitelisted = True
            account.save(update_fields=["purchase_whitelisted", "updated_at"])
            entry = None
        elif action == "remove":
            # 移出白名单只取消权限，余额与历史保留。
            account.purchase_whitelisted = False
            account.save(update_fields=["purchase_whitelisted", "updated_at"])
            entry = None
        elif action == "recharge":
            amount = parse_amount(require(payload, "amount", label="充值金额"), field="充值金额")
            entry = recharge_buyer(
                account,
                amount=amount,
                operator_label=request.staff_account.display_name,
                note=(payload.get("note") or "").strip(),
            )
        elif action == "adjust":
            target = parse_amount(require(payload, "balance", label="调整后余额"), field="余额")
            entry = adjust_buyer_balance(
                account,
                target_balance=target,
                operator_label=request.staff_account.display_name,
                note=(payload.get("note") or "").strip(),
            )
        else:
            raise StaffApiError(
                business_code="ACTION_UNSUPPORTED", message="不支持的操作。", status_code=400
            )

        account.refresh_from_db()
        record_audit(
            request=request,
            actor=request.staff_account,
            action=f"WHITELIST_{action.upper()}",
            target_type="buyer_account",
            target_id=str(account.public_id),
            reason="",
            before_state=before,
            after_state={
                "whitelisted": account.purchase_whitelisted,
                "balance": money_str(account.balance),
            },
            tenant_type="buyer",
            tenant_id=str(account.public_id),
        )
        return Response(
            {
                "buyer": _buyer_payload(account),
                "entry": _ledger_payload(entry) if entry else None,
            }
        )


class AdminBuyerLookupView(OpsAPIView):
    """白名单页的「搜索已注册用户」输入框。"""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["whitelist.manage"]
    view_permissions = ["whitelist.view"]

    def get(self, request):
        query = (request.query_params.get("q") or "").strip()
        queryset = BuyerAccount.objects.all()
        if query:
            queryset = queryset.filter(Q(email__icontains=query) | Q(phone_e164__icontains=query))
        return Response(
            {
                "items": [
                    {
                        "id": str(account.public_id),
                        "account": account.email or account.phone_e164 or "",
                        "whitelisted": account.purchase_whitelisted,
                        "enabled": account.status == BuyerAccount.Status.ACTIVE,
                        "balance": money_str(account.balance),
                    }
                    for account in queryset.order_by("-created_at")[:20]
                ]
            }
        )
