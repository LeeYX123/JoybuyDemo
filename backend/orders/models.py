import uuid

from django.db import models
from django.db.models import Q

from common.ids import (
    new_order_public_id,
    new_payment_public_id,
    new_refund_public_id,
    new_shipment_public_id,
    save_with_public_id_retry,
)


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING_PAYMENT = "PENDING_PAYMENT", "Pending payment"
        # 演示阶段：白名单免真付，下单即视为支付成功（WP-42，文档 M01 §1）。
        PAID = "PAID", "Paid"
        CANCELED = "CANCELED", "Canceled"

    # 迭代02：支付渠道任意选、直接购买成功（演示性质），但渠道记录进订单，
    # 商家端订单管理可见"这笔是什么支付的"。
    # 2026-11-28：银行卡下按品牌直记支付方式（VISA/MASTERCARD/AMEX/UNIONPAY），
    # 管理端订单明细按此值展示（如银联）。白名单演示口径：任选即支付成功。
    PAYMENT_METHODS = (
        "BALANCE",
        "CARD",
        "VISA",
        "MASTERCARD",
        "AMEX",
        "UNIONPAY",
        "MAESTRO",
        "JCB",
        "DISCOVER",
        "DINERS",
        "GOOGLE_PAY",
        "APPLE_PAY",
        "WECHAT_PAY",
        "KLARNA",
    )

    # 对外订单号：JYO + YYYYMMDD + 6 位随机（见 common.ids）；主键仍是 bigint。
    public_id = models.CharField(
        max_length=32, unique=True, editable=False, default=new_order_public_id
    )
    account = models.ForeignKey(
        "accounts_buyers.BuyerAccount", on_delete=models.PROTECT, related_name="orders"
    )
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING_PAYMENT)
    currency = models.ForeignKey("offers.Currency", on_delete=models.PROTECT)
    items_subtotal = models.DecimalField(max_digits=18, decimal_places=4)
    shipping_cost = models.DecimalField(max_digits=18, decimal_places=4)
    total = models.DecimalField(max_digits=18, decimal_places=4)
    shipping_address = models.JSONField(default=dict)
    payment_expires_at = models.DateTimeField()
    payment_method = models.CharField(max_length=32, blank=True, default="")
    paid_at = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "order"
        indexes = [
            models.Index(fields=["account", "status", "created_at"], name="order_account_idx"),
            models.Index(fields=["status", "payment_expires_at"], name="order_expiry_idx"),
        ]

    def save(self, *args, **kwargs):
        """新建时 public_id 撞唯一约束会换号重试（其它唯一键冲突原样抛出）。"""

        if self.pk is not None:
            return super().save(*args, **kwargs)
        return save_with_public_id_retry(
            self,
            kind="order",
            save_fn=super().save,
            args=args,
            kwargs=kwargs,
        )


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    merchant_order = models.ForeignKey(
        "orders.MerchantOrder",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="items",
    )
    offer = models.ForeignKey("offers.Offer", on_delete=models.PROTECT)
    spu_public_id = models.CharField(max_length=36)
    title = models.CharField(max_length=500)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=18, decimal_places=4)
    # 单位成本快照：发货扣款与商家利润都以它为准，商品后续调价不回写历史。
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    currency = models.CharField(max_length=3)

    class Meta:
        db_table = "order_item"


class MerchantOrder(models.Model):
    """按商家拆分的履约子单。

    买家侧的 ``Order`` 依旧是一次支付的整体（可跨商家）；商家端、发货扣成本、
    8 个物流节点和回款都落在子单上，这样两家店各自的进度与资金互不干扰。
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "待处理"
        SHIPPED = "SHIPPED", "已发货"
        COMPLETED = "COMPLETED", "已完成"

    NODE_LABELS = (
        "待出库",
        "已出库",
        "已揽收",
        "运输中",
        "到达网点",
        "派送中",
        "已签收",
        "用户确认收货",
    )

    # 商家子单号同属订单体系：JYO 前缀 + 与 Order 一致的格式。
    public_id = models.CharField(
        max_length=32, unique=True, editable=False, default=new_order_public_id
    )
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="merchant_orders")
    merchant = models.ForeignKey(
        "merchants.Merchant",
        on_delete=models.PROTECT,
        related_name="merchant_orders",
    )
    currency = models.CharField(max_length=3, default="CNY")
    items_total = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    cost_total = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    # -1 = 未发货；0..7 = 已到达的节点下标。进度不是订单状态。
    progress = models.SmallIntegerField(default=-1)
    node_times = models.JSONField(default=list, blank=True)
    # 发货时按区间随机生成的扭转时刻表（ISO 字符串 × 7）：下标 i 是"到达节点 i+1"
    # 的计划时刻，下一段从上一计划时刻累进；最后一项是 14 天自动确认收货截止。
    # 实际扭转即按计划时刻执行，node_times 记录计划时刻（WP-42 文档 M04 §3）。
    planned_node_times = models.JSONField(default=list, blank=True)
    payment_method = models.CharField(max_length=32, blank=True, default="")
    recipient_region = models.CharField(max_length=120, blank=True, default="")
    tracking_reference = models.CharField(max_length=120, blank=True, default="")
    settled = models.BooleanField(default=False)
    settled_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    fulfillment_reset_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "merchant_order"
        constraints = [
            models.UniqueConstraint(
                fields=["order", "merchant"],
                name="merchant_order_unique",
            ),
            models.CheckConstraint(
                condition=Q(progress__gte=-1) & Q(progress__lte=7),
                name="merchant_order_progress_range",
            ),
        ]
        indexes = [
            models.Index(
                fields=["merchant", "status", "created_at"],
                name="merchant_order_status_idx",
            ),
            models.Index(fields=["order", "merchant"], name="merchant_order_parent_idx"),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            return super().save(*args, **kwargs)
        return save_with_public_id_retry(
            self,
            kind="order",
            save_fn=super().save,
            args=args,
            kwargs=kwargs,
        )

    @property
    def profit(self):
        return self.items_total - self.cost_total


class InventoryReservation(models.Model):
    """Row per order item; release writes the inventory ledger once."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="reservations")
    offer = models.ForeignKey("offers.Offer", on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    released = models.BooleanField(default=False)

    class Meta:
        db_table = "inventory_reservation"


class AutoOrderTask(models.Model):
    """一键下单定时任务（迭代02，管理端创建）。

    向导：白名单用户 → 商家 → 商品 → 规格(offer) → 数量 → 触发时间。
    触发时间按**电脑（服务器）时间**判定（doc02 第四节拍板），由
    ``execute_due_auto_orders``（run_order_sweeps / 管理端列表惰性）到点执行；
    下单走与用户正常购买完全相同的 ``place_order``，买家端和商家端正常生成订单。
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "待执行"
        EXECUTED = "EXECUTED", "已下单"
        FAILED = "FAILED", "下单失败"
        CANCELED = "CANCELED", "已取消"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    account = models.ForeignKey(
        "accounts_buyers.BuyerAccount", on_delete=models.CASCADE, related_name="auto_orders"
    )
    merchant = models.ForeignKey(
        "merchants.Merchant", on_delete=models.CASCADE, related_name="auto_orders"
    )
    offer = models.ForeignKey(
        "offers.Offer", on_delete=models.SET_NULL, null=True, blank=True, related_name="auto_orders"
    )
    # 创建时的快照（任务列表展示 & offer 被删后仍可读）。
    product_title = models.CharField(max_length=500, blank=True, default="")
    specification = models.JSONField(default=dict, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    trigger_at = models.DateTimeField(db_index=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    executed_order = models.ForeignKey(
        Order, on_delete=models.SET_NULL, null=True, blank=True, related_name="auto_order_tasks"
    )
    failure_reason = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        "accounts_staff.StaffAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="auto_order_tasks",
    )
    executed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "auto_order_task"
        ordering = ["trigger_at", "-pk"]
        indexes = [
            models.Index(fields=["status", "trigger_at"], name="auto_order_due_idx"),
            models.Index(fields=["merchant", "status"], name="auto_order_merchant_idx"),
        ]


# --------------------------------------------------------------------------
# 全站编号改造阶段 2：支付 / 退款 / 物流
#
# 三张表都只做「记录」：支付与物流分别在既有落点（下单即付、商家发货）
# 顺手写入一条，退款目前没有真实打款动作，只留管理端手动创建。
# 对外编号 public_id 是 JYPAY / JYR / JYLOG + YYYYMMDD + 6 位随机，主键仍是 bigint。
# --------------------------------------------------------------------------


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "待支付"
        SUCCEEDED = "SUCCEEDED", "支付成功"
        FAILED = "FAILED", "支付失败"
        REFUNDED = "REFUNDED", "已退款"

    public_id = models.CharField(
        max_length=32, unique=True, editable=False, default=new_payment_public_id
    )
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    # 取值沿用 Order.PAYMENT_METHODS（BALANCE / CARD / GOOGLE_PAY ...）。
    method = models.CharField(max_length=32, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    # 外部支付网关流水号；当前没有真实网关，留空。
    provider_reference = models.CharField(max_length=120, blank=True, default="")
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payment"
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["order", "created_at"], name="payment_order_idx"),
            models.Index(fields=["status", "created_at"], name="payment_status_idx"),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            return super().save(*args, **kwargs)
        return save_with_public_id_retry(
            self,
            kind="payment",
            save_fn=super().save,
            args=args,
            kwargs=kwargs,
        )


class Refund(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "待处理"
        APPROVED = "APPROVED", "已批准"
        PROCESSING = "PROCESSING", "退款中"
        SUCCEEDED = "SUCCEEDED", "退款成功"
        FAILED = "FAILED", "退款失败"
        REJECTED = "REJECTED", "已驳回"

    public_id = models.CharField(
        max_length=32, unique=True, editable=False, default=new_refund_public_id
    )
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="refunds")
    payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="refunds",
    )
    after_sale = models.ForeignKey(
        "merchant_ops.AfterSale",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="refunds",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    reason = models.TextField(blank=True, default="")
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "refund"
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["order", "created_at"], name="refund_order_idx"),
            models.Index(fields=["status", "created_at"], name="refund_status_idx"),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            return super().save(*args, **kwargs)
        return save_with_public_id_retry(
            self,
            kind="refund",
            save_fn=super().save,
            args=args,
            kwargs=kwargs,
        )


class Shipment(models.Model):
    class Status(models.TextChoices):
        CREATED = "CREATED", "已创建"
        IN_TRANSIT = "IN_TRANSIT", "运输中"
        DELIVERED = "DELIVERED", "已送达"

    public_id = models.CharField(
        max_length=32, unique=True, editable=False, default=new_shipment_public_id
    )
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="shipments")
    merchant_order = models.ForeignKey(
        MerchantOrder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shipments",
    )
    carrier = models.CharField(max_length=120, blank=True, default="")
    # 语义承接 MerchantOrder.tracking_reference（商家发货时填的运单号）。
    tracking_no = models.CharField(max_length=120, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CREATED)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "shipment"
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["order", "created_at"], name="shipment_order_idx"),
            models.Index(fields=["merchant_order"], name="shipment_suborder_idx"),
            models.Index(fields=["status", "created_at"], name="shipment_status_idx"),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            return super().save(*args, **kwargs)
        return save_with_public_id_retry(
            self,
            kind="shipment",
            save_fn=super().save,
            args=args,
            kwargs=kwargs,
        )
