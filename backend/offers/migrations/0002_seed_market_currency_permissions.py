from django.db import migrations


def seed_market_currency_permissions(apps, schema_editor):
    currency_model = apps.get_model("offers", "Currency")
    market_model = apps.get_model("offers", "Market")
    permission_model = apps.get_model("accounts_staff", "PlatformPermission")
    role_model = apps.get_model("accounts_staff", "PlatformRole")

    gbp, _ = currency_model.objects.update_or_create(
        code="GBP",
        defaults={
            "name": "Pound sterling",
            "symbol": "£",
            "exponent": 2,
            "is_active": True,
        },
    )
    market_model.objects.update_or_create(
        code="GB",
        defaults={
            "name": "United Kingdom",
            "default_locale": "en-GB",
            "time_zone": "Europe/London",
            "default_currency": gbp,
            "is_active": True,
        },
    )

    permissions = []
    for code, name, description in (
        (
            "catalog.products.manage",
            "Manage products",
            "Manage SPUs, SKUs and their source identities.",
        ),
        (
            "offers.manage",
            "Manage offers",
            "Manage merchant offers, prices and local inventory.",
        ),
    ):
        permission, _ = permission_model.objects.update_or_create(
            code=code,
            defaults={"name": name, "description": description},
        )
        permissions.append(permission)
    platform_admin = role_model.objects.filter(code="platform_admin").first()
    if platform_admin:
        platform_admin.permissions.add(*permissions)


def unseed_market_currency_permissions(apps, schema_editor):
    market_model = apps.get_model("offers", "Market")
    currency_model = apps.get_model("offers", "Currency")
    permission_model = apps.get_model("accounts_staff", "PlatformPermission")
    market_model.objects.filter(code="GB").delete()
    currency_model.objects.filter(code="GBP").delete()
    permission_model.objects.filter(code__in=["catalog.products.manage", "offers.manage"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts_staff", "0002_seed_rbac"),
        ("offers", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_market_currency_permissions, unseed_market_currency_permissions)
    ]
