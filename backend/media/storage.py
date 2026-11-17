import hashlib
import os
import posixpath
from pathlib import Path

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from media.domain import MediaContentInvalid, MediaKindInvalid, MediaPathInvalid
from media.models import MediaAsset

KIND_PATH_PREFIX = {
    MediaAsset.Kind.PRODUCT: "products",
    MediaAsset.Kind.REVIEW: "reviews",
    MediaAsset.Kind.CMS: "cms",
    MediaAsset.Kind.MERCHANT: "merchants",
    MediaAsset.Kind.ICON: "icons",
    MediaAsset.Kind.FONT: "fonts",
    MediaAsset.Kind.VIDEO: "videos",
}

IMAGE_MIME_PREFIX = "image/"

MIME_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/avif": ".avif",
    "image/gif": ".gif",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "font/ttf": ".ttf",
    "font/otf": ".otf",
    "font/woff": ".woff",
    "font/woff2": ".woff2",
    "application/octet-stream": ".bin",
}


def media_url(relative_path: str) -> str:
    """Build the public URL for a stored file; Nginx serves ``/media/``."""

    clean = posixpath.normpath(str(relative_path).replace("\\", "/"))
    if clean.startswith("..") or clean.startswith("/"):
        raise MediaPathInvalid("relative_path must stay inside the media root.")
    return f"{settings.MEDIA_URL.rstrip('/')}/{clean}"


def resolve_media_path(relative_path: str) -> Path:
    """Resolve a stored relative path under MEDIA_ROOT, refusing escapes."""

    clean = posixpath.normpath(str(relative_path).replace("\\", "/"))
    if not clean or clean.startswith("..") or clean.startswith("/") or ":" in clean:
        raise MediaPathInvalid("relative_path must be a relative path inside the media root.")
    root = Path(settings.MEDIA_ROOT).resolve()
    full = (root / clean).resolve()
    if root != full and root not in full.parents:
        raise MediaPathInvalid("relative_path escapes the media root.")
    return full


def _detect_image_dimensions(full_path: Path) -> tuple[int | None, int | None]:
    try:
        from PIL import Image

        with Image.open(full_path) as image:
            return image.width, image.height
    except ImportError:
        return None, None
    except Exception as exc:
        raise MediaContentInvalid("The stored bytes are not a decodable image.") from exc


def store_bytes(
    data: bytes,
    *,
    kind: str,
    mime_type: str = "",
    source_url: str = "",
    observed_at=None,
) -> tuple[MediaAsset, bool]:
    """Content-addressed storage: identical bytes are stored exactly once.

    Returns ``(asset, created)``. Only relative paths are persisted; the
    physical location is ``<MEDIA_ROOT>/<kind prefix>/original/<aa>/<bb>/<sha256>.<ext>``.
    """

    if kind not in KIND_PATH_PREFIX:
        raise MediaKindInvalid(f"Unknown media kind: {kind}.")
    if not data:
        raise MediaContentInvalid("Cannot store empty media content.")
    normalized_mime = (mime_type or "").strip().lower()
    observed_at = observed_at or timezone.now()
    digest = hashlib.sha256(data).hexdigest()

    existing = MediaAsset.objects.filter(sha256=digest).first()
    if existing:
        fields = ["last_seen_at", "updated_at"]
        existing.last_seen_at = observed_at
        if source_url and source_url != existing.source_url:
            existing.source_url = source_url
            fields.append("source_url")
        existing.save(update_fields=fields)
        return existing, False

    prefix = KIND_PATH_PREFIX[kind]
    extension = MIME_EXTENSIONS.get(normalized_mime, "")
    relative_path = f"{prefix}/original/{digest[:2]}/{digest[2:4]}/{digest}{extension}"
    full_path = resolve_media_path(relative_path)
    full_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = full_path.with_name(f"{full_path.name}.tmp-{os.getpid()}")
    tmp_path.write_bytes(data)
    os.replace(tmp_path, full_path)

    width = height = None
    if normalized_mime.startswith(IMAGE_MIME_PREFIX):
        # Metadata extraction is best-effort: undecodable bytes stay stored so
        # the WP-18 pipeline can retry or flag them instead of losing content.
        try:
            width, height = _detect_image_dimensions(full_path)
        except MediaContentInvalid:
            width, height = None, None

    try:
        with transaction.atomic():
            asset = MediaAsset.objects.create(
                sha256=digest,
                kind=kind,
                relative_path=relative_path,
                mime_type=normalized_mime,
                extension=extension.lstrip("."),
                byte_size=len(data),
                width=width,
                height=height,
                source_url=source_url.strip(),
                first_seen_at=observed_at,
                last_seen_at=observed_at,
                download_status=MediaAsset.DownloadStatus.DOWNLOADED,
                process_status=MediaAsset.ProcessStatus.PENDING,
            )
            return asset, True
    except IntegrityError:
        existing = MediaAsset.objects.get(sha256=digest)
        existing.last_seen_at = observed_at
        existing.save(update_fields=["last_seen_at", "updated_at"])
        return existing, False


def delete_asset_file(asset: MediaAsset) -> None:
    """Remove the physical file behind an asset; metadata rows are kept."""

    full_path = resolve_media_path(asset.relative_path)
    if full_path.exists():
        full_path.unlink()
