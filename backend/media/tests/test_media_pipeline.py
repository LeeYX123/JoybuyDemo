import shutil
import sys
import tempfile
import unittest
from importlib.util import find_spec
from io import BytesIO
from pathlib import Path

CRAWLER_DIR = Path(__file__).resolve().parents[3] / "crawler"
if str(CRAWLER_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWLER_DIR))

from django.test import override_settings  # noqa: E402
from PIL import Image  # noqa: E402

from crawler_control.services import start_run  # noqa: E402
from crawler_control.tests.test_crawler_control_domain import CrawlerControlTestBase  # noqa: E402
from media.domain import MediaContentInvalid  # noqa: E402
from media.models import MediaAsset, MediaUsage, MediaVariant  # noqa: E402
from media.pipeline import (  # noqa: E402
    process_media_bytes,
    retry_failed_media,
    strip_exif,
)
from media.storage import media_url  # noqa: E402
from media.tests.test_media_storage import IsolatedMediaRootMixin  # noqa: E402

SCRAPY_AVAILABLE = find_spec("scrapy") is not None
FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def make_jpeg_with_exif(width=120, height=90):
    buffer = BytesIO()
    image = Image.new("RGB", (width, height), (90, 140, 200))
    exif = image.getexif()
    exif[0x010F] = "FixtureCam"
    exif[0x0110] = "Model X100"
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def make_png_bytes(width=120, height=90, color=(10, 120, 240)) -> bytes:
    image = Image.new("RGB", (width, height), color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class ExifStrippingTests(IsolatedMediaRootMixin, unittest.TestCase):
    def test_jpeg_exif_is_removed_and_pixels_kept(self):
        original = make_jpeg_with_exif()
        self.assertTrue(Image.open(BytesIO(original)).getexif())

        cleaned = strip_exif(original, "image/jpeg")
        cleaned_image = Image.open(BytesIO(cleaned))
        self.assertFalse(cleaned_image.getexif(), "EXIF must be stripped.")
        self.assertEqual(cleaned_image.size, (120, 90))
        self.assertNotEqual(original, cleaned)

    def test_non_exif_payloads_pass_through_unchanged(self):
        png = make_png_bytes()
        self.assertEqual(strip_exif(png, "image/png"), png)
        self.assertEqual(strip_exif(b"binary-video", "video/mp4"), b"binary-video")

    def test_corrupt_jpeg_is_rejected_not_silently_stored(self):
        with self.assertRaises(MediaContentInvalid):
            strip_exif(b"not-a-jpeg", "image/jpeg")


@unittest.skipUnless(SCRAPY_AVAILABLE, "scrapy is not installed")
class MediaPipelineTests(CrawlerControlTestBase):
    """End-to-end: fixture site -> download_media -> process -> /media/ URLs."""

    def setUp(self):
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory(prefix="joybuy-media-pipe-")
        self.addCleanup(self._tmp.cleanup)
        override = override_settings(MEDIA_ROOT=self._tmp.name)
        override.enable()
        self.addCleanup(override.disable)
        self.make_account()
        self.job = self.make_job(name="Media job")
        self.run = start_run(self.job)

        from joybuy_crawler.fixtures.http_site import (
            CrawlerFixtureServer,
            make_exif_jpeg,
            make_exif_png,
            register_media_route,
            unregister_media_route,
        )

        self.site = CrawlerFixtureServer()
        self.addCleanup(self.site.stop)
        register_media_route("/media/photo.png", make_exif_png(), mime_type="image/png")
        register_media_route("/media/photo.jpg", make_exif_jpeg(), mime_type="image/jpeg")
        self.addCleanup(unregister_media_route, "/media/photo.png")
        self.addCleanup(unregister_media_route, "/media/photo.jpg")
        self.base = self.site.base_url

    def download(self, path):
        from joybuy_crawler.media_pipeline import download_media

        return download_media(f"{self.base}{path}")

    def test_downloaded_png_is_stored_deduped_variants_and_usage(self):
        payload = self.download("/media/photo.png")
        from catalog.product_services import get_or_create_spu_from_source

        spu, _ = get_or_create_spu_from_source(
            source_system="joybuy", source_id="media-spu", title="Media product"
        )
        asset, created = process_media_bytes(
            payload,
            kind="PRODUCT",
            mime_type="image/png",
            source_url=f"{self.base}/media/photo.png",
            target=spu,
            role="gallery",
        )

        self.assertTrue(created)
        asset.refresh_from_db()
        self.assertEqual(asset.process_status, MediaAsset.ProcessStatus.PROCESSED)
        self.assertEqual(asset.width, 64)
        self.assertEqual(asset.height, 48)
        self.assertTrue(asset.relative_path.startswith("products/original/"))
        self.assertEqual(MediaUsage.objects.count(), 1)
        self.assertEqual(
            MediaUsage.objects.get().asset, asset, "Usage must link the asset to the SPU."
        )
        self.assertEqual(MediaVariant.objects.filter(asset=asset).count(), 6)
        for variant in MediaVariant.objects.filter(asset=asset):
            url = media_url(variant.relative_path)
            self.assertTrue(url.startswith("/media/products/derived/"))
            self.assertFalse(url.startswith("http"), "Storefront URLs must be local.")
        self.assertTrue(
            (Path(self._tmp.name) / asset.relative_path).is_file(),
            "The original file must exist on disk.",
        )

        # Same payload again: content-addressed dedup, no new rows.
        same, created_again = process_media_bytes(
            payload,
            kind="PRODUCT",
            mime_type="image/png",
            target=spu,
            role="gallery",
        )
        self.assertFalse(created_again)
        self.assertEqual(same, asset)
        self.assertEqual(MediaAsset.objects.count(), 1)
        self.assertEqual(MediaUsage.objects.count(), 1)

    def test_downloaded_jpeg_is_exif_cleaned_before_storage(self):
        payload = self.download("/media/photo.jpg")
        from io import BytesIO

        asset, _ = process_media_bytes(
            payload,
            kind="PRODUCT",
            mime_type="image/jpeg",
            source_url=f"{self.base}/media/photo.jpg",
        )
        stored = (Path(self._tmp.name) / asset.relative_path).read_bytes()
        self.assertFalse(Image.open(BytesIO(stored)).getexif(), "Stored file must have no EXIF.")
        self.assertNotEqual(stored, payload, "EXIF-laden bytes must not be stored as-is.")

    def test_download_failures_raise_actionable_errors(self):
        from joybuy_crawler.media_pipeline import MediaDownloadFailed

        with self.assertRaises(MediaDownloadFailed):
            self.download("/missing-media")

    @unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg is not installed")
    def test_video_cover_is_extracted_with_ffmpeg(self):
        from joybuy_crawler.fixtures.http_site import write_video_payload

        with tempfile.TemporaryDirectory(prefix="joybuy-vid-") as vid_dir:
            video_path = Path(vid_dir) / "sample.mp4"
            write_video_payload(video_path)
            payload = video_path.read_bytes()

        asset, created = process_media_bytes(
            payload, kind="PRODUCT", mime_type="video/mp4", source_url=f"{self.base}/media/v.mp4"
        )
        self.assertTrue(created)
        asset.refresh_from_db()
        self.assertEqual(asset.process_status, MediaAsset.ProcessStatus.PROCESSED)
        cover = MediaVariant.objects.get(asset=asset, preset="cover")
        self.assertEqual(cover.status, MediaVariant.Status.READY)
        cover_file = Path(self._tmp.name) / cover.relative_path
        self.assertTrue(cover_file.is_file())
        with Image.open(cover_file) as cover_image:
            self.assertGreater(cover_image.width, 0)
        self.assertTrue(media_url(cover.relative_path).startswith("/media/products/derived/cover/"))

    @unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg is not installed")
    def test_video_cover_is_extracted_in_s3_mode_without_local_file(self):
        """S3 mode: cover still works; source bytes are staged from the bucket."""
        from unittest.mock import patch

        from joybuy_crawler.fixtures.http_site import write_video_payload

        from media.tests.test_media_storage_s3 import FakeS3Client

        with tempfile.TemporaryDirectory(prefix="joybuy-vid-") as vid_dir:
            video_path = Path(vid_dir) / "sample.mp4"
            write_video_payload(video_path)
            payload = video_path.read_bytes()

        fake = FakeS3Client()
        with override_settings(MEDIA_BACKEND="s3", MEDIA_S3_BUCKET="fake-media-bucket"):
            with patch("media.storage.get_s3_client", return_value=fake):
                asset, created = process_media_bytes(
                    payload,
                    kind="PRODUCT",
                    mime_type="video/mp4",
                    source_url=f"{self.base}/media/v.mp4",
                )

        self.assertTrue(created)
        self.assertEqual(len(fake.put_calls), 2, "original video + cover frame must be uploaded")
        asset.refresh_from_db()
        self.assertEqual(asset.process_status, MediaAsset.ProcessStatus.PROCESSED)
        cover = MediaVariant.objects.get(asset=asset, preset="cover")
        self.assertEqual(cover.status, MediaVariant.Status.READY)
        self.assertIn(f"media/{cover.relative_path}", fake.objects)
        self.assertFalse(
            (Path(self._tmp.name) / asset.relative_path).exists(),
            "S3 mode must not keep the video on local disk.",
        )

    def test_processing_failure_is_recoverable_via_retry(self):
        from unittest.mock import patch

        payload = make_png_bytes()
        from catalog.product_services import get_or_create_spu_from_source

        spu, _ = get_or_create_spu_from_source(
            source_system="joybuy", source_id="retry-spu", title="Retry product"
        )

        with patch("media.pipeline.ensure_image_variants") as mock_variants:
            mock_variants.side_effect = MediaContentInvalid("transient decoder failure")
            asset, _ = process_media_bytes(
                payload, kind="PRODUCT", mime_type="image/png", target=spu, role="gallery"
            )

        asset.refresh_from_db()
        self.assertEqual(asset.process_status, MediaAsset.ProcessStatus.PENDING)

        result = retry_failed_media()
        self.assertEqual(result["processed"], 1)
        asset.refresh_from_db()
        self.assertEqual(asset.process_status, MediaAsset.ProcessStatus.PROCESSED)
        self.assertEqual(MediaVariant.objects.filter(asset=asset).count(), 6)

        # Corrupt content stays failed and is reported, not silently dropped.
        corrupt, _ = process_media_bytes(b"garbage-bytes", kind="PRODUCT", mime_type="image/png")
        result = retry_failed_media()
        corrupt.refresh_from_db()
        self.assertEqual(result["still_failed"], 1)
        self.assertEqual(corrupt.process_status, MediaAsset.ProcessStatus.FAILED)

    def test_unknown_mime_is_skipped_but_stored(self):
        asset, created = process_media_bytes(b"font-bytes", kind="FONT", mime_type="font/woff2")
        self.assertTrue(created)
        asset.refresh_from_db()
        self.assertEqual(asset.process_status, MediaAsset.ProcessStatus.SKIPPED)
        self.assertEqual(MediaVariant.objects.count(), 0)
