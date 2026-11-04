import io
import json
import logging
import uuid

from django.test import SimpleTestCase, TestCase

from common.logging import JsonFormatter


class ApiFoundationTests(TestCase):
    def test_api_root(self):
        response = self.client.get("/api/v1/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["api_version"], "v1")
        uuid.UUID(response.headers["X-Request-ID"])

    def test_health_checks_database_and_cache(self):
        response = self.client.get("/api/v1/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["checks"]["database"]["status"], "ok")
        self.assertEqual(payload["checks"]["cache"]["status"], "ok")
        self.assertEqual(payload["request_id"], response.headers["X-Request-ID"])

    def test_valid_request_id_is_preserved(self):
        request_id = str(uuid.uuid4())

        response = self.client.get("/api/v1/", HTTP_X_REQUEST_ID=request_id)

        self.assertEqual(response.headers["X-Request-ID"], request_id)

    def test_invalid_request_id_is_replaced(self):
        response = self.client.get("/api/v1/", HTTP_X_REQUEST_ID="not-a-uuid")

        returned_id = response.headers["X-Request-ID"]
        uuid.UUID(returned_id)
        self.assertNotEqual(returned_id, "not-a-uuid")

    def test_unknown_api_route_uses_unified_error_shape(self):
        response = self.client.get("/api/v1/does-not-exist")

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "NOT_FOUND")
        self.assertEqual(payload["request_id"], response.headers["X-Request-ID"])

    def test_drf_error_uses_unified_error_shape(self):
        response = self.client.post("/api/v1/", data={}, content_type="application/json")

        self.assertEqual(response.status_code, 405)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "METHOD_NOT_ALLOWED")
        self.assertEqual(payload["request_id"], response.headers["X-Request-ID"])


class JsonLoggingTests(SimpleTestCase):
    def test_formatter_emits_machine_readable_json(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonFormatter())
        logger = logging.getLogger("joybuy.test.json")
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.INFO)

        logger.info("foundation.ready", extra={"event": "foundation.ready"})

        payload = json.loads(stream.getvalue())
        self.assertEqual(payload["level"], "INFO")
        self.assertEqual(payload["message"], "foundation.ready")
        self.assertEqual(payload["event"], "foundation.ready")
