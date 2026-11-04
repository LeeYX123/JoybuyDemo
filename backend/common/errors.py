from django.http import JsonResponse


def _error_response(request, *, code: str, message: str, status: int):
    return JsonResponse(
        {
            "error": {"code": code, "message": message, "details": None},
            "request_id": getattr(request, "request_id", None),
        },
        status=status,
    )


def bad_request(request, exception=None):
    return _error_response(
        request,
        code="BAD_REQUEST",
        message="The request could not be understood.",
        status=400,
    )


def not_found(request, exception=None):
    return _error_response(
        request,
        code="NOT_FOUND",
        message="The requested resource was not found.",
        status=404,
    )


def server_error(request):
    return _error_response(
        request,
        code="INTERNAL_ERROR",
        message="An unexpected error occurred.",
        status=500,
    )
