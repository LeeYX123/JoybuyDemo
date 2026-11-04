from rest_framework.views import exception_handler

STATUS_CODES = {
    400: "VALIDATION_ERROR",
    401: "AUTH_REQUIRED",
    403: "PERMISSION_DENIED",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    429: "RATE_LIMITED",
}


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    request = context.get("request")
    request_id = getattr(request, "request_id", None)
    original_data = response.data
    detail = original_data.get("detail") if isinstance(original_data, dict) else None
    message = str(detail) if detail else "The request could not be processed."
    code = getattr(exc, "business_code", None) or STATUS_CODES.get(
        response.status_code, "API_ERROR"
    )

    response.data = {
        "error": {
            "code": code,
            "message": message,
            "details": original_data if response.status_code == 400 else None,
        },
        "request_id": request_id,
    }
    return response
