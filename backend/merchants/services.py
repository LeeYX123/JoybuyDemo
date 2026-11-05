import hashlib

from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts_staff.models import StaffAccount
from merchants.models import Merchant, MerchantMembership, MerchantSourceMapping

IMPORT_FALLBACK_SLUG = "joybuy-self-operated-import"
IMPORT_FALLBACK_NAME = "Joybuy 自营导入"


def get_import_fallback_merchant() -> Merchant:
    return Merchant.objects.get(slug=IMPORT_FALLBACK_SLUG, is_system=True)


def _source_merchant_slug(source_system: str, source_seller_id: str) -> str:
    fingerprint = hashlib.sha256(f"{source_system}:{source_seller_id}".encode()).hexdigest()[:24]
    return f"source-{fingerprint}"


def resolve_import_merchant(
    *,
    source_system: str,
    source_seller_id: str | None,
    source_name: str = "",
    source_url: str = "",
) -> Merchant:
    normalized_system = source_system.strip().casefold()
    if not normalized_system:
        raise ValueError("source_system is required")

    normalized_seller_id = (source_seller_id or "").strip()
    if not normalized_seller_id:
        return get_import_fallback_merchant()

    existing = (
        MerchantSourceMapping.objects.select_related("merchant")
        .filter(
            source_system=normalized_system,
            source_seller_id=normalized_seller_id,
        )
        .first()
    )
    if existing:
        fields = []
        if existing.source_name != source_name.strip():
            existing.source_name = source_name.strip()
            fields.append("source_name")
        if existing.source_url != source_url.strip():
            existing.source_url = source_url.strip()
            fields.append("source_url")
        existing.last_seen_at = timezone.now()
        fields.extend(["last_seen_at", "updated_at"])
        existing.save(update_fields=fields)
        return existing.merchant

    try:
        with transaction.atomic():
            merchant, _ = Merchant.objects.get_or_create(
                slug=_source_merchant_slug(normalized_system, normalized_seller_id),
                defaults={
                    "display_name": source_name.strip()
                    or f"Imported seller {normalized_seller_id}",
                    "merchant_type": Merchant.Type.SOURCE_VIRTUAL,
                    "onboarding_status": Merchant.OnboardingStatus.ACTIVE,
                    "is_system": True,
                    "activated_at": timezone.now(),
                },
            )
            MerchantSourceMapping.objects.create(
                merchant=merchant,
                source_system=normalized_system,
                source_seller_id=normalized_seller_id,
                source_name=source_name.strip(),
                source_url=source_url.strip(),
                last_seen_at=timezone.now(),
            )
            return merchant
    except IntegrityError:
        return (
            MerchantSourceMapping.objects.select_related("merchant")
            .get(
                source_system=normalized_system,
                source_seller_id=normalized_seller_id,
            )
            .merchant
        )


def get_active_membership(*, staff: StaffAccount, merchant: Merchant) -> MerchantMembership | None:
    if not merchant.is_active:
        return None
    return (
        MerchantMembership.objects.select_related("role", "merchant")
        .filter(
            staff=staff,
            merchant=merchant,
            status=MerchantMembership.Status.ACTIVE,
        )
        .first()
    )


def has_merchant_permission(
    *, staff: StaffAccount, merchant: Merchant, permission_code: str
) -> bool:
    membership = get_active_membership(staff=staff, merchant=merchant)
    if membership is None:
        return False
    return membership.role.permissions.filter(code=permission_code).exists()


def accessible_merchant_ids(staff: StaffAccount, permission_code: str):
    return MerchantMembership.objects.filter(
        staff=staff,
        status=MerchantMembership.Status.ACTIVE,
        merchant__onboarding_status=Merchant.OnboardingStatus.ACTIVE,
        role__permissions__code=permission_code,
    ).values_list("merchant_id", flat=True)


# --------------------------------------------------------------------------
# 平台管理后台「商家管理」（A02）
# --------------------------------------------------------------------------


class MerchantAdminError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def generate_referral_code() -> str:
    import secrets

    while True:
        code = f"M{secrets.token_hex(4).upper()}"
        if not Merchant.objects.filter(referral_code=code).exists():
            return code


def ensure_referral_code(merchant: Merchant) -> str:
    if merchant.referral_code:
        return merchant.referral_code
    code = generate_referral_code()
    Merchant.objects.filter(pk=merchant.pk).update(referral_code=code)
    merchant.referral_code = code
    return code


def _unique_slug(display_name: str) -> str:
    from django.utils.text import slugify

    base = slugify(display_name, allow_unicode=False) or "merchant"
    candidate = base[:90]
    suffix = 1
    while Merchant.objects.filter(slug=candidate).exists():
        suffix += 1
        candidate = f"{base[:84]}-{suffix}"
    return candidate


def create_merchant(
    *,
    display_name: str,
    legal_name: str = "",
    avatar_url: str = "",
    admission_approved: bool = False,
    require_deposit: bool = False,
    deposit_required=None,
    ban_after_days: int = 4,
) -> Merchant:
    """管理端补录商家（正式入驻申请由用户端提交，这里供演示与迁移补数据）。"""

    name = (display_name or "").strip()
    if not name:
        raise MerchantAdminError("NAME_REQUIRED", "店铺名称不能为空。")
    if len(name) > 160:
        raise MerchantAdminError("NAME_TOO_LONG", "店铺名称不能超过 160 个字符。")
    if ban_after_days < 1:
        raise MerchantAdminError("BAN_DAYS_INVALID", "未发货封店天数至少为 1 天。")

    status = (
        Merchant.OnboardingStatus.ACTIVE
        if admission_approved
        else Merchant.OnboardingStatus.PENDING_REVIEW
    )
    merchant = Merchant.objects.create(
        slug=_unique_slug(name),
        display_name=name,
        legal_name=legal_name.strip(),
        avatar_url=avatar_url.strip(),
        onboarding_status=status,
        admission_approved=admission_approved,
        admission_reviewed_at=timezone.now() if admission_approved else None,
        activated_at=timezone.now() if admission_approved else None,
        deposit_enabled=require_deposit,
        deposit_required=deposit_required if require_deposit else None,
        deposit_initial_paid=not require_deposit,
        ban_after_days=ban_after_days,
        referral_code=generate_referral_code(),
    )
    return merchant


def review_admission(
    merchant: Merchant,
    *,
    approved: bool,
    require_deposit: bool = False,
    deposit_required=None,
    ban_after_days: int = 4,
) -> Merchant:
    """入驻审核。保证金启用/免缴在首次审核通过后永久锁定。"""

    with transaction.atomic():
        locked = Merchant.objects.select_for_update().get(pk=merchant.pk)
        if locked.admission_reviewed_at is not None:
            raise MerchantAdminError(
                "ADMISSION_LOCKED",
                "该商家已完成入驻审核，保证金与封店天数规则不可再次修改。",
            )
        if ban_after_days < 1:
            raise MerchantAdminError("BAN_DAYS_INVALID", "未发货封店天数至少为 1 天。")

        if not approved:
            locked.onboarding_status = Merchant.OnboardingStatus.REJECTED
            locked.admission_approved = False
            locked.admission_reviewed_at = None
            locked.save(
                update_fields=[
                    "onboarding_status",
                    "admission_approved",
                    "admission_reviewed_at",
                    "updated_at",
                ]
            )
            return locked

        if require_deposit:
            amount = deposit_required
            if amount is None or amount <= 0:
                raise MerchantAdminError(
                    "DEPOSIT_AMOUNT_REQUIRED",
                    "启用保证金时必须填写大于 0 的应缴金额。",
                )
            locked.deposit_enabled = True
            locked.deposit_required = amount
            locked.deposit_initial_paid = False
            locked.onboarding_status = Merchant.OnboardingStatus.PENDING_DEPOSIT
        else:
            locked.deposit_enabled = False
            locked.deposit_required = None
            locked.deposit_initial_paid = True
            locked.onboarding_status = Merchant.OnboardingStatus.ACTIVE
            locked.activated_at = timezone.now()

        locked.admission_approved = True
        locked.admission_reviewed_at = timezone.now()
        locked.ban_after_days = ban_after_days
        locked.save(
            update_fields=[
                "deposit_enabled",
                "deposit_required",
                "deposit_initial_paid",
                "onboarding_status",
                "activated_at",
                "admission_approved",
                "admission_reviewed_at",
                "ban_after_days",
                "updated_at",
            ]
        )
        return locked


def update_merchant_profile(
    merchant: Merchant,
    *,
    display_name=None,
    avatar_url=None,
    legal_name=None,
) -> Merchant:
    fields = []
    if display_name is not None:
        name = display_name.strip()
        if not name:
            raise MerchantAdminError("NAME_REQUIRED", "店铺名称不能为空。")
        if len(name) > 160:
            raise MerchantAdminError("NAME_TOO_LONG", "店铺名称不能超过 160 个字符。")
        merchant.display_name = name
        fields.append("display_name")
    if avatar_url is not None:
        merchant.avatar_url = avatar_url.strip()
        fields.append("avatar_url")
    if legal_name is not None:
        merchant.legal_name = legal_name.strip()
        fields.append("legal_name")
    if fields:
        merchant.save(update_fields=[*fields, "updated_at"])
    return merchant


def set_merchant_suspension(merchant: Merchant, *, suspended: bool, reason: str = "") -> Merchant:
    with transaction.atomic():
        locked = Merchant.objects.select_for_update().get(pk=merchant.pk)
        if suspended:
            if locked.onboarding_status != Merchant.OnboardingStatus.ACTIVE:
                raise MerchantAdminError("MERCHANT_NOT_ACTIVE", "只有接单中的商家可以封店。")
            locked.onboarding_status = Merchant.OnboardingStatus.SUSPENDED
            locked.suspended_at = timezone.now()
            locked.suspend_reason = reason or "订单超时未发货"
        else:
            if locked.onboarding_status != Merchant.OnboardingStatus.SUSPENDED:
                raise MerchantAdminError("MERCHANT_NOT_SUSPENDED", "该商家当前不是封店状态。")
            locked.onboarding_status = Merchant.OnboardingStatus.ACTIVE
            locked.suspended_at = None
            locked.suspend_reason = ""
            # 解封后履约计时从此刻重新起算。
            from orders.models import MerchantOrder

            MerchantOrder.objects.filter(
                merchant=locked,
                status=MerchantOrder.Status.PENDING,
            ).update(fulfillment_reset_at=timezone.now())
        locked.save(
            update_fields=[
                "onboarding_status",
                "suspended_at",
                "suspend_reason",
                "updated_at",
            ]
        )
        return locked


def deduct_credit(merchant: Merchant, *, points, note: str = "") -> Merchant:
    from decimal import Decimal

    amount = Decimal(str(points or 0))
    if amount <= 0:
        raise MerchantAdminError("CREDIT_POINTS_INVALID", "扣分数必须为正数。")
    with transaction.atomic():
        locked = Merchant.objects.select_for_update().get(pk=merchant.pk)
        if amount > locked.credit_score:
            raise MerchantAdminError("CREDIT_EXCEEDS_CURRENT", "扣分数不能超过当前信誉分。")
        locked.credit_score = locked.credit_score - amount
        locked.save(update_fields=["credit_score", "updated_at"])
        return locked


def add_followers(merchant: Merchant, *, count: int) -> Merchant:
    if count <= 0:
        raise MerchantAdminError("COUNT_INVALID", "新增关注必须是正整数。")
    today = timezone.localdate()
    with transaction.atomic():
        locked = Merchant.objects.select_for_update().get(pk=merchant.pk)
        if locked.follow_day != today:
            locked.follow_day = today
            locked.follow_delta = 0
        locked.followers += count
        locked.follow_delta += count
        locked.save(update_fields=["followers", "follow_delta", "follow_day", "updated_at"])
        return locked


def add_exposure(merchant: Merchant, *, count: int) -> Merchant:
    if count <= 0:
        raise MerchantAdminError("COUNT_INVALID", "新增曝光必须是正整数。")
    with transaction.atomic():
        locked = Merchant.objects.select_for_update().get(pk=merchant.pk)
        locked.exposure += count
        locked.save(update_fields=["exposure", "updated_at"])
        return locked
