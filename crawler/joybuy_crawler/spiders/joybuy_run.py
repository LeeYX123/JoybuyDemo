"""Per-run Joybuy category spider (2026-11-05 rebuild).

One spider instance crawls one ``CrawlRun``: it expands the job's frozen
multi-category selection, fetches listing pages (Scrapy HTTP first; the
downloader middleware swaps in DrissionPage renders when the site serves
a risk-control/login wall), parses product cards and then each product
detail page into the structure-version-2 payload.

The heavy lifting per product (dataset files, staging ingest, import,
progress counters, events) happens in ``pipelines.StagingPipeline``; the
run is completed by ``runner.execute_run`` after the crawl closes.
"""

import logging

import scrapy
from crawler_control.models import CrawlRun

from joybuy_crawler.parsers.joybuy_uk import (
    UK_PRODUCT_URL_PATTERN,
    parse_uk_listing,
    parse_uk_product_detail,
)

logger = logging.getLogger("joybuy_crawler.spider")

UK_BASE_URL = "https://www.joybuy.co.uk"


class JoybuyRunSpider(scrapy.Spider):
    name = "joybuy_run"

    def __init__(self, run_public_id: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.crawl_run_public_id = run_public_id
        self.run = CrawlRun.objects.select_related("job", "job__source_catalog").get(
            public_id=run_public_id
        )
        self.job = self.run.job
        snapshot = self.run.params_snapshot or {}

        self.product_limit = int(
            snapshot.get("product_limit") or self.job.product_limit
        )
        self.targets = self._build_targets(snapshot)
        self.seen_product_ids: set[str] = set()
        self.fatal_error: str = ""

    # -- planning -----------------------------------------------------------

    def _build_targets(self, snapshot: dict) -> list[dict]:
        """One listing target per frozen category selection.

        The listing URL comes from the synced tree snapshot (the real menu
        URL captured from the live site); pagination appends ``&page=N`` —
        verified against the live site during tree sync.
        """

        from catalog.models import SourceCategorySnapshot

        targets = []
        version = self.job.source_tree_version
        selections = list(
            self.job.source_selections.select_related("source_category").order_by(
                "sort_order", "pk"
            )
        )
        if not selections:
            # Legacy single-category job.
            selections = [self.job]
        for selection in selections:
            if hasattr(selection, "source_category"):
                category = selection.source_category
                include_descendants = selection.include_descendants
            else:  # legacy path uses the job columns
                category = self.job.source_category
                include_descendants = self.job.category_mode == "INCLUDE_SUBCATEGORIES"
            snapshot_row = (
                SourceCategorySnapshot.objects.filter(
                    tree_version=version, category=category
                ).first()
                if version
                else None
            )
            targets.append(
                {
                    "category_name": snapshot_row.name
                    if snapshot_row
                    else category.source_id,
                    "source_url": (snapshot_row.source_url if snapshot_row else "")
                    or f"{UK_BASE_URL}/s?k={category.source_id}",
                    "include_descendants": include_descendants,
                    "limit": self.product_limit,
                    "collected": 0,
                }
            )
        return targets

    # -- crawling -----------------------------------------------------------

    @staticmethod
    def _robots_safe_listing_url(url: str) -> str:
        """Normalize a listing URL to the robots.txt-allowed form.

        joybuy.co.uk robots.txt (fetched 2026-11-05) forbids ``/s?``
        URLs carrying ``l1/l2/l3/page/sortType/...`` params but allows
        plain ``/s?k=<name>`` and ``/dp/<slug>/<id>`` pages. The snapshot
        keeps the original verbatim URL; the crawl target strips it down
        to the allowed ``k`` search term.
        """

        from urllib.parse import parse_qs, quote, urlparse

        parsed = urlparse(url)
        if "/s" not in parsed.path:
            return url  # channel pages (/minihome/...) are allowed as-is
        query = parse_qs(parsed.query)
        keyword = (query.get("k") or [""])[0]
        if not keyword:
            return url
        return f"{UK_BASE_URL}/s?k={quote(keyword)}"

    def start_requests(self):
        for index, target in enumerate(self.targets):
            crawl_url = self._robots_safe_listing_url(target["source_url"])
            self.logger.info(
                "列表页目标 %d/%d：%s（%s）",
                index + 1,
                len(self.targets),
                target["category_name"],
                crawl_url,
            )
            yield scrapy.Request(
                crawl_url,
                callback=self.parse_listing,
                meta={"target": target},
                dont_filter=True,
            )

    def parse_listing(self, response):
        target = response.meta["target"]
        try:
            entries = parse_uk_listing(response.text)
        except RuntimeError as exc:
            from crawler_control.services import record_run_event

            record_run_event(
                self.run,
                level="WARNING",
                code="LISTING_PARSE_FAILED",
                message=f"列表页解析失败 {response.url}：{exc}",
                source_url=response.url,
            )
            return
        from crawler_control.services import record_run_event

        from joybuy_crawler.quality import check_listing_entry

        # Advert/recommendation tiles link to /dp/ exactly like products do
        # (2026-11-05: such a tile silently consumed a product slot). They
        # are rejected here, before they count against the category limit.
        accepted_entries = []
        rejected_cards = []
        for entry in entries:
            verdict = check_listing_entry(
                title=entry.title, source_url=entry.source_url
            )
            if verdict.fatal:
                rejected_cards.append(verdict.summary())
                continue
            accepted_entries.append(entry)
        if rejected_cards:
            record_run_event(
                self.run,
                level="WARNING",
                code="LISTING_CARDS_REJECTED",
                message=f"从 {response.url} 丢弃 {len(rejected_cards)} 个非商品卡片："
                f"{'; '.join(rejected_cards[:5])}",
                source_url=response.url,
            )

        fresh = 0
        duplicates = 0
        over_limit = 0
        for entry in accepted_entries:
            if target["collected"] >= target["limit"]:
                over_limit += 1
                continue
            match = UK_PRODUCT_URL_PATTERN.search(entry.source_url)
            if not match:
                continue
            if match.group(1) in self.seen_product_ids:
                duplicates += 1
                continue
            self.seen_product_ids.add(match.group(1))
            target["collected"] += 1
            fresh += 1
            yield scrapy.Request(
                entry.source_url,
                callback=self.parse_detail,
                meta={"target": target, "rank": entry.rank},
            )

        latency = response.meta.get("download_latency")
        record_run_event(
            self.run,
            level="INFO",
            code="LISTING_FETCHED",
            message=(
                f"列表页已获取 {response.url}（HTTP {response.status}，"
                f"{len(response.body) / 1024:.1f} KB"
                + (
                    f"，耗时 {latency:.1f}s"
                    if isinstance(latency, (int, float))
                    else ""
                )
                + f"）；解析出 {len(entries)} 张卡片，"
                f"本轮入队 {fresh} 个商品，重复跳过 {duplicates} 个"
                + (f"，超出上限 {over_limit} 个" if over_limit else "")
                + (f"，非商品卡片 {len(rejected_cards)} 个" if rejected_cards else "")
                + f"；累计已入队 {target['collected']}/{target['limit']}。"
            ),
            source_url=response.url,
        )
        if fresh:
            from crawler_control.services import update_run_progress

            update_run_progress(self.run, discovered=fresh)
        if target["collected"] < target["limit"]:
            # robots.txt forbids /s?*&page= — pagination is not crawlable;
            # the shortfall is visible in the run counters instead.
            record_run_event(
                self.run,
                level="INFO",
                code="LISTING_SHORTFALL",
                message=f"类目「{target['category_name']}」首屏只拿到 "
                f"{target['collected']}/{target['limit']} 个商品"
                "（robots.txt 不允许翻页，无法继续补齐）。",
                source_url=response.url,
            )

    def parse_detail(self, response):
        # Imported at function scope: the event helpers are used on every path,
        # and a conditional import below would make this a local name that is
        # unbound on the success path.
        from crawler_control.services import record_run_event

        try:
            product = parse_uk_product_detail(response.text, source_url=response.url)
        except Exception as exc:  # noqa: BLE001 - one bad page must not kill the run
            record_run_event(
                self.run,
                level="ERROR",
                code="DETAIL_PARSE_FAILED",
                message=f"商品详情页解析失败 {response.url}：{exc}",
                source_url=response.url,
            )
            return
        if product.missing_fields:
            record_run_event(
                self.run,
                level="WARNING",
                code="DETAIL_FIELDS_MISSING",
                message=f"商品 {product.source_id} 缺少字段：{', '.join(product.missing_fields)}",
                source_url=response.url,
            )
        target = response.meta["target"]
        latency = response.meta.get("download_latency")
        crumbs_text = " / ".join(
            crumb.get("name", "") for crumb in product.breadcrumbs if crumb.get("name")
        )
        rating_text = (
            f"评分 {product.rating_average}（{product.rating_count} 条）"
            if product.rating_average
            else "暂无评分"
        )
        record_run_event(
            self.run,
            level="INFO",
            code="PRODUCT_PARSED",
            message=(
                f"详情页已解析 {response.url}（HTTP {response.status}，"
                f"{len(response.body) / 1024:.1f} KB"
                + (
                    f"，耗时 {latency:.1f}s"
                    if isinstance(latency, (int, float))
                    else ""
                )
                + f"）；商品 {product.source_id}「{product.title[:48]}」，"
                f"原价 {product.current_price or '—'} {product.currency}，"
                f"SKU {len(product.skus)} 个，图片 {len(product.gallery)} 张，"
                f"{rating_text}，分类 {crumbs_text or '—'}"
                + (f"，摘要 {len(product.ai_summary)} 字" if product.ai_summary else "")
                + "。"
            ),
            source_url=response.url,
        )
        # Dataset folders follow the job's selected category first, then the
        # page's own trail. Since 2026-11-05 the parser already cuts that
        # trail to two levels and drops the home crumb, so this list is at
        # most three entries and ``category_folder`` keeps the first two.
        page_crumbs = [
            crumb.get("name", "")
            for crumb in product.breadcrumbs
            if crumb.get("name") and crumb.get("name").lower() not in {"home", "首页"}
        ]
        breadcrumb_names = [target["category_name"]]
        for crumb in page_crumbs:
            if crumb not in breadcrumb_names:
                breadcrumb_names.append(crumb)
        yield {
            "type": "product",
            "payload": product.to_payload(),
            "breadcrumb_names": breadcrumb_names,
            "source_url": response.url,
            "structure_version": 2,
            "parser_version": "joybuy_uk.v2",
        }
