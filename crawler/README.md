# Crawler

Scrapy、Playwright、解析器、fixture 与受控导入流水线。

- 解析器必须先使用保存的 fixture 完成契约测试。
- 遵守授权范围、速率限制和风控，不绕过验证码或保护措施。
- Cookie、OAuth 令牌和原始敏感响应不得进入日志或版本控制。
- Facebook 密码永不收集、永不入库（`crawler_control.record_account_session` 会拒绝包含密码类字段的会话载荷）。

## 运行基座（WP-14）

```text
crawler/
  scrapy.cfg                    Scrapy 项目入口
  requirements.txt              Scrapy 与 Playwright 锁定依赖
  joybuy_crawler/
    settings.py                 Scrapy 设置：robots 遵守、限速、退避重试、HTTP 缓存、脱敏中间件、原始响应归档流水线
    middlewares.py              HeaderRedactionMiddleware：日志中的 Cookie/Authorization 一律 [REDACTED]
    pipelines.py                RawArchivePipeline：每个响应 gzip 归档并写入 crawler_control.RawResponse（30 天保留）
    core/policies.py            指数退避 + 抖动 + Retry-After 策略（框架无关，HTTP/浏览器/Scrapy 共用）
    core/redaction.py           日志脱敏（redact_headers / redact_text / SensitiveDataFilter）
    core/http_client.py         纯 HTTP 下载路径：429/5xx/408 按策略重试，耗尽后抛 FetchFailed
    core/browser.py             Playwright 浏览器路径：无头 Chromium 渲染需要 JavaScript 的页面
    fixtures/http_site.py       本地 fixture 测试站（/ok /flaky /boom /echo /js），仅供测试
```

## 命令

依赖安装（与后端共用仓库根目录 `.venv`）：

```powershell
& .\.venv\Scripts\python.exe -m pip install -r crawler\requirements.txt
& .\.venv\Scripts\python.exe -m playwright install chromium
```

测试（随 `backend\manage.py test` 一起运行，位于 `crawler_control/tests/test_crawler_runtime.py`）：

```powershell
& .\.venv\Scripts\python.exe backend\manage.py test crawler_control.tests.test_crawler_runtime
```

速率、并发、缓存过期等参数全部来自环境变量（见 `joybuy_crawler/settings.py`），不得在代码中写死授权配额。
