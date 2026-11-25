"""Crawl run executor: drives one CrawlRun through Scrapy to a terminal state.

Launched by the admin "start" action as a detached subprocess
(``manage.py run_crawl_run --run <public_id>``). Every exit path writes a
terminal run status: normal close -> SUCCEEDED, any fatal error (site
risk-control, missing login account, unexpected crash) -> FAILED with a
``RUN_FAILED`` event, and the wrapper below catches even hard crashes so
a run can never be left stuck in RUNNING.
"""

import logging
import os
from urllib.parse import urlsplit

from scrapy.crawler import CrawlerProcess

REPOSITORY_ROOT_CRAWLER = __file__.rsplit("crawler", 1)[0]

logger = logging.getLogger("joybuy_crawler.runner")

DEFAULT_SITE_HOST = "www.joybuy.co.uk"
DEFAULT_SITE_PORT = 443
DEFAULT_PREFLIGHT_TIMEOUT = 8.0

# Scrapy 2.13 runs callbacks on the asyncio reactor; the executor is a
# dedicated crawl process, so Django's sync-ORM guard is disabled there.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


def _proxy_endpoint(settings: dict) -> tuple[str, int] | None:
    """Host/port of the operator-configured proxy, or None for a direct crawl."""

    for key in ("CRAWL_HTTPS_PROXY", "CRAWL_HTTP_PROXY"):
        raw = str(settings.get(key) or "").strip()
        if not raw:
            continue
        if "://" not in raw:
            raw = f"http://{raw}"
        parts = urlsplit(raw)
        if not parts.hostname:
            continue
        default_port = 443 if parts.scheme == "https" else 80
        return parts.hostname, parts.port or default_port
    return None


def check_connectivity(
    host: str, port: int, *, timeout: float, use_tls: bool = True
) -> tuple[bool, str]:
    """Bounded TCP/TLS connectivity probe (no HTTP request, robots untouched).

    The 2026-11-09 incident: the host accepted the TCP connection and then
    dropped it mid-TLS-handshake, so every listing request failed and the
    run was blamed on risk control. One connect proves reachability cheaply;
    it never fetches a page, so it cannot bypass robots.txt.
    """

    import socket
    import ssl

    sock = None
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        if use_tls:
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
        return True, ""
    except Exception as exc:  # noqa: BLE001 - any failure is the diagnosis
        return False, f"{type(exc).__name__}: {exc}"
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:  # noqa: BLE001, S110 - closing a dead socket
                pass


def _run_settings(run) -> dict:
    """Scrapy settings for one run, derived from the base project settings."""

    from joybuy_crawler import settings as base

    job = run.job
    settings = {key: value for key, value in vars(base).items() if key.isupper()}
    settings.update(
        {
            "ITEM_PIPELINES": {
                # Record rules run before staging: a fatal violation drops
                # the item so junk never reaches the dataset or the DB.
                "joybuy_crawler.pipelines.RecordRulePipeline": 150,
                "joybuy_crawler.pipelines.StagingPipeline": 200,
            },
            "DOWNLOADER_MIDDLEWARES": {
                # 550: attach the account session before Scrapy's cookie jar
                # (700) turns it into a Cookie header, so every request is
                # authenticated from the first byte.
                "joybuy_crawler.middlewares.AccountCookieMiddleware": 550,
                "joybuy_crawler.middlewares.HeaderRedactionMiddleware": 560,
                "joybuy_crawler.middlewares.RiskControlRenderMiddleware": 570,
                # 580: set request.meta["proxy"] from CRAWL_HTTP(S)_PROXY
                # before Scrapy's HttpProxyMiddleware (750) reads it.
                "joybuy_crawler.middlewares.ProxyConfigMiddleware": 580,
            },
            # 翻页开关（2026-11-12，运营者拍板默认开）：Joybuy robots.txt 禁止
            # /s?*&page=，开启翻页等同于运营者授权偏离这一条规则，此时关闭
            # ROBOTSTXT_OBEY（/s?k= 与 /dp/ 本就 Allow，行为上只放开 page= 请求）。
            # 关闭翻页的任务保持完全遵守 robots.txt。
            "ROBOTSTXT_OBEY": not bool(getattr(job, "allow_pagination", True)),
            "JOYBUY_MAX_LISTING_PAGES": int(os.getenv("CRAWL_MAX_LISTING_PAGES", "25")),
            # AccountCookieMiddleware owns cookies so accounts can rotate
            # without a shared jar merging their sessions together.
            "COOKIES_ENABLED": False,
            # Scrapy 2.13.4's ProtegoRobotParser swaps (url, user_agent)
            # and forbids random URLs; see joybuy_crawler/robots.py.
            "ROBOTSTXT_PARSER": "joybuy_crawler.robots.FixedProtegoRobotParser",
            "CONCURRENT_REQUESTS": job.concurrency or 1,
            "CONCURRENT_REQUESTS_PER_DOMAIN": job.concurrency or 1,
            "DOWNLOAD_DELAY": (
                round(60.0 / job.rate_limit_per_minute, 2)
                if job.rate_limit_per_minute
                else base.DOWNLOAD_DELAY
            ),
            "JOYBUY_RUN_PUBLIC_ID": str(run.public_id),
            "LOG_LEVEL": "INFO",
        }
    )
    # 2026-11-25：页面采集任务（活动页/店铺页）只取商品卡需要的字段，跳过
    # 「图文详情（/dg/）+ 变体价格链」两段附加抓取——否则每个商品会放大到
    # 10+ 次请求，一次 360 商品的批次要跑数小时。品类任务的设置保持不变。
    if getattr(job, "job_kind", "CATEGORY") == "PAGE_SET":
        settings["JOYBUY_MOBILE_DETAIL_ENABLED"] = False
        settings["JOYBUY_VARIANT_PRICES_ENABLED"] = False
        # 页面采集是一次性命中一批商品（360 件量级），单并发 + 2s 延迟要跑数小时；
        # 站点是静态详情页，4 并发 / 0.5s 延迟仍在既有礼貌抓取范围内。
        settings["CONCURRENT_REQUESTS"] = 6
        settings["CONCURRENT_REQUESTS_PER_DOMAIN"] = 3
        settings["DOWNLOAD_DELAY"] = 0.3
        # AUTOTHROTTLE_TARGET_CONCURRENCY 默认 1.0，会把上面的并发压回单并发
        # （实测 1.7 件/分钟）；页面采集是一次性批次，这里显式关掉自适应节流。
        settings["AUTOTHROTTLE_ENABLED"] = False
    return settings


def execute_run(run_public_id: str) -> None:
    """Run one crawl to completion; always leaves a terminal run status."""

    from crawler_control.models import CrawlRun
    from crawler_control.services import complete_run_failed, record_run_event

    run = CrawlRun.objects.select_related("job").get(public_id=run_public_id)
    if run.status != CrawlRun.Status.RUNNING:
        logger.info("任务运行 %s 当前状态为 %s，无需执行。", run_public_id, run.status)
        return

    record_run_event(
        run,
        level="INFO",
        code="RUN_STARTED",
        message=f"执行器已启动，任务「{run.job.name}」共 "
        f"{len(run.params_snapshot.get('source_categories') or [])} 个类目选择。",
    )

    from joybuy_crawler.spiders.joybuy_run import JoybuyRunSpider
    from joybuy_crawler.spiders.pages_run import PageRunSpider

    settings = _run_settings(run)
    if settings.get("CRAWL_PREFLIGHT_ENABLED", True):
        proxy = _proxy_endpoint(settings)
        timeout = float(
            settings.get("CRAWL_PREFLIGHT_TIMEOUT") or DEFAULT_PREFLIGHT_TIMEOUT
        )
        if proxy is None:
            target = f"{DEFAULT_SITE_HOST}:{DEFAULT_SITE_PORT}"
            reachable, detail = check_connectivity(
                DEFAULT_SITE_HOST, DEFAULT_SITE_PORT, timeout=timeout
            )
        else:
            host, port = proxy
            target = f"代理 {host}:{port}"
            reachable, detail = check_connectivity(
                host, port, timeout=timeout, use_tls=False
            )
        if not reachable:
            reason = (
                f"网络不可达：无法连接{target}（{detail[:300]}）。本轮未启动抓取；"
                "请检查网络、VPN 或代理（可用 CRAWL_HTTP_PROXY / CRAWL_HTTPS_PROXY "
                "显式指定代理），这不是风控或站点结构改版。"
            )
            record_run_event(
                run,
                level="ERROR",
                code="CONNECTIVITY_PREFLIGHT_FAILED",
                message=reason,
                source_url="https://www.joybuy.co.uk/",
            )
            complete_run_failed(run, reason=reason)
            return

    # 2026-11-25：页面采集任务（活动页/店铺页）走独立 spider；品类任务不变。
    spider_cls = (
        PageRunSpider
        if getattr(run.job, "job_kind", "CATEGORY") == "PAGE_SET"
        else JoybuyRunSpider
    )
    process = CrawlerProcess(settings, install_root_handler=False)
    process.crawl(spider_cls, run_public_id=run_public_id)
    try:
        process.start()
    except Exception as exc:
        run.refresh_from_db()
        if run.status == CrawlRun.Status.RUNNING:
            complete_run_failed(run, reason=f"执行器崩溃：{exc}")
        raise
