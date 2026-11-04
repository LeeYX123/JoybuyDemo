import secrets
import uuid

from django.db import models

ANONYMOUS_TOKEN_LENGTH = 48
MAX_QTY_PER_ITEM = 99


def generate_anonymous_token() -> str:
    return secrets.token_urlsafe(ANONYMOUS_TOKEN_LENGTH)


class Cart(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        MERGED = "MERGED", "Merged into another cart"
        CHECKED_OUT = "CHECKED_OUT", "Checked out"
        ABANDONED = "ABANDONED", "Abandoned"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    account = models.ForeignKey(
        "accounts_buyers.BuyerAccount",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="carts",
    )
    anonymous_token = models.CharField(max_length=128, blank=True, default="", editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cart"
        constraints = [
            models.UniqueConstraint(
                fields=["account"],
                condition=models.Q(status="OPEN", account__isnull=False),
                name="cart_single_open_per_buyer",
            ),
            models.UniqueConstraint(
                fields=["anonymous_token"],
                condition=models.Q(status="OPEN", anonymous_token__gt=""),
                name="cart_single_open_per_token",
            ),
        ]
        indexes = [
            models.Index(fields=["account", "status"], name="cart_account_status_idx"),
            models.Index(fields=["anonymous_token", "status"], name="cart_token_status_idx"),
        ]

    @property
    def is_anonymous(self) -> bool:
        return self.account_id is None


class CartItem(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    offer = models.ForeignKey("offers.Offer", on_delete=models.CASCADE, related_name="cart_items")
    quantity = models.PositiveIntegerField()
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cart_item"
        constraints = [models.UniqueConstraint(fields=["cart", "offer"], name="cart_item_unique")]

    def clean_quantity(self) -> None:
        if not 1 <= self.quantity <= MAX_QTY_PER_ITEM:
            raise ValueError(f"Quantity must be between 1 and {MAX_QTY_PER_ITEM}.")
