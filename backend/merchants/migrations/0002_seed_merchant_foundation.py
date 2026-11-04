from django.db import migrations
from django.utils import timezone

MERCHANT_PERMISSIONS = (
    (
        "merchant.members.manage",
        "Manage merchant members",
        "Invite, change or disable staff memberships for a merchant.",
    ),
    (
        "merchant.catalog.manage",
        "Manage merchant catalog",
        "Manage the merchant's offers and catalogue data.",
    ),
    (
        "merchant.orders.view",
        "View merchant orders",
        "View orders belonging to the merchant.",
    ),
)

MERCHANT_ROLES = (
    (
        "merchant_owner",
        "Merchant owner",
        "Full tenant-scoped merchant access.",
        (
            "merchant.members.manage",
            "merchant.catalog.manage",
            "merchant.orders.view",
        ),
    ),
    (
        "merchant_catalog_manager",
        "Merchant catalog manager",
        "Manage catalogue data for one merchant.",
        ("merchant.catalog.manage",),
    ),
    (
        "merchant_viewer",
        "Merchant viewer",
        "Read-only order access for one merchant.",
        ("merchant.orders.view",),
    ),
)


def seed_merchant_foundation(apps, schema_editor):
    merchant_model = apps.get_model("merchants", "Merchant")
    permission_model = apps.get_model("merchants", "MerchantPermission")
    role_model = apps.get_model("merchants", "MerchantRole")
    platform_permission_model = apps.get_model("accounts_staff", "PlatformPermission")
    platform_role_model = apps.get_model("accounts_staff", "PlatformRole")

    permissions = {}
    for code, name, description in MERCHANT_PERMISSIONS:
        permission, _ = permission_model.objects.update_or_create(
            code=code,
            defaults={"name": name, "description": description},
        )
        permissions[code] = permission

    for code, name, description, permission_codes in MERCHANT_ROLES:
        role, _ = role_model.objects.update_or_create(
            code=code,
            defaults={"name": name, "description": description, "is_system": True},
        )
        role.permissions.set([permissions[item] for item in permission_codes])

    merchant_model.objects.update_or_create(
        slug="joybuy-self-operated-import",
        defaults={
            "display_name": "Joybuy 自营导入",
            "legal_name": "",
            "merchant_type": "IMPORT_FALLBACK",
            "onboarding_status": "ACTIVE",
            "requires_staff_totp": False,
            "is_system": True,
            "activated_at": timezone.now(),
        },
    )

    platform_permission, _ = platform_permission_model.objects.update_or_create(
        code="merchants.manage",
        defaults={
            "name": "Manage merchants",
            "description": "Manage merchant records and memberships from the platform.",
        },
    )
    platform_admin = platform_role_model.objects.filter(code="platform_admin").first()
    if platform_admin:
        platform_admin.permissions.add(platform_permission)


def unseed_merchant_foundation(apps, schema_editor):
    merchant_model = apps.get_model("merchants", "Merchant")
    permission_model = apps.get_model("merchants", "MerchantPermission")
    role_model = apps.get_model("merchants", "MerchantRole")
    platform_permission_model = apps.get_model("accounts_staff", "PlatformPermission")

    merchant_model.objects.filter(slug="joybuy-self-operated-import", is_system=True).delete()
    role_model.objects.filter(
        code__in=[item[0] for item in MERCHANT_ROLES],
        is_system=True,
    ).delete()
    permission_model.objects.filter(code__in=[item[0] for item in MERCHANT_PERMISSIONS]).delete()
    platform_permission_model.objects.filter(code="merchants.manage").delete()


class Migration(migrations.Migration):
    dependencies = [("merchants", "0001_initial")]

    operations = [migrations.RunPython(seed_merchant_foundation, unseed_merchant_foundation)]
