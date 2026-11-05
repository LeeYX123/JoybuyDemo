"""HTTP cache policy for the live site (2026-11-05).

Scrapy's default ``DummyPolicy`` caches every status except a few 5xx codes —
**including 307 redirects**. The cache key is the request fingerprint, which
ignores headers and cookies. That combination is dangerous here: an anonymous
request that got bounced to ``/login`` (307) is cached under the listing URL,
so the next crawler run is served the cached redirect and never touches the
network at all. On 2026-11-05 a run with a *valid* account session reported
"login wall" for exactly this reason — the account cookies never left the
process.

Rules enforced here:

- only ``200`` responses are cached (a redirect is a state, not content);
- a page that classifies as a login wall or risk-control wall is never
  cached, because replaying it would hide the wall from later runs;
- expiry keeps the project-wide setting (``HTTPCACHE_EXPIRATION_SECS``).
"""

from scrapy.extensions.httpcache import DummyPolicy


class SuccessOnlyCachePolicy(DummyPolicy):
    """Cache successful, non-blocked pages only."""

    def should_cache_response(self, response, request) -> bool:
        if response.status != 200:
            return False
        try:
            from joybuy_crawler.render import classify_page
        except Exception:  # noqa: BLE001 - policy must never break a download
            return True
        html = getattr(response, "text", "") or ""
        verdict = classify_page(response.url, html[:200000])
        return not (verdict.risk_control or verdict.login_required)
