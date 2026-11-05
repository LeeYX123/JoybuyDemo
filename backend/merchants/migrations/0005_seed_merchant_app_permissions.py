"""补齐商家端 M01–M10 的权限码与角色模板。

既有种子只有 3 个权限（成员/商品/订单），覆盖不了商家端 10 个模块。
这里按模块补权限，并给「店主」角色一次性授满，保证新商家可用。
"""

from django.db import migrations

PERMISSIONS = (
    ("merchant.dashboard.view", "查看经营看板", "查看本店订单、曝光、关注与信誉统计。"),
    ("merchant.store.manage", "管理店铺资料", "编辑店铺名称与头像。"),
    ("merchant.listings.manage", "商品上架中心", "从平台商品池上架商品到本店。"),
    ("merchant.orders.manage", "处理订单", "确认发货、查看物流节点与收益。"),
    ("merchant.wallet.manage", "钱包管理", "查看资金明细、设置钱包密码、申请提现。"),
    ("merchant.deposit.view", "保证金管理", "查看应缴与保证金记录（仅启用保证金的商家可见）。"),
    ("merchant.aftersales.manage", "售后中心", "处理用户投诉与退货、申请平台介入。"),
    ("merchant.activities.view", "平台活动中心", "参与平台活动、查看推荐码与返佣。"),
    ("merchant.messages.use", "消息中心", "查看买家咨询与平台客服会话。"),
    ("merchant.notifications.view", "平台通知中心", "查看平台通知与商品好评并回复。"),
)

OWNER_ONLY = tuple(code for code, _name, _desc in PERMISSIONS)


def seed(apps, schema_editor):
    Permission = apps.get_model("merchants", "MerchantPermission")
    Role = apps.get_model("merchants", "MerchantRole")

    created = {}
    for code, name, description in PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(
            code=code, defaults={"name": name, "description": description}
        )
        created[code] = permission

    owner = Role.objects.filter(code="merchant_owner").first()
    if owner is not None:
        wanted = [created[code] for code in OWNER_ONLY]
        existing = set(owner.permissions.values_list("code", flat=True))
        owner.permissions.add(*[p for p in wanted if p.code not in existing])

    Role.objects.update_or_create(
        code="merchant_staff",
        defaults={
            "name": "店铺运营",
            "description": "处理订单、商品与售后，不含钱包提现。",
            "is_system": True,
        },
    )
    staff_role = Role.objects.get(code="merchant_staff")
    staff_codes = (
        "merchant.dashboard.view",
        "merchant.listings.manage",
        "merchant.orders.manage",
        "merchant.aftersales.manage",
        "merchant.messages.use",
        "merchant.notifications.view",
    )
    staff_role.permissions.set([created[code] for code in staff_codes])


def unseed(apps, schema_editor):
    Permission = apps.get_model("merchants", "MerchantPermission")
    Role = apps.get_model("merchants", "MerchantRole")
    Permission.objects.filter(code__in=OWNER_ONLY).delete()
    Role.objects.filter(code="merchant_staff", is_system=True).delete()


class Migration(migrations.Migration):
    dependencies = [("merchants", "0004_backfill_merchant_accounts")]

    operations = [migrations.RunPython(seed, unseed)]
