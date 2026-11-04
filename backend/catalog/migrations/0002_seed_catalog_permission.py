from django.db import migrations


def seed_catalog_permission(apps, schema_editor):
    permission_model = apps.get_model("accounts_staff", "PlatformPermission")
    role_model = apps.get_model("accounts_staff", "PlatformRole")
    permission, _ = permission_model.objects.update_or_create(
        code="catalog.taxonomy.manage",
        defaults={
            "name": "Manage catalogue taxonomy",
            "description": "Manage category trees, mappings, brands and attribute definitions.",
        },
    )
    platform_admin = role_model.objects.filter(code="platform_admin").first()
    if platform_admin:
        platform_admin.permissions.add(permission)


def unseed_catalog_permission(apps, schema_editor):
    permission_model = apps.get_model("accounts_staff", "PlatformPermission")
    permission_model.objects.filter(code="catalog.taxonomy.manage").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts_staff", "0002_seed_rbac"),
        ("catalog", "0001_initial"),
    ]

    operations = [migrations.RunPython(seed_catalog_permission, unseed_catalog_permission)]
