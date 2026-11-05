"""补齐平台管理后台 A02–A17 的权限码与角色模板。

管理端「账号与权限」按逐模块查看/操作授权，权限码与文档模块一一对应；
角色模板只是预填建议，真正的访问范围仍以逐模块权限为准。
"""

from django.db import migrations

PERMISSIONS = (
    ("merchants.manage", "商家管理", "审核入驻、调整店铺资金与信誉、封店解封。"),
    ("catalog.pool.manage", "商品池管理", "维护平台商品品类、图片、规格与价格。"),
    ("catalog.listings.manage", "商家商品管理", "按店铺下架商品。"),
    ("orders.manage", "订单管理", "维护订单数据、物流节点与回款。"),
    ("finance.manage", "资金审核", "商家钱包充值、提现审核与出款。"),
    ("deposits.manage", "保证金管理", "保证金充值与余额调整。"),
    ("aftersales.manage", "售后处理", "查看售后、平台介入与结论。"),
    ("activities.manage", "平台活动与推荐返佣", "维护活动、返佣规则与发放。"),
    ("cms.banners.manage", "商城首页轮播图", "管理首页轮播图。"),
    ("notifications.manage", "平台通知推送", "推送普通通知与商品好评。"),
    ("support.manage", "客服中心", "接待商家咨询。"),
    ("buyers.manage", "用户端管理", "查询商城用户与资金明细。"),
    ("whitelist.manage", "白名单账号", "配置白名单购买权限与充值。"),
    ("merchants.growth.manage", "商家关注与曝光", "调整商家关注与曝光。"),
)

ROLE_PERMISSIONS = {
    "platform_admin": tuple(code for code, _name, _desc in PERMISSIONS),
    "platform_finance": (
        "merchants.manage",
        "finance.manage",
        "deposits.manage",
        "activities.manage",
        "audit.logs.view",
    ),
    "platform_operator": (
        "merchants.manage",
        "catalog.pool.manage",
        "catalog.listings.manage",
        "activities.manage",
        "cms.banners.manage",
        "notifications.manage",
        "merchants.growth.manage",
    ),
    "platform_support": (
        "merchants.manage",
        "aftersales.manage",
        "support.manage",
        "notifications.manage",
        "buyers.manage",
        "whitelist.manage",
    ),
}

NEW_ROLES = (
    (
        "platform_finance",
        "财务审核员",
        "资金审核、保证金与返佣发放。",
        False,
    ),
    (
        "platform_operator",
        "运营专员",
        "商品池、商家商品、活动与首页轮播。",
        False,
    ),
    (
        "platform_support",
        "客服专员",
        "售后、客服会话与商家通知。",
        False,
    ),
)


def seed_permissions(apps, schema_editor):
    Permission = apps.get_model("accounts_staff", "PlatformPermission")
    Role = apps.get_model("accounts_staff", "PlatformRole")

    permissions = {}
    for code, name, description in PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={"name": name, "description": description},
        )
        permissions[code] = permission

    for code, name, description, is_admin in NEW_ROLES:
        Role.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "description": description,
                "is_platform_admin": is_admin,
                "is_system": True,
            },
        )

    for role_code, codes in ROLE_PERMISSIONS.items():
        role = Role.objects.filter(code=role_code).first()
        if role is None:
            continue
        wanted = [permissions[code] for code in codes if code in permissions]
        existing = set(role.permissions.values_list("code", flat=True))
        # 已存在的平台管理员可能被人工加过权限，这里只做并集，不回收。
        role.permissions.add(*[p for p in wanted if p.code not in existing])


def unseed_permissions(apps, schema_editor):
    Permission = apps.get_model("accounts_staff", "PlatformPermission")
    Role = apps.get_model("accounts_staff", "PlatformRole")
    Permission.objects.filter(code__in=[code for code, _n, _d in PERMISSIONS]).delete()
    Role.objects.filter(code__in=[code for code, *_rest in NEW_ROLES], is_system=True).delete()


class Migration(migrations.Migration):
    dependencies = [("accounts_staff", "0002_seed_rbac")]

    operations = [migrations.RunPython(seed_permissions, unseed_permissions)]
