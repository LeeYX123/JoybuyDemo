"""Crisp 入站同步测试（批次 AA / 需求 23.2）。

全部 HTTP 一律 mock（``crisp_inbound._get_messages``），**绝不真连 Crisp**。覆盖：

1. 节流：20s 内不再发请求、窗口过后才拉；失败后同样占用窗口（不会打爆配额）；
2. 只认 ``from=operator`` 且 ``user.user_id`` 存在（且 != session_id）的消息 ——
   我方镜像（``user={type:"website"}``）与访客消息都不入库；
3. ``fingerprint`` 去重：重复拉取不产生重复消息；
4. 游标推进：``timestamp_after`` 用上一批最大时间戳；首次只回看 72 小时；
5. 墙钟预算：超预算立即停（只拉一批），已拉到的仍落库；
6. 失败降级：抛错也不抛给调用方，只写 ``CrispMirrorLog``（status=failed）；
7. 落库路由：``bp:`` → ``SupportChatMessage(sender_kind=support)``；
   ``merchant:`` → ``SupportMessage(sender=PLATFORM)``；``bm:`` 不支持；
8. 视图接线：买家/商家打开会话的 GET 会顺带触发一次拉取。
"""

from datetime import UTC, datetime, timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from accounts_buyers.models import BuyerAccount
from accounts_buyers.services import create_buyer_session
from accounts_staff.models import StaffAccount
from accounts_staff.services import create_staff_session
from merchant_ops import crisp_inbound, crisp_mirror
from merchant_ops.crisp_inbound import (
    STATUS_FAILED,
    STATUS_PULLED,
    STATUS_SKIPPED,
    STATUS_THROTTLED,
    STATUS_UNSUPPORTED,
    pull_conversation,
    pull_merchant_chat,
    pull_support_chat,
    pull_thread,
)
from merchant_ops.models import (
    CrispMirrorLog,
    CrispMirrorSession,
    MerchantChatMessage,
    MerchantChatThread,
    SupportChatMessage,
    SupportChatThread,
    SupportConversation,
    SupportMessage,
)
from merchants.models import Merchant, MerchantMembership, MerchantRole

CONFIGURED = {
    "CRISP_WEBSITE_ID": "website-123",
    "CRISP_WEBSITE_TOKEN": "website-token",
    "CRISP_PLUGIN_ID": "",
    "CRISP_PLUGIN_TOKEN": "",
    "CRISP_API_TOKEN_ID": "",
    "CRISP_API_TOKEN_KEY": "",
    "CRISP_API_TIER": "website",
}
NOT_CONFIGURED = {**CONFIGURED, "CRISP_WEBSITE_ID": "", "CRISP_WEBSITE_TOKEN": ""}

SESSION_ID = "session-abc"
OPERATOR_UUID = "61b9b8df-41b1-43c1-bf89-84966f49a745"


def operator_reply(fingerprint=85823551556041, when=1795425803438, content="人工回复"):
    """Crisp Inbox 里人工客服回复的真实形态（实测 A1/A5）。"""

    return {
        "type": "text",
        "from": "operator",
        "origin": "chat",
        "timestamp": when,
        "fingerprint": fingerprint,
        "content": content,
        "session_id": SESSION_ID,
        "user": {"user_id": OPERATOR_UUID, "nickname": "Joy"},
    }


def api_operator_reply(fingerprint=85823551556042, content="API 模拟的人工回复"):
    """用 website API 以 operator 身份发消息后 Crisp 的存储形态（实测 2026-11-23）：
    与真实 Inbox 回复同形，但 Crisp 会补上 ``user.type=website``。
    """

    return {
        **operator_reply(fingerprint=fingerprint, content=content),
        "user": {"user_id": OPERATOR_UUID, "type": "website", "nickname": "Joy"},
    }


def mirrored_operator(content="我们镜像的"):
    """我方 API 注入的 operator 消息：没有 user_id，user.type=website（实测 A5）。"""

    return {
        "type": "text",
        "from": "operator",
        "origin": "chat",
        "timestamp": 1795351479362,
        "fingerprint": 179535147826468,
        "content": content,
        "session_id": SESSION_ID,
        "user": {"type": "website", "nickname": "演示店铺"},
    }


def visitor_message(content="访客提问"):
    return {
        "type": "text",
        "from": "user",
        "origin": "chat",
        "timestamp": 1795351479300,
        "fingerprint": 179535147826469,
        "content": content,
        "session_id": SESSION_ID,
        "user": {"user_id": SESSION_ID, "type": "website", "nickname": "小明"},
    }


class CrispInboundBase(TestCase):
    def setUp(self):
        self.buyer = BuyerAccount(email="inbound-buyer@joybuy.test", display_name="小明")
        self.buyer.set_password("Buyer#2026pass")
        self.buyer.save()
        self.thread = SupportChatThread.objects.create(buyer=self.buyer)
        self.buyer_key = crisp_mirror.thread_key_for_support_chat(self.thread)
        CrispMirrorSession.objects.create(thread_key=self.buyer_key, session_id=SESSION_ID)

        self.merchant = Merchant.objects.create(
            slug="inbound-shop",
            display_name="入站测试店",
            onboarding_status=Merchant.OnboardingStatus.ACTIVE,
            admission_approved=True,
            deposit_initial_paid=True,
            referral_code="MCINB01",
        )
        self.conversation = SupportConversation.objects.create(
            merchant=self.merchant,
            kind=SupportConversation.Kind.PLATFORM_SUPPORT,
            peer_name="客服中心",
        )
        self.merchant_key = crisp_mirror.thread_key_for_conversation(self.conversation)
        CrispMirrorSession.objects.create(thread_key=self.merchant_key, session_id="session-mch")

    def _mock_get(self, *batches):
        """按批次返回 ``{"data": [...]}``；批次用尽后返回空批。"""

        responses = [{"data": list(batch)} for batch in batches] + [{"data": []}]
        return mock.patch.object(crisp_inbound, "_get_messages", side_effect=responses)


class CrispInboundPullTests(CrispInboundBase):
    @override_settings(**NOT_CONFIGURED)
    def test_unconfigured_returns_skipped_without_http(self):
        with self._mock_get([operator_reply()]) as http:
            result = pull_thread(self.buyer_key)

        self.assertEqual(result["status"], STATUS_SKIPPED)
        http.assert_not_called()
        self.assertFalse(SupportChatMessage.objects.exists())

    def test_without_crisp_session_is_skipped(self):
        other = BuyerAccount.objects.create(email="no-session@joybuy.test")
        thread = SupportChatThread.objects.create(buyer=other)
        with self._mock_get([operator_reply()]) as http:
            result = pull_thread(crisp_mirror.thread_key_for_support_chat(thread))

        self.assertEqual(result["status"], STATUS_SKIPPED)
        http.assert_not_called()

    @override_settings(**CONFIGURED)
    def test_throttle_blocks_second_pull_within_window(self):
        SupportChatThread.objects.filter(pk=self.thread.pk).update(
            last_inbound_at=timezone.now() - timedelta(seconds=2)
        )
        with self._mock_get([operator_reply()]) as http:
            result = pull_thread(self.buyer_key)

        self.assertEqual(result["status"], STATUS_THROTTLED)
        self.assertEqual(result["reason"], crisp_inbound.REASON_WINDOW)
        self.assertEqual(result["imported"], 0)
        http.assert_not_called()

    @override_settings(**CONFIGURED)
    def test_pull_runs_after_throttle_window(self):
        # 验收口径：节流窗口 5s（与前端 5s 轮询对齐），6s 前必须能再拉。
        self.assertEqual(crisp_inbound.INBOUND_THROTTLE_SECONDS, 5)
        SupportChatThread.objects.filter(pk=self.thread.pk).update(
            last_inbound_at=timezone.now() - timedelta(seconds=6)
        )
        with self._mock_get([operator_reply()]) as http:
            result = pull_thread(self.buyer_key)

        self.assertEqual(result["status"], STATUS_PULLED)
        self.assertEqual(http.call_count, 1)
        self.thread.refresh_from_db()
        self.assertIsNotNone(self.thread.last_inbound_at)

    @override_settings(**CONFIGURED)
    def test_minute_cap_blocks_extra_pulls(self):
        """每线程每分钟最多 12 次（5s 节流之上再兜底）。"""

        minute_start = timezone.now().replace(second=0, microsecond=0)
        SupportChatThread.objects.filter(pk=self.thread.pk).update(
            last_inbound_at=timezone.now() - timedelta(seconds=30),
            inbound_window_start=minute_start,
            inbound_window_count=crisp_inbound.INBOUND_MAX_PER_MINUTE,
        )
        with self._mock_get([operator_reply()]) as http:
            result = pull_thread(self.buyer_key)

        self.assertEqual(result["status"], STATUS_THROTTLED)
        self.assertEqual(result["reason"], crisp_inbound.REASON_MINUTE_CAP)
        http.assert_not_called()

    @override_settings(**CONFIGURED)
    def test_minute_counter_resets_on_new_minute(self):
        minute_start = timezone.now().replace(second=0, microsecond=0)
        SupportChatThread.objects.filter(pk=self.thread.pk).update(
            last_inbound_at=timezone.now() - timedelta(seconds=30),
            inbound_window_start=minute_start - timedelta(minutes=1),
            inbound_window_count=crisp_inbound.INBOUND_MAX_PER_MINUTE,
        )
        with self._mock_get([operator_reply()]):
            result = pull_thread(self.buyer_key)

        self.assertEqual(result["status"], STATUS_PULLED)
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.inbound_window_count, 1)
        self.assertEqual(self.thread.inbound_window_start, minute_start)

    @override_settings(**CONFIGURED)
    def test_first_pull_only_looks_back_window_hours(self):
        with self._mock_get([]) as http:
            pull_thread(self.buyer_key)

        session_id, after_ms, timeout = http.call_args.args
        self.assertEqual(session_id, SESSION_ID)
        self.assertEqual(timeout, crisp_inbound.CALL_BUDGET_SECONDS)
        expected = int(
            (timezone.now() - timedelta(hours=crisp_inbound.FIRST_PULL_WINDOW_HOURS)).timestamp()
            * 1000
        )
        # 允许几秒误差：window 起点是按调用时刻现算的。
        self.assertLess(abs(after_ms - expected), 10_000)

    @override_settings(**CONFIGURED)
    def test_only_operator_with_user_id_is_imported(self):
        batch = [
            mirrored_operator(),  # 我方镜像（无 user_id）→ 跳过
            {**operator_reply(fingerprint=1), "user": {"nickname": "无 user_id"}},  # → 跳过
            {**operator_reply(fingerprint=2), "user": {"user_id": SESSION_ID}},  # 访客自身 → 跳过
            visitor_message(),  # from=user → 跳过
            {**operator_reply(fingerprint=3), "type": "note"},  # 非 text → 跳过
            operator_reply(fingerprint=4, content="这条要进库"),
        ]
        with self._mock_get(batch):
            result = pull_thread(self.buyer_key)

        self.assertEqual(result["imported"], 1)
        message = SupportChatMessage.objects.get()
        self.assertEqual(message.body, "这条要进库")
        self.assertEqual(message.sender_kind, SupportChatMessage.SenderKind.SUPPORT)
        self.assertEqual(message.source, "crisp")
        self.assertEqual(message.crisp_fingerprint, 4)

    @override_settings(**CONFIGURED)
    def test_fingerprint_dedupe_survives_repeated_pull(self):
        with self._mock_get([operator_reply(fingerprint=85823551556041)]):
            pull_thread(self.buyer_key)
        # 让节流窗口失效，模拟下一轮再次拉到同一条消息。
        SupportChatThread.objects.filter(pk=self.thread.pk).update(
            last_inbound_at=timezone.now() - timedelta(seconds=30), inbound_cursor_ms=None
        )
        with self._mock_get([operator_reply(fingerprint=85823551556041)]):
            result = pull_thread(self.buyer_key)

        self.assertEqual(result["imported"], 0)
        self.assertEqual(SupportChatMessage.objects.count(), 1)

    @override_settings(**CONFIGURED)
    def test_cursor_advances_to_latest_timestamp(self):
        with self._mock_get([operator_reply(fingerprint=11, when=1795425800000)]):
            pull_thread(self.buyer_key)
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.inbound_cursor_ms, 1795425800000)

        SupportChatThread.objects.filter(pk=self.thread.pk).update(
            last_inbound_at=timezone.now() - timedelta(seconds=30)
        )
        with self._mock_get([]) as http:
            pull_thread(self.buyer_key)

        self.assertEqual(http.call_args.args[1], 1795425800000)

    @override_settings(**CONFIGURED)
    def test_buyer_unread_and_last_message_are_updated(self):
        with self._mock_get([operator_reply(fingerprint=21)]):
            pull_thread(self.buyer_key)

        self.thread.refresh_from_db()
        self.assertEqual(self.thread.buyer_unread, 1)
        self.assertIsNotNone(self.thread.last_message_at)

    @override_settings(**CONFIGURED)
    def test_one_http_request_per_pull(self):
        """配额口径：每次拉取只发 1 个 HTTP（5s 节流 → 单线程 ≤12 次/分钟）。"""

        batch = [operator_reply(fingerprint=31, when=1795425800000)]
        with self._mock_get(batch) as http:
            result = pull_thread(self.buyer_key, budget_seconds=2.0)

        self.assertEqual(result["status"], STATUS_PULLED)
        self.assertEqual(http.call_count, 1)
        self.assertEqual(SupportChatMessage.objects.count(), 1)
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.inbound_cursor_ms, 1795425800000)

    @override_settings(**CONFIGURED)
    def test_http_failure_degrades_and_still_holds_throttle(self):
        error = crisp_mirror.CrispRequestError("GET messages -> timed out")
        with mock.patch.object(crisp_inbound, "_get_messages", side_effect=error):
            result = pull_thread(self.buyer_key)

        self.assertEqual(result["status"], STATUS_FAILED)
        self.assertIn("timed out", result["error"])
        log = CrispMirrorLog.objects.get(thread_key=self.buyer_key)
        self.assertEqual(log.status, CrispMirrorLog.Status.FAILED)
        self.assertEqual(log.message_id, crisp_inbound.INBOUND_LOG_MESSAGE_ID)
        # 失败也占用窗口：下一轮 5s 内不会再打 Crisp。
        self.thread.refresh_from_db()
        self.assertIsNotNone(self.thread.last_inbound_at)
        with self._mock_get([operator_reply()]) as http:
            self.assertEqual(pull_thread(self.buyer_key)["status"], STATUS_THROTTLED)
        http.assert_not_called()

    @override_settings(**CONFIGURED)
    def test_bm_key_with_unknown_ids_is_skipped(self):
        with self._mock_get([operator_reply()]) as http:
            result = pull_thread(
                "bm:11111111-1111-1111-1111-111111111111:22222222-2222-2222-2222-222222222222"
            )

        self.assertEqual(result["status"], STATUS_SKIPPED)
        http.assert_not_called()


class CrispInboundMerchantChatTests(CrispInboundBase):
    """``bm:``（买家 ↔ 商家）：Crisp 人工回复落成 ``sender_kind=support``，买卖双方都可见。"""

    def _bm_thread(self):
        thread = MerchantChatThread.objects.create(buyer=self.buyer, merchant=self.merchant)
        CrispMirrorSession.objects.create(
            thread_key=crisp_mirror.thread_key_for_merchant_chat(thread), session_id="session-bm"
        )
        return thread

    @override_settings(**CONFIGURED)
    def test_bm_reply_lands_as_support_message(self):
        thread = self._bm_thread()
        with self._mock_get([operator_reply(fingerprint=71, content="客服介入这条会话")]):
            result = pull_merchant_chat(thread)

        self.assertEqual(result["imported"], 1)
        message = MerchantChatMessage.objects.get()
        self.assertEqual(message.sender_kind, MerchantChatMessage.SenderKind.SUPPORT)
        self.assertEqual(message.body, "客服介入这条会话")
        self.assertEqual(message.source, "crisp")
        self.assertEqual(message.crisp_fingerprint, 71)
        thread.refresh_from_db()
        self.assertEqual(thread.buyer_unread, 1)
        self.assertIsNotNone(thread.last_message_at)
        self.assertIsNotNone(thread.inbound_cursor_ms)

    @override_settings(**CONFIGURED)
    def test_bm_reply_is_deduped_by_fingerprint(self):
        thread = self._bm_thread()
        with self._mock_get([operator_reply(fingerprint=72)]):
            pull_merchant_chat(thread)
        MerchantChatThread.objects.filter(pk=thread.pk).update(
            last_inbound_at=timezone.now() - timedelta(seconds=30), inbound_cursor_ms=None
        )
        thread.refresh_from_db()
        with self._mock_get([operator_reply(fingerprint=72)]):
            result = pull_merchant_chat(thread)

        self.assertEqual(result["imported"], 0)
        self.assertEqual(MerchantChatMessage.objects.filter(thread=thread).count(), 1)

    @override_settings(**CONFIGURED)
    def test_buyer_merchant_chat_get_triggers_pull(self):
        thread = self._bm_thread()
        self.buyer.purchase_whitelisted = True
        self.buyer.save(update_fields=["purchase_whitelisted"])
        token, _session = create_buyer_session(
            account=self.buyer, ip_address="127.0.0.1", user_agent="test"
        )
        self.client.cookies["joybuy_buyer_session"] = token
        with self._mock_get([operator_reply(fingerprint=73, content="买家能看到客服回复")]) as http:
            response = self.client.get(
                f"/api/v1/account/merchant-chat/threads/{thread.public_id}/messages"
            )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(http.call_count, 1)
        rows = response.json()["messages"]
        self.assertEqual([row["sender_kind"] for row in rows], ["support"])
        self.assertEqual(rows[0]["body"], "买家能看到客服回复")


class CrispInboundMerchantThreadTests(CrispInboundBase):
    @override_settings(**CONFIGURED)
    def test_merchant_thread_reply_lands_as_platform_message(self):
        with self._mock_get([operator_reply(fingerprint=41, content="平台客服人工回复")]):
            result = pull_conversation(self.conversation)

        self.assertEqual(result["imported"], 1)
        message = SupportMessage.objects.get()
        self.assertEqual(message.sender, SupportMessage.Sender.PLATFORM)
        self.assertEqual(message.author_label, "Joy")
        self.assertEqual(message.text, "平台客服人工回复")
        self.assertEqual(message.source, "crisp")
        self.assertEqual(message.crisp_fingerprint, 41)
        self.conversation.refresh_from_db()
        self.assertIsNotNone(self.conversation.last_message_at)

    def test_buyer_inquiry_conversation_is_not_pulled(self):
        inquiry = SupportConversation.objects.create(
            merchant=self.merchant, kind=SupportConversation.Kind.BUYER, peer_name="买家"
        )
        with self._mock_get([operator_reply()]) as http:
            result = pull_conversation(inquiry)

        self.assertEqual(result["status"], STATUS_UNSUPPORTED)
        http.assert_not_called()


class CrispInboundViewWiringTests(CrispInboundBase):
    def _login_buyer(self):
        token, _session = create_buyer_session(
            account=self.buyer, ip_address="127.0.0.1", user_agent="test"
        )
        self.client.cookies["joybuy_buyer_session"] = token

    @override_settings(**CONFIGURED)
    def test_buyer_messages_get_triggers_pull(self):
        self._login_buyer()
        with self._mock_get([operator_reply(fingerprint=51, content="买家能看到这条")]) as http:
            response = self.client.get("/api/v1/account/support-chat/messages")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(http.call_count, 1)
        bodies = [row["body"] for row in response.json()["messages"]]
        self.assertIn("买家能看到这条", bodies)

    @override_settings(**CONFIGURED)
    def test_merchant_detail_get_triggers_pull(self):
        staff = StaffAccount.objects.create(
            email="inbound-staff@joybuy.test",
            display_name="商家老板",
            status=StaffAccount.Status.ACTIVE,
        )
        staff.set_password("Staff#2026pass")
        staff.save()
        MerchantMembership.objects.create(
            merchant=self.merchant,
            staff=staff,
            role=MerchantRole.objects.get(code="merchant_owner"),
            status="ACTIVE",
        )
        token, _session = create_staff_session(
            staff=staff, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token

        with self._mock_get([operator_reply(fingerprint=61, content="商家能看到这条")]) as http:
            response = self.client.get(
                f"/api/v1/merchant/conversations/{self.conversation.public_id}",
                HTTP_X_MERCHANT_ID=str(self.merchant.public_id),
            )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(http.call_count, 1)
        texts = [row["text"] for row in response.json()["conversation"]["messages"]]
        self.assertIn("商家能看到这条", texts)

    @override_settings(**CONFIGURED)
    def test_pull_failure_never_breaks_buyer_request(self):
        self._login_buyer()
        with mock.patch.object(
            crisp_inbound,
            "_get_messages",
            side_effect=crisp_mirror.CrispRequestError("boom"),
        ):
            response = self.client.get("/api/v1/account/support-chat/messages")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["messages"], [])


class CrispInboundHelperTests(TestCase):
    def test_is_operator_reply_matrix(self):
        self.assertTrue(crisp_inbound.is_operator_reply(operator_reply()))
        self.assertFalse(crisp_inbound.is_operator_reply(mirrored_operator()))
        self.assertFalse(crisp_inbound.is_operator_reply(visitor_message()))
        self.assertFalse(crisp_inbound.is_operator_reply(None))
        self.assertFalse(crisp_inbound.is_operator_reply({**operator_reply(), "from": "user"}))
        self.assertFalse(crisp_inbound.is_operator_reply({**operator_reply(), "user": {}}))

    def test_api_injected_reply_with_user_id_is_accepted(self):
        """Crisp 会把 API 注入的 operator 消息补成 user.type=website —— 不能因此误杀。"""

        self.assertTrue(crisp_inbound.is_operator_reply(api_operator_reply()))

    def test_fingerprint_falls_back_to_stable_hash_when_missing(self):
        item = {**operator_reply(), "fingerprint": None}
        first = crisp_inbound._fingerprint(item, SESSION_ID, "正文")
        second = crisp_inbound._fingerprint(item, SESSION_ID, "正文")
        self.assertEqual(first, second)
        self.assertLess(first, 2**53)

    def test_fingerprint_accepts_numeric_string(self):
        item = {**operator_reply(), "fingerprint": "85823551556041"}
        self.assertEqual(crisp_inbound._fingerprint(item, SESSION_ID, "正文"), 85823551556041)

    def test_resolve_target_rejects_garbage_ids(self):
        self.assertIsNone(crisp_inbound._resolve_target("bp:not-a-uuid"))
        self.assertIsNone(crisp_inbound._resolve_target(""))
        self.assertIsNone(crisp_inbound._resolve_target("bm:a:b"))

    def test_pull_support_chat_wrapper_uses_thread_key(self):
        buyer = BuyerAccount.objects.create(email="wrapper@joybuy.test")
        thread = SupportChatThread.objects.create(buyer=buyer)
        with mock.patch.object(crisp_inbound, "pull_thread") as pull:
            pull.return_value = {"status": STATUS_SKIPPED, "imported": 0, "requested": 0}
            pull_support_chat(thread)

        pull.assert_called_once_with(crisp_mirror.thread_key_for_support_chat(thread))


class CrispMirrorPayloadTests(TestCase):
    """Q8：merchant: 线程商家改访客身份；bm: 线程保持 operator。"""

    def test_merchant_visitor_payload_uses_from_user(self):
        when = datetime(2026, 11, 23, 10, 0, tzinfo=UTC)
        payload = crisp_mirror.build_message_payload(
            crisp_mirror.SENDER_MERCHANT_VISITOR,
            "演示店铺",
            "商家说的话",
            when,
            "merchant:M1",
            "77",
        )
        self.assertEqual(payload["from"], "user")
        self.assertEqual(payload["content"], "商家说的话")
        self.assertEqual(payload["user"], {"type": "website", "nickname": "演示店铺"})
        self.assertEqual(payload["timestamp"], int(when.timestamp() * 1000))
        self.assertEqual(
            payload["fingerprint"], crisp_mirror._numeric_fingerprint("merchant:M1", "77")
        )

    def test_bm_thread_merchant_stays_operator(self):
        payload = crisp_mirror.build_message_payload(
            crisp_mirror.SENDER_MERCHANT, "演示店铺", "商家回复买家", None, "bm:B1:M1", "78"
        )
        self.assertEqual(payload["from"], "operator")
        self.assertEqual(payload["user"], {"type": "website", "nickname": "演示店铺"})

    def test_platform_payload_stays_operator(self):
        payload = crisp_mirror.build_message_payload(
            crisp_mirror.SENDER_PLATFORM, "客服小王", "平台回复", None, "merchant:M1", "79"
        )
        self.assertEqual(payload["from"], "operator")
        self.assertEqual(
            payload["user"], {"type": "website", "nickname": crisp_mirror.platform_nickname()}
        )


class CrispInboundModelConstraintTests(TestCase):
    def test_fingerprint_is_unique_per_thread(self):
        buyer = BuyerAccount.objects.create(email="constraint@joybuy.test")
        thread = SupportChatThread.objects.create(buyer=buyer)
        SupportChatMessage.objects.create(
            thread=thread,
            sender_kind=SupportChatMessage.SenderKind.SUPPORT,
            body="第一条",
            source="crisp",
            crisp_fingerprint=12345,
        )
        with self.assertRaises(Exception):
            SupportChatMessage.objects.create(
                thread=thread,
                sender_kind=SupportChatMessage.SenderKind.SUPPORT,
                body="重复指纹",
                source="crisp",
                crisp_fingerprint=12345,
            )

    def test_null_fingerprints_do_not_collide(self):
        buyer = BuyerAccount.objects.create(email="nullfp@joybuy.test")
        thread = SupportChatThread.objects.create(buyer=buyer)
        for index in range(2):
            SupportChatMessage.objects.create(
                thread=thread,
                sender_kind=SupportChatMessage.SenderKind.BUYER,
                body=f"本地消息 {index}",
            )
        self.assertEqual(SupportChatMessage.objects.filter(thread=thread).count(), 2)
        self.assertEqual(
            SupportChatMessage.objects.filter(thread=thread, source="local").count(), 2
        )
