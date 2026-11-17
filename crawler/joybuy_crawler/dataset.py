"""Local crawl dataset writer (user requirement #2).

Every crawled product lands on disk in a per-category folder tree that
maps 1:1 to the crawled data:

    var/crawl_exports/{job.public_id}-{job.name}/
      {一级类目slug}/{二级类目slug}/{productId}/
        product.json            # full payload, Joybuy-native fields
        meta.json               # capture history: hash, first/last seen, changed
        images/main/…           # highest-resolution main image
        images/detail/…         # gallery + description images
      {一级类目slug}/dataset_index.jsonl   # one line per changed product

The content-addressed media library (``var/media``) that serves the
storefront is untouched — this dataset is the crawler's own raw archive.
``dataset_index.jsonl`` is the join table between JSON fields and files.

Incremental rule (2026-11-05): ``product.json`` and the images are always
refreshed — the raw snapshot is never lost, because a bad parse can only
be debugged against the HTML/JSON that was actually served. The index,
however, only gains a line when the payload fingerprint changed, so a
daily re-crawl of an unchanged catalogue does not bloat the index with
identical rows.
"""

import hashlib
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from joybuy_crawler.image_variants import resolve_highest_resolution

#: 商品媒体（主图/详情图/视频）的并发下载数。CDN 单张约 1.5–2s，串行下载
#: 15 张就要 25–30s，是正式爬虫比调试脚本慢的主因（2026-11-10）。
MEDIA_DOWNLOAD_WORKERS = int(os.getenv("CRAWL_MEDIA_DOWNLOAD_WORKERS", "6"))

#: 商品视频下载所用 UA：joy-sourcing CDN 对爬虫 UA 直接 403（2026-11-05 实测）。
_VIDEO_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)


def download_video(url: str, *, timeout: int = 120) -> bytes:
    """下载画廊视频（浏览器 UA + 重试）。

    视频可达数 MB（蒸锅 23s / 7.1MB 实测），所以超时放宽到 120s；
    重试与退避复用 ``core.http_client.fetch_url`` 的策略。
    """

    from joybuy_crawler.core.http_client import fetch_url

    result = fetch_url(
        url,
        headers={"User-Agent": _VIDEO_UA, "Accept": "*/*"},
        timeout_seconds=timeout,
        max_attempts=3,
    )
    if result.status_code != 200 or not result.body:
        raise RuntimeError(f"HTTP {result.status_code}")
    return result.body


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", (name or "").lower()).strip("-")
    return slug[:80] or "uncategorized"


def payload_fingerprint(payload: dict) -> str:
    """Stable hash of the parsed payload (key order and spacing independent)."""

    canonical = json.dumps(
        payload or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _read_meta(meta_path: Path) -> dict:
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def dataset_root(job_public_id: str, job_name: str) -> Path:
    from django.conf import settings

    configured = str(getattr(settings, "CRAWL_EXPORT_ROOT", "") or "")
    root = (
        Path(configured)
        if configured
        else Path(settings.BASE_DIR).parent / "var" / "crawl_exports"
    )
    folder = f"{job_public_id[:8]}-{_slugify(job_name)}"
    return root / folder


def category_folder(root: Path, breadcrumb_names: list[str]) -> Path:
    """{一级}/{二级}/ under the job root; deeper levels are flattened."""

    parts = [_slugify(name) for name in (breadcrumb_names or [])[:2]] or [
        "uncategorized"
    ]
    return root.joinpath(*parts)


def _download_many(urls: list[str], resolve) -> list[tuple[bytes | None, str | None]]:
    """并发下载一组 URL，按输入顺序返回 ``(bytes, error)``。

    ``resolve`` 可能是图片的 ``(url, bytes)`` 也可能是视频的 ``bytes``，
    这里统一取字节；单个失败只记录错误，不影响其它 URL（与原串行行为一致）。
    """

    if not urls:
        return []

    def _one(url: str) -> tuple[bytes | None, str | None]:
        try:
            downloaded = resolve(url)
        except Exception as exc:  # noqa: BLE001 - 单张/单个失败不终止整批
            return None, str(exc)
        if isinstance(downloaded, tuple):
            downloaded = downloaded[-1]
        return downloaded, None

    workers = max(1, min(MEDIA_DOWNLOAD_WORKERS, len(urls)))
    if workers == 1:
        return [_one(url) for url in urls]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        # ``map`` 按提交顺序返回，图片/视频文件编号与源站顺序保持一致。
        return list(pool.map(_one, urls))


def save_product(
    root: Path,
    *,
    breadcrumb_names: list[str],
    payload: dict,
    resolve_image=resolve_highest_resolution,
    resolve_video=download_video,
) -> dict:
    """Write one product folder; returns the index-line mapping.

    ``resolve_image`` / ``resolve_video`` are injectable for tests. Download
    failures are recorded on the returned mapping instead of aborting the
    crawl — the JSON fields stay complete even when a CDN object is
    unavailable.
    """

    source_id = str(payload.get("source_id") or "unknown")
    # Keep the raw source id in the folder name (it is the mapping key).
    product_dir = category_folder(root, breadcrumb_names) / re.sub(
        r"[^A-Za-z0-9_.-]+", "_", source_id
    )
    (product_dir / "images" / "main").mkdir(parents=True, exist_ok=True)
    (product_dir / "images" / "detail").mkdir(parents=True, exist_ok=True)

    # Incremental bookkeeping: compare against the previous capture before
    # overwriting anything, so "did this product actually change?" has an
    # answer that does not depend on re-reading the database.
    from django.utils import timezone

    meta_path = product_dir / "meta.json"
    previous = _read_meta(meta_path)
    fingerprint = payload_fingerprint(payload)
    captured_at = timezone.now()
    changed = previous.get("payload_sha256") != fingerprint

    (product_dir / "product.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    image_files = {"main": [], "detail": []}
    image_paths_by_url: dict[str, str] = {}
    urls = payload.get("image_urls") or []
    main_urls, detail_urls = (urls[:1], urls[1:]) if urls else ([], [])
    detail_urls += payload.get("detail_image_urls") or []
    image_tasks: list[tuple[str, int, str]] = []
    for group, group_urls in (("main", main_urls), ("detail", detail_urls)):
        for position, url in enumerate(group_urls, start=1):
            image_tasks.append((group, position, url))
    downloads = _download_many(
        [url for _group, _position, url in image_tasks], resolve_image
    )
    for (group, position, url), (image_bytes, error) in zip(image_tasks, downloads):
        if error is not None:
            image_files[f"{group}_errors"] = image_files.get(f"{group}_errors", []) + [
                {"url": url, "error": error}
            ]
            continue
        suffix = ".webp" if ".webp" in url else ".jpg"
        target = product_dir / "images" / group / f"{position:02d}{suffix}"
        target.write_bytes(image_bytes)
        image_files[group].append(str(target.relative_to(product_dir)))
        image_paths_by_url[url] = str(target.resolve())

    # 画廊视频（2026-11-09）：保存到 <商品>/videos/01.mp4，失败只记账。
    # 只落 dataset 与 payload，不进 var/media 媒体库（详见 docs/05 §9.2）。
    video_files: list[str] = []
    video_errors: list[dict] = []
    video_paths_by_url: dict[str, str] = {}
    video_urls = []
    for position, video in enumerate(payload.get("videos") or [], start=1):
        video_url = str((video or {}).get("url") or "").strip()
        if video_url:
            video_urls.append((position, video_url))
    video_downloads = _download_many(
        [url for _position, url in video_urls], resolve_video
    )
    for (position, video_url), (video_bytes, error) in zip(video_urls, video_downloads):
        if error is not None:
            video_errors.append({"url": video_url, "error": error})
            continue
        target = product_dir / "videos" / f"{position:02d}.mp4"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(video_bytes)
        video_files.append(str(target.relative_to(product_dir)))
        video_paths_by_url[video_url] = str(target.resolve())

    meta_path.write_text(
        json.dumps(
            {
                "source_id": source_id,
                "payload_sha256": fingerprint,
                "first_captured_at": previous.get("first_captured_at")
                or captured_at.isoformat(),
                "last_captured_at": captured_at.isoformat(),
                "capture_count": int(previous.get("capture_count") or 0) + 1,
                "changed": changed,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    index_line = {
        "source_id": source_id,
        "product_dir": str(product_dir.relative_to(root)),
        "product_json": str((product_dir / "product.json").relative_to(root)),
        "images": image_files,
        "videos": video_files,
        "title": payload.get("title", ""),
        "payload_sha256": fingerprint,
        "captured_at": captured_at.isoformat(),
        "changed": changed,
        "breadcrumbs": [
            crumb.get("name", "")
            for crumb in (payload.get("joybuy", {}).get("breadcrumbs") or [])
        ],
    }
    if video_errors:
        index_line["video_errors"] = video_errors
    # One index per top-level category folder. Unchanged products keep
    # their earlier line instead of appending a duplicate.
    category_dir = category_folder(root, breadcrumb_names)
    index_path = category_dir / "dataset_index.jsonl"
    if changed or not previous:
        with open(index_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(index_line, ensure_ascii=False) + "\n")
    index_line["index_path"] = str(index_path)
    # 本次抓取已落盘的媒体文件（URL → 绝对路径）。导入媒体库时直接复用这些
    # 文件，不再对同一张图/同一个视频发起第二次下载（2026-11-10 提速）。
    # 只放在返回值里、不写进 dataset_index.jsonl，避免索引被本地路径撑大。
    gallery_urls = set(urls)
    index_line["local_media"] = {
        "gallery": {
            url: path for url, path in image_paths_by_url.items() if url in gallery_urls
        },
        "videos": video_paths_by_url,
    }
    return index_line
