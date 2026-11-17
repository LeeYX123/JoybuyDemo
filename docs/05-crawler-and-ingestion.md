# 爬虫与数据导入

## 1. 目标

- 支持选择二级或三级类目后抓取该范围内商品；
- 支持设置商品条数、排序、评价目标数、市场和语言；
- 支持试点抓取、全站抓取、增量同步和完整刷新；
- 支持断点续爬、幂等导入、媒体下载和数据质量告警；
- 避免触发风控优先（真实浏览器环境、规范化指纹、低频抓取、复用会话）；【修订 2026-11-05】出现验证码/风控页时采用人工接管处理（见 7.3），不程序化打码、不伪造签名绕过接口校验。

## 2. 分阶段策略

1. 选择 3-5 个类目；
2. 每类抓取 50-100 个商品；
3. 验证字段、SKU、图片、评价、去重、增量和重放；
4. 通过质量闸门后逐步扩大类目；
5. 最后才运行全站任务。

全站模式默认每件商品目标 50 条评价；指定类目或商品可设 `1-300`。真实评价不足时只保存实际数据。

## 3. 抓取技术

- 优先调用页面实际使用、且授权允许访问的数据接口；
- Scrapy 负责 URL 队列、限速、缓存、重试、去重和下载；
- Playwright 仅用于必须执行 JavaScript、建立登录会话或完成管理员人工验证的页面；
- Celery 负责任务编排和状态；
- 浏览器 worker 与 HTTP worker 分开；
- 解析器按页面类型和结构版本组织；
- 导入使用 staging 表或导入服务，不直接在 spider 内散写业务表。
- **浏览器生命周期（2026-11-05 修正）**：一个任务只允许一个爬虫浏览器。类目抓取走
  `BrowserSession`（一次 open、翻多页、退出时 `quit()` + 进程回收）；Scrapy 风控/登录墙
  回退渲染在中间件里复用同一个 session，并在 `spider_closed` 关闭。每条兜底渲染都新开浏览器
  的实现会让一个任务堆出几十个 Chrome，已废弃。残留实例可用
  `manage.py close_crawler_browsers` 回收（只匹配爬虫 `user-data-dir` 与 9333/9334 调试端口，
  不会碰用户自己的 Chrome）。

## 4. 类目任务参数

> 2026-11-03 起的品类配额与树形选择改造，以
> [爬虫任务品类与配额页面改造方案](./09-crawler-category-task-redesign.md)
> 为最新设计基线。现有单类目参数保留用于历史任务兼容。

- 每次抓取必须显式保存 `source_locale`；后续中文类目分析使用 Joybuy 简体中文页面，英文现场结果只作历史参考；
- 每个实际支持的市场/语言组合独立抓取 Joybuy 页面并保存原样文本；德国页面出现德英混合时逐字段记录实际语言，不强制翻译，也不要求用户触发翻译；

管理端任务至少包含：

- 任务名称和优先级；
- 市场、语言、币种；
- 来源二级/三级类目；
- `仅当前类目` / `包含子类目`；
- 二级类目默认包含子类目，三级类目默认仅当前类目；
- 商品数量上限（新页面改名为“本任务最多成功入库商品数”，按去重且通过质量闸门的成功入库商品计数，不按请求数、页面数或发现链接数计数）；
- 排序：来源默认、销量、评分、新品、随机；
- 默认来源排序，并保存当时榜单位置；
- 模式：增量同步 / 完整刷新；
- 商品媒体与详情媒体的下载开关；
- 调度时间、并发、速率和账号组；
- 失败策略和是否允许人工恢复。

> 【停用：2026-11-05】评价目标数（原 `1-300`，默认 50）与"评价媒体下载"两项参数不再生效——爬虫停止采集评价内容，只采集评分聚合与 AI 摘要，见 §10。

随机抽样必须保存 seed，使重复任务可复现。

### 4.1 类目中文名对照（2026-11-05）

管理端【新建任务】的类目选择器同时显示「中文名 / English name」，两个名字按**来源 ID**
（`minihome:UK-Mini-HP-Electronics`、`l2:1405`）严格一对一，绝不按名称或位置匹配。

- **语言开关**：joybuy.co.uk 把界面语言存在 `_lang` Cookie（默认 `en_GB`）；设为 `zh_CN`
  后整个站点（含类目菜单与频道页类目磁贴）变中文，URL 与 source id 完全不变。
- **登录墙**：2026-11-05 起未登录访问首页/频道页会被 307 跳 `/login`，匿名抓取拿不到
  类目内容。抓取必须带已登录账号会话（`--account <账号 public_id>`）。
- **存储**：`SourceCategory.name_zh` 按 source id 持久保存，`SourceCategorySnapshot.name_zh`
  是版本内展示名；英文树仍是结构基线，重新同步英文树时中文名自动继承，不会丢。
- **命令**：

  ```bash
  # 全量抓取（14 个频道）+ 落库
  manage.py sync_joybuy_category_names_zh --account <id> \
      --dump-json var/joybuy_demo/data/category_menu_zh.json
  
  # 被限流时按频道分块抓取，多次运行自动合并
  manage.py sync_joybuy_category_names_zh --account <id> --merge-json \
      --dump-json var/joybuy_demo/data/category_menu_zh.json \
      --channel minihome:UK-Mini-HP-Toys-Baby-and-Kids --pause 20
  
  # 只回放已保存的抓取结果（无网络）
  manage.py sync_joybuy_category_names_zh --from-json <dump.json>
  ```

  命令会报告 `unknown`（抓到了树里没有的 id）与 `still_missing`（树里有但没抓到中文名）
  两类差异；`still_missing` 只影响展示（该节点仅显示英文名），不会伪造译名。

## 5. 增量与刷新

### 5.1 增量同步

- 发现新商品；
- 更新变化字段；
- 增量抓取新评价；
- 媒体 URL 或内容哈希变化时才重新下载；
- 已有商品不会因本次限量任务未出现而失效。

本地数据集（`var/crawl_exports/…`）的增量口径（2026-11-05 实现）：

- `product.json` 与图片**每次都重写**——原始快照永不丢失，解析错了只能靠当时真正抓到的那份数据回放；
- 每个商品目录额外写 `meta.json`（`payload_sha256`、`first_captured_at`、`last_captured_at`、`capture_count`、`changed`）；
- `dataset_index.jsonl` 只在内容指纹变化（或首次落盘）时追加一行，重复抓取同一商品不会把索引刷成重复行；
- 任务结束时写 `DATASET_SUMMARY` 事件，汇报刷新了多少目录、其中多少条内容真正发生变化。

### 5.2 跳过已入库（2026-11-12，任务级开关）

管理端【新建任务】复选框「跳过已入库商品」（`CrawlJob.skip_imported_products`，默认关闭）；
开关随 `params_snapshot.skip_imported_products` 冻结进运行记录。

- **判定**：列表页解析出商品卡片后，蜘蛛一次性按来源身份查
  `spu_source_identity(source_system=job.source_catalog.source_system, source_id IN (...))`；
  命中的商品**不再请求详情页**（PC 详情 + `/dg/` 图文页都省掉），也不占本任务的成功入库名额。
- **范围**：命中即跳过，无论 SPU 当前状态（DRAFT/ACTIVE）——判定标准是"已入库"。
- **代价**：跳过的商品不会刷新价格、库存、评分、评价数和 AI 摘要；需要刷新时关闭该开关重跑。
- **日志**：每页写 `PRODUCTS_SKIPPED_IMPORTED`（INFO）事件，说明该页跳过了多少个已入库商品；
  被跳过的 source_id 同时进入本轮 `seen_product_ids`，其它类目列表不会重复查库。
- **未开启时行为不变**：仍按 `product_limit` 全量抓取，导入侧继续幂等更新。

### 5.3 列表翻页（2026-11-12，任务级开关，默认开启）

背景：Joybuy robots.txt `Disallow: /s?*&page=`（同时禁止 l1/l2/b1/b2/b3/sortType/
filterByBrandIds 等参数），蜘蛛此前每个类目只抓第一屏（实测 20–40 张卡片），单类目
无法到达 200+。运营者拍板：**任务级「翻页抓取」开关，默认开启**，开启即视为运营者
授权偏离 `page=` 这一条规则。

- **字段**：`CrawlJob.allow_pagination`（默认 True），随
  `params_snapshot.allow_pagination` 冻结进运行记录；管理端新建表单复选框
  「翻页抓取」默认勾选，任务详情抽屉显示 开启/关闭。
- **行为**：`parse_listing` 处理完一页后，若开关开、目标未抓满、本页有新内容
  （新入队，或因「跳过已入库」被跳过的新商品），继续请求
  `<robots 安全化 URL>&page=N+1`（`dont_filter=True`），直到抓满 limit。
- **结束条件**（满足其一）：抓满 limit；某页没有新内容（空页/全部跨类目重复）；
  达到安全上限 `JOYBUY_MAX_LISTING_PAGES`（env `CRAWL_MAX_LISTING_PAGES`，默认 25 页）；
  minihome 频道页没有翻页基准 URL，不翻页（写 LISTING_SHORTFALL）。
- **robots 处理**：开启翻页的运行由 runner 设 `ROBOTSTXT_OBEY=False`
  （`/s?k=` 与 `/dp/` 本就 Allow，实际只放开了 `page=` 请求）；关闭翻页的任务
  保持完全遵守 robots.txt。
- **事件**：翻页结束且仍有缺口 → `LISTING_SHORTFALL`（注明「翻页至第 N 页后没有
  更多结果（安全上限 25 页）」）；翻页页没有卡片 → `PAGINATION_COMPLETE`（INFO，
  属正常结束而非解析失败）。
- **其它参数仍禁止**：l1/l2/sortType 等过滤排序参数依旧不发送，URL 仍是
  robots 安全化的 `k=` 单参数形态 + `page=`。

### 5.4 完整刷新

- 重新遍历任务范围；
- 更新现有数据并新增商品；
- 本轮未出现的来源 Offer 标记为疑似失效；
- 经连续确认后改为失效，不直接物理删除；
- 不覆盖本地人工覆盖值。

## 6. 建议频率

- 价格与来源库存状态：每 6 小时；
- 商品基础信息：每日；
- 评价：每日增量；
- 类目与品牌：每周；
- 媒体：内容变化触发；
- 所有频率可在管理端调整。

## 7. 多账号与会话

### 7.1 安全存储

- 使用用户提供且有权使用的 Facebook 账号手动完成 Joybuy OAuth；
- 系统不收集或保存 Facebook 密码；
- 只保存加密后的 Joybuy 会话；
- 会话失效后由管理员重新手动登录；
- 凭据不进入普通配置文件、错误日志或任务导出。

### 7.2 调度规则

- 任一账号触发验证码/风控后立即移出队列；
- 被中断任务能自动切换其他账号接管；
- 短时间多个账号出现相同风险时全局熔断；

### 7.3 风控与验证码处理（2026-11-05 口径更新）

- **避免触发优先**：所有页面抓取优先走真实 Chrome（DrissionPage）而不是纯 HTTP；浏览器环境规范化——去除 Chromium 自动化特征（`AutomationControlled`）、UA 使用本机 Chrome 真实值（无头模式剥离 `HeadlessChrome` 标记）、独立专用 profile 复用登录态；
- 单浏览器低并发 + 页间延迟 + 429/403/5xx 指数退避（见第 8 节），不并发轰击；
- **人工接管**：仍出现验证码或风控页时，任务暂停并提示操作者在有头浏览器窗口中**本人完成**验证/登录；完成后爬虫在同一会话内继续，不重放已失败页面以外的请求；
- 不使用打码平台、不程序化识别或绕过验证码；不伪造签名、不破解加密参数绕过接口校验；
- 风控页绝不作为正常商品/列表页解析，即使人工验证后也要重新请求确认。

### 7.4 账号与任务绑定（2026-11-05 实现）

此前任务表只有 `account_group`（默认 `default`），建任务界面上没有任何账号入口，于是**每个任务都只会落到 default 组**；而且即使运行拿到了账号，也只有浏览器回退那一步带 Cookie，Scrapy 的普通 HTTP 请求是匿名的——每页都要先撞一次登录墙（307 → `/login`）再开浏览器重抓。

现行规则：

- 建任务时可**指定账号**（`CrawlJob.account`，迁移 `0006`）。不指定则按 `account_group` 自动挑「最近最少使用」的可用账号；
- 可用 = `status=ACTIVE` **且** `session_status=VALID` **且** 会话密文能解开 **且解出的载荷里真的含 Cookie**。最后一条是 2026-11-05 补的：历史上有账号被写成 `session_status=VALID`、但载荷只有一个占位字段 `{"joybuy_session": "..."}`，选中它等于"看起来已登录、实际匿名"，正是登录墙的直接原因。演示类管理命令（`load_joybuy_demo`、`load_uk_bestsellers_demo`）也因此不再伪造会话。
- 指定账号不可用时**不静默失败**：写 `ACCOUNT_FALLBACK`（WARNING）事件说明原因，再回退到组内自动选号；组内也没有则写 `RUN_UNAUTHENTICATED` 并匿名启动；
- 成功选到账号时写 `RUN_ACCOUNT_SELECTED`（INFO）事件，内容含账号名与账号组，**任务详情里能直接看到这轮用的是哪个身份**；
- 抓取侧由 `middlewares.AccountCookieMiddleware`（优先级 550，早于 Scrapy 的 CookiesMiddleware 700）把**当前活跃账号**的 Cookie 注入每一个请求，因此第一跳就是登录态；浏览器回退复用同一个账号的 Cookie；
- 只回放 `joybuy` 域 Cookie：第三方 Cookie（Facebook 等）绝不发给源站，避免把凭据泄露到别的域；
- 会话解密只发生在爬虫进程内（账号池构建时按账号各解一次，不跨进程、不落盘），密文始终留在库里，日志不打印 Cookie 值。

### 7.5 账号池轮换（2026-11-05 用户决定）

> 口径变更：一次抓取不再一路固定一个身份。用户在 2026-11-05 明确要求「利用多个账号不定时换号抓取」，原 §7.2「被中断任务不能自动切换其他账号接管」与 §8「不为提高吞吐量轮换账号」两条已按此调整。

**目标**：把一次抓取的请求量分摊到多个账号，让单个账号的请求密度更低，而不是提高总速率。

**池的构成**（`services.usable_accounts_for_run`）：

1. `CrawlJob.account` 指定的账号（若可用）排第一；
2. 其后是同 `account_group` 内 `ACTIVE` + `VALID` 且**会话里真有 Cookie** 的账号，按 `last_used_at` 升序；
3. 上限 50 个，避免一次解密过多会话。

**换号时机**（`account_rotation.AccountPool`）：

- 每段「班次」抽一对随机预算：时间 `CRAWL_ACCOUNT_ROTATE_MIN_SECONDS~MAX_SECONDS`（默认 300~900 秒）与请求数 `MIN_REQUESTS~MAX_REQUESTS`（默认 20~60），**先到者触发**；
- 每次换号后重新抽取，所以换号节奏不是固定周期——固定周期本身就是可识别特征；
- 每次换号重置该账号的班次计数（累计值不跨班次），避免"回到旧账号立刻又触发换号"。

**隔离与安全**：

- 换号只切换 Cookie 集合。**Scrapy 全局 CookieJar 在抓取运行里关闭**（`runner` 里 `COOKIES_ENABLED=False`），否则两个账号的 Cookie 会混在同一个 jar 里一起发出去；
- 因为 `CookiesMiddleware` 被关掉，**`Request.cookies` 不会被转成请求头**——中间件必须自己写 `Cookie` 请求头。这点如果写回 `request.cookies`，抓取会静默变成匿名（踩过一次）；
- 只回放 `joybuy` 域 Cookie，第三方（Facebook）永不出站；
- 浏览器回退用**当前活跃账号**的 Cookie 渲染，保证同一页面不会"HTTP 用一个身份、浏览器用另一个身份"；
- `CrawlRun.account` 记录首个账号；后续换号通过事件留痕，不覆盖该字段。

**风控命中后的处理**：

- 任一页面被判定为风控页 → 该账号在本轮**标记 blocked 并移出账号池**，后续请求交给下一个账号，写 `ACCOUNT_RISK_ROTATED`（WARNING）；
- 全部账号都 blocked → 停止换号，写 `ACCOUNT_POOL_EXHAUSTED`（ERROR）；
- 仍然不程序化识别/绕过验证码，遇到验证码按 §7.3 人工接管。

**运行事件**（任务详情可见）：

| 事件码 | 级别 | 含义 |
| --- | --- | --- |
| `ACCOUNT_POOL_READY` | INFO | 账号池就绪，列出账号数与换号区间 |
| `ACCOUNT_ROTATED` | INFO | 定时/按量换号，含"从 A 切到 B、第 N 次" |
| `ACCOUNT_RISK_ROTATED` | WARNING | 账号命中风控被移出，已切换到下一个 |
| `ACCOUNT_POOL_EXHAUSTED` | ERROR | 池内账号全部被移出，停止换号 |
| `ACCOUNT_POOL_EMPTY` | INFO | 一个可用账号都没有，本轮匿名抓取 |

**配置**（环境变量，遵循"参数不写死"的既有约定）：

```text
CRAWL_ACCOUNT_ROTATION=true                 # false = 只使用第一个账号，不换号
CRAWL_ACCOUNT_ROTATE_MIN_SECONDS=300
CRAWL_ACCOUNT_ROTATE_MAX_SECONDS=900
CRAWL_ACCOUNT_ROTATE_MIN_REQUESTS=20
CRAWL_ACCOUNT_ROTATE_MAX_REQUESTS=60
```

**已知限制**（写在这里，避免下次误判）：

- 所有账号仍共用同一出口 IP 与同一套浏览器指纹，换号只改变身份维度；
- 账号越多，同一 IP 上关联到的身份越多，平台侧"多账号关联"的判断风险也随之上升；
- 会话 Cookie 以登录时捕获的快照为准，抓取过程中不跟随响应 `Set-Cookie` 更新（宁可少刷新，也不让一个账号的令牌串到另一个账号）。

### 7.6 账号组与账号管理（2026-11-05）

**账号组是独立实体**（`CrawlerAccountGroup`，`name` 唯一）。此前账号组只是账号上的一个自由字符串，导致两个问题：组只能在"有账号使用它"时存在，界面上也只能手填。现在：

- 管理端可先「新增账号组」再放账号，账号组字段在新增/编辑账号、新建任务里都是**下拉选择**；
- 账号仍以 `account_group` 名称软引用组（任务侧 `CrawlJob.account_group` 也是名称），改组名不级联，需要时先改组内账号；
- 迁移 `0007` 建表、`0008` 把历史账号的组名回填成组记录（含 `default`），老数据不会出现"下拉框是空的"。

**账号可编辑**（`PUT /api/v1/admin/crawlers/accounts/<uuid>`）：改 `label` / `account_group` / `note`，不动已保存的会话；改组只是把账号挪到另一个轮换池。

**账号可删除**（`DELETE /api/v1/admin/crawlers/accounts/<uuid>`），按**软删除**处理：

- 置 `deleted_at`、状态改 `DISABLED`、`session_cipher` 清空（凭据立即销毁）、会话状态回 `UNKNOWN`；
- 行保留不物理删除——`CrawlRun.account` 是 `SET_NULL`，硬删会让历史运行"忘了"当时用的哪个账号；
- 删除后从账号列表、选号、账号池里全部消失（查询统一加 `deleted_at__isnull=True`），编辑/动作接口返回 404，登录命令拒绝执行；
- 该账号正在被 `RUNNING` 运行使用时**拒绝删除**，提示先暂停或取消任务；
- 所有编辑/删除都写审计（`admin.crawleraccount.update` / `.delete`，删除前记录 label/组/状态）。

接口一览：

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `/api/v1/admin/crawlers/account-groups` | 组列表（含每组账号数） |
| POST | `/api/v1/admin/crawlers/account-groups` | 新增账号组（空组也可建） |
| PUT/PATCH | `/api/v1/admin/crawlers/accounts/<uuid>` | 编辑账号 |
| DELETE | `/api/v1/admin/crawlers/accounts/<uuid>` | 软删除账号 |

## 8. 限速、退避与缓存

- 域名级、接口级、账号级和全局四层限速；
- 429、403、5xx 使用带抖动的指数退避；
- 尊重服务端 Retry-After；
- 相同请求在有效期内使用缓存，但**只缓存 200**：3xx 跳转（尤其是 307 → `/login`）与被判定为登录墙/风控页的响应一律不缓存；
  - 原因（2026-11-05 事故）：Scrapy 默认 `DummyPolicy` 会缓存 307，而缓存键基于 URL、**不包含 Cookie**。一次匿名请求被跳登录后，这个 307 就被存在列表页 URL 下，后续**带着有效账号 Cookie** 的运行直接命中缓存、根本没发网络请求，却报告"登录墙"。现在由 `cache_policy.SuccessOnlyCachePolicy` 兜住（见 §8.1）；
- URL、source ID、响应哈希和媒体哈希多层去重；
- 账号可在池内轮换（见 7.5），但**只换身份**：不轮换代理、不伪造设备指纹、不提高全局总速率；
- 风控页面不得作为正常商品页面解析（处理流程见 7.3：避免触发 → 人工接管 → 重新确认）。

具体速率不在代码中写死，应按授权配额配置并记录变更。

### 8.1 缓存策略（2026-11-05）

- 实现：`crawler/joybuy_crawler/cache_policy.py::SuccessOnlyCachePolicy`（继承 Scrapy `DummyPolicy`，重写 `should_cache_response`）；
- 规则：`status != 200` 不缓存；页面被 `classify_page` 判为登录墙或风控页不缓存；
- 有效期仍是 `CRAWL_HTTPCACHE_EXPIRATION_SECS`（默认 6 小时）；
- 排查提示：如果怀疑"改了 Cookie 却还是登录墙"，先看 `var/cache/scrapy/joybuy_run/` 里有没有 `meta` 写着 `'status': 307` 的条目——有就说明命中了旧缓存，删掉即可（缓存可随时重建）。

### 8.2 代理（2026-11-09）

Scrapy 自带的 `HttpProxyMiddleware` 会读进程环境变量（`http_proxy` / `https_proxy`）和
**Windows 注册表里的系统代理**，所以"系统代理是否生效"不需要改代码。但它有两个坑：

- `no_proxy` 会按 host 旁路（本项目 `.env` 里就有 `NO_PROXY=localhost...` 一类值），一旦命中
  joybuy.co.uk 就静默直连，看起来像"代理没起作用"；
- 环境变量是**进程级**的，无法只给爬虫执行进程指定代理，也不方便单次运行切换。

因此新增显式 opt-in（留空 = 完全沿用 Scrapy 原有行为，**代码里没有任何硬编码代理**）：

| 变量 | 作用 |
| --- | --- |
| `CRAWL_HTTP_PROXY` | 只作用于 `http://` 请求 |
| `CRAWL_HTTPS_PROXY` | 只作用于 `https://` 请求（正式抓取几乎全是 https） |

`middlewares.ProxyConfigMiddleware`（优先级 580，早于 Scrapy 的 750）按请求 scheme 写
`request.meta["proxy"]`。设置 meta 后 `HttpProxyMiddleware` 不再做 `proxy_bypass` 判断，
因此显式配置一定生效、且可逐次运行切换。支持 `http://user:pass@host:port`
（Scrapy 转成 `Proxy-Authorization`）；日志与 `PROXY_CONFIGURED` 事件只用
`redact_proxy_url()` 的脱敏形式（`http://host:port`），密码永不进日志。
只支持 http/https 代理，`socks5://` 会被忽略。

### 8.3 网络失败诊断与连接前置检查（2026-11-09）

**为什么需要**：2026-11-09 的运行 `4d0b3954-2899-4dcb-9d95-b6f0ebb4f52e` 里，
`robots.txt` 与 `/s?k=Phones` 各重试 4 次全部失败于
`ResponseNeverReceived / ConnectionLost`（同机 `urllib` 复现
`SSL: UNEXPECTED_EOF_WHILE_READING`，属 VPN/代理/站点侧的 TLS 断连），
但旧逻辑把零商品运行统一报成「没有发现任何商品：列表页可能被风控拦截、需要登录，
或站点结构已改版。」——完全误导。

**判定规则**（`pipelines.zero_item_failure_reason()`，纯函数、有单测）：

| 条件 | 结论文案 |
| --- | --- |
| `discovered_count == 0` 且列表页下载异常 > 0 | 网络/TLS：「全部/部分列表页请求失败：列表页请求失败 N 次（ConnectionLost 2 次、ResponseNeverReceived 6 次）。请检查网络、VPN 或代理；这是下载/TLS 层错误，不是风控、登录或站点结构改版。…」 |
| `discovered_count == 0` 且列表页**拿到响应**但解析 0 商品 | 保留原文案：「没有发现任何商品：列表页可能被风控拦截、需要登录，或站点结构已改版。」 |
| 有商品且导入成功 | `SUCCEEDED` |

- 计数来源：spider 的 `listing_failed` errback 累计 `listing_fetch_errors` /
  `listing_error_types` / `listing_successes`，并立即写 `LISTING_FETCH_FAILED`（ERROR，
  带 URL、异常类型与文本、本轮第几次失败）。
- 部分失败但仍有商品：写 `LISTING_FETCH_PARTIAL`（WARNING），运行仍可 SUCCEEDED，
  但明确提示"结果可能不完整"。
- `robots.txt` 也拿不到时，原因追加「robots.txt 同样无法获取。」；**只有 robots 失败、
  列表页仍拿到响应时不判成网络问题**（那更像风控页/空页面）。

**连接前置检查**：`runner.execute_run` 在启动 Scrapy 前做一次有超时的 TCP（配置了
`CRAWL_HTTPS_PROXY` 时连代理端口）/ TLS（直连 `www.joybuy.co.uk:443`）连接检查，默认 8 秒
（`CRAWL_PREFLIGHT_TIMEOUT`）。失败时立即写 `CONNECTIVITY_PREFLIGHT_FAILED` 并把运行置
FAILED，不再等 40 秒重试；只建立连接、不发任何 HTTP 请求，因此**不绕过 robots.txt**。
需要恢复旧行为（例如完全离线只跑缓存）时设 `CRAWL_PREFLIGHT_ENABLED=false`。

### 8.4 媒体下载并发与导入复用（2026-11-10，提速）

**问题**：正式任务约 2 分钟/商品，而调试脚本快得多。事件时间线（RUN 22，10 个商品，21 分 25 秒）
拆解出的耗时：页面抓取 ~5s、dataset 落盘（串行下载主图/详情图/视频）平均 **54s**（最大 121s）、
导入媒体库（**同一批图再下一次** + 6 个变体编码）平均 **66s**（最大 140s）。即 96% 的时间花在
媒体 I/O，且全部发生在 Scrapy 的 item pipeline 里，`CONCURRENT_REQUESTS=1` 时会把唯一的抓取
worker 卡住（事件里能看到下一个商品的 `/dg/` 请求排队 60–190s）。

**改动**：

| 位置 | 变更 |
| --- | --- |
| `crawler/joybuy_crawler/dataset.py` | 新增 `_download_many`：图片/视频按 `CRAWL_MEDIA_DOWNLOAD_WORKERS`（默认 6）并发下载，`ThreadPoolExecutor.map` 保证文件编号仍按源站顺序；单张失败只记账。实测同一商品 9 张图：串行 30.44s → 并发 7.72s。`save_product` 返回值新增 `local_media = {"gallery": {url: 绝对路径}, "videos": {url: 绝对路径}}`（只含本次成功落盘的文件，**不写进 `dataset_index.jsonl`**） |
| `crawler/joybuy_crawler/pipelines.py` | 调 `import_staging_product(..., local_media=index_line.get("local_media"))`；`index_line` 预置 `{}`，dataset 写入失败时不会 NameError |
| `backend/crawler_control/import_services.py` | `import_staging_product` 新增 `local_media` 参数；`_import_gallery_images` / `_import_spu_videos` 优先读 dataset 本地文件、缺失才下载；画廊图片仍并发取字节（`_fetch_media_many`），媒体写入/变体生成保持串行；`gallery_images` 汇总新增 `reused` 计数 |

**未改**：页面请求的 `DOWNLOAD_DELAY=2s`（随机 1–3s）、`CONCURRENT_REQUESTS=1`、robots、
账号轮换节奏都保持原样——这些是礼貌性约束，不是本次瓶颈。

**验证**：新增 `DatasetIncrementalTests.test_local_media_maps_gallery_urls_to_files`、
`ImportLocalMediaReuseTests`（本地命中时 `_fetch_image_bytes` 完全不被调用；文件缺失回退下载）、
`StagingPipelineTests.test_process_item_passes_dataset_local_media_to_import`（pipeline 必须把
`local_media` 传给导入）。`test_crawler_import + test_crawler_detail_extras + test_crawler_field_rules`
60 tests OK；`test_crawler_rebuild.StagingPipelineTests + DatasetTests` 11 tests OK。
基准脚本 `var/bench_media_download.py`：同一商品 9 张图，串行 30.44s vs 6 并发 7.72s。

## 9. 数据流水线

```mermaid
flowchart LR
    T[任务配置] --> D[URL 发现]
    D --> H{需要浏览器?}
    H -- 否 --> S[Scrapy 下载]
    H -- 是 --> P[Playwright 会话]
    S --> R[原始响应]
    P --> R
    R --> V[结构与质量校验]
    V --> X[解析为 staging 数据]
    X --> N[规范化/去重/关联]
    N --> I[幂等导入业务表]
    I --> M[媒体下载与变体]
    I --> Q[索引/快照/推荐关系]
    V -- 异常 --> B[暂停与告警]
```

### 9.1 价格采集口径（2026-11-03 需求）

- 爬虫只采集原价：商品详情页同时出现优惠价（current）与原价（list）时，以原价为准入库，优惠价被丢弃；
- 详情解析契约 `product_detail.py` 把原价写入 `current_price`，`list_price` 恒为 `None`，不保存优惠拆分；
- SKU 的 `data-price` 属于展示优惠价：页面存在原价时所有 SKU 价格统一归一为原价；页面没有原价时，页面唯一价格视为原价，SKU 各自价格保留；
- 商城端只展示该原价，展示层规则（美元符号、不渲染"今日送达"类标签）见 `docs/06-api-and-workflows.md` 第 6 节。

### 9.3 列表页解析：两套布局并存（2026-11-05）

搜索结果页改版后，商品卡片不再是"一个带文字的 `<a>`"：

- **卡片布局**：`div[class*="product_card"]` 包住 `a[class*="image_wrapper"]`（**该锚点内没有文字**）+ `[class*="style_title"]` + `[class*="crossOffPrice"]` / `[class*="mainPriceText"]`；
- **锚点布局**：老页面 / 畅销榜页，卡片本身就是一个包含标题与价格的 `a[href*="/dp/"]`。

`parse_uk_listing` 先按卡片扫描，页面没有卡片时回退到锚点逻辑，两种都能解析；只按锚点解析会在新布局产出**空标题、无价格**的卡片（2026-11-05 实际发生过）。另外价格在卡片里被拆成多个文本节点（`£ 32 . 33`），`_price` 会先把小数间的空格合并再取值。

### 9.2 类目层级口径（2026-11-05 需求，2026-11-09 修订）

- 商品详情页的面包屑层级不固定，深的时候能到五级以上（例如 `首页 / 母婴用品 / 健康护理 / 湿巾及配件 / 湿巾 / 商品名`）；
- 入库只保留**去掉站点根后的前两级**：`母婴用品 / 健康护理`，之后的 `湿巾及配件 / 湿巾` 一律丢弃；
- 站点根标签按 `home / 首页 / 主页 / 首頁` 识别并丢弃（区分大小写不敏感）；
- **2026-11-09 修订：面包屑来源改为 flight。** 优先读
  `productBreadCrumbFloor.data["C-M#viewBreadCrumbItem&core"].categories`
  （带 Joybuy 数字类目 ID，如 `厨具餐具(288) → 锅具(361) → 炒锅(372)`），
  仍只保留前两级；DOM 面包屑只作为兜底。第三级及更深**不写入 payload**；
- `joybuy.breadcrumbs` 仍是两级 `[{name,cid}]`；商品类目 ID 放入独立字段：
  - `product_category_path`: `[{id,name,depth}]`，最多两级；
  - `product_category_id`: 最深一级 ID（如 `361`）；
  - `source_category_id` 继续表示**菜单来源类目**，不复用为商品类目 ID；
- 导入时按 `product_category_path` upsert `product_category` 表（最多两级），
  并把最深节点写到 `Spu.product_category`；第三级永不落库；
- **活动商品例外**：菜单 `l2:1580 节庆装饰品` 不建本地类目；任务选中它、或商品类目
  路径含 `节日与活动(4945)` 时，导入直接写 `Spu.is_activity=True` 且
  `local_category=None`（详见 `docs/15` §2.1）；
- 被丢弃的深层分类仍保存在原始响应归档里（§12），确需更细粒度时从归档回放，不需要重抓。

### 9.4 商品详情增量字段：画廊 / 系列规格 / 图文详情 / 规格表格 / 视频（2026-11-09）

正式爬虫已按下表补齐 `joybuy_uk.py`（调试脚本 `crawler/debug_crawl.py` 里验证过的行为，
问题与实测见 `docs/14` §7）。payload 只增字段，导入端可忽略未消费的字段。

| payload 字段 | 来源 | 说明 |
| --- | --- | --- |
| `image_urls` | flight `productMainImageFloor.mediaData[*].bigImageUrl` | 全部商品图，统一 s1248；按去掉尺寸/`!q70.webp` 后缀的路径去重；丢弃 `-000-com` 服务 icon、s32/s64/s96、非 `/product/` 静态资源。DOM 只作兜底并走同一套清洗。 |
| `spec_options` | `productSeriesFloor.series` + `productSelectedFloor.colorSizePartList` | 系列在前、颜色/尺寸在后；值带 `image_url`（规格图 s96）与 `sku_ids`。 |
| `skus[].specs` | 同上 | 按 `skuList` 映射；单 SKU 商品在没有匹配时只挂"只有一个可选值"的维度。 |
| `content_sections` | /dg/ 页 `structuredFloors` + PC `MuiAccordion-root` | `[{title, blocks:[{type:"heading"|"paragraph",text}], text, images}]`；移动端区块优先，PC 补它没有的区块（如「重要信息」）。 |
| `specifications` | /dg/ 页 mode 8（`extendPartList`/`specificationPartList` → `C-P#Attribute&attributeBasic`）、旧版 `graphDetailsModule` | `[{group,name,value}]`，行顺序按源站，**不按 `attributeSort` 重排**。 |
| `specification_tables` | 由 `specifications` 生成 | `[{title, columns:["属性","值"], rows:[{name,value}]}]`；Joybuy 上就是两列表格，前端必须按表格渲染（`docs/14` §7.6）。 |
| `videos` / `video_urls` | `mediaData` 里 `mediaType=2` / `video=true` | `[{url,duration,cover,video_id}]`。 |
| `description` | 由 `content_sections` 生成 | 纯文本兜底，子标题加 `## ` 前缀；规格类区块（规格参数/材质与规格/技术规格）不进正文。 |
| `detail_image_urls` | `content_sections[].images` | 图文详情图片（多为 `/da/...` 原图）。 |

**两次请求的流程**（`joybuy_run.py::parse_detail`）：

1. 解析 `/dp/<slug>/<id>`（机器人/登录墙/风控逻辑不变）；
2. 再 `yield` 一个 `https://www.joybuy.co.uk/dg/<sku>` 请求（带同一 `meta`、独立 `errback`），
   `parse_mobile_detail` 用 `merge_mobile_detail()` 合并后**只产出一条商品 item**；
3. 移动端请求失败（超时 / 风控 / 将来 robots 收紧）时 `mobile_detail_failed` 按 PC 数据落盘，
   运行事件 `MOBILE_DETAIL_FAILED`；合并成功写 `MOBILE_DETAIL_MERGED`（区块/规格/视频计数）。

**robots 口径（2026-11-09 实测）**：`m.joybuy.co.uk/robots.txt` 明确 `Disallow: /dg/`，
因此正式链路**不请求 m. 域名**；`www.joybuy.co.uk/dg/<sku>` 返回同一份 SSR 且 www 站
robots.txt 未禁止 `/dg/`，故只用 www。开关 `CRAWL_MOBILE_DETAIL`（settings
`JOYBUY_MOBILE_DETAIL_ENABLED`，默认开）；每个商品因此多 1 次请求。

**数据集**：视频用浏览器 UA 下载（120s 超时、3 次退避重试）到
`<商品目录>/videos/01.mp4`，写进 `dataset_index.jsonl` 的 `videos`（失败记 `video_errors`）。
**视频不进 `var/media` 媒体库**：媒体库目前只有图片管线与图片用途（role），视频没有
对应的 kind/role 与业务字段，本轮只在 dataset + payload 落库，是否进业务表另立任务。

## 10. 评价采集口径

> 【修订：2026-11-05 需求变更】**不再采集评价内容。** 评价正文、评价者信息、评价图片/视频一律不抓、不入库。原"评价采样"设计（按星级分层抽样保存评论正文）作废，下文为现行口径。

只采集评分聚合与 AI 摘要，来源是详情页内嵌的 Next.js flight JSON：

> 评分展示口径（2026-11-10 确认）：**只入库评价数量、平均分、1~5 星各自数量这三个聚合值，
> 不需要也不导入任何单条评价内容**（reviews 表只保留站内演示数据）。聚合值写入
> `SpuDetail.rating_count / rating_average / rating_distribution`（迁移 `catalog/0016`），
> 购物端评价区用它显示评分与星级分布；本地有 ACTIVE 评价时以本地统计优先。

| 字段（payload） | 来源字段 | 说明 |
| --- | --- | --- |
| `rating_distribution` | `ratingInfo.score1Count` … `score5Count` | 1~5 星各自数量，键为 `"1"`~`"5"` |
| `rating_average` | 优先 `star` / `starShow`，回落 `ratingInfo.averageScore` | 0 条评价时页面把 `averageScore` 默认成 5，此时**不记录**平均分，避免编造 |
| `rating_count` | `totalCommentCount`，回落 `ratingInfo.commentCount` | 总评价条数 |
| `ai_summary` | `aiSummary.summaryContent`（2026-11-09 起优先），回落扁平块里的 `aiSummary` 字符串 | 【内容由人工智能总结自用户评价】正文；**只有页面渲染了才写**，没有就是空字符串且 native 块里不出现 `aiReviewSummary` |
| `ai_summary_title` | `aiSummary.summaryText`，回落 `aiTagTitle` | 摘要标题（通常就是"内容由人工智能总结自用户评价"） |
| `ai_summary_tags` | `aiTagList[].tagName`，回落扁平块 `aiTagList` | 摘要标签 |
| `rating_source` | — | `flight` / `dom` / 空，标明数据来自哪一层 |

实现要点：

- `ratingInfo` 在 flight 流里通常是引用（`"ratingInfo":"$19c"`），必须按 `19c:{...}` 槽位解析；只看引用本身会拿到字符串而非对象。
- 评价聚合对象锚定"包含 `ratingInfo` 的那个大括号对象"，不要用全局 `aiSummary` 关键字搜索——i18n 文案里也有同名字段，会取到错的值。
- 页面 JSON 完全拿不到评分时，才回落到可见评分区（`rating_source=dom`）。**星分布不做 DOM 猜测**：宁可留空，也不根据进度条宽度推算数量。
- 2026-11-09：`aiSummary` 也可能是**内联对象**（`{"summaryContent":..,"summaryText":..}`），
  不是一个字符串；`extract_ai_summary()` 直接 `raw_decode` 冒号后的值（必要时跟 `$ref` 槽位），
  标签从 `aiTagList[].tagName` 取。内联对象优先，扁平块作为兜底，都拿不到就留空不编造。
- 星级各档之和与总条数应能对上（fixture 里有该断言），对不上说明读错了位置。
- 后端 `reviews` 应用与 `joybuy_crawler/sampling.py`（WP-17 评价导入）仍在代码里，但爬虫已不再向它供数；是否整体下线评价模块属于另一个决策，未在本次变更范围内。

## 11. 质量闸门

每类页面定义：

- 结构版本；
- 必填字段；
- 类型、长度和取值范围；
- 样例响应与解析契约测试；
- 核心字段缺失率阈值；
- 价格、SKU 数、媒体数和评价数异常阈值。

若标题、价格、SKU、主图等核心字段缺失率超过阈值：

1. 暂停任务；
2. 保留原始响应；
3. 告警并标记疑似页面改版；
4. 禁止异常批次覆盖已有数据；
5. 修复解析器并重放原始响应；
6. 通过抽样审核后恢复。

### 11.1 记录级字段规则（2026-11-05 实现）

上表里"类型、长度和取值范围"与"异常阈值"两层，分别落在两个独立实现上，职责不重叠：

| 层 | 实现 | 回答的问题 | 触发后的动作 |
| --- | --- | --- | --- |
| 批级缺失率 | `crawler_control.quality_services.evaluate_batch_quality` | 这一批里字段 X 缺了多少比例 | 冻结批次、按失败策略暂停任务 |
| 记录级规则 | `crawler/joybuy_crawler/quality.py` + `pipelines.RecordRulePipeline` | 这一条记录本身是否可信 | 致命项丢弃该条（不进 dataset / staging / 业务表）；警告项放行并上报事件 |

记录级规则的判定口径：

- **身份**：`source_id` 必须存在且形如 `[A-Za-z0-9_.-]{1,64}`；
- **标题**：去空白后长度 ≥ 5，> 500 视为选择器吞掉了整块；含 `sponsored` / `advertisement` / `hot sale` / `为你推荐` / `热推` / `广告` 视为广告位；
- **价格**：必须解析为数字（接受 `£12.99`、`1,299.00`、区间写法一律拒绝），且落在 `0.01 ~ 100000`；**0 与负价是致命项**，因为"价格全变 0 但程序不报错"是历史上最难发现的一类污染；
- **币种**：必须是 3 位字母代码，小写会被归一为大写；
- **SKU**：至少一条；个别 SKU 价格不可解析只警告，不整条丢弃；
- **来源 URL**：host 必须是 `joybuy.co.uk` / `www.joybuy.co.uk` 且路径含 `/dp/`（拦住跳转到登录页或错误页的情况）；
- **图片**：只保留 `joy-sourcing.com` 域的 URL，其余直接丢弃并警告（不写入 dataset、不从陌生源下载）；
- **价格倒挂**：`mainPrice`（优惠价）> `crossOffPrice`（原价）时警告，说明两个选择器大概率串位了。

列表页卡片另有 `check_listing_entry`：标题过短、含广告标记、URL 里取不到商品 ID 的卡片会被丢弃，不再占用每个类目的商品配额。被丢弃的条数写入 `LISTING_CARDS_REJECTED` 事件。

### 11.2 运行级价格分布告警（2026-11-05 实现）

单条记录看起来"合理"（数字在合法区间），整轮却可能已经坏了。`PriceDistributionGuard` 在任务结束时检查分布，命中后写 `PRICE_ANOMALY_MISSING`（ERROR）或 `PRICE_ANOMALY_UNIFORM`（WARNING）事件：

- 样本 ≥ 3 且不可用价格占比 ≥ 50% → ERROR，提示价格选择器失效、应重放原始响应；
- 样本 ≥ 3 且所有有效价格完全相同 → WARNING，提示选择器读到了公共容器价。

该告警**只上报事件、不改变任务状态**：判断"这一轮是否算失败"仍由 `complete_run_failed` 的既有规则（零成功、零发现、异常结束）决定，避免把"价格可疑但数据可用"直接判死。

### 11.3 运行日志文案约定（2026-11-05）

管理端【爬虫任务 → 任务详情 → 运行日志】直接展示 `CrawlRunEvent.message`，因此：

- **`message` 一律用中文**，面向运维人员读写；写了英文文案等同于让日志不可读。新增事件时不要图省事复制英文模板。
- **`code` 与字段名保持英文常量**（如 `RECORD_REJECTED`、`current_price`）：`code` 是排障与检索的稳定标识，字段名是 payload 的键，翻译会破坏可检索性。中文短标签在前端 `admin-web/src/lib/locale.js` 的 `EVENT_CODE_LABELS` 里维护，原始 code 保留在悬停提示中。
- 事件级别 `INFO/WARNING/ERROR` 由前端 `valueLabel()` 显示为「信息 / 警告 / 错误」。
- 文案里要保留可定位的原始值（source id、URL、异常文本、计数），不要为了"像中文"把关键信息抹掉。
- 底层传输日志（`crawler/joybuy_crawler/core/http_client.py`、`core/browser.py`）保持英文——它们是请求/响应级别的技术日志，不是运维事件流。

**抓取过程的日志粒度（2026-11-05 补充）**：每抓一个页面、每个商品都要能回答"访问了哪个 URL、拿到了什么、处理成什么、存到哪"。约定如下：

| 事件码 | 何时写 | 内容 |
| --- | --- | --- |
| `LISTING_FETCHED` | 每个列表页解析完 | URL、HTTP 状态、响应大小、耗时、卡片数、本轮入队/重复跳过/超上限/非商品卡片数、累计入队进度 |
| `PRODUCT_PARSED` | 每个详情页解析完 | URL、HTTP 状态、响应大小、耗时、商品 ID 与标题、原价+币种、SKU 数、图片数、评分/条数、分类路径、AI 摘要字数 |
| `DATASET_SAVED` | 每个商品落盘后 | `var/crawl_exports/{任务目录}/{类目}/{商品ID}`、`product.json`、主图/详情图张数、失败图片数、内容是否变化 |
| `PRODUCT_IMPORTED` | 每个商品入库后 | SPU（新建/更新）、SKU 数、Offer 数、暂存记录 ID |
| `IMPORT_SOURCE_CONFLICT` | 来源身份已绑定到别的 Offer/SKU 时 | 来源身份、现有/本次商家与 SKU 规格、市场/币种、不一致字段、卖家名/本地化提示；**不自动改绑**（详见 `docs/14` §10） |
| `LISTING_FETCH_FAILED` | 列表页请求重试耗尽/传输层异常 | URL、异常类型与文本、本轮第几次失败；文案明确"属网络/TLS 层错误，不是风控或结构改版" |
| `LISTING_FETCH_PARTIAL` | 结束时有列表页下载失败但仍有商品 | 失败次数与类型、已发现商品数、结果可能不完整 |
| `CONNECTIVITY_PREFLIGHT_FAILED` | 启动前连接检查失败 | 目标 host:port、异常文本、排查建议与代理变量 |
| `PROXY_CONFIGURED` | 按显式代理设置启动 | 脱敏后的代理地址（不含账号密码） |

一个商品因此固定产出 3 条日志（解析 → 落盘 → 入库），排查时按商品 ID 串起来即可看到完整链路。失败路径保留原有事件（`*_FAILED` / `RECORD_REJECTED` / `IMPORT_REJECTED` / `IMPORT_SOURCE_CONFLICT`），文案里同样带 URL 与原因。

任务详情的接口一次返回最近 **200** 条事件（原为 50），因为按上面的粒度，50 个商品就会产生约 150 条。

**写事件时必须注意**：`record_run_event` 要在函数顶部导入。2026-11-05 踩过——在 `if` 分支里导入会让它在整个函数作用域变成局部变量，成功路径上未赋值直接 `UnboundLocalError`，每个详情页都会崩。

## 12. 原始数据与追溯

- 原始 HTML/JSON 默认保留 30 天；
- 规范化数据、媒体、来源哈希和任务记录长期保留；
- 每个字段尽量记录来源 URL、抓取时间和解析器版本；
- 排名必须记录榜单上下文；
- 来源没有展示的销量、排名等字段保持为空；
- 任何估算值使用独立字段和算法版本。

## 13. 站点快照

实施开始时建立页面与数据基线：

- 页面 URL 与类型；
- 桌面/移动截图；
- DOM 摘要与关键选择器；
- 接口请求/响应样例；
- 国家、语言、货币选项；
- 图标、字体和媒体清单；
- 当前规则说明和抓取日期。

Joybuy 后续变更先进入差异报告，不直接改变当前复刻版本。


## 14. 独立浏览器爬取脚本（2026-11-05）

后台 Scrapy 任务在 joybuy.co.uk 上的失败模式：站点对 **headless / 仅注入 Cookie 的浏览器**返回
`403 页面`（`/error403?referrer=...`），列表页没有任何 `/dp/` 商品卡，运行以
`LISTING_PARSE_FAILED` + `No products were discovered` 结束。现场对比（2026-11-05 16:10）：

| 访问方式 | 列表页结果 |
|---|---|
| headed + 常驻已登录 profile | 真实页面，2,649,944 字节，40 个 `/dp/` 卡 |
| headless + 注入账号 Cookie | `403 页面`，0 个商品卡 |

因此提供独立脚本 `scripts/joybuy_standalone_crawler.py`，思路与
`crawler_friend_list_Korea1111.py` 一致：**真实有头浏览器 + 常驻 `user_data_path`
（登录态留在 profile 里，不搬 Cookie）+ `page.listen` 抓文档流**。

- 数据落盘与入库**沿用原有链路**：`joybuy_crawler.dataset.save_product` 写
  `var/crawl_exports/{run 前 8 位}-{任务 slug}/{类目 slug}/{商品ID}/product.json + images/main|detail`
  与 `dataset_index.jsonl`；DB 走 `ingest_product_payload` → `StagingProduct` →
  `import_staging_product`（SPU/Offer/Media/搜索文档）。
- 运行记录仍写 `CrawlRun` 计数与 `CrawlRunEvent`，并新增 `STANDALONE_STARTED` /
  `LISTING_PARSED` / `PRODUCT_IMPORTED` 事件，管理端可见进度。
- 入口参数：`--job <public_id>`（失败任务可直接复用，会新建 run）、`--limit`、
  `--profile`（默认 `var/browser_profiles/account-9b189970`）、`--port`（默认 9335）、
  `--pause`、`--lang`（默认 `en_GB`，让面包屑保持英文以便落盘 slug 与既有导出一致）。
- 关键细节（踩过的坑）：
  - 详情页 URL 含中文 slug，`page.listen` 关键字必须用**商品 ID**，否则 40s 超时拿不到包；
  - 刚 `get` 完 DOM 只有骨架，必须轮询到文档 ≥200KB（且含 `<h1>`）再解析，否则标题/价格为空被质量闸门拒收；
  - 脚本用独立端口（9335），不占用后台任务的 9333 与登录窗口的 9334。
- 前提：`--profile` 指向的 profile **必须已登录** joybuy.co.uk（在管理端「爬虫账号 → 登录」
  弹窗里登录一次即可，profile 会保留登录态）。
