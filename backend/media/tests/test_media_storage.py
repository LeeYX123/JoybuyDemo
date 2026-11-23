import io
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings
from PIL import Image

from media.domain import MediaContentInvalid, MediaKindInvalid, MediaPathInvalid
from media.models import MediaAsset, MediaUsage, MediaVariant
from media.storage import delete_asset_file, media_url, resolve_media_path, store_bytes
from media.variants import IMAGE_VARIANT_PRESETS, ensure_image_variants, link_asset_to_object
from offers.models import Currency


def make_png(width=800, height=600, color=(10, 120, 240)) -> bytes:
    image = Image.new("RGB", (width, height), color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class IsolatedMediaRootMixin:
    """Run each test against a throwaway media root so the shared var/media
    development tree is never polluted by test fixtures."""

    def setUp(self):
        super().setUp()
        self._media_root = tempfile.TemporaryDirectory()
        override = override_settings(MEDIA_ROOT=self._media_root.name)
        override.enable()
        self.addCleanup(override.disable)
        self.addCleanup(self._media_root.cleanup)


class MediaStorageTests(IsolatedMediaRootMixin, TestCase):
    def store_sample(
        self,
        *,
        kind=MediaAsset.Kind.PRODUCT,
        source_url="",
        color=(10, 120, 240),
        width=800,
        height=600,
    ):
        payload = make_png(width=width, height=height, color=color)
        return store_bytes(payload, kind=kind, mime_type="image/png", source_url=source_url)

    def test_identical_content_is_stored_exactly_once(self):
        first, first_created = self.store_sample(source_url="https://example.test/a.png")
        second, second_created = self.store_sample(source_url="https://example.test/b.png")

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first, second)
        self.assertEqual(MediaAsset.objects.count(), 1)
        self.assertEqual(first.download_status, MediaAsset.DownloadStatus.DOWNLOADED)
        physical = Path(settings.MEDIA_ROOT) / first.relative_path
        self.assertTrue(physical.is_file())

    def test_sha_hit_rewrites_missing_physical_file(self):
        """A DB row without bytes (S3-era asset) must be re-materialized on dedup."""
        payload = make_png(color=(4, 5, 6))
        first, created = store_bytes(payload, kind=MediaAsset.Kind.PRODUCT, mime_type="image/png")
        self.assertTrue(created)
        physical = Path(settings.MEDIA_ROOT) / first.relative_path
        physical.unlink()
        self.assertFalse(physical.exists())

        again, again_created = store_bytes(
            payload, kind=MediaAsset.Kind.PRODUCT, mime_type="image/png"
        )

        self.assertFalse(again_created)
        self.assertEqual(again.pk, first.pk)
        self.assertEqual(MediaAsset.objects.count(), 1)
        self.assertEqual(physical.read_bytes(), payload)

    def test_sha_hit_does_not_rewrite_existing_file(self):
        payload = make_png(color=(7, 8, 9))
        asset, _ = store_bytes(payload, kind=MediaAsset.Kind.PRODUCT, mime_type="image/png")
        physical = Path(settings.MEDIA_ROOT) / asset.relative_path
        before = physical.stat().st_mtime_ns

        with patch("media.storage.store_file_bytes") as store_file_bytes:
            again, created = store_bytes(
                payload, kind=MediaAsset.Kind.PRODUCT, mime_type="image/png"
            )

        self.assertFalse(created)
        self.assertEqual(again.pk, asset.pk)
        store_file_bytes.assert_not_called()
        self.assertEqual(physical.stat().st_mtime_ns, before)

    def test_database_paths_are_relative_and_urls_are_local(self):
        asset, _ = self.store_sample()

        self.assertNotIn(str(Path(settings.MEDIA_ROOT)).lower(), asset.relative_path)
        self.assertNotIn(":", asset.relative_path)
        self.assertFalse(asset.relative_path.startswith("/"))
        self.assertTrue(asset.relative_path.startswith("products/original/"))
        url = media_url(asset.relative_path)
        self.assertTrue(url.startswith("/media/products/original/"))
        self.assertNotIn("http://", url)
        self.assertNotIn("https://", url)

    def test_different_content_creates_separate_assets(self):
        first, first_created = self.store_sample(color=(1, 2, 3))
        second, second_created = self.store_sample(color=(9, 9, 9))
        self.assertTrue(first_created)
        self.assertTrue(second_created)
        self.assertNotEqual(first.sha256, second.sha256)
        self.assertEqual(MediaAsset.objects.count(), 2)

    def test_image_dimensions_are_extracted_and_paths_are_sharded(self):
        asset, _ = self.store_sample(width=640, height=480)
        self.assertEqual(asset.width, 640)
        self.assertEqual(asset.height, 480)
        parts = Path(asset.relative_path).parts
        # products / original / aa / bb / file
        self.assertEqual(len(parts), 5)
        self.assertEqual(parts[2], asset.sha256[:2])
        self.assertEqual(parts[3], asset.sha256[2:4])

    def test_path_traversal_and_unknown_kinds_are_rejected(self):
        with self.assertRaises(MediaPathInvalid):
            resolve_media_path("../../etc/passwd")
        with self.assertRaises(MediaPathInvalid):
            resolve_media_path("products/../../secret.txt")
        with self.assertRaises(MediaKindInvalid):
            store_bytes(b"abc", kind="UNKNOWN", mime_type="text/plain")
        with self.assertRaises(MediaContentInvalid):
            store_bytes(b"", kind=MediaAsset.Kind.CMS, mime_type="image/png")
        with self.assertRaises(MediaPathInvalid):
            media_url("../../../etc/passwd")

    def test_delete_removes_file_but_metadata_is_kept(self):
        asset, _ = self.store_sample()
        relative_path = asset.relative_path
        delete_asset_file(asset)
        self.assertFalse((Path(settings.MEDIA_ROOT) / relative_path).exists())
        self.assertTrue(MediaAsset.objects.filter(pk=asset.pk).exists())

    def test_image_variants_are_generated_idempotently_and_never_upscale(self):
        asset, _ = self.store_sample(width=800, height=600)
        variants = ensure_image_variants(asset)

        asset.refresh_from_db()
        self.assertEqual(asset.process_status, MediaAsset.ProcessStatus.PROCESSED)
        self.assertEqual(len(variants), 6)
        by_key = {(item.preset, item.format): item for item in variants}
        self.assertEqual(by_key[("thumb", MediaVariant.Format.WEBP)].width, 320)
        self.assertEqual(by_key[("detail", MediaVariant.Format.WEBP)].width, 800)
        for (preset, _format), item in by_key.items():
            self.assertEqual(item.width, min(IMAGE_VARIANT_PRESETS[preset], 800))
            self.assertEqual(item.status, MediaVariant.Status.READY)
            physical = Path(settings.MEDIA_ROOT) / item.relative_path
            self.assertTrue(physical.is_file())
            self.assertTrue(item.relative_path.startswith(f"products/derived/{preset}/"))
            local_url = media_url(item.relative_path)
            self.assertTrue(local_url.startswith("/media/products/derived/"))

        rerun = ensure_image_variants(asset)
        self.assertEqual(MediaVariant.objects.count(), 6)
        self.assertEqual(
            {(item.preset, item.format, item.relative_path) for item in rerun},
            {(item.preset, item.format, item.relative_path) for item in variants},
        )

    def test_small_image_variants_keep_original_dimensions(self):
        asset, _ = self.store_sample(width=200, height=120)
        variants = ensure_image_variants(asset)
        for item in variants:
            self.assertEqual(item.width, 200)

    def test_corrupt_image_marks_processing_failed_without_losing_original(self):
        asset, created = store_bytes(
            b"this is not an image",
            kind=MediaAsset.Kind.PRODUCT,
            mime_type="image/png",
        )
        self.assertTrue(created)
        self.assertIsNone(asset.width)
        with self.assertRaises(MediaContentInvalid):
            ensure_image_variants(asset)
        asset.refresh_from_db()
        self.assertEqual(asset.process_status, MediaAsset.ProcessStatus.FAILED)
        self.assertTrue(
            (Path(settings.MEDIA_ROOT) / asset.relative_path).is_file(),
            "Original bytes must be preserved when processing fails.",
        )

    def test_asset_usage_links_are_idempotent(self):
        asset, _ = self.store_sample()
        currency = Currency.objects.get(code="GBP")
        first, first_created = link_asset_to_object(asset, currency, role="gallery")
        second, second_created = link_asset_to_object(asset, currency, role="gallery")

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first, second)
        self.assertEqual(MediaUsage.objects.count(), 1)
        self.assertEqual(first.target, currency)
