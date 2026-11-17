"""频道页 banner 的权限码种子。

与首页活动卡片 / 轮播图同一套逐模块 read/write 口径：
``cms.channel_banners.manage``（编辑）隐式包含
``cms.channel_banners.view``（查看）。
"""

from django.db import migrations

PERMISSIONS = (
    ("cms.channel_banners.manage", "频道页 banner 管理"),
    ("cms.channel_banners.view", "频道页 banner 查看"),
)

ROLES = ("platform_admin", "platform_operator")


def seed(apps, schema_editor):
    Permission = apps.get_model("accounts_staff", "PlatformPermission")
    Role = apps.get_model("accounts_staff", "PlatformRole")

    created = {}
    for code, name in PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(code=code, defaults={"name": name})
        created[code] = permission

    for role_code in ROLES:
        role = Role.objects.filter(code=role_code).first()
        if role is None:
            continue
        existing = set(role.permissions.values_list("code", flat=True))
        role.permissions.add(*[p for p in created.values() if p.code not in existing])

    # 查看角色（只读审计等）若存在，补 view 权限。
    for role in Role.objects.filter(code__endswith="_viewer"):
        role.permissions.add(created["cms.channel_banners.view"])


def unseed(apps, schema_editor):
    Permission = apps.get_model("accounts_staff", "PlatformPermission")
    Permission.objects.filter(code__in=[code for code, _name in PERMISSIONS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0008_channelbanner"),
        ("accounts_staff", "0004_seed_module_view_permissions"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
