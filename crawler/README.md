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
    settings.py                 Scrapy 设置：robots 遵守、限速（固定间隔 + 0.5~1.5x 随机抖动）、
                                退避重试、HTTP 缓存、脱敏中间件、原始响应归档流水线
    middlewares.py              HeaderRedactionMiddleware：日志中的 Cookie/Authorization 一律 [REDACTED]
    pipelines.py                RawArchivePipeline：每个响应 gzip 归档并写入 crawler_control.RawResponse（30 天保留）
                                RecordRulePipeline：记录级字段规则 + 运行级价格分布告警
                                StagingPipeline：dataset 落盘 → staging → 质量闸门 → 导入
    quality.py                  记录级字段规则（标题/价格/币种/SKU/URL/图片/价格倒挂）与价格分布守卫
    dataset.py                  本地数据集写入（product.json / meta.json / dataset_index.jsonl，按内容指纹增量）
    core/policies.py            指数退避 + 抖动 + Retry-After 策略（框架无关，HTTP/浏览器/Scrapy 共用）
    core/redaction.py           日志脱敏（redact_headers / redact_text / SensitiveDataFilter）
    core/http_client.py         纯 HTTP 下载路径：429/5xx/408 按策略重试，耗尽后抛 FetchFailed
    core/browser.py             Playwright 浏览器路径：无头 Chromium 渲染需要 JavaScript 的页面
    fixtures/http_site.py       本地 fixture 测试站（/ok /flaky /boom /echo /js），仅供测试
```

## 采集口径（2026-11-05）

- **价格**：只采原价（`crossOffPrice`），优惠价丢弃，`list_price` 恒为 `None`。
- **评价**：不采评价内容（正文/图片/视频/评价者信息），只采评分聚合（1~5 星数量、平均分、条数）与
  【内容由人工智能总结自用户评价】区块（`aiSummary`，页面没有就不写）。数据来自详情页的 Next.js
  flight JSON；`ratingInfo` 通常是 `"$19c"` 形式的引用，需按槽位解析。
- **类目**：面包屑只保留去掉站点根后的前两级（`truncate_breadcrumbs`，`BREADCRUMB_DEPTH = 2`）。
- **账号**：一次抓取在账号池内不定时换号（`account_rotation.AccountPool`）：每段班次随机抽时间/请求预算，
  先到者触发换号；命中风控页的账号本轮直接移出池子。换号只换 Cookie（Scrapy 全局 CookieJar 关闭），
  不换代理、不伪造指纹。细节见 `docs/05` §7.5。

解析器契约测试用 `fixtures/product_detail_reviews_v2.html`（按 2026-11-05 归档页结构构造）。

## 数据可信度分层

解析器返回"看起来像商品"的记录，不等于记录是真的。三层防线，职责不重叠：

1. **记录级规则**（`quality.apply_product_rules`）：单条记录是否可信。致命项（无 `source_id`、
   标题过短、价格为 0/不可解析/超范围、币种非法、无 SKU、来源 URL 非 `joybuy.co.uk/dp/`）
   直接丢弃，永不到达 dataset / staging / 业务表；警告项（标题过长或含广告词、个别 SKU 价格坏、
   非 CDN 图片、价格倒挂）放行并写 `RECORD_FLAGGED` 事件。
2. **运行级分布告警**（`quality.PriceDistributionGuard`）：整轮价格分布是否异常。
   不可用价格 ≥ 50% → `PRICE_ANOMALY_MISSING`(ERROR)；所有有效价格完全相同 →
   `PRICE_ANOMALY_UNIFORM`(WARNING)。只上报事件，不改变任务状态。
3. **批级缺失率闸门**（`crawler_control.quality_services.evaluate_batch_quality`）：整批字段
   缺失比例超标时冻结批次并按失败策略暂停任务。

规则细节与判定口径见 `docs/05-crawler-and-ingestion.md` §11.1、§11.2。

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
