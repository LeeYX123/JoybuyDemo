"""客户端时区上下文（迭代02 第四节：时间存储统一 UTC、展示按登录地区当地时间）。

前端在请求头 ``X-Client-Timezone`` 里携带 IANA 时区名（如 ``Asia/Shanghai``，
取自 ``Intl.DateTimeFormat().resolvedOptions().timeZone``），中间件解析后存入
ContextVar；``merchant_ops.api_utils.iso()`` 序列化时间时优先用它转换。

规则：
- 底层业务时间一律 UTC 存储，不按 IP/时区改写任何业务逻辑；
- 只影响展示序列化；头缺失或时区名无效时回退服务器默认时区；
- 一键下单的触发判定不受影响（比较的是 UTC now，与展示无关）。
"""

from contextvars import ContextVar

_client_timezone = ContextVar("client_timezone", default=None)


def set_client_timezone(name: str | None) -> None:
    _client_timezone.set(name)


def get_client_timezone():
    return _client_timezone.get()


class ClientTimezoneMiddleware:
    """读取 ``X-Client-Timezone`` 请求头，供序列化层做当地时间转换。"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_client_timezone(request.headers.get("X-Client-Timezone"))
        try:
            return self.get_response(request)
        finally:
            set_client_timezone(None)
