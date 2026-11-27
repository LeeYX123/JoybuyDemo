"""一次性修历史 Crisp 会话标题（2026-11-27 标题口径变更）。

背景：``patch_conversation_meta`` / ``_backfill_conversation_meta`` 只在 meta **为空**
时写昵称，所以改动 ``merchant_chat_meta_nickname`` / ``support_chat_meta_nickname``
只影响**新会话**；已有会话的标题仍是旧口径（``买家`` / ``买家 · 店名`` / ``店名``）。

用法（**默认 DRY_RUN，零 PATCH**）：

    python manage.py crisp_retitle                  # 只打印 session_id / 线程键 / 新标题
    python manage.py crisp_retitle --fetch          # 额外 GET 一次旧昵称（只读，做前后对照）
    python manage.py crisp_retitle --limit 5        # 只看前 5 条
    python manage.py crisp_retitle --apply          # 真的 PATCH meta（会改 Inbox 标题）

建议 ``--apply --fetch`` 一起用：有旧昵称才能跳过「已是目标标题」的会话；只加 ``--apply``
时不读旧值，会对每条命中的会话无条件 PATCH 一次（幂等，但多一次写请求）。

线程来源：``CrispMirrorLog`` 的 distinct ``thread_key``（按前缀 ``bp:`` / ``bm:`` /
``merchant:`` 分组），``session_id`` 由 ``CrispMirrorSession`` 映射解析；没有映射的
线程说明从未成功建会话，跳过并计数；线程/商家已从库里删除的旧键（如历史 UUID 版
``bp:<uuid>``）无法重算标题，也计入「无法识别」并跳过。新标题一律用 ``crisp_mirror``
里的现成 helper 重算（与线上新会话完全同口径）。失败写 ``CrispMirrorLog``
（``sender_kind=retitle``，``status=failed``）并继续下一条。
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from merchant_ops import crisp_mirror
from merchant_ops.models import (
    CrispMirrorLog,
    CrispMirrorSession,
    MerchantChatThread,
    SupportChatThread,
)
from merchants.models import Merchant

KIND_BUYER_PLATFORM = "bp"
KIND_BUYER_MERCHANT = "bm"
KIND_MERCHANT_PLATFORM = "merchant"
KIND_LABELS = {
    KIND_BUYER_PLATFORM: "买家↔平台客服",
    KIND_BUYER_MERCHANT: "买家↔商家",
    KIND_MERCHANT_PLATFORM: "商家↔平台客服",
}


class Command(BaseCommand):
    help = "重算并（可选）回写历史 Crisp 会话标题；默认 DRY_RUN，--apply 才 PATCH"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="真的 PATCH 会话 meta（默认只打印，不发任何写请求）",
        )
        parser.add_argument(
            "--fetch",
            action="store_true",
            help="DRY_RUN 时额外 GET 一次旧昵称做前后对照（只读；默认不发任何网络请求）",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="最多处理多少条会话（0 = 不限）",
        )

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        apply_changes = bool(options["apply"])
        fetch_old = bool(options["fetch"])
        limit = max(int(options["limit"] or 0), 0)

        if apply_changes and not crisp_mirror.is_configured():
            self.stderr.write(
                self.style.ERROR("Crisp 未配置，无法 PATCH；请先补齐 CRISP_* 环境变量。")
            )
            return
        if fetch_old and not crisp_mirror.is_configured():
            self.stdout.write(
                self.style.WARNING("Crisp 未配置：跳过 GET，旧昵称显示为「(未读取)」。")
            )
            fetch_old = False

        rows, unmapped, unknown = self._collect_rows()
        if limit:
            rows = rows[:limit]

        mode = "APPLY（会 PATCH）" if apply_changes else "DRY_RUN（不发写请求）"
        self.stdout.write(f"Crisp 会话标题回写：{mode}")
        self.stdout.write(
            "发现 distinct 线程 %d 条（按前缀分组：%s）"
            % (
                len(self._all_keys),
                "，".join(
                    f"{KIND_LABELS[kind]} {count}"
                    for kind, count in sorted(self._kind_counts.items())
                )
                or "无",
            )
        )
        self.stdout.write(
            f"可回写（有 session 映射）：{len(self._all_rows)} 条；"
            f"无 session 映射跳过：{unmapped} 条；无法识别的线程键：{unknown} 条"
        )
        if limit:
            self.stdout.write(f"--limit {limit}：本次只处理前 {len(rows)} 条")
        self.stdout.write("")

        patched = 0
        failed = 0
        unchanged = 0
        run_stamp = timezone.now().strftime("%Y%m%dT%H%M%S")
        for index, row in enumerate(rows, start=1):
            old_nickname = "（未读取）"
            if fetch_old:
                meta = crisp_mirror.fetch_conversation_meta(row["session_id"])
                if meta is None:
                    old_nickname = "（GET 失败）"
                else:
                    old_nickname = (meta.get("nickname") or "").strip() or "（空）"

            self.stdout.write(f"[{index}] {row['session_id']}  {row['thread_key']}")
            self.stdout.write(f"    类型: {KIND_LABELS.get(row['kind'], row['kind'])}")
            self.stdout.write(f"    旧昵称: {old_nickname}")
            self.stdout.write(f"    新昵称: {row['title']}")

            if not apply_changes:
                continue
            if old_nickname == row["title"]:
                unchanged += 1
                self.stdout.write("    结果: 已是目标标题，跳过 PATCH")
                continue
            if crisp_mirror.patch_conversation_meta(row["session_id"], nickname=row["title"]):
                patched += 1
                self.stdout.write(self.style.SUCCESS("    结果: PATCH 成功"))
            else:
                failed += 1
                self._log_failure(row, run_stamp)
                self.stdout.write(self.style.ERROR("    结果: PATCH 失败（已记 CrispMirrorLog）"))

        self.stdout.write("")
        if apply_changes:
            self.stdout.write(
                self.style.SUCCESS(
                    f"完成：PATCH 成功 {patched} 条，已是目标标题 {unchanged} 条，失败 {failed} 条。"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "DRY_RUN 结束：未发出任何写请求（未 PATCH）。确认无误后加 --apply 执行。"
                )
            )

    # ------------------------------------------------------------------
    def _collect_rows(self) -> tuple[list[dict], int, int]:
        """把 distinct thread_key 解析成待回写行（按线程类型排序，便于人工核对）。"""

        thread_keys = list(
            CrispMirrorLog.objects.order_by("thread_key")
            .values_list("thread_key", flat=True)
            .distinct()
        )
        self._kind_counts: dict[str, int] = {}
        for thread_key in thread_keys:
            kind = str(thread_key).split(":", 1)[0]
            if kind in KIND_LABELS:
                self._kind_counts[kind] = self._kind_counts.get(kind, 0) + 1

        sessions = dict(
            CrispMirrorSession.objects.filter(thread_key__in=thread_keys).values_list(
                "thread_key", "session_id"
            )
        )

        rows: list[dict] = []
        unmapped = 0
        unknown = 0
        for thread_key in thread_keys:
            title = self._resolve_title(thread_key)
            if title is None:
                unknown += 1
                continue
            session_id = sessions.get(thread_key)
            if not session_id:
                unmapped += 1
                continue
            rows.append(
                {
                    "thread_key": thread_key,
                    "kind": thread_key.split(":", 1)[0],
                    "session_id": session_id,
                    "title": title,
                }
            )
        order = {KIND_BUYER_MERCHANT: 0, KIND_BUYER_PLATFORM: 1, KIND_MERCHANT_PLATFORM: 2}
        rows.sort(key=lambda row: (order.get(row["kind"], 9), row["thread_key"]))
        self._all_keys = thread_keys
        self._all_rows = rows
        return rows, unmapped, unknown

    def _resolve_title(self, thread_key: str) -> str | None:
        """按线程前缀重算目标标题；线程/商家已不存在时返回 None（跳过）。"""

        parts = thread_key.split(":")
        kind = parts[0] if parts else ""
        try:
            if kind == KIND_BUYER_PLATFORM and len(parts) >= 2:
                thread = (
                    SupportChatThread.objects.select_related("buyer")
                    .filter(buyer__public_id=parts[1])
                    .first()
                )
                return crisp_mirror.support_chat_meta_nickname(thread) if thread else None
            if kind == KIND_BUYER_MERCHANT and len(parts) >= 3:
                thread = (
                    MerchantChatThread.objects.select_related("buyer", "merchant")
                    .filter(buyer__public_id=parts[1], merchant__public_id=parts[2])
                    .first()
                )
                return crisp_mirror.merchant_chat_meta_nickname(thread) if thread else None
            if kind == KIND_MERCHANT_PLATFORM and len(parts) >= 2:
                # ``merchant:{public_id}``：同一商家只有一个会话（thread_key_for_conversation）。
                merchant = Merchant.objects.filter(public_id=parts[1]).only("display_name").first()
                if merchant is None:
                    return None
                return crisp_mirror.build_session_title(
                    merchant.display_name or crisp_mirror.META_TITLE_MERCHANT_FALLBACK,
                    crisp_mirror.META_TITLE_PLATFORM_NAME,
                )
        except Exception:  # noqa: BLE001 - 单条解析失败不能中断整批
            return None
        return None

    def _log_failure(self, row: dict, run_stamp: str) -> None:
        """失败落 CrispMirrorLog（沿用既有投递记录表的观测方式），不抛异常。"""

        try:
            log, _created = crisp_mirror._claim_log(
                row["thread_key"], f"retitle:{run_stamp}", "retitle"
            )
            crisp_mirror._mark(
                log,
                CrispMirrorLog.Status.FAILED,
                f"retitle failed: session={row['session_id']} title={row['title']}",
                bump_attempts=True,
            )
        except Exception:  # noqa: BLE001 - 记日志失败不影响继续处理
            pass
