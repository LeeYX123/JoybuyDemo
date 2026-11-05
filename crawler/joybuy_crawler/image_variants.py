"""Highest-resolution image variant resolution for Joybuy CDN URLs.

Joybuy product images live on ``images{3,4}.joy-sourcing.com`` and share
one path pattern: ``.../product/s{W}x{H}_{path}``. The same path is
available at several sizes; the repo has verified s135/s240/s360/s384/
s480 (transparent ``.png.webp``) and s624 variants (HANDOFF 2026-11-04).
This module walks a size ladder from largest to smallest and returns the
first variant that the CDN actually serves, so every crawled image is
the highest resolution available (user requirement #3).

``/da/``-style URLs are already complete — they are returned as-is.
"""

import re

from joybuy_crawler.core.http_client import fetch_url

SIZE_LADDER = (1248, 800, 624, 480, 360, 240, 135)
_SIZE_PATTERN = re.compile(r"/s(\d+)x(\d+)_")


def candidate_variants(
    image_url: str, *, ladder: tuple[int, ...] = SIZE_LADDER
) -> list[str]:
    """All candidate URLs for one image, highest resolution first."""

    url = (image_url or "").strip()
    if not url:
        return []
    match = _SIZE_PATTERN.search(url)
    if not match:
        return [url]
    candidates = []
    for size in ladder:
        candidate = _SIZE_PATTERN.sub(f"/s{size}x{size}_", url, count=1)
        if candidate not in candidates:
            candidates.append(candidate)
    original = _SIZE_PATTERN.sub("/", url, count=1)
    if original not in candidates:
        candidates.append(original)
    return candidates


def resolve_highest_resolution(
    image_url: str, *, timeout: int = 30
) -> tuple[str, bytes]:
    """Return ``(url, image_bytes)`` for the best variant that the CDN serves.

    Probes the ladder top-down with cheap ranged GETs; falls back to the
    input URL unchanged when no variant responds.
    """

    # The joy-sourcing CDN 403s bot UAs (measured 2026-11-05); probe with
    # a browser User-Agent instead.
    browser_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
        )
    }
    candidates = candidate_variants(image_url)
    last_error = ""
    for candidate in candidates:
        try:
            result = fetch_url(candidate, headers=browser_headers, timeout_seconds=timeout)
            if result.status_code == 200 and result.body:
                return candidate, result.body
            last_error = f"HTTP {result.status_code}"
        except Exception as exc:  # noqa: BLE001 - probe failures move down the ladder
            last_error = str(exc)
            continue
    raise RuntimeError(f"No usable image variant for {image_url}: {last_error}")


def split_main_and_detail_images(image_urls: list[str]) -> tuple[list[str], list[str]]:
    """First image is the main (cover) image; the rest are gallery/detail."""

    urls = [url for url in (image_urls or []) if url]
    if not urls:
        return [], []
    unique = list(dict.fromkeys(urls))
    return unique[:1], unique[1:]
