import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="BuyerAccount",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("email", models.EmailField(blank=True, max_length=254, null=True, unique=True)),
                ("phone_e164", models.CharField(blank=True, max_length=16, null=True, unique=True)),
                ("password", models.CharField(max_length=128)),
                (
                    "status",
                    models.CharField(
                        choices=[("ACTIVE", "Active"), ("DISABLED", "Disabled")],
                        default="ACTIVE",
                        max_length=16,
                    ),
                ),
                ("email_verified_at", models.DateTimeField(blank=True, null=True)),
                ("phone_verified_at", models.DateTimeField(blank=True, null=True)),
                ("last_login_at", models.DateTimeField(blank=True, null=True)),
                ("disabled_at", models.DateTimeField(blank=True, null=True)),
                ("disabled_reason", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "buyer_account",
                "indexes": [
                    models.Index(fields=["status", "created_at"], name="buyer_status_created_idx")
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            ("email__isnull", False), ("phone_e164__isnull", False), _connector="OR"
                        ),
                        name="buyer_account_has_identifier",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="VerificationCode",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "channel",
                    models.CharField(
                        choices=[("EMAIL", "Email"), ("PHONE", "Phone")], max_length=16
                    ),
                ),
                ("target", models.CharField(max_length=254)),
                ("purpose", models.CharField(choices=[("REGISTER", "Register")], max_length=24)),
                ("code_digest", models.CharField(max_length=64)),
                ("expires_at", models.DateTimeField()),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("failed_attempts", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "buyer_verification_code",
                "indexes": [
                    models.Index(
                        fields=["target", "purpose", "created_at"], name="buyer_vcode_lookup_idx"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="BuyerSession",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("token_digest", models.CharField(max_length=64, unique=True)),
                ("expires_at", models.DateTimeField()),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("last_seen_at", models.DateTimeField()),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, default="", max_length=512)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sessions",
                        to="accounts_buyers.buyeraccount",
                    ),
                ),
            ],
            options={
                "db_table": "buyer_session",
                "indexes": [
                    models.Index(fields=["expires_at", "revoked_at"], name="buyer_session_exp_idx")
                ],
            },
        ),
    ]
