"""Batch crawler-account setup from an Excel sheet (2026-11-12, operator request).

Input: an .xlsx with columns [账号, 密码, 解码(TOTP seed)] — Facebook accounts
used to sign into joybuy.co.uk. The sheet stays OUTSIDE the repo (user's
Downloads); passwords/TOTP secrets are read at runtime and are never stored
in the database, logs, notes or the progress file — only the session cookies
(the existing encrypted ``record_account_session`` path) persist.

Phases:
- ``--create-only``: split rows into groups of ``--group-size`` named
  ``<prefix>01``… (数据抓取01…), create CrawlerAccounts (label = FB id),
  re-group accounts that already exist (keeps their stored session).
- ``--login``: for each numbered-group account without a VALID session,
  attempt an automated Facebook login (headed browser, TOTP generated
  locally — same algorithm as 2fa.cn). Failure modes:
  * Facebook "account disabled/banned" → note + skip (session stays UNKNOWN);
  * automation stuck (unknown checkpoint, selectors missing) → the SAME
    headed window stays open for the operator to finish manually
    (``--manual-wait`` seconds, default 300; ``--no-manual-fallback`` skips);
  * success → Joybuy cookies captured + session saved.
- ``--manual <label>``: open the manual window for one account without
  attempting automation first.

Between accounts the command sleeps a random ``--delay-min``…``--delay-max``
(default 25–45s) to avoid hammering Facebook from one IP. Progress is
appended to ``var/logs/fb_batch_progress.jsonl`` (no credentials inside).
"""

import os
import random
import re
import sys
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
if str(REPOSITORY_ROOT / "crawler") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "crawler"))

UK_BASE_URL = "https://www.joybuy.co.uk/"
#: Dedicated CDP port for login windows; never the crawl executor port.
LOGIN_CDP_PORT = "127.0.0.1:9334"
PROGRESS_FILE = REPOSITORY_ROOT / "var" / "logs" / "fb_batch_progress.jsonl"

#: Facebook texts that mean "this account is banned/disabled" — skip.
BANNED_KEYWORDS = (
    "disabled",
    "suspended",
    "已被停用",
    "已被禁用",
    "帐号已被停用",
    "账号已被停用",
    "已被锁定",
)
#: Facebook texts that mean credentials were rejected (recoverable by hand).
BAD_CREDENTIALS_KEYWORDS = (
    "incorrect password",
    "密码不正确",
    "找不到你的账号",
    "we couldn't find your account",
)
#: facebook.com 不可达时 Chrome 的报错页（2026-11-13 实测：joybuy 可访问、FB 超时）。
NETWORK_ERROR_KEYWORDS = (
    "err_connection_timed_out",
    "err_connection_reset",
    "err_name_not_resolved",
    "err_proxy_connection_failed",
    "err_internet_disconnected",
    "无法访问此网站",
    "响应时间过长",
)


def _clean_secret(raw) -> str:
    """Normalize a TOTP seed: keep base32 chars, uppercase. 2fa.cn-compatible."""

    return re.sub(r"[^A-Za-z0-9]", "", str(raw or "")).upper()


def _cell_id(value) -> str:
    """Excel cell → clean id string ('100011734838229', never '… .0')."""

    if value is None:
        return ""
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value).strip()


class Command(BaseCommand):
    help = "Batch-create crawler accounts from the operator's Excel and log them in."

    def add_arguments(self, parser):
        parser.add_argument("--excel", type=str, required=True)
        parser.add_argument("--group-prefix", type=str, default="数据抓取")
        parser.add_argument("--group-size", type=int, default=10)
        parser.add_argument("--create-only", action="store_true")
        parser.add_argument("--login", action="store_true")
        parser.add_argument("--limit", type=int, default=0, help="Max logins this run (0 = all)")
        parser.add_argument(
            "--manual", type=str, default="", help="Open the manual window for one label only"
        )
        parser.add_argument("--manual-wait", type=int, default=300)
        parser.add_argument("--no-manual-fallback", action="store_true")
        parser.add_argument("--delay-min", type=float, default=25.0)
        parser.add_argument("--delay-max", type=float, default=45.0)

    # ------------------------------------------------------------------
    # Excel + phase A
    # ------------------------------------------------------------------

    def _read_rows(self, excel_path):
        import openpyxl

        workbook = openpyxl.load_workbook(excel_path, data_only=True)
        sheet = workbook.worksheets[0]
        rows = []
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not row or not _cell_id(row[0] if row else None):
                continue
            account_id = _cell_id(row[0])
            password = str(row[1] or "").strip()
            secret = _clean_secret(row[2])
            if not password or not secret:
                self.stdout.write(f"跳过 {account_id}：密码或 2FA 密钥为空。")
                continue
            rows.append((account_id, password, secret))
        return rows

    def _create_accounts(self, rows, *, prefix, size):
        from crawler_control.models import CrawlerAccount
        from crawler_control.services import create_crawler_account, ensure_account_group

        self.stdout.write(f"共 {len(rows)} 个账号，按每 {size} 个一组分组。")
        for index, (account_id, _pwd, _secret) in enumerate(rows):
            group_name = f"{prefix}{index // size + 1:02d}"
            ensure_account_group(group_name)
            existing = CrawlerAccount.objects.filter(label=account_id, deleted_at=None).first()
            if existing is not None:
                if existing.account_group != group_name:
                    old = existing.account_group
                    existing.account_group = group_name
                    existing.save(update_fields=["account_group", "updated_at"])
                    self.stdout.write(
                        f"已有账号 {account_id} 从组「{old}」移到「{group_name}」（会话保留）。"
                    )
                else:
                    self.stdout.write(f"已有账号 {account_id} 已在组「{group_name}」，跳过。")
                continue
            create_crawler_account(
                label=account_id,
                account_group=group_name,
                note="FB 账号（Excel 批量导入）",
            )
            self.stdout.write(f"创建账号 {account_id} → 组「{group_name}」。")

    # ------------------------------------------------------------------
    # Phase B: automated Facebook login
    # ------------------------------------------------------------------

    def _progress(self, label, status, detail=""):
        PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        line = f"{timezone.now().isoformat()}\t{label}\t{status}\t{detail}"
        with open(PROGRESS_FILE, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def _browser(self, profile_dir):
        from DrissionPage import ChromiumOptions, ChromiumPage

        options = ChromiumOptions()
        options.set_address(LOGIN_CDP_PORT)
        options.set_user_data_path(str(profile_dir))
        options.set_argument("--disable-blink-features=AutomationControlled")
        # Joybuy 的 Facebook OAuth 走 window.open 弹窗，别让 Chromium 拦截。
        options.set_argument("--disable-popup-blocking")
        options.set_argument("--window-size", "1280,860")
        # 2026-11-13：FB 登录页已是纯客户端渲染的 Comet 应用，窗口被遮挡时
        # Chrome 会对 renderer 降频（backgrounding），实测 6 分钟仍停在空白壳
        # （DOM 里 0 个 <input>，日志只有「FB 状态=未知」）。这三个开关强制
        # 后台窗口也按前台渲染。
        options.set_argument("--disable-backgrounding-occluded-windows")
        options.set_argument("--disable-renderer-backgrounding")
        options.set_argument("--disable-background-timer-throttling")
        options.set_timeouts(page_load=45, script=20)
        # Joybuy 页面挂着广告/统计 iframe（insight.adsrvr.org 等），load 事件经常
        # 迟迟不触发，`get()` 会一直等到 page_load 超时（实测卡 45s+ 仍未返回）。
        # eager = DOMContentLoaded 即返回，页面渲染由调用处的 sleep 覆盖。
        options.set_load_mode("eager")
        # 可选代理：主机不在 VPN 全局路由里时，用 FB_LOGIN_PROXY=http://ip:port
        # 单独把登录浏览器送出去（joybuy 直连可用时不要设，避免整体变慢）。
        proxy = os.getenv("FB_LOGIN_PROXY", "").strip()
        if proxy:
            options.set_proxy(proxy)
        return ChromiumPage(options)

    @staticmethod
    def _facebook_reachable(timeout=8):
        """TCP+TLS 预检 facebook.com；不通就别开几十个浏览器白跑。"""

        import socket
        import ssl

        if os.getenv("FB_LOGIN_PROXY", "").strip():
            return True  # 走显式代理时直连预检没有意义，交给浏览器报错兜底
        try:
            with socket.create_connection(("www.facebook.com", 443), timeout=timeout) as sock:
                ssl.create_default_context().wrap_socket(sock, server_hostname="www.facebook.com")
            return True
        except Exception:  # noqa: BLE001 - 任何异常都视为不可达
            return False

    def _goto(self, page, url, *, timeout=25):
        """Navigate without letting a slow/redirecting page wedge the flow.

        2026-11-13 起 Joybuy 全站未登录时 307 到 /login，页面挂着广告 iframe，
        ``get()`` 不显式给超时时会一直等 load 事件（实测 >150s 卡死）。
        """

        try:
            page.get(url, timeout=timeout)
        except Exception:  # noqa: BLE001 - 超时/断连都当「页面可能已可用」继续
            return False
        return True

    def _step(self, account, message):
        """调试步骤行（带时间戳，便于定位卡点）。"""

        self.stdout.write(f"  [{time.strftime('%H:%M:%S')}] {message}")
        self.stdout.flush()

    def _totp(self, secret):
        import pyotp

        code = pyotp.TOTP(secret).now()
        remaining = pyotp.TOTP(secret).interval - int(time.time()) % pyotp.TOTP(secret).interval
        if remaining < 5:
            # 代码即将过期：等下一窗口再生成，避免填进去就失效。
            time.sleep(remaining + 1)
            code = pyotp.TOTP(secret).now()
        return code

    def _page_text(self, page):
        """可见文案（title + 去掉 script/style 的正文），绝不匹配原始 HTML。

        2026-11-13 实测缺陷：原来取 ``page.html[:20000]``，而 facebook.com 的
        登录页把这 20KB 全花在内联 ``<script>``/``<style>`` 上（到处是
        ``disabled`` 之类的关键词），正常登录页被误判成封号直接跳过。改为复用
        蜘蛛侧的 ``_visible_text``（剥掉 script/style 再匹配）。
        """

        from joybuy_crawler.render import _visible_text

        return _visible_text(page.html or "")

    def _dump_fb_html(self, page, account, reason):
        """失败取证：把当前 FB 页面 HTML 存到 var/logs/fb_dialog_<label>.html。"""

        from django.conf import settings

        try:
            dump = (
                Path(settings.BASE_DIR).parent / "var" / "logs" / f"fb_dialog_{account.label}.html"
            )
            dump.write_text((page.html or "")[:300000], encoding="utf-8")
            self._step(account, f"页面快照（{reason}）→ var/logs/fb_dialog_{account.label}.html")
        except Exception:  # noqa: BLE001, S110 - 诊断失败不影响流程
            pass

    def _classify_facebook_page(self, page):
        """'banned' | 'bad_credentials' | 'need_2fa' | 'checkpoint' | 'form' | ''."""

        text = self._page_text(page)
        if not text:
            return ""
        if any(keyword in text for keyword in NETWORK_ERROR_KEYWORDS):
            return "network"
        if any(keyword in text for keyword in BANNED_KEYWORDS):
            return "banned"
        if any(keyword in text for keyword in BAD_CREDENTIALS_KEYWORDS):
            return "bad_credentials"
        if self._ele(page, "#approvals_code") or self._ele(
            page, 'css:input[name="approvals_code"]'
        ):
            return "need_2fa"
        # 2026-11-13 诊断结论：新版 FB 登录页的 input **没有 id**（id 是 React 随机串），
        # 只有 ``name="email"`` / ``name="pass"``。旧代码按 ``#email``/``#pass`` 找，
        # 永远失败 → 一直判成「未知」，6 分钟也不填表。DrissionPage 的裸字符串
        # locator 不按 CSS 解析，必须显式写 ``css:`` 前缀。
        if self._ele(page, 'css:input[name="email"]') and self._ele(page, 'css:input[name="pass"]'):
            return "form"
        if "checkpoint" in (page.url or "").lower():
            return "checkpoint"
        return ""

    @staticmethod
    def _ele(node, locator, timeout=1):
        """取元素，找不到时返回 **None**。

        DrissionPage 4.1.1.4 的 ``ele()`` 找不到元素时返回的是 ``NoneElement``
        对象而不是 ``None``，且对它的任何属性/方法访问都会抛
        ``ElementNotFoundError``。2026-11-13 实测：FB 页面上没有
        ``button[name="__CONFIRM__"]`` 时 ``confirm is None`` 恒为假，
        随后的 ``confirm.click()`` 抛异常被外层吞掉——于是 150s 循环只是空转，
        DOM 快照也不会落盘，日志里只有「FB 状态=未知」。
        """

        try:
            ele = node.ele(locator, timeout=timeout)
        except Exception:  # noqa: BLE001 - 页签正在导航/已关闭
            return None
        return None if ele.__class__.__name__ == "NoneElement" else ele

    def _consent_visible(self, page) -> bool:
        """隐私弹窗（cookieManageDrawer）当前是否可见。"""

        ele = self._ele(page, '[class*="cookieManageDrawer_showMask"]', timeout=2)
        if ele is None:
            return False
        try:
            return ele.states.is_displayed
        except Exception:  # noqa: BLE001 - DOM 竞态按可见处理
            return True

    @staticmethod
    def _is_displayed(ele):
        try:
            return ele.states.is_displayed
        except Exception:  # noqa: BLE001 - detached node
            return False

    def _find_displayed(self, page, texts, *, wait_seconds=4, scope=None):
        """按**纯文本子串**在按钮/输入控件里找可见元素。

        2026-11-13：DrissionPage 的 ``text:`` 选择器要遍历整棵 DOM，在 Joybuy
        登录页（645KB、含广告 iframe）上实测直接卡死——faulthandler 抓栈停在
        ``chromium_base._find_elements``，命令卡住 >150s 不返回。改成 CSS 取
        ``tag:button``/``tag:input``/``css:div[role="button"]``（实测 0.08s）后本地
        比对文本，并过滤 ``states.is_displayed``（DOM 里有隐藏副本，真实点击会报
        「该元素没有位置及大小」）。2026-11-13 补充：FB 登录页的「登录」按钮是
        ``div[role="button"]``，全页 ``tag:button`` 数量为 0，扫描必须带上它。
        """

        wanted = [text.lower() for text in texts]
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            root = scope or page
            elements = []
            for tag in ("tag:button", "tag:input", 'css:div[role="button"]'):
                try:
                    elements.extend(root.eles(tag))
                except Exception:  # noqa: BLE001 - 页面正在导航
                    pass
            for ele in elements:
                try:
                    label = (ele.text or "").strip().lower()
                except Exception:  # noqa: BLE001 - detached node
                    continue
                if not label:
                    continue
                if any(token in label for token in wanted) and self._is_displayed(ele):
                    return ele
            time.sleep(1)
        return None

    def _dismiss_consent(self, page):
        """关闭 Cookie 同意/隐私弹窗（遮罩会挡住 Facebook 按钮与点击事件）。

        用**真实鼠标点击**（React 合成事件对 JS 点击经常无响应）；点击后
        轮询遮罩真正消失，最多重试 3 轮。
        """

        patterns = (
            "accept all",
            "accept all cookies",
            "allow all",
            "同意",
            "接受全部",
            "接受所有",
        )
        for _round in range(3):
            if not self._consent_visible(page):
                return
            ele = self._find_displayed(page, patterns, wait_seconds=3)
            if ele is None:
                time.sleep(2)
                continue
            try:
                ele.click()  # 真实鼠标事件，React 才能收到
            except Exception:  # noqa: BLE001 - 被遮挡时退回 JS 点击
                ele.click(by_js=True)
            for _ in range(6):
                time.sleep(1)
                if not self._consent_visible(page):
                    return

    def _click_facebook_button(self, page):
        fb_patterns = (
            "continue with facebook",
            "facebook",
            "脸书",
        )
        for _attempt in range(3):
            self._dismiss_consent(page)
            ele = self._find_displayed(page, fb_patterns, wait_seconds=3)
            if ele is None:
                # 2026-11-13 登录页改版：Facebook 折叠在「View more options」里。
                more = self._find_displayed(
                    page, ["view more options", "查看更多选项"], wait_seconds=3
                )
                if more is None:
                    continue
                try:
                    more.click()  # 真实点击展开折叠项
                except Exception:  # noqa: BLE001
                    more.click(by_js=True)
                time.sleep(2)
                ele = self._find_displayed(page, fb_patterns, wait_seconds=3)
            if ele is None:
                continue
            try:
                ele.click()  # 真实点击触发 React 事件
            except Exception:  # noqa: BLE001
                ele.click(by_js=True)
            return True
        self.stdout.write("  未找到可见的 Facebook 登录按钮（含展开后）。")
        return False

    def _auto_login(self, account, password, secret, *, manual_wait):
        """Returns 'ok' | 'banned' | 'manual_ok' | 'manual_pending' | 'failed'."""

        from django.conf import settings
        from django.utils import timezone as tz
        from joybuy_crawler.render import (
            _kill_stale_crawler_browsers,
            _visible_text,
        )

        from crawler_control.services import record_account_session

        profile_root = (
            Path(settings.BASE_DIR).parent / "var" / "browser_profiles" / f"fb-{account.label}"
        )
        profile_root.mkdir(parents=True, exist_ok=True)
        # 上一个账号的登录窗口可能还挂着（同端口会 attach 到旧窗口）。
        from joybuy_crawler.render import _kill_stale_crawler_browsers as _kill

        _kill()
        page = None
        status = "failed"
        try:
            page = self._browser(profile_root)
            self._step(account, "浏览器已启动，打开 Joybuy 首页")
            self._goto(page, UK_BASE_URL)
            # CMP（cookieManageDrawer）异步渲染，等它出现再关，否则点空。
            time.sleep(6)
            self._dismiss_consent(page)
            self._step(
                account, f"首页 {page.url[:60]} | 隐私弹窗可见={self._consent_visible(page)}"
            )

            from crawler_control.management.commands.crawler_account_login import (
                _is_logged_in,
                _joybuy_cookies,
            )

            if not _is_logged_in(page, _visible_text):
                self._goto(page, f"{UK_BASE_URL}login")
                time.sleep(6)
                self._dismiss_consent(page)
                self._dismiss_consent(page)  # CMP 分两层，关两遍
                self._step(
                    account, f"登录页 {page.url[:60]} | 隐私弹窗可见={self._consent_visible(page)}"
                )
                if not self._click_facebook_button(page):
                    self._step(account, "未找到 Facebook 按钮")
                    return "failed"
                self._step(account, "已点击 Continue with Facebook，等待 Facebook 页签")
                # Facebook OAuth：可能是同窗跳转，也可能是弹窗。
                deadline = time.monotonic() + 60
                fb_page = None
                while time.monotonic() < deadline:
                    current = self._current_fb_page(page)
                    if current is not None:
                        fb_page = current
                        break
                    time.sleep(2)
                self._step(
                    account,
                    "页签状态 "
                    + str(
                        [
                            (getattr(page.get_tab(t), "url", "?") or "?")[:50]
                            for t in page.get_tabs()
                        ]
                    ),
                )
                if fb_page is None:
                    self.stdout.write("  未能进入 Facebook 登录页。")
                    return "failed"

                self._step(
                    account, f"进入 Facebook 流程：{(getattr(fb_page, 'url', '') or '')[:70]}"
                )
                outcome = self._drive_facebook(fb_page, account, password, secret, main_page=page)
                self._step(account, f"Facebook 流程结束：{outcome}")
                if outcome in {"banned", "bad_credentials", "network"}:
                    return outcome
                # 等 OAuth 回跳 Joybuy。
                joybuy_deadline = time.monotonic() + 45
                while time.monotonic() < joybuy_deadline:
                    try:
                        if _is_logged_in(page, _visible_text):
                            break
                    except Exception:  # noqa: BLE001 - transient DOM races
                        pass
                    time.sleep(2)
                else:
                    self._step(account, f"自动登录未回到 Joybuy 已登录态（当前 {page.url[:60]}）")
                    outcome = "stuck"
                if outcome == "stuck":
                    return "failed"

            cookies = _joybuy_cookies(page)
            if not cookies:
                self.stdout.write("  未捕获到 Joybuy Cookie。")
                return "failed"
            record_account_session(
                account,
                {
                    "cookies": cookies,
                    "user_agent": page.user_agent or "",
                    "captured_at": tz.now().isoformat(),
                },
            )
            account.refresh_from_db()
            account.note = f"自动 FB 登录成功，已保存会话（{len(cookies)} 条 Cookie）。"
            account.save(update_fields=["note", "updated_at"])
            return "ok"
        except Exception as exc:  # noqa: BLE001 - per-account isolation
            import traceback

            trace = traceback.format_exc()
            try:
                dump_dir = Path(settings.BASE_DIR).parent / "var" / "logs"
                dump_dir.mkdir(parents=True, exist_ok=True)
                (dump_dir / f"fb_auto_error_{account.label}.txt").write_text(
                    trace[-4000:], encoding="utf-8"
                )
                if page is not None:
                    page.get_screenshot(
                        path=str(dump_dir / f"fb_auto_error_{account.label}.png"), full_page=False
                    )
            except Exception:  # noqa: BLE001, S110 - 诊断失败不影响主流程
                pass
            self.stdout.write(
                f"  自动登录异常：{str(exc)[:200]}（traceback: var/logs/fb_auto_error_{account.label}.txt）"
            )
            status = "failed"
        finally:
            if page is not None:
                try:
                    page.quit()
                except Exception:  # noqa: BLE001, S110
                    pass
                _kill_stale_crawler_browsers()
        return status

    def _current_fb_page(self, page):
        """The tab currently showing facebook.com (OAuth may open a popup).

        DrissionPage 4.x 的 ``get_tabs()`` 返回**标签页 ID 字符串**，必须经
        ``get_tab(id)`` 换成 Tab 对象才能读 ``url``——2026-11-13 修复：此前
        ``tab.url`` 对字符串抛 AttributeError 被吞掉，弹窗形态的 OAuth 永远
        探测不到，误报「未能进入 Facebook 登录页」。
        """

        try:
            for tab_id in page.get_tabs():
                try:
                    tab = page.get_tab(tab_id)
                except Exception:  # noqa: BLE001 - tab 可能刚关闭
                    continue
                url = getattr(tab, "url", None) or ""
                if "facebook.com" in url:
                    return tab
        except Exception:  # noqa: BLE001 - tab list races
            pass
        if "facebook.com" in (page.url or ""):
            return page
        return None

    def _drive_facebook(self, fb_page, account, password, secret, main_page=None):
        """Fill the FB form / 2FA / OAuth consent; returns 'ok' | 'banned' | 'bad_credentials' | 'stuck'.

        2026-11-13 加固：FB OAuth 弹窗在授权完成后会**自行关闭**，DrissionPage 对已关闭
        的目标做任何操作都会抛 ``PageDisconnectedError``（"与页面的连接已断开"）。因此
        每一轮循环都重新从 ``get_tabs()`` 取当前 FB 页签，并把页面操作整体包在 except 里
        ——断连即视为「弹窗已结束」，回到主页面等 ``pin`` Cookie，而不是让异常冒到外层。
        """

        # 2026-11-13 实测：FB 登录页要 6–20s 才渲染出表单（OAuth v17 dialog 冷启
        # 19.8s / 暖 11.4s，页面本身是客户端渲染），90s 足够；此前「一直未知」
        # 不是等得不够久，而是选择器过时（见 _classify_facebook_page 注释）。
        page_timeout = float(os.getenv("FB_LOGIN_PAGE_TIMEOUT", "90"))
        deadline = time.monotonic() + page_timeout
        fill_attempts = 0
        two_factor_attempts = 0
        dumped_unknown = False
        errors_logged = 0
        while time.monotonic() < deadline:
            current = self._current_fb_page(main_page)
            if current is None:
                # 没有 facebook.com 页签 = OAuth 弹窗已闭合/已回跳 Joybuy。
                return "ok"
            fb_page = current
            try:
                kind = self._classify_facebook_page(fb_page)
            except Exception as exc:  # noqa: BLE001 - 页签正在导航
                if errors_logged < 3:
                    self._step(account, f"FB 页面读取异常：{type(exc).__name__}: {str(exc)[:120]}")
                    errors_logged += 1
                time.sleep(3)
                continue
            self._step(
                account,
                f"FB 状态={kind or '未知'} | {(getattr(fb_page, 'url', '') or '')[:70]}",
            )
            if kind == "network":
                self._step(account, "facebook.com 无法访问（网络/VPN 不通），本轮终止")
                account.note = "facebook.com 网络不可达：本轮未执行自动登录，请检查代理/VPN。"
                account.save(update_fields=["note", "updated_at"])
                return "network"
            if kind == "banned":
                self._dump_fb_html(fb_page, account, "banned")
                account.note = "Facebook 账号疑似被封（自动检测），已跳过，未保存会话。"
                account.save(update_fields=["note", "updated_at"])
                return "banned"
            if kind == "bad_credentials":
                account.note = "Facebook 密码疑似不正确，需要人工处理。"
                account.save(update_fields=["note", "updated_at"])
                return "bad_credentials"
            try:
                acted = self._act_on_facebook_page(
                    fb_page,
                    kind,
                    account,
                    password,
                    secret,
                    fill_attempts=fill_attempts,
                    two_factor_attempts=two_factor_attempts,
                    dumped_unknown=dumped_unknown,
                )
            except Exception as exc:  # noqa: BLE001 - 断连/导航中操作失败，下一轮重新取页签
                if errors_logged < 3:
                    self._step(account, f"FB 页面操作异常：{type(exc).__name__}: {str(exc)[:120]}")
                    errors_logged += 1
                time.sleep(3)
                continue
            fill_attempts = acted["fill_attempts"]
            two_factor_attempts = acted["two_factor_attempts"]
            dumped_unknown = acted["dumped_unknown"]
            time.sleep(1)
        return "stuck"

    def _act_on_facebook_page(
        self,
        fb_page,
        kind,
        account,
        password,
        secret,
        *,
        fill_attempts,
        two_factor_attempts,
        dumped_unknown,
    ):
        """One FB page action; returns updated progress flags."""

        state = {
            "fill_attempts": fill_attempts,
            "two_factor_attempts": two_factor_attempts,
            "dumped_unknown": dumped_unknown,
        }
        if kind == "form" and fill_attempts < 2:
            # 2026-11-13：input 没有 id，只有 name；提交按钮是 div[role="button"]
            # （全页 0 个 tag:button），所以必须走 _find_displayed 的 role 扫描，
            # 最后才兜底 input[type=submit]。
            # 实测：点提交后页面会短暂重渲染（表单消失 3–4s 再回来），字段可能被
            # 清空；因此允许最多重填 2 次，第 2 次改用「密码框回车」提交（不依赖
            # 那个 div 按钮的命中），并把实际点击目标写进日志便于定位。
            email_ele = self._ele(fb_page, 'css:input[name="email"]', timeout=2)
            pass_ele = self._ele(fb_page, 'css:input[name="pass"]', timeout=2)
            if email_ele is None or pass_ele is None:
                return state
            email_ele.input(account.label, clear=True)  # 第 1 列是账号
            pass_ele.input(password, clear=True)  # 第 2 列才是密码
            # FB 的输入框是 React 受控组件：只写 DOM value 时 React state 仍为空，
            # 「登录」div 按钮就是禁用态，点了没有任何反应（实测：点完页面不变、
            # FB 侧也没有凭据错误，profile 里始终没有 c_user/xs）。这里用原生
            # value setter + input/change 事件再把值刷一遍，让 React 接管。
            try:
                fb_page.run_js(
                    """
const set = (sel, val) => {
  const el = document.querySelector(sel);
  if (!el) return;
  const desc = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
  desc.set.call(el, val);
  el.dispatchEvent(new Event('input', {bubbles: true}));
  el.dispatchEvent(new Event('change', {bubbles: true}));
};
set('input[name="email"]', arguments[0]);
set('input[name="pass"]', arguments[1]);
""",
                    account.label,
                    password,
                )
            except Exception:  # noqa: BLE001 - 刷新失败就按已输入的内容提交
                pass
            try:  # 只记录长度，绝不打凭据
                filled = (
                    len(getattr(email_ele, "value", "") or ""),
                    len(getattr(pass_ele, "value", "") or ""),
                )
            except Exception:  # noqa: BLE001 - 元素失效
                filled = (-1, -1)
            self._step(
                account,
                f"已填入凭据（第 {fill_attempts + 1} 次）：账号框 {filled[0]} 字符、"
                f"密码框 {filled[1]} 字符，准备提交",
            )
            if fill_attempts == 0:
                button = self._find_displayed(
                    fb_page, ["log in", "登录"], wait_seconds=4
                ) or self._ele(fb_page, 'css:input[type="submit"]', timeout=2)
                if button is None:
                    self._step(account, "未找到可见的提交按钮，改在密码框回车提交")
                    pass_ele.input("\n")
                else:
                    label = (getattr(button, "text", "") or "").strip()[:24]
                    try:
                        button.click()
                        self._step(account, f"已点击提交按钮「{label}」")
                    except Exception as exc:  # noqa: BLE001 - 真实点击失败改 JS 点击
                        self._step(
                            account, f"真实点击失败（{type(exc).__name__}），改 JS 点击「{label}」"
                        )
                        button.click(by_js=True)
            else:
                self._step(account, "表单仍在，改在密码框回车提交")
                pass_ele.input("\n")
            state["fill_attempts"] = fill_attempts + 1
            time.sleep(6)
            return state
        if kind == "need_2fa":
            if two_factor_attempts >= 2:
                return state  # 连续两次验证码失败，交给外层人工兜底
            code = self._totp(secret)
            code_ele = self._ele(fb_page, "#approvals_code", timeout=2) or self._ele(
                fb_page, 'css:input[name="approvals_code"]', timeout=1
            )
            if code_ele is None:
                return state
            code_ele.input(code, clear=True)
            try:
                submit = self._ele(fb_page, "#checkpointSubmitButton", timeout=2)
                if submit is None:
                    submit = self._find_displayed(
                        fb_page, ["submit", "继续", "continue"], wait_seconds=3
                    ) or self._ele(fb_page, 'css:input[type="submit"]', timeout=2)
                if submit is not None:
                    submit.click()
            except Exception:  # noqa: BLE001 - 按钮文案/结构不固定，下一轮重试
                pass
            state["two_factor_attempts"] += 1
            time.sleep(5)
            return state
        if kind == "checkpoint":
            # 「记住浏览器 / 继续」这类可推进的检查点。
            button = self._ele(fb_page, "#checkpointSubmitButton", timeout=3)
            if button is None:
                button = self._ele(fb_page, 'button[name="__CONFIRM__"]', timeout=1)
            if button is not None:
                button.click()
                time.sleep(5)
            return state
        # kind == ""：FB 登录表单、2FA、授权确认之外的一切页面——多半是
        # OAuth 授权弹窗（"以 xx 身份继续"）或 Facebook 帮助/错误页。
        confirm = self._ele(fb_page, 'button[name="__CONFIRM__"]', timeout=2)
        if confirm is None:
            confirm = self._find_displayed(
                fb_page, ["continue as", "以…身份继续", "继续"], wait_seconds=2
            )
        if confirm is not None:
            try:
                confirm.click()
            except Exception:  # noqa: BLE001 - 真实点击失败时用 JS 点击
                confirm.click(by_js=True)
            time.sleep(5)
            return state
        if not dumped_unknown:
            self._dump_fb_html(fb_page, account, "unknown")
            state["dumped_unknown"] = True
        for sel in ('button[type="submit"]', "#checkpointSubmitButton"):
            button = self._ele(fb_page, sel, timeout=1)
            if button is not None:
                try:
                    button.click()
                except Exception:  # noqa: BLE001
                    button.click(by_js=True)
                time.sleep(4)
                break
        return state

    # ------------------------------------------------------------------
    # Manual fallback (same experience as the admin 登录 button)
    # ------------------------------------------------------------------

    def _manual_login(self, account, *, wait_seconds):
        from django.conf import settings
        from django.utils import timezone as tz
        from joybuy_crawler.render import _kill_stale_crawler_browsers, _visible_text

        from crawler_control.services import record_account_session

        profile_root = (
            Path(settings.BASE_DIR).parent / "var" / "browser_profiles" / f"fb-{account.label}"
        )
        profile_root.mkdir(parents=True, exist_ok=True)
        account.note = "自动登录未成功：请在弹出的浏览器里手动完成 Facebook 登录。"
        account.save(update_fields=["note", "updated_at"])
        self.stdout.write(
            f">>> 请在弹出的浏览器中为账号 {account.label} 手动完成 Facebook 登录"
            f"（最多等待 {wait_seconds} 秒）……"
        )
        page = None
        try:
            page = self._browser(profile_root)
            self._goto(page, UK_BASE_URL)
            time.sleep(3)
            from crawler_control.management.commands.crawler_account_login import (
                _is_logged_in,
                _joybuy_cookies,
            )

            deadline = time.monotonic() + wait_seconds
            while time.monotonic() < deadline:
                time.sleep(4)
                try:
                    if _is_logged_in(page, _visible_text):
                        break
                except Exception:  # noqa: BLE001 - transient DOM races
                    continue
            else:
                account.note = "人工登录未在限时内完成，未保存会话；可重跑 --login 再试。"
                account.save(update_fields=["note", "updated_at"])
                return "manual_pending"
            self._goto(page, UK_BASE_URL)
            time.sleep(4)
            cookies = _joybuy_cookies(page)
            if not cookies:
                account.note = "人工登录后未捕获到 Joybuy Cookie，请重试。"
                account.save(update_fields=["note", "updated_at"])
                return "manual_pending"
            record_account_session(
                account,
                {
                    "cookies": cookies,
                    "user_agent": page.user_agent or "",
                    "captured_at": tz.now().isoformat(),
                },
            )
            account.refresh_from_db()
            account.note = f"人工登录成功，已保存会话（{len(cookies)} 条 Cookie）。"
            account.save(update_fields=["note", "updated_at"])
            return "manual_ok"
        finally:
            if page is not None:
                try:
                    page.quit()
                except Exception:  # noqa: BLE001, S110
                    pass
                _kill_stale_crawler_browsers()

    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        rows = self._read_rows(options["excel"])
        if not rows:
            raise CommandError("Excel 里没有可用账号行。")
        if options["create_only"] or not options["login"]:
            self._create_accounts(rows, prefix=options["group_prefix"], size=options["group_size"])
            return

        from crawler_control.models import CrawlerAccount

        if options["manual"]:
            account = CrawlerAccount.objects.filter(
                label=options["manual"], deleted_at=None
            ).first()
            if account is None:
                raise CommandError(f"找不到账号 {options['manual']}。")
            self._manual_login(account, wait_seconds=options["manual_wait"])
            return

        if not self._facebook_reachable():
            raise CommandError(
                "www.facebook.com 不可达（网络/VPN 未覆盖 Facebook），自动登录已中止："
                "本次没有对任何账号执行登录。请先让 facebook.com 可访问后重跑 --login。"
            )

        password_by_id = {account_id: password for account_id, password, _secret in rows}
        secret_by_id = {account_id: secret for account_id, _password, secret in rows}
        accounts = (
            CrawlerAccount.objects.filter(
                deleted_at=None, account_group__startswith=options["group_prefix"]
            )
            .exclude(session_status="VALID")
            .order_by("account_group", "pk")
        )
        if options["limit"]:
            accounts = accounts[: options["limit"]]
        self.stdout.write(f"待登录账号 {accounts.count()} 个。")
        done = 0
        for account in accounts:
            label = account.label
            if label not in password_by_id:
                self.stdout.write(f"跳过 {label}：Excel 中没有该账号的凭据。")
                continue
            if account.session_status == "VALID":
                continue
            self.stdout.write(f"== {label}（组 {account.account_group}）自动登录……")
            outcome = self._auto_login(
                account,
                password_by_id[label],
                secret_by_id[label],
                manual_wait=options["manual_wait"],
            )
            self._progress(label, outcome)
            if outcome in {"ok", "manual_ok"}:
                done += 1
                self.stdout.write(self.style.SUCCESS(f"== {label} 登录成功。"))
            elif outcome == "network":
                self.stdout.write(
                    self.style.ERROR("== facebook.com 网络不可达，本轮终止；其余账号未尝试。")
                )
                break
            elif outcome == "banned":
                self.stdout.write(self.style.WARNING(f"== {label} 疑似被封，跳过。"))
            elif outcome in {"manual_pending", "manual_ok"}:
                self.stdout.write(f"== {label} 人工流程结束：{outcome}。")
            else:
                if not options["no_manual_fallback"]:
                    result = self._manual_login(account, wait_seconds=options["manual_wait"])
                    self._progress(label, result)
                    if result == "manual_ok":
                        done += 1
                else:
                    self.stdout.write(
                        self.style.WARNING(f"== {label} 自动登录失败（人工兜底已关）。")
                    )
            time.sleep(random.uniform(options["delay_min"], options["delay_max"]))
        self.stdout.write(f"本轮完成 {done} 个登录。")
