"""Record-level field rules and run-level price anomaly detection.

Why this module exists (2026-11-05)
-----------------------------------
``crawler_control.quality_services`` already answers "how many records in
this batch are missing field X?" (a batch-rate gate). It cannot answer
"is *this one record* plausible?", which is the failure mode that actually
polluted the dataset before: a selector that keeps matching after a site
revamp, a recommendation/advert card that links to ``/dp/`` like a real
product, or a price element that silently returns ``0``.

Rule of thumb taken from the field: a parse that returns *something*
wrong is far more dangerous than a parse that raises, because nothing
alerts. Every rule here therefore produces an explicit, code-tagged
violation instead of quietly accepting the value.

Severities
----------
- ``fatal``: the record must not reach staging/import (data would be junk).
- ``warning``: the record is importable but suspicious; it is flagged on
  the run event stream and kept for review.

Nothing here talks to Scrapy or Django — it is pure functions plus two
small stateful collectors — so it can be unit-tested without a database.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

# -- tunables -------------------------------------------------------------

TITLE_MIN_LENGTH = 5
TITLE_MAX_LENGTH = 500
PRICE_MIN = Decimal("0.01")
PRICE_MAX = Decimal(100000)

#: Hosts a product/page URL may legitimately point at.
SOURCE_URL_HOSTS = ("joybuy.co.uk", "www.joybuy.co.uk")
#: Hosts trusted to serve product imagery (gallery / detail images).
IMAGE_HOST_SUFFIXES = ("joy-sourcing.com",)

#: Card titles that identify an advert / recommendation slot rather than a
#: real product. Such cards link to ``/dp/`` exactly like products do, so
#: only the title distinguishes them.
PROMO_TITLE_MARKERS = (
    "sponsored",
    "advertisement",
    "hot sale",
    "为你推荐",
    "热推",
    "广告",
)

_SOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")
_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


@dataclass(frozen=True)
class Violation:
    """One rule breach on one record."""

    code: str
    field: str
    message: str
    fatal: bool

    def as_log_line(self) -> str:
        severity = "致命" if self.fatal else "警告"
        return f"[{self.code}] {self.field}：{self.message}（{severity}）"


@dataclass
class RuleOutcome:
    violations: list[Violation] = field(default_factory=list)

    @property
    def fatal(self) -> bool:
        return any(item.fatal for item in self.violations)

    @property
    def warnings(self) -> list[Violation]:
        return [item for item in self.violations if not item.fatal]

    @property
    def codes(self) -> list[str]:
        return [item.code for item in self.violations]

    def summary(self) -> str:
        return "; ".join(item.as_log_line() for item in self.violations)

    def add(self, code, field_name, message, *, fatal):
        self.violations.append(
            Violation(code=code, field=field_name, message=message, fatal=fatal)
        )
        return self


# -- helpers --------------------------------------------------------------


def parse_price(raw) -> Decimal | None:
    """Parse a crawled price into a Decimal, or None when it is not a number.

    Accepts the shapes the parsers produce (``"12.99"``, ``"£12.99"``,
    ``"1,299.00"``, ``12.99``) and returns None for anything unparseable —
    including the empty string, ``"N/A"`` and prices carrying a range
    separator (``"9.99 - 12.99"``), which are ambiguous by nature.
    """

    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, Decimal):
        return raw
    if isinstance(raw, int | float):
        return Decimal(str(raw))
    text = str(raw).strip().replace(",", "")
    for symbol in ("£", "$", "€", "¥", "\u00a0"):
        text = text.replace(symbol, "")
    text = text.strip()
    if not text or "-" in text[1:]:  # keep a leading sign, reject ranges
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _host_of(url: str) -> str:
    match = re.match(r"^(?:https?:)?//([^/?#]+)", (url or "").strip(), re.IGNORECASE)
    return match.group(1).lower() if match else ""


def _is_allowed_image_url(url: str) -> bool:
    host = _host_of(url)
    return bool(host) and any(
        host == suffix or host.endswith(f".{suffix}") for suffix in IMAGE_HOST_SUFFIXES
    )


def _looks_like_promo_title(title: str) -> str:
    lowered = (title or "").casefold()
    for marker in PROMO_TITLE_MARKERS:
        if marker.casefold() in lowered:
            return marker
    return ""


# -- product detail rules -------------------------------------------------


def apply_product_rules(
    payload: dict, *, source_url: str = ""
) -> tuple[dict, RuleOutcome]:
    """Check one product payload and return a cleaned copy plus violations.

    The returned payload differs from the input only where a value had to
    be dropped (off-host image URLs) or where annotations were added
    (``rule_warnings``). The input dict is never mutated — callers decide
    whether to adopt the result.
    """

    outcome = RuleOutcome()
    cleaned = dict(payload or {})

    # 1. Identity: without a usable source id nothing downstream can dedupe.
    source_id = str(cleaned.get("source_id") or "").strip()
    if not source_id:
        outcome.add(
            "SOURCE_ID_MISSING", "source_id", "没有解析到 source_id", fatal=True
        )
    elif not _SOURCE_ID_PATTERN.match(source_id):
        outcome.add(
            "SOURCE_ID_INVALID",
            "source_id",
            f"{source_id!r} 不是合法的商品 ID",
            fatal=True,
        )

    # 2. Title: the strongest signal that a selector latched onto an advert
    #    card or a layout wrapper instead of the product heading.
    title = " ".join(str(cleaned.get("title") or "").split())
    cleaned["title"] = title
    if len(title) < TITLE_MIN_LENGTH:
        outcome.add(
            "TITLE_TOO_SHORT",
            "title",
            f"标题 {title!r} 少于 {TITLE_MIN_LENGTH} 个字符",
            fatal=True,
        )
    elif len(title) > TITLE_MAX_LENGTH:
        outcome.add(
            "TITLE_TOO_LONG",
            "title",
            f"标题长度 {len(title)} 个字符，疑似选择器吞掉了整块内容",
            fatal=False,
        )
    promo_marker = _looks_like_promo_title(title)
    if promo_marker:
        outcome.add(
            "TITLE_PROMO_TEXT",
            "title",
            f"标题含广告标记 {promo_marker!r}",
            fatal=False,
        )

    # 3. Price: the classic silent-corruption case — a price element that
    #    starts returning 0 or an empty node without the parse failing.
    price = parse_price(cleaned.get("current_price"))
    if price is None:
        outcome.add(
            "PRICE_MISSING",
            "current_price",
            f"无法从 {cleaned.get('current_price')!r} 解析出数字",
            fatal=True,
        )
    elif price <= 0:
        outcome.add(
            "PRICE_NOT_POSITIVE",
            "current_price",
            f"解析出的价格为 {price}；价格为 0 或负数通常说明选择器已失效",
            fatal=True,
        )
    elif price < PRICE_MIN or price > PRICE_MAX:
        outcome.add(
            "PRICE_OUT_OF_RANGE",
            "current_price",
            f"价格 {price} 超出合理区间 {PRICE_MIN}~{PRICE_MAX}",
            fatal=True,
        )

    # 4. Currency: a missing currency silently books offers under the
    #    market default, which makes price history incomparable.
    currency = str(cleaned.get("currency") or "").strip().upper()
    cleaned["currency"] = currency
    if not _CURRENCY_PATTERN.match(currency):
        outcome.add(
            "CURRENCY_INVALID",
            "currency",
            f"{currency!r} 不是三位字母币种代码",
            fatal=True,
        )

    # 5. SKUs: the offer import needs at least one purchasable variant.
    skus = cleaned.get("skus") or []
    if not skus:
        outcome.add("SKUS_MISSING", "skus", "没有解析到任何 SKU", fatal=True)
    else:
        bad_skus = [
            str(sku.get("source_id") or "?")
            for sku in skus
            if parse_price(sku.get("price")) is None
        ]
        if bad_skus:
            outcome.add(
                "SKU_PRICE_INVALID",
                "skus",
                f"{len(bad_skus)} 个 SKU 的价格无法解析：{', '.join(bad_skus[:5])}",
                fatal=False,
            )

    # 6. Source URL: guards against redirects to an error/login page and
    #    against a listing card that linked somewhere other than /dp/.
    if source_url:
        host = _host_of(source_url)
        if host not in SOURCE_URL_HOSTS:
            outcome.add(
                "SOURCE_URL_HOST_INVALID",
                "source_url",
                f"{host or source_url!r} 不是 joybuy.co.uk 域名",
                fatal=True,
            )
        elif "/dp/" not in source_url:
            outcome.add(
                "SOURCE_URL_NOT_PRODUCT",
                "source_url",
                f"{source_url!r} 不是 /dp/ 商品详情页地址",
                fatal=True,
            )

    # 7. Images: drop off-host URLs instead of writing them into the
    #    dataset (they would be downloaded from an unknown origin).
    images = list(cleaned.get("image_urls") or [])
    allowed = [url for url in images if _is_allowed_image_url(url)]
    if len(allowed) != len(images):
        outcome.add(
            "IMAGE_HOST_DROPPED",
            "image_urls",
            f"有 {len(images) - len(allowed)} 个图片地址不在受信域名 "
            f"({', '.join(IMAGE_HOST_SUFFIXES)}) 内，已剔除",
            fatal=False,
        )
        cleaned["image_urls"] = allowed
    detail_images = list(cleaned.get("detail_image_urls") or [])
    cleaned["detail_image_urls"] = [
        url for url in detail_images if _is_allowed_image_url(url)
    ]

    # 8. Price inversion: the business rule keeps the *original* price in
    #    ``current_price`` and the discounted one in ``main_price``, so the
    #    discounted price can never exceed the original. When it does, the
    #    two selectors were swapped and the recorded "original" is really
    #    the promo price — exactly the "price moved weirdly" symptom.
    main_price = parse_price(
        cleaned.get("joybuy", {}).get("priceInfo", {}).get("mainPrice")
    )
    if price is not None and main_price is not None and main_price > price:
        outcome.add(
            "PRICE_INVERSION",
            "current_price",
            f"优惠价 {main_price} 高于记录的原价 {price}，"
            "crossOffPrice / mainPrice 两个选择器疑似取反",
            fatal=False,
        )

    cleaned["rule_warnings"] = [item.code for item in outcome.warnings]
    return cleaned, outcome


# -- listing card rules ---------------------------------------------------


def check_listing_entry(*, title: str, source_url: str) -> RuleOutcome:
    """Decide whether one listing card is a real product.

    Listing pages interleave recommendation and advert tiles with genuine
    cards; those tiles still point at ``/dp/`` and would otherwise consume
    a share of the per-category product limit and pollute the dataset.
    """

    outcome = RuleOutcome()
    clean_title = " ".join(str(title or "").split())
    if len(clean_title) < TITLE_MIN_LENGTH:
        outcome.add(
            "LISTING_TITLE_TOO_SHORT",
            "title",
            f"卡片标题 {clean_title!r} 过短，不像是商品（可能是广告位）",
            fatal=True,
        )
    promo_marker = _looks_like_promo_title(clean_title)
    if promo_marker:
        outcome.add(
            "LISTING_PROMO_CARD",
            "title",
            f"卡片标题含广告标记 {promo_marker!r}",
            fatal=True,
        )
    match = re.search(r"/dp/[^/]+/([A-Za-z0-9_\-]+)", source_url or "")
    if not match:
        outcome.add(
            "LISTING_PRODUCT_ID_MISSING",
            "source_url",
            f"{source_url!r} 里取不到商品 ID",
            fatal=True,
        )
    return outcome


# -- run-level anomaly guard ----------------------------------------------


class PriceDistributionGuard:
    """Watch the price shape of one run, not one record.

    A run where every product carries the same price, or where the price
    is missing for most products, means the parser collapsed onto a shared
    container. Individually each record may look fine (a plausible number
    in a plausible band), so only the distribution reveals the breakage.
    This is the "all prices came back as 0 and nothing raised" case.
    """

    def __init__(self, *, min_samples: int = 3, missing_ratio: float = 0.5):
        self.min_samples = min_samples
        self.missing_ratio = missing_ratio
        self._prices: list[Decimal | None] = []

    def observe(self, payload: dict) -> None:
        self._prices.append(parse_price((payload or {}).get("current_price")))

    @property
    def samples(self) -> int:
        return len(self._prices)

    def verdict(self) -> dict | None:
        """Return ``{"code", "level", "message"}`` when the run looks broken."""

        total = len(self._prices)
        if total < self.min_samples:
            return None
        missing = sum(1 for price in self._prices if price is None or price <= 0)
        if missing / total >= self.missing_ratio:
            return {
                "code": "PRICE_ANOMALY_MISSING",
                "level": "ERROR",
                "message": (
                    f"{missing}/{total} 个商品拿不到可用价格。价格选择器很可能在页面"
                    "改版后失效，请先重放已归档的原始响应再采信本轮数据。"
                ),
            }
        valid = [price for price in self._prices if price is not None and price > 0]
        if len(valid) >= self.min_samples and len(set(valid)) == 1:
            return {
                "code": "PRICE_ANOMALY_UNIFORM",
                "level": "WARNING",
                "message": (
                    f"{len(valid)} 个有价格的商品全部是同一个价（{valid[0]}）。"
                    "通常说明选择器读到的是公共容器的价格，而不是各商品自己的价格。"
                ),
            }
        return None
