import uuid
from decimal import Decimal

from django.db import models
from django.db.models import Q


class Merchant(models.Model):
    class Type(models.TextChoices):
        STANDARD = "STANDARD", "Standard"
        SOURCE_VIRTUAL = "SOURCE_VIRTUAL", "Source virtual"
        IMPORT_FALLBACK = "IMPORT_FALLBACK", "Import fallback"

    class OnboardingStatus(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING_REVIEW = "PENDING_REVIEW", "Pending review"
        PENDING_DEPOSIT = "PENDING_DEPOSIT", "Pending deposit"
        ACTIVE = "ACTIVE", "Active"
        REJECTED = "REJECTED", "Rejected"
        SUSPENDED = "SUSPENDED", "Suspended"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    slug = models.SlugField(max_length=100, unique=True)
    display_name = models.CharField(max_length=160)
    legal_name = models.CharField(max_length=200, blank=True, default="")
    avatar_url = models.URLField(max_length=1000, blank=True, default="")
    merchant_type = models.CharField(max_length=24, choices=Type.choices, default=Type.STANDARD)
    onboarding_status = models.CharField(
        max_length=24,
        choices=OnboardingStatus.choices,
        default=OnboardingStatus.DRAFT,
    )
    requires_staff_totp = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False)
    activated_at = models.DateTimeField(null=True, blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)

    # --- 商家端经营账户（文档「商家与入驻」合并进 merchant，不另建表） ---
    currency = models.CharField(max_length=3, default="CNY")
    wallet_balance = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    deposit_balance = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    credit_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("100"))
    wallet_password_hash = models.CharField(max_length=128, blank=True, default="")
    wallet_password_failures = models.PositiveSmallIntegerField(default=0)
    wallet_password_locked_until = models.DateTimeField(null=True, blank=True)

    # --- 入驻审核结论（首次审核通过后锁定，双向不可再改） ---
    admission_approved = models.BooleanField(default=False)
    admission_reviewed_at = models.DateTimeField(null=True, blank=True)
    deposit_enabled = models.BooleanField(default=False)
    deposit_required = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    deposit_initial_paid = models.BooleanField(default=False)
    ban_after_days = models.PositiveSmallIntegerField(default=4)
    suspend_reason = models.CharField(max_length=255, blank=True, default="")

    # --- 经营看板指标（后台正向调整，跨日归零的当天增量单独存） ---
    followers = models.PositiveIntegerField(default=0)
    follow_delta = models.PositiveIntegerField(default=0)
    follow_day = models.DateField(null=True, blank=True)
    exposure = models.PositiveIntegerField(default=0)
    last_online_at = models.DateTimeField(null=True, blank=True)

    referral_code = models.CharField(max_length=32, unique=True, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "merchant"
        constraints = [
            models.CheckConstraint(
                condition=Q(wallet_balance__gte=0),
                name="merchant_wallet_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(credit_score__gte=0) & Q(credit_score__lte=100),
                name="merchant_credit_range",
            ),
        ]
        indexes = [
            models.Index(
                fields=["onboarding_status", "created_at"],
                name="merchant_status_created_idx",
            )
        ]

    @property
    def is_active(self) -> bool:
        return self.onboarding_status == self.OnboardingStatus.ACTIVE

    @property
    def can_operate(self) -> bool:
        """接单中 + 入驻通过 + （保证金免缴或已首次缴足）。"""
        if self.onboarding_status != self.OnboardingStatus.ACTIVE:
            return False
        if not self.admission_approved:
            return False
        return not self.deposit_enabled or self.deposit_initial_paid


class MerchantPermission(models.Model):
    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "merchant_permission"
        ordering = ["code"]


class MerchantRole(models.Model):
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True, default="")
    is_system = models.BooleanField(default=False)
    permissions = models.ManyToManyField(MerchantPermission, related_name="roles", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "merchant_role"
        ordering = ["code"]


class MerchantMembership(models.Model):
    class Status(models.TextChoices):
        INVITED = "INVITED", "Invited"
        ACTIVE = "ACTIVE", "Active"
        DISABLED = "DISABLED", "Disabled"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    staff = models.ForeignKey(
        "accounts_staff.StaffAccount",
        on_delete=models.CASCADE,
        related_name="merchant_memberships",
    )
    role = models.ForeignKey(
        MerchantRole,
        on_delete=models.PROTECT,
        related_name="memberships",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.INVITED)
    joined_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "merchant_membership"
        constraints = [
            models.UniqueConstraint(
                fields=["merchant", "staff"],
                name="merchant_membership_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=["staff", "status", "merchant"],
                name="merchant_member_staff_idx",
            )
        ]


class MerchantSourceMapping(models.Model):
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.PROTECT,
        related_name="source_mappings",
    )
    source_system = models.CharField(max_length=50)
    source_seller_id = models.CharField(max_length=160)
    source_name = models.CharField(max_length=200, blank=True, default="")
    source_url = models.URLField(max_length=1000, blank=True, default="")
    last_seen_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "merchant_source_mapping"
        constraints = [
            models.UniqueConstraint(
                fields=["source_system", "source_seller_id"],
                name="merchant_source_seller_unique",
            ),
            models.CheckConstraint(
                condition=~Q(source_system="") & ~Q(source_seller_id=""),
                name="merchant_source_mapping_nonempty",
            ),
        ]
        indexes = [
            models.Index(
                fields=["merchant", "source_system"],
                name="merchant_source_lookup_idx",
            )
        ]
