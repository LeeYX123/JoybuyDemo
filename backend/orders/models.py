import uuid

from django.db import models


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
    offer = models.ForeignKey("offers.Offer", on_delete=models.PROTECT)
    spu_public_id = models.CharField(max_length=36)
    title = models.CharField(max_length=500)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=18, decimal_places=4)
    currency = models.CharField(max_length=3)

    class Meta:
        db_table = "order_item"


class InventoryReservation(models.Model):
    """Row per order item; release writes the inventory ledger once."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="reservations")
    offer = models.ForeignKey("offers.Offer", on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    released = models.BooleanField(default=False)

    class Meta:
        db_table = "inventory_reservation"
