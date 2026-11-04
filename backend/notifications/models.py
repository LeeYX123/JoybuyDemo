import uuid

from django.db import models


class NotificationTemplate(models.Model):
    class Channel(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        SMS = "SMS", "SMS"
        INBOX = "INBOX", "Site inbox"

    class Event(models.TextChoices):
        ORDER_CANCELED = "ORDER_CANCELED", "Order canceled by timeout"
        ACCOUNT_SECURITY = "ACCOUNT_SECURITY", "Account security event"

    key = models.CharField(max_length=100)
    channel = models.CharField(max_length=8, choices=Channel.choices)
    event = models.CharField(max_length=32, choices=Event.choices)
    subject = models.CharField(max_length=300)
    body = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notification_template"
        constraints = [
            models.UniqueConstraint(
                fields=["key", "channel", "event"], name="notification_template_unique"
            )
        ]

    def render(self, context: dict) -> tuple[str, str]:
        """{{var}} substitution; unknown variables stay visible, no crashes."""
        import re

        subject = re.sub(
            r"\{\{\s*(\w+)\s*\}\}",
            lambda m: str(context.get(m.group(1), f"{{{m.group(1)}}}")),
            self.subject,
        )
        body = re.sub(
            r"\{\{\s*(\w+)\s*\}\}",
            lambda m: str(context.get(m.group(1), f"{{{m.group(1)}}}")),
            self.body,
        )
        return subject, body


class NotificationMessage(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    template = models.ForeignKey(
        NotificationTemplate, on_delete=models.PROTECT, related_name="messages"
    )
    channel = models.CharField(max_length=8, choices=NotificationTemplate.Channel.choices)
    recipient = models.CharField(max_length=254)
    subject = models.CharField(max_length=300)
    body = models.TextField()
    status = models.CharField(max_length=16, default="PENDING")  # PENDING/SENT/FAILED
    error_message = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notification_message"
        indexes = [models.Index(fields=["status", "created_at"], name="notif_status_created_idx")]
