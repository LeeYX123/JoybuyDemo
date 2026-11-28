"""买家 ↔ 平台客服统一会话（需求 21 / 批次 X）测试。

覆盖：
1. 免白名单：非白名单买家也能建线程/收发（显式断言 ``purchase_whitelisted=False``）；
2. 未登录 401；没有线程时读/写 404；建线程幂等；
3. 收发与未读双向、``after`` 增量、空/超长校验；
4. 越权：买家 A 的消息买家 B 读不到；买家会话打 admin 接口 401；无权限员工 403；
5. 管理端：列表含买家昵称/最后消息/未读、读后清零 support_unread、回复回传给买家；
6. Crisp 镜像：thread_key ``bp:{buyer}``、sender_kind（user / platform）、正文无前缀、
   会话 meta 标题是买家昵称、``crisp_status`` 回写、镜像抛错不影响落库。

Crisp 全部 mock：测试绝不真连外网。
"""

import json
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from accounts_buyers.models import BuyerAccount
from accounts_buyers.services import create_buyer_session
from accounts_staff.models import (
    PlatformPermission,
    PlatformRole,
    StaffAccount,
    StaffRoleAssignment,
)
from accounts_staff.services import create_staff_session
from merchant_ops import crisp_mirror
from merchant_ops.models import SupportChatMessage, SupportChatThread

BUYER_THREAD_URL = "/api/v1/account/support-chat/thread"
BUYER_MESSAGES_URL = "/api/v1/account/support-chat/messages"
ADMIN_THREADS_URL = "/api/v1/admin/support-chat/threads"
BUYER_PASSWORD = "Buyer#2026pass"
STAFF_PASSWORD = "Staff#2026pass"


def admin_messages_url(thread_or_id) -> str:
    public_id = getattr(thread_or_id, "public_id", thread_or_id)
    return f"{ADMIN_THREADS_URL}/{public_id}/messages"


class SupportChatTestBase(TestCase):
    def setUp(self):
        self.client.cookies.clear()
        # 买家侧不要求白名单：默认就用非白名单账号证明门禁不存在。
        self.buyer = self._make_buyer(
            "bp-buyer@joybuy.test", display_name="小明", whitelisted=False
        )
        self.other_buyer = self._make_buyer("bp-other@joybuy.test", display_name="小红")

        self.staff = StaffAccount.objects.create(
            email="bp-support@joybuy.test", display_name="客服甲", status=StaffAccount.Status.ACTIVE
        )
        self.staff.set_password(STAFF_PASSWORD)
        self.staff.save()
        self._grant(self.staff, "support.manage", "support.view")

        self.readonly_staff = StaffAccount.objects.create(
            email="bp-noperm@joybuy.test",
            display_name="无权限员工",
            status=StaffAccount.Status.ACTIVE,
        )
        self.readonly_staff.set_password(STAFF_PASSWORD)
        self.readonly_staff.save()

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _make_buyer(self, email, *, display_name="", whitelisted=True):
        buyer = BuyerAccount(email=email, password="x", display_name=display_name)
        buyer.set_password(BUYER_PASSWORD)
        buyer.purchase_whitelisted = whitelisted
        buyer.save()
        return buyer

    def _login_buyer(self, buyer=None):
        token, _session = create_buyer_session(
            account=buyer or self.buyer, ip_address="127.0.0.1", user_agent="test"
        )
        self.client.cookies["joybuy_buyer_session"] = token

    def _login_staff(self, staff=None):
        token, _session = create_staff_session(
            staff=staff or self.staff,
            ip_address="127.0.0.1",
            user_agent="test",
            totp_verified=True,
        )
        self.client.cookies["joybuy_staff_session"] = token

    def _grant(self, staff, *codes):
        role, _ = PlatformRole.objects.update_or_create(
            code=f"support-chat-role-{staff.pk}",
            defaults={"name": f"Support chat {staff.pk}", "is_system": False},
        )
        for code in codes:
            permission, _ = PlatformPermission.objects.get_or_create(
                code=code, defaults={"name": code}
            )
            role.permissions.add(permission)
        StaffRoleAssignment.objects.get_or_create(staff=staff, role=role)

    def _post_json(self, path, payload):
        return self.client.post(path, data=json.dumps(payload), content_type="application/json")

    def _create_thread(self, *, buyer=None):
        self._login_buyer(buyer)
        response = self._post_json(BUYER_THREAD_URL, {})
        self.assertEqual(response.status_code, 201, response.content)
        return SupportChatThread.objects.get(public_id=response.json()["thread"]["id"])

    def _send_buyer_message(self, thread, body, *, buyer=None):
        self._login_buyer(buyer or thread.buyer)
        return self._post_json(BUYER_MESSAGES_URL, {"body": body})

    def _send_support_message(self, thread, body):
        self._login_staff()
        return self._post_json(admin_messages_url(thread), {"body": body})


class BuyerSupportChatGateTests(SupportChatTestBase):
    def test_create_thread_requires_login(self):
        response = self._post_json(BUYER_THREAD_URL, {})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "BUYER_AUTH_REQUIRED")

    def test_messages_require_login(self):
        read = self.client.get(BUYER_MESSAGES_URL)
        self.assertEqual(read.status_code, 401)
        self.assertEqual(read.json()["error"]["code"], "BUYER_AUTH_REQUIRED")
        send = self._post_json(BUYER_MESSAGES_URL, {"body": "hi"})
        self.assertEqual(send.status_code, 401)

    def test_non_whitelisted_buyer_can_use_support_chat(self):
        """需求 21：所有登录买家都能联系平台客服，**不要求白名单**。"""

        self.assertFalse(self.buyer.purchase_whitelisted)
        thread = self._create_thread()
        self.assertEqual(thread.buyer_id, self.buyer.pk)

        sent = self._send_buyer_message(thread, "非白名单也能联系客服")
        self.assertEqual(sent.status_code, 201, sent.content)
        self.assertEqual(SupportChatMessage.objects.count(), 1)

        self._login_buyer()
        read = self.client.get(BUYER_MESSAGES_URL)
        self.assertEqual(read.status_code, 200, read.content)
        self.assertEqual([row["body"] for row in read.json()["messages"]], ["非白名单也能联系客服"])

    def test_create_thread_is_idempotent(self):
        self._login_buyer()
        first = self._post_json(BUYER_THREAD_URL, {})
        second = self._post_json(BUYER_THREAD_URL, {})
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(first.json()["thread"]["id"], second.json()["thread"]["id"])
        self.assertEqual(SupportChatThread.objects.count(), 1)
        self.assertEqual(first.json()["thread"]["buyer_unread"], 0)
        self.assertIsNone(first.json()["thread"]["last_message_at"])

    def test_messages_before_thread_returns_404(self):
        self._login_buyer()
        read = self.client.get(BUYER_MESSAGES_URL)
        self.assertEqual(read.status_code, 404)
        self.assertEqual(read.json()["error"]["code"], "THREAD_NOT_FOUND")
        send = self._post_json(BUYER_MESSAGES_URL, {"body": "先建线程"})
        self.assertEqual(send.status_code, 404)
        self.assertEqual(send.json()["error"]["code"], "THREAD_NOT_FOUND")

    def test_blank_and_too_long_body_rejected(self):
        thread = self._create_thread()
        blank = self._send_buyer_message(thread, "   ")
        self.assertEqual(blank.status_code, 400)
        self.assertEqual(blank.json()["error"]["code"], "MESSAGE_EMPTY")
        too_long = self._send_buyer_message(thread, "字" * 2001)
        self.assertEqual(too_long.status_code, 400)
        self.assertEqual(too_long.json()["error"]["code"], "MESSAGE_TOO_LONG")
        self.assertEqual(SupportChatMessage.objects.count(), 0)


class BuyerSupportChatMessageTests(SupportChatTestBase):
    def test_send_message_updates_thread_and_support_unread(self):
        thread = self._create_thread()
        response = self._send_buyer_message(thread, "请问发票怎么开？")
        self.assertEqual(response.status_code, 201, response.content)
        message = SupportChatMessage.objects.get()
        self.assertEqual(message.sender_kind, SupportChatMessage.SenderKind.BUYER)
        self.assertEqual(message.body, "请问发票怎么开？")
        thread.refresh_from_db()
        self.assertEqual(thread.support_unread, 1)
        self.assertEqual(thread.buyer_unread, 0)
        self.assertIsNotNone(thread.last_message_at)
        self.assertEqual(response.json()["message"]["id"], message.pk)

    def test_after_returns_only_newer_messages(self):
        thread = self._create_thread()
        first = self._send_buyer_message(thread, "第一条")
        self.assertEqual(first.status_code, 201)
        old_time = timezone.now() - timedelta(minutes=10)
        SupportChatMessage.objects.filter(pk=first.json()["message"]["id"]).update(
            created_at=old_time
        )
        self.assertEqual(self._send_buyer_message(thread, "第二条").status_code, 201)

        self._login_buyer()
        full = self.client.get(BUYER_MESSAGES_URL)
        self.assertEqual(len(full.json()["messages"]), 2)
        incremental = self.client.get(BUYER_MESSAGES_URL, {"after": old_time.isoformat()})
        self.assertEqual(incremental.status_code, 200)
        self.assertEqual([row["body"] for row in incremental.json()["messages"]], ["第二条"])

    def test_after_rejects_invalid_iso(self):
        self._create_thread()
        self._login_buyer()
        response = self.client.get(BUYER_MESSAGES_URL, {"after": "not-a-date"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "AFTER_INVALID")

    def test_other_buyer_cannot_read_or_send_to_my_thread(self):
        thread = self._create_thread()
        self._send_buyer_message(thread, "只给小明自己看")
        self._login_buyer(self.other_buyer)
        # B 还没有线程 → 读/写都是 404，且拿不到 A 的任何消息。
        read = self.client.get(BUYER_MESSAGES_URL)
        self.assertEqual(read.status_code, 404)
        self.assertNotIn("只给小明自己看", read.content.decode())
        self.assertEqual(self._post_json(BUYER_MESSAGES_URL, {"body": "越权"}).status_code, 404)

        # B 建自己的线程后，只看到自己的（空）会话。
        own = self._post_json(BUYER_THREAD_URL, {})
        self.assertEqual(own.status_code, 201, own.content)
        self.assertNotEqual(own.json()["thread"]["id"], str(thread.public_id))
        own_read = self.client.get(BUYER_MESSAGES_URL)
        self.assertEqual(own_read.status_code, 200)
        self.assertEqual(own_read.json()["messages"], [])
        self.assertEqual(SupportChatThread.objects.count(), 2)


class AdminSupportChatTests(SupportChatTestBase):
    def test_buyer_session_cannot_access_admin_api(self):
        self._create_thread()
        self._login_buyer()
        response = self.client.get(ADMIN_THREADS_URL)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "STAFF_AUTH_REQUIRED")

    def test_staff_without_support_permission_is_rejected(self):
        thread = self._create_thread()
        self._login_staff(self.readonly_staff)
        for path in (ADMIN_THREADS_URL, admin_messages_url(thread)):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 403, response.content)
            self.assertEqual(response.json()["error"]["code"], "STAFF_PERMISSION_DENIED")

    def test_list_threads_shows_buyer_last_message_and_unread(self):
        thread = self._create_thread()
        self._send_buyer_message(thread, "最新一条咨询")
        self._login_staff()
        response = self.client.get(ADMIN_THREADS_URL)
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        item = payload["items"][0]
        self.assertEqual(item["id"], str(thread.public_id))
        self.assertEqual(item["buyer"]["display_name"], "小明")
        self.assertEqual(item["buyer"]["email"], "bp-buyer@joybuy.test")
        self.assertEqual(item["unread"], 1)
        self.assertEqual(item["last_message"], "最新一条咨询")
        self.assertEqual(item["last_message_kind"], "buyer")

    def test_read_clears_support_unread_and_marks_messages_read(self):
        thread = self._create_thread()
        self._send_buyer_message(thread, "第一条")
        self._send_buyer_message(thread, "第二条")
        thread.refresh_from_db()
        self.assertEqual(thread.support_unread, 2)

        self._login_staff()
        response = self.client.get(admin_messages_url(thread))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.json()["messages"]), 2)
        self.assertEqual(response.json()["thread"]["unread"], 0)
        thread.refresh_from_db()
        self.assertEqual(thread.support_unread, 0)
        self.assertEqual(thread.messages.filter(read_at__isnull=True).count(), 0)

    def test_support_reply_reaches_buyer(self):
        thread = self._create_thread()
        self._send_buyer_message(thread, "能开发票吗？")

        reply = self._send_support_message(thread, "可以开电子发票")
        self.assertEqual(reply.status_code, 201, reply.content)
        self.assertEqual(reply.json()["message"]["sender_kind"], "support")
        thread.refresh_from_db()
        self.assertEqual(thread.buyer_unread, 1)

        self._login_buyer()
        response = self.client.get(BUYER_MESSAGES_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row["body"] for row in response.json()["messages"]], ["能开发票吗？", "可以开电子发票"]
        )
        self.assertEqual(response.json()["messages"][1]["sender_kind"], "support")
        self.assertEqual(response.json()["thread"]["buyer_unread"], 0)
        thread.refresh_from_db()
        self.assertEqual(thread.buyer_unread, 0)
        self.assertIsNotNone(thread.messages.get(sender_kind="support").read_at)

    def test_unknown_thread_returns_404(self):
        self._login_staff()
        response = self.client.get(admin_messages_url("00000000-0000-0000-0000-000000000000"))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "THREAD_NOT_FOUND")

    def test_support_reply_validation(self):
        thread = self._create_thread()
        blank = self._send_support_message(thread, "  ")
        self.assertEqual(blank.status_code, 400)
        self.assertEqual(blank.json()["error"]["code"], "MESSAGE_EMPTY")
        too_long = self._send_support_message(thread, "字" * 2001)
        self.assertEqual(too_long.status_code, 400)
        self.assertEqual(too_long.json()["error"]["code"], "MESSAGE_TOO_LONG")


class SupportChatCrispMirrorTests(SupportChatTestBase):
    def test_buyer_message_is_mirrored_after_commit(self):
        thread = self._create_thread()
        with mock.patch.object(crisp_mirror, "mirror_message") as mirror:
            mirror.return_value = {"status": "skipped", "session_id": "", "error": ""}
            with self.captureOnCommitCallbacks(execute=True):
                response = self._send_buyer_message(thread, "镜像这条买家消息")
        self.assertEqual(response.status_code, 201, response.content)
        mirror.assert_called_once()
        kwargs = mirror.call_args.kwargs
        self.assertEqual(kwargs["thread_key"], f"bp:{self.buyer.public_id}")
        self.assertEqual(kwargs["sender_kind"], "user")
        self.assertEqual(kwargs["sender_name"], "小明")
        self.assertEqual(kwargs["body"], "镜像这条买家消息")
        # 会话 meta 标题 = 🟢 买家昵称 ➡️ JoyBuy客服（客服端 Inbox 只认这个），带邮箱。
        self.assertEqual(kwargs["session_nickname"], "🟢 小明 ➡️ JoyBuy客服")
        self.assertEqual(kwargs["session_email"], "bp-buyer@joybuy.test")
        message = SupportChatMessage.objects.get()
        self.assertEqual(kwargs["message_id"], str(message.pk))
        message.refresh_from_db()
        self.assertEqual(message.crisp_status, SupportChatMessage.CrispStatus.SKIPPED)

    def test_support_reply_is_mirrored_as_platform_without_prefix(self):
        thread = self._create_thread()
        self._send_buyer_message(thread, "先问一句")
        with mock.patch.object(crisp_mirror, "mirror_message") as mirror:
            mirror.return_value = {"status": "sent", "session_id": "s1", "error": ""}
            with self.captureOnCommitCallbacks(execute=True):
                response = self._send_support_message(thread, "客服回复一句")
        self.assertEqual(response.status_code, 201, response.content)
        mirror.assert_called_once()
        kwargs = mirror.call_args.kwargs
        self.assertEqual(kwargs["thread_key"], f"bp:{self.buyer.public_id}")
        self.assertEqual(kwargs["sender_kind"], "platform")
        self.assertEqual(kwargs["sender_name"], crisp_mirror.platform_nickname())
        # 正文保持干净：不带 [商家]/[平台] 等前缀。
        self.assertEqual(kwargs["body"], "客服回复一句")
        # 客服回复时会话标题仍是「🟢 买家昵称 ➡️ JoyBuy客服」，不会被「系统客服」覆盖。
        self.assertEqual(kwargs["session_nickname"], "🟢 小明 ➡️ JoyBuy客服")
        reply = SupportChatMessage.objects.get(sender_kind="support")
        reply.refresh_from_db()
        self.assertEqual(reply.crisp_status, SupportChatMessage.CrispStatus.SENT)

    def test_duplicate_mirror_result_is_recorded_as_sent(self):
        thread = self._create_thread()
        with mock.patch.object(crisp_mirror, "mirror_message") as mirror:
            mirror.return_value = {
                "status": crisp_mirror.STATUS_DUPLICATE,
                "session_id": "",
                "error": "",
            }
            with self.captureOnCommitCallbacks(execute=True):
                response = self._send_buyer_message(thread, "重复镜像")
        self.assertEqual(response.status_code, 201, response.content)
        message = SupportChatMessage.objects.get()
        self.assertEqual(message.crisp_status, SupportChatMessage.CrispStatus.SENT)

    def test_mirror_crash_does_not_block_message(self):
        thread = self._create_thread()
        with mock.patch.object(crisp_mirror, "mirror_message") as mirror:
            mirror.side_effect = RuntimeError("crisp down")
            with self.captureOnCommitCallbacks(execute=True):
                response = self._send_buyer_message(thread, "镜像炸了也要落库")
        self.assertEqual(response.status_code, 201, response.content)
        message = SupportChatMessage.objects.get()
        self.assertEqual(message.body, "镜像炸了也要落库")
        self.assertIsNone(message.crisp_status)
