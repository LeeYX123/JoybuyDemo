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

HTTPCACHE_ENABLED = os.getenv("CRAWL_HTTPCACHE_ENABLED", "true").strip().lower() == "true"
HTTPCACHE_EXPIRATION_SECS = int(os.getenv("CRAWL_HTTPCACHE_EXPIRATION_SECS", "21600"))
HTTPCACHE_DIR = str(VAR_ROOT / "cache" / "scrapy")
HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"

COOKIES_ENABLED = True
DEFAULT_REQUEST_HEADERS = {
    "Accept-Language": os.getenv("CRAWL_ACCEPT_LANGUAGE", "en-GB,en;q=0.8"),
}

DOWNLOADER_MIDDLEWARES = {
    "joybuy_crawler.middlewares.HeaderRedactionMiddleware": 560,
}

ITEM_PIPELINES = {
    "joybuy_crawler.pipelines.RawArchivePipeline": 100,
}

LOG_LEVEL = os.getenv("CRAWL_LOG_LEVEL", "INFO")
LOG_FORMAT = "%(levelname)s %(message)s"

# Scrapy runs outside manage.py; wire Django before pipelines import models.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"
