"""频道页活动卡片（13.2【品类页卡片展示】）的权限码种子。

与频道页 banner / 商品楼层同一套 read/write 口径：
``cms.channel_page_cards.manage``（编辑）与 ``cms.channel_page_cards.view``
（查看，manage 隐式包含）。
"""

from django.db import migrations

PERMISSIONS = (
    ("cms.channel_page_cards.manage", "频道页活动卡片管理"),
    ("cms.channel_page_cards.view", "频道页活动卡片查看"),
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

    for role in Role.objects.filter(code__endswith="_viewer"):
        role.permissions.add(created["cms.channel_page_cards.view"])


def unseed(apps, schema_editor):
    Permission = apps.get_model("accounts_staff", "PlatformPermission")
    Permission.objects.filter(code__in=[code for code, _name in PERMISSIONS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0012_channelpagecard"),
        ("accounts_staff", "0004_seed_module_view_permissions"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
