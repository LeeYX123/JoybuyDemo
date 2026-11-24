"""S3 storage backend tests (MEDIA_BACKEND=s3).

A fake S3 client stands in for boto3 so no network is touched: the tests
assert put/get/head/delete calls, dedup behaviour without uploads, variant
generation from in-memory bytes, and the dev-view fallback redirect. A
separate class covers MEDIA_S3_ENDPOINT mode (S3-compatible providers such
as DigitalOcean Spaces) without touching the network either.
"""

import io
from pathlib import Path
from unittest.mock import patch

from botocore.exceptions import ClientError
from django.conf import settings
from django.core.signals import request_finished
from django.db import close_old_connections
from django.http import Http404
from django.test import RequestFactory, TestCase, override_settings
from PIL import Image

from media.models import MediaAsset, MediaVariant
from media.storage import (
    delete_asset_file,
    get_s3_client,
    read_stored_bytes,
    reset_s3_client,
    s3_key,
    s3_public_url,
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

    def test_dedup_hit_reuploads_missing_object(self):
        """A row whose object vanished from the bucket is re-put on the sha hit."""
        payload = make_png(color=(11, 12, 13))
        asset, _ = store_bytes(payload, kind="PRODUCT", mime_type="image/png")
        key = f"media/{asset.relative_path}"
        del self.fake.objects[key]
        self.assertEqual(len(self.fake.put_calls), 1)

        again, created = store_bytes(payload, kind="PRODUCT", mime_type="image/png")

        self.assertFalse(created)
        self.assertEqual(again.pk, asset.pk)
        self.assertEqual(len(self.fake.put_calls), 2)
        self.assertEqual(self.fake.objects[key]["body"], payload)
        self.assertEqual(self.fake.objects[key]["content_type"], "image/png")
        self.assertEqual(MediaAsset.objects.count(), 1)

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
    """Dev /media/ endpoint: S3-mode redirect vs local-mode placeholder/200.

    Calls the view directly (the URL route only exists when DEBUG was True at
    import time). 404 paths assert on the Http404 exception; the FileResponse
    case closes the response so Windows does not lock the temp media root.
    """

    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()

    def request(self, path):
        return serve_media_file(self.factory.get(f"/media/{path}"), path)

    def drain(self, response) -> bytes:
        """Read a streaming response and close it without breaking the test DB.

        ``HttpResponseBase.close()`` fires ``request_finished``; its
        ``close_old_connections`` receiver closes the DB connection, which marks
        the surrounding TestCase atomic block as needing rollback (the next
        query in the class then raises TransactionManagementError). Django's
        test client disconnects that receiver for the same reason.
        """

        payload = b"".join(response.streaming_content)
        request_finished.disconnect(close_old_connections)
        try:
            response.close()
        finally:
            request_finished.connect(close_old_connections)
        return payload

    def test_local_mode_missing_file_returns_svg_placeholder(self):
        with override_settings(DEBUG=True, MEDIA_BACKEND="local"):
            response = self.request("products/original/aa/bb/missing.png")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/svg+xml")
        self.assertEqual(response["Cache-Control"], "public, max-age=3600")
        self.assertIn(b"<svg", response.content)

    def test_local_mode_placeholder_is_extension_agnostic(self):
        bodies = set()
        with override_settings(DEBUG=True, MEDIA_BACKEND="local"):
            for name in ("x.jpg", "x.png", "x.webp", "x.avif", "x.bin"):
                response = self.request(f"products/original/aa/bb/{name}")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], "image/svg+xml")
                bodies.add(response.content)
        self.assertEqual(len(bodies), 1, "Every missing extension must yield one placeholder.")

    def test_local_mode_existing_file_is_served_without_placeholder(self):
        payload = make_png(color=(4, 4, 9))
        with override_settings(DEBUG=True, MEDIA_BACKEND="local"):
            asset, _ = store_bytes(payload, kind="PRODUCT", mime_type="image/png")
            response = self.request(asset.relative_path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.drain(response), payload)

    def test_local_mode_missing_fallback_queries_no_db_and_logs_event(self):
        path = "products/original/aa/bb/missing.webp"
        with override_settings(DEBUG=True, MEDIA_BACKEND="local"):
            with self.assertNumQueries(0):
                with self.assertLogs("media.fallback", level="DEBUG") as captured:
                    response = self.request(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(captured.records), 1)
        record = captured.records[0]
        self.assertEqual(record.levelname, "DEBUG")
        self.assertEqual(record.event, "media.placeholder_fallback")
        self.assertEqual(record.path, path)

    def test_local_mode_path_traversal_is_404_not_placeholder(self):
        with override_settings(DEBUG=True, MEDIA_BACKEND="local"):
            with self.assertRaises(Http404):
                self.request("../../etc/passwd")

    def test_local_mode_directory_path_is_404_not_placeholder(self):
        directory = Path(settings.MEDIA_ROOT) / "products" / "original" / "aa"
        directory.mkdir(parents=True)
        with override_settings(DEBUG=True, MEDIA_BACKEND="local"):
            with self.assertRaises(Http404):
                self.request("products/original/aa")

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
        self.assertEqual(self.drain(response), payload)

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


class S3EndpointTests(IsolatedMediaRootMixin, TestCase):
    """MEDIA_S3_ENDPOINT mode: S3-compatible providers (DigitalOcean Spaces).

    The endpoint must reach both the boto3 client factory (endpoint_url plus
    path-style addressing) and the anonymous public URL builder; an empty
    endpoint keeps the AWS defaults verbatim.
    """

    ENDPOINT = "https://fra1.digitaloceanspaces.com"

    def setUp(self):
        super().setUp()
        override = override_settings(
            MEDIA_BACKEND="s3",
            MEDIA_S3_BUCKET=FAKE_BUCKET,
            MEDIA_S3_ENDPOINT=self.ENDPOINT,
        )
        override.enable()
        self.addCleanup(override.disable)
        # The client is a module-level singleton: drop any endpoint-mode client
        # cached by one test so no other test inherits it (and vice versa).
        reset_s3_client()
        self.addCleanup(reset_s3_client)

    @staticmethod
    def record_boto3_client():
        recorded = {}

        def fake_client(service, **kwargs):
            recorded["service"] = service
            recorded.update(kwargs)
            return FakeS3Client()

        return recorded, fake_client

    def test_get_s3_client_uses_endpoint_and_path_style(self):
        recorded, fake_client = self.record_boto3_client()
        with patch("boto3.client", fake_client):
            client = get_s3_client()
        self.assertIsInstance(client, FakeS3Client)
        self.assertEqual(recorded["service"], "s3")
        self.assertEqual(recorded["endpoint_url"], self.ENDPOINT)
        self.assertEqual(recorded["region_name"], settings.MEDIA_S3_REGION)
        self.assertEqual(recorded["config"].s3.get("addressing_style"), "path")

    def test_empty_endpoint_keeps_aws_default_client(self):
        recorded, fake_client = self.record_boto3_client()
        with override_settings(MEDIA_S3_ENDPOINT=""):
            with patch("boto3.client", fake_client):
                get_s3_client()
        self.assertEqual(recorded["service"], "s3")
        self.assertNotIn("endpoint_url", recorded)
        self.assertNotIn("config", recorded)
        self.assertEqual(recorded["region_name"], settings.MEDIA_S3_REGION)

    def test_s3_public_url_is_path_style_with_endpoint(self):
        self.assertEqual(
            s3_public_url("cms/original/aa/bb/x.png"),
            f"{self.ENDPOINT}/{FAKE_BUCKET}/media/cms/original/aa/bb/x.png",
        )

    def test_empty_endpoint_keeps_aws_virtual_host_url(self):
        with override_settings(MEDIA_S3_ENDPOINT=""):
            self.assertEqual(
                s3_public_url("cms/original/aa/bb/x.png"),
                f"https://{FAKE_BUCKET}.s3.{settings.MEDIA_S3_REGION}"
                ".amazonaws.com/media/cms/original/aa/bb/x.png",
            )

    def test_store_bytes_uploads_object_via_endpoint_client(self):
        """The write path is endpoint-agnostic; a fake put still lands."""
        fake = FakeS3Client()
        payload = make_png(color=(21, 22, 23))
        with patch("media.storage.get_s3_client", return_value=fake):
            asset, created = store_bytes(payload, kind="CMS", mime_type="image/png")
        self.assertTrue(created)
        self.assertEqual(len(fake.put_calls), 1)
        self.assertEqual(fake.put_calls[0]["Bucket"], FAKE_BUCKET)
        self.assertEqual(fake.put_calls[0]["Key"], f"media/{asset.relative_path}")
        self.assertEqual(fake.objects[f"media/{asset.relative_path}"]["body"], payload)
