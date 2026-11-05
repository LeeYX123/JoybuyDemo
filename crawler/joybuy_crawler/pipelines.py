"""Scrapy pipelines archiving raw responses and importing products.

``RawArchivePipeline`` is the legacy response archiver.
``RecordRulePipeline`` (2026-11-05) is the per-record gate: field rules
reject implausible products before they can reach staging, and a run-level
price guard raises the alarm when the whole run looks broken.
``StagingPipeline`` (2026-11-05) is the per-product stage of the live
run executor: dataset files, staging ingest, quality-gated import and
run progress/events.
"""

import logging

from crawler_control.models import CrawlRun
from crawler_control.services import (
    complete_run_failed,
    record_raw_response,
    record_run_event,
    update_run_progress,
)

logger = logging.getLogger("joybuy_crawler.pipelines")


class RawArchivePipeline:
    def open_spider(self, spider):
        public_id = getattr(spider, "crawl_run_public_id", None)
        if not public_id:
            raise RuntimeError(
                "Spider is missing crawl_run_public_id; raw responses cannot be archived."
            )
        self.run = CrawlRun.objects.get(public_id=public_id)

    def process_response(self, response, spider):
        record_raw_response(
            self.run,
            url=response.url,
            status_code=response.status,
            payload=response.body,
            content_type=response.headers.get(b"Content-Type", b"").decode("latin-1"),
        )


class RecordRulePipeline:
    """Record-level field rules + run-level price anomaly alarm.

    Sits between the spider and ``StagingPipeline`` (priority 150 vs 200).
    A product that trips a fatal rule is dropped here, so a selector that
    keeps matching after a site revamp can never write junk into staging,
    the dataset folder or the business tables. Non-fatal violations stay
    on the record (``rule_warnings``) and are reported per product.

    The price guard accumulates every observed price for the run; its
    verdict is written once when the spider closes. Nothing here changes
    the run status — it only makes the breakage visible, because a silent
    anomaly is the failure this layer exists to prevent.
    """

    def __init__(self):
        from joybuy_crawler.quality import PriceDistributionGuard

        self.guard = PriceDistributionGuard()
        self.run = None
        self.rejected = 0
        self.flagged = 0
        self.accepted = 0

    @classmethod
    def from_crawler(cls, crawler):
        from scrapy import signals

        instance = cls()
        crawler.signals.connect(instance.spider_closed, signal=signals.spider_closed)
        return instance

    def open_spider(self, spider):
        self.run = getattr(spider, "run", None)
        if self.run is None:
            raise RuntimeError(
                "Spider is missing run; RecordRulePipeline cannot report violations."
            )

    def process_item(self, item, spider):
        from scrapy.exceptions import DropItem

        from joybuy_crawler.quality import apply_product_rules

        if item.get("type") != "product":
            return item

        payload, outcome = apply_product_rules(
            item.get("payload") or {}, source_url=item.get("source_url", "")
        )
        item["payload"] = payload
        self.guard.observe(payload)
        source_id = str(payload.get("source_id") or "?")
        source_url = item.get("source_url", "")

        if outcome.fatal:
            self.rejected += 1
            update_run_progress(self.run, failed=1)
            record_run_event(
                self.run,
                level="ERROR",
                code="RECORD_REJECTED",
                message=f"已丢弃商品 {source_id}：{outcome.summary()}",
                source_url=source_url,
            )
            raise DropItem(f"{source_id}: {outcome.summary()}")

        self.accepted += 1
        if outcome.violations:
            self.flagged += 1
            record_run_event(
                self.run,
                level="WARNING",
                code="RECORD_FLAGGED",
                message=f"商品 {source_id} 存在可疑字段，已放行：{outcome.summary()}",
                source_url=source_url,
            )
        return item

    def spider_closed(self, spider, reason=""):
        if self.run is None:
            return
        verdict = self.guard.verdict()
        if verdict is None:
            return
        record_run_event(
            self.run,
            level=verdict["level"],
            code=verdict["code"],
            message=verdict["message"],
        )
        spider.logger.warning("%s: %s", verdict["code"], verdict["message"])


class StagingPipeline:
    """Turn one parsed product item into dataset files + imported rows."""

    def __init__(self):
        # Initialised here so ``close_spider`` stays safe when a caller
        # (or a test) closes the pipeline without opening it first.
        self.saved_count = 0
        self.changed_count = 0

    def open_spider(self, spider):
        self.run = getattr(spider, "run", None)
        if self.run is None:
            raise RuntimeError(
                "Spider is missing run; StagingPipeline cannot record progress."
            )
        self.job = self.run.job
        self.saved_count = 0
        self.changed_count = 0

    def process_item(self, item, spider):
        from joybuy_crawler.dataset import dataset_root, save_product

        payload = item.get("payload") or {}
        source_id = str(payload.get("source_id") or "")
        if not source_id:
            return item

        # 1. Local dataset folder (requirement: folder ↔ data 1:1 mapping).
        try:
            root = dataset_root(str(self.run.public_id), self.job.name)
            index_line = save_product(
                root,
                breadcrumb_names=item.get("breadcrumb_names") or [],
                payload=payload,
            )
            self.saved_count += 1
            if index_line.get("changed"):
                self.changed_count += 1

            images = index_line.get("images") or {}
            main_count = len(images.get("main") or [])
            detail_count = len(images.get("detail") or [])
            failed_images = len(images.get("main_errors") or []) + len(
                images.get("detail_errors") or []
            )
            record_run_event(
                self.run,
                level="INFO",
                code="DATASET_SAVED",
                message=(
                    f"商品 {source_id} 已落盘：var/crawl_exports/"
                    f"{root.name}/{index_line.get('product_dir') or '?'}"
                    f"（product.json；主图 {main_count} 张、详情图 {detail_count} 张"
                    + (f"，失败 {failed_images} 张" if failed_images else "")
                    + (
                        "，内容无变化，索引未追加"
                        if not index_line.get("changed")
                        else ""
                    )
                    + "）。"
                ),
                source_url=item.get("source_url", ""),
            )
        except Exception as exc:  # noqa: BLE001 - dataset failure is logged, not fatal
            record_run_event(
                self.run,
                level="WARNING",
                code="DATASET_WRITE_FAILED",
                message=f"商品 {source_id} 的本地数据集写入失败：{exc}",
                source_url=item.get("source_url", ""),
            )

        # 2. Staging + quality-gated import (existing chain, unchanged).
        from crawler_control.import_services import (
            StagingImportRejected,
            import_staging_product,
        )
        from offers.models import Currency, Market

        from joybuy_crawler.ingest import ingest_product_payload

        update_run_progress(self.run, downloaded=1)
        try:
            staging = ingest_product_payload(
                self.run,
                payload,
                source_system=self.job.source_catalog.source_system,
                source_url=item.get("source_url", ""),
                parser_version=item.get("parser_version", "joybuy_uk.v2"),
                structure_version=item.get("structure_version", 2),
            )
        except Exception as exc:  # noqa: BLE001
            update_run_progress(self.run, failed=1)
            record_run_event(
                self.run,
                level="ERROR",
                code="STAGING_FAILED",
                message=f"商品 {source_id} 写入暂存表失败：{exc}",
                source_url=item.get("source_url", ""),
            )
            return item

        market = Market.objects.filter(code="GB", is_active=True).first()
        currency = Currency.objects.filter(
            code=(payload.get("currency") or "GBP")
        ).first()
        try:
            outcome = import_staging_product(
                staging,
                market=market,
                currency=currency or market.default_currency,
                locale=self.job.locale,
            )
        except StagingImportRejected as exc:
            update_run_progress(self.run, failed=1)
            record_run_event(
                self.run,
                level="ERROR",
                code="IMPORT_REJECTED",
                message=str(exc),
                source_url=item.get("source_url", ""),
            )
            return item
        except Exception as exc:  # noqa: BLE001 - per-product import failure
            update_run_progress(self.run, failed=1)
            record_run_event(
                self.run,
                level="ERROR",
                code="IMPORT_FAILED",
                message=f"商品 {source_id} 导入失败：{exc}",
                source_url=item.get("source_url", ""),
            )
            return item

        update_run_progress(self.run, succeeded=1)
        record_run_event(
            self.run,
            level="INFO",
            code="PRODUCT_IMPORTED",
            message=(
                f"商品 {source_id} 已入库：SPU {outcome.spu.public_id}"
                f"（{'新建' if outcome.created_spu else '更新'}），"
                f"SKU {len(outcome.skus)} 个，Offer {len(outcome.offers)} 个，"
                f"暂存记录 {staging.public_id}。"
            ),
            source_url=item.get("source_url", ""),
        )
        return item

    def close_spider(self, spider):
        """Terminal state write-back (requirement: failures update status).

        Scrapy 2.13 calls ``close_spider(spider)`` without a reason; the
        finish reason is read from the stats instead.
        """

        if self.saved_count:
            record_run_event(
                self.run,
                level="INFO",
                code="DATASET_SUMMARY",
                message=f"共刷新 {self.saved_count} 个商品目录，其中 {self.changed_count} 个内容有变化"
                f"（{self.saved_count - self.changed_count} 个未变化，索引未追加）。",
            )

        run = CrawlRun.objects.select_related("job").get(pk=self.run.pk)
        if run.status != CrawlRun.Status.RUNNING:
            return  # paused/canceled by an admin while crawling
        finish_reason = "finished"
        try:
            stats = spider.crawler.stats.get_stats()
            finish_reason = str(stats.get("finish_reason", "finished"))
        except Exception:  # noqa: BLE001, S110 - stats may be gone during teardown
            pass
        fatal = getattr(spider, "fatal_error", "")
        if finish_reason not in {"finished", "completed"} or fatal:
            complete_run_failed(
                run,
                reason=fatal or f"爬虫异常结束（结束原因：{finish_reason}）",
            )
        elif run.succeeded_count == 0 and run.failed_count > 0:
            complete_run_failed(
                run,
                reason=f"发现的商品全部导入失败（失败 {run.failed_count} 个，成功 0 个）。",
            )
        elif run.succeeded_count == 0 and run.discovered_count == 0:
            complete_run_failed(
                run,
                reason="没有发现任何商品：列表页可能被风控拦截、需要登录，"
                "或站点结构已改版。",
            )
        else:
            from crawler_control.services import complete_run

            complete_run(run, outcome=CrawlRun.Status.SUCCEEDED)
