"""Scrapy middleware ensuring credentials never reach logs.

Scrapy's own downloader logs may include response headers; this middleware
emits a redacted, single-line summary at DEBUG for every request and
response so operators get visibility without cookie/token leakage.
"""

from joybuy_crawler.core.redaction import redact_headers


class HeaderRedactionMiddleware:
    def process_request(self, request, spider):
        spider.logger.debug(
            "Request %s %s headers=%s",
            request.method,
            request.url,
            redact_headers(request.headers),
        )
        return None

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
        spider.logger.debug("Request %s failed: %s", request.url, type(exception).__name__)
        return None
