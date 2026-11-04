from django.db import migrations


def seed_crawler_permissions(apps, schema_editor):
    permission_model = apps.get_model("accounts_staff", "PlatformPermission")
    role_model = apps.get_model("accounts_staff", "PlatformRole")

    permissions = []
    for code, name, description in (
        (
            "crawler.jobs.manage",
            "Manage crawl jobs",
            "Create, start, pause and cancel crawl jobs and their runs.",
        ),
        (
            "crawler.accounts.manage",
            "Manage crawler accounts",
            "Manage crawler account sessions, risk-control pauses and reactivation.",
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


def unseed_crawler_permissions(apps, schema_editor):
    permission_model = apps.get_model("accounts_staff", "PlatformPermission")
    permission_model.objects.filter(
        code__in=["crawler.jobs.manage", "crawler.accounts.manage"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts_staff", "0002_seed_rbac"),
        ("crawler_control", "0001_initial"),
    ]

    operations = [migrations.RunPython(seed_crawler_permissions, unseed_crawler_permissions)]
