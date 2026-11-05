"""管理端接口共用工具：错误映射、分页、字段格式化。"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from accounts_staff.api_exceptions import StaffApiError
from accounts_staff.views import StaffCsrfAPIView
from merchant_ops.services import MerchantOpsError
from merchants.services import MerchantAdminError

CENT = Decimal("0.01")


class OpsAPIView(StaffCsrfAPIView):
    """把域层错误统一翻译成管理端错误码，避免 500。

    必须挂在 ``handle_exception`` 上而不是 ``dispatch``：DRF 的 dispatch 已
    经走过异常处理链，在那里抛 ``StaffApiError`` 不再有人接住。
    """

    # 只读请求用 view 权限、写请求用 manage 权限（A16 逐模块查看/操作）。
    view_permissions = None

    def resolve_required_permissions(self, request):
        if self.view_permissions and request.method in ("GET", "HEAD", "OPTIONS"):
            return self.view_permissions
        return getattr(self, "required_permissions", [])

    def handle_exception(self, exc):
        from accounts_buyers.services import BuyerWalletError

        if isinstance(exc, (MerchantOpsError, MerchantAdminError, BuyerWalletError)):
            exc = StaffApiError(
                business_code=exc.code,
                message=exc.message,
                status_code=exc.status_code,
            )
        return super().handle_exception(exc)


def money_str(value) -> str:
    if value is None:
        return "0.00"
    return str(Decimal(value).quantize(CENT))


def iso(value) -> str | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return timezone.localtime(value).isoformat()
    return value.isoformat()


def date_str(value) -> str | None:
    if not value:
        return None
    return value.isoformat()


def parse_amount(raw, *, field="金额") -> Decimal:
    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise StaffApiError(
            business_code="AMOUNT_INVALID",
            message=f"{field}必须是数字。",
            status_code=400,
        ) from exc
    if value.as_tuple().exponent < -2:
        raise StaffApiError(
            business_code="AMOUNT_PRECISION",
            message=f"{field}最多保留两位小数。",
            status_code=400,
        )
    return value


def parse_positive_int(raw, *, field="数量", minimum=1) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise StaffApiError(
            business_code="INTEGER_INVALID",
            message=f"{field}必须是整数。",
            status_code=400,
        ) from exc
    if value < minimum:
        raise StaffApiError(
            business_code="INTEGER_TOO_SMALL",
            message=f"{field}不能小于 {minimum}。",
            status_code=400,
        )
    return value


def parse_date(raw, *, field="日期") -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError as exc:
        raise StaffApiError(
            business_code="DATE_INVALID",
            message=f"{field}格式必须为 YYYY-MM-DD。",
            status_code=400,
        ) from exc


def paginate(queryset, request, *, default_size=20, max_size=100):
    try:
        page = max(1, int(request.query_params.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        size = int(request.query_params.get("page_size", default_size))
    except (TypeError, ValueError):
        size = default_size
    size = max(1, min(size, max_size))

    total = queryset.count()
    start = (page - 1) * size
    return list(queryset[start : start + size]), {
        "page": page,
        "page_size": size,
        "total": total,
        "has_next": start + size < total,
    }


def require(payload, key, *, label=None):
    value = payload.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise StaffApiError(
            business_code="FIELD_REQUIRED",
            message=f"{label or key}不能为空。",
            status_code=400,
        )
    return value


def csv_response(filename: str, header: list, rows: list):
    """导出 CSV。所有单元格做公式注入转义（= + - @ 开头加前导单引号）。"""

    import csv

    from django.http import HttpResponse

    def safe(value):
        text = "" if value is None else str(value)
        if text[:1] in {"=", "+", "-", "@", "\t", "\r"}:
            return "'" + text
        return text

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(header)
    for row in rows:
        writer.writerow([safe(cell) for cell in row])
    return response
