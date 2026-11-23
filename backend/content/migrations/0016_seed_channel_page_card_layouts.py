# Generated manually on 2026-11-23

"""按频道写入品类页卡片的默认展示布局（layout 是频道级属性）。

- ``row3_scroll``：健康保健（``UK-Mini-HP-Health-and-Wellness``，一屏 3 张共 6 张）
- ``grid2x2``：母婴童玩（``UK-Mini-HP-Toys-Baby-and-Kids``，2 列 × 2 行共 4 张）
- 其余频道（家居/电子/美妆/家电/户外/宠物/游戏）→ ``row3``（即字段默认值）

正向/反向都幂等：重复执行只会把对应频道写成同一值，不会报错，也不新增/删除行。
"""

from django.db import migrations

LAYOUT_BY_CHANNEL = {
    "UK-Mini-HP-Health-and-Wellness": "row3_scroll",
    "UK-Mini-HP-Toys-Baby-and-Kids": "grid2x2",
}

DEFAULT_LAYOUT = "row3"

# 其余频道显式列出，便于正向迁移时把它们从历史值纠正回 row3。
# 户外是比利时站频道，真实 code 为 ``mini-hp-nl-sports-outdoor``（非 UK-Mini-HP-Outdoor）。
OTHER_CHANNELS = (
    "UK-Mini-HP-Home-Living",
    "UK-Mini-HP-Electronics",
    "UK-Mini-HP-Beauty",
    "UK-Mini-HP-Home-Appliances",
    "mini-hp-nl-sports-outdoor",
    "UK-Mini-HP-Pets",
    "UK-Mini-HP-Gaming",
)


def apply_channel_layouts(apps, schema_editor):
    card = apps.get_model("content", "ChannelPageCard")
    for channel_code, layout in LAYOUT_BY_CHANNEL.items():
        card.objects.filter(channel_code=channel_code).exclude(layout=layout).update(layout=layout)
    card.objects.filter(channel_code__in=OTHER_CHANNELS).exclude(layout=DEFAULT_LAYOUT).update(
        layout=DEFAULT_LAYOUT
    )


def revert_channel_layouts(apps, schema_editor):
    """反向：迁移前所有卡片都是字段默认值 ``row3``。"""

    card = apps.get_model("content", "ChannelPageCard")
    card.objects.exclude(layout=DEFAULT_LAYOUT).update(layout=DEFAULT_LAYOUT)


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0015_channelpagecard_layout"),
    ]

    operations = [
        migrations.RunPython(apply_channel_layouts, revert_channel_layouts),
    ]
