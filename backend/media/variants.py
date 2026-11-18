import hashlib
import io

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from PIL import Image

from media.domain import MediaContentInvalid
from media.models import MediaAsset, MediaUsage, MediaVariant
from media.storage import KIND_PATH_PREFIX, read_stored_bytes, store_file_bytes

IMAGE_VARIANT_PRESETS = {
    "thumb": 320,
    "card": 640,
    "detail": 1200,
}

IMAGE_VARIANT_FORMATS = (
    (MediaVariant.Format.WEBP, "WEBP", {"quality": 82, "method": 6}),
    (MediaVariant.Format.AVIF, "AVIF", {"quality": 60}),
)

FORMAT_EXTENSIONS = {
    MediaVariant.Format.WEBP: ".webp",
    MediaVariant.Format.AVIF: ".avif",
}

FORMAT_MIME_TYPES = {
    MediaVariant.Format.WEBP: "image/webp",
    MediaVariant.Format.AVIF: "image/avif",
}


def _render_variant(source: Image.Image, target_width: int, format_name: str, options: dict):
    scale = min(1.0, target_width / source.width)
    width = max(1, round(source.width * scale))
    height = max(1, round(source.height * scale))
    resized = source.resize((width, height), Image.LANCZOS)
    buffer = io.BytesIO()
    if resized.mode == "RGBA":
        resized.save(buffer, format_name, **options)
    else:
        resized.convert("RGB").save(buffer, format_name, **options)
    return width, height, buffer.getvalue()


def ensure_image_variants(asset: MediaAsset) -> list[MediaVariant]:
    """Generate WebP/AVIF variants for an image asset.

    Files are content-addressed like originals; re-running with unchanged
    inputs reproduces identical bytes and therefore identical rows. The
    actual video/FFmpeg pipeline is delivered with WP-18.
    """

    if not asset.mime_type.startswith("image/"):
        raise MediaContentInvalid("Image variants require an image mime type.")
    # Decode from the stored bytes (local file or S3 object), not from a path,
    # so variant generation works in both storage backends.
    payload = read_stored_bytes(asset.relative_path)

    try:
        with Image.open(io.BytesIO(payload)) as source:
            source.load()
            decoded = source.convert("RGBA") if source.mode in {"RGBA", "LA", "P"} else source
    except Exception as exc:
        asset.process_status = MediaAsset.ProcessStatus.FAILED
        asset.error_message = "Source image could not be decoded."
        asset.save(update_fields=["process_status", "error_message", "updated_at"])
        raise MediaContentInvalid("Source image could not be decoded.") from exc

    prefix = KIND_PATH_PREFIX[asset.kind]
    results = []
    failures = []
    for preset, target_width in IMAGE_VARIANT_PRESETS.items():
        for format_enum, format_name, options in IMAGE_VARIANT_FORMATS:
            try:
                width, _height, payload = _render_variant(
                    decoded, target_width, format_name, options
                )
            except Exception:
                failures.append(f"{preset}/{format_enum.value}")
                continue
            digest = hashlib.sha256(payload).hexdigest()
            extension = FORMAT_EXTENSIONS[format_enum]
            relative_path = (
                f"{prefix}/derived/{preset}/{digest[:2]}/{digest[2:4]}/{digest}{extension}"
            )
            store_file_bytes(relative_path, payload, content_type=FORMAT_MIME_TYPES[format_enum])
            results.append(
                {
                    "preset": preset,
                    "format": format_enum,
                    "width": width,
                    "relative_path": relative_path,
                    "byte_size": len(payload),
                }
            )

    with transaction.atomic():
        for item in results:
            MediaVariant.objects.update_or_create(
                asset=asset,
                preset=item["preset"],
                format=item["format"],
                defaults={
                    "width": item["width"],
                    "relative_path": item["relative_path"],
                    "byte_size": item["byte_size"],
                    "status": MediaVariant.Status.READY,
                    "error_message": "",
                },
            )
        if not results:
            asset.process_status = MediaAsset.ProcessStatus.FAILED
            asset.error_message = (
                f"Variant generation failed for: {', '.join(failures) or 'all formats'}."
            )
        else:
            asset.process_status = MediaAsset.ProcessStatus.PROCESSED
            asset.error_message = (
                f"Partial variant failures: {', '.join(failures)}." if failures else ""
            )
        asset.save(update_fields=["process_status", "error_message", "updated_at"])

    return list(MediaVariant.objects.filter(asset=asset).order_by("preset", "format"))


def link_asset_to_object(asset: MediaAsset, target, *, role: str, sort_order: int = 0):
    """Idempotently record that ``target`` uses ``asset`` under ``role``."""

    if target is None or getattr(target, "pk", None) is None:
        raise MediaContentInvalid("The usage target must be a saved model instance.")
    if not role.strip():
        raise MediaContentInvalid("A usage role is required.")
    usage, created = MediaUsage.objects.get_or_create(
        asset=asset,
        content_type=ContentType.objects.get_for_model(type(target)),
        object_id=target.pk,
        role=role.strip(),
        defaults={"sort_order": sort_order},
    )
    return usage, created
