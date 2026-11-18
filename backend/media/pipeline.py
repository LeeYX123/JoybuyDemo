"""Media download and processing pipeline (WP-18).

Server side of the flow the crawler feeds:

1. ``strip_exif`` removes metadata from downloaded images before storage;
2. ``process_media_bytes`` stores content-addressed originals (global SHA-256
   dedup), generates WebP/AVIF variants for images, an MP4 cover frame for
   videos via FFmpeg, and links the asset to its business object;
3. ``retry_failed_media`` reprocesses failed assets so transient problems
   (decoder hiccups, missing FFmpeg) are recoverable without re-downloading.

Every produced URL goes through ``media_url`` and therefore points at the
local ``/media/`` tree; source CDNs are never referenced by the storefront.
"""

import hashlib
import io
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from media.domain import MediaContentInvalid
from media.models import MediaAsset, MediaVariant
from media.storage import (
    KIND_PATH_PREFIX,
    read_stored_bytes,
    resolve_media_path,
    s3_enabled,
    store_bytes,
    store_file_bytes,
)
from media.variants import ensure_image_variants, link_asset_to_object

EXIF_STRIP_MIMES = ("image/jpeg", "image/tiff")
FFMPEG_TIMEOUT_SECONDS = 60


def strip_exif(data: bytes, mime_type: str) -> bytes:
    """Remove EXIF metadata from an image, keeping pixels and format.

    Non-image payloads and formats without EXIF come back unchanged.
    """

    normalized = (mime_type or "").strip().lower()
    if normalized not in EXIF_STRIP_MIMES:
        return data
    try:
        with Image.open(io.BytesIO(data)) as image:
            if not image.getexif():
                return data
            clean = Image.new(image.mode, image.size)
            clean.putdata(list(image.getdata()))
            buffer = io.BytesIO()
            clean.save(buffer, format="JPEG", quality=95)
            return buffer.getvalue()
    except Exception as exc:
        raise MediaContentInvalid("EXIF stripping failed for the provided image.") from exc


def generate_video_cover(asset: MediaAsset, *, timeout_seconds: int = FFMPEG_TIMEOUT_SECONDS):
    """Extract a cover frame from a stored video asset using FFmpeg.

    Returns the cover ``MediaVariant`` or ``None`` when FFmpeg is not
    installed; the caller decides whether that is acceptable. FFmpeg needs a
    real input file, so in S3 mode the object bytes are staged into the
    working directory first; the cover is written through the storage backend.
    """

    if asset.mime_type != "video/mp4":
        raise MediaContentInvalid("Video covers require a stored video/mp4 asset.")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return None
    with tempfile.TemporaryDirectory(prefix="joybuy-cover-") as tmp_dir:
        if s3_enabled():
            source_path = Path(tmp_dir) / "source.mp4"
            source_path.write_bytes(read_stored_bytes(asset.relative_path))
        else:
            source_path = resolve_media_path(asset.relative_path)
        output_path = Path(tmp_dir) / "cover.jpg"
        completed = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(source_path),
                "-frames:v",
                "1",
                "-q:v",
                "3",
                str(output_path),
            ],
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        if completed.returncode != 0 or not output_path.exists():
            asset.process_status = MediaAsset.ProcessStatus.FAILED
            asset.error_message = "FFmpeg could not extract a cover frame."
            asset.save(update_fields=["process_status", "error_message", "updated_at"])
            raise MediaContentInvalid("FFmpeg could not extract a cover frame.")
        payload = output_path.read_bytes()

    digest = hashlib.sha256(payload).hexdigest()
    prefix = KIND_PATH_PREFIX[asset.kind]
    relative_path = f"{prefix}/derived/cover/{digest[:2]}/{digest[2:4]}/{digest}.jpg"
    store_file_bytes(relative_path, payload, content_type="image/jpeg")
    variant, _ = MediaVariant.objects.update_or_create(
        asset=asset,
        preset="cover",
        format=MediaVariant.Format.JPEG,
        defaults={
            "relative_path": relative_path,
            "byte_size": len(payload),
            "status": MediaVariant.Status.READY,
            "error_message": "",
        },
    )
    return variant


def process_media_bytes(
    data: bytes,
    *,
    kind: str,
    mime_type: str,
    source_url: str = "",
    target=None,
    role: str = "",
    observed_at=None,
) -> tuple[MediaAsset, bool]:
    """EXIF-clean, store, process and (optionally) link one downloaded payload.

    A failing processing step never loses the download: the asset stays
    PENDING so ``retry_failed_media`` can pick it up later.
    """

    cleaned = strip_exif(data, mime_type)
    asset, created = store_bytes(
        cleaned,
        kind=kind,
        mime_type=mime_type,
        source_url=source_url,
        observed_at=observed_at,
    )
    try:
        if asset.mime_type.startswith("image/"):
            ensure_image_variants(asset)
        elif asset.mime_type == "video/mp4":
            generate_video_cover(asset)
            asset.process_status = MediaAsset.ProcessStatus.PROCESSED
            asset.save(update_fields=["process_status", "updated_at"])
        else:
            asset.process_status = MediaAsset.ProcessStatus.SKIPPED
            asset.save(update_fields=["process_status", "updated_at"])
    except MediaContentInvalid:
        pass
    if target is not None and role:
        link_asset_to_object(asset, target, role=role)
    return asset, created


def retry_failed_media(*, limit: int = 100) -> dict:
    """Reprocess failed or pending assets; files are already local.

    Returns counts so the orchestrator (WP-19) can report progress.
    """

    candidates = MediaAsset.objects.filter(
        process_status__in=[
            MediaAsset.ProcessStatus.FAILED,
            MediaAsset.ProcessStatus.PENDING,
        ]
    ).order_by("updated_at")[:limit]
    processed = 0
    still_failed = 0
    for asset in candidates:
        try:
            if asset.mime_type.startswith("image/"):
                ensure_image_variants(asset)
            elif asset.mime_type == "video/mp4":
                generate_video_cover(asset)
                asset.process_status = MediaAsset.ProcessStatus.PROCESSED
                asset.save(update_fields=["process_status", "updated_at"])
            else:
                continue
            processed += 1
        except MediaContentInvalid:
            still_failed += 1
    return {"processed": processed, "still_failed": still_failed}
