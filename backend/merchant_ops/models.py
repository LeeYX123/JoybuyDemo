"""商家经营域：钱包、提现、保证金、售后、平台活动与推荐返佣。

这些表在需求文档里各自独立，但都挂在 ``Merchant`` 下，且共用同一套
资金/记账口径，所以收在同一个应用里，避免跨应用循环依赖。
"""

import uuid
from decimal import Decimal

from django.db import models
from django.db.models import Q


def _money(**kwargs):
    kwargs.setdefault("max_digits", 18)
    kwargs.setdefault("decimal_places", 4)
    return models.DecimalField(**kwargs)


class MerchantWalletEntry(models.Model):
    """统一资金明细：充值、提现、订单发货扣成本、订单回款、推荐返佣、余额调整。

    一张表承载商家端「统一资金明细」和管理端「资金流水」，避免像原型那样
    拆成多张表后统计口径不一致。金额收入为正、支出为负。
    """

    class Kind(models.TextChoices):
        RECHARGE = "RECHARGE", "充值入账"
        WITHDRAWAL = "WITHDRAWAL", "提现申请"
        ORDER_SHIPPING = "ORDER_SHIPPING", "订单发货"
        ORDER_SETTLEMENT = "ORDER_SETTLEMENT", "订单回款"
        REFERRAL_COMMISSION = "REFERRAL_COMMISSION", "推荐返佣"
        ADJUSTMENT = "ADJUSTMENT", "余额调整"

    class State(models.TextChoices):
        COMPLETED = "COMPLETED", "已完成"
        PENDING = "PENDING", "处理中"
        FAILED = "FAILED", "失败"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    merchant = models.ForeignKey(
        "merchants.Merchant",
        on_delete=models.PROTECT,
        related_name="wallet_entries",
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    state = models.CharField(max_length=16, choices=State.choices, default=State.COMPLETED)
    currency = models.CharField(max_length=3, default="CNY")
    amount = _money()
    balance_before = _money(default=Decimal("0"))
    balance_after = _money(default=Decimal("0"))
    order = models.ForeignKey(
        "orders.MerchantOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wallet_entries",
    )
    withdrawal = models.ForeignKey(
        "merchant_ops.MerchantWithdrawal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wallet_entries",
    )
    note = models.CharField(max_length=255, blank=True, default="")
    idempotency_key = models.CharField(max_length=120, unique=True, null=True, blank=True)
    occurred_at = models.DateTimeField()
    created_by = models.ForeignKey(
        "accounts_staff.StaffAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merchant_wallet_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "merchant_wallet_entry"
        ordering = ["-occurred_at", "-pk"]
        indexes = [
            models.Index(
                fields=["merchant", "kind", "occurred_at"],
                name="mwallet_merchant_kind_idx",
            ),
            models.Index(fields=["occurred_at"], name="mwallet_occurred_idx"),
        ]


class MerchantWithdrawal(models.Model):
    class Method(models.TextChoices):
        BANK = "BANK", "银行卡"
        CHAIN = "CHAIN", "数字货币链上转账"

    class State(models.TextChoices):
        PENDING = "PENDING", "待审核"
        REJECTED = "REJECTED", "已打回"
        APPROVED = "APPROVED", "审核通过"
        TRANSFERRING = "TRANSFERRING", "转账中"
        FAILED = "FAILED", "转账失败"
        PAID = "PAID", "已到账"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    merchant = models.ForeignKey(
        "merchants.Merchant",
        on_delete=models.PROTECT,
        related_name="withdrawals",
    )
    method = models.CharField(max_length=8, choices=Method.choices)
    currency = models.CharField(max_length=3, default="CNY")
    amount = _money()
    fee = _money(default=Decimal("0"))
    net_amount = _money(default=Decimal("0"))
    state = models.CharField(max_length=16, choices=State.choices, default=State.PENDING)

    bank_name = models.CharField(max_length=120, blank=True, default="")
    bank_account = models.CharField(max_length=64, blank=True, default="")
    bank_holder = models.CharField(max_length=120, blank=True, default="")
    bank_branch = models.CharField(max_length=160, blank=True, default="")
    bank_code = models.CharField(max_length=40, blank=True, default="")

    coin = models.CharField(max_length=8, blank=True, default="")
    network = models.CharField(max_length=16, blank=True, default="")
    chain_address = models.CharField(max_length=160, blank=True, default="")

    reference = models.CharField(max_length=160, blank=True, default="")
    reason = models.CharField(max_length=255, blank=True, default="")
    # 申请时已占用可用余额；退回只发生一次，避免重复加钱。
    balance_reserved = models.BooleanField(default=True)
    returned = models.BooleanField(default=False)
    approved_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        "accounts_staff.StaffAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_withdrawals",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "merchant_withdrawal"
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="withdrawal_amount_positive"),
            models.CheckConstraint(condition=Q(fee__gte=0), name="withdrawal_fee_nonnegative"),
        ]
        indexes = [
            models.Index(fields=["state", "created_at"], name="withdrawal_state_idx"),
            models.Index(fields=["merchant", "created_at"], name="withdrawal_merchant_idx"),
        ]

    @property
    def is_open(self) -> bool:
        return self.state in {
            self.State.PENDING,
            self.State.APPROVED,
            self.State.TRANSFERRING,
        }


class MerchantDepositEntry(models.Model):
    """保证金记录。保证金余额本身存在 ``Merchant.deposit_balance``。"""

    class Kind(models.TextChoices):
        INITIAL = "INITIAL", "首次缴纳"
        RECHARGE = "RECHARGE", "保证金充值"
        ADJUSTMENT = "ADJUSTMENT", "余额调整"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    merchant = models.ForeignKey(
        "merchants.Merchant",
        on_delete=models.PROTECT,
        related_name="deposit_entries",
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    amount = _money()
    balance_before = _money(default=Decimal("0"))
    balance_after = _money(default=Decimal("0"))
    currency = models.CharField(max_length=3, default="CNY")
    related_id = models.CharField(max_length=100, blank=True, default="")
    note = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        "accounts_staff.StaffAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merchant_deposit_entries",
    )
    occurred_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "merchant_deposit_entry"
        ordering = ["-occurred_at", "-pk"]
        indexes = [models.Index(fields=["merchant", "occurred_at"], name="mdeposit_merchant_idx")]


class AfterSale(models.Model):
    class Kind(models.TextChoices):
        COMPLAINT = "COMPLAINT", "用户投诉"
        RETURN = "RETURN", "退货订单"

    class State(models.TextChoices):
        PENDING = "PENDING", "待处理"
        PROCESSING = "PROCESSING", "处理中"
        PLATFORM = "PLATFORM", "平台介入中"
        COMPLETED = "COMPLETED", "已完成"
        REJECTED = "REJECTED", "已驳回"

    class Decision(models.TextChoices):
        INVESTIGATE = "INVESTIGATE", "继续核实"
        COMPLETE = "COMPLETE", "完成处理"
        REJECT_RETURN = "REJECT_RETURN", "驳回退货申请"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    merchant = models.ForeignKey(
        "merchants.Merchant",
        on_delete=models.PROTECT,
        related_name="after_sales",
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name="after_sales",
    )
    merchant_order = models.ForeignKey(
        "orders.MerchantOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="after_sales",
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    state = models.CharField(max_length=16, choices=State.choices, default=State.PENDING)
    issue = models.TextField(blank=True, default="")
    progress = models.CharField(max_length=255, blank=True, default="")
    result = models.TextField(blank=True, default="")
    platform_decision = models.CharField(
        max_length=16, choices=Decision.choices, blank=True, default=""
    )
    proof = models.JSONField(default=list, blank=True)
    currency = models.CharField(max_length=3, default="CNY")
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "after_sale"
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["merchant", "state"], name="aftersale_merchant_idx"),
            models.Index(fields=["state", "created_at"], name="aftersale_state_idx"),
        ]


class AfterSaleEvent(models.Model):
    class Actor(models.TextChoices):
        MERCHANT = "MERCHANT", "商家"
        PLATFORM = "PLATFORM", "平台"
        BUYER = "BUYER", "买家"
        SYSTEM = "SYSTEM", "系统"

    after_sale = models.ForeignKey(
        AfterSale,
        on_delete=models.CASCADE,
        related_name="events",
    )
    actor = models.CharField(max_length=16, choices=Actor.choices, default=Actor.SYSTEM)
    actor_label = models.CharField(max_length=120, blank=True, default="")
    action = models.CharField(max_length=64)
    content = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "after_sale_event"
        ordering = ["created_at", "pk"]
        indexes = [models.Index(fields=["after_sale", "created_at"], name="aftersale_event_idx")]


class MerchantActivity(models.Model):
    """平台活动。``is_referral`` 为真的那条是推荐返佣常驻活动。"""

    class Kind(models.TextChoices):
        PERMANENT = "PERMANENT", "常驻活动"
        LIMITED = "LIMITED", "限时活动"

    class State(models.TextChoices):
        ONGOING = "ONGOING", "进行中"
        ENDED = "ENDED", "已结束"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    title = models.CharField(max_length=160)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.PERMANENT)
    state = models.CharField(max_length=16, choices=State.choices, default=State.ONGOING)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True, default="")
    image_url = models.URLField(max_length=1000, blank=True, default="")
    is_referral = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "merchant_activity"
        ordering = ["sort_order", "-created_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=models.F("start_date")),
                name="activity_date_order",
            )
        ]


class MerchantActivityParticipation(models.Model):
    activity = models.ForeignKey(
        MerchantActivity,
        on_delete=models.CASCADE,
        related_name="participations",
    )
    merchant = models.ForeignKey(
        "merchants.Merchant",
        on_delete=models.CASCADE,
        related_name="activity_participations",
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    exposure_added = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "merchant_activity_participation"
        constraints = [
            models.UniqueConstraint(
                fields=["activity", "merchant"],
                name="activity_participation_unique",
            )
        ]
        ordering = ["-joined_at", "-pk"]


class ReferralProgram(models.Model):
    """推荐返佣规则，单行配置（阶梯 + 有效月数）。"""

    tiers = models.JSONField(default=list)
    valid_months = models.PositiveSmallIntegerField(default=12)
    updated_by = models.ForeignKey(
        "accounts_staff.StaffAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referral_program_updates",
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "referral_program"

    @classmethod
    def load(cls) -> "ReferralProgram":
        program = cls.objects.order_by("pk").first()
        if program is None:
            program = cls.objects.create(
                tiers=[
                    {"min": "0", "rate": "1"},
                    {"min": "10000", "rate": "2"},
                    {"min": "50000", "rate": "3"},
                ],
                valid_months=12,
            )
        return program


class MerchantReferral(models.Model):
    """推荐关系：referee 由 referrer 的推荐码带入，一人只能绑定一个推荐人。"""

    referrer = models.ForeignKey(
        "merchants.Merchant",
        on_delete=models.PROTECT,
        related_name="referrals_made",
    )
    referee = models.OneToOneField(
        "merchants.Merchant",
        on_delete=models.PROTECT,
        related_name="referral_source",
    )
    code_used = models.CharField(max_length=32, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "merchant_referral"
        constraints = [
            models.CheckConstraint(
                condition=~Q(referrer=models.F("referee")),
                name="referral_no_self_reference",
            )
        ]
        indexes = [models.Index(fields=["referrer", "created_at"], name="referral_referrer_idx")]


class ReferralCommission(models.Model):
    class State(models.TextChoices):
        PENDING_CALC = "PENDING_CALC", "待核算"
        PENDING_PAY = "PENDING_PAY", "待发放"
        PAID = "PAID", "已到账"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    referral = models.ForeignKey(
        MerchantReferral,
        on_delete=models.PROTECT,
        related_name="commissions",
    )
    period = models.CharField(max_length=7)  # YYYY-MM，核算上一个自然月
    shipped_amount = _money(default=Decimal("0"))
    rate = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0"))
    amount = _money(default=Decimal("0"))
    state = models.CharField(max_length=16, choices=State.choices, default=State.PENDING_CALC)
    calculated_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(
        "accounts_staff.StaffAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referral_payouts",
    )
    wallet_entry = models.ForeignKey(
        MerchantWalletEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referral_commissions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "referral_commission"
        ordering = ["-period", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["referral", "period"],
                name="referral_commission_period_unique",
            )
        ]
        indexes = [models.Index(fields=["state", "period"], name="commission_state_idx")]


class SupportConversation(models.Model):
    """商家侧会话（A12 客服中心 / M09 消息中心）。

    两类会话共用一张表、用 ``kind`` 区分：
    - ``PLATFORM_SUPPORT``：商家 ↔ 平台客服（充值、保证金、解封等），每个商家一条；
    - ``BUYER``：买家从某个商品发起的咨询，携带商品与订单上下文。
    文档明确「客服会话与好评通知是两套业务，不共享消息列表」，所以通知走
    ``notifications.MerchantNotification``，会话走这里。
    """

    class Kind(models.TextChoices):
        BUYER = "BUYER", "买家咨询"
        PLATFORM_SUPPORT = "PLATFORM_SUPPORT", "平台客服"

    class State(models.TextChoices):
        PENDING = "PENDING", "待回复"
        PROCESSING = "PROCESSING", "处理中"
        RESOLVED = "RESOLVED", "已解决"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    merchant = models.ForeignKey(
        "merchants.Merchant",
        on_delete=models.CASCADE,
        related_name="support_conversations",
    )
    kind = models.CharField(max_length=24, choices=Kind.choices, default=Kind.BUYER)
    state = models.CharField(max_length=16, choices=State.choices, default=State.PENDING)
    buyer = models.ForeignKey(
        "accounts_buyers.BuyerAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_conversations",
    )
    peer_name = models.CharField(max_length=120, blank=True, default="")
    spu = models.ForeignKey(
        "catalog.Spu",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_conversations",
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_conversations",
    )
    merchant_last_read_at = models.DateTimeField(null=True, blank=True)
    platform_last_read_at = models.DateTimeField(null=True, blank=True)
    last_message_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "support_conversation"
        ordering = ["-last_message_at", "-pk"]
        indexes = [
            models.Index(fields=["merchant", "kind", "state"], name="support_conv_merchant_idx"),
            models.Index(fields=["state", "last_message_at"], name="support_conv_state_idx"),
        ]


class SupportMessage(models.Model):
    class Sender(models.TextChoices):
        BUYER = "BUYER", "买家"
        MERCHANT = "MERCHANT", "商家"
        PLATFORM = "PLATFORM", "平台客服"

    conversation = models.ForeignKey(
        SupportConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.CharField(max_length=16, choices=Sender.choices)
    author_label = models.CharField(max_length=120, blank=True, default="")
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "support_message"
        ordering = ["created_at", "pk"]
        indexes = [models.Index(fields=["conversation", "created_at"], name="support_msg_conv_idx")]
