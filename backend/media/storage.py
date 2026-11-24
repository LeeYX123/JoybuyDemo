import hashlib
import io
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

_s3_client = None


def s3_enabled() -> bool:
    """True when media bytes live in S3 instead of the local ``MEDIA_ROOT``."""

    return settings.MEDIA_BACKEND == "s3"


def get_s3_client():
    """Lazy boto3 S3 client singleton; credentials come from the default chain.

    Kept as a module-level function so tests can monkeypatch it with a fake
    client. No credentials are ever hardcoded; the bucket must allow anonymous
    reads for ``MEDIA_S3_PREFIX*`` (public access is managed at the provider).

    When ``MEDIA_S3_ENDPOINT`` is set (S3-compatible providers such as
    DigitalOcean Spaces) the client targets that endpoint with path-style
    addressing; otherwise the AWS default endpoint/virtual-host style applies.
    """

    global _s3_client
    if _s3_client is None:
        import boto3
        from botocore.config import Config

        endpoint = settings.MEDIA_S3_ENDPOINT
        if endpoint:
            _s3_client = boto3.client(
                "s3",
                endpoint_url=endpoint,
                region_name=settings.MEDIA_S3_REGION,
                config=Config(s3={"addressing_style": "path"}),
            )
        else:
            _s3_client = boto3.client("s3", region_name=settings.MEDIA_S3_REGION)
    return _s3_client


def reset_s3_client() -> None:
    """Drop the cached client (used after tests monkeypatch it)."""

    global _s3_client
    _s3_client = None


def s3_key(relative_path: str) -> str:
    """Object key for a media-relative path inside the bucket."""

    clean = posixpath.normpath(str(relative_path).replace("\\", "/"))
    return f"{settings.MEDIA_S3_PREFIX}{clean}"


def s3_public_url(relative_path: str) -> str:
    """Anonymous bucket URL for a media-relative path (nginx proxies this too).

    Endpoint mode (MEDIA_S3_ENDPOINT set, e.g. DigitalOcean Spaces) builds a
    path-style URL; empty endpoint keeps the AWS virtual-host style.
    """

    endpoint = settings.MEDIA_S3_ENDPOINT
    if endpoint:
        return f"{endpoint}/{settings.MEDIA_S3_BUCKET}/{s3_key(relative_path)}"
    return (
        f"https://{settings.MEDIA_S3_BUCKET}.s3.{settings.MEDIA_S3_REGION}"
        f".amazonaws.com/{s3_key(relative_path)}"
    )


def store_file_bytes(relative_path: str, data: bytes, *, content_type: str = "") -> None:
    """Persist raw bytes at ``relative_path`` in the active backend.

    S3 mode uploads one object and keeps no local copy; local mode writes via a
    temp file + atomic replace exactly as before.
    """

    if s3_enabled():
        get_s3_client().put_object(
            Bucket=settings.MEDIA_S3_BUCKET,
            Key=s3_key(relative_path),
            Body=data,
            ContentType=content_type or "application/octet-stream",
        )
        return
    full_path = resolve_media_path(relative_path)
    full_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = full_path.with_name(f"{full_path.name}.tmp-{os.getpid()}")
    tmp_path.write_bytes(data)
    os.replace(tmp_path, full_path)


def read_stored_bytes(relative_path: str) -> bytes:
    """Read back stored bytes (variant generation, covers, dimension checks).

    Works in both backends so assets stored before a backend switch stay
    processable: S3 mode always fetches from the bucket, local mode from disk.
    """

    if s3_enabled():
        response = get_s3_client().get_object(
            Bucket=settings.MEDIA_S3_BUCKET, Key=s3_key(relative_path)
        )
        return response["Body"].read()
    return resolve_media_path(relative_path).read_bytes()


def stored_file_exists(relative_path: str) -> bool:
    """Backend-aware existence check for a stored media object."""

    if s3_enabled():
        from botocore.exceptions import ClientError

        try:
            get_s3_client().head_object(Bucket=settings.MEDIA_S3_BUCKET, Key=s3_key(relative_path))
        except ClientError:
            return False
        return True
    try:
        return resolve_media_path(relative_path).is_file()
    except MediaPathInvalid:
        return False


def _object_exists(relative_path: str) -> bool:
    """Existence of the stored **bytes** in the active backend.

    Alias of :func:`stored_file_exists`, kept as a private name to make the
    dedup contract explicit: a ``MediaAsset`` row is metadata only, and a row
    surviving says nothing about the object (S3-era rows have no local file).
    """

    return stored_file_exists(relative_path)


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


def _detect_image_dimensions(data: bytes) -> tuple[int | None, int | None]:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
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
    physical location is ``<MEDIA_ROOT>/<kind prefix>/original/<aa>/<bb>/<sha256>.<ext>``
    on the local backend, or the same relative path as an object key under
    ``MEDIA_S3_PREFIX`` in the S3 bucket. A sha256 hit in the database refreshes
    ``last_seen_at`` and **verifies the physical object still exists in the
    active backend**, re-writing it from ``data`` when it is missing: dedup is
    keyed on the DB row, but the bytes can be gone (rows created while
    ``MEDIA_BACKEND=s3`` have no local file after switching back to local).
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
        # Backfill before touching metadata: a dedup hit must never leave the
        # asset pointing at bytes that the active backend does not have.
        if not _object_exists(existing.relative_path):
            store_file_bytes(
                existing.relative_path,
                data,
                content_type=normalized_mime or existing.mime_type,
            )
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
    store_file_bytes(relative_path, data, content_type=normalized_mime)

    width = height = None
    if normalized_mime.startswith(IMAGE_MIME_PREFIX):
        # Metadata extraction is best-effort: undecodable bytes stay stored so
        # the WP-18 pipeline can retry or flag them instead of losing content.
        # Runs from the in-memory payload, so it works without a local file.
        try:
            width, height = _detect_image_dimensions(data)
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
    """Remove the stored object behind an asset; metadata rows are kept."""

    if s3_enabled():
        from botocore.exceptions import ClientError

        try:
            get_s3_client().delete_object(
                Bucket=settings.MEDIA_S3_BUCKET, Key=s3_key(asset.relative_path)
            )
        except ClientError:
            return
        return
    full_path = resolve_media_path(asset.relative_path)
    if full_path.exists():
        full_path.unlink()
