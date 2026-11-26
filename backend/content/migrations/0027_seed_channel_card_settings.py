"""Seed per-channel card display limits (ADR-0002, 2026-11-26).

Default is 3 cards per channel; 母婴童玩（Toys-Baby-and-Kids）按用户口径豁免
（max_cards=NULL = 不截断）。已存在的配置行不覆盖（幂等，可重跑）。
"""

from django.db import migrations

CHANNELS = [
    "UK-Mini-HP-Home-Living",
    "UK-Mini-HP-Electronics",
    "UK-Mini-HP-Beauty",
    "UK-Mini-HP-Home-Appliances",
    "UK-Mini-HP-Health-and-Wellness",
    "mini-hp-nl-sports-outdoor",
    "UK-Mini-HP-Pets",
    "UK-Mini-HP-Gaming",
]
UNLIMITED_CHANNELS = ["UK-Mini-HP-Toys-Baby-and-Kids"]


def seed_settings(apps, schema_editor):
    setting = apps.get_model("content", "ChannelCardSetting")
    for channel_code in CHANNELS:
        setting.objects.get_or_create(channel_code=channel_code, defaults={"max_cards": 3})
    for channel_code in UNLIMITED_CHANNELS:
        setting.objects.get_or_create(channel_code=channel_code, defaults={"max_cards": None})


def revert_settings(apps, schema_editor):
    setting = apps.get_model("content", "ChannelCardSetting")
    setting.objects.filter(
        channel_code__in=[*CHANNELS, *UNLIMITED_CHANNELS]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0026_channel_card_activity_page_binding"),
    ]

    operations = [
        migrations.RunPython(seed_settings, revert_settings),
    ]
