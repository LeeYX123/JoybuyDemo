"""用户 ↔ 商家会话（需求 19 / 批次 V2）测试。

覆盖：
1. 白名单门禁：非白名单建会话/读/发一律 403 ``NOT_WHITELISTED``，未登录 401；
2. 会话幂等：同一买家同一商家重复建会话返回同一条；
3. 消息收发与未读计数、``after`` 增量；
4. 越权：买家 A 看不到 B 的会话/消息，商家 X 看不到 Y 的会话；
5. Crisp 镜像：thread_key ``bm:{buyer}:{merchant}``、sender_kind、body 前缀、
   ``crisp_status`` 回写；镜像抛错不影响消息落库；
6. 买家 session payload 下发 ``purchase_whitelisted``。

Crisp 全部 mock：测试绝不真连外网。
"""

import json
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from accounts_buyers.models import BuyerAccount
from accounts_buyers.services import create_buyer_session
from accounts_staff.models import StaffAccount
from accounts_staff.services import create_staff_session
from merchant_ops import crisp_mirror
from merchant_ops.models import MerchantChatMessage, MerchantChatThread
from merchants.models import Merchant, MerchantMembership, MerchantRole

THREADS_URL = "/api/v1/account/merchant-chat/threads"
MERCHANT_CHATS_URL = "/api/v1/merchant/chats"
BUYER_PASSWORD = "Buyer#2026pass"
STAFF_PASSWORD = "Staff#2026pass"


def messages_url(thread_or_id) -> str:
    public_id = getattr(thread_or_id, "public_id", thread_or_id)
    return f"{THREADS_URL}/{public_id}/messages"


def merchant_messages_url(thread_or_id) -> str:
    public_id = getattr(thread_or_id, "public_id", thread_or_id)
    return f"{MERCHANT_CHATS_URL}/{public_id}/messages"


class MerchantChatTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner_role = MerchantRole.objects.get(code="merchant_owner")
        cls.shop = Merchant.objects.create(
            slug="chat-shop",
            display_name="会话测试店",
            onboarding_status=Merchant.OnboardingStatus.ACTIVE,
            admission_approved=True,
            deposit_initial_paid=True,
            referral_code="MCHAT00001",
        )
        cls.other_shop = Merchant.objects.create(
            slug="chat-other-shop",
            display_name="别家会话店",
            onboarding_status=Merchant.OnboardingStatus.ACTIVE,
            admission_approved=True,
            deposit_initial_paid=True,
            referral_code="MCHAT00002",
        )

        cls.staff = StaffAccount.objects.create(
            email="chat-seller@joybuy.test", display_name="会话店长", status="ACTIVE"
        )
        cls.staff.set_password(STAFF_PASSWORD)
        cls.staff.save()
        MerchantMembership.objects.create(
            merchant=cls.shop, staff=cls.staff, role=cls.owner_role, status="ACTIVE"
        )

        cls.other_staff = StaffAccount.objects.create(
            email="chat-other-seller@joybuy.test", display_name="别家店长", status="ACTIVE"
        )
        cls.other_staff.set_password(STAFF_PASSWORD)
        cls.other_staff.save()
        MerchantMembership.objects.create(
            merchant=cls.other_shop,
            staff=cls.other_staff,
            role=cls.owner_role,
            status="ACTIVE",
        )

    def setUp(self):
        self.client.cookies.clear()
        self.buyer = self._make_buyer("chat-buyer@joybuy.test", display_name="小明")
        self.other_buyer = self._make_buyer("chat-other-buyer@joybuy.test", display_name="小红")

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

    def _post_json(self, path, payload, *, merchant=None):
        kwargs = {}
        if merchant is not None:
            kwargs["HTTP_X_MERCHANT_ID"] = str(merchant.public_id)
        return self.client.post(
            path, data=json.dumps(payload), content_type="application/json", **kwargs
        )

    def _get(self, path, *, merchant=None):
        kwargs = {}
        if merchant is not None:
            kwargs["HTTP_X_MERCHANT_ID"] = str(merchant.public_id)
        return self.client.get(path, **kwargs)

    def _create_thread(self, *, buyer=None, merchant=None):
        self._login_buyer(buyer)
        response = self._post_json(THREADS_URL, {"merchant": (merchant or self.shop).slug})
        self.assertEqual(response.status_code, 201, response.content)
        return MerchantChatThread.objects.get(public_id=response.json()["thread"]["id"])

    def _send_buyer_message(self, thread, body):
        self._login_buyer(thread.buyer)
        return self._post_json(messages_url(thread), {"body": body})


class BuyerChatGateTests(MerchantChatTestBase):
    def test_create_thread_requires_login(self):
        response = self._post_json(THREADS_URL, {"merchant": self.shop.slug})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "BUYER_AUTH_REQUIRED")

    def test_non_whitelisted_buyer_is_rejected(self):
        buyer = self._make_buyer("chat-blocked@joybuy.test", whitelisted=False)
        self._login_buyer(buyer)
        response = self._post_json(THREADS_URL, {"merchant": self.shop.slug})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "NOT_WHITELISTED")
        self.assertEqual(MerchantChatThread.objects.count(), 0)

    def test_non_whitelisted_buyer_cannot_read_or_send(self):
        thread = self._create_thread()
        self._login_buyer(self.buyer)
        self._post_json(messages_url(thread), {"body": "先发一条"})
        BuyerAccount.objects.filter(pk=self.buyer.pk).update(purchase_whitelisted=False)

        self._login_buyer(self.buyer)
        read = self._get(messages_url(thread))
        self.assertEqual(read.status_code, 403)
        self.assertEqual(read.json()["error"]["code"], "NOT_WHITELISTED")
        send = self._post_json(messages_url(thread), {"body": "被拦"})
        self.assertEqual(send.status_code, 403)
        self.assertEqual(send.json()["error"]["code"], "NOT_WHITELISTED")
        self.assertEqual(MerchantChatMessage.objects.count(), 1)

    def test_unknown_merchant_returns_404(self):
        self._login_buyer()
        response = self._post_json(THREADS_URL, {"merchant": "no-such-shop"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "MERCHANT_NOT_FOUND")

    def test_missing_merchant_returns_400(self):
        self._login_buyer()
        response = self._post_json(THREADS_URL, {})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "MERCHANT_REQUIRED")

    def test_create_thread_is_idempotent(self):
        self._login_buyer()
        first = self._post_json(THREADS_URL, {"merchant": self.shop.slug})
        second = self._post_json(THREADS_URL, {"merchant": self.shop.slug})
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(first.json()["thread"]["id"], second.json()["thread"]["id"])
        self.assertEqual(MerchantChatThread.objects.count(), 1)
        payload = first.json()["thread"]
        self.assertEqual(payload["merchant"]["public_id"], self.shop.public_id)
        self.assertEqual(payload["merchant"]["display_name"], "会话测试店")
        self.assertEqual(payload["unread"], 0)
        self.assertIsNone(payload["last_message_at"])


class BuyerChatMessageTests(MerchantChatTestBase):
    def test_send_message_updates_thread_and_merchant_unread(self):
        thread = self._create_thread()
        response = self._send_buyer_message(thread, "这个支持 220V 吗？")
        self.assertEqual(response.status_code, 201, response.content)
        message = MerchantChatMessage.objects.get()
        self.assertEqual(message.sender_kind, MerchantChatMessage.SenderKind.BUYER)
        self.assertEqual(message.body, "这个支持 220V 吗？")
        thread.refresh_from_db()
        self.assertEqual(thread.merchant_unread, 1)
        self.assertEqual(thread.buyer_unread, 0)
        self.assertIsNotNone(thread.last_message_at)
        self.assertEqual(response.json()["message"]["id"], message.pk)

    def test_blank_and_too_long_body_rejected(self):
        thread = self._create_thread()
        blank = self._send_buyer_message(thread, "   ")
        self.assertEqual(blank.status_code, 400)
        self.assertEqual(blank.json()["error"]["code"], "MESSAGE_EMPTY")
        too_long = self._send_buyer_message(thread, "字" * 2001)
        self.assertEqual(too_long.status_code, 400)
        self.assertEqual(too_long.json()["error"]["code"], "MESSAGE_TOO_LONG")
        self.assertEqual(MerchantChatMessage.objects.count(), 0)

    def test_after_returns_only_newer_messages(self):
        thread = self._create_thread()
        first = self._send_buyer_message(thread, "第一条")
        self.assertEqual(first.status_code, 201)
        first_id = first.json()["message"]["id"]
        old_time = timezone.now() - timedelta(minutes=10)
        MerchantChatMessage.objects.filter(pk=first_id).update(created_at=old_time)

        second = self._send_buyer_message(thread, "第二条")
        self.assertEqual(second.status_code, 201)

        self._login_buyer()
        response = self._get(messages_url(thread))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["messages"]), 2)

        incremental = self.client.get(messages_url(thread), {"after": old_time.isoformat()})
        self.assertEqual(incremental.status_code, 200)
        bodies = [row["body"] for row in incremental.json()["messages"]]
        self.assertEqual(bodies, ["第二条"])

    def test_after_rejects_invalid_iso(self):
        thread = self._create_thread()
        self._login_buyer()
        response = self.client.get(messages_url(thread), {"after": "not-a-date"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "AFTER_INVALID")

    def test_list_threads_sorted_by_last_message(self):
        thread_a = self._create_thread(merchant=self.shop)
        thread_b = self._create_thread(merchant=self.other_shop)
        MerchantChatThread.objects.filter(pk=thread_a.pk).update(
            last_message_at=timezone.now() - timedelta(minutes=5)
        )
        MerchantChatThread.objects.filter(pk=thread_b.pk).update(last_message_at=timezone.now())
        self._login_buyer()
        response = self._get(THREADS_URL)
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.json()["items"]]
        self.assertEqual(ids, [str(thread_b.public_id), str(thread_a.public_id)])

    def test_other_buyer_cannot_access_thread(self):
        thread = self._create_thread()
        self._login_buyer(self.other_buyer)
        read = self._get(messages_url(thread))
        self.assertEqual(read.status_code, 404)
        self.assertEqual(read.json()["error"]["code"], "THREAD_NOT_FOUND")
        send = self._post_json(messages_url(thread), {"body": "越权消息"})
        self.assertEqual(send.status_code, 404)
        self.assertEqual(MerchantChatMessage.objects.count(), 0)


class MerchantChatSideTests(MerchantChatTestBase):
    def test_merchant_list_only_contains_own_threads(self):
        own = self._create_thread()
        self._send_buyer_message(own, "给本店的消息")
        foreign = self._create_thread(buyer=self.other_buyer, merchant=self.other_shop)
        self._send_buyer_message(foreign, "给别家的消息")

        self._login_staff()
        response = self._get(MERCHANT_CHATS_URL, merchant=self.shop)
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        item = payload["items"][0]
        self.assertEqual(item["id"], str(own.public_id))
        self.assertEqual(item["buyer"]["display_name"], "小明")
        self.assertEqual(item["unread"], 1)
        self.assertEqual(item["last_message"], "给本店的消息")

        self._login_staff(self.other_staff)
        other_payload = self._get(MERCHANT_CHATS_URL, merchant=self.other_shop).json()
        self.assertEqual(other_payload["total"], 1)
        self.assertEqual(other_payload["items"][0]["id"], str(foreign.public_id))

    def test_other_merchant_cannot_read_thread(self):
        thread = self._create_thread()
        self._send_buyer_message(thread, "只给本店")
        self._login_staff(self.other_staff)
        response = self._get(merchant_messages_url(thread), merchant=self.other_shop)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "THREAD_NOT_FOUND")

    def test_merchant_read_clears_unread_and_marks_messages_read(self):
        thread = self._create_thread()
        self._send_buyer_message(thread, "第一条")
        self._send_buyer_message(thread, "第二条")
        thread.refresh_from_db()
        self.assertEqual(thread.merchant_unread, 2)

        self._login_staff()
        response = self._get(merchant_messages_url(thread), merchant=self.shop)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(len(body["messages"]), 2)
        self.assertEqual(body["thread"]["unread"], 0)
        thread.refresh_from_db()
        self.assertEqual(thread.merchant_unread, 0)
        self.assertEqual(thread.messages.filter(read_at__isnull=True).count(), 0)

    def test_merchant_reply_reaches_buyer(self):
        thread = self._create_thread()
        self._send_buyer_message(thread, "能开专票吗？")

        self._login_staff()
        reply = self._post_json(
            merchant_messages_url(thread), {"body": "可以开专票"}, merchant=self.shop
        )
        self.assertEqual(reply.status_code, 201, reply.content)
        self.assertEqual(
            reply.json()["message"]["sender_kind"],
            MerchantChatMessage.SenderKind.MERCHANT,
        )
        thread.refresh_from_db()
        self.assertEqual(thread.buyer_unread, 1)
        self.assertEqual(thread.merchant_unread, 1)  # 之前没打开过会话

        self._login_buyer(self.buyer)
        response = self._get(messages_url(thread))
        self.assertEqual(response.status_code, 200)
        rows = response.json()["messages"]
        self.assertEqual([row["body"] for row in rows], ["能开专票吗？", "可以开专票"])
        self.assertEqual(rows[1]["sender_kind"], "merchant")
        self.assertEqual(response.json()["thread"]["unread"], 0)
        thread.refresh_from_db()
        self.assertEqual(thread.buyer_unread, 0)
        self.assertIsNotNone(thread.messages.get(sender_kind="merchant").read_at)

    def test_merchant_reply_validation(self):
        thread = self._create_thread()
        self._login_staff()
        blank = self._post_json(merchant_messages_url(thread), {"body": "  "}, merchant=self.shop)
        self.assertEqual(blank.status_code, 400)
        self.assertEqual(blank.json()["error"]["code"], "MESSAGE_EMPTY")
        too_long = self._post_json(
            merchant_messages_url(thread), {"body": "字" * 2001}, merchant=self.shop
        )
        self.assertEqual(too_long.status_code, 400)
        self.assertEqual(too_long.json()["error"]["code"], "MESSAGE_TOO_LONG")


class BuyerSessionWhitelistTests(MerchantChatTestBase):
    def test_session_payload_exposes_purchase_whitelisted(self):
        self._login_buyer(self.buyer)
        response = self._get("/api/v1/auth/buyer/session")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["account"]["purchase_whitelisted"])

        BuyerAccount.objects.filter(pk=self.buyer.pk).update(purchase_whitelisted=False)
        self._login_buyer(self.buyer)
        response = self._get("/api/v1/auth/buyer/session")
        self.assertFalse(response.json()["account"]["purchase_whitelisted"])
        # 既有字段不能被新增项影响。
        self.assertIn("display_name", response.json()["account"])
        self.assertIn("merchant_application_status", response.json()["account"])


class CrispMirrorWiringTests(MerchantChatTestBase):
    def test_buyer_message_is_mirrored_after_commit(self):
        thread = self._create_thread()
        with mock.patch.object(crisp_mirror, "mirror_message") as mirror:
            mirror.return_value = {"status": "skipped", "session_id": "", "error": ""}
            with self.captureOnCommitCallbacks(execute=True):
                response = self._send_buyer_message(thread, "镜像这条买家消息")
        self.assertEqual(response.status_code, 201, response.content)
        mirror.assert_called_once()
        kwargs = mirror.call_args.kwargs
        self.assertEqual(
            kwargs["thread_key"],
            f"bm:{self.buyer.public_id}:{self.shop.public_id}",
        )
        self.assertEqual(kwargs["sender_kind"], "user")
        self.assertEqual(kwargs["sender_name"], "小明")
        self.assertEqual(kwargs["body"], "镜像这条买家消息")
        # 会话 meta 标题 = 🟢 买家昵称 ➡️ 🟠 商家ID（客服端 Inbox 只认这个）+ 邮箱。
        self.assertEqual(kwargs["session_nickname"], f"🟢 小明 ➡️ 🟠 {self.shop.public_id}")
        self.assertEqual(kwargs["session_email"], "chat-buyer@joybuy.test")
        message = MerchantChatMessage.objects.get()
        self.assertEqual(kwargs["message_id"], str(message.pk))
        message.refresh_from_db()
        self.assertEqual(message.crisp_status, MerchantChatMessage.CrispStatus.SKIPPED)

    def test_merchant_reply_is_mirrored_with_merchant_kind(self):
        thread = self._create_thread()
        self._send_buyer_message(thread, "先问一句")
        self._login_staff()
        with mock.patch.object(crisp_mirror, "mirror_message") as mirror:
            mirror.return_value = {"status": "sent", "session_id": "s1", "error": ""}
            with self.captureOnCommitCallbacks(execute=True):
                response = self._post_json(
                    merchant_messages_url(thread),
                    {"body": "商家回复"},
                    merchant=self.shop,
                )
        self.assertEqual(response.status_code, 201, response.content)
        mirror.assert_called_once()
        kwargs = mirror.call_args.kwargs
        self.assertEqual(
            kwargs["thread_key"],
            f"bm:{self.buyer.public_id}:{self.shop.public_id}",
        )
        self.assertEqual(kwargs["sender_kind"], "merchant")
        self.assertEqual(kwargs["sender_name"], self.shop.display_name)
        self.assertEqual(kwargs["body"], "商家回复")
        self.assertEqual(kwargs["session_nickname"], f"🟢 小明 ➡️ 🟠 {self.shop.public_id}")
        reply = MerchantChatMessage.objects.get(sender_kind="merchant")
        reply.refresh_from_db()
        self.assertEqual(reply.crisp_status, MerchantChatMessage.CrispStatus.SENT)

    def test_duplicate_mirror_result_is_recorded_as_sent(self):
        thread = self._create_thread()
        with mock.patch.object(crisp_mirror, "mirror_message") as mirror:
            mirror.return_value = {
                "status": crisp_mirror.STATUS_DUPLICATE,
                "session_id": "",
                "error": "",
            }
            with self.captureOnCommitCallbacks(execute=True):
                response = self._send_buyer_message(thread, "重复")
        self.assertEqual(response.status_code, 201, response.content)
        message = MerchantChatMessage.objects.get()
        message.refresh_from_db()
        self.assertEqual(message.crisp_status, MerchantChatMessage.CrispStatus.SENT)

    def test_mirror_crash_does_not_block_message(self):
        thread = self._create_thread()
        with mock.patch.object(crisp_mirror, "mirror_message") as mirror:
            mirror.side_effect = RuntimeError("crisp down")
            with self.captureOnCommitCallbacks(execute=True):
                response = self._send_buyer_message(thread, "镜像炸了也要落库")
        self.assertEqual(response.status_code, 201, response.content)
        message = MerchantChatMessage.objects.get()
        self.assertEqual(message.body, "镜像炸了也要落库")
        self.assertIsNone(message.crisp_status)
