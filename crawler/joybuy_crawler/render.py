"""DrissionPage real-browser rendering fallback (2026-11-05 rebuild).

docs/11 evidence: headless/plain-HTTP fetches of joybuy.co.uk can land on
the "Risk Control" interception page while a real browser renders fine.
This module is the shared fetch layer for pages that plain HTTP cannot
serve: the Scrapy middleware swaps blocked responses for rendered HTML,
the tree-sync command captures the live category menu, and the account
login flow (round 2) uses the same session handling.

Discipline (docs/05 §7.3, updated 2026-11-05): AVOIDING risk control
comes first — real Chrome, normalized fingerprint (automation flags
stripped, real Chrome UA, dedicated reusable profile), low rates. When a
captcha/risk page still appears, the run pauses and the operator completes
it manually in a headed browser window (human-in-the-loop); captchas are
never solved programmatically, signatures never forged, and risk pages
are never parsed as product/listing pages.
"""

import re
import time
from dataclasses import dataclass, field

# Substrings that identify a Joybuy risk-control / interception page.
# A page matching these is NEVER parsed as a listing or product page.
# Plain "captcha" is deliberately NOT a marker: the normal Joybuy footer
# contains "protected by reCAPTCHA" and must not false-positive.
RISK_CONTROL_MARKERS = (
    "risk control",
    "risk-control",
    "access denied",
    "403 forbidden",
    "verify you are human",
    "are you a robot",
    "temporary service interruption",
    "访问验证",
    "安全验证",
    # 2026-11-05 中文界面现场核对：限流/拦截页标题为「403 页面」，
    # 正文为「服务暂时中断 / 系统当前负载过高」，必须按拦截页处理。
    "403 页面",
    "服务暂时中断",
    "系统当前负载过高",
)

# Substrings / URL fragments that identify a login wall.
LOGIN_URL_FRAGMENTS = ("/login", "passport.", "signin", "sign-in")
LOGIN_TEXT_MARKERS = ("sign in or register", "请登录", "login to continue")


@dataclass
class RenderedPage:
    url: str
    html: str
    status: int  # 200 rendered ok, 0 = fetch failure
    risk_control: bool = False
    login_required: bool = False
    rendered: bool = False  # True when DrissionPage produced the HTML
    error: str = ""
    cookies: list[dict] = field(default_factory=list)


_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE
)
_TAG_RE = re.compile(r"<[^>]+>")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.DOTALL | re.IGNORECASE)


def _visible_text(html: str) -> str:
    """Title + visible body text, with all script/style payloads removed.

    Markers must never be matched against raw HTML: Joybuy embeds i18n
    bundles containing "403 Forbidden" and "protected by reCAPTCHA" in
    every normal page (2026-11-05 live evidence).
    """

    if not html:
        return ""
    title = _TITLE_RE.search(html)
    parts = [title.group(1) if title else ""]
    body = _SCRIPT_STYLE_RE.sub(" ", html)
    body = _TAG_RE.sub(" ", body)
    parts.append(body)
    return " ".join(parts)[:6000].lower()


def detect_risk_control(html: str) -> bool:
    text = _visible_text(html)
    return any(marker in text for marker in RISK_CONTROL_MARKERS)


def detect_login_required(url: str, html: str) -> bool:
    lowered_url = (url or "").lower()
    if any(fragment in lowered_url for fragment in LOGIN_URL_FRAGMENTS):
        return True
    # Only treat text as a login wall when the visible page is tiny; real
    # listing pages legitimately contain "sign in" links.
    text = _visible_text(html)
    if len(text) < 4000:
        return any(marker in text for marker in LOGIN_TEXT_MARKERS)
    return False


def classify_page(url: str, html: str) -> RenderedPage:
    return RenderedPage(
        url=url,
        html=html or "",
        status=200 if html else 0,
        risk_control=detect_risk_control(html),
        login_required=detect_login_required(url, html),
    )


def _build_options(*, headless: bool, profile_dir: str | None = None):
    from DrissionPage import ChromiumOptions

    options = ChromiumOptions()
    # Never touch the operator's own Chrome: a dedicated debugging port +
    # dedicated user-data dir keep the crawler browser isolated. render_page
    # additionally verifies the process list after connecting.
    options.set_address(f"127.0.0.1:{_DEBUG_PORT}")
    options.set_user_data_path(
        str(profile_dir or (_browser_profile_root() / "profile"))
    )
    options.set_paths(browser_path=_chrome_path() or None)
    # Joybuy 403s browsers that announce automation (docs/11: real browsers
    # are fine). These flags make Chromium present itself as a normal
    # browser; risk-control/login pages are still never parsed or bypassed.
    options.set_argument("--disable-blink-features=AutomationControlled")
    # Proxy: follow the system setting by default (the operator's VPN may
    # be required to reach the site); set CRAWL_BROWSER_PROXY=direct to
    # force a direct connection bypassing the system proxy.
    import os

    if os.getenv("CRAWL_BROWSER_PROXY", "").strip().lower() == "direct":
        options.set_argument("--no-proxy-server")
    if headless:
        options.headless()
        # Headless Chrome's UA contains "HeadlessChrome" — normalize it.
        options.set_user_agent(_chrome_user_agent())
    options.set_argument("--no-first-run")
    options.set_argument("--disable-gpu")
    options.set_argument("--window-size", "1440,900")
    options.set_timeouts(page_load=45, script=20)
    return options


def _browser_profile_root():
    from pathlib import Path

    from django.conf import settings

    root = (
        Path(getattr(settings, "CRAWL_BROWSER_PROFILE_ROOT", ""))
        if getattr(settings, "CRAWL_BROWSER_PROFILE_ROOT", "")
        else Path(settings.BASE_DIR).parent / "var" / "browser_profiles"
    )
    root.mkdir(parents=True, exist_ok=True)
    return root


def reset_browser_profile() -> None:
    """Delete the crawler's browser profile (fresh session next launch).

    Only ever touches the crawler's own ``browser_profiles`` directory.
    Live evidence 2026-11-05: Joybuy serves a degraded homepage variant to
    warm profiles; a fresh profile receives the full SSR payload.
    """

    import shutil

    profile = _browser_profile_root() / "profile"
    _kill_stale_crawler_browsers()
    if profile.exists():
        shutil.rmtree(profile, ignore_errors=True)


def _chrome_path() -> str:
    """Locate an installed Chrome; empty string lets DrissionPage search."""

    from pathlib import Path

    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return ""


_NORMAL_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)


def _chrome_user_agent() -> str:
    """The installed Chrome's real UA (stripped of Headless markers)."""

    import subprocess

    chrome = _chrome_path()
    if chrome:
        try:
            output = subprocess.run(
                [chrome, "--version"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            ).stdout.strip()
            # "Google Chrome 141.0.7390.66" -> embed the real version.
            version = output.rsplit(" ", 1)[-1] if output else ""
            if version:
                return _NORMAL_CHROME_UA.replace(
                    "Chrome/141.0.0.0", f"Chrome/{version}"
                )
        except Exception:  # noqa: BLE001, S110 - UA detection is best-effort
            pass
    return _NORMAL_CHROME_UA


def _apply_cookies(browser_page, cookies: list[dict]) -> None:
    """Inject stored session cookies (from CrawlerAccount.session_cipher)."""

    if not cookies:
        return
    try:
        browser_page.set.cookies(cookies)
    except Exception:  # noqa: BLE001 - API shape differs across builds
        # Older DrissionPage builds expose set_cookies on the page directly.
        browser_page.set_cookies(cookies)


def _to_cookie_dicts(raw_cookies) -> list[dict]:
    cookies = []
    for cookie in raw_cookies or []:
        if isinstance(cookie, dict) and cookie.get("name"):
            cookies.append(
                {
                    "name": cookie.get("name"),
                    "value": cookie.get("value", ""),
                    "domain": cookie.get("domain", ""),
                    "path": cookie.get("path", "/"),
                }
            )
    return cookies


_DEBUG_PORT = 9333


_LOGIN_DEBUG_PORT = 9334


def _crawler_chrome_pids() -> list[str]:
    """PIDs of Chrome processes that belong to the crawler, and only those.

    Matching rules: the command line references the crawler's own
    ``browser_profiles`` directory, or it listens on one of the crawler's
    dedicated debug ports (9333 crawl / 9334 login). The operator's own
    Chrome never matches either marker.
    """

    import subprocess

    script = (
        "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" "
        "| Where-Object { $_.CommandLine -match 'browser_profiles"
        f"|remote-debugging-port=({_DEBUG_PORT}|{_LOGIN_DEBUG_PORT})' }} "
        "| Select-Object -ExpandProperty ProcessId"
    )
    try:
        output = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        ).stdout
    except Exception:  # noqa: BLE001 - cleanup is best-effort
        return []
    return [pid.strip() for pid in output.split() if pid.strip().isdigit()]


def _kill_stale_crawler_browsers() -> int:
    """Kill leftover crawler Chrome instances; return how many were killed.

    Called before every launch and after every teardown: DrissionPage's
    ``quit()`` can leave the browser process alive (especially when it
    attached to an already-running instance), and a 15-page task used to
    stack up one browser per page. One session + an explicit reap keeps
    exactly one browser per task.
    """

    import subprocess

    pids = _crawler_chrome_pids()
    killed = 0
    for pid in pids:
        subprocess.run(
            ["taskkill", "/PID", pid, "/F", "/T"],
            check=False,
            capture_output=True,
            timeout=15,
        )
        killed += 1
    return killed


def _verify_browser_isolation() -> None:
    """Abort if the debug port is served by a non-crawler Chrome.

    Every chrome.exe listening on the crawler's debug port MUST carry our
    dedicated ``--user-data-dir``; anything else means DrissionPage
    connected to a browser we did not launch (e.g. the operator's own
    browser with a debug port) and we must not navigate in it.
    """

    import subprocess

    output = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" "
            "| Where-Object { $_.CommandLine -match 'remote-debugging-port="
            + str(_DEBUG_PORT)
            + "' } | Select-Object -ExpandProperty CommandLine",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    ).stdout
    lines = [line for line in output.splitlines() if "chrome.exe" in line.lower()]
    if not lines:
        return  # no debug-port chrome found (headless launch may still be starting)
    our_marker = str(_browser_profile_root()).replace("\\", "/").lower()
    for line in lines:
        normalized = line.replace("\\", "/").lower()
        if "browser_profiles" not in normalized and our_marker not in normalized:
            raise RuntimeError(
                "Browser isolation violated: a chrome.exe is listening on the "
                "crawler debug port without the crawler user-data-dir. "
                "Refusing to navigate (it may be the operator's own browser)."
            )


def _assert_clean_browser(page) -> None:
    """Second isolation layer: the connected browser must be a blank one.

    A dedicated crawler instance starts with exactly one new-tab/blank
    page; the operator's own browser always has real tabs open. If the
    browser we connected to already shows real pages, quit immediately
    and refuse to navigate (2026-11-05: measured fresh instance = one
    ``chrome://newtab/`` tab).
    """

    try:
        tab_ids = page.tab_ids or []
    except Exception:  # noqa: BLE001 - unreadable tab list cannot be judged
        return
    for tab_id in tab_ids:
        try:
            url = (page.get_tab(tab_id).url or "").strip()
        except Exception:  # noqa: BLE001, S112 - skip unreadable tabs
            continue
        if url and url not in ("about:blank",) and not url.startswith("chrome://"):
            try:
                page.quit()
            except Exception:  # noqa: BLE001, S110
                pass
            raise RuntimeError(
                "Browser isolation violated: the connected browser already has "
                f"open pages ({url[:80]}). It is not a dedicated crawler "
                "instance — refusing to navigate it."
            )


def _capture_document_html(page, url: str, *, timeout: float = 30.0) -> str:
    """Capture the server-rendered HTML of ``url`` from the network layer.

    Joybuy's hydrated DOM drops most server-rendered links (2026-11-05
    live evidence), so readers that need SSR content must take the
    document response body instead of ``page.html``. Callers must call
    ``page.listen.start(<url substring>)`` BEFORE ``page.get``.
    """

    try:
        packet = page.listen.wait(timeout=timeout)
    except Exception:  # noqa: BLE001 - fall back to whatever the DOM holds
        return ""
    body = packet.response.body if packet.response else None
    if isinstance(body, bytes):
        try:
            body = body.decode("utf-8")
        except UnicodeDecodeError:
            body = body.decode("latin-1", errors="replace")
    return str(body or "")


class BrowserSession:
    """One real-Chrome session reused across pages, always closed at exit.

    Why this exists (2026-11-05): ``render_page`` launched a fresh browser
    for every URL, so a 15-page category capture stacked up ~15 Chrome
    instances at once (users saw "几十个浏览器"), and a failed ``quit()``
    left them running. A session opens the browser once, navigates many
    URLs, and on ``close()`` runs ``quit()`` plus an explicit process reap.

    Isolation is unchanged: the browser is the crawler's own
    ``user-data-dir`` on the crawler debug port, verified on open.
    """

    def __init__(
        self,
        *,
        headless: bool = True,
        cookies: list[dict] | None = None,
        profile_dir: str | None = None,
    ) -> None:
        self.headless = headless
        self.cookies = cookies or []
        self.profile_dir = profile_dir
        self.page = None

    def __enter__(self) -> "BrowserSession":  # noqa: PYI034 - plain context manager
        self.open()
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def open(self) -> None:
        from DrissionPage import ChromiumPage

        _kill_stale_crawler_browsers()
        page = ChromiumPage(
            _build_options(headless=self.headless, profile_dir=self.profile_dir)
        )
        _verify_browser_isolation()
        try:
            _assert_clean_browser(page)
            if self.cookies:
                _apply_cookies(page, self.cookies)
        except Exception:
            try:
                page.quit()
            except Exception:  # noqa: BLE001, S110 - teardown is best-effort
                pass
            _kill_stale_crawler_browsers()
            raise
        self.page = page

    def get(
        self,
        url: str,
        *,
        wait_seconds: float = 3.0,
        scroll_for_lazy_load: bool = False,
        capture_ssr: bool = False,
    ) -> RenderedPage:
        if self.page is None:
            raise RuntimeError("BrowserSession.open() must be called before get().")
        page = self.page
        try:
            try:
                page.listen.stop()
            except Exception:  # noqa: BLE001, S110 - listener may not be running
                pass
            if capture_ssr:
                page.listen.start(url.split("?")[0])
            page.get(url)
            if page.url in ("", "about:blank", "chrome://newtab/"):
                raise RuntimeError(f"Browser did not navigate to {url}.")
            html = _capture_document_html(page, url) if capture_ssr else ""
            if not html:
                if wait_seconds:
                    time.sleep(wait_seconds)
                if scroll_for_lazy_load:
                    try:
                        page.scroll.to_bottom()
                        time.sleep(1.0)
                    except Exception:  # noqa: BLE001, S110 - best-effort lazy load
                        pass
                html = page.html or ""
            result = classify_page(page.url, html)
            result.rendered = True
            result.cookies = _to_cookie_dicts(
                page.cookies() if not self.cookies else []
            )
            return result
        except Exception as exc:  # noqa: BLE001 - renderer failures are runtime conditions
            return RenderedPage(url=url, html="", status=0, error=str(exc))

    def close(self) -> None:
        page, self.page = self.page, None
        if page is None:
            return
        try:
            page.quit()
        except Exception:  # noqa: BLE001, S110 - teardown is best-effort
            pass
        time.sleep(0.2)
        # quit() is not always enough; never leave a crawler window behind.
        _kill_stale_crawler_browsers()


def render_page(
    url: str,
    *,
    cookies: list[dict] | None = None,
    headless: bool = True,
    wait_seconds: float = 3.0,
    scroll_for_lazy_load: bool = False,
    capture_ssr: bool = False,
    profile_dir: str | None = None,
) -> RenderedPage:
    """Fetch one URL through a real Chrome via DrissionPage.

    Single-shot convenience wrapper around :class:`BrowserSession`: the
    browser is always closed (and reaped) when the call returns. Batch
    readers should keep one session open for all pages instead — see
    ``capture_category_tree``.

    Lazy-loaded Joybuy pages only render viewport content, so
    ``scroll_for_lazy_load`` scrolls to the bottom before reading the DOM.
    With ``capture_ssr`` the DOM is taken from the document response
    (pre-hydration) instead of the live page.
    """

    session = BrowserSession(
        headless=headless, cookies=cookies, profile_dir=profile_dir
    )
    try:
        session.open()
        return session.get(
            url,
            wait_seconds=wait_seconds,
            scroll_for_lazy_load=scroll_for_lazy_load,
            capture_ssr=capture_ssr,
        )
    except Exception as exc:  # noqa: BLE001 - renderer failures are runtime conditions
        return RenderedPage(url=url, html="", status=0, error=str(exc))
    finally:
        session.close()
