from django.core import mail
from django.test import TestCase, override_settings

from notifications.models import NotificationMessage, NotificationTemplate
from notifications.services import (
    NotificationSendError,
    ensure_default_templates,
    notify,
    notify_order_canceled,
)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class NotificationTests(TestCase):
    def setUp(self):
        ensure_default_templates()
        self.email_template = NotificationTemplate.objects.get(
            event="ORDER_CANCELED", channel="EMAIL"
        )

    def test_template_rendering_substitutes_and_keeps_unknown(self):
        subject, body = self.email_template.render(
            {"order_id": "abc12345", "buyer_name": "Sleeper"}
        )
        self.assertEqual(subject, "Your order #abc12345 was canceled")
        self.assertIn("Sleeper", body)
        _, body_unknown = self.email_template.render({})
        self.assertTrue(body_unknown.count("order_id") >= 1)

    def test_email_send_through_dev_backend(self):
        message = notify(
            channel="EMAIL",
            event="ORDER_CANCELED",
            recipient="buyer@joybuy.test",
            context={"order_id": "abcd1234", "buyer_name": "buyer"},
        )
        self.assertEqual(message.status, "SENT")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("abcd1234", mail.outbox[0].subject)

    def test_sms_without_provider_fails_openly(self):
        with self.assertRaises(NotificationSendError) as raised:
            notify(
                channel="SMS",
                event="ORDER_CANCELED",
                recipient="+447000000000",
                context={"order_id": "x"},
            )
        self.assertEqual(raised.exception.code, "SMS_PROVIDER_UNAVAILABLE")
        failed = NotificationMessage.objects.get(channel="SMS")
        self.assertEqual(failed.status, "FAILED")

    def test_missing_template_is_explicit(self):
        NotificationTemplate.objects.all().delete()
        with self.assertRaises(NotificationSendError) as raised:
            notify(
                channel="EMAIL",
                event="ORDER_CANCELED",
                recipient="x@joybuy.test",
                context={},
            )
        self.assertEqual(raised.exception.code, "TEMPLATE_NOT_FOUND")

    def test_order_timeout_notification_best_effort(self):
        class FakeAccount:
            email = "timeout@joybuy.test"

        class FakeOrder:
            account = FakeAccount()
            public_id = "fake-order-id"

        sent = notify_order_canceled(FakeOrder())
        self.assertEqual(sent, 1)
        self.assertEqual(len(mail.outbox), 1)
