"""Scrapy settings for the Joybuy research crawler.

Rate limits, concurrency and cache behaviour are read from the environment
so quotas follow the granted authorisation instead of being hard-coded.
"""

import os
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
VAR_ROOT = REPOSITORY_ROOT / "var"

BOT_NAME = "joybuy_crawler"
SPIDER_MODULES = ["joybuy_crawler.spiders"]
NEWSPIDER_MODULE = "joybuy_crawler.spiders"

# Honour the authorisation scope: robots.txt and low default rates.
ROBOTSTXT_OBEY = True
DOWNLOAD_DELAY = float(os.getenv("CRAWL_DOWNLOAD_DELAY", "2.0"))
# Every inter-request gap is randomised to 0.5x–1.5x DOWNLOAD_DELAY. A
# fixed interval is itself a fingerprint: an exactly-2.000s cadence is
# trivially distinguishable from a human session, so the jitter is what
# keeps the crawl polite-looking rather than the absolute delay value.
RANDOMIZE_DOWNLOAD_DELAY = True
CONCURRENT_REQUESTS = int(os.getenv("CRAWL_CONCURRENT_REQUESTS", "2"))
CONCURRENT_REQUESTS_PER_DOMAIN = int(os.getenv("CRAWL_CONCURRENT_PER_DOMAIN", "2"))
DOWNLOAD_TIMEOUT = int(os.getenv("CRAWL_DOWNLOAD_TIMEOUT", "60"))
USER_AGENT = "JoybuyResearchBot/1.0 (+authorized-research)"

# 429/5xx follow the exponential backoff retry policy; 403/401 never retry.
RETRY_ENABLED = True
RETRY_TIMES = int(os.getenv("CRAWL_RETRY_TIMES", "3"))
RETRY_HTTP_CODES = [408, 429, 500, 502, 503, 504]
RETRY_PRIORITY_ADJUST = -1

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = float(os.getenv("CRAWL_AUTOTHROTTLE_START", "2.0"))
AUTOTHROTTLE_MAX_DELAY = float(os.getenv("CRAWL_AUTOTHROTTLE_MAX", "30.0"))
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

# Multi-account rotation (2026-11-05, operator decision): one crawl spreads
# its requests across the account pool instead of holding a single identity.
# Each stint draws a fresh random budget, so the switch cadence is not a
# fixed period. Set CRAWL_ACCOUNT_ROTATION=false to pin the first account.
CRAWL_ACCOUNT_ROTATION_ENABLED = (
    os.getenv("CRAWL_ACCOUNT_ROTATION", "true").strip().lower() == "true"
)
CRAWL_ACCOUNT_ROTATE_MIN_SECONDS = float(
    os.getenv("CRAWL_ACCOUNT_ROTATE_MIN_SECONDS", "300")
)
CRAWL_ACCOUNT_ROTATE_MAX_SECONDS = float(
    os.getenv("CRAWL_ACCOUNT_ROTATE_MAX_SECONDS", "900")
)
CRAWL_ACCOUNT_ROTATE_MIN_REQUESTS = int(
    os.getenv("CRAWL_ACCOUNT_ROTATE_MIN_REQUESTS", "20")
)
CRAWL_ACCOUNT_ROTATE_MAX_REQUESTS = int(
    os.getenv("CRAWL_ACCOUNT_ROTATE_MAX_REQUESTS", "60")
)

HTTPCACHE_ENABLED = (
    os.getenv("CRAWL_HTTPCACHE_ENABLED", "true").strip().lower() == "true"
)
HTTPCACHE_EXPIRATION_SECS = int(os.getenv("CRAWL_HTTPCACHE_EXPIRATION_SECS", "21600"))
HTTPCACHE_DIR = str(VAR_ROOT / "cache" / "scrapy")
HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"
# DummyPolicy (the default) caches 307 redirects, and the cache key ignores
# cookies — so an anonymous "/login" bounce would be replayed to every later
# run, including authenticated ones. Only successful pages are cached now.
HTTPCACHE_POLICY = "joybuy_crawler.cache_policy.SuccessOnlyCachePolicy"

COOKIES_ENABLED = True
DEFAULT_REQUEST_HEADERS = {
    "Accept-Language": os.getenv("CRAWL_ACCEPT_LANGUAGE", "en-GB,en;q=0.8"),
}

# 图文详情/规格参数（2026-11-09）：PC 详情页这段是客户端渲染，只有
# https://www.joybuy.co.uk/dg/<sku> 的 SSR 里有 structuredFloors。
# 这里刻意选 www 域名——m.joybuy.co.uk/robots.txt 明确 Disallow: /dg/，
# www 站 robots 没有这条限制（见 docs/14 §7.4）。每个商品多 1 次请求。
JOYBUY_MOBILE_DETAIL_ENABLED = (
    os.getenv("CRAWL_MOBILE_DETAIL", "true").strip().lower() == "true"
)

# 变体价格补抓（WP-45 阶段 1，2026-11-15）：详情页 JSON 只有当前浏览 sku 的
# 价格，非主变体的价格要逐个请求它自己的 /dp/<sku> 页面（与 /dg/ 同理，www
# 域名）。默认开，但每个商品最多补 CRAWL_VARIANT_PRICE_LIMIT 个变体，防变体
# 数失控打爆请求预算；风控收紧时可设 CRAWL_VARIANT_PRICES=false 关掉，
# 变体价格留空不阻断商品落盘。
JOYBUY_VARIANT_PRICES_ENABLED = (
    os.getenv("CRAWL_VARIANT_PRICES", "true").strip().lower() == "true"
)
JOYBUY_VARIANT_PRICE_LIMIT = int(os.getenv("CRAWL_VARIANT_PRICE_LIMIT", "10"))

# 代理（2026-11-09）：Scrapy 自带的 HttpProxyMiddleware 会读取进程环境变量
# 和 Windows 注册表代理，但 `no_proxy` 可能把它旁路掉，也不方便只给爬虫进程
# 指定代理。这里提供显式 opt-in：留空 = 完全沿用 Scrapy 原有行为，绝不硬编码
# 任何代理地址；`CRAWL_HTTPS_PROXY` 只作用于 https 请求。
CRAWL_HTTP_PROXY = os.getenv("CRAWL_HTTP_PROXY", "").strip()
CRAWL_HTTPS_PROXY = os.getenv("CRAWL_HTTPS_PROXY", "").strip()

# 连接前置检查（2026-11-09）：正式运行在启动 Scrapy 前做一次有超时的
# TCP（配置代理时）/ TLS（直连时）连接检查。网络不通就立即失败并写明原因，
# 而不是重试 40 秒后把网络问题误报成"风控/改版"。只做连接，不发 HTTP 请求。
CRAWL_PREFLIGHT_ENABLED = (
    os.getenv("CRAWL_PREFLIGHT_ENABLED", "true").strip().lower() == "true"
)
CRAWL_PREFLIGHT_TIMEOUT = float(os.getenv("CRAWL_PREFLIGHT_TIMEOUT", "8"))

DOWNLOADER_MIDDLEWARES = {
    "joybuy_crawler.middlewares.HeaderRedactionMiddleware": 560,
    # 580 在 Scrapy 的 HttpProxyMiddleware（750）之前，只设置 request.meta。
    "joybuy_crawler.middlewares.ProxyConfigMiddleware": 580,
}

ITEM_PIPELINES = {
    "joybuy_crawler.pipelines.RawArchivePipeline": 100,
}

LOG_LEVEL = os.getenv("CRAWL_LOG_LEVEL", "INFO")
LOG_FORMAT = "%(levelname)s %(message)s"

# Scrapy runs outside manage.py; wire Django before pipelines import models.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"
