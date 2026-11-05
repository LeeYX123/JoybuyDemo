"""Account session bridge: encrypted crawler session -> request cookies.

Why this module exists (2026-11-05)
-----------------------------------
Runs already carried an ``account`` FK, but only the DrissionPage fallback
ever handed that account's cookies to a request. Plain Scrapy requests went
out anonymously, so every page first hit the login wall (307 -> /login),
wasted a round trip and then required a full browser render. This module is
the single place that turns the encrypted session blob into cookies, used by
both the HTTP path and the browser fallback, so a run is authenticated from
its very first request.

Secrets rule: the blob stays encrypted in the database and is only decrypted
in the crawl process; nothing here logs cookie values.
"""

#: Cookie domains that belong to the source site. Anything else (Facebook
#: login cookies, analytics) must never be replayed to the source.
import logging

JOYBUY_COOKIE_DOMAIN_HINTS = ("joybuy",)

logger = logging.getLogger("joybuy_crawler.account_session")


def load_account_cookies(spider) -> list[dict]:
    """Decrypted cookie list for the run's account (empty when unavailable).

    The spider carries the ``CrawlRun``; ``run.account`` is the account
    pinned at start time. Undecryptable or missing sessions degrade to an
    anonymous crawl instead of failing the run.
    """

    run = getattr(spider, "run", None)
    account = getattr(run, "account", None) if run is not None else None
    if account is None or not getattr(account, "session_cipher", ""):
        return []
    try:
        from crawler_control.services import load_account_session

        payload = load_account_session(account)
    except Exception:  # noqa: BLE001 - a bad session must not kill the crawl
        return []
    cookies = payload.get("cookies") if isinstance(payload, dict) else None
    return cookies if isinstance(cookies, list) else []


def joybuy_cookie_pairs(cookies: list[dict]) -> dict[str, str]:
    """Flatten cookies to ``{name: value}`` for Scrapy's ``Request.cookies``.

    Third-party cookies are dropped: replaying a Facebook cookie to
    joybuy.co.uk would leak a credential to the wrong origin.
    """

    pairs: dict[str, str] = {}
    for cookie in cookies or []:
        if not isinstance(cookie, dict):
            continue
        name = str(cookie.get("name") or "").strip()
        if not name:
            continue
        domain = str(cookie.get("domain") or "").lower()
        if domain and not any(hint in domain for hint in JOYBUY_COOKIE_DOMAIN_HINTS):
            continue
        pairs[name] = str(cookie.get("value") or "")
    return pairs


def load_account_pool(spider) -> list[dict]:
    """Every usable account of the run's group, one record each.

    Returns plain dicts (``public_id``/``label``/``group``/``cookies``) so the
    rotation logic stays framework- and ORM-free and can be unit-tested.
    The pinned account comes first; the rest follow the group's LRU order.
    """

    run = getattr(spider, "run", None)
    if run is None:
        return []
    try:
        from crawler_control.services import (
            load_account_session,
            usable_accounts_for_run,
        )

        accounts = usable_accounts_for_run(run.job)
    except Exception:  # noqa: BLE001 - pool building must not kill the crawl
        return []
    records = []
    for account in accounts:
        try:
            payload = load_account_session(account)
        except Exception as exc:  # noqa: BLE001 - skip it, the pool goes on
            logger.warning(
                "跳过无法解密的账号会话：%s（%s）", account.label, type(exc).__name__
            )
            continue
        pairs = joybuy_cookie_pairs(
            (payload or {}).get("cookies") if isinstance(payload, dict) else []
        )
        if not pairs:
            continue
        records.append(
            {
                "public_id": str(account.public_id),
                "label": account.label,
                "group": account.account_group,
                "cookies": pairs,
            }
        )
    return records
