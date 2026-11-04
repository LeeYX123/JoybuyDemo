import uuid

from django.db import models
from django.db.models import Q


class Currency(models.Model):
    code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=80)
    symbol = models.CharField(max_length=8)
    exponent = models.PositiveSmallIntegerField(default=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "currency"
        ordering = ["code"]


class Market(models.Model):
    code = models.CharField(max_length=8, unique=True)
    name = models.CharField(max_length=100)
    default_locale = models.CharField(max_length=16)
    time_zone = models.CharField(max_length=64)
    default_currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        related_name="default_for_markets",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "market"
        ordering = ["code"]


class Offer(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"

    class SourceAvailability(models.TextChoices):
        UNKNOWN = "UNKNOWN", "Unknown"
        IN_STOCK = "IN_STOCK", "In stock"
        OUT_OF_STOCK = "OUT_OF_STOCK", "Out of stock"
        UNAVAILABLE = "UNAVAILABLE", "Unavailable"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    merchant = models.ForeignKey(
        "merchants.Merchant",
        on_delete=models.PROTECT,
        related_name="offers",
    )
    sku = models.ForeignKey("catalog.Sku", on_delete=models.PROTECT, related_name="offers")
    market = models.ForeignKey(Market, on_delete=models.PROTECT, related_name="offers")
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name="offers")
    current_price = models.DecimalField(max_digits=18, decimal_places=4)
    list_price = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    promotion_label = models.CharField(max_length=120, blank=True, default="")
    local_inventory = models.PositiveIntegerField(default=9999)
    source_availability = models.CharField(
        max_length=24,
        choices=SourceAvailability.choices,
        default=SourceAvailability.UNKNOWN,
    )
    # Full-refresh staleness tracking (WP-19): set when a refresh run did not
    # see the offer; after consecutive confirmations the source is treated
    # as UNAVAILABLE. History is never deleted.
    suspected_stale_since = models.DateTimeField(null=True, blank=True)
    stale_confirmations = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "offer"
        constraints = [
            models.UniqueConstraint(
                fields=["merchant", "sku", "market", "currency"],
                name="offer_merchant_sku_market_unique",
            ),
            models.CheckConstraint(
                condition=Q(current_price__gte=0),
                name="offer_current_price_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(list_price__isnull=True) | Q(list_price__gte=models.F("current_price")),
                name="offer_list_price_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=["market", "status", "source_availability"],
                name="offer_market_status_idx",
            ),
            models.Index(fields=["merchant", "status"], name="offer_merchant_status_idx"),
            models.Index(fields=["sku", "status"], name="offer_sku_status_idx"),
        ]

    @property
    def display_inventory(self) -> str:
        return "999+" if self.local_inventory >= 999 else str(self.local_inventory)


class OfferSourceIdentity(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.PROTECT, related_name="source_identities")
    source_system = models.CharField(max_length=50)
    source_id = models.CharField(max_length=160)
    source_url = models.URLField(max_length=1000, blank=True, default="")
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "offer_source_identity"
        constraints = [
            models.UniqueConstraint(
                fields=["source_system", "source_id"],
                name="offer_source_identity_unique",
            )
        ]
        indexes = [models.Index(fields=["offer", "source_system"], name="offer_source_lookup_idx")]


class PriceSnapshot(models.Model):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name="price_snapshots")
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name="price_snapshots")
    current_price = models.DecimalField(max_digits=18, decimal_places=4)
    list_price = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    promotion_label = models.CharField(max_length=120, blank=True, default="")
    observed_at = models.DateTimeField()
    source_url = models.URLField(max_length=1000, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "price_snapshot"
        ordering = ["-observed_at", "-pk"]
        indexes = [models.Index(fields=["offer", "observed_at"], name="price_offer_observed_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["offer", "observed_at"],
                name="price_snapshot_observation_unique",
            ),
            models.CheckConstraint(
                condition=Q(current_price__gte=0),
                name="price_snapshot_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(list_price__isnull=True) | Q(list_price__gte=models.F("current_price")),
                name="price_snapshot_list_valid",
            ),
        ]


class InventoryLedger(models.Model):
    class Reason(models.TextChoices):
        INITIAL_IMPORT = "INITIAL_IMPORT", "Initial import"
        MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT", "Manual adjustment"
        RESERVATION = "RESERVATION", "Reservation"
        RELEASE = "RELEASE", "Release"
        CORRECTION = "CORRECTION", "Correction"

    offer = models.ForeignKey(Offer, on_delete=models.PROTECT, related_name="inventory_ledger")
    quantity_delta = models.IntegerField()
    balance_after = models.PositiveIntegerField()
    reason = models.CharField(max_length=32, choices=Reason.choices)
    idempotency_key = models.CharField(max_length=100, unique=True, null=True, blank=True)
    actor = models.ForeignKey(
        "accounts_staff.StaffAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_adjustments",
    )
    request_id = models.UUIDField(null=True, blank=True)
    reference_type = models.CharField(max_length=50, blank=True, default="")
    reference_id = models.CharField(max_length=100, blank=True, default="")
    note = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "inventory_ledger"
        ordering = ["created_at", "pk"]
        indexes = [models.Index(fields=["offer", "created_at"], name="inventory_offer_created_idx")]
