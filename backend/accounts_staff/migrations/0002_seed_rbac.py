from django.db import migrations

PERMISSIONS = (
    ("staff.roles.manage", "Manage staff roles", "Assign global platform roles to staff."),
    ("audit.logs.view", "View audit logs", "View platform audit log entries."),
)

ROLES = (
    (
        "platform_admin",
        "Platform administrator",
        "Full platform administration role; TOTP is mandatory.",
        True,
        ("staff.roles.manage", "audit.logs.view"),
    ),
    (
        "platform_auditor",
        "Platform auditor",
        "Read-only access to platform audit records.",
        False,
        ("audit.logs.view",),
    ),
)


def seed_rbac(apps, schema_editor):
    permission_model = apps.get_model("accounts_staff", "PlatformPermission")
    role_model = apps.get_model("accounts_staff", "PlatformRole")

    permissions = {}
    for code, name, description in PERMISSIONS:
        permission, _ = permission_model.objects.update_or_create(
            code=code,
            defaults={"name": name, "description": description},
        )
        permissions[code] = permission

    for code, name, description, is_admin, permission_codes in ROLES:
        role, _ = role_model.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "description": description,
                "is_platform_admin": is_admin,
                "is_system": True,
            },
        )
        role.permissions.set([permissions[item] for item in permission_codes])


def unseed_rbac(apps, schema_editor):
    role_model = apps.get_model("accounts_staff", "PlatformRole")
    permission_model = apps.get_model("accounts_staff", "PlatformPermission")
    role_model.objects.filter(code__in=[item[0] for item in ROLES], is_system=True).delete()
    permission_model.objects.filter(code__in=[item[0] for item in PERMISSIONS]).delete()


class Migration(migrations.Migration):
    dependencies = [("accounts_staff", "0001_initial")]

    operations = [migrations.RunPython(seed_rbac, unseed_rbac)]
