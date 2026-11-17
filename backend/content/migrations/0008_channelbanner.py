import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0007_alter_homecampaigncard_options_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChannelBanner",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "public_id",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                ),
                ("channel_code", models.CharField(max_length=64)),
                ("image_url", models.CharField(max_length=1000)),
                ("href", models.CharField(blank=True, default="", max_length=1000)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "channel_banner",
                "ordering": ["sort_order", "public_id"],
                "indexes": [
                    models.Index(
                        fields=["channel_code", "enabled", "sort_order"],
                        name="channel_banner_lookup_idx",
                    )
                ],
            },
        ),
    ]
