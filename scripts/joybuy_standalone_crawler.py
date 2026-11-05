"""Joybuy 独立爬取脚本（浏览器常驻 profile 版）。

为什么单独写这个脚本（2026-11-05）
----------------------------------
后台任务（Scrapy + DrissionPage 回退）在 joybuy.co.uk 上失败：站点对
**headless / 注入 Cookie 的浏览器**返回 ``403 页面``（`/error403`），
列表页拿不到任何 ``/dp/`` 商品卡。现场对比（16:10）证明：

    headed + 常驻已登录 profile → 真实页面，2649944 字节，40 个 /dp/ 卡
    headless + 注入 Cookie       → 403 页面，0 个商品卡

所以这里改用与 ``crawler_friend_list_Korea1111.py`` 相同的思路：
真实浏览器 + **常驻 user_data_path**（登录态留在 profile 里，不搬 Cookie）
+ ``page.listen`` 抓 SSR 文档流，再按项目既有的解析/落盘/入库链路处理。

存储方式不变
------------
- 本地数据集：``var/crawl_exports/{run.public_id[:8]}-{job slug}/``
  ``{一级类目}/{二级类目}/{productId}/product.json`` + ``images/main|detail``
  + ``dataset_index.jsonl``（复用 ``joybuy_crawler.dataset.save_product``）。
- 数据库：``ingest_product_payload`` → ``StagingProduct`` →
  ``import_staging_product``（SPU/Offer/Media/搜索文档，与正式任务同一条链）。
- 运行记录：写入 ``CrawlRun`` 的计数与 ``CrawlRunEvent``，管理端能看到进度。

用法
----
    # 用管理端已建好的任务（失败任务也可以直接复用）
    python scripts/joybuy_standalone_crawler.py --job 27000fba-c015-4401-a715-805436e2fedc

    # 覆盖商品数上限、放慢节奏、指定 profile / 端口
    python scripts/joybuy_standalone_crawler.py --job <public_id> --limit 20 \
        --profile var/browser_profiles/account-9b189970 --port 9335 --pause 5

前提：``--profile`` 指向的浏览器 profile 必须**已登录 joybuy.co.uk**
（在管理端「爬虫账号 → 登录」弹出的窗口里登录一次即可，profile 会保留）。
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "crawler"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from crawler_control.models import CrawlJob, CrawlRun
from crawler_control.services import (
    complete_run,
    complete_run_failed,
    record_run_event,
    start_run,
    update_run_progress,
)

UK_BASE_URL = "https://www.joybuy.co.uk"
DEFAULT_PROFILE = REPO / "var" / "browser_profiles" / "account-9b189970"
LOG_DIR = REPO / "var" / "logs"

logger = logging.getLogger("joybuy_standalone")


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


class Config:
    """运行时配置（对应参考脚本里的 ConfigItem）。"""

    # 常驻浏览器 profile：登录态留在这里，不要每次重建
    PROFILE = str(DEFAULT_PROFILE)
    # 独立调试端口，避开后台任务用的 9333 / 登录窗口的 9334
    PORT = 9335
    # 页面之间的礼貌间隔（秒）
    PAUSE = 4.0
    # 单个页面最多渲染几次
    RENDER_RETRIES = 2
    # SSR 文档流等待上限（秒）
    LISTEN_TIMEOUT = 40
    # 低于这个长度视为「还没加载完」，继续等 DOM
    MIN_HTML = 200_000
    # DOM 最长等待（秒）
    DOM_TIMEOUT = 12
    # 页面语言：en_GB 让面包屑保持英文，落盘目录沿用既有英文 slug 约定
    LANG = "en_GB"
    # 列表页最多取前 N 个商品卡（None = 用任务上限）
    LIMIT = None
    # 是否显示浏览器窗口（站点对 headless 返回 403，默认必须有窗口）
    HEADLESS = False


def setup_logging() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / f"standalone_crawler_{datetime.now():%Y-%m-%d}.log"
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s")
    )
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter("%(asctime)s | %(message)s", "%H:%M:%S"))
    logger.addHandler(console)
    return path


# ---------------------------------------------------------------------------
# 浏览器
# ---------------------------------------------------------------------------


def build_page(profile: str, port: int):
    """启动（或接上）常驻 profile 的真实 Chrome。

    与参考脚本一致：``ChromiumOptions().set_paths(local_port, user_data_path)``。
    profile 目录复用 = 登录态复用，不需要搬 Cookie。
    """

    from DrissionPage import ChromiumOptions, ChromiumPage

    profile_path = Path(profile)
    if not profile_path.is_absolute():
        profile_path = REPO / profile_path
    profile_path.mkdir(parents=True, exist_ok=True)

    options = ChromiumOptions()
    options.set_paths(local_port=port, user_data_path=str(profile_path))
    options.set_argument("--disable-blink-features=AutomationControlled")
    options.set_argument("--window-size=1440,900")
    options.set_argument("--no-first-run")
    options.set_timeouts(page_load=60, script=30)
    if Config.HEADLESS:
        options.headless()
    page = ChromiumPage(options)
    try:
        page.set.window.max()
    except Exception:  # noqa: BLE001, S110 - 窗口最大化只是体验优化
        pass
    return page


def listen_target(url: str) -> str:
    """``page.listen`` 的关键字必须是 ASCII。

    详情页 URL 里带中文 slug，直接用整段 URL 会匹配不到（2026-11-05
    现场：详情页监听 40s 超时，``packet`` 为 False）。改用商品 ID 作为
    关键字，列表页仍用去掉查询串的路径。
    """

    from urllib.parse import urlparse

    parsed = urlparse(url)
    if "/dp/" in parsed.path:
        match = re.search(r"/(\d{5,})(?:/)?$", parsed.path)
        return match.group(1) if match else "/dp/"
    return f"{parsed.netloc}{parsed.path}"


def wait_for_dom(
    page, *, min_len: int | None = None, timeout: float | None = None
) -> str:
    """轮询到页面 DOM 基本完整（长度达标或有 ``<h1>``）再返回。

    2026-11-05 现场：详情页刚 ``get`` 完时 DOM 只有骨架，1.5s 后仍可能
    不足，解析会得到空标题/空价格，被质量闸门拒收。这里改成轮询，
    拿到足够大的文档再解析。
    """

    min_len = min_len or Config.MIN_HTML
    deadline = time.monotonic() + (timeout or Config.DOM_TIMEOUT)
    html = page.html or ""
    while time.monotonic() < deadline:
        html = page.html or ""
        if len(html) >= min_len and ("<h1" in html or "/dp/" in html):
            return html
        time.sleep(0.5)
    return html


def fetch_ssr(page, url: str) -> tuple[str, str, bool, bool]:
    """抓一次文档流里的 SSR HTML（服务端渲染内容，含水合前的链接）。

    返回 ``(html, final_url, risk_control, login_required)``。
    站点风控/登录页必须能被识别出来，绝不当作商品页解析。
    """

    from joybuy_crawler.render import classify_page

    last_error = ""
    target = listen_target(url)
    for attempt in range(1, Config.RENDER_RETRIES + 1):
        try:
            page.listen.start(target)
            page.get(url)
            packet = page.listen.wait(timeout=Config.LISTEN_TIMEOUT)
            body = None
            if packet and getattr(packet, "response", None) is not None:
                body = packet.response.body
            if isinstance(body, bytes):
                try:
                    body = body.decode("utf-8")
                except UnicodeDecodeError:
                    body = body.decode("latin-1", errors="replace")
            html = str(body or "")
            if len(html) < Config.MIN_HTML:
                # 监听可能抓到的是 XHR 小包（比整页文档小得多），
                # 或者页面还在渲染；等 DOM 长到完整大小再解析。
                html = wait_for_dom(page)
            verdict = classify_page(page.url, html)
            return html, page.url, verdict.risk_control, verdict.login_required
        except Exception as exc:  # noqa: BLE001 - 单页失败可重试
            last_error = str(exc)
            logger.warning(
                "渲染第 %d/%d 次失败：%s", attempt, Config.RENDER_RETRIES, exc
            )
            time.sleep(Config.PAUSE)
        finally:
            try:
                page.listen.stop()
            except Exception:  # noqa: BLE001, S110 - 监听器可能没启动
                pass
    logger.error("页面渲染全部失败：%s", last_error)
    return "", page.url, False, False


# ---------------------------------------------------------------------------
# 任务与类目
# ---------------------------------------------------------------------------


def resolve_targets(job: CrawlJob, limit: int | None) -> list[dict]:
    """把任务的冻结类目选择展开成列表页目标（与 spider 口径一致）。"""

    from catalog.models import SourceCategorySnapshot

    version = job.source_tree_version
    targets = []
    selections = list(
        job.source_selections.select_related("source_category").order_by(
            "sort_order", "pk"
        )
    )
    for selection in selections:
        category = selection.source_category
        snapshot = (
            SourceCategorySnapshot.objects.filter(
                tree_version=version, category=category
            ).first()
            if version
            else None
        )
        targets.append(
            {
                "category_name": snapshot.name if snapshot else category.source_id,
                "category_name_zh": snapshot.name_zh if snapshot else "",
                "selection": category.source_id,
                "source_url": (snapshot.source_url if snapshot else "")
                or f"{UK_BASE_URL}/s?k={category.source_id}",
                "limit": limit or job.product_limit,
                "collected": 0,
            }
        )
    return targets


def robots_safe_listing_url(url: str) -> str:
    """把 ``/s?...l2=...`` 收敛成 robots.txt 允许的 ``/s?k=<关键词>``。"""

    from urllib.parse import parse_qs, quote, urlparse

    parsed = urlparse(url)
    if "/s" not in parsed.path:
        return url
    keyword = (parse_qs(parsed.query).get("k") or [""])[0]
    return f"{UK_BASE_URL}/s?k={quote(keyword)}" if keyword else url


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


class StandaloneCrawler:
    def __init__(self, job_public_id: str, *, limit: int | None = None):
        self.job = CrawlJob.objects.select_related("source_catalog").get(
            public_id=job_public_id
        )
        self.crawl_run = self._current_or_new_run()
        self.targets = resolve_targets(self.job, limit)
        self.seen: set[str] = set()
        self.page = None

    def _current_or_new_run(self) -> CrawlRun:
        running = self.run_candidate()
        if running is not None:
            logger.info("复用进行中的运行 %s", running.public_id)
            return running
        run = start_run(self.job)
        record_run_event(
            run,
            level="INFO",
            code="STANDALONE_STARTED",
            message="Standalone browser crawler started (headed Chromium + persistent profile).",
        )
        logger.info("已创建运行 %s（任务 %s）", run.public_id, self.job.name)
        return run

    def run_candidate(self) -> CrawlRun | None:
        return (
            CrawlRun.objects.filter(job=self.job, status=CrawlRun.Status.RUNNING)
            .order_by("-created_at")
            .first()
        )

    # -- 落盘 + 入库（与正式管线同一条链） --------------------------------

    def persist(self, product, target: dict, source_url: str) -> bool:
        from joybuy_crawler.dataset import dataset_root, save_product

        payload = product.to_payload()
        source_id = str(payload.get("source_id") or "")
        from joybuy_crawler.dataset import _slugify

        breadcrumb_names = [target["category_name"]]
        for crumb in product.breadcrumbs:
            name = crumb.get("name", "")
            if not name or name.lower() == "home" or name in breadcrumb_names:
                continue
            # 中文面包屑 slug 化后为空，会写出 uncategorized 目录；跳过，
            # 目录结构与既有导出（英文 slug）保持一致。
            if _slugify(name) == "uncategorized":
                continue
            breadcrumb_names.append(name)

        try:
            root = dataset_root(str(self.crawl_run.public_id), self.job.name)
            index_line = save_product(
                root, breadcrumb_names=breadcrumb_names, payload=payload
            )
            logger.info(
                "落盘 %s -> %s（图片 main=%d detail=%d）",
                source_id,
                index_line["product_json"],
                len(index_line["images"].get("main") or []),
                len(index_line["images"].get("detail") or []),
            )
        except Exception as exc:  # noqa: BLE001 - 落盘失败不阻断入库
            record_run_event(
                self.crawl_run,
                level="WARNING",
                code="DATASET_WRITE_FAILED",
                message=f"Dataset write failed for {source_id}: {exc}",
                source_url=source_url,
            )

        from crawler_control.import_services import (
            StagingImportRejected,
            import_staging_product,
        )
        from joybuy_crawler.ingest import ingest_product_payload
        from offers.models import Currency, Market

        update_run_progress(self.crawl_run, downloaded=1)
        try:
            staging = ingest_product_payload(
                self.crawl_run,
                payload,
                source_system=self.job.source_catalog.source_system,
                source_url=source_url,
                parser_version="joybuy_uk.standalone",
                structure_version=2,
            )
        except Exception as exc:  # noqa: BLE001
            update_run_progress(self.crawl_run, failed=1)
            record_run_event(
                self.crawl_run,
                level="ERROR",
                code="STAGING_FAILED",
                message=f"Staging failed for {source_id}: {exc}",
                source_url=source_url,
            )
            logger.error("staging 失败 %s：%s", source_id, exc)
            return False

        market = Market.objects.filter(code="GB", is_active=True).first()
        currency = Currency.objects.filter(
            code=payload.get("currency") or "GBP"
        ).first()
        try:
            outcome = import_staging_product(
                staging,
                market=market,
                currency=currency or market.default_currency,
                locale=self.job.locale,
            )
        except StagingImportRejected as exc:
            update_run_progress(self.crawl_run, failed=1)
            record_run_event(
                self.crawl_run,
                level="ERROR",
                code="IMPORT_REJECTED",
                message=str(exc),
                source_url=source_url,
            )
            logger.error("入库被质量闸门拒绝 %s：%s", source_id, exc)
            return False
        except Exception as exc:  # noqa: BLE001
            update_run_progress(self.crawl_run, failed=1)
            record_run_event(
                self.crawl_run,
                level="ERROR",
                code="IMPORT_FAILED",
                message=f"Import failed for {source_id}: {exc}",
                source_url=source_url,
            )
            logger.error("入库失败 %s：%s", source_id, exc)
            return False

        update_run_progress(self.crawl_run, succeeded=1)
        record_run_event(
            self.crawl_run,
            level="INFO",
            code="PRODUCT_IMPORTED",
            message=f"Imported {source_id} -> SPU {outcome.spu.public_id}",
            source_url=source_url,
        )
        logger.info("入库成功 %s -> SPU %s", source_id, outcome.spu.public_id)
        return True

    # -- 爬取 --------------------------------------------------------------

    def crawl_listing(self, target: dict) -> list[str]:
        from joybuy_crawler.parsers.joybuy_uk import (
            UK_PRODUCT_URL_PATTERN,
            parse_uk_listing,
        )

        url = robots_safe_listing_url(target["source_url"])
        html, final_url, risk, login = fetch_ssr(self.page, url)
        if risk:
            raise RuntimeError(
                f"列表页被风控拦截（{url} -> {final_url}）：请确认 profile 已登录且用有头浏览器运行"
            )
        if login:
            raise RuntimeError(
                f"列表页要求登录（{final_url}）：profile 登录态已失效，请重新登录"
            )
        entries = parse_uk_listing(html)

        product_urls: list[str] = []
        for entry in entries:
            if len(product_urls) >= target["limit"]:
                break
            match = UK_PRODUCT_URL_PATTERN.search(entry.source_url)
            if not match or match.group(1) in self.seen:
                continue
            self.seen.add(match.group(1))
            product_urls.append(entry.source_url)

        update_run_progress(self.crawl_run, discovered=len(product_urls))
        record_run_event(
            self.crawl_run,
            level="INFO",
            code="LISTING_PARSED",
            message=f"Listing {url} yielded {len(product_urls)} product link(s).",
            source_url=url,
        )
        logger.info(
            "列表页解析完成：%d 个商品（目标上限 %d）",
            len(product_urls),
            target["limit"],
        )
        return product_urls

    def crawl_product(self, product_url: str, target: dict) -> bool:
        from joybuy_crawler.parsers.joybuy_uk import parse_uk_product_detail

        html, final_url, risk, login = fetch_ssr(self.page, product_url)
        if risk or login:
            record_run_event(
                self.crawl_run,
                level="ERROR",
                code="DETAIL_BLOCKED",
                message=f"Detail page blocked (risk={risk}, login={login}): {final_url}",
                source_url=product_url,
            )
            update_run_progress(self.crawl_run, failed=1)
            return False
        try:
            product = parse_uk_product_detail(html, source_url=final_url or product_url)
        except Exception as exc:  # noqa: BLE001 - 单个商品解析失败不影响整体
            record_run_event(
                self.crawl_run,
                level="ERROR",
                code="DETAIL_PARSE_FAILED",
                message=f"Detail {product_url} failed to parse: {exc}",
                source_url=product_url,
            )
            update_run_progress(self.crawl_run, failed=1)
            logger.error("详情解析失败 %s：%s", product_url, exc)
            return False
        return self.persist(product, target, final_url or product_url)

    def run(self) -> int:
        logger.info("=" * 68)
        logger.info("任务：%s（%s）", self.job.name, self.job.public_id)
        logger.info(
            "运行：%s | profile：%s | 端口：%d",
            self.crawl_run.public_id,
            Config.PROFILE,
            Config.PORT,
        )
        logger.info(
            "类目：%s",
            ", ".join(f"{t['category_name']}[{t['selection']}]" for t in self.targets),
        )
        logger.info("=" * 68)

        succeeded = failed = 0
        try:
            self.page = build_page(Config.PROFILE, Config.PORT)
            for index, target in enumerate(self.targets, start=1):
                logger.info(
                    "---- 类目 %d/%d：%s（上限 %d）",
                    index,
                    len(self.targets),
                    target["category_name"],
                    target["limit"],
                )
                try:
                    product_urls = self.crawl_listing(target)
                except Exception as exc:  # noqa: BLE001 - 类目级失败记事件后继续
                    record_run_event(
                        self.crawl_run,
                        level="ERROR",
                        code="LISTING_FAILED",
                        message=str(exc),
                        source_url=target["source_url"],
                    )
                    logger.error("类目抓取失败：%s", exc)
                    continue
                for position, product_url in enumerate(product_urls, start=1):
                    logger.info("[%d/%d] %s", position, len(product_urls), product_url)
                    try:
                        ok = self.crawl_product(product_url, target)
                    except Exception:
                        logger.exception("商品处理异常")
                        update_run_progress(self.crawl_run, failed=1)
                        ok = False
                    succeeded += int(ok)
                    failed += int(not ok)
                    time.sleep(Config.PAUSE)
        except Exception as exc:
            logger.exception("爬取中断")
            complete_run_failed(
                self.crawl_run, reason=f"Standalone crawler crashed: {exc}"
            )
            return 1
        finally:
            if self.page is not None:
                try:
                    self.page.quit()
                except Exception:  # noqa: BLE001, S110
                    pass

        self.crawl_run.refresh_from_db()
        if succeeded == 0:
            complete_run_failed(
                self.crawl_run,
                reason=(
                    "Standalone crawler imported 0 products "
                    f"({failed} failure(s)); check the profile login and the listing URL."
                ),
            )
            logger.error("结束：0 成功 / %d 失败", failed)
            return 1
        complete_run(self.crawl_run, outcome=CrawlRun.Status.SUCCEEDED)
        self.crawl_run.refresh_from_db()
        logger.info(
            "结束：成功 %d / 失败 %d；运行状态 %s",
            succeeded,
            failed,
            self.crawl_run.status,
        )
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Joybuy standalone browser crawler")
    parser.add_argument(
        "--job", required=True, help="CrawlJob public_id（失败任务也可直接复用）"
    )
    parser.add_argument("--limit", type=int, default=None, help="覆盖商品数上限")
    parser.add_argument(
        "--profile", default=str(DEFAULT_PROFILE), help="常驻浏览器 profile 目录"
    )
    parser.add_argument(
        "--port", type=int, default=Config.PORT, help="调试端口（避开 9333/9334）"
    )
    parser.add_argument(
        "--pause", type=float, default=Config.PAUSE, help="页面间隔秒数"
    )
    parser.add_argument(
        "--headless", action="store_true", help="无头模式（站点会 403，仅供排查）"
    )
    parser.add_argument(
        "--lang",
        default=Config.LANG,
        help="页面语言 Cookie（默认 en_GB，落盘目录沿用英文 slug）",
    )
    options = parser.parse_args()

    Config.PROFILE = options.profile
    Config.PORT = options.port
    Config.PAUSE = options.pause
    Config.HEADLESS = options.headless
    Config.LIMIT = options.limit
    Config.LANG = options.lang

    log_path = setup_logging()
    logger.info("日志文件：%s", log_path)
    return StandaloneCrawler(options.job, limit=options.limit).run()


if __name__ == "__main__":
    raise SystemExit(main())
