"""Crisp 消息镜像配置自检（需求 18 / 批次 V）。

用法：
- ``python manage.py crisp_mirror_check``         只看配置是否齐备；
- ``python manage.py crisp_mirror_check --send-test`` 有 token 时真发一条测试消息
  （会写入 ``CrispMirrorLog`` 一行，可在 Crisp Inbox 的 ``diag:*`` 会话里看到）。

未配置时明确提示「未配置，跳过镜像」，不尝试任何外部请求。
"""

import uuid

from django.core.management.base import BaseCommand
from django.utils import timezone

from merchant_ops import crisp_mirror


class Command(BaseCommand):
    help = "检查 Crisp 客服消息镜像配置；可选 --send-test 真发一条测试消息"

    def add_arguments(self, parser):
        parser.add_argument(
            "--send-test",
            action="store_true",
            help="配置齐备时真发一条测试消息到 Crisp（会产生一次 REST 调用）",
        )
        parser.add_argument(
            "--thread",
            default="crisp-check",
            help="测试用线程标识（默认 crisp-check，最终 thread_key 为 diag:<thread>）",
        )

    def handle(self, *args, **options):
        config = crisp_mirror.crisp_config()
        website_id = config["website_id"]
        has_website_token = bool(config["website_token"])
        has_plugin_token = bool(config["plugin_id"] and config["plugin_token"])
        has_api_token = bool(config["api_token_id"] and config["api_token_key"])
        configured = crisp_mirror.is_configured()

        # 只展示标识前缀，绝不输出完整 token/key。
        api_id = config["api_token_id"]
        api_id_note = f"{api_id[:4]}…({len(api_id)} chars)" if api_id else "(empty)"
        rows = [
            ("CRISP_WEBSITE_ID", website_id or "(empty)"),
            ("CRISP_WEBSITE_TOKEN", "set" if has_website_token else "(empty)"),
            ("CRISP_PLUGIN_ID", config["plugin_id"] or "(empty)"),
            ("CRISP_PLUGIN_TOKEN", "set" if config["plugin_token"] else "(empty)"),
            ("CRISP_API_TOKEN_ID", api_id_note),
            ("CRISP_API_TOKEN_KEY", "set" if config["api_token_key"] else "(empty)"),
            ("CRISP_API_TIER", config["api_tier"]),
        ]
        self.stdout.write("Crisp 客服消息镜像配置：")
        for name, value in rows:
            self.stdout.write(f"  {name}: {value}")

        if not configured:
            missing = []
            if not website_id:
                missing.append("CRISP_WEBSITE_ID")
            if not has_api_token and not has_website_token and not has_plugin_token:
                missing.append(
                    "CRISP_API_TOKEN_ID+CRISP_API_TOKEN_KEY 或 CRISP_WEBSITE_TOKEN 或 "
                    "CRISP_PLUGIN_ID+CRISP_PLUGIN_TOKEN"
                )
            self.stdout.write(
                self.style.WARNING(
                    "未配置，跳过镜像（mirror_message 返回 skipped，不发外部请求）。"
                    f"缺少：{', '.join(missing)}"
                )
            )
            self.stdout.write(
                "获取路径：Crisp 后台 → 设定 → 工作区 → 进阶设定 → API 令牌（identifier + key）；"
                "或 Settings → Workspace Settings → Advanced configuration 生成 Website Token；"
                "或在 Crisp Marketplace 创建插件拿 Plugin Token"
                "（scope 需含 conversation 读写 + message 发送）。"
            )
            return

        identifier, _key, tier = crisp_mirror._credentials()
        if tier == "plugin":
            tier_note = f"plugin token（identifier 前缀 {identifier[:4]}…，X-Crisp-Tier: plugin，每日 5,000 次）"
        elif has_api_token:
            tier_note = (
                f"workspace API token（identifier 前缀 {identifier[:4]}…，"
                f"X-Crisp-Tier: {tier}，每日 10,000 次）"
            )
        else:
            tier_note = f"website token（X-Crisp-Tier: {tier}，每日 10,000 次）"
        self.stdout.write(self.style.SUCCESS(f"配置齐备，将使用 {tier_note}。"))

        if not options["send_test"]:
            self.stdout.write("未指定 --send-test，仅做配置检查。")
            return

        thread_key = f"diag:{options['thread']}"
        result = crisp_mirror.mirror_message(
            thread_key=thread_key,
            sender_kind=crisp_mirror.SENDER_PLATFORM,
            sender_name="系统诊断",
            body=f"Crisp mirror check at {timezone.now().isoformat()}",
            occurred_at=timezone.now(),
            message_id=f"test:{uuid.uuid4().hex}",
        )
        self.stdout.write(f"发送结果：{result}")
        if result["status"] == crisp_mirror.STATUS_FAILED:
            self.stderr.write(self.style.ERROR(f"发送失败：{result['error']}"))
