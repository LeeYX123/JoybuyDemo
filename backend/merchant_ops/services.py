"""商家经营域服务层：资金、履约、保证金、返佣。

所有涉及余额的动作都必须走这里，保证「余额 + 流水」在同一事务里落库，
且同一业务重复提交不会二次入账（幂等键 / settled 标记）。
"""

from datetime import datetime, time
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from merchant_ops.models import (
    AfterSale,
    AfterSaleEvent,
    MerchantDepositEntry,
    MerchantWalletEntry,
    MerchantWithdrawal,
    ReferralCommission,
    ReferralProgram,
)
from merchants.models import Merchant
from orders.models import MerchantOrder

MONEY = Decimal("0.0001")
CENT = Decimal("0.01")


class MerchantOpsError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY)


def _lock_merchant(merchant_id: int) -> Merchant:
    return Merchant.objects.select_for_update().get(pk=merchant_id)


def record_wallet_entry(
    *,
    merchant_id: int,
    kind: str,
    amount: Decimal,
    occurred_at=None,
    note: str = "",
    order=None,
    withdrawal=None,
    idempotency_key: str | None = None,
    actor=None,
    state: str = MerchantWalletEntry.State.COMPLETED,
) -> MerchantWalletEntry:
    """写入一条资金流水并同步余额（收入正、支出负）。

    ``idempotency_key`` 已存在时直接返回旧流水，不再改余额——这是回款、
    返佣到账、充值重复提交的唯一防线。
    """

    amount = money(amount)
    if amount == 0:
        raise MerchantOpsError("AMOUNT_REQUIRED", "金额不能为 0。")

    with transaction.atomic():
        if idempotency_key:
            existing = MerchantWalletEntry.objects.filter(idempotency_key=idempotency_key).first()
            if existing:
                return existing

        merchant = _lock_merchant(merchant_id)
        before = merchant.wallet_balance
        after = money(before + amount)
        if after < 0:
            raise MerchantOpsError(
                "INSUFFICIENT_WALLET_BALANCE",
                "钱包可用余额不足，无法完成本次扣款。",
            )

        entry = MerchantWalletEntry.objects.create(
            merchant=merchant,
            kind=kind,
            state=state,
            currency=merchant.currency,
            amount=amount,
            balance_before=before,
            balance_after=after,
            order=order,
            withdrawal=withdrawal,
            note=note,
            idempotency_key=idempotency_key,
            occurred_at=occurred_at or timezone.now(),
            created_by=actor,
        )
        merchant.wallet_balance = after
        merchant.save(update_fields=["wallet_balance", "updated_at"])
        return entry


def reserve_withdrawal(merchant: Merchant, *, withdrawal: MerchantWithdrawal, actor=None):
    """提现申请占用可用余额（记一笔负向流水，代表资金已从可用余额划出）。"""

    return record_wallet_entry(
        merchant_id=merchant.pk,
        kind=MerchantWalletEntry.Kind.WITHDRAWAL,
        amount=-money(withdrawal.amount),
        note=f"提现申请 {withdrawal.public_id.hex[:8].upper()} 占用余额",
        withdrawal=withdrawal,
        idempotency_key=f"withdrawal-reserve:{withdrawal.public_id}",
        actor=actor,
        state=MerchantWalletEntry.State.PENDING,
    )


def return_withdrawal(withdrawal: MerchantWithdrawal, *, actor=None, reason: str = ""):
    """打回 / 转账失败退回一次；已退回过的直接返回。"""

    if withdrawal.returned:
        return None
    with transaction.atomic():
        locked = MerchantWithdrawal.objects.select_for_update().get(pk=withdrawal.pk)
        if locked.returned:
            return None
        entry = record_wallet_entry(
            merchant_id=locked.merchant_id,
            kind=MerchantWalletEntry.Kind.WITHDRAWAL,
            amount=money(locked.amount),
            note=f"提现退回 {locked.public_id.hex[:8].upper()}{('：' + reason) if reason else ''}",
            withdrawal=locked,
            idempotency_key=f"withdrawal-return:{locked.public_id}",
            actor=actor,
        )
        locked.returned = True
        locked.state = (
            MerchantWithdrawal.State.REJECTED
            if locked.state == MerchantWithdrawal.State.PENDING
            else MerchantWithdrawal.State.FAILED
        )
        locked.reason = reason or locked.reason
        locked.save(update_fields=["returned", "state", "reason", "updated_at"])
        return entry


def recharge_wallet(merchant: Merchant, *, amount, actor=None, note: str = ""):
    amount = money(amount)
    if amount <= 0:
        raise MerchantOpsError("AMOUNT_INVALID", "充值金额必须大于 0。")
    return record_wallet_entry(
        merchant_id=merchant.pk,
        kind=MerchantWalletEntry.Kind.RECHARGE,
        amount=amount,
        note=note or "平台充值",
        idempotency_key=f"recharge:{merchant.pk}:{timezone.now().timestamp()}",
        actor=actor,
    )


def adjust_wallet(merchant: Merchant, *, target_balance, actor=None, note: str = ""):
    """按「调整后余额」记差额，管理端改余额只用这个入口。"""

    target = money(target_balance)
    if target < 0:
        raise MerchantOpsError("BALANCE_NEGATIVE", "钱包余额不能为负。")
    delta = money(target - merchant.wallet_balance)
    if delta == 0:
        raise MerchantOpsError("NO_CHANGE", "余额未发生变化。")
    return record_wallet_entry(
        merchant_id=merchant.pk,
        kind=MerchantWalletEntry.Kind.ADJUSTMENT,
        amount=delta,
        note=note or "平台调整余额",
        actor=actor,
    )


# --------------------------------------------------------------------------
# 保证金
# --------------------------------------------------------------------------


def _deposit_entry(
    merchant: Merchant,
    *,
    kind: str,
    delta: Decimal,
    actor=None,
    note: str = "",
    related_id: str = "",
) -> MerchantDepositEntry:
    before = merchant.deposit_balance
    after = money(before + delta)
    entry = MerchantDepositEntry.objects.create(
        merchant=merchant,
        kind=kind,
        amount=money(delta),
        balance_before=before,
        balance_after=after,
        currency=merchant.currency,
        related_id=related_id,
        note=note,
        created_by=actor,
        occurred_at=timezone.now(),
    )
    merchant.deposit_balance = after
    fields = ["deposit_balance", "updated_at"]
    # 首次累计达到应缴额即视为已缴足：待缴保证金 → 接单中。
    if (
        merchant.deposit_enabled
        and not merchant.deposit_initial_paid
        and merchant.deposit_required is not None
        and after >= merchant.deposit_required
    ):
        merchant.deposit_initial_paid = True
        fields.append("deposit_initial_paid")
        if merchant.onboarding_status == Merchant.OnboardingStatus.PENDING_DEPOSIT:
            merchant.onboarding_status = Merchant.OnboardingStatus.ACTIVE
            fields.append("onboarding_status")
    merchant.save(update_fields=fields)
    return entry


def recharge_deposit(merchant: Merchant, *, amount, actor=None, note: str = ""):
    amount = money(amount)
    if amount <= 0:
        raise MerchantOpsError("AMOUNT_INVALID", "保证金充值金额必须大于 0。")
    if not merchant.deposit_enabled:
        raise MerchantOpsError("DEPOSIT_NOT_ENABLED", "该商家未启用保证金，无需缴纳。")
    with transaction.atomic():
        locked = _lock_merchant(merchant.pk)
        return _deposit_entry(
            locked,
            kind=MerchantDepositEntry.Kind.INITIAL
            if not locked.deposit_initial_paid
            else MerchantDepositEntry.Kind.RECHARGE,
            delta=amount,
            actor=actor,
            note=note or "平台充值保证金",
        )


def adjust_deposit(merchant: Merchant, *, target_balance, actor=None, note: str = ""):
    """按「调整后余额」记差额；允许 0 或负数，且不触发封店。"""

    target = money(target_balance)
    with transaction.atomic():
        locked = _lock_merchant(merchant.pk)
        delta = money(target - locked.deposit_balance)
        if delta == 0:
            raise MerchantOpsError("NO_CHANGE", "保证金余额未发生变化。")
        return _deposit_entry(
            locked,
            kind=MerchantDepositEntry.Kind.ADJUSTMENT,
            delta=delta,
            actor=actor,
            note=note or "平台调整保证金余额",
        )


# --------------------------------------------------------------------------
# 履约：发货 / 节点推进 / 回款
# --------------------------------------------------------------------------


def _ensure_node_times(merchant_order: MerchantOrder) -> list:
    times = list(merchant_order.node_times or [])
    while len(times) < 8:
        times.append(None)
    return times[:8]


def ship_merchant_order(merchant_order: MerchantOrder, *, actor=None, reference: str = ""):
    """确认发货：扣成本 → 已发货 → 进度到「待出库」。"""

    with transaction.atomic():
        locked = (
            MerchantOrder.objects.select_for_update()
            .select_related("merchant")
            .get(pk=merchant_order.pk)
        )
        if locked.status != MerchantOrder.Status.PENDING:
            raise MerchantOpsError("ORDER_ALREADY_SHIPPED", "该订单已发货，不能重复发货。")
        if locked.cost_total > 0:
            record_wallet_entry(
                merchant_id=locked.merchant_id,
                kind=MerchantWalletEntry.Kind.ORDER_SHIPPING,
                amount=-money(locked.cost_total),
                note=f"订单发货扣成本 {locked.public_id.hex[:8].upper()}",
                order=locked,
                idempotency_key=f"ship:{locked.public_id}",
                actor=actor,
            )
        else:
            # 成本为 0 也写一条流水，保证资金明细能看到这次发货动作。
            MerchantWalletEntry.objects.create(
                merchant_id=locked.merchant_id,
                kind=MerchantWalletEntry.Kind.ORDER_SHIPPING,
                amount=money(0),
                balance_before=locked.merchant.wallet_balance,
                balance_after=locked.merchant.wallet_balance,
                order=locked,
                note=f"订单发货（成本为 0）{locked.public_id.hex[:8].upper()}",
                idempotency_key=f"ship:{locked.public_id}",
                occurred_at=timezone.now(),
                created_by=actor,
            )

        now = timezone.now()
        times = _ensure_node_times(locked)
        if not times[0]:
            times[0] = now.isoformat()
        locked.node_times = times
        locked.progress = max(locked.progress, 0)
        locked.status = MerchantOrder.Status.SHIPPED
        locked.shipped_at = now
        if reference:
            locked.tracking_reference = reference
        locked.save(
            update_fields=[
                "node_times",
                "progress",
                "status",
                "shipped_at",
                "tracking_reference",
                "updated_at",
            ]
        )
        return locked


def advance_progress(
    merchant_order: MerchantOrder, *, node_index: int, actor=None, reference: str = ""
):
    """推进到指定节点。不能回退、不能跳级重复同一节点。"""

    with transaction.atomic():
        locked = MerchantOrder.objects.select_for_update().get(pk=merchant_order.pk)
        if locked.status == MerchantOrder.Status.PENDING:
            raise MerchantOpsError("ORDER_NOT_SHIPPED", "订单尚未发货，不能推进物流节点。")
        if node_index <= locked.progress:
            raise MerchantOpsError("NODE_NOT_FORWARD", "只能推进到更靠后的节点。")
        if node_index < 0 or node_index > 7:
            raise MerchantOpsError("NODE_INVALID", "节点索引必须在 0 到 7 之间。")

        times = _ensure_node_times(locked)
        now = timezone.now()
        for index in range(locked.progress + 1, node_index + 1):
            if not times[index]:
                times[index] = now.isoformat()
        locked.node_times = times
        locked.progress = node_index
        if reference:
            locked.tracking_reference = reference
        if node_index == 7:
            locked = _settle_locked(locked, actor=actor)
        locked.save(
            update_fields=[
                "node_times",
                "progress",
                "status",
                "settled",
                "settled_at",
                "tracking_reference",
                "updated_at",
            ]
        )
        return locked


def complete_all_nodes(merchant_order: MerchantOrder, *, actor=None):
    """一键完成：补齐空时间并推进到「用户确认收货」，触发一次回款。"""

    with transaction.atomic():
        locked = MerchantOrder.objects.select_for_update().get(pk=merchant_order.pk)
        if locked.status == MerchantOrder.Status.PENDING:
            raise MerchantOpsError("ORDER_NOT_SHIPPED", "订单尚未发货，不能完成物流节点。")
        if locked.progress >= 7:
            return locked
        now = timezone.now()
        times = _ensure_node_times(locked)
        for index in range(8):
            if not times[index]:
                times[index] = now.isoformat()
        locked.node_times = times
        locked.progress = 7
        locked = _settle_locked(locked, actor=actor)
        locked.save(
            update_fields=[
                "node_times",
                "progress",
                "status",
                "settled",
                "settled_at",
                "updated_at",
            ]
        )
        return locked


def _settle_locked(merchant_order: MerchantOrder, *, actor=None) -> MerchantOrder:
    """回款：以订单号幂等，只入账一次。"""

    if merchant_order.settled:
        return merchant_order
    if merchant_order.items_total > 0:
        record_wallet_entry(
            merchant_id=merchant_order.merchant_id,
            kind=MerchantWalletEntry.Kind.ORDER_SETTLEMENT,
            amount=money(merchant_order.items_total),
            note=f"订单回款 {merchant_order.public_id.hex[:8].upper()}",
            order=merchant_order,
            idempotency_key=f"settle:{merchant_order.public_id}",
            actor=actor,
        )
    merchant_order.settled = True
    merchant_order.settled_at = timezone.now()
    merchant_order.status = MerchantOrder.Status.COMPLETED
    return merchant_order


# --------------------------------------------------------------------------
# 推荐返佣
# --------------------------------------------------------------------------


def resolve_tier_rate(program: ReferralProgram, shipped_amount: Decimal) -> Decimal:
    """按整月金额匹配单一档位（不累进）。"""

    tiers = sorted(
        (tier for tier in (program.tiers or []) if "min" in tier),
        key=lambda tier: Decimal(str(tier["min"])),
    )
    rate = Decimal("0")
    for tier in tiers:
        if shipped_amount >= Decimal(str(tier["min"])):
            rate = Decimal(str(tier.get("rate") or 0))
    return rate


def _month_bounds(period: str) -> tuple:
    year, month = (int(part) for part in period.split("-"))
    start = timezone.make_aware(datetime(year, month, 1))
    if month == 12:
        end = timezone.make_aware(datetime(year + 1, 1, 1))
    else:
        end = timezone.make_aware(datetime(year, month + 1, 1))
    return start, end


def previous_period(now=None) -> str:
    now = now or timezone.localtime()
    year, month = now.year, now.month
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


def calculate_commissions(period: str, *, merchant_filter=None) -> list:
    """核算某月返佣：只生成「待发放」，绝不直接入钱包。"""

    from merchant_ops.models import MerchantReferral

    program = ReferralProgram.load()
    start, end = _month_bounds(period)
    created = []
    referrals = MerchantReferral.objects.select_related("referrer", "referee")
    if merchant_filter is not None:
        referrals = referrals.filter(referee=merchant_filter)

    for referral in referrals:
        if referral.referee.created_at >= end:
            continue
        # 有效月数：从入驻月起算
        joined = timezone.localtime(referral.created_at)
        months = (int(period[:4]) - joined.year) * 12 + (int(period[5:7]) - joined.month)
        if months >= program.valid_months:
            continue

        shipped = MerchantOrder.objects.filter(
            merchant=referral.referee,
            shipped_at__gte=start,
            shipped_at__lt=end,
        ).aggregate(total=Sum("items_total"))["total"] or Decimal("0")
        shipped = money(shipped)
        rate = resolve_tier_rate(program, shipped)
        if shipped <= 0 or rate <= 0:
            continue
        amount = money(shipped * rate / Decimal("100"))
        commission, _ = ReferralCommission.objects.update_or_create(
            referral=referral,
            period=period,
            defaults={
                "shipped_amount": shipped,
                "rate": rate,
                "amount": amount,
                "state": ReferralCommission.State.PENDING_PAY,
                "calculated_at": timezone.now(),
            },
        )
        created.append(commission)
    return created


def pay_commission(commission: ReferralCommission, *, actor=None):
    """客服确认发放：加推荐商家钱包 + 生成推荐返佣明细，幂等。"""

    with transaction.atomic():
        locked = (
            ReferralCommission.objects.select_for_update()
            .select_related("referral__referrer")
            .get(pk=commission.pk)
        )
        if locked.state == ReferralCommission.State.PAID:
            return locked
        if locked.state != ReferralCommission.State.PENDING_PAY:
            raise MerchantOpsError("COMMISSION_NOT_PAYABLE", "该返佣尚未核算完成。")

        entry = record_wallet_entry(
            merchant_id=locked.referral.referrer_id,
            kind=MerchantWalletEntry.Kind.REFERRAL_COMMISSION,
            amount=money(locked.amount),
            note=f"推荐返佣 {locked.period}",
            idempotency_key=f"commission:{locked.public_id}",
            actor=actor,
        )
        locked.state = ReferralCommission.State.PAID
        locked.paid_at = timezone.now()
        locked.paid_by = actor
        locked.wallet_entry = entry
        locked.save(update_fields=["state", "paid_at", "paid_by", "wallet_entry", "updated_at"])
        return locked


# --------------------------------------------------------------------------
# 售后
# --------------------------------------------------------------------------


def append_after_sale_event(
    after_sale: AfterSale, *, actor_type, action, content="", actor_label=""
):
    return AfterSaleEvent.objects.create(
        after_sale=after_sale,
        actor=actor_type,
        actor_label=actor_label,
        action=action,
        content=content,
    )


def touch_merchant_online(merchant: Merchant) -> None:
    Merchant.objects.filter(pk=merchant.pk).update(last_online_at=timezone.now())


def _day_start(value) -> datetime:
    return timezone.make_aware(datetime.combine(value, time.min))


# --------------------------------------------------------------------------
# 钱包密码与提现申请（商家端 M05）
# --------------------------------------------------------------------------

WALLET_PASSWORD_MAX_FAILURES = 5
WALLET_PASSWORD_LOCK_MINUTES = 15


def _validate_wallet_password_format(raw) -> str:
    value = str(raw or "").strip()
    if len(value) != 6 or not value.isdigit():
        raise MerchantOpsError("WALLET_PASSWORD_FORMAT", "钱包密码必须是 6 位数字。")
    return value


def set_wallet_password(
    merchant: Merchant, *, new_password, confirm_password, old_password=None
) -> Merchant:
    """设置/修改 6 位数字钱包密码。已设置过时必须校验旧密码。"""

    from django.contrib.auth.hashers import check_password, make_password

    new_value = _validate_wallet_password_format(new_password)
    if str(confirm_password or "").strip() != new_value:
        raise MerchantOpsError("WALLET_PASSWORD_MISMATCH", "两次输入的钱包密码不一致。")

    with transaction.atomic():
        locked = _lock_merchant(merchant.pk)
        if locked.wallet_password_hash:
            if not old_password or not check_password(
                str(old_password).strip(), locked.wallet_password_hash
            ):
                raise MerchantOpsError("WALLET_PASSWORD_OLD_INVALID", "当前钱包密码不正确。")
        locked.wallet_password_hash = make_password(new_value)
        locked.wallet_password_failures = 0
        locked.wallet_password_locked_until = None
        locked.save(
            update_fields=[
                "wallet_password_hash",
                "wallet_password_failures",
                "wallet_password_locked_until",
                "updated_at",
            ]
        )
        return locked


def verify_wallet_password(merchant: Merchant, raw) -> None:
    """校验钱包密码。连续 5 次错误锁定 15 分钟。

    失败计数必须先提交再抛错：如果把 raise 放在 atomic 块里，异常会把
    「+1 次失败」一起回滚，锁定逻辑永远不生效（这个坑踩过一次）。
    """

    from datetime import timedelta

    from django.contrib.auth.hashers import check_password

    value = str(raw or "").strip()
    now = timezone.now()

    outcome = None
    remaining = 0
    lock_minutes = 0

    with transaction.atomic():
        locked = _lock_merchant(merchant.pk)
        # 未设置密码优先提示「去设置」，比空输入提示更有指引性。
        if not locked.wallet_password_hash:
            raise MerchantOpsError(
                "WALLET_PASSWORD_NOT_SET", "尚未设置钱包密码，请先设置后再提现。"
            )
        if not value:
            raise MerchantOpsError("WALLET_PASSWORD_REQUIRED", "请输入钱包密码。")
        if locked.wallet_password_locked_until and locked.wallet_password_locked_until > now:
            raise MerchantOpsError(
                "WALLET_PASSWORD_LOCKED",
                "密码错误次数过多，请稍后再试。",
            )
        if not check_password(value, locked.wallet_password_hash):
            failures = locked.wallet_password_failures + 1
            if failures >= WALLET_PASSWORD_MAX_FAILURES:
                locked.wallet_password_failures = 0
                locked.wallet_password_locked_until = now + timedelta(
                    minutes=WALLET_PASSWORD_LOCK_MINUTES
                )
                outcome = "LOCKED"
                lock_minutes = WALLET_PASSWORD_LOCK_MINUTES
            else:
                locked.wallet_password_failures = failures
                outcome = "INVALID"
                remaining = WALLET_PASSWORD_MAX_FAILURES - failures
            locked.save(
                update_fields=[
                    "wallet_password_failures",
                    "wallet_password_locked_until",
                    "updated_at",
                ]
            )
        elif locked.wallet_password_failures or locked.wallet_password_locked_until:
            locked.wallet_password_failures = 0
            locked.wallet_password_locked_until = None
            locked.save(
                update_fields=[
                    "wallet_password_failures",
                    "wallet_password_locked_until",
                    "updated_at",
                ]
            )

    if outcome == "LOCKED":
        raise MerchantOpsError(
            "WALLET_PASSWORD_LOCKED",
            f"密码错误次数过多，已锁定 {lock_minutes} 分钟。",
        )
    if outcome == "INVALID":
        raise MerchantOpsError(
            "WALLET_PASSWORD_INVALID", f"钱包密码不正确，还可尝试 {remaining} 次。"
        )
    merchant.wallet_password_failures = 0
    merchant.wallet_password_locked_until = None


def request_withdrawal(
    merchant: Merchant,
    *,
    method: str,
    amount,
    wallet_password,
    bank: dict | None = None,
    chain: dict | None = None,
    actor=None,
) -> MerchantWithdrawal:
    """创建提现申请：校验密码 → 占用可用余额 → 待审核。"""

    # 先按原始输入判断小数位：money() 会先把金额量化到 4 位，
    # 之后再看 exponent 永远是 -4，会把所有合法金额都判成精度超限。
    from decimal import Decimal, InvalidOperation

    try:
        parsed = Decimal(str(amount).strip())
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise MerchantOpsError("WITHDRAWAL_AMOUNT_INVALID", "提现金额格式不正确。") from exc
    if parsed <= 0:
        raise MerchantOpsError("WITHDRAWAL_AMOUNT_INVALID", "提现金额必须大于 0。")
    if -parsed.as_tuple().exponent > 2:
        raise MerchantOpsError("WITHDRAWAL_AMOUNT_PRECISION", "提现金额最多保留 2 位小数。")
    value = money(parsed)

    if method == MerchantWithdrawal.Method.BANK:
        bank = bank or {}
        bank_name = str(bank.get("name") or "").strip()
        account = str(bank.get("account") or "").replace(" ", "")
        holder = str(bank.get("holder") or "").strip()
        branch = str(bank.get("branch") or "").strip()
        code = str(bank.get("code") or "").strip()
        if not bank_name:
            raise MerchantOpsError("BANK_NAME_REQUIRED", "请填写银行名称。")
        if not (account.isdigit() and 12 <= len(account) <= 22):
            raise MerchantOpsError("BANK_ACCOUNT_INVALID", "银行卡号需为 12 至 22 位数字。")
        if not holder:
            raise MerchantOpsError("BANK_HOLDER_REQUIRED", "请填写收款人姓名。")
        if not branch:
            raise MerchantOpsError("BANK_BRANCH_REQUIRED", "请填写银行支行名称。")
        if not code:
            raise MerchantOpsError("BANK_CODE_REQUIRED", "请填写支行编号。")
        chain = {}
    elif method == MerchantWithdrawal.Method.CHAIN:
        chain = chain or {}
        coin = str(chain.get("coin") or "").strip().upper()
        network = str(chain.get("network") or "").strip().upper()
        address = str(chain.get("address") or "").strip()
        if coin not in {"ETH", "USDT"}:
            raise MerchantOpsError("COIN_INVALID", "币种只能是 ETH 或 USDT。")
        if network not in {"ERC-20", "TRC-20"}:
            raise MerchantOpsError("NETWORK_INVALID", "链类型只能是 ERC-20 或 TRC-20。")
        if coin == "ETH" and network != "ERC-20":
            raise MerchantOpsError("NETWORK_COIN_MISMATCH", "ETH 只能选择 ERC-20。")
        if len(address) < 20:
            raise MerchantOpsError("CHAIN_ADDRESS_INVALID", "请填写有效的链上钱包地址。")
        bank = {}
    else:
        raise MerchantOpsError("WITHDRAWAL_METHOD_INVALID", "请选择提现方式。")

    verify_wallet_password(merchant, wallet_password)

    with transaction.atomic():
        locked = _lock_merchant(merchant.pk)
        if value > locked.wallet_balance:
            raise MerchantOpsError("INSUFFICIENT_WALLET_BALANCE", "提现金额超过可用余额。")
        withdrawal = MerchantWithdrawal.objects.create(
            merchant=locked,
            method=method,
            currency=locked.currency,
            amount=value,
            bank_name=(bank or {}).get("name", "").strip(),
            bank_account=str((bank or {}).get("account", "")).replace(" ", ""),
            bank_holder=(bank or {}).get("holder", "").strip(),
            bank_branch=(bank or {}).get("branch", "").strip(),
            bank_code=(bank or {}).get("code", "").strip(),
            coin=(chain or {}).get("coin", ""),
            network=(chain or {}).get("network", ""),
            chain_address=(chain or {}).get("address", "").strip(),
        )
        reserve_withdrawal(locked, withdrawal=withdrawal, actor=actor)
        return withdrawal
