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
from collections import Counter

import scrapy
from crawler_control.models import CrawlRun

from joybuy_crawler.parsers.joybuy_uk import (
    UK_PRODUCT_URL_PATTERN,
    extract_variant_price,
    merge_mobile_detail,
    mobile_detail_url,
    parse_uk_listing,
    parse_uk_product_detail,
    variant_page_url,
)

logger = logging.getLogger("joybuy_crawler.spider")

UK_BASE_URL = "https://www.joybuy.co.uk"
#: 是否追加一次图文/规格详情请求（settings 可关）。
MOBILE_DETAIL_SETTING = "JOYBUY_MOBILE_DETAIL_ENABLED"
#: WP-45 阶段 1：是否为非主变体逐个补抓价格页（每变体 1 次 /dp/<sku> 请求）。
VARIANT_PRICES_SETTING = "JOYBUY_VARIANT_PRICES_ENABLED"
#: 单个商品最多补抓多少个变体价格页（防变体数失控打爆请求预算）。
VARIANT_PRICE_LIMIT_SETTING = "JOYBUY_VARIANT_PRICE_LIMIT"
DEFAULT_VARIANT_PRICE_LIMIT = 10


def _fill_from_listing_entry(product, entry: dict) -> list[str]:
    """用列表卡片数据补齐详情页缺失的必填字段，返回补上的字段名。

    2026-11-16：Joybuy 详情页改版/风控时可能拿不到 title、价格或图片，
    而列表卡片仍带着这些信息。这里只补 import 的硬要求字段（title /
    currency / current_price / skus）与主图，并对``missing_fields``重算，
    让落库至少有一份可用的最小 payload。
    """

    if not entry:
        return []
    filled: list[str] = []
    missing = set(getattr(product, "missing_fields", []) or [])

    if "title" in missing and not getattr(product, "title", ""):
        title = str(entry.get("title") or "").strip()
        if title:
            product.title = title
            filled.append("title")

    price = str(entry.get("original_price") or "").strip()
    if price and (
        "current_price" in missing or not getattr(product, "current_price", "")
    ):
        product.current_price = price
        product.list_price = product.list_price or price
        filled.append("current_price")
    if price and not getattr(product, "currency", ""):
        product.currency = "GBP"
        filled.append("currency")

    # skus 是 import 的硬要求：详情页连 sku 都没解析出来时，用列表
    # source_id 造一个最小 sku（价格取列表价），否则整条记录会被拒。
    if ("skus" in missing or not getattr(product, "skus", None)) and getattr(
        product, "source_id", ""
    ):
        product.skus = [
            {
                "skuId": product.source_id,
                "price": price or "",
                "availability": "UNKNOWN",
                "specs": [],
            }
        ]
        filled.append("skus")

    if not getattr(product, "gallery", None) and entry.get("image_url"):
        product.gallery = [str(entry["image_url"])]
        filled.append("gallery")

    product.missing_fields = [
        name
        for name in ("source_id", "title", "currency", "current_price", "skus")
        if not getattr(product, name)
    ]
    return filled


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
        # 「跳过已入库」任务级开关（2026-11-12）：参数快照优先，旧任务回退字段。
        self.skip_imported_products = bool(
            snapshot.get("skip_imported_products", self.job.skip_imported_products)
        )
        # 列表翻页（2026-11-12，默认开）：开启后允许 /s?k=…&page=N 继续翻页
        # 直到抓满 limit；robots.txt 禁止 page= 参数，因此该开关的运行由
        # runner 关闭 ROBOTSTXT_OBEY（运营者授权偏离，见 runner 注释）。
        self.allow_pagination = bool(
            snapshot.get(
                "allow_pagination", getattr(self.job, "allow_pagination", True)
            )
        )
        # Listing download diagnostics (2026-11-09). A run whose every listing
        # request dies at the transport layer used to be reported as
        # "风险/登录/改版"; these counters let the pipeline tell the two apart.
        self.listing_fetch_errors = 0
        self.listing_error_types: Counter[str] = Counter()
        self.listing_successes = 0
        self.last_listing_error = ""

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
            safe_url = self._robots_safe_listing_url(
                (snapshot_row.source_url if snapshot_row else "")
                or f"{UK_BASE_URL}/s?k={category.source_id}"
            )
            # 翻页基准 URL：只有 /s?k=… 形式可翻页（minihome 频道页不翻）。
            pagination_base = ""
            if "/s?" in safe_url and "k=" in safe_url:
                pagination_base = safe_url
            targets.append(
                {
                    "source_category_id": category.source_id,
                    "category_name": snapshot_row.name
                    if snapshot_row
                    else category.source_id,
                    "source_url": safe_url,
                    "pagination_base": pagination_base,
                    "include_descendants": include_descendants,
                    "limit": self.product_limit,
                    "collected": 0,
                }
            )
        return targets

    # -- crawling -----------------------------------------------------------

    def _imported_source_ids(self, source_ids: list[str]) -> set[str]:
        """返回其中已入库（存在 ``SpuSourceIdentity``）的 source_id 集合。

        仅用于「跳过已入库」开关；一次 IN 查询，不逐个查库。
        """

        from catalog.models import SpuSourceIdentity

        if not source_ids:
            return set()
        system = str(self.job.source_catalog.source_system or "").strip().casefold()
        if not system:
            return set()
        return set(
            SpuSourceIdentity.objects.filter(
                source_system=system, source_id__in=source_ids
            ).values_list("source_id", flat=True)
        )

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
                "列表页目标 %d/%d：%s（%s，翻页=%s）",
                index + 1,
                len(self.targets),
                target["category_name"],
                crawl_url,
                "开"
                if self.allow_pagination and target.get("pagination_base")
                else "关",
            )
            yield scrapy.Request(
                crawl_url,
                callback=self.parse_listing,
                errback=self.listing_failed,
                meta={"target": target, "page": 1},
                dont_filter=True,
            )

    def listing_failed(self, failure):
        """Record a listing request that never produced a response.

        Scrapy routes exhausted retries and transport failures here, e.g.
        ``twisted.internet.error.ConnectionLost`` or
        ``twisted.web._newclient.ResponseNeverReceived`` (the 2026-11-09
        VPN/TLS incident). The event and counters are what let
        ``StagingPipeline.close_spider`` say "network/TLS" instead of
        guessing "risk control / login / site revamp".
        """

        from crawler_control.services import record_run_event

        request = getattr(failure, "request", None)
        url = getattr(request, "url", "") or ""
        value = getattr(failure, "value", None)
        exc_type = type(value).__name__ if value is not None else "UnknownError"
        detail = " ".join(str(value or "").split())[:300]

        self.listing_fetch_errors += 1
        self.listing_error_types[exc_type] += 1
        self.last_listing_error = f"{exc_type}: {detail}".strip(": ")
        record_run_event(
            self.run,
            level="ERROR",
            code="LISTING_FETCH_FAILED",
            message=(
                f"列表页请求失败 {url}：{exc_type}{f'：{detail}' if detail else ''}"
                f"（本轮列表页下载失败第 {self.listing_fetch_errors} 次）。"
                "属网络/TLS 层错误，不是风控或结构改版。"
            ),
            source_url=url,
        )
        self.logger.warning("LISTING_FETCH_FAILED %s %s (%s)", url, exc_type, detail)
        stats = getattr(getattr(self, "crawler", None), "stats", None)
        if stats is not None:
            try:
                stats.inc_value("joybuy/listing_fetch_failed")
                stats.inc_value(f"joybuy/listing_error_type/{exc_type}")
            except Exception:  # noqa: BLE001, S110 - stats are diagnostics only
                pass

    def parse_listing(self, response):
        # A response exists, so this listing page did reach us even if the
        # card selectors later turn out empty (the risk/login/structure case).
        self.listing_successes += 1
        target = response.meta["target"]
        page_number = int(response.meta.get("page", 1))
        try:
            entries = parse_uk_listing(response.text)
        except RuntimeError as exc:
            from crawler_control.services import record_run_event

            if page_number >= 2 and self.allow_pagination:
                # 翻页页没有卡片 = 结果集到此为止，属正常结束而非解析失败。
                record_run_event(
                    self.run,
                    level="INFO",
                    code="PAGINATION_COMPLETE",
                    message=f"类目「{target['category_name']}」第 {page_number} 页"
                    "没有更多商品，翻页结束。",
                    source_url=response.url,
                )
                self._emit_shortfall(target, page_number, pagination_ended=True)
                return
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
        candidates: list[tuple[object, str]] = []
        for entry in accepted_entries:
            # collected 在候选全部收集后才统一递增（skip_imported 会先分流），
            # 这里必须按「已收集 + 已入候选数」判断，否则跨页时会超过 limit。
            if target["collected"] + len(candidates) >= target["limit"]:
                over_limit += 1
                continue
            match = UK_PRODUCT_URL_PATTERN.search(entry.source_url)
            if not match:
                continue
            if match.group(1) in self.seen_product_ids:
                duplicates += 1
                continue
            candidates.append((entry, match.group(1)))

        # 跳过已入库（2026-11-12，任务级开关）：列表阶段先查来源身份，
        # 已入库商品不再请求详情页（因此不会刷新价格/库存/评分）。
        skipped_imported = 0
        if self.skip_imported_products and candidates:
            existing = self._imported_source_ids(
                [source_id for _entry, source_id in candidates]
            )
            if existing:
                skipped_imported = sum(
                    1 for _entry, source_id in candidates if source_id in existing
                )
                for _entry, source_id in candidates:
                    # 计入 seen：同一商品在其它类目列表里也不再重复查询/抓取。
                    self.seen_product_ids.add(source_id)
                candidates = [
                    (entry, source_id)
                    for entry, source_id in candidates
                    if source_id not in existing
                ]

        for entry, source_id in candidates:
            self.seen_product_ids.add(source_id)
            target["collected"] += 1
            fresh += 1
            yield scrapy.Request(
                entry.source_url,
                callback=self.parse_detail,
                # 2026-11-16: 列表卡片数据随请求透传，详情解析缺 title/价格时兜底
                # （Joybuy 改版/风控导致详情页拿不到字段时，至少还能导入最小 payload）。
                meta={
                    "target": target,
                    "rank": entry.rank,
                    "listing_entry": {
                        "title": entry.title,
                        "original_price": entry.original_price,
                        "image_url": entry.image_url,
                        "source_id": source_id,
                    },
                },
            )

        if skipped_imported:
            record_run_event(
                self.run,
                level="INFO",
                code="PRODUCTS_SKIPPED_IMPORTED",
                message=(
                    f"类目「{target['category_name']}」本轮跳过 {skipped_imported} 个"
                    "已入库商品（任务开启「跳过已入库」，不再请求其详情页）。"
                ),
                source_url=response.url,
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

        # 列表翻页（2026-11-12，任务级开关默认开）：还有缺口且本页仍有新内容
        # （新入队，或因「跳过已入库」被跳过的新商品）时请求下一页；整页全是
        # 跨类目重复/无卡片 = 结果集到头，停止翻页。
        pagination_base = target.get("pagination_base") or ""
        page_has_new = fresh > 0 or skipped_imported > 0
        can_paginate = (
            self.allow_pagination
            and bool(pagination_base)
            and target["collected"] < target["limit"]
            and page_has_new
            and page_number < self._max_listing_pages()
        )
        if can_paginate:
            yield scrapy.Request(
                f"{pagination_base}&page={page_number + 1}",
                callback=self.parse_listing,
                errback=self.listing_failed,
                meta={"target": target, "page": page_number + 1},
                dont_filter=True,
            )
        elif target["collected"] < target["limit"]:
            self._emit_shortfall(
                target,
                page_number,
                pagination_ended=bool(self.allow_pagination),
            )

    def _max_listing_pages(self) -> int:
        """翻页安全上限（防止异常站点导致无限翻页），settings 可调。"""

        crawler = getattr(self, "crawler", None)
        settings = getattr(crawler, "settings", None)
        if settings is not None:
            return int(settings.getint("JOYBUY_MAX_LISTING_PAGES", 25))
        return 25

    def _emit_shortfall(self, target, page_number, *, pagination_ended: bool):
        from crawler_control.services import record_run_event

        if pagination_ended:
            reason = (
                f"翻页至第 {page_number} 页后没有更多结果"
                f"（安全上限 {self._max_listing_pages()} 页）。"
            )
        else:
            # 任务关闭了翻页：robots.txt 禁止 page=，只抓第一屏。
            reason = "任务未开启翻页，robots.txt 也不允许 page= 参数。"
        record_run_event(
            self.run,
            level="INFO",
            code="LISTING_SHORTFALL",
            message=(
                f"类目「{target['category_name']}」最终只拿到 "
                f"{target['collected']}/{target['limit']} 个商品：{reason}"
            ),
            source_url=target.get("pagination_base") or target.get("source_url", ""),
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
            # 2026-11-16: 详情页字段缺失时用列表卡片数据兜底（title/原价/主图），
            # 保证 import 的硬要求字段齐全；仍然把缺字段如实打事件。
            entry = response.meta.get("listing_entry") or {}
            filled = _fill_from_listing_entry(product, entry)
            if filled:
                record_run_event(
                    self.run,
                    level="INFO",
                    code="DETAIL_FROM_LISTING_FALLBACK",
                    message=(
                        f"商品 {product.source_id} 详情页缺字段（{', '.join(product.missing_fields)}），"
                        f"已用列表卡片数据补齐：{', '.join(filled)}。"
                    ),
                    source_url=response.url,
                )
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
        # page's own trail (assembled in ``_build_item``); the parser already
        # cut that trail to two levels and dropped the home crumb.
        if self._mobile_detail_enabled() and product.source_id:
            # 图文详情/规格参数在 PC 端是客户端渲染（SSR 里只有 BAILOUT 占位），
            # 只有详情 SSR 页有 structuredFloors。追加一次请求，取回后合并再产出
            # 唯一一个 item；请求失败由 errback 兜底按 PC 数据落盘。
            yield scrapy.Request(
                mobile_detail_url(product.source_id),
                callback=self.parse_mobile_detail,
                errback=self.mobile_detail_failed,
                meta={**response.meta, "product": product},
                dont_filter=True,
            )
            return
        yield from self._start_variant_price_chain(product, target, response)

    def _mobile_detail_enabled(self) -> bool:
        """是否追加图文详情请求（默认开；settings 可关）。"""

        settings = getattr(getattr(self, "crawler", None), "settings", None)
        if settings is None:
            return True
        return settings.getbool(MOBILE_DETAIL_SETTING, True)

    def parse_mobile_detail(self, response):
        from crawler_control.services import record_run_event

        product = response.meta["product"]
        target = response.meta["target"]
        try:
            merge_mobile_detail(product, response.text)
        except Exception as exc:  # noqa: BLE001 - PC 数据仍可落盘
            record_run_event(
                self.run,
                level="WARNING",
                code="MOBILE_DETAIL_PARSE_FAILED",
                message=f"商品 {product.source_id} 的图文详情解析失败，"
                f"按 PC 数据落盘：{exc}",
                source_url=response.url,
            )
        else:
            record_run_event(
                self.run,
                level="INFO",
                code="MOBILE_DETAIL_MERGED",
                message=(
                    f"商品 {product.source_id} 已合并图文详情："
                    f"图文区块 {len(product.content_sections)} 个，"
                    f"规格参数 {len(product.specifications)} 条"
                    + (
                        f"（{len(product.specification_tables)} 张表格）"
                        if product.specification_tables
                        else ""
                    )
                    + f"，视频 {len(product.videos)} 个。"
                ),
                source_url=response.url,
            )
        yield from self._start_variant_price_chain(product, target, response)

    def mobile_detail_failed(self, failure):
        """图文详情请求失败（含 robots 拦截）：只按 PC 数据落盘。"""

        from crawler_control.services import record_run_event

        request = getattr(failure, "request", None)
        meta = getattr(request, "meta", {}) or {}
        product = meta.get("product")
        target = meta.get("target")
        if product is None or target is None:
            return
        record_run_event(
            self.run,
            level="WARNING",
            code="MOBILE_DETAIL_FAILED",
            message=(
                f"商品 {product.source_id} 的图文详情请求失败，"
                f"已按 PC 数据落盘：{failure.value}"
            ),
            source_url=getattr(request, "url", ""),
        )
        response = getattr(failure, "request", None)
        yield from self._start_variant_price_chain(product, target, response)

    # -- WP-45 阶段 1：变体价格补抓 ------------------------------------
    # 详情页 JSON 只描述当前浏览 sku 的价格（productPriceFloor）；每个非主
    # 变体的价格要用自己的 /dp/<sku> 页面补（实测 2026-11-15，docs/14 §8 的
    # 第二请求先例）。逐个串行补抓，队列空了才产出唯一一个 item；任何一次
    # 失败只影响那一个变体（price 留空），不阻断商品落盘。

    def _variant_prices_enabled(self) -> bool:
        settings = getattr(getattr(self, "crawler", None), "settings", None)
        if settings is None:
            return True
        return settings.getbool(VARIANT_PRICES_SETTING, True)

    def _variant_price_limit(self) -> int:
        settings = getattr(getattr(self, "crawler", None), "settings", None)
        if settings is None:
            return DEFAULT_VARIANT_PRICE_LIMIT
        return settings.getint(VARIANT_PRICE_LIMIT_SETTING, DEFAULT_VARIANT_PRICE_LIMIT)

    def _pending_variant_skus(self, product) -> list[str]:
        """需要补价格的变体源 sku id（主变体继承页面价格，跳过）。

        ``CRAWL_VARIANT_PRICE_LIMIT <= 0`` 表示**不限个数**（2026-11-19 用户
        口径：商品规格必须一比一完整抓取，宁可慢也不能缺变体价格）。
        """

        limit = self._variant_price_limit()
        pending = []
        for variant in product.variants or []:
            if limit > 0 and len(pending) >= limit:
                break
            sku_id = str(variant.get("source_sku_id") or "").strip()
            if not sku_id or variant.get("price") or variant.get("is_primary"):
                continue
            pending.append(sku_id)
        return pending

    def _start_variant_price_chain(self, product, target, response):
        """有变体价格要补就发第一个请求，否则直接产出 item。"""

        if not self._variant_prices_enabled() or not product.variants:
            yield self._build_item(product, target)
            return
        pending = self._pending_variant_skus(product)
        if not pending:
            yield self._build_item(product, target)
            return
        meta = {
            **(getattr(response, "meta", {}) or {}),
            "product": product,
            "target": target,
            "variant_queue": pending,
            "variant_fetched": 0,
            "variant_price_failed": 0,
            "variant_sku_id": pending.pop(0),
        }
        yield scrapy.Request(
            variant_page_url(meta["variant_sku_id"]),
            callback=self.parse_variant_price,
            errback=self.variant_price_failed,
            meta=meta,
            dont_filter=True,
        )

    def _continue_variant_chain(self, product, target, meta):
        """补完一个变体后继续队列；队列空了合并事件并产出 item。"""

        from crawler_control.services import record_run_event

        queue = meta.get("variant_queue") or []
        if queue:
            meta["variant_sku_id"] = queue.pop(0)
            yield scrapy.Request(
                variant_page_url(meta["variant_sku_id"]),
                callback=self.parse_variant_price,
                errback=self.variant_price_failed,
                meta=meta,
                dont_filter=True,
            )
            return
        record_run_event(
            self.run,
            level="INFO",
            code="VARIANT_PRICES_MERGED",
            message=(
                f"商品 {product.source_id} 变体价格补抓完成："
                f"变体 {len(product.variants or [])} 个，"
                f"补抓 {meta.get('variant_fetched', 0)} 次"
                f"（失败 {meta.get('variant_price_failed', 0)} 次）。"
            ),
        )
        yield self._build_item(product, target)

    def parse_variant_price(self, response):
        meta = response.meta
        product = meta["product"]
        target = meta["target"]
        sku_id = meta.get("variant_sku_id") or ""
        price = None
        try:
            price = extract_variant_price(response.text)
        except Exception as exc:  # noqa: BLE001 - 单变体失败不阻断商品
            logger.warning(
                "商品 %s 变体 %s 价格页解析失败：%s",
                product.source_id,
                sku_id,
                exc,
            )
        if price:
            for variant in product.variants or []:
                if str(variant.get("source_sku_id")) == str(sku_id):
                    variant["price"] = price
                    variant["price_source"] = "variant_page"
                    break
            meta["variant_fetched"] = meta.get("variant_fetched", 0) + 1
        else:
            meta["variant_price_failed"] = meta.get("variant_price_failed", 0) + 1
        yield from self._continue_variant_chain(product, target, meta)

    def variant_price_failed(self, failure):
        """单个变体价格页失败（含 robots/风控）：价格留空，继续队列。"""

        meta = getattr(getattr(failure, "request", None), "meta", {}) or {}
        product = meta.get("product")
        target = meta.get("target")
        if product is None or target is None:
            return
        meta["variant_price_failed"] = meta.get("variant_price_failed", 0) + 1
        yield from self._continue_variant_chain(product, target, meta)

    def _build_item(self, product, target) -> dict:
        """组装唯一一条商品 item（PC 解析 + 可能的移动端合并）。"""

        page_crumbs = [
            crumb.get("name", "")
            for crumb in product.breadcrumbs
            if crumb.get("name") and crumb.get("name").lower() not in {"home", "首页"}
        ]
        breadcrumb_names = [target["category_name"]]
        for crumb in page_crumbs:
            if crumb not in breadcrumb_names:
                breadcrumb_names.append(crumb)
        payload = product.to_payload()
        # 任务所选的 Joybuy 菜单类目（如 l2:1580 节庆装饰品）。
        # source_category_id 语义仍是「菜单来源类目」（docs/05 §9.2），
        # 导入时用它解析本地类目（品类）并判断是否属于「活动商品」；
        # 商品自身的两级别名在 product_category_path 里，二者不要混用。
        payload["source_category_id"] = target.get("source_category_id", "")
        payload["crawl_source_category_id"] = target.get("source_category_id", "")
        payload["crawl_source_category_name"] = target.get("category_name", "")
        return {
            "type": "product",
            "payload": payload,
            "breadcrumb_names": breadcrumb_names,
            "source_url": product.source_url,
            "structure_version": 2,
            "parser_version": "joybuy_uk.v2",
        }
