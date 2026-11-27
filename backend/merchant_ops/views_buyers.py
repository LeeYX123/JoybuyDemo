"""A13 用户端管理 / A14 白名单账号。"""

import secrets
import string

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.response import Response

from accounts_buyers.models import BuyerAccount, BuyerSession, BuyerWalletEntry
from accounts_buyers.normalization import normalize_email, normalize_phone
from accounts_buyers.services import adjust_buyer_balance, recharge_buyer
from accounts_staff.api_exceptions import StaffApiError
from accounts_staff.permissions import StaffRbacPermission
from audit.services import record_audit
from merchant_ops.api_utils import OpsAPIView, iso, money_str, paginate, parse_amount, require

# 已开放地区（正式应改为可配置的地区策略表；开发期先给默认集合）。
OPEN_REGIONS = {"GB", "CN", "HK", "US"}

DISPLAY_NAME_MAX_LENGTH = 32
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 64


def _buyer_payload(account: BuyerAccount) -> dict:
    return {
        "id": str(account.public_id),
        "account": account.email or account.phone_e164 or "",
        "email": account.email,
        "phone": account.phone_e164,
        # 批次 CA：用户名（购物端展示昵称；不唯一，仅用于展示与搜索）。
        "display_name": account.display_name,
        "name": account.email or account.phone_e164 or "买家",
        # 迭代02：登录渠道（Facebook / Google / 邮箱）。
        "auth_provider": account.auth_provider or BuyerAccount.AuthProvider.EMAIL,
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
        # 2026-11-27 管理端【编辑】：支付权限改为真实字段（原硬编码假值）。
        # 语义 = 是否允许下单支付；与白名单独立，关闭后 place_order 抛 PAYMENT_DISABLED。
        "payment_enabled": account.payment_enabled,
        "payment_permission": "允许" if account.payment_enabled else "已关闭",
    }


def _buyer_snapshot(account: BuyerAccount) -> dict:
    """审计用 before/after 快照；不包含密码哈希。"""

    return {
        "display_name": account.display_name,
        "email": account.email,
        "phone_e164": account.phone_e164,
        "status": account.status,
        "purchase_whitelisted": account.purchase_whitelisted,
        "payment_enabled": account.payment_enabled,
        "balance": money_str(account.balance),
        "disabled_at": iso(account.disabled_at),
    }


def _parse_bool(value, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", ""}:
            return False
    raise StaffApiError(
        business_code="BOOLEAN_INVALID",
        message=f"{field}必须是布尔值。",
        status_code=400,
    )


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
            # 批次 CA：用户名（display_name）也参与模糊搜索，与邮箱/电话并列（OR）。
            # 用户名不唯一（购物端设置昵称不做唯一校验），命中多条属预期。
            condition = (
                Q(email__icontains=query)
                | Q(phone_e164__icontains=query)
                | Q(display_name__icontains=query)
            )
            # 2026-11-27 全站编号改造：用户编号 JYU+10 位字符串。
            condition |= Q(public_id__iexact=query)
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


class AdminBuyerEditView(OpsAPIView):
    """用户端管理【编辑】——一次原子保存资料 / 支付权限 / 白名单 / 余额（2026-11-27）。

    RBAC 组合：资料与状态归 ``buyers.manage``；一旦入参带 ``balance`` 或
    ``purchase_whitelisted``，额外要求 ``whitelist.manage``（沿用项目「资金/白名单
    单独授权」口径，与 AdminBuyerWhitelistView 一致）。权限在
    ``resolve_required_permissions`` 里按入参动态判定，只给 buyers.manage 的账号
    仍可改用户名/邮箱/手机号/状态/支付权限，但动不了余额与白名单。
    """

    permission_classes = [StaffRbacPermission]
    required_permissions = ["buyers.manage"]

    def resolve_required_permissions(self, request):
        required = ["buyers.manage"]
        payload = getattr(request, "data", None) or {}
        if "balance" in payload or "purchase_whitelisted" in payload:
            required.append("whitelist.manage")
        return required

    def post(self, request, public_id):
        account = BuyerAccount.objects.filter(public_id=public_id).first()
        if account is None:
            raise StaffApiError(
                business_code="BUYER_NOT_FOUND", message="买家账号不存在。", status_code=404
            )
        payload = request.data or {}
        note = str(payload.get("note") or "").strip()[:255]

        with transaction.atomic():
            # 行锁：余额调整与资料保存同一事务，避免并发改同一买家时互相覆盖。
            account = BuyerAccount.objects.select_for_update().get(pk=account.pk)
            before = _buyer_snapshot(account)

            # ---- 1) 先做全部校验与目标值计算，任何一步失败都不落库 ----
            changes: dict = {}
            if "display_name" in payload:
                raw = payload.get("display_name")
                display_name = "" if raw is None else str(raw).strip()
                if len(display_name) > DISPLAY_NAME_MAX_LENGTH:
                    raise StaffApiError(
                        business_code="DISPLAY_NAME_TOO_LONG",
                        message=f"用户名不能超过 {DISPLAY_NAME_MAX_LENGTH} 个字符。",
                        status_code=400,
                    )
                changes["display_name"] = display_name

            if "email" in payload:
                raw = payload.get("email")
                raw_email = "" if raw is None else str(raw).strip()
                if not raw_email:
                    changes["email"] = None
                else:
                    try:
                        email = normalize_email(raw_email)
                    except ValidationError as exc:
                        raise StaffApiError(
                            business_code="EMAIL_INVALID",
                            message="邮箱格式不正确。",
                            status_code=400,
                        ) from exc
                    if BuyerAccount.objects.filter(email=email).exclude(pk=account.pk).exists():
                        raise StaffApiError(
                            business_code="EMAIL_TAKEN",
                            message="该邮箱已被其他账号使用。",
                            status_code=400,
                        )
                    changes["email"] = email

            if "phone_e164" in payload:
                raw = payload.get("phone_e164")
                raw_phone = "" if raw is None else str(raw).strip()
                if not raw_phone:
                    changes["phone_e164"] = None
                else:
                    try:
                        phone = normalize_phone(raw_phone)
                    except ValidationError as exc:
                        raise StaffApiError(
                            business_code="PHONE_INVALID",
                            message="手机号必须是国际格式（含国家码，如 +447700900123）。",
                            status_code=400,
                        ) from exc
                    if (
                        BuyerAccount.objects.filter(phone_e164=phone)
                        .exclude(pk=account.pk)
                        .exists()
                    ):
                        raise StaffApiError(
                            business_code="PHONE_TAKEN",
                            message="该手机号已被其他账号使用。",
                            status_code=400,
                        )
                    changes["phone_e164"] = phone

            # 账号标识不变量（与 DB 约束 buyer_account_has_identifier 一致）：
            # 邮箱/手机号改后至少留一个，或该账号已绑定三方身份。
            final_email = changes.get("email", account.email)
            final_phone = changes.get("phone_e164", account.phone_e164)
            if not final_email and not final_phone and not account.identity_bound:
                raise StaffApiError(
                    business_code="BUYER_IDENTIFIER_REQUIRED",
                    message="邮箱和手机号至少保留一项，否则该账号将无法登录。",
                    status_code=400,
                )

            new_status = account.status
            if "status" in payload:
                status = str(payload.get("status") or "").strip().upper()
                if status not in BuyerAccount.Status.values:
                    raise StaffApiError(
                        business_code="BUYER_STATUS_INVALID",
                        message="状态只能是启用或停用。",
                        status_code=400,
                    )
                new_status = status

            new_whitelisted = account.purchase_whitelisted
            if "purchase_whitelisted" in payload:
                new_whitelisted = _parse_bool(payload.get("purchase_whitelisted"), field="白名单")
                # 与 AdminBuyerWhitelistView 的 add 同口径：停用账号不能进白名单。
                if new_whitelisted and new_status != BuyerAccount.Status.ACTIVE:
                    raise StaffApiError(
                        business_code="BUYER_DISABLED",
                        message="账号已停用，不能加入白名单。",
                        status_code=400,
                    )

            new_payment_enabled = account.payment_enabled
            if "payment_enabled" in payload:
                new_payment_enabled = _parse_bool(payload.get("payment_enabled"), field="支付权限")

            target_balance = None
            if "balance" in payload:
                target_balance = parse_amount(payload.get("balance"), field="余额")
                if target_balance < 0:
                    raise StaffApiError(
                        business_code="BALANCE_NEGATIVE",
                        message="余额不能为负。",
                        status_code=400,
                    )

            # ---- 2) 余额走 adjust_buyer_balance（写台账），再保存其余字段 ----
            entry = None
            if target_balance is not None and target_balance != account.balance:
                entry = adjust_buyer_balance(
                    account,
                    target_balance=target_balance,
                    operator_label=request.staff_account.display_name,
                    note=note or "管理端编辑资料时调整余额",
                )
                account.refresh_from_db()

            for field, value in changes.items():
                setattr(account, field, value)
            if new_status == BuyerAccount.Status.DISABLED:
                # 停用补 disabled_at（已有则保留原时间）；备注作为停用原因留痕。
                if account.disabled_at is None:
                    account.disabled_at = timezone.now()
                if note:
                    account.disabled_reason = note
            else:
                account.disabled_at = None
                account.disabled_reason = ""
            account.status = new_status
            account.purchase_whitelisted = new_whitelisted
            account.payment_enabled = new_payment_enabled
            account.save()

            after = _buyer_snapshot(account)
            if before != after:
                record_audit(
                    request=request,
                    actor=request.staff_account,
                    action="BUYER_EDIT",
                    target_type="buyer_account",
                    target_id=str(account.public_id),
                    reason=note,
                    before_state=before,
                    after_state=after,
                    tenant_type="buyer",
                    tenant_id=str(account.public_id),
                )

        return Response(
            {
                "buyer": _buyer_payload(account),
                "entry": _ledger_payload(entry) if entry else None,
            }
        )


def _generate_password(length: int = 16) -> str:
    """强随机临时密码：大小写字母 + 数字（不含易混字符不额外处理，长度即强度）。"""

    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class AdminBuyerResetPasswordView(OpsAPIView):
    """重设买家密码（2026-11-27）。明文只在本次响应里出现，审计只记「已重设」。"""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["buyers.manage"]

    def post(self, request, public_id):
        account = BuyerAccount.objects.filter(public_id=public_id).first()
        if account is None:
            raise StaffApiError(
                business_code="BUYER_NOT_FOUND", message="买家账号不存在。", status_code=404
            )
        payload = request.data or {}
        note = str(payload.get("note") or "").strip()[:255]
        generate = _parse_bool(payload.get("generate", False), field="自动生成")

        if generate:
            password = _generate_password()
        else:
            password = str(payload.get("password") or "")
            if len(password) < PASSWORD_MIN_LENGTH:
                raise StaffApiError(
                    business_code="PASSWORD_TOO_SHORT",
                    message=f"密码至少 {PASSWORD_MIN_LENGTH} 位。",
                    status_code=400,
                )
            if len(password) > PASSWORD_MAX_LENGTH:
                raise StaffApiError(
                    business_code="PASSWORD_TOO_LONG",
                    message=f"密码不能超过 {PASSWORD_MAX_LENGTH} 位。",
                    status_code=400,
                )

        with transaction.atomic():
            account = BuyerAccount.objects.select_for_update().get(pk=account.pk)
            account.set_password(password)
            account.save(update_fields=["password", "updated_at"])
            # 会话失效：本项目买家登录态是 DB 里的 BuyerSession 行（cookie 里是
            # 随机 token，库里只存其 HMAC 摘要）。resolve_buyer_session 要求
            # revoked_at 为空，因此把该账号所有未撤销会话批量置 revoked_at 即可
            # 让所有已登录设备（含商家端 handoff 换来的）立即失效。
            revoked = BuyerSession.objects.filter(account=account, revoked_at__isnull=True).update(
                revoked_at=timezone.now()
            )
            record_audit(
                request=request,
                actor=request.staff_account,
                action="BUYER_RESET_PASSWORD",
                target_type="buyer_account",
                target_id=str(account.public_id),
                reason=note,
                # 不记录明文/哈希，只记「已重设 + 失效会话数」。
                before_state={"password_reset": False},
                after_state={
                    "password_reset": True,
                    "generated": generate,
                    "revoked_sessions": revoked,
                },
                tenant_type="buyer",
                tenant_id=str(account.public_id),
            )

        return Response(
            {
                "buyer": _buyer_payload(account),
                # 明文只在「自动生成」时回给当前响应一次，不入库/不入日志/不入审计。
                "generated_password": password if generate else None,
                "revoked_sessions": revoked,
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
