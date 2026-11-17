from django.conf import settings
from django.http import FileResponse, Http404
from django.views.static import serve as static_serve

from media.models import MediaAsset, MediaVariant
from media.storage import media_url, resolve_media_path


def serve_media_file(request, path):
    """Development-only file server; production Nginx serves ``/media/``."""

    if not settings.DEBUG:
        raise Http404()
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
