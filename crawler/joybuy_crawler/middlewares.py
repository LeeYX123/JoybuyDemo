"""Scrapy downloader middlewares.

``HeaderRedactionMiddleware`` keeps credentials out of logs.
``AccountCookieMiddleware`` owns the cookie state of every request and
rotates the crawler account on a randomised budget (2026-11-05): a run no
longer holds one identity end to end, it spreads the work across the
account pool. Scrapy's own cookie jar is disabled for crawl runs because a
shared jar would merge accounts together (see ``runner``).
``RiskControlRenderMiddleware`` is the Scrapy↔DrissionPage hybrid seam
(2026-11-05): every response is checked for Joybuy risk-control / login
walls; blocked pages are re-fetched through a real Chrome (with the
currently active account's cookies) and the rendered HTML replaces the
blocked response. Every response is archived through
``record_raw_response`` here, where the full response is available.
"""

from scrapy.http import HtmlResponse

from joybuy_crawler.core.redaction import redact_headers


def _run_event(spider, code: str, message: str, *, level: str = "INFO") -> None:
    """Write one run event and mirror it to the process log."""

    run = getattr(spider, "run", None)
    if run is not None:
        from crawler_control.services import record_run_event

        try:
            record_run_event(run, level=level, code=code, message=message)
        except Exception:  # noqa: BLE001, S110 - logging must not kill the crawl
            pass
    logger_method = spider.logger.warning if level != "INFO" else spider.logger.info
    logger_method("%s %s", code, message)


class AccountCookieMiddleware:
    """Attach the active account's cookies and rotate accounts periodically.

    Priority 550 keeps it ahead of Scrapy's ``CookiesMiddleware`` (700);
    with ``COOKIES_ENABLED=False`` that jar is out of the picture entirely,
    so an account's cookies can never bleed into another account's request.
    """

    def __init__(self):
        self._pool = None

    # -- pool -----------------------------------------------------------

    @staticmethod
    def _conf(spider):
        crawler = getattr(spider, "crawler", None)
        return getattr(crawler, "settings", None)

    def _pool_for(self, spider):
        if self._pool is not None:
            return self._pool
        from joybuy_crawler.account_rotation import AccountPool
        from joybuy_crawler.account_session import load_account_pool

        conf = self._conf(spider)
        records = load_account_pool(spider)
        rotation_enabled = (
            conf.getbool("CRAWL_ACCOUNT_ROTATION_ENABLED", True) if conf else True
        )
        if not rotation_enabled:
            records = records[:1]
        self._pool = AccountPool(
            records,
            min_seconds=conf.getfloat("CRAWL_ACCOUNT_ROTATE_MIN_SECONDS", 300.0)
            if conf
            else 300.0,
            max_seconds=conf.getfloat("CRAWL_ACCOUNT_ROTATE_MAX_SECONDS", 900.0)
            if conf
            else 900.0,
            min_requests=conf.getint("CRAWL_ACCOUNT_ROTATE_MIN_REQUESTS", 20)
            if conf
            else 20,
            max_requests=conf.getint("CRAWL_ACCOUNT_ROTATE_MAX_REQUESTS", 60)
            if conf
            else 60,
        )
        # The render fallback needs to know which identity is active.
        spider.account_pool = self._pool
        self._announce(spider, conf)
        return self._pool

    def _announce(self, spider, conf) -> None:
        pool = self._pool
        if not len(pool):
            _run_event(
                spider,
                "ACCOUNT_POOL_EMPTY",
                "没有可用账号（账号会话里没有 Cookie），本轮按匿名抓取。",
            )
            return
        if not pool.enabled:
            _run_event(
                spider,
                "ACCOUNT_POOL_READY",
                f"账号池只有 1 个可用账号「{pool.active.label}」，本轮不轮换。",
            )
            return
        low_min = (
            int(conf.getfloat("CRAWL_ACCOUNT_ROTATE_MIN_SECONDS", 300.0) // 60)
            if conf
            else 5
        )
        high_min = (
            int(conf.getfloat("CRAWL_ACCOUNT_ROTATE_MAX_SECONDS", 900.0) // 60)
            if conf
            else 15
        )
        _run_event(
            spider,
            "ACCOUNT_POOL_READY",
            f"账号池就绪：共 {len(pool)} 个账号（{'、'.join(pool.labels()[:6])}），"
            f"每 {low_min}~{high_min} 分钟或若干请求后不定时换号。",
        )

    # -- scrapy hooks ---------------------------------------------------

    def process_request(self, request, spider):
        pool = self._pool_for(spider)
        if not len(pool):
            return
        if pool.should_rotate():
            previous = pool.active
            nxt = pool.rotate()
            if nxt is None:
                if not getattr(spider, "_account_pool_exhausted", False):
                    spider._account_pool_exhausted = True
                    _run_event(
                        spider,
                        "ACCOUNT_POOL_EXHAUSTED",
                        "账号池内所有账号都已触发风控，本轮停止轮换。",
                        level="ERROR",
                    )
            elif previous is not None and previous is not nxt:
                _run_event(
                    spider,
                    "ACCOUNT_ROTATED",
                    f"已从账号「{previous.label}」切换到「{nxt.label}」"
                    f"（本轮第 {pool.rotations} 次换号）。",
                )
        entry = pool.active
        if entry is None or not entry.cookies:
            return
        # Scrapy's CookiesMiddleware owns the Request.cookies -> Cookie header
        # translation and it is DISABLED for crawl runs (a shared jar would
        # merge accounts), so the header is built here. A per-request cookie
        # still wins over the account default.
        cookies = dict(entry.cookies)
        cookies.update(request.cookies or {})
        request.headers["Cookie"] = "; ".join(
            f"{name}={value}" for name, value in cookies.items()
        )
        pool.record_request()


class HeaderRedactionMiddleware:
    def process_request(self, request, spider):
        spider.logger.debug(
            "Request %s %s headers=%s",
            request.method,
            request.url,
            redact_headers(request.headers),
        )

    def process_response(self, request, response, spider):
        spider.logger.debug(
            "Response %s %s status=%s headers=%s",
            request.method,
            request.url,
            response.status,
            redact_headers(response.headers),
        )
        return response

    def process_exception(self, request, exception, spider):
        spider.logger.debug(
            "Request %s failed: %s", request.url, type(exception).__name__
        )


class RiskControlRenderMiddleware:
    """Plain-HTTP first, DrissionPage render fallback, raw archive."""

    def __init__(self):
        from joybuy_crawler.render import BrowserSession, RenderedPage, classify_page

        self._classify = classify_page
        self._RenderedPage = RenderedPage
        # One browser per crawl task (2026-11-05 feedback: a per-page
        # render opened dozens of Chrome instances in a single run).
        self._session = None
        self._session_cookie_key = None
        self._BrowserSession = BrowserSession
        self._cookies_loaded = False
        self._account_cookies = None

    @classmethod
    def from_crawler(cls, crawler):
        from scrapy import signals

        instance = cls()
        crawler.signals.connect(instance.spider_closed, signal=signals.spider_closed)
        return instance

    def spider_closed(self, spider, reason=""):
        self._close_session()

    def _close_session(self):
        session, self._session = self._session, None
        self._session_cookie_key = None
        if session is not None:
            session.close()

    def _session_for(self, cookies: list[dict] | None):
        """Reuse one browser for the whole crawl (reopen if cookies differ)."""

        key = tuple(
            sorted((c.get("name", ""), c.get("value", "")) for c in cookies or [])
        )
        if self._session is not None and key == self._session_cookie_key:
            return self._session
        self._close_session()
        session = self._BrowserSession(headless=True, cookies=cookies or None)
        session.open()
        self._session = session
        self._session_cookie_key = key
        return session

    def _render(self, url, *, cookies=None, headless=True, scroll_for_lazy_load=True):
        try:
            session = self._session_for(cookies)
        except Exception as exc:  # noqa: BLE001 - render fallback must not kill the crawl
            return self._RenderedPage(url=url, html="", status=0, error=str(exc))
        rendered = session.get(
            url, wait_seconds=2, scroll_for_lazy_load=scroll_for_lazy_load
        )
        if rendered.error:
            # A dead session must be recreated on the next fallback.
            self._close_session()
        return rendered

    @staticmethod
    def _event(run, *, level, code, message, url=""):
        if run is None:
            return
        from crawler_control.services import record_run_event

        record_run_event(run, level=level, code=code, message=message, source_url=url)

    def _load_account_cookies(self, spider) -> list[dict]:
        """Cookies of the account that is active right now.

        The pool advances during the crawl, so this cannot be cached for the
        whole run: the browser fallback must render as the same identity the
        HTTP request used.
        """

        pool = getattr(spider, "account_pool", None)
        entry = pool.active if pool is not None else None
        if entry is not None and entry.cookies:
            return [
                {"name": name, "value": value, "domain": "joybuy.co.uk", "path": "/"}
                for name, value in entry.cookies.items()
            ]
        if self._cookies_loaded:
            return self._account_cookies or []
        self._cookies_loaded = True
        from joybuy_crawler.account_session import load_account_cookies

        self._account_cookies = load_account_cookies(spider)
        return self._account_cookies

    @staticmethod
    def _rotate_away_from_blocked_account(spider, *, url=""):
        """Eject the account that just hit a wall and move to the next one."""

        pool = getattr(spider, "account_pool", None)
        entry = pool.active if pool is not None else None
        if entry is None or entry.blocked:
            return
        blocked = pool.mark_blocked(reason="风控页")
        nxt = pool.rotate()
        tail = (
            f"改用账号「{nxt.label}」继续。"
            if nxt is not None
            else "账号池已无可用账号。"
        )
        _run_event(
            spider,
            "ACCOUNT_RISK_ROTATED",
            f"账号「{blocked.label}」命中风控页，已从本轮账号池移除，{tail}",
            level="WARNING",
        )

    def process_response(self, request, response, spider):
        from crawler_control.services import record_raw_response

        run = getattr(spider, "run", None)
        if run is not None:
            try:
                record_raw_response(
                    run,
                    url=request.url,
                    status_code=response.status,
                    payload=response.body,
                    content_type=response.headers.get(b"Content-Type", b"").decode(
                        "latin-1"
                    ),
                )
            except Exception:  # noqa: BLE001, S110 - archiving must never kill a crawl
                pass

        verdict = self._classify(request.url, response.text)
        if not (verdict.risk_control or verdict.login_required):
            return response

        if verdict.risk_control:
            spider.logger.warning("命中风控页，改用真实浏览器重新抓取：%s", request.url)
            # That identity is burned for this run: drop it from the pool and
            # continue with the next account instead of retrying with it.
            self._rotate_away_from_blocked_account(spider, url=request.url)
            self._event(
                run,
                level="INFO",
                code="RISK_CONTROL_FALLBACK",
                message=f"检测到风控页，正在用 DrissionPage 重新抓取：{request.url}",
                url=request.url,
            )
        else:
            self._event(
                run,
                level="INFO",
                code="LOGIN_WALL_FALLBACK",
                message=f"检测到登录墙，正在带账号会话重试：{request.url}",
                url=request.url,
            )

        rendered = self._render(
            request.url,
            cookies=self._load_account_cookies(spider)
            if verdict.login_required
            else None,
            headless=True,
            scroll_for_lazy_load=True,
        )
        if rendered.error or not rendered.html:
            self._event(
                run,
                level="ERROR",
                code="RENDER_FAILED",
                message=f"浏览器渲染失败 {request.url}：{rendered.error or '页面为空'}",
                url=request.url,
            )
            return response
        self._event(
            run,
            level="INFO",
            code="RENDERED_OK",
            message=f"已通过真实浏览器取到页面：{request.url}",
            url=request.url,
        )
        return HtmlResponse(
            url=request.url,
            status=200,
            body=rendered.html.encode("utf-8"),
            encoding="utf-8",
            request=request,
        )
