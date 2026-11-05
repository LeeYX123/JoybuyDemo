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

from scrapy.crawler import CrawlerProcess

REPOSITORY_ROOT_CRAWLER = __file__.rsplit("crawler", 1)[0]

logger = logging.getLogger("joybuy_crawler.runner")

# Scrapy 2.13 runs callbacks on the asyncio reactor; the executor is a
# dedicated crawl process, so Django's sync-ORM guard is disabled there.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


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
            },
            "ROBOTSTXT_OBEY": True,
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

    process = CrawlerProcess(_run_settings(run), install_root_handler=False)
    process.crawl(JoybuyRunSpider, run_public_id=run_public_id)
    try:
        process.start()
    except Exception as exc:
        run.refresh_from_db()
        if run.status == CrawlRun.Status.RUNNING:
            complete_run_failed(run, reason=f"执行器崩溃：{exc}")
        raise
