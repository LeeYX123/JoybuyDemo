import uuid

from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.db.models import Q


class BuyerAccount(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        DISABLED = "DISABLED", "Disabled"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    email = models.EmailField(max_length=254, unique=True, null=True, blank=True)
    phone_e164 = models.CharField(max_length=16, unique=True, null=True, blank=True)
    password = models.CharField(max_length=128)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    phone_verified_at = models.DateTimeField(null=True, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    disabled_at = models.DateTimeField(null=True, blank=True)
    disabled_reason = models.CharField(max_length=255, blank=True, default="")
    # docs/12 requirement 6-6: only whitelisted accounts may buy. The demo
    # stage defaults every account to whitelisted so the storefront keeps
    # working; the admin can flip the flag to exercise the blocking popup.
    purchase_whitelisted = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "buyer_account"
        constraints = [
            models.CheckConstraint(
                condition=(Q(email__isnull=False) & ~Q(email=""))
                | (Q(phone_e164__isnull=False) & ~Q(phone_e164="")),
                name="buyer_account_has_identifier",
            )
        ]
        indexes = [models.Index(fields=["status", "created_at"], name="buyer_status_created_idx")]

    def set_password(self, raw_password: str) -> None:
        self.password = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password(raw_password, self.password)

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE


class BuyerSession(models.Model):
    account = models.ForeignKey(
        BuyerAccount,
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    token_digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "buyer_session"
        indexes = [models.Index(fields=["expires_at", "revoked_at"], name="buyer_session_exp_idx")]


class VerificationCode(models.Model):
    class Channel(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        PHONE = "PHONE", "Phone"

    class Purpose(models.TextChoices):
        REGISTER = "REGISTER", "Register"

    channel = models.CharField(max_length=16, choices=Channel.choices)
    target = models.CharField(max_length=254)
    purpose = models.CharField(max_length=24, choices=Purpose.choices)
    code_digest = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "buyer_verification_code"
        indexes = [
            models.Index(
                fields=["target", "purpose", "created_at"],
                name="buyer_vcode_lookup_idx",
            )
        ]


class Favourite(models.Model):
    """Buyer's saved product (SPU); unique per buyer."""

    account = models.ForeignKey(BuyerAccount, on_delete=models.CASCADE, related_name="favourites")
    spu = models.ForeignKey("catalog.Spu", on_delete=models.CASCADE, related_name="favourited_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "buyer_favourite"
        constraints = [
            models.UniqueConstraint(fields=["account", "spu"], name="buyer_favourite_unique")
        ]
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["account", "created_at"], name="fav_account_created_idx")]


class RecentlyViewed(models.Model):
    """One row per buyer+SPU; re-viewing bumps viewed_at (no history rows)."""

    account = models.ForeignKey(
        BuyerAccount, on_delete=models.CASCADE, related_name="recently_viewed"
    )
    spu = models.ForeignKey("catalog.Spu", on_delete=models.CASCADE, related_name="viewed_by")
    viewed_at = models.DateTimeField()

    class Meta:
        db_table = "buyer_recently_viewed"
        constraints = [
            models.UniqueConstraint(fields=["account", "spu"], name="buyer_recently_viewed_unique")
        ]
        ordering = ["-viewed_at", "-pk"]
        indexes = [models.Index(fields=["account", "viewed_at"], name="recent_account_viewed_idx")]
