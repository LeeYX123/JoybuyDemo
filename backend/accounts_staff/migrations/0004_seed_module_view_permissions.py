"""为每个「操作权限」补齐对应的「查看权限」。

A16 要求逐模块区分查看/操作，且「操作必须同时具备查看」。历史角色只持有
``X.manage``，这里为每个 ``.manage`` 派生 ``.view`` 并授予同样持有该
``.manage`` 的角色，保证升级后既有账号不会突然失去菜单。
"""

from django.db import migrations

from accounts_staff.modules import MODULES


def seed_view_permissions(apps, schema_editor):
    Permission = apps.get_model("accounts_staff", "PlatformPermission")
    Role = apps.get_model("accounts_staff", "PlatformRole")

    for module in MODULES:
        if not module.manage.endswith(".manage"):
            continue
        permission, _ = Permission.objects.update_or_create(
            code=module.view,
            defaults={
                "name": f"查看{module.label}",
                "description": f"进入并查看{module.label}；不包含写操作。",
            },
        )
        for role in Role.objects.filter(permissions__code=module.manage).distinct():
            role.permissions.add(permission)

    # 操作日志模块的「查看」就是既有的 audit.logs.view，这里只补导出权限的说明。
    export, _ = Permission.objects.update_or_create(
        code="audit.logs.export",
        defaults={
            "name": "导出操作日志",
            "description": "按授权查询范围导出审计日志。",
        },
    )
    for role in Role.objects.filter(permissions__code="audit.logs.view"):
        role.permissions.add(export)


def unseed_view_permissions(apps, schema_editor):
    Permission = apps.get_model("accounts_staff", "PlatformPermission")
    codes = [module.view for module in MODULES if module.manage.endswith(".manage")]
    codes.append("audit.logs.export")
    Permission.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):
    dependencies = [("accounts_staff", "0003_seed_commerce_permissions")]

    operations = [migrations.RunPython(seed_view_permissions, unseed_view_permissions)]
