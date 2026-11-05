import uuid

from django.db import models
from django.db.models import Q


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING_PAYMENT = "PENDING_PAYMENT", "Pending payment"
        CANCELED = "CANCELED", "Canceled"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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
        "到达目的地网点",
        "派送中",
        "已签收",
        "用户确认收货",
    )

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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
