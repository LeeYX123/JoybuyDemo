import logging
import os

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse, HttpResponseRedirect
from django.views.static import serve as static_serve

from media.domain import MediaPathInvalid
from media.models import MediaAsset, MediaVariant
from media.storage import media_url, resolve_media_path, s3_enabled, s3_public_url

logger = logging.getLogger("media.fallback")

# Inline SVG keeps the backend self-contained (no dependency on a storefront
# file layout or a deployed static asset) and lets one placeholder answer every
# missing extension (.jpg/.png/.webp/...) with a renderable image.
PLACEHOLDER_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 360" role="img" '
    'aria-label="Image unavailable">'
    '<rect width="360" height="360" fill="#f5f6f7"/>'
    '<rect x="0.5" y="0.5" width="359" height="359" fill="none" stroke="#d9dee5"/>'
    '<g fill="none" stroke="#b9c1cb" stroke-width="10" stroke-linecap="round" '
    'stroke-linejoin="round">'
    '<rect x="90" y="90" width="180" height="180" rx="16"/>'
    '<circle cx="150" cy="150" r="18"/>'
    '<path d="M102 246 L162 186 L198 222 L232 188 L258 214"/>'
    "</g></svg>"
)

PLACEHOLDER_CACHE_CONTROL = "public, max-age=3600"


def placeholder_image_response() -> HttpResponse:
    """200 + SVG placeholder for a missing local media file (cacheable)."""

    response = HttpResponse(PLACEHOLDER_SVG, content_type="image/svg+xml")
    response["Cache-Control"] = PLACEHOLDER_CACHE_CONTROL
    return response


def serve_media_file(request, path):
    """Development-only file server; production Nginx serves ``/media/``.

    In S3 mode new assets have no local copy, so missing files redirect to the
    anonymous bucket URL (the bucket allows public reads under the media
    prefix); a missing object must stay visible there, so no placeholder is
    substituted.

    In local mode a missing file means the historical import never downloaded
    the asset (S3-era data + partial crawls). Returning 404 produced broken
    product images across search / cart / PDP, so those paths get a cacheable
    SVG placeholder (HTTP 200) instead. Existence checks are filesystem-only
    (no DB queries) and paths that escape MEDIA_ROOT still raise 404.
    """

    if not settings.DEBUG:
        raise Http404()
    if s3_enabled():
        try:
            exists = resolve_media_path(path).is_file()
        except MediaPathInvalid:
            raise Http404() from None
        if not exists:
            return HttpResponseRedirect(s3_public_url(path))
        return static_serve(request, path, document_root=str(settings.MEDIA_ROOT))

    try:
        full_path = resolve_media_path(path)
    except MediaPathInvalid:
        raise Http404() from None
    if not os.path.isfile(full_path):
        if os.path.isdir(full_path):
            # A directory is a bad URL, not a missing asset; keep it a 404 so
            # misconfigured prefixes do not silently render placeholders.
            raise Http404()
        # Debug level on purpose: a whole-site backfill can emit thousands of
        # these; raise DJANGO_LOG_LEVEL to DEBUG to survey the missing scale.
        logger.debug(
            "media.placeholder_fallback",
            extra={"event": "media.placeholder_fallback", "path": path},
        )
        return placeholder_image_response()
    return static_serve(request, path, document_root=str(settings.MEDIA_ROOT))


def asset_urls(asset: MediaAsset) -> dict:
    """Public URL payload for an asset and its ready variants."""

    payload = {"sha256": asset.sha256, "url": media_url(asset.relative_path), "variants": {}}
    ready = MediaVariant.objects.filter(asset=asset, status=MediaVariant.Status.READY)
    for variant in ready:
        payload["variants"].setdefault(variant.preset, {})[variant.format] = media_url(
            variant.relative_path
        )
    return payload


def open_media_file(relative_path: str):
    """Resolve and open a stored file for streaming; 404-equivalent on escape."""

    full_path = resolve_media_path(relative_path)
    if not full_path.is_file():
        raise Http404()
    return FileResponse(full_path.open("rb"))
