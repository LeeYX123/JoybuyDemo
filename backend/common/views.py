import uuid

from django.core.cache import cache
from django.db import connection
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.errors import not_found


@api_view(["GET"])
@permission_classes([AllowAny])
def api_root(request):
    return Response(
        {
            "service": "joybuy-api",
            "api_version": "v1",
            "health": "/api/v1/health",
        }
    )


class HealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        checks = {}

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            checks["database"] = {"status": "ok"}
        except Exception as exc:
            checks["database"] = {
                "status": "error",
                "error_type": type(exc).__name__,
            }

        cache_key = f"health:{uuid.uuid4()}"
        try:
            cache.set(cache_key, "ok", timeout=10)
            if cache.get(cache_key) != "ok":
                raise RuntimeError("Cache read-after-write failed")
            cache.delete(cache_key)
            checks["cache"] = {"status": "ok"}
        except Exception as exc:
            checks["cache"] = {
                "status": "error",
                "error_type": type(exc).__name__,
            }

        healthy = all(check["status"] == "ok" for check in checks.values())
        return Response(
            {
                "status": "ok" if healthy else "degraded",
                "checks": checks,
                "timestamp": timezone.now().isoformat(),
                "request_id": getattr(request, "request_id", None),
            },
            status=200 if healthy else 503,
        )


def api_not_found(request, unmatched=None):
    return not_found(request)
