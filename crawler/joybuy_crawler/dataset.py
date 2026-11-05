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
import re
from pathlib import Path

from joybuy_crawler.image_variants import resolve_highest_resolution


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


def save_product(
    root: Path,
    *,
    breadcrumb_names: list[str],
    payload: dict,
    resolve_image=resolve_highest_resolution,
) -> dict:
    """Write one product folder; returns the index-line mapping.

    ``resolve_image`` is injectable for tests. Image download failures are
    recorded on the returned mapping instead of aborting the crawl — the
    JSON fields stay complete even when a CDN object is unavailable.
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
    urls = payload.get("image_urls") or []
    main_urls, detail_urls = (urls[:1], urls[1:]) if urls else ([], [])
    detail_urls += payload.get("detail_image_urls") or []
    for group, group_urls in (("main", main_urls), ("detail", detail_urls)):
        for position, url in enumerate(group_urls, start=1):
            try:
                _resolved_url, image_bytes = resolve_image(url)
            except Exception as exc:  # noqa: BLE001 - one bad CDN object must not stop the run
                image_files[f"{group}_errors"] = image_files.get(
                    f"{group}_errors", []
                ) + [{"url": url, "error": str(exc)}]
                continue
            suffix = ".webp" if ".webp" in url else ".jpg"
            target = product_dir / "images" / group / f"{position:02d}{suffix}"
            target.write_bytes(image_bytes)
            image_files[group].append(str(target.relative_to(product_dir)))

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
        "title": payload.get("title", ""),
        "payload_sha256": fingerprint,
        "captured_at": captured_at.isoformat(),
        "changed": changed,
        "breadcrumbs": [
            crumb.get("name", "")
            for crumb in (payload.get("joybuy", {}).get("breadcrumbs") or [])
        ],
    }
    # One index per top-level category folder. Unchanged products keep
    # their earlier line instead of appending a duplicate.
    category_dir = category_folder(root, breadcrumb_names)
    index_path = category_dir / "dataset_index.jsonl"
    if changed or not previous:
        with open(index_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(index_line, ensure_ascii=False) + "\n")
    index_line["index_path"] = str(index_path)
    return index_line
