import uuid

from django.contrib.auth.hashers import check_password, make_password
from django.db import models


class StaffAccount(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        DISABLED = "DISABLED", "Disabled"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    email = models.EmailField(max_length=254, unique=True)
    display_name = models.CharField(max_length=120)
    password = models.CharField(max_length=128)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    totp_required = models.BooleanField(default=False)
    last_login_at = models.DateTimeField(null=True, blank=True)
    disabled_at = models.DateTimeField(null=True, blank=True)
    disabled_reason = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    roles = models.ManyToManyField(
        "PlatformRole",
        through="StaffRoleAssignment",
        through_fields=("staff", "role"),
        related_name="staff_accounts",
    )

    class Meta:
        db_table = "staff_account"
        indexes = [models.Index(fields=["status", "created_at"], name="staff_status_created_idx")]

    def set_password(self, raw_password: str) -> None:
        self.password = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password(raw_password, self.password)

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE

    @property
    def requires_totp(self) -> bool:
        if self.totp_required:
            return True
        if self.roles.filter(is_platform_admin=True).exists():
            return True
        return self.merchant_memberships.filter(
            status="ACTIVE",
            merchant__requires_staff_totp=True,
            merchant__onboarding_status="ACTIVE",
        ).exists()


class PlatformPermission(models.Model):
    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "platform_permission"
        ordering = ["code"]


class PlatformRole(models.Model):
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True, default="")
    is_platform_admin = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False)
    permissions = models.ManyToManyField(PlatformPermission, related_name="roles", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "platform_role"
        ordering = ["code"]


class StaffRoleAssignment(models.Model):
    staff = models.ForeignKey(
        StaffAccount,
        on_delete=models.CASCADE,
        related_name="role_assignments",
    )
    role = models.ForeignKey(
        PlatformRole,
        on_delete=models.CASCADE,
        related_name="staff_assignments",
    )
    assigned_by = models.ForeignKey(
        StaffAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="role_assignments_made",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "staff_role_assignment"
        constraints = [
            models.UniqueConstraint(
                fields=["staff", "role"],
                name="staff_role_assignment_unique",
            )
        ]


class StaffTotpDevice(models.Model):
    staff = models.OneToOneField(
        StaffAccount,
        on_delete=models.CASCADE,
        related_name="totp_device",
    )
    secret_ciphertext = models.TextField()
    confirmed_at = models.DateTimeField()
    disabled_at = models.DateTimeField(null=True, blank=True)
    last_verified_counter = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "staff_totp_device"

    @property
    def is_active(self) -> bool:
        return self.disabled_at is None


class StaffSession(models.Model):
    staff = models.ForeignKey(
        StaffAccount,
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    token_digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField()
    totp_verified_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "staff_session"
        indexes = [models.Index(fields=["expires_at", "revoked_at"], name="staff_session_exp_idx")]
