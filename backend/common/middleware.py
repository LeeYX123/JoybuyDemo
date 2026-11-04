import logging
import time
import uuid

from common.request_context import request_id_context

logger = logging.getLogger("joybuy.request")


def _request_id_from_header(value: str | None) -> str:
    if value:
        try:
            return str(uuid.UUID(value))
        except (ValueError, AttributeError):
            pass
    return str(uuid.uuid4())


class RequestIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = _request_id_from_header(request.headers.get("X-Request-ID"))
        request.request_id = request_id
        token = request_id_context.set(request_id)
        started_at = time.perf_counter()
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request_id
            logger.info(
                "request.completed",
                extra={
                    "event": "request.completed",
                    "method": request.method,
                    "path": request.path,
                    "status_code": response.status_code,
                    "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                },
            )
            return response
        finally:
            request_id_context.reset(token)
