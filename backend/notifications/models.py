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


class MerchantNotification(models.Model):
    """推送商家的一条通知（A11）。

    与 ``NotificationTemplate``/``NotificationMessage`` 分工不同：那两张表是
    「按模板外发邮件/短信」的出站队列，只有渲染后的正文；这里承载商家端
    「平台通知中心」的站内信——需要多轮回复、已读、商品快照与评论图片，
    且平台回复后要重新置为未读，所以单独建表。
    """

    class Kind(models.TextChoices):
        NORMAL = "NORMAL", "普通通知"
        REVIEW = "REVIEW", "商品好评"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    merchant = models.ForeignKey(
        "merchants.Merchant",
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.NORMAL)
    title = models.CharField(max_length=200)
    content = models.TextField(blank=True, default="")
    # 商品好评专用：商品快照 + 星级 + 图片，改价/下架不影响历史记录。
    spu = models.ForeignKey(
        "catalog.Spu",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merchant_notifications",
    )
    product_snapshot = models.JSONField(default=dict, blank=True)
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    images = models.JSONField(default=list, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        "accounts_staff.StaffAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_merchant_notifications",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "merchant_notification"
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(
                fields=["merchant", "read_at", "created_at"],
                name="mnotif_merchant_read_idx",
            ),
            models.Index(fields=["kind", "created_at"], name="mnotif_kind_created_idx"),
        ]


class MerchantNotificationReply(models.Model):
    """通知下的多轮回复（商家 / 平台各一侧，永不覆盖历史）。"""

    class Role(models.TextChoices):
        MERCHANT = "MERCHANT", "商家"
        PLATFORM = "PLATFORM", "平台"

    notification = models.ForeignKey(
        MerchantNotification,
        on_delete=models.CASCADE,
        related_name="replies",
    )
    role = models.CharField(max_length=16, choices=Role.choices)
    author_label = models.CharField(max_length=120, blank=True, default="")
    content = models.CharField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "merchant_notification_reply"
        ordering = ["created_at", "pk"]
        indexes = [models.Index(fields=["notification", "created_at"], name="mnotif_reply_idx")]
