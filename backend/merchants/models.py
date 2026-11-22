import uuid
from decimal import Decimal

from django.db import IntegrityError, models, transaction
from django.db.models import Q

# 商家对外展示 ID：固定 `MER` + 6 位数字，从 001000 起顺序分配。
# 需求原话是「MER+6位数字（随机数字），数字起点 001000」；这里按顺序编号
# 实现（天然唯一、可读、避免随机碰撞），格式与起点完全一致。
MERCHANT_ID_PREFIX = "MER"
MERCHANT_ID_START = 1000
MERCHANT_ID_DIGITS = 6
MERCHANT_ID_MAX_ATTEMPTS = 5


def format_merchant_public_id(number: int) -> str:
    return f"{MERCHANT_ID_PREFIX}{number:0{MERCHANT_ID_DIGITS}d}"


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

    public_id = models.CharField(max_length=16, unique=True, editable=False)
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
    # 订单未处理自动封店天数（天）：null = 不自动封店；判定口径见 merchants.services.auto_suspend_overdue_merchants
    ban_after_days = models.PositiveSmallIntegerField(null=True, blank=True)
    suspend_reason = models.CharField(max_length=255, blank=True, default="")

    # --- 经营看板指标（后台正向调整，跨日归零的当天增量单独存） ---
    followers = models.PositiveIntegerField(default=0)
    follow_delta = models.PositiveIntegerField(default=0)
    follow_day = models.DateField(null=True, blank=True)
    exposure = models.PositiveIntegerField(default=0)
    exposure_delta = models.PositiveIntegerField(default=0)
    exposure_day = models.DateField(null=True, blank=True)
    last_online_at = models.DateTimeField(null=True, blank=True)

    # --- 折扣（按商家统一设置，不做单商品差异化；百分数，20 = 成本价减免 20%） ---
    # 2026-11-10 最终口径：成本价 = ceil_to_cent(零售价 × (1 − 折扣%))；
    # 未设置折扣 = 减免 0% → 成本价 = 零售价；活动商品优先用 activity_discount_rate。
    # 文档拍板：不做区间校验、不做默认值兜底，管理端设多少按多少算。
    discount_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    activity_discount_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )

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

    def save(self, *args, **kwargs):
        """新建商家时自动生成 MER+6 位 public_id（任何创建路径都覆盖）。"""

        if self.public_id:
            return super().save(*args, **kwargs)

        # 并发保护分两层：事务内 select_for_update 锁住现有号段后再取 max+1；
        # 极端并发下仍撞唯一约束时，回滚保存点、重算最大号重试。
        for attempt in range(MERCHANT_ID_MAX_ATTEMPTS):
            try:
                with transaction.atomic():
                    self.public_id = self._next_public_id()
                    return super().save(*args, **kwargs)
            except IntegrityError as exc:
                # 只吞 public_id 冲突；slug 等其他唯一键冲突原样抛出。
                if "public_id" not in str(exc):
                    raise
                self.public_id = ""
                if attempt == MERCHANT_ID_MAX_ATTEMPTS - 1:
                    raise

    @classmethod
    def _next_public_id(cls) -> str:
        """取当前最大号 +1（需在调用方事务内执行，锁随事务释放）。"""

        values = (
            cls.objects.select_for_update()
            .filter(public_id__startswith=MERCHANT_ID_PREFIX)
            .values_list("public_id", flat=True)
        )
        numbers = []
        for value in values:
            suffix = value[len(MERCHANT_ID_PREFIX) :]
            if suffix.isdigit():
                numbers.append(int(suffix))
        return format_merchant_public_id(max(numbers, default=MERCHANT_ID_START - 1) + 1)

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


class MerchantDailyStat(models.Model):
    """商家按天统计（曝光度趋势 / 关注增量 / 订单量）。

    只在动作发生时 upsert 当日行（后台调整曝光/关注、生成已付款商家子单），
    历史行不回填——趋势图按实际有数据的日期展示。
    """

    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name="daily_stats")
    stat_date = models.DateField()
    exposure_delta = models.PositiveIntegerField(default=0)
    followers_delta = models.PositiveIntegerField(default=0)
    order_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "merchant_daily_stat"
        constraints = [
            models.UniqueConstraint(fields=["merchant", "stat_date"], name="merchant_daily_unique")
        ]
        indexes = [models.Index(fields=["merchant", "stat_date"], name="merchant_daily_idx")]


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


class MerchantApplication(models.Model):
    """购物端「申请店铺」：买家账号提交的开店申请（一人一份）。

    状态流转：PENDING →（管理端审核）APPROVED / REJECTED；
    REJECTED 可修改信息后重新提交（原行重置为 PENDING，清空驳回原因、
    刷新提交时间）；APPROVED 时回填 ``merchant`` 并打通商家端账号
    （同 email+密码，见 merchant_ops.views_shop_application）。
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    # 2026-11-17 申请表单 7 项：店铺logo、用户名字、店铺名、手机号码、
    # 邀请码（选填）、个人证件（类型 + 照片）、个人居住地址。
    # legal_name 为旧表单遗留字段（历史行仍有值），新表单不再收集。
    class IdDocumentType(models.TextChoices):
        ID_CARD = "ID_CARD", "Identity card"
        PASSPORT = "PASSPORT", "Passport"
        DRIVER_LICENSE = "DRIVER_LICENSE", "Driver license"

    buyer = models.OneToOneField(
        "accounts_buyers.BuyerAccount",
        on_delete=models.CASCADE,
        related_name="merchant_application",
    )
    user_name = models.CharField(max_length=60, blank=True, default="")
    shop_name = models.CharField(max_length=60)
    phone = models.CharField(max_length=32, blank=True, default="")
    legal_name = models.CharField(max_length=200, blank=True, default="")
    referrer_code = models.CharField(max_length=32, blank=True, default="")
    id_document_type = models.CharField(
        max_length=24,
        choices=IdDocumentType.choices,
        default=IdDocumentType.ID_CARD,
    )
    residential_address = models.CharField(max_length=255, blank=True, default="")
    # 本地上传的 /media/ 路径（买家侧上传接口落盘 MediaAsset 后回传）。
    # 证件照属敏感信息：仅本人提交、平台审核读取（dev 演示用途，不做额外加密）。
    logo_image_url = models.CharField(max_length=500, blank=True, default="")
    id_document_image_url = models.CharField(max_length=500, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    reject_reason = models.TextField(blank=True, default="")
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        "accounts_staff.StaffAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_merchant_applications",
    )
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="applications",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "merchant_application"
        ordering = ["-submitted_at", "-pk"]
        indexes = [
            models.Index(fields=["status", "submitted_at"], name="merchant_apply_status_idx")
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
