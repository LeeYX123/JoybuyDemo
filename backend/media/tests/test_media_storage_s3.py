"""S3 storage backend tests (MEDIA_BACKEND=s3).

A fake S3 client stands in for boto3 so no network is touched: the tests
assert put/get/head/delete calls, dedup behaviour without uploads, variant
generation from in-memory bytes, and the dev-view fallback redirect.
"""

import io
from pathlib import Path
from unittest.mock import patch

from botocore.exceptions import ClientError
from django.conf import settings
from django.http import Http404
from django.test import RequestFactory, TestCase, override_settings
from PIL import Image

from media.models import MediaAsset, MediaVariant
from media.storage import (
    delete_asset_file,
    read_stored_bytes,
    s3_key,
    store_bytes,
    stored_file_exists,
)
from media.tests.test_media_storage import IsolatedMediaRootMixin, make_png
from media.variants import ensure_image_variants
from media.views import serve_media_file

FAKE_BUCKET = "fake-media-bucket"


class FakeS3Client:
    """In-memory stand-in recording every call the storage layer makes."""

    def __init__(self):
        self.objects = {}
        self.put_calls = []
        self.get_calls = []
        self.head_calls = []
        self.delete_calls = []

    @staticmethod
    def _error(code, operation):
        return ClientError({"Error": {"Code": code, "Message": "Not Found"}}, operation)

    def put_object(self, Bucket, Key, Body, ContentType=""):
        payload = bytes(Body)
        self.put_calls.append(
            {"Bucket": Bucket, "Key": Key, "ContentType": ContentType, "Body": payload}
        )
        self.objects[Key] = {"body": payload, "content_type": ContentType}

    def get_object(self, Bucket, Key):
        self.get_calls.append({"Bucket": Bucket, "Key": Key})
        obj = self.objects.get(Key)
        if obj is None:
            raise self._error("NoSuchKey", "GetObject")
        return {"Body": io.BytesIO(obj["body"])}

    def head_object(self, Bucket, Key):
        self.head_calls.append({"Bucket": Bucket, "Key": Key})
        if Key not in self.objects:
            raise self._error("404", "HeadObject")
        return {"ContentLength": len(self.objects[Key]["body"])}

    def delete_object(self, Bucket, Key):
        self.delete_calls.append({"Bucket": Bucket, "Key": Key})
        self.objects.pop(Key, None)


class S3BackendTestCase(IsolatedMediaRootMixin, TestCase):
    """Base: MEDIA_BACKEND=s3 + get_s3_client patched to a FakeS3Client."""

    def setUp(self):
        super().setUp()
        self.fake = FakeS3Client()
        s3_override = override_settings(MEDIA_BACKEND="s3", MEDIA_S3_BUCKET=FAKE_BUCKET)
        s3_override.enable()
        self.addCleanup(s3_override.disable)
        client_patch = patch("media.storage.get_s3_client", return_value=self.fake)
        client_patch.start()
        self.addCleanup(client_patch.stop)


class S3StoreBytesTests(S3BackendTestCase):
    def test_store_bytes_uploads_object_and_skips_disk(self):
        payload = make_png(width=320, height=200)
        asset, created = store_bytes(payload, kind="CMS", mime_type="image/png")

        self.assertTrue(created)
        self.assertEqual(len(self.fake.put_calls), 1)
        call = self.fake.put_calls[0]
        self.assertEqual(call["Bucket"], FAKE_BUCKET)
        self.assertEqual(call["Key"], f"media/{asset.relative_path}")
        self.assertEqual(call["ContentType"], "image/png")
        self.assertEqual(call["Body"], payload)
        self.assertEqual(s3_key(asset.relative_path), f"media/{asset.relative_path}")
        self.assertTrue(asset.relative_path.startswith("cms/original/"))
        # Dimension detection must work from bytes; there is no local file.
        self.assertEqual((asset.width, asset.height), (320, 200))
        self.assertFalse(
            (Path(settings.MEDIA_ROOT) / asset.relative_path).exists(),
            "S3 mode must not write a local copy.",
        )

    def test_dedup_hit_does_not_upload_again(self):
        payload = make_png(color=(3, 4, 5))
        first, first_created = store_bytes(payload, kind="PRODUCT", mime_type="image/png")
        second, second_created = store_bytes(payload, kind="PRODUCT", mime_type="image/png")

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first, second)
        self.assertEqual(MediaAsset.objects.count(), 1)
        self.assertEqual(len(self.fake.put_calls), 1, "Dedup must not put_object again.")

    def test_read_stored_bytes_returns_uploaded_payload(self):
        payload = make_png(color=(9, 8, 7))
        asset, _ = store_bytes(payload, kind="PRODUCT", mime_type="image/png")
        self.assertEqual(read_stored_bytes(asset.relative_path), payload)
        self.assertTrue(stored_file_exists(asset.relative_path))

    def test_stored_file_exists_false_for_missing_object(self):
        self.assertFalse(stored_file_exists("cms/original/00/11/does-not-exist.png"))
        self.assertEqual(len(self.fake.head_calls), 1)

    def test_delete_asset_file_removes_object(self):
        payload = make_png(color=(1, 1, 2))
        asset, _ = store_bytes(payload, kind="PRODUCT", mime_type="image/png")
        delete_asset_file(asset)
        self.assertEqual(len(self.fake.delete_calls), 1)
        self.assertNotIn(f"media/{asset.relative_path}", self.fake.objects)
        self.assertFalse(stored_file_exists(asset.relative_path))


class S3VariantTests(S3BackendTestCase):
    def test_variants_upload_derived_objects(self):
        payload = make_png(width=800, height=600)
        asset, _ = store_bytes(payload, kind="PRODUCT", mime_type="image/png")
        original_puts = len(self.fake.put_calls)

        variants = ensure_image_variants(asset)

        self.assertEqual(len(variants), 6)
        self.assertEqual(
            len(self.fake.put_calls),
            original_puts + 6,
            "Each derived variant must be uploaded as its own object.",
        )
        for variant in variants:
            self.assertTrue(variant.relative_path.startswith("products/derived/"))
            key = f"media/{variant.relative_path}"
            self.assertIn(key, self.fake.objects)
            expected_mime = (
                "image/webp" if variant.format == MediaVariant.Format.WEBP else "image/avif"
            )
            self.assertEqual(self.fake.objects[key]["content_type"], expected_mime)
        # Every derived object must decode as an image built from the source.
        for variant in variants:
            derived = self.fake.objects[f"media/{variant.relative_path}"]["body"]
            with Image.open(io.BytesIO(derived)) as decoded:
                self.assertGreater(decoded.width, 0)


class ServeMediaFileTests(IsolatedMediaRootMixin, TestCase):
    """Dev /media/ endpoint: S3-mode redirect vs local-mode 404.

    Calls the view directly (the URL route only exists when DEBUG was True at
    import time). 404 paths assert on the Http404 exception; the FileResponse
    case closes the response so Windows does not lock the temp media root.
    """

    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()

    def request(self, path):
        return serve_media_file(self.factory.get(f"/media/{path}"), path)

    def test_local_mode_missing_file_returns_404(self):
        with override_settings(DEBUG=True, MEDIA_BACKEND="local"):
            with self.assertRaises(Http404):
                self.request("products/original/aa/bb/missing.png")

    def test_s3_mode_missing_local_file_redirects_to_bucket(self):
        with override_settings(DEBUG=True, MEDIA_BACKEND="s3"):
            response = self.request("products/original/aa/bb/missing.png")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            "https://joybuy-media-fra.s3.eu-central-1.amazonaws.com"
            "/media/products/original/aa/bb/missing.png",
        )

    def test_s3_mode_existing_local_file_is_served_locally(self):
        # Files that predate the S3 switch stay on disk and keep being served.
        payload = make_png(color=(5, 5, 6))
        with override_settings(DEBUG=True, MEDIA_BACKEND="local"):
            asset, _ = store_bytes(payload, kind="PRODUCT", mime_type="image/png")
        with override_settings(DEBUG=True, MEDIA_BACKEND="s3"):
            response = self.request(asset.relative_path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), payload)
        response.close()

    def test_s3_mode_path_traversal_is_404_not_redirect(self):
        with override_settings(DEBUG=True, MEDIA_BACKEND="s3"):
            with self.assertRaises(Http404):
                self.request("../../etc/passwd")

    def test_production_debug_off_is_404_in_both_modes(self):
        with override_settings(DEBUG=False, MEDIA_BACKEND="local"):
            with self.assertRaises(Http404):
                self.request("x.png")
        with override_settings(DEBUG=False, MEDIA_BACKEND="s3"):
            with self.assertRaises(Http404):
                self.request("x.png")
