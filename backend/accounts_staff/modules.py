"""平台管理后台的模块目录（A16 账号与权限）。

一个模块对应两个权限码：
- ``view``：能进入模块并查看列表/详情；
- ``manage``：能在模块内执行写操作（操作权限必须同时具备查看权限）。

权限码沿用既有命名（``<module>.manage``），``view`` 由
``manage`` 的命名空间派生（``merchants.manage`` → ``merchants.view``），
这样历史角色只要持有 ``manage`` 就自动获得查看权，不会因为升级被挡在门外。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Module:
    code: str
    label: str
    group: str
    view: str
    manage: str


MODULES: tuple[Module, ...] = (
    Module("merchants", "商家管理", "交易管理", "merchants.view", "merchants.manage"),
    Module("products", "商品池管理", "交易管理", "catalog.pool.view", "catalog.pool.manage"),
    Module(
        "listings",
        "商家商品管理",
        "交易管理",
        "catalog.listings.view",
        "catalog.listings.manage",
    ),
    Module("orders", "订单管理", "交易管理", "orders.view", "orders.manage"),
    Module("finance", "资金审核", "资金与风控", "finance.view", "finance.manage"),
    Module("deposits", "保证金管理", "资金与风控", "deposits.view", "deposits.manage"),
    Module("aftersales", "售后处理", "服务与运营", "aftersales.view", "aftersales.manage"),
    Module("activities", "平台活动与返佣", "服务与运营", "activities.view", "activities.manage"),
    Module("banners", "商城首页轮播图", "服务与运营", "cms.banners.view", "cms.banners.manage"),
    Module(
        "notifications",
        "平台通知推送",
        "服务与运营",
        "notifications.view",
        "notifications.manage",
    ),
    Module("support", "客服中心", "服务与运营", "support.view", "support.manage"),
    Module("buyers", "用户端管理", "用户与权限", "buyers.view", "buyers.manage"),
    Module("whitelist", "白名单账号", "用户与权限", "whitelist.view", "whitelist.manage"),
    Module(
        "growth",
        "商家关注与曝光",
        "用户与权限",
        "merchants.growth.view",
        "merchants.growth.manage",
    ),
    Module("crawlers", "爬虫任务", "采集与基础数据", "crawler.jobs.view", "crawler.jobs.manage"),
    Module("audit", "操作日志", "用户与权限", "audit.logs.view", "audit.logs.export"),
    Module("staff", "账号与权限", "用户与权限", "staff.roles.view", "staff.roles.manage"),
)

MODULE_BY_CODE = {module.code: module for module in MODULES}

# 角色模板 → 模块 code 列表（只给 manage，view 由后端自动补齐）
ROLE_TEMPLATES = {
    "platform_admin": [module.code for module in MODULES],
    "platform_finance": ["merchants", "finance", "deposits", "activities", "audit"],
    "platform_operator": [
        "merchants",
        "products",
        "listings",
        "activities",
        "banners",
        "notifications",
        "growth",
    ],
    "platform_support": [
        "merchants",
        "aftersales",
        "support",
        "notifications",
        "buyers",
        "whitelist",
    ],
}


def module_catalog() -> list[dict]:
    return [
        {
            "code": module.code,
            "label": module.label,
            "group": module.group,
            "view": module.view,
            "manage": module.manage,
        }
        for module in MODULES
    ]
