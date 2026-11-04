# 系统架构

## 1. 总体结构

```mermaid
flowchart LR
    U[购物端用户] --> N[Nginx]
    A[平台管理员] --> N
    N --> S[Nuxt 3 购物端]
    N --> P[Vue 3 平台端]
    N --> D[Django + DRF]
    N --> M[/media 本地媒体]
    S --> D
    P --> D
    D --> DB[(MySQL)]
    D --> R[(Redis)]
    D --> C[Celery Workers]
    C --> DB
    C --> F[媒体处理]
    C --> Q[Scrapy Workers]
    Q --> B[Playwright Browser Pool]
    Q --> J[授权访问的 Joybuy]
    B --> J
    F --> M
```

## 2. 代码库建议

```text
Joybuy/
  backend/                 Django + DRF
  storefront/              Nuxt 3
  admin-web/               Vue 3 + Vite
  merchant-web/            仅保留空基座，待参考网页
  crawler/                 Scrapy、Playwright、解析器
  infra/                   Docker、Nginx、监控和脚本
  var/                     本地开发持久数据，不提交 Git
  docs/                    本文档集
```

可采用单仓库，但模块必须保持清晰边界。爬虫不能直接绕过服务层随意修改业务表，应通过导入服务或受控 staging 表完成。

## 3. Django 领域模块

- `accounts_buyers`：买家账号、会话、验证码；
- `accounts_staff`：员工、平台角色、TOTP；
- `merchants`：商家、入驻、成员关系；
- `catalog`：类目、品牌、SPU、SKU、属性、翻译；
- `offers`：Offer、价格、库存、来源状态；
- `reviews`：来源评价、虚拟用户、媒体、版本；
- `content`：CMS、活动、横幅、页面版本；
- `cart`：匿名/登录购物车；
- `checkout`：地址、配送、运费和结算草稿；
- `orders`：订单、订单行、库存预占、超时取消；
- `notifications`：站内信、邮件、短信和模板；
- `crawler_control`：账号会话、任务、运行、质量告警；
- `media`：资产元数据、变体和处理状态；
- `audit`：后台审计日志；
- `system_config`：市场、语言、货币、功能开关。

## 4. 前端职责

### 4.1 Nuxt 3 购物端

- SSR 用于首屏一致性和快速可见内容，不用于 SEO；
- 浏览、搜索、商品、评价、账户、购物车、结算和待支付订单；
- 所有业务价格和订单结果以后端返回为准；
- 支付按钮调用后端后展示统一的“当前地区暂不支持”；
- 不在浏览器保存敏感令牌。

### 4.2 平台管理端

- Vue 3 SPA；
- 数据表格、批量操作、差异审核、任务监控和 CMS；
- 高风险操作二次确认并填写原因；
- 长任务只创建任务并轮询/订阅状态，不阻塞 HTTP 请求。

### 4.3 商家端

- 首期只保留路由基座、认证边界和未来 API namespace；
- 等用户提供参考网页后重新进行需求评审；
- 不把平台端页面简单复制后称为商家端。

## 5. 搜索

不使用 OpenSearch。首期方案：

- 建立扁平化 `product_search_document` 表；
- 保存 SPU/SKU/Offer 的可搜索文本、类目、品牌、价格区间、评分、标签和可售状态；
- 使用 MySQL FULLTEXT、前缀字段和组合索引；
- JavaScript 前端只调用统一 `SearchService` API；
- 写入商品后通过 Celery 更新搜索文档；
- 定期运行索引一致性校验；
- 若未来实测不能满足 `P95 <= 1s`，再单独评审搜索引擎，不在首期预装 OpenSearch。

## 6. 异步任务

Celery 队列建议隔离：

- `crawl_control`：任务编排；
- `crawl_http`：Scrapy 请求；
- `crawl_browser`：Playwright；
- `parse_import`：解析和规范化；
- `media_download`：媒体下载；
- `media_process`：图片/视频变体；
- `notifications`：邮件和短信；
- `maintenance`：订单超时、清理、索引和备份检查。

浏览器 worker 必须设置较低并发，与普通 HTTP worker 分开扩缩容。

## 7. API 与认证

- REST API 前缀 `/api/v1/`；
- OpenAPI 作为接口契约；
- 买家和员工使用独立登录端点、Cookie 名称和会话存储命名空间；
- Cookie：Secure、HttpOnly、SameSite；
- 所有写操作启用 CSRF 防护；
- 管理 API 强制 RBAC 和租户范围过滤；
- 平台管理员强制 TOTP；
- 文件上传使用类型白名单、大小限制、内容检测和异步处理。

## 8. 配置与功能开关

以下能力必须可配置：

- 市场、语言、货币、时区；
- 验证码供应商；
- 短信和邮件模板；
- 订单待支付超时（默认 60 分钟）；
- 爬虫速率、并发、重试、熔断和保留期；
- 评价目标数量；
- 媒体变体；
- 第三方客服入口；
- 第二阶段 OAuth；
- 未实现功能的展示或隐藏。

秘密信息只从环境变量或秘密文件加载，不写入仓库、数据库普通字段或日志。

## 9. 架构约束

- MySQL 是业务真相源；Redis 不保存唯一业务事实；
- 抓取原始数据、规范化数据和本地覆盖数据分层；
- 文件数据库中只保存相对路径，不保存机器绝对路径；
- 所有导入、媒体处理和订单创建具有幂等键；
- 业务时间存 UTC；
- 金额使用 Decimal 或最小货币单位，禁止浮点数；
- 删除采用软删除或状态迁移，重要业务数据不直接物理删除。

