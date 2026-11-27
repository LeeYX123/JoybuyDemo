import uuid

from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.db.models import Q

from common.ids import new_buyer_public_id, save_with_public_id_retry


class BuyerAccount(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        DISABLED = "DISABLED", "Disabled"

    # 对外用户编号：JYU + 10 位随机（见 common.ids）；主键仍是 bigint。
    public_id = models.CharField(
        max_length=32, unique=True, editable=False, default=new_buyer_public_id
    )
    email = models.EmailField(max_length=254, unique=True, null=True, blank=True)
    phone_e164 = models.CharField(max_length=16, unique=True, null=True, blank=True)
    password = models.CharField(max_length=128)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    # 登录渠道（迭代02）：FACEBOOK / GOOGLE / EMAIL。三方 OAuth 本机开发阶段
    # 只做按钮占位，实际注册路径目前只有 EMAIL。
    class AuthProvider(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        FACEBOOK = "FACEBOOK", "Facebook"
        GOOGLE = "GOOGLE", "Google"

    auth_provider = models.CharField(
        max_length=16, choices=AuthProvider.choices, default=AuthProvider.EMAIL
    )
    # 三方登录（docs/16）：Facebook 可能不返回邮箱，这类账号没有任何 email/phone。
    # 该布尔列在「建号 + 写 BuyerIdentity」的同一事务里置 True，用于把
    # `buyer_account_has_identifier` 的不变量放宽成「有标识 或 已绑定三方身份」——
    # 否则无邮箱账号会被 DB 约束直接拒绝。CheckConstraint 不能跨表判断，故去规范化冗余一列。
    identity_bound = models.BooleanField(default=False)
    # 需求文档03 13.5-6: 展示用户名。未设置时首次登录生成 `user+4位数字+4位小写字母`
    # （真站格式实证 user4323txlb），一次生成固定存库；用户以后设置昵称则覆盖显示。
    display_name = models.CharField(max_length=32, blank=True, default="")
    email_verified_at = models.DateTimeField(null=True, blank=True)
    phone_verified_at = models.DateTimeField(null=True, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    disabled_at = models.DateTimeField(null=True, blank=True)
    disabled_reason = models.CharField(max_length=255, blank=True, default="")
    # docs/12 requirement 6-6: only whitelisted accounts may buy. The demo
    # stage defaults every account to whitelisted so the storefront keeps
    # working; the admin can flip the flag to exercise the blocking popup.
    purchase_whitelisted = models.BooleanField(default=True)
    # 平台管理后台 A13：是否允许下单支付（2026-11-27 管理端【编辑】新增）。
    # 与 purchase_whitelisted 是两条独立闸门：白名单决定「能不能买」，本字段决定
    # 「能不能付款」；关闭后 orders.place_order 抛 PAYMENT_DISABLED，已存在的
    # 登录态与购物车不受影响。默认 True，保持历史账号行为不变。
    payment_enabled = models.BooleanField(default=True)
    # 平台管理后台 A13/A14：白名单余额账户。与商家钱包是两套独立账户，不可互相覆盖。
    balance = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    region = models.CharField(max_length=32, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "buyer_account"
        constraints = [
            models.CheckConstraint(
                condition=(Q(email__isnull=False) & ~Q(email=""))
                | (Q(phone_e164__isnull=False) & ~Q(phone_e164=""))
                | Q(identity_bound=True),
                name="buyer_account_has_identifier",
            ),
            models.CheckConstraint(
                condition=Q(balance__gte=0),
                name="buyer_balance_nonnegative",
            ),
        ]
        indexes = [models.Index(fields=["status", "created_at"], name="buyer_status_created_idx")]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            return super().save(*args, **kwargs)
        return save_with_public_id_retry(
            self,
            kind="buyer",
            save_fn=super().save,
            args=args,
            kwargs=kwargs,
        )

    def set_password(self, raw_password: str) -> None:
        self.password = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password(raw_password, self.password)

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE


class BuyerIdentity(models.Model):
    """三方登录身份（Google / Facebook）；``(provider, subject)`` 是账号的唯一键。

    Facebook 可能不返回邮箱，这类买家账号 ``email`` 为 NULL，只能靠本表 subject 认人。
    subject 语义：Google 是稳定不变的 ``sub``；Facebook 是 **app-scoped id**
    （同一人在不同 App 里 ID 不同，dev/prod 换 App 即不能复用）。对外一律用
    ``BuyerAccount.public_id``，本表的 subject 不进前端 payload / URL。
    """

    class Provider(models.TextChoices):
        FACEBOOK = "FACEBOOK", "Facebook"
        GOOGLE = "GOOGLE", "Google"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    account = models.ForeignKey(
        BuyerAccount, on_delete=models.CASCADE, related_name="identities"
    )
    provider = models.CharField(max_length=16, choices=Provider.choices)
    subject = models.CharField(max_length=191)
    # 三方当时返回的邮箱快照：Facebook 可能为空且不可信，仅作排障线索，不参与认人。
    email_snapshot = models.EmailField(max_length=254, null=True, blank=True)
    display_name = models.CharField(max_length=120, blank=True, default="")
    avatar_url = models.CharField(max_length=512, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    last_login_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "buyer_identity"
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "subject"], name="buyer_identity_unique"
            )
        ]
        indexes = [models.Index(fields=["account"], name="buyer_identity_account_idx")]


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


class BuyerWalletEntry(models.Model):
    """买家（白名单）余额流水（A13/A14）。

    与商家 ``merchant_wallet_entry`` 刻意分开：文档明确「白名单余额消费与商家
    钱包成本/回款为不同账户，不可相互覆盖」。金额收入为正、消费为负。
    """

    class Kind(models.TextChoices):
        RECHARGE = "RECHARGE", "余额充值"
        PURCHASE = "PURCHASE", "商城消费"
        ADJUSTMENT = "ADJUSTMENT", "余额调整"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    account = models.ForeignKey(
        BuyerAccount,
        on_delete=models.CASCADE,
        related_name="wallet_entries",
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    amount = models.DecimalField(max_digits=18, decimal_places=4)
    balance_before = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    balance_after = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, default="CNY")
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="buyer_wallet_entries",
    )
    operator_label = models.CharField(max_length=120, blank=True, default="")
    note = models.CharField(max_length=255, blank=True, default="")
    idempotency_key = models.CharField(max_length=120, unique=True, null=True, blank=True)
    occurred_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "buyer_wallet_entry"
        ordering = ["-occurred_at", "-pk"]
        indexes = [
            models.Index(
                fields=["account", "kind", "occurred_at"],
                name="bwallet_account_kind_idx",
            )
        ]
