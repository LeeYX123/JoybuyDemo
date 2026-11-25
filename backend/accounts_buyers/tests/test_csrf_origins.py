"""手机壳主机名（m.localhost）的 CSRF 放行回归。

背景（2026-11-24 线上问题）：手机端登录点「登录」返回 403，报
`POST http://m.localhost:3000/api/v1/auth/buyer/register/email 403 (Forbidden)`。
根因不是前端：`CSRF_TRUSTED_ORIGINS` 里只放行了 `m.localhost:5174`（商家端手机壳），
漏了 `m.localhost:3000`（商城手机壳）。经 Nuxt 代理后 Host 被改写成 127.0.0.1:8000，
只剩 Origin 参与校验，于是所有写请求都被 CSRF 中间件拒掉。

这组用例锁住两件事：
1. 三个前端端口的 m. 主机名都在默认白名单里；
2. 带 `Origin: http://m.localhost:3000` 的写请求真的能过 CSRF（不只是配置字符串对）。
"""

import json

from django.conf import settings
from django.core.cache import cache
from django.test import Client, TestCase

REGISTER_EMAIL_URL = "/api/v1/auth/buyer/register/email"
SESSION_URL = "/api/v1/auth/buyer/session"


class MobileShellCsrfTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(enforce_csrf_checks=True)

    def test_mobile_shell_origins_are_trusted_by_default(self):
        for port in (3000, 5173, 5174):
            self.assertIn(f"http://m.localhost:{port}", settings.CSRF_TRUSTED_ORIGINS)

    def test_mobile_shell_can_register_with_csrf(self):
        token = self.client.get(SESSION_URL).json()["csrf_token"]

        response = self.client.post(
            REGISTER_EMAIL_URL,
            data=json.dumps(
                {"email": "mobile-shell@example.test", "password": "StrongPass!234"}
            ),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
            # 浏览器在 m.localhost 下发出的就是它
            HTTP_ORIGIN="http://m.localhost:3000",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["account"]["email"], "mobile-shell@example.test")

    def test_untrusted_origin_is_still_rejected(self):
        """白名单不能因此放宽成「任何 Origin」——未知来源必须维持 403。"""

        token = self.client.get(SESSION_URL).json()["csrf_token"]

        response = self.client.post(
            REGISTER_EMAIL_URL,
            data=json.dumps({"email": "evil@example.test", "password": "StrongPass!234"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
            HTTP_ORIGIN="http://evil.example.com",
        )

        self.assertEqual(response.status_code, 403)
