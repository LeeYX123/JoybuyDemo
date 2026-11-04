"""Scrapy pipeline archiving every raw response into crawler_control.

Spiders carry ``crawl_run_public_id`` (a ``CrawlRun.public_id`` set by the
task orchestrator); each downloaded response is gzip-archived and indexed
with retention bookkeeping via ``crawler_control.services``.
"""

from crawler_control.models import CrawlRun
from crawler_control.services import record_raw_response


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
        return None
