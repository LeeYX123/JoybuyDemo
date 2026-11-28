"""Crisp 客服消息镜像测试（需求 18 / 批次 V）。

全部 HTTP 一律 mock：测试只验证我们发给 Crisp 的请求体、幂等与降级行为，
**绝不真连 Crisp**。覆盖：
- 未配置 → skipped 且零 HTTP；
- 首次会话 → 先建会话 → PATCH meta（昵称/邮箱）→ from=user 首消息 → 正式消息；
- merchant / platform / user 三种消息体（身份走 user.nickname，正文无前缀）；
- 同一 message_id 重复调用只发一次；
- HTTP 500 / 超时 → 不抛异常、日志 failed；
- transaction.on_commit 语义（提交后才发、回滚不发）；
- 商家端、管理端真实接口接线；
- crisp_mirror_check 无 token 输出。
"""

import base64
import json
from datetime import UTC, datetime
from io import BytesIO, StringIO
from types import SimpleNamespace
from unittest import mock

from django.core.management import call_command
from django.db import transaction
from django.test import TestCase, override_settings

from accounts_staff.models import (
    PlatformPermission,
    PlatformRole,
    StaffAccount,
    StaffRoleAssignment,
)
from accounts_staff.services import create_staff_session
from merchant_ops import crisp_mirror
from merchant_ops.crisp_mirror import (
    STATUS_DUPLICATE,
    STATUS_FAILED,
    STATUS_SENT,
    STATUS_SKIPPED,
    CrispRequestError,
    mirror_message,
    queue_support_message_mirror,
)
from merchant_ops.models import (
    CrispMirrorLog,
    CrispMirrorSession,
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
NOT_CONFIGURED = {
    "CRISP_WEBSITE_ID": "",
    "CRISP_WEBSITE_TOKEN": "",
    "CRISP_PLUGIN_ID": "",
    "CRISP_PLUGIN_TOKEN": "",
    "CRISP_API_TOKEN_ID": "",
    "CRISP_API_TOKEN_KEY": "",
    "CRISP_API_TIER": "website",
}
PLUGIN_CONFIGURED = {
    "CRISP_WEBSITE_ID": "website-123",
    "CRISP_WEBSITE_TOKEN": "",
    "CRISP_PLUGIN_ID": "plugin-1",
    "CRISP_PLUGIN_TOKEN": "plugin-token",
    "CRISP_API_TOKEN_ID": "",
    "CRISP_API_TOKEN_KEY": "",
    "CRISP_API_TIER": "website",
}
API_CONFIGURED = {
    "CRISP_WEBSITE_ID": "website-123",
    "CRISP_WEBSITE_TOKEN": "",
    "CRISP_PLUGIN_ID": "",
    "CRISP_PLUGIN_TOKEN": "",
    "CRISP_API_TOKEN_ID": "api-id-1",
    "CRISP_API_TOKEN_KEY": "api-key-1",
    "CRISP_API_TIER": "website",
}
ALL_CONFIGURED = {
    "CRISP_WEBSITE_ID": "website-123",
    "CRISP_WEBSITE_TOKEN": "website-token",
    "CRISP_PLUGIN_ID": "plugin-1",
    "CRISP_PLUGIN_TOKEN": "plugin-token",
    "CRISP_API_TOKEN_ID": "api-id-1",
    "CRISP_API_TOKEN_KEY": "api-key-1",
    "CRISP_API_TIER": "website",
}


class CrispMirrorServiceTests(TestCase):
    thread_key = "merchant:MER001001"

    def setUp(self):
        # 失败重试的等待时间在测试里归零。
        patcher = mock.patch.object(crisp_mirror, "RETRY_DELAY_SECONDS", 0)
        patcher.start()
        self.addCleanup(patcher.stop)
        # 会话 meta PATCH 默认 mock 成功：测试绝不真连 Crisp。
        patch = mock.patch.object(crisp_mirror, "_http_patch", return_value={})
        self.patch_http = patch.start()
        self.addCleanup(patch.stop)
        # 读 meta 默认返回「已有昵称」：历史会话不会被重复补写。
        get = mock.patch.object(
            crisp_mirror, "_http_get", return_value={"data": {"nickname": "已有昵称"}}
        )
        self.get_http = get.start()
        self.addCleanup(get.stop)
        crisp_mirror._META_READY.clear()
        self.addCleanup(crisp_mirror._META_READY.clear)

    # ------------------------------------------------------------------
    # 未配置 / 降级
    # ------------------------------------------------------------------
    @override_settings(**NOT_CONFIGURED)
    def test_unconfigured_returns_skipped_without_http(self):
        with mock.patch.object(crisp_mirror, "_http_post") as http:
            result = mirror_message(
                self.thread_key, "merchant", "演示店铺", "你好", datetime.now(UTC), "101"
            )

        self.assertEqual(result["status"], STATUS_SKIPPED)
        http.assert_not_called()
        self.patch_http.assert_not_called()
        self.assertFalse(CrispMirrorSession.objects.exists())
        log = CrispMirrorLog.objects.get()
        self.assertEqual(log.status, CrispMirrorLog.Status.SKIPPED)
        self.assertEqual(log.attempts, 0)
        self.assertEqual(log.error, "")

    @override_settings(**CONFIGURED)
    def test_http_error_does_not_raise_and_is_logged_failed(self):
        with mock.patch.object(
            crisp_mirror, "_http_post", side_effect=CrispRequestError("POST x -> HTTP 500")
        ) as http:
            result = mirror_message(self.thread_key, "merchant", "演示店铺", "你好", None, "102")

        self.assertEqual(result["status"], STATUS_FAILED)
        self.assertIn("HTTP 500", result["error"])
        # 1 次同步 + 1 次重试后放弃，不无限重试。
        self.assertEqual(http.call_count, 2)
        log = CrispMirrorLog.objects.get(message_id="102")
        self.assertEqual(log.status, CrispMirrorLog.Status.FAILED)
        self.assertEqual(log.attempts, 1)
        self.assertIn("HTTP 500", log.error)

    @override_settings(**CONFIGURED)
    def test_timeout_is_mapped_to_crisp_error(self):
        with mock.patch(
            "merchant_ops.crisp_mirror.urllib.request.urlopen", side_effect=TimeoutError("timed out")
        ):
            with self.assertRaises(CrispRequestError):
                crisp_mirror._http_post("/website/w/conversation", None)

    @override_settings(**CONFIGURED)
    def test_http_500_status_is_mapped_to_crisp_error(self):
        error = crisp_mirror.urllib.error.HTTPError(
            "https://api.crisp.chat/v1/x", 500, "Server Error", {}, None
        )
        with mock.patch("merchant_ops.crisp_mirror.urllib.request.urlopen", side_effect=error):
            with self.assertRaises(CrispRequestError):
                crisp_mirror._http_post("/website/w/conversation", None)

    @override_settings(**CONFIGURED)
    def test_get_with_retry_accepts_the_uniform_send_signature(self):
        """回归：``_get_with_retry`` 用 ``send(path, payload)`` 调用，``_http_get`` 必须收两个参数。

        真实环境里「已存在会话 → 补写 meta」分支走的就是这条路径，签名不对会抛
        TypeError，导致所有后续消息都不再镜像（测试里 ``_http_get`` 一直被 mock，曾漏掉）。
        """

        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return False

            def read(self):
                return '{"data": {"nickname": "已有昵称"}}'.encode()

        with mock.patch(
            "merchant_ops.crisp_mirror.urllib.request.urlopen", return_value=_Response()
        ):
            meta = crisp_mirror.fetch_conversation_meta("session-abc")

        self.assertEqual(meta, {"nickname": "已有昵称"})

    @override_settings(**CONFIGURED)
    def test_existing_session_still_mirrors_when_meta_is_filled(self):
        """回归：已有会话（meta 为空需补写）时，消息照常发出，不会卡在 pending。"""

        CrispMirrorSession.objects.create(thread_key=self.thread_key, session_id="session-old")
        self.get_http.return_value = {"data": {"nickname": ""}}
        with mock.patch.object(crisp_mirror, "_http_post", return_value={}) as http:
            result = mirror_message(
                self.thread_key, "merchant_visitor", "演示店铺", "补写后仍要发", None, "321"
            )

        self.assertEqual(result["status"], STATUS_SENT)
        self.assertEqual(http.call_args.args[1]["content"], "补写后仍要发")

    # ------------------------------------------------------------------
    # 会话创建 + 消息体
    # ------------------------------------------------------------------
    @override_settings(**CONFIGURED)
    def test_first_message_creates_conversation_then_sends(self):
        responses = [{"error": False, "data": {"session_id": "session-abc"}}, {}, {}]
        with mock.patch.object(
            crisp_mirror, "_http_post", side_effect=responses
        ) as http:
            result = mirror_message(
                self.thread_key, "merchant", "演示店铺", "能开票吗", None, "201"
            )

        self.assertEqual(result["status"], STATUS_SENT)
        self.assertEqual(result["session_id"], "session-abc")
        self.assertEqual(http.call_count, 3)

        create_call, opening_call, message_call = http.call_args_list
        self.assertEqual(create_call.args[0], "/website/website-123/conversation")
        self.assertIsNone(create_call.args[1])

        self.assertEqual(opening_call.args[0], "/website/website-123/conversation/session-abc/message")
        self.assertEqual(opening_call.args[1]["from"], "user")
        self.assertEqual(opening_call.args[1]["content"], "Conversation started")
        # 开场消息时间早于正式消息，Inbox 预览才不会被 "Conversation started" 盖住。
        self.assertLess(
            opening_call.args[1]["timestamp"], message_call.args[1]["timestamp"]
        )

        body = message_call.args[1]
        self.assertEqual(body["from"], "operator")
        self.assertEqual(body["origin"], "chat")
        # 身份改由 user.nickname 表达：正文不再带 [商家] 前缀。
        self.assertEqual(body["content"], "能开票吗")
        self.assertEqual(body["user"], {"type": "website", "nickname": "演示店铺"})
        # Crisp 要求 fingerprint 是 number（字符串会 400 invalid_data）；同一消息稳定同值。
        self.assertIsInstance(body["fingerprint"], int)
        self.assertEqual(
            body["fingerprint"], crisp_mirror._numeric_fingerprint(self.thread_key, "201")
        )
        self.assertLess(body["fingerprint"], 2**53)

        # 建会话后先 PATCH meta（Inbox 列表显示店名而不是 anonymous）。
        self.patch_http.assert_called_once()
        meta_path, meta_body = self.patch_http.call_args.args
        self.assertEqual(meta_path, "/website/website-123/conversation/session-abc/meta")
        self.assertEqual(meta_body, {"nickname": "演示店铺"})

        self.assertEqual(
            CrispMirrorSession.objects.get().session_id, "session-abc"
        )

    @override_settings(**CONFIGURED)
    def test_session_meta_patch_carries_buyer_nickname_and_email(self):
        responses = [{"data": {"session_id": "session-abc"}}, {}, {}]
        with mock.patch.object(crisp_mirror, "_http_post", side_effect=responses):
            mirror_message(
                self.thread_key,
                "user",
                "张三",
                "包裹到哪了",
                None,
                "202",
                session_nickname="张三",
                session_email="zhangsan@example.com",
            )

        self.patch_http.assert_called_once()
        meta_path, meta_body = self.patch_http.call_args.args
        self.assertEqual(meta_path, "/website/website-123/conversation/session-abc/meta")
        self.assertEqual(
            meta_body, {"nickname": "张三", "email": "zhangsan@example.com"}
        )

    @override_settings(**CONFIGURED)
    def test_meta_patch_failure_does_not_block_message(self):
        error = CrispRequestError("PATCH /meta -> HTTP 400")
        self.patch_http.side_effect = error
        responses = [{"data": {"session_id": "session-abc"}}, {}, {}]
        with mock.patch.object(crisp_mirror, "_http_post", side_effect=responses) as http:
            result = mirror_message(
                self.thread_key, "merchant", "演示店铺", "meta 挂了也要发", None, "203"
            )

        self.assertEqual(result["status"], STATUS_SENT)
        # 失败重试 2 次后放弃，正式消息照常发送（建会话 + 开场 + 正文 = 3 次 POST）。
        self.assertEqual(self.patch_http.call_count, 2)
        self.assertEqual(http.call_count, 3)
        self.assertEqual(http.call_args_list[-1].args[1]["content"], "meta 挂了也要发")

    @override_settings(**CONFIGURED)
    def test_meta_nickname_is_truncated_to_crisp_safe_length(self):
        long_name = "商" * 60
        responses = [{"data": {"session_id": "session-abc"}}, {}, {}]
        with mock.patch.object(crisp_mirror, "_http_post", side_effect=responses):
            mirror_message(
                self.thread_key, "merchant", long_name, "长昵称", None, "204"
            )

        _path, meta_body = self.patch_http.call_args.args
        self.assertEqual(len(meta_body["nickname"]), 40)

    @override_settings(**CONFIGURED)
    def test_merchant_and_platform_messages_use_user_nickname(self):
        CrispMirrorSession.objects.create(thread_key=self.thread_key, session_id="session-abc")
        with mock.patch.object(crisp_mirror, "_http_post", return_value={}) as http:
            mirror_message(self.thread_key, "merchant", "演示店铺", "第一条", None, "301")
            mirror_message(self.thread_key, "platform", "客服小王", "第二条", None, "302")

        merchant_body = http.call_args_list[0].args[1]
        platform_body = http.call_args_list[1].args[1]
        self.assertEqual(merchant_body["content"], "第一条")
        self.assertEqual(platform_body["content"], "第二条")
        self.assertNotIn("[商家]", merchant_body["content"])
        self.assertNotIn("[平台]", platform_body["content"])
        self.assertEqual(merchant_body["from"], "operator")
        self.assertEqual(platform_body["from"], "operator")
        # user.nickname 只影响访客端 chatbox（加分项）；客服端 Inbox 不采用，靠 meta nickname。
        self.assertEqual(
            merchant_body["user"], {"type": "website", "nickname": "演示店铺"}
        )
        self.assertEqual(
            platform_body["user"], {"type": "website", "nickname": "Joybuy 客服"}
        )
        # 会话已存在且 meta 已有昵称 → 不再重复 PATCH。
        self.patch_http.assert_not_called()

    @override_settings(**CONFIGURED)
    def test_anonymous_existing_session_is_backfilled_once(self):
        CrispMirrorSession.objects.create(thread_key=self.thread_key, session_id="session-old")
        self.get_http.return_value = {"data": {"nickname": ""}}
        with mock.patch.object(crisp_mirror, "_http_post", return_value={}) as http:
            mirror_message(self.thread_key, "merchant", "演示店铺", "历史会话", None, "311")
            mirror_message(self.thread_key, "merchant", "演示店铺", "再发一条", None, "312")

        # 历史会话（meta nickname 为空）补写一次；进程内缓存后不再 GET。
        self.patch_http.assert_called_once()
        meta_path, meta_body = self.patch_http.call_args.args
        self.assertEqual(meta_path, "/website/website-123/conversation/session-old/meta")
        self.assertEqual(meta_body["nickname"], "演示店铺")
        self.assertEqual(self.get_http.call_count, 1)
        self.assertEqual(http.call_count, 2)

    @override_settings(**CONFIGURED)
    def test_existing_session_with_nickname_is_not_patched(self):
        CrispMirrorSession.objects.create(thread_key=self.thread_key, session_id="session-old")
        self.get_http.return_value = {"data": {"nickname": "小明 · 演示店铺"}}
        with mock.patch.object(crisp_mirror, "_http_post", return_value={}):
            mirror_message(self.thread_key, "merchant", "演示店铺", "已有昵称", None, "313")

        self.patch_http.assert_not_called()

    @override_settings(**CONFIGURED)
    def test_backfill_failure_does_not_block_message(self):
        CrispMirrorSession.objects.create(thread_key=self.thread_key, session_id="session-old")
        self.get_http.return_value = {"data": {"nickname": ""}}
        self.patch_http.side_effect = CrispRequestError("PATCH /meta -> HTTP 500")
        with mock.patch.object(crisp_mirror, "_http_post", return_value={}) as http:
            result = mirror_message(
                self.thread_key, "merchant", "演示店铺", "补写失败也要发", None, "314"
            )

        self.assertEqual(result["status"], STATUS_SENT)
        self.assertEqual(http.call_count, 1)
        self.assertEqual(http.call_args.args[1]["content"], "补写失败也要发")
        self.assertNotIn("session-old", crisp_mirror._META_READY)

    @override_settings(**CONFIGURED)
    def test_backfill_meta_fetch_failure_does_not_block_message(self):
        CrispMirrorSession.objects.create(thread_key=self.thread_key, session_id="session-old")
        self.get_http.side_effect = CrispRequestError("GET /meta -> HTTP 500")
        with mock.patch.object(crisp_mirror, "_http_post", return_value={}) as http:
            result = mirror_message(
                self.thread_key, "merchant", "演示店铺", "读 meta 失败也要发", None, "315"
            )

        self.assertEqual(result["status"], STATUS_SENT)
        self.assertEqual(http.call_count, 1)
        self.patch_http.assert_not_called()

    @override_settings(**{**CONFIGURED, "CRISP_PLATFORM_NICKNAME": "平台小助手"})
    def test_platform_nickname_can_be_configured(self):
        CrispMirrorSession.objects.create(thread_key=self.thread_key, session_id="session-abc")
        with mock.patch.object(crisp_mirror, "_http_post", return_value={}) as http:
            mirror_message(self.thread_key, "platform", "客服小王", "第二条", None, "303")

        self.assertEqual(
            http.call_args.args[1]["user"], {"type": "website", "nickname": "平台小助手"}
        )

    @override_settings(**CONFIGURED)
    def test_user_message_carries_nickname(self):
        CrispMirrorSession.objects.create(thread_key="buyer:abc", session_id="session-user")
        when = datetime(2026, 11, 22, 10, 30, tzinfo=UTC)
        with mock.patch.object(crisp_mirror, "_http_post", return_value={}) as http:
            result = mirror_message("buyer:abc", "user", "张三", "包裹到哪了", when, "401")

        self.assertEqual(result["status"], STATUS_SENT)
        body = http.call_args.args[1]
        self.assertEqual(body["from"], "user")
        self.assertEqual(body["content"], "包裹到哪了")
        self.assertEqual(body["user"], {"type": "website", "nickname": "张三"})
        self.assertEqual(body["timestamp"], int(when.timestamp() * 1000))

    # ------------------------------------------------------------------
    # 幂等
    # ------------------------------------------------------------------
    @override_settings(**CONFIGURED)
    def test_same_message_id_is_sent_once(self):
        CrispMirrorSession.objects.create(thread_key=self.thread_key, session_id="session-abc")
        with mock.patch.object(crisp_mirror, "_http_post", return_value={}) as http:
            first = mirror_message(self.thread_key, "merchant", "演示店铺", "只发一次", None, "501")
            second = mirror_message(self.thread_key, "merchant", "演示店铺", "只发一次", None, "501")

        self.assertEqual(first["status"], STATUS_SENT)
        self.assertEqual(second["status"], STATUS_DUPLICATE)
        self.assertEqual(http.call_count, 1)
        self.assertEqual(CrispMirrorLog.objects.count(), 1)

    @override_settings(**CONFIGURED)
    def test_skipped_message_is_retried_once_configured(self):
        with override_settings(**NOT_CONFIGURED):
            first = mirror_message(self.thread_key, "merchant", "演示店铺", "先跳过", None, "601")
        self.assertEqual(first["status"], STATUS_SKIPPED)

        CrispMirrorSession.objects.create(thread_key=self.thread_key, session_id="session-abc")
        with mock.patch.object(crisp_mirror, "_http_post", return_value={}) as http:
            second = mirror_message(self.thread_key, "merchant", "演示店铺", "先跳过", None, "601")

        self.assertEqual(second["status"], STATUS_SENT)
        self.assertEqual(http.call_count, 1)
        self.assertEqual(CrispMirrorLog.objects.get().status, CrispMirrorLog.Status.SENT)

    @override_settings(**PLUGIN_CONFIGURED)
    def test_plugin_token_is_preferred_when_both_present(self):
        self.assertEqual(crisp_mirror._credentials(), ("plugin-1", "plugin-token", "plugin"))

    # ------------------------------------------------------------------
    # workspace API token（identifier + key）
    # ------------------------------------------------------------------
    @override_settings(**API_CONFIGURED)
    def test_api_token_alone_is_configured(self):
        self.assertTrue(crisp_mirror.is_configured())
        self.assertEqual(crisp_mirror._credentials(), ("api-id-1", "api-key-1", "website"))

    @override_settings(**ALL_CONFIGURED)
    def test_api_token_takes_priority_over_plugin_and_website(self):
        self.assertEqual(crisp_mirror._credentials(), ("api-id-1", "api-key-1", "website"))

    @override_settings(**{**API_CONFIGURED, "CRISP_API_TIER": "plugin"})
    def test_api_token_tier_comes_from_setting(self):
        self.assertEqual(crisp_mirror._credentials(), ("api-id-1", "api-key-1", "plugin"))

    @override_settings(**API_CONFIGURED)
    def test_api_token_is_sent_as_basic_auth_with_tier_header(self):
        captured = {}

        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return False

            def read(self):
                return b"{}"

        def fake_urlopen(request, timeout=None):
            captured["request"] = request
            return _Response()

        with mock.patch(
            "merchant_ops.crisp_mirror.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            crisp_mirror._http_post("/website/website-123/conversation", None)

        request = captured["request"]
        expected = base64.b64encode(b"api-id-1:api-key-1").decode()
        self.assertEqual(request.get_header("Authorization"), f"Basic {expected}")
        self.assertEqual(request.get_header("X-crisp-tier"), "website")
        self.assertNotIn("website-token", request.get_header("Authorization"))

    @override_settings(**API_CONFIGURED)
    def test_meta_patch_uses_patch_method(self):
        captured = {}

        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return False

            def read(self):
                return b"{}"

        def fake_urlopen(request, timeout=None):
            captured["request"] = request
            return _Response()

        with mock.patch(
            "merchant_ops.crisp_mirror.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            crisp_mirror._http_request(
                "PATCH",
                "/website/website-123/conversation/session-abc/meta",
                {"nickname": "张三"},
            )

        request = captured["request"]
        expected_url = (
            f"{crisp_mirror.API_BASE_URL}/website/website-123/conversation/session-abc/meta"
        )
        self.assertEqual(request.get_method(), "PATCH")
        self.assertEqual(request.full_url, expected_url)
        self.assertEqual(json.loads(request.data.decode()), {"nickname": "张三"})

    @override_settings(**API_CONFIGURED)
    def test_http_error_body_is_included_in_error_message(self):
        error = crisp_mirror.urllib.error.HTTPError(
            "https://api.crisp.chat/v1/x",
            401,
            "Unauthorized",
            {},
            BytesIO(b'{"reason":"invalid_token"}'),
        )
        with mock.patch("merchant_ops.crisp_mirror.urllib.request.urlopen", side_effect=error):
            with self.assertRaises(CrispRequestError) as ctx:
                crisp_mirror._http_post("/website/website-123/conversation", None)

        message = str(ctx.exception)
        self.assertIn("HTTP 401", message)
        self.assertIn("invalid_token", message)

    # ------------------------------------------------------------------
    # on_commit 语义
    # ------------------------------------------------------------------
    def test_rollback_discards_mirror(self):
        merchant = self._merchant()
        conversation = SupportConversation.objects.create(
            merchant=merchant,
            kind=SupportConversation.Kind.PLATFORM_SUPPORT,
            peer_name="客服中心",
        )

        class Boom(Exception):
            pass

        with mock.patch.object(crisp_mirror, "mirror_message") as mirror:
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertRaises(Boom):
                    with transaction.atomic():
                        message = SupportMessage.objects.create(
                            conversation=conversation,
                            sender=SupportMessage.Sender.MERCHANT,
                            author_label=merchant.display_name,
                            text="会被回滚",
                        )
                        queue_support_message_mirror(message)
                        raise Boom

        mirror.assert_not_called()

    def test_commit_triggers_mirror_once(self):
        merchant = self._merchant()
        conversation = SupportConversation.objects.create(
            merchant=merchant,
            kind=SupportConversation.Kind.PLATFORM_SUPPORT,
            peer_name="客服中心",
        )

        with mock.patch.object(crisp_mirror, "mirror_message") as mirror:
            with self.captureOnCommitCallbacks(execute=True):
                message = SupportMessage.objects.create(
                    conversation=conversation,
                    sender=SupportMessage.Sender.MERCHANT,
                    author_label=merchant.display_name,
                    text="提交后发送",
                )
                queue_support_message_mirror(message)

        mirror.assert_called_once()
        kwargs = mirror.call_args.kwargs
        self.assertEqual(kwargs["thread_key"], f"merchant:{merchant.public_id}")
        # 批次 AA（Q8）：本线程的访客是商家 → 走 merchant_visitor（payload from=user）。
        self.assertEqual(kwargs["sender_kind"], "merchant_visitor")
        self.assertEqual(kwargs["message_id"], str(message.pk))

    def test_buyer_conversation_is_not_mirrored(self):
        merchant = self._merchant()
        conversation = SupportConversation.objects.create(
            merchant=merchant, kind=SupportConversation.Kind.BUYER, peer_name="买家"
        )
        message = SupportMessage.objects.create(
            conversation=conversation,
            sender=SupportMessage.Sender.MERCHANT,
            author_label=merchant.display_name,
            text="买家咨询回复不在本轮范围",
        )

        with mock.patch.object(crisp_mirror, "mirror_message") as mirror:
            with self.captureOnCommitCallbacks(execute=True):
                queue_support_message_mirror(message)

        mirror.assert_not_called()

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _merchant(self, slug="crisp-mirror-shop"):
        return Merchant.objects.create(
            slug=slug,
            display_name="镜像测试店",
            onboarding_status=Merchant.OnboardingStatus.ACTIVE,
            admission_approved=True,
            deposit_initial_paid=True,
            referral_code="MCRISP01",
        )


class CrispMetaTitleTests(TestCase):
    """Inbox 会话标题口径（2026-11-29）：买家 🟢 / 商家 🟠，商家显示 public_id。"""

    MERCHANT_ID = "JYM0012345678"

    def setUp(self):
        crisp_mirror._META_READY.clear()
        self.addCleanup(crisp_mirror._META_READY.clear)

    def test_build_title_uses_role_emoji_arrow(self):
        title = crisp_mirror.build_session_title("小明", self.MERCHANT_ID)

        self.assertEqual(title, "🟢 小明 ➡️ 🟠 JYM0012345678")
        self.assertNotIn(" · ", title)
        self.assertNotIn("-->", title)
        self.assertEqual(title.count(crisp_mirror.META_TITLE_ARROW), 1)

    def test_merchant_chat_title_keeps_both_sides(self):
        thread = SimpleNamespace(
            buyer=SimpleNamespace(display_name="小明", email=""),
            merchant=SimpleNamespace(display_name="会话测试店", public_id=self.MERCHANT_ID),
        )

        self.assertEqual(
            crisp_mirror.merchant_chat_meta_nickname(thread), "🟢 小明 ➡️ 🟠 JYM0012345678"
        )

    def test_merchant_chat_title_uses_id_not_store_name(self):
        thread = SimpleNamespace(
            buyer=SimpleNamespace(display_name="小明", email=""),
            merchant=SimpleNamespace(display_name="非常有辨识度的店名", public_id=self.MERCHANT_ID),
        )

        title = crisp_mirror.merchant_chat_meta_nickname(thread)

        self.assertNotIn("非常有辨识度的店名", title)
        self.assertIn(self.MERCHANT_ID, title)

    def test_merchant_chat_title_falls_back_when_merchant_id_missing(self):
        thread = SimpleNamespace(
            buyer=SimpleNamespace(display_name="小明", email=""),
            merchant=SimpleNamespace(display_name="会话测试店", public_id="  "),
        )

        self.assertEqual(crisp_mirror.merchant_chat_meta_nickname(thread), "🟢 小明 ➡️ 🟠 商家")

    def test_support_chat_title_appends_platform_name(self):
        thread = SimpleNamespace(buyer=SimpleNamespace(display_name="小明", email=""))

        title = crisp_mirror.support_chat_meta_nickname(thread)

        self.assertEqual(title, "🟢 小明 ➡️ JoyBuy客服")
        # 平台侧在标题里**不带 emoji**，且与消息气泡昵称是独立口径。
        self.assertTrue(title.endswith(f"{crisp_mirror.META_TITLE_ARROW} JoyBuy客服"))
        self.assertNotEqual(crisp_mirror.META_TITLE_PLATFORM_NAME, crisp_mirror.platform_nickname())

    def test_merchant_platform_title_uses_orange_emoji_on_left(self):
        title = crisp_mirror.build_session_title(
            self.MERCHANT_ID,
            "JoyBuy客服",
            left_role=crisp_mirror.META_TITLE_ROLE_MERCHANT,
            right_role=crisp_mirror.META_TITLE_ROLE_PLATFORM,
        )

        self.assertEqual(title, "🟠 JYM0012345678 ➡️ JoyBuy客服")

    def test_long_merchant_id_truncates_id_not_platform_suffix(self):
        title = crisp_mirror.build_session_title(
            "J" * 60,
            "JoyBuy客服",
            left_role=crisp_mirror.META_TITLE_ROLE_MERCHANT,
            right_role=crisp_mirror.META_TITLE_ROLE_PLATFORM,
        )

        self.assertEqual(len(title), crisp_mirror.META_NICKNAME_MAX_LENGTH)
        self.assertTrue(title.endswith(f" {crisp_mirror.META_TITLE_ARROW} JoyBuy客服"))
        # emoji 与箭头的变体选择符/不变选择符完整：只截名字，不切固定部分。
        self.assertTrue(title.startswith(f"{crisp_mirror.META_EMOJI_MERCHANT} "))
        self.assertEqual(title.count("\ufe0f"), 1)

    def test_long_buyer_name_keeps_right_emoji_and_arrow(self):
        thread = SimpleNamespace(
            buyer=SimpleNamespace(display_name="买" * 60, email=""),
            merchant=SimpleNamespace(display_name="会话测试店", public_id=self.MERCHANT_ID),
        )

        title = crisp_mirror.merchant_chat_meta_nickname(thread)

        self.assertEqual(len(title), crisp_mirror.META_NICKNAME_MAX_LENGTH)
        self.assertTrue(title.endswith(f" {crisp_mirror.META_TITLE_ARROW} 🟠 {self.MERCHANT_ID}"))
        self.assertTrue(title.startswith(f"{crisp_mirror.META_EMOJI_BUYER} "))
        # 箭头是 U+27A1 + U+FE0F 两个码位，截断后仍完整出现（不残留孤立 U+27A1）。
        self.assertEqual(title.count(crisp_mirror.META_TITLE_ARROW), 1)
        self.assertEqual(title.count("\ufe0f"), 1)

    def test_long_buyer_name_bp_keeps_platform_suffix(self):
        thread = SimpleNamespace(buyer=SimpleNamespace(display_name="买" * 60, email=""))

        title = crisp_mirror.support_chat_meta_nickname(thread)

        self.assertEqual(len(title), crisp_mirror.META_NICKNAME_MAX_LENGTH)
        self.assertTrue(title.endswith(f" {crisp_mirror.META_TITLE_ARROW} JoyBuy客服"))
        self.assertTrue(title.startswith(f"{crisp_mirror.META_EMOJI_BUYER} "))

    def test_overlong_right_name_truncated_but_keeps_emoji_prefix(self):
        title = crisp_mirror.build_session_title("小明", "店" * 60)

        self.assertEqual(len(title), crisp_mirror.META_NICKNAME_MAX_LENGTH)
        self.assertEqual(
            title,
            f"{crisp_mirror.META_EMOJI_BUYER} 小 {crisp_mirror.META_TITLE_ARROW} "
            f"{crisp_mirror.META_EMOJI_MERCHANT} " + "店" * 31,
        )

    @override_settings(**CONFIGURED)
    def test_meta_patch_keeps_platform_suffix_for_long_merchant_id(self):
        long_merchant_id = "JYM" * 20
        nickname = crisp_mirror.build_session_title(
            long_merchant_id,
            "JoyBuy客服",
            left_role=crisp_mirror.META_TITLE_ROLE_MERCHANT,
            right_role=crisp_mirror.META_TITLE_ROLE_PLATFORM,
        )
        responses = [{"data": {"session_id": "session-long"}}, {}, {}]
        with (
            mock.patch.object(crisp_mirror, "_http_post", side_effect=responses),
            mock.patch.object(crisp_mirror, "_http_patch", return_value={}) as patch_http,
        ):
            mirror_message(
                "merchant:JYLONGTITLE",
                "merchant_visitor",
                long_merchant_id,
                "长店名",
                None,
                "601",
                session_nickname=nickname,
            )

        _path, meta_body = patch_http.call_args.args
        self.assertEqual(len(meta_body["nickname"]), crisp_mirror.META_NICKNAME_MAX_LENGTH)
        self.assertTrue(
            meta_body["nickname"].endswith(f" {crisp_mirror.META_TITLE_ARROW} JoyBuy客服")
        )
        self.assertIn(crisp_mirror.META_EMOJI_MERCHANT, meta_body["nickname"])


class CrispMirrorEndpointTests(TestCase):
    """真实接口接线：商家端 / 管理端发消息 → on_commit 后镜像。"""

    def setUp(self):
        patcher = mock.patch.object(crisp_mirror, "RETRY_DELAY_SECONDS", 0)
        patcher.start()
        self.addCleanup(patcher.stop)
        patch = mock.patch.object(crisp_mirror, "_http_patch", return_value={})
        self.patch_http = patch.start()
        self.addCleanup(patch.stop)
        get = mock.patch.object(
            crisp_mirror, "_http_get", return_value={"data": {"nickname": "已有昵称"}}
        )
        self.get_http = get.start()
        self.addCleanup(get.stop)
        crisp_mirror._META_READY.clear()
        self.addCleanup(crisp_mirror._META_READY.clear)

        self.merchant = Merchant.objects.create(
            slug="crisp-endpoint-shop",
            display_name="接口镜像店",
            onboarding_status=Merchant.OnboardingStatus.ACTIVE,
            admission_approved=True,
            deposit_initial_paid=True,
            referral_code="MCRISP02",
        )
        self.staff = StaffAccount.objects.create(
            email="crisp-staff@joybuy.test", display_name="客服甲", status=StaffAccount.Status.ACTIVE
        )
        self.staff.set_password("Staff#2026pass")
        self.staff.save()
        MerchantMembership.objects.create(
            merchant=self.merchant,
            staff=self.staff,
            role=MerchantRole.objects.get(code="merchant_owner"),
            status="ACTIVE",
        )
        self._login()

    def _login(self):
        token, _session = create_staff_session(
            staff=self.staff, ip_address="127.0.0.1", user_agent="test", totp_verified=True
        )
        self.client.cookies["joybuy_staff_session"] = token

    def _grant(self, *codes):
        role, _ = PlatformRole.objects.update_or_create(
            code="crisp-support-role", defaults={"name": "Crisp support", "is_system": False}
        )
        for code in codes:
            permission, _ = PlatformPermission.objects.get_or_create(
                code=code, defaults={"name": code}
            )
            role.permissions.add(permission)
        StaffRoleAssignment.objects.get_or_create(staff=self.staff, role=role)

    def _post_merchant_reply(self, conversation, text):
        return self.client.post(
            f"/api/v1/merchant/conversations/{conversation.public_id}/messages",
            data=json.dumps({"text": text}),
            content_type="application/json",
            HTTP_X_MERCHANT_ID=str(self.merchant.public_id),
        )

    @override_settings(**NOT_CONFIGURED)
    def test_merchant_reply_logs_skipped_and_returns_201(self):
        conversation = SupportConversation.objects.create(
            merchant=self.merchant,
            kind=SupportConversation.Kind.PLATFORM_SUPPORT,
            peer_name="客服中心",
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self._post_merchant_reply(conversation, "无 token 时也应 201")

        self.assertEqual(response.status_code, 201, response.content)
        log = CrispMirrorLog.objects.get()
        self.assertEqual(log.status, CrispMirrorLog.Status.SKIPPED)
        self.assertEqual(log.sender_kind, "merchant_visitor")
        self.assertEqual(log.thread_key, f"merchant:{self.merchant.public_id}")

    @override_settings(**CONFIGURED)
    def test_merchant_reply_is_mirrored_after_commit(self):
        conversation = SupportConversation.objects.create(
            merchant=self.merchant,
            kind=SupportConversation.Kind.PLATFORM_SUPPORT,
            peer_name="客服中心",
        )
        responses = [{"data": {"session_id": "session-merchant"}}, {}, {}]
        with mock.patch.object(crisp_mirror, "_http_post", side_effect=responses) as http:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                response = self._post_merchant_reply(conversation, "商家真实消息")
                # 接口返回前（提交前）不应发 HTTP。
                self.assertEqual(http.call_count, 0)
            self.assertEqual(len(callbacks), 1)

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(http.call_count, 3)
        final_body = http.call_args_list[-1].args[1]
        self.assertEqual(final_body["content"], "商家真实消息")
        # 批次 AA（Q8）：merchant: 线程里商家是访客身份（from=user），不再是 operator。
        self.assertEqual(final_body["from"], "user")
        self.assertEqual(final_body["user"], {"type": "website", "nickname": "接口镜像店"})
        # 线程的访客是商家 → 会话 meta 标题 = 「🟠 商家ID ➡️ JoyBuy客服」（2026-11-29 口径）。
        self.patch_http.assert_called_once()
        _meta_path, meta_body = self.patch_http.call_args.args
        self.assertEqual(meta_body, {"nickname": f"🟠 {self.merchant.public_id} ➡️ JoyBuy客服"})
        self.assertEqual(CrispMirrorLog.objects.get().status, CrispMirrorLog.Status.SENT)

    @override_settings(**CONFIGURED)
    def test_merchant_reply_survives_mirror_failure(self):
        conversation = SupportConversation.objects.create(
            merchant=self.merchant,
            kind=SupportConversation.Kind.PLATFORM_SUPPORT,
            peer_name="客服中心",
        )
        with mock.patch.object(
            crisp_mirror, "_http_post", side_effect=CrispRequestError("HTTP 500")
        ):
            with self.captureOnCommitCallbacks(execute=True):
                response = self._post_merchant_reply(conversation, "镜像挂了也要成功")

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(conversation.messages.count(), 1)
        self.assertEqual(CrispMirrorLog.objects.get().status, CrispMirrorLog.Status.FAILED)

    @override_settings(**CONFIGURED)
    def test_admin_reply_is_mirrored_with_platform_nickname(self):
        self._grant("support.manage", "support.view")
        conversation = SupportConversation.objects.create(
            merchant=self.merchant,
            kind=SupportConversation.Kind.PLATFORM_SUPPORT,
            peer_name="客服中心",
        )
        CrispMirrorSession.objects.create(
            thread_key=f"merchant:{self.merchant.public_id}", session_id="session-admin"
        )
        with mock.patch.object(crisp_mirror, "_http_post", return_value={}) as http:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    f"/api/v1/admin/support/conversations/{conversation.public_id}",
                    data=json.dumps({"action": "reply", "text": "平台已处理"}),
                    content_type="application/json",
                )

        self.assertEqual(response.status_code, 201, response.content)
        body = http.call_args.args[1]
        self.assertEqual(body["content"], "平台已处理")
        self.assertEqual(body["from"], "operator")
        self.assertEqual(body["user"], {"type": "website", "nickname": "Joybuy 客服"})
        # 平台回复与商家消息共用同一个 Crisp 会话。
        self.assertEqual(
            http.call_args.args[0], "/website/website-123/conversation/session-admin/message"
        )


class CrispMirrorCheckCommandTests(TestCase):
    @override_settings(**NOT_CONFIGURED)
    def test_command_reports_not_configured(self):
        out = StringIO()
        call_command("crisp_mirror_check", stdout=out)

        output = out.getvalue()
        self.assertIn("未配置，跳过镜像", output)
        self.assertIn("CRISP_WEBSITE_ID", output)
        self.assertFalse(CrispMirrorLog.objects.exists())
