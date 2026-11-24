# Generated manually on 2026-11-24

"""把已有品类页活动卡片纠正到「每频道多组」之前的最终基线状态。

用户逐组确认后（真站每页有多个 ``uk-pc-image-ads`` 模块，只有一部分是品类
活动卡），每个频道的最终布局如下（此时每组都还只有一组 ``group_index=0``，
真正的多组拆分与新增卡由 ``var/channel_styles_20261123/scripts/
import_channel_page_cards.py`` 导入；本迁移只负责把**已有行**摆正）：

===========  =============================  ================
频道          layout                         is_active
===========  =============================  ================
家居生活      row3                           全部 True
电子          row3                           全部 True
美妆          row3                           全部 True
家电          row3                           全部 True
健康保健      row3_scroll（一屏 3 张共 6 张）  全部 True
户外          row3                           全部 True
宠物          row3_scroll                    全部 True
母婴童玩      row2                           全部 True
游戏          row3                           全部 **False**（组 #1 是品牌卡，
                                             不保留任何品类卡，行保留不删）
===========  =============================  ================

正向/反向都幂等：只更新现存行的 ``group_index`` / ``layout`` / ``is_active``，
不新增、不删除任何行。
"""

from django.db import migrations

# 最终状态：9 个频道各自唯一一个组的布局。
FINAL_LAYOUT_BY_CHANNEL = {
    "UK-Mini-HP-Home-Living": "row3",
    "UK-Mini-HP-Electronics": "row3",
    "UK-Mini-HP-Beauty": "row3",
    "UK-Mini-HP-Home-Appliances": "row3",
    "UK-Mini-HP-Health-and-Wellness": "row3_scroll",
    "mini-hp-nl-sports-outdoor": "row3",
    "UK-Mini-HP-Pets": "row3_scroll",
    "UK-Mini-HP-Toys-Baby-and-Kids": "row2",
    "UK-Mini-HP-Gaming": "row3",
}

# 用户圈定「不保留任何组」的频道：行保留、只下线（组 #1 是真站品牌卡）。
INACTIVE_CHANNELS = ("UK-Mini-HP-Gaming",)

# 反向：恢复 0016 结束时的状态（母婴当时是 grid2x2，其余 row3 / row3_scroll）。
REVERT_LAYOUT_BY_CHANNEL = {
    "UK-Mini-HP-Health-and-Wellness": "row3_scroll",
    "UK-Mini-HP-Toys-Baby-and-Kids": "grid2x2",
}


def apply_final_state(apps, schema_editor):
    card = apps.get_model("content", "ChannelPageCard")
    # 多组拆分还没做：先把所有现存行归到第 0 组（幂等）。
    card.objects.exclude(group_index=0).update(group_index=0)

    card.objects.exclude(channel_code__in=INACTIVE_CHANNELS).filter(is_active=False).update(
        is_active=True
    )
    card.objects.filter(channel_code__in=INACTIVE_CHANNELS).exclude(is_active=False).update(
        is_active=False
    )
    for channel_code, layout in FINAL_LAYOUT_BY_CHANNEL.items():
        card.objects.filter(channel_code=channel_code).exclude(layout=layout).update(layout=layout)


def revert_final_state(apps, schema_editor):
    card = apps.get_model("content", "ChannelPageCard")
    card.objects.exclude(group_index=0).update(group_index=0)
    card.objects.exclude(is_active=True).update(is_active=True)
    for channel_code, layout in REVERT_LAYOUT_BY_CHANNEL.items():
        card.objects.filter(channel_code=channel_code).exclude(layout=layout).update(layout=layout)
    card.objects.exclude(channel_code__in=REVERT_LAYOUT_BY_CHANNEL).exclude(layout="row3").update(
        layout="row3"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0017_channelpagecard_group_index"),
    ]

    operations = [
        migrations.RunPython(apply_final_state, revert_final_state),
    ]
