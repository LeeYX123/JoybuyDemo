"""DrissionPage real-browser rendering fallback (2026-11-05 rebuild).

docs/11 evidence: headless/plain-HTTP fetches of joybuy.co.uk can land on
the "Risk Control" interception page while a real browser renders fine.
This module is the shared fetch layer for pages that plain HTTP cannot
serve: the Scrapy middleware swaps blocked responses for rendered HTML,
the tree-sync command captures the live category menu, and the account
login flow (round 2) uses the same session handling.

Discipline (docs/05 §7-8): real-browser sessions only, no captcha or
risk-control bypass, cookie sessions are captured from a manual login
the account owner performs themselves; passwords are never collected.
"""

import time
from dataclasses import dataclass, field

# Substrings that identify a Joybuy risk-control / interception page.
# A page matching these is NEVER parsed as a listing or product page.
RISK_CONTROL_MARKERS = (
    "risk control",
    "risk-control",
    "access denied",
    "verify you are human",
    "captcha",
    "访问验证",
    "安全验证",
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


def detect_risk_control(html: str) -> bool:
    lowered = (html or "")[:200000].lower()
    return any(marker in lowered for marker in RISK_CONTROL_MARKERS)


def detect_login_required(url: str, html: str) -> bool:
    lowered_url = (url or "").lower()
    if any(fragment in lowered_url for fragment in LOGIN_URL_FRAGMENTS):
        return True
    # Only treat text as a login wall when the page is tiny; large real
    # listing pages legitimately contain "sign in" links.
    body = (html or "")[:200000].lower()
    if len(html or "") < 4000:
        return any(marker in body for marker in LOGIN_TEXT_MARKERS)
    return False


def classify_page(url: str, html: str) -> RenderedPage:
    return RenderedPage(
        url=url,
        html=html or "",
        status=200 if html else 0,
        risk_control=detect_risk_control(html),
        login_required=detect_login_required(url, html),
    )


def _build_options(*, headless: bool):
    from DrissionPage import ChromiumOptions

    options = ChromiumOptions()
    if headless:
        options.headless()
    options.set_argument("--no-first-run")
    options.set_argument("--disable-gpu")
    options.set_argument("--window-size", "1440,900")
    options.set_timeouts(page_load=45, script=20)
    options.set_prefers_reduction_motion()
    return options


def _apply_cookies(browser_page, cookies: list[dict]) -> None:
    """Inject stored session cookies (from CrawlerAccount.session_cipher)."""

    if not cookies:
        return
    try:
        browser_page.set.cookies(cookies)
    except Exception:
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


def render_page(
    url: str,
    *,
    cookies: list[dict] | None = None,
    headless: bool = True,
    wait_seconds: float = 3.0,
    scroll_for_lazy_load: bool = False,
) -> RenderedPage:
    """Fetch one URL through a real Chrome via DrissionPage.

    Lazy-loaded Joybuy pages only render viewport content, so
    ``scroll_for_lazy_load`` scrolls to the bottom before reading the DOM.
    """

    from DrissionPage import ChromiumPage

    page = ChromiumPage(_build_options(headless=headless))
    try:
        if cookies:
            _apply_cookies(page, cookies)
        page.get(url)
        if wait_seconds:
            time.sleep(wait_seconds)
        if scroll_for_lazy_load:
            try:
                page.scroll.to_bottom()
                time.sleep(1.0)
            except Exception:
                pass
        html = page.html or ""
        result = classify_page(page.url, html)
        result.rendered = True
        result.cookies = _to_cookie_dicts(page.cookies() if not cookies else [])
        return result
    except Exception as exc:  # noqa: BLE001 - renderer failures are runtime conditions
        return RenderedPage(url=url, html="", status=0, error=str(exc))
    finally:
        try:
            page.quit()
        except Exception:
            pass
