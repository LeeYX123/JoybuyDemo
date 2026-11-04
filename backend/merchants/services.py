import hashlib

from accounts_staff.models import StaffAccount
from django.db import IntegrityError, transaction
from django.utils import timezone

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
