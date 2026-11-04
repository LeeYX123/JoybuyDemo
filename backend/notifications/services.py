"""Notification dispatch (WP-36): templated email/SMS/inbox messages.

Email uses Django's SMTP backend (Mailpit in dev). SMS requires an
unconfigured adapter on purpose: it returns a 503-style failure instead of
pretending to succeed. Failures keep the message row as FAILED so retries
never lose the intent.
"""

import logging

from django.core.mail import send_mail
from django.utils import timezone

from notifications.models import NotificationMessage, NotificationTemplate

logger = logging.getLogger(__name__)


class NotificationSendError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def ensure_default_templates() -> None:
    """Idempotent seed for the order-timeout and security templates."""

    defaults = (
        (
            "order-timeout-email",
            NotificationTemplate.Channel.EMAIL,
            NotificationTemplate.Event.ORDER_CANCELED,
            "Your order #{{order_id}} was canceled",
            "Hi {{buyer_name}},\n\nYour pending payment order #{{order_id}} timed out after 60 minutes and was canceled. You can place a new order at any time.\n\nJoybuy",
        ),
        (
            "order-timeout-sms",
            NotificationTemplate.Channel.SMS,
            NotificationTemplate.Event.ORDER_CANCELED,
            "Order {{order_id}} canceled",
            "Your pending order {{order_id}} timed out and was canceled.",
        ),
        (
            "account-security-email",
            NotificationTemplate.Channel.EMAIL,
            NotificationTemplate.Event.ACCOUNT_SECURITY,
            "Security update on your Joybuy account",
            "Hi {{buyer_name}},\n\n{{event_description}}\n\nIf this wasn't you, contact support immediately.\n\nJoybuy",
        ),
    )
    for key, channel, event, subject, body in defaults:
        NotificationTemplate.objects.update_or_create(
            key=key,
            channel=channel,
            event=event,
            defaults={"subject": subject, "body": body, "is_active": True},
        )


def notify(
    *,
    channel: str,
    event: str,
    recipient: str,
    context: dict,
) -> NotificationMessage:
    """Render the active template for (event, channel) and dispatch it."""

    template = NotificationTemplate.objects.filter(
        event=event, channel=channel, is_active=True
    ).first()
    if template is None:
        raise NotificationSendError(
            "TEMPLATE_NOT_FOUND", f"No active template for {event}/{channel}."
        )
    subject, body = template.render(context)
    message = NotificationMessage.objects.create(
        template=template,
        channel=channel,
        recipient=recipient,
        subject=subject,
        body=body,
    )

    try:
        if channel == NotificationTemplate.Channel.EMAIL:
            send_mail(
                subject=subject,
                message=body,
                from_email=None,
                recipient_list=[recipient],
                fail_silently=False,
            )
        elif channel == NotificationTemplate.Channel.SMS:
            # No provider configured by design; never fake success.
            raise NotificationSendError(
                "SMS_PROVIDER_UNAVAILABLE", "No SMS provider is configured."
            )
        else:  # inbox
            pass
    except NotificationSendError as exc:
        message.status = "FAILED"
        message.error_message = exc.message[:500]
        message.save(update_fields=["status", "error_message"])
        raise
    except Exception as exc:
        message.status = "FAILED"
        message.error_message = str(exc)[:500]
        message.save(update_fields=["status", "error_message"])
        raise NotificationSendError("SEND_FAILED", str(exc)) from exc

    message.status = "SENT"
    message.sent_at = timezone.now()
    message.save(update_fields=["status", "sent_at"])
    return message


def notify_order_canceled(order) -> int:
    """Best-effort timeout notification; failures never break the sweep."""

    try:
        notify(
            channel=NotificationTemplate.Channel.EMAIL,
            event=NotificationTemplate.Event.ORDER_CANCELED,
            recipient=order.account.email,
            context={
                "order_id": str(order.public_id)[:8],
                "buyer_name": order.account.email.split("@")[0],
            },
        )
        return 1
    except Exception as exc:
        logger.warning("Order timeout notification failed: %s", exc)
        return 0


def notify_order_canceled_batch(orders) -> int:
    return sum(notify_order_canceled(order) for order in orders)
