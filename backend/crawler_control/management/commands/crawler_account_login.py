"""Manual crawler-account login window (docs/05 §7.1/§7.3).

Spawned detached by the admin "登录" action. Opens a HEADED Chrome on a
per-account profile, the account owner completes Facebook login
themselves in that window, the command detects the signed-in state,
captures the Joybuy cookies and stores them encrypted via
``record_account_session``. Passwords are never collected or stored.

Detection (2026-11-05 site behaviour): joybuy.co.uk redirects anonymous
visitors to ``/login``, so the browser landing back on a real joybuy.co.uk
page (not /login) after the OAuth round-trip is the login signal. Only
joybuy.co.uk cookies are captured — a browser sitting on facebook.com is
still mid-flow and its cookies are never stored.
"""

import sys
import time
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
if str(REPOSITORY_ROOT / "crawler") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "crawler"))

LOGIN_BASE_URL = "https://www.joybuy.co.uk/"


class Command(BaseCommand):
    help = "Open a headed browser for manual crawler-account login (internal)."

    def add_arguments(self, parser):
        parser.add_argument("--account", type=str, required=True, help="CrawlerAccount public_id")
        parser.add_argument(
            "--timeout-seconds", type=int, default=480, help="Give up after this long"
        )

    def handle(self, *args, **options):
        from django.conf import settings
        from joybuy_crawler.render import _to_cookie_dicts, _visible_text

        from crawler_control.models import CrawlerAccount
        from crawler_control.services import record_account_session

        account = CrawlerAccount.objects.get(public_id=options["account"])
        if account.deleted_at is not None:
            # A deleted account must not be resurrected by a stale admin tab.
            self.stderr.write("该账号已删除，无法登录；请先重新创建账号。")
            return
        profile_root = (
            Path(settings.BASE_DIR).parent
            / "var"
            / "browser_profiles"
            / f"account-{str(account.public_id)[:8]}"
        )
        profile_root.mkdir(parents=True, exist_ok=True)
        account.note = "登录窗口已打开：请在弹出的浏览器中完成 Facebook 登录。"
        account.save(update_fields=["note", "updated_at"])

        from DrissionPage import ChromiumOptions, ChromiumPage

        timeout_seconds = max(60, int(options["timeout_seconds"]))
        chrome_options = ChromiumOptions()
        chrome_options.set_address("127.0.0.1:9334")  # dedicated port; never the crawl port
        chrome_options.set_user_data_path(str(profile_root))
        chrome_options.set_argument("--disable-blink-features=AutomationControlled")
        chrome_options.set_argument("--window-size", "1440,900")
        chrome_options.set_timeouts(page_load=45, script=20)

        deadline = time.monotonic() + timeout_seconds
        logged_in = False
        page = None
        try:
            page = ChromiumPage(chrome_options)
            page.get(LOGIN_BASE_URL)
            time.sleep(3)
            accept = page.ele("text:Accept all", timeout=3)
            if accept and accept.tag == "button":
                accept.click(by_js=True)
            # 登录动作的可靠信号：登录后站点不再把访问者 307 到 /login
            # （2026-11-05 起 joybuy.co.uk 对未登录访问者强制跳登录页），
            # 且当前页面必须已经回到 joybuy.co.uk —— 用户在 Facebook 授权页
            # 停留期间不能算登录成功，更不能把 facebook.com 的 Cookie 当会话。
            initial_cookie_names = {c.get("name") for c in _to_cookie_dicts(page.cookies() or [])}
            while time.monotonic() < deadline:
                time.sleep(4)
                try:
                    if _is_logged_in(page, _visible_text, initial_cookie_names):
                        logged_in = True
                        break
                except Exception:  # noqa: BLE001 - transient DOM races
                    continue
            if not logged_in:
                account.note = "登录未在限时内完成，未保存任何会话；可重新点击“登录”再试。"
                account.save(update_fields=["note", "updated_at"])
                return

            # Land on the homepage so cookie capture sees the full session.
            page.get(LOGIN_BASE_URL)
            time.sleep(4)
            if "/login" in (page.url or ""):
                account.note = "登录后仍被跳回登录页，未保存会话；请重新登录。"
                account.save(update_fields=["note", "updated_at"])
                return
            cookies = _joybuy_cookies(page)
            if not cookies:
                account.note = "未捕获到 Joybuy Cookie，登录结果未知；请重试。"
                account.save(update_fields=["note", "updated_at"])
                return
            record_account_session(
                account,
                {
                    "cookies": cookies,
                    "user_agent": page.user_agent or "",
                    "captured_at": timezone.now().isoformat(),
                },
            )
            account.refresh_from_db()
            account.note = f"登录成功，已保存会话（{len(cookies)} 条 Cookie）。"
            account.save(update_fields=["note", "updated_at"])
            self.stdout.write(
                self.style.SUCCESS(
                    f"Account {account.public_id} session saved ({len(cookies)} cookies)."
                )
            )
        except Exception as exc:  # noqa: BLE001 - report through account note
            account.note = f"登录窗口异常：{str(exc)[:300]}"
            account.save(update_fields=["note", "updated_at"])
            raise
        finally:
            if page is not None:
                try:
                    page.quit()
                except Exception:  # noqa: BLE001, S110
                    pass
                # quit() is not always enough; never leave the login window behind.
                from joybuy_crawler.render import _kill_stale_crawler_browsers

                _kill_stale_crawler_browsers()


def _is_logged_in(page, visible_text_fn, initial_cookie_names=None) -> bool:
    """Joybuy-only login signal (2026-11-05 site behaviour).

    joybuy.co.uk now 307s anonymous visitors to ``/login``, so "we are on a
    real joybuy.co.uk page and not on /login" is the decisive signal. A
    page still on facebook.com (or any other host) is the OAuth step, not
    a logged-in state, and must never be treated as success — that bug
    stored Facebook cookies as the account session on 2026-11-05.
    """

    url = (page.url or "").lower()
    if "joybuy.co.uk" not in url or "/login" in url:
        return False

    cookies = _joybuy_cookies(page)
    if len(cookies) < 3:
        return False

    text = visible_text_fn(page.html or "")
    if len(text) < 2000:
        return False  # interception/error page, not the real homepage
    return True


def _joybuy_cookies(page) -> list[dict]:
    """Only site cookies — third-party (e.g. facebook.com) must never be stored."""

    from joybuy_crawler.render import _to_cookie_dicts

    return [
        cookie
        for cookie in _to_cookie_dicts(page.cookies(all_domains=True) or [])
        if "joybuy" in (cookie.get("domain") or "").lower()
    ]
