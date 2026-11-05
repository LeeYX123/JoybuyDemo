# Joybuy 新会话交接文档

> 本文档是新会话的第一入口。每次任务结束前必须更新；详细纪律见 `AGENTS.md`。

## 1. 我们在做什么

- **当前任务（2026-11-05 夜，三轮 + 图片本地上传全部完成）**：按 `商家端及平台管理端文档/` 重构商家后台与平台管理后台。**第 1 轮**：数据模型 + 平台 A02–A09。**第 2 轮**：A10–A17。**第 3 轮**：`merchant-web` + 商家端 M01–M10。**图片**：新增统一上传接口，落盘到 `var/media/`，业务表只存 `/media/...` URL，前端直接渲染。**已无遗留必做项**（对象存储/图片压缩变体可作为后续优化）。
- 当前任务（2026-11-05，**运行日志已细化**）：用户要求日志里能看到访问的 URL、拿到的数据、处理结果和落盘路径。已加 `LISTING_FETCHED` / `PRODUCT_PARSED` / `DATASET_SAVED` 并增强 `PRODUCT_IMPORTED`（每商品 3 条：解析→落盘→入库），详情接口事件数 50→200；顺带修掉 `parse_detail` 里会导致每个详情页崩溃的 `UnboundLocalError`。详见 §2"补充 11"。
- 当前任务（2026-11-05，**登录墙根因已修**）：用户反馈最新任务仍报登录墙。实测证明账号 Cookie 有效（带 Cookie curl 得 200），真因是 **Scrapy 默认缓存策略把匿名请求的 307 跳登录缓存了 6 小时，带 Cookie 的运行直接吃缓存、根本没发请求**；同时列表页改版导致解析出空标题/无价格。已加 `SuccessOnlyCachePolicy` + 清缓存 + 列表双布局解析器，端到端实抓验证 40/40 卡片有标题有原价。详见 §2"补充 10"。
- 当前任务（2026-11-05，**账号组实体化 + 账号可编辑/删除**）：用户要求账号可改组、可编辑、可删除，新增账号时组要下拉选，并能新建账号组。已加 `CrawlerAccountGroup` 表 + 账号软删除 + 4 个接口 + 管理端下拉/编辑/删除。**删除是软删除**（会话销毁、行保留以保住历史运行的账号归属）。详见 §2"补充 9"。
- 当前任务（2026-11-05，**多账号不定时换号已实现**）：用户明确决定用多个账号轮换抓取，并按"对话优先"改掉了 `docs/05` 的冲突条目。已实现 `AccountPool`（随机时间/请求预算触发换号）、风控命中即移出池子、Scrapy 全局 CookieJar 关闭以防串号、5 个中文事件码。详见 §2"补充 8"。
- 当前任务（2026-11-05，**爬虫账号绑定已修**）：用户问"抓取时到底有没有带爬虫账号"。查出三个真问题：建任务接口忽略账号、HTTP 请求从不带 Cookie（只有浏览器回退带）、`Joybuy homepage demo` 是"假 VALID"占位会话（0 条 Cookie）。已加 `CrawlJob.account`（迁移 0006）+ 建任务可选账号 + 账号 Cookie 注入 + 可用性判定要求"会话里真有 Cookie"。详见 §2"补充 7"。
- 当前任务（2026-11-05，**运行日志已中文化**）：用户反馈爬虫任务详情的日志是英文。已把全部运行事件文案、失败原因、质量规则说明改成中文；`code` 与字段名保留英文常量以维持可检索性，中文短标签放前端 `locale.js`。详见 §2 同日"补充 6"小节。
- 当前任务（2026-11-05，**评价只采聚合、分类只到二级**）：用户两条数据口径变更。①**不再爬评价内容**，只采 1~5 星各自数量、平均分、评价条数，以及【内容由人工智能总结自用户评价】区块（有才采、没有就不写）；②面包屑**只保留去掉"首页"后的前两级**（`首页/母婴用品/健康护理/湿巾及配件/湿巾/商品` → `母婴用品/健康护理`）。两条都已落到解析器（`joybuy_uk.py`）并有 fixture 契约测试。详见 §2 同日"补充 4"小节。
- 当前任务（2026-11-05，**爬虫记录级质量层已落地**）：参照一篇商城爬虫实战文章（CSDN 166029197）里"解析看起来成功但数据是脏的"教训，给爬虫补了**记录级字段规则 + 运行级价格分布告警 + 数据集按内容指纹增量**三层。新建 `crawler/joybuy_crawler/quality.py` 与 `pipelines.RecordRulePipeline`（优先级 150，在 `StagingPipeline` 200 之前），致命违规直接丢该条，永不进 dataset/staging/业务表。**实测探针**：拿 `var/crawl_exports` 里 9 份真实抓取 payload 回放，6 份正常商品零违规通过、3 份本来就是空解析（title/price/currency 全空）的脏数据全部拦截，无误杀。详见 §2 同日"爬虫记录级质量层"小节。
- 当前任务（2026-11-05，**浏览器生命周期已修**）：用户反馈「一个任务打开几十个浏览器且不关闭」。已改为**一个任务一个浏览器、退出必关**（`BrowserSession` + 进程回收 + `close_crawler_browsers` 命令），并用探针证实「1 个浏览器抓 2 页、结束后 0 个进程」。详见 §2 同日补充小节。
- 当前任务（2026-11-05，**类目中英双语展示，代码已完成、数据 170/177**）：管理端【新建任务】-【选择 Joybuy 类目】原来只显示英文，现在同时显示「中文名 / English name」。中文名从 joybuy.co.uk 切到 `_lang=zh_CN` 后按 **source id 一对一** 抓取并入库，英文树结构不变。详见 §2 同日小节与 `docs/05` §4.1。
- 当前任务（2026-11-05，**第 1、2 轮全部完成**）：按用户 7 条要求重建爬虫任务模块。用户确认 4 个口径：**类目树选择**、**Scrapy+DrissionPage 混合**、**人工弹窗登录+加密 Cookie**、数据集按**类目/商品分层**。
- **第 2 轮成果（账号管理 + 管理端 UI，全部浏览器实测通过）**：
  - **账号管理后端**：`GET/POST /api/v1/admin/crawlers/accounts`（列表不暴露 session_cipher）+ `POST /crawlers/accounts/{id}/actions`（`login`/`logout`/`verify`/`disable`/`enable`/`reactivate`，权限码 `crawler.accounts.manage`，全部写审计）。`login` 派生独立进程 `manage.py crawler_account_login --account <id>`：弹**有头 Chrome**（独立端口 9334 + 每账号独立 profile `var/browser_profiles/account-{id8}`），用户本人完成 Facebook 登录后自动检测（首页可见文本无 "Sign in" + Cookie≥5 条）→ Cookie 加密入库 `record_account_session`（密码永不收集），8 分钟超时；`verify` 用存储 Cookie 无头渲染首页判定，失败则 `mark_session_expired`（风控页不算失败）；`logout`=清除会话；风控账号必须走 `reactivate`（`set_account_status` 拦截直接 enable）。
  - **admin-web 重做**（`CrawlersView.vue` + 新组件 `CategoryTreePicker.vue`）：**任务 Tab**——新建表单内嵌 Joybuy 类目树（搜索过滤+两级展开勾选+每节点"含子类目"切换，数据来自 `/crawlers/source-tree`），列表新增类目摘要列，**详情抽屉**（冻结类目选择/树版本/运行计数/事件流，RUNNING 时 5s 轮询）；**爬虫账号 Tab**——列表（状态/会话/最近动作 note）+ 新增 + 登录/验证/清除会话/解除风控/停用/启用，登录等待期 5s 轮询自动刷新。locale.js 补齐 SUCCEEDED/VALID/EXPIRED/LOGIN_PENDING 等中文映射。
  - **实测修复的真 bug**：任务创建 API 用不存在的 `SourceCategory.public_id` 查类目（旧 UI 同样是坏的）→ 统一改为 `source_id`（`l2:1405`/`minihome:...`），前端 payload 改发 `source_ids`，并补 HTTP 层测试 `test_crawl_jobs_api.py` 防回归。
  - **遗留**：登录流程需要用户本人在弹窗里完成 Facebook 登录（未实测到 Cookie 落库那一步，检测逻辑已按可见文本规则实现并有单测覆盖 verify 路径）；列表页 window.prompt 的审计原因框在自动化浏览器中不便处理，人工使用正常。
- **第 1 轮成果（后端，全部已实测）**：① 类目树同步 `manage.py sync_joybuy_category_tree`（14 一级频道+163 子类目已发布 `joybuy-uk-20261104-4dcfbbe5`）+ `GET /crawlers/source-tree`；② `CrawlJobSourceSelection` 多类目+树版本冻结（迁移 0005）+ `CrawlRunEvent` 事件模型 + 任务详情 API；③ 执行器：`start` 派生独立进程 → Scrapy spider → 风控中间件自动切 DrissionPage → 解析器 v2（joybuy 原生字段）→ StagingPipeline；④ 数据集 `var/crawl_exports/{任务}/{类目}/{类目}/{商品ID}/`，主图 s1248 阶梯最高清；⑤ `import_staging_product` 补 gallery 导入。**实测**：3 商品 3/3 导入、52 图 0 失败、1248×1248 主图落盘。
- **docs/05 已按用户指示更新**（§1、§7.3、§8）：避免触发风控优先；出现验证码/风控时人工接管，不程序化打码。
- 上一任务（2026-11-05，已完成）：产出数据库说明文档 `docs/13-database-schema.md`（79 表 759 字段，纯文档）。再上一任务：管理端登录移除 TOTP 验证器只保留邮箱+密码（详见下方记录）。
- 上一任务（2026-11-04，已完成）：补齐商城端【畅销榜单】11 个标准类目的公开 Joybuy 演示商品。已从 `joybuy.co.uk` 中文浏览器会话和固定公开榜单页采集 11 类 × 3 条，全部通过 staging 导入、激活并建立 GB 搜索文档；33/33 fixture 商品均已下载到本地媒体库，榜单接口现在返回本地 `/media/...` 首图，页面已抽查美妆与游戏类目正常显示。服装是唯一例外：Joybuy 畅销榜侧栏没有服装一级榜，fixture 明确标记使用“时装配饰频道 → 爆款直降”替代来源，绝不能伪装成官方 bestseller 子榜。
- 当前任务（2026-11-04 夜间自动执行，**已完成**）：按用户指令"参照 joybuy.co.uk 逐元素视觉对齐全部文档页面"的全自动流程执行完毕。四份交付物在 `var/ui-alignment/deliverables.md`（页面清单+基准规格表+代码修改记录+复核差异清单 D-01~D-14）。覆盖：全局头部（logo 图片化/搜索框/圆形按钮/类目行）、首页、Categories 面板、列表页（234px 左栏+274px 卡重写）、**畅销榜单页新建**（/promo/best-seller，hero 384px/11 品类无箭头/仅价格筛选/排名徽章 32×32 #E4E6EB）、详情页重写（Buy now #E1251B hover #D14335 / Add to cart #1A1A1A hover #282828 / 数量步进器 47×34 / 白名单拦截弹窗 / 服务保障纯文本行）、结算页两步化（3 字段地址表单→支付步骤：余额支付置顶+精简 Summary+精简页脚）。后端最小支撑：`BuyerAccount.purchase_whitelisted`（迁移 0004，默认 True=开发阶段放行，session payload 返回）。E2E purchase-funnel 的结算步骤已同步新流程；funnel 在 dev 水合竞态下仍偶发超时（差异清单 D-14），全流程已浏览器人工验证（含下单 201）。
- 下一轮（待用户确认后）：第 2 轮榜单后台配置（RankingList/管理端 RankingsView，见更下方计划）；第 3 轮钱包/白名单 admin/直购参数/地址后端校验放宽（对应差异清单 D-07~D-10）。
- 当前任务（三轮制，**已完成第 1 轮，待用户确认后进入第 2 轮**）：按 `docs/12-joybuy-co-uk-ui-spec.md`（目标状态规格，对应 `功能需求清单.md` 8 组需求）实施改造。用户已确认两个口径：**界面语言中英文可配置**（EN/ZH 双语，storefront 轻量 i18n + 后端双语数据）、**分三轮逐轮确认**（第 1 轮全局头部+类目体系+首页 CMS → 第 2 轮畅销榜单页+后台榜单配置 → 第 3 轮详情页购买改造+地址页+支付页+白名单/钱包后台）。完整计划见本会话已批准的实施计划；第 1 轮成果见下方"2026-11-04"节。
- 下一轮（第 2 轮）要点：`RankingList`/`RankingEntry` 模型 + `/api/v1/admin/rankings`（权限码 `catalog.rankings.manage`）+ admin-web RankingsView；商城端 `/promo/best-seller` 页（左栏 11 品类无展开箭头 + 仅价格区间筛选 + 右栏榜单分段，榜单卡无营销标签）；首页 Bestsellers 楼层用新 CMS 模块类型 `bestseller_floor`（同步三处：schemas.py、CmsModule.Type+迁移、CmsRenderer）。
- 上一任务：浏览器实测遍历真实 Joybuy 站点（joybuy.co.uk）并产出产品功能分析文档，作为复刻参考。已完成：`docs/11-joybuy-co-uk-product-features.md`。
- 追加（同日第二轮）：产出界面还原规格文档 `docs/12-joybuy-co-uk-ui-spec.md`（逐元素三层规格：页面整体/元素清单表/排版关系，含截图采样色值与推测标注），与功能文档互补。
- 追加（同日第三轮，应用户问询）：补测 4 个类目子页面（Noodles/Fragrance/Womens Clothing/Electronics 对照），确认所有二级类目图块统一落地 /s?k= 列表页模板，但筛选面板数据驱动——快捷 Tab 数量（3–6 个）、价格区间、Category 细分、是否带二级图块行、商品卡是否带加购均随类目变化；食品类特有 Repeat & Save；/s?b1= 直达形式可能空态（仅 Notify me when available）。差异已写入 `docs/12` 4.1 节与 `docs/11` 列表页模块。
- 追加（同日 21:37–21:45，用户授权登录）：在 WorkBuddy 内置浏览器中完成 Joybuy Facebook OAuth 登录。账号信息：Joybuy 用户名 `user4323txlb`（Facebook 首登自动创建的新账号，2026-11-03 注册，含 2 张 Welcome Offer 优惠券），对应 Facebook ID `100013498475534`（用户提供），登录方式 Facebook（loginType=30），登录态保存在 WorkBuddy Browser 的会话 profile 中，后续会话可直接操作已登录页面。**密码一律未记录、不得记录**。已知怪象：OAuth 回跳中间页会闪现 `{"code":"1","echo":"cross-origin request from '' is not allowed"}`（color-api.joybuy.com 的 loginByTicket CORS 校验报错），但会话实际已建立，回首页即见头像，可忽略该报错——复刻项目如做第三方登录回跳需注意此坑（回调中间页应走前端 XHR 而非直接 302 到 API URL）。
- 追加（同日 21:48–21:58，依据 `功能需求清单.md` 8 条需求）：将 `docs/12-joybuy-co-uk-ui-spec.md` 就地修订为**目标状态规格文档**（文档开头新增"修订说明"表 + 全局约定：11 个标准类目、品类发现 6 品类、白名单购买弹窗、钱包余额逻辑；每条修订标注【修订：性质｜需求编号】；文末新增"已删除元素记录"28 项）。修订前现状版已备份到 `var/ui-spec-backup/12-joybuy-co-uk-ui-spec.current-state.md`。本轮新实测：畅销榜单页 /promo/best-seller、头像下拉、详情页下半、Buy now 直达 /checkout 支付页与地址表单弹窗（字段全部核验，未保存任何数据）。
- 追加（同日 21:50–21:58，中文语言复查）：应用户要求把站点切到"中文(简体)-ZH"（Custom settings 抽屉 → Save Changes，当前浏览器会话已为中文）逐项核对需求中文名。结论：需求 8 条的中文名称全部与中文页面对上（秒杀/奥莱/多买多省/JoyPlus会员=首页图标行原文；品类发现含"中国方便食品"；畅销榜单+查看全部；优惠明细/共减/优惠码和优惠券/礼品卡/微信支付=支付页原文；配送至/经常一起购买/立即购买/加入购物车均精确对应）；**重要修正**：需求6-1 的 JoyPlus 模块在中文详情页"购买面板价格行下方"已检出（"JoyPlus 会员享无限免运费; 立即免费试用"，英文采样漏检），文档已从"未检出"改为"已检出"；需求6-2 限购标签中英文均未检出维持原判。中文频道行为 15 项（超市/家居生活/个护家清/家用电器/母婴童玩/电子产品/宠物/美妆/电视与影音/时装配饰/健康保健/汽车及零配件/游戏/世界美食/中华美食）。`docs/12` 已更新（新增"中文语言复查对照"节）。
- 当前任务：让商城端首页贴近真实 Joybuy 主页并填充真实爬取内容做效果展示——已对齐真实首页结构：顶部黑色通知条、红色字标头部（圆搜索按钮+配送至）、"Offers for you" 2×5 活动砖石区（真实图片，替代原红色 hero）、6 个圆形快捷入口、品类发现磁贴行、6 个真实商品楼层（53 商品仅原价、图片全本地化）。浏览器截图对比通过，首页 CMS 现为 v4。
- 新验证纪律（用户 2026-11-03 确定，已写入 `AGENTS.md`）：开发阶段每次任务只做针对性验证（仅覆盖本次改动的模块/文件），全量验证只在功能全部开发完成或用户明确要求时跑。不得每轮默认全量。
- 用户明确分工（上一轮）：原价规则是爬虫职责；“今日送达”标签过滤与 `$` 符号只是页面展示层职责，与爬虫无关。
- 此前任务“Joybuy 中文会话与多语言内容方案”的口径仍然有效：切换国家/语言后所有内容自动刷新，德英混合是正确来源状态；类目分析仍暂停，须用已保存的中文会话重新分析。
- 上一任务“平台管理端全面中文化（仅保留 Joybuy 标识）”已完成并通过验证，历史记录保留在下方。

## 2. 已经完成了什么

### 2026-11-05（图片改本地存储 + 真实上传）

- **用户诉求**：图片存到服务器本地，路径写进 URL，前端直接从本地读图渲染。
- **现状盘点**：项目本来就有完整的媒体库（`MediaAsset` 内容寻址 + `media_url()` + `serve_media_file` + `MEDIA_ROOT=var/media`），**缺的只是上传入口**——所有表单此前只能手填 URL。
- **后端新增**：
  - `media/uploads.py`：`store_upload(file, purpose=...)`。按 purpose 决定 kind 与大小上限；文件内容分块读、超限立即中断（不把大文件整个读进内存）；Pillow 先 `verify()` 再重新解码取尺寸；只放行 **JPEG/PNG/WebP**；像素上限 4000 万防解压炸弹。**不信任客户端 Content-Type 与文件名**。
  - `media.MediaAsset.Kind` 新增 `MERCHANT`（店铺头像桶，路径 `var/media/merchants/...`），迁移 `media/0003`。
  - `merchant_ops/views_media.py`：`POST /api/v1/admin/media` 与 `POST /api/v1/merchant/media`。管理端按 purpose 校验**对应模块**的写权限（商品图要 `catalog.pool.manage`、轮播图要 `cms.banners.manage`……不能互相顶替）；商家端只开放 product/avatar/review 三类。
  - 售后凭证新增 `action="proof"`：只接受 `/media/` 或 http(s) 地址，最多 5 张（挡掉 `javascript:` 之类）。
  - `merchant-listings` 列表与上架响应补 `image`（批量取 `MediaUsage` 主图，避免 N+1）；会话商品信息也改用同一套取图逻辑。
- **前端新增**：
  - `admin-web` / `merchant-web` 各一个 `components/ImageUploader.vue`：点击选图 → `FormData` 上传 → 回填 URL；支持多图、设为主图、移除、单张大小预检、**相同图片不重复追加**（内容寻址会返回同一 URL）。
  - `adminUpload` / `merchantUpload`：**绝对不能手动设 `Content-Type`**，否则浏览器补不了 boundary，后端解析不出文件。
  - **两个 `vite.config.js` 都加了 `/media` 代理**——不加的话 `<img src="/media/...">` 在 5173/5174 直接 404，这是「图能上传但显示不出来」的头号原因。
- **接入的 5 处表单**：A03 商品池图片（最多 5 张，1MB）、A10 轮播图（2MB）、A11 好评评论图（5 张，1MB）、M02 店铺头像（2MB）、M07 售后凭证（5 张，1MB）。
- **数据落点**：业务表仍只存 URL 字符串，不存二进制、不存 asset 外键——换存储或加 CDN 只需改 `media_url()`。
- **本轮修掉的 2 个 bug**：
  1. `adminUpload` 一开始写 `/admin/media`，但管理端 `API_BASE_URL` 已含 `/admin`，实际请求变成 `/api/v1/admin/admin/media` → 404。改成 `/media`。
  2. **M02「保存资料」一直 405**：`merchantWrite('/merchant/profile', ...)` 没传 method，默认 POST，而接口是 PATCH。这个 bug 在第 3 轮就存在，本轮测头像上传才暴露。
- **验证**：
  - `manage.py test merchant_ops.tests.test_media_upload` → **13 passed**（落盘字节与上传一致、URL 形状、去重、非图片/伪装图片、GIF 拒绝、>1MB 413、>4000 万像素拒绝、非法 purpose、缺文件、管理端跨模块权限 403、商家端 banner 用途不开放、受限角色 403、凭证 URL 白名单）；`merchant_ops media` → **134 passed**。
  - **浏览器实测（真实 `input[type=file]`）**：商品池上传后缩略图 `naturalWidth=600`、保存后列表首行图宽 600；轮播图上传预览 220、列表 220；好评评论图上传成功；店铺头像上传后页头头像 600；售后凭证上传 + 保存后凭证区渲染。
  - **渲染巡检**：管理端商品池 20/20 张图加载；商家端商品池卡片 8/8、已上架列表 4/4、会话商品图 480px；**0 个失败请求**。
- **生产部署注意**：`/media/` 由 Nginx 直接 `alias` 到 `var/media/`（`serve_media_file` 只在 `DEBUG` 下注册路由，生产不走 Django）。上传目录需要写权限。

### 2026-11-05（商家/平台后台重构 · 第 3 轮续）：商家端 M03–M10 全部完成

- **交付范围**：M02 店铺管理（顺手补上，接口本来就有）、M03 商品上架中心、M04 订单管理与详情、M05 钱包管理、M06 保证金、M07 售后中心、M08 平台活动与推荐返佣、M09 消息中心、M10 平台通知中心。前端 9 个页面替换掉占位页，后端新增 24 条 `/api/v1/merchant/*` 路由。
- **新增后端文件**：
  - `merchant_ops/views_merchant_catalog.py`（M03）：商品池筛选/搜索/分页 + 上架；
  - `merchant_ops/views_merchant_orders.py`（M04）：列表/详情/发货/导出；
  - `merchant_ops/views_merchant_wallet.py`（M05+M06）：明细/密码/提现/保证金；
  - `merchant_ops/views_merchant_service.py`（M07+M08）：售后处理、活动参与、推荐返佣；
  - `merchant_ops/views_merchant_inbox.py`（M09+M10）：会话与通知；
  - `merchant_ops/management/commands/seed_merchant_demo.py`：本地演示数据（幂等，见下）。
- **新增前端文件**：`CatalogueView` / `OrdersView` / `WalletView` / `DepositView` / `AfterSalesView` / `ActivitiesView` / `MessagesView` / `NotificationsView` / `StoreView`。
- **关键设计（沿用第一轮的合并口径）**：
  - **上架 = 创建/复活一条 `Offer`**：成本价与零售价从 `spu` 快照到 `offer.cost_price/current_price`；平台下架过的商品重新上架时**复用原 Offer**（不新建行），避免唯一约束冲突并保留历史。
  - **上架双校验**：商品必须 `ACTIVE` 且成本/零售价齐全（零售 ≥ 成本），店铺必须 `can_operate`（接单中 + 入驻通过 + 保证金免缴或已缴足）；前端按钮置灰只是提示，服务端仍完整校验。
  - **发货扣成本**复用 `ship_merchant_order`：与钱包流水同事务、`ship:<order>` 幂等、余额不足拒绝。
  - **提现**：先过 6 位钱包密码 → 占用可用余额（负向 `WITHDRAWAL` 流水）→ 待审核。密码错 5 次锁 15 分钟。
  - **售后**：投诉与退货分开；退货类在用户确认收货（子单 `COMPLETED`）后禁止完成；已完成只读；可申请平台介入。
  - **会话与通知分开**：客服会话每店铺一条、列表固定第一；通知含普通与商品好评，打开详情自动已读，好评按「星级 → 文字 → 图片 → 时间」排版。
- **本轮修掉的 4 个真 bug（都是自己写的，不是遗留）**：
  1. **`AppDrawer`/`AppModal` 没有 `open` 属性也没有 `v-if`** —— 抽屉和弹窗内容常驻 DOM，全屏遮罩会把整页盖住。已加 `open` prop + `v-if`。管理端是父级 `v-if` 包裹，所以没暴露；商家端用了 `:open`，必须组件自己判。
  2. **提现金额精度校验永远失败**：`money()` 先把金额量化到 4 位小数，再看 `exponent < -2` 必然成立，任何金额都报「最多 2 位小数」。改成先按原始 `Decimal` 输入判断小数位，再量化。
  3. **钱包密码失败计数被事务回滚**：`raise` 写在 `transaction.atomic()` 里，异常把「+1 次失败」一起滚掉，5 次锁定永远不生效。改成块内只落库、块外再抛。
  4. **seed 的幂等键跨店冲突**：`demo:recharge` 是全局唯一键，第二家店直接复用了第一家的流水，余额没加却去发货 → `INSUFFICIENT_WALLET_BALANCE`。键改成 `demo:recharge:<merchant_id>`。
- **演示数据（本地库）**：
  ```
  ./.venv/Scripts/python.exe backend/manage.py seed_merchant_demo --merchant HOMCOM --reset
  ./.venv/Scripts/python.exe backend/manage.py seed_merchant_demo --merchant CHiQ --reset --with-deposit
  ```
  - 会给商品池**补价格**（120 个 SPU：零售价取该 SPU 在售 Offer 的真实价，成本价按 62% 估算，**仅本地演示**；真实成本必须由平台运营在 A03 录入）；
  - 每家店造 3 个上架商品、20000 充值、三种状态各一单（待处理/已发货/已完成，走真实服务生成流水）、1 个售后退货单、2 个活动（1 个已参与）、2 条通知（普通 + 好评含平台回复）、1 个买家会话、1 条推荐关系与待发放返佣；
  - `--with-deposit` 给该店启用 5000 保证金并缴足，用来让 M06 菜单可见（CHiQ 用了，HOMCOM 保持免缴做对比）。
- **验证（按纪律仅针对性）**：
  - `manage.py test merchant_ops.tests.test_merchant_modules` → **34 passed**（上架重复 409 / 商品无价格 / 店铺不可经营 / 发货扣成本 / 余额不足 / 跨店 404 / 密码 6 位与 5 次锁定 / 提现超余额与精度 / 流水隔离 / 售后状态机 / 活动幂等 / 返佣隔离 / 会话首条客服 / 通知已读与长度校验）。
  - `merchant_ops orders accounts_staff accounts_buyers` → **136 passed**（回归未破）。
  - **浏览器实测**：`/store`、`/catalog`、`/orders`、`/wallet`、`/deposit`、`/after-sales`、`/activities`、`/messages`、`/notifications` 全部标题正确、**0 console 错误、0 失败请求、0 遮罩残留**；两店切换后菜单项从 9 项变 10 项（保证金按 `deposit_enabled` 显隐）。
  - **写链路实测（Playwright 真实点击）**：上架商品成功、发货成功（待处理 1→0、扣成本）、设置钱包密码成功、提现 100.50 创建待审核申请并占用余额、售后进度更新、参与活动、买家消息发送、通知回复 + 全部标记已读。测试后已 `--reset` 恢复演示态。
  - `ruff check/format`、`prettier --check`、`eslint`、`vite build` 全通过。

### 2026-11-05（商家/平台后台重构 · 第 3 轮）：merchant-web 骨架 + M01/M02

- **用户诉求**：问「商家端地址」——此前只有平台管理端，商家端从未建过。
- **新增工程 `merchant-web`**（`pnpm --filter @joybuy/merchant-web dev`）：
  - **http://127.0.0.1:5174**，Vite + Vue3 + vue-router，`/api` 代理到 8000；
  - 主题**独立于管理端**：白底 220px 侧栏 + 品牌红 `#df2636`（原型 `海外电商商家后台.html` 采样：logo 36×36/radius 8、body `#f5f6f8` 14px、卡片 radius 8、顶栏 68px）；
  - 结构：`layouts/MerchantLayout.vue`（侧栏按权限过滤 + 顶部店铺切换）、`composables/useMerchantSession.js`（会话 + 店铺上下文）、`lib/api.js`（自动带 `X-Merchant-Id`）、4 个通用组件。
- **商家身份（关键设计）**：**不新建商家账号表**，复用 `staff_account` 登录（`/api/v1/admin/auth/*`），归属店铺由 `merchant_membership` 决定、可做范围由该 membership 的 `merchant_role` 决定。
  - `MerchantAPIView.initial` 解析 `X-Merchant-Id`；**多店成员必须显式指定店铺**，否则返回 400 `MERCHANT_CONTEXT_REQUIRED`——绝不隐式「取第一个」，否则切店会静默串店；
  - `skip_context = True` 的类（如 `/merchant/shops`）跳过上下文解析；
  - 权限用 `permission_any` / `required_merchant_permissions` 声明，缺权限即 403。
- **新增接口**：`GET /api/v1/merchant/shops`（可选店铺+权限）、`GET /api/v1/merchant/overview`（经营看板）、`GET|PATCH /api/v1/merchant/profile`（店铺资料）。
- **新增权限**：迁移 `merchants/0005` 补 10 个 `merchant.*` 权限码（看板/店铺/上架/订单/钱包/保证金/售后/活动/消息/通知），`merchant_owner` 授满，新增 `merchant_staff` 角色（不含提现）。
- **修复两个真 bug（都是本次才暴露的）**：
  1. **员工会话 Cookie 的 `Path` 是 `/api/v1/admin/`**，所以 `/api/v1/merchant/*` **根本收不到 cookie**，商家端所有接口 401。已改为可配置 `STAFF_SESSION_COOKIE_PATH="/api/v1/"`，并在登出时顺带清理旧 path 的残留 cookie（`STAFF_SESSION_COOKIE_LEGACY_PATHS`）。**这是商家端接不上的根因，不是前端问题。**
  2. **`CSRF_TRUSTED_ORIGINS` 里没有 5174**，Django 的 Origin 校验直接 403 拒绝商家端登录。已补 `http://127.0.0.1:5174`。**以后每加一个前端端口，必须同步这两处配置。**
  3. `MerchantAPIView.handle_exception` 起初只翻译 `MerchantContextError`，`MerchantAdminError`（改店铺名为空）会漏成 500，已一并翻译。
- **演示数据（本地库）**：`admin@joybuy.test` 已绑定 **HOMCOM + CHiQ** 两家店（`merchant_owner`），用来验证多店切换；绑定命令见下方「本地开发登录凭据」。原来误绑的「Joybuy 自营导入」兜底店已解绑。
- **验证（按纪律仅针对性）**：
  - `manage.py test merchant_ops.tests.test_merchant_app` → **13 passed**（单店隐式解析、多店必须指定、跨店 403、无 membership 403、匿名 401、看板只统计本店、7 天柱状图不除零、权限清单、受限角色 403、改店铺名校验）。
  - `merchant_ops accounts_staff accounts_buyers orders` → **102 passed**（回归未破）。
  - **浏览器实测**：登录后落在 `/dashboard`，侧栏实测 **220px / rgb(255,255,255)**、logo `rgb(223,38,54)` 36px/8px、body `#f5f6f8` 14px；菜单 9 项（保证金按 `deposit_enabled=false` 正确隐藏）；6 张统计卡、7 条柱状条、店铺切换显示 HOMCOM/CHiQ；`/orders`、`/wallet`、`/messages` 占位页正常；**0 console 错误、0 失败请求**。
  - `eslint`、`prettier --check`、`vite build` 全通过；根 `package.json` 补 `dev:merchant` / `build:merchant`，并加入 lint/format 范围。

### 2026-11-05（商家/平台后台重构 · 第 2 轮）：A10–A17 全部完成

- **交付范围**：A10 首页轮播图、A11 平台通知推送、A12 客服中心、A13 用户端管理、A14 白名单账号、A15 商家关注与曝光、A16 账号与权限、A17 操作日志。
- **新增 6 张表**（详见 `docs/13-database-schema.md` §13.5）：
  - `home_banner`（**没有并进 `cms_module`**：CMS 是整页版本快照，轮播图要单条开关 + 排序）；
  - `merchant_notification` + `merchant_notification_reply`（**没有复用 `notification_message`**：那张是模板外发队列，站内信需要已读/多轮回复/商品快照）；
  - `support_conversation` + `support_message`（`kind` 区分买家咨询与平台客服，每商家一条平台客服会话）；
  - `buyer_wallet_entry`（买家余额流水）+ `buyer_account.balance/region`。
- **权限模型（A16，重要）**：
  - 不新增表：给每个模块补 `<模块>.view`，`<模块>.manage` **隐式包含** view —— `get_staff_permission_codes` 统一补齐，所以升级后持有 `manage` 的历史角色不会掉菜单；
  - `StaffRbacPermission` 支持 `view.resolve_required_permissions(request)`：GET 走 `view_permissions`、写走 `required_permissions`；`OpsAPIView` 已内置该钩子，第一轮 8 个模块也全部补了 `view_permissions`；
  - 前端 `useStaffAuth` 新增 `canView(module)` / `canWrite(perm)`；侧栏与路由守卫改用 `module` 语义，**只读账号也能看到菜单**；
  - 「账号与权限」保存时按模块勾选生成一个内置角色 `staff-<public_id 前 12 位>`，权限取并集；超级管理员（`is_platform_admin`）不能停用、不能改权限（防自锁）。
- **关键业务规则（已用测试锁死）**：
  - 商品好评**只能推给该店确实已上架的 SPU**，服务端二次校验 `PRODUCT_NOT_LISTED`；
  - 平台回复通知后 `read_at` 置空 → 商家端重新未读；
  - 买家余额不能为负（CHECK + 服务层双重），充值走 `idempotency_key`；
  - 移出白名单**只取消权限**，余额与历史保留；停用账号不能加入白名单；
  - 关注/曝光只做正向累加，调整记录直接读 `audit_log`（不另建日志表）。
- **前端**：新增 8 个页面 `BannersView`/`NotificationsView`/`SupportView`/`WhitelistView`/`GrowthView`/`StaffAccountsView`/`AuditLogsView`，并**重写** `BuyersView`（改用 `/buyers/accounts`）；侧栏按「交易管理 / 资金与风控 / 服务与运营 / 用户与权限 / 采集与基础数据」5 组共 17 项。
- **踩坑补充**：
  1. **老 `/admin/buyers` 接口一直 500**（`account.phone` 但字段是 `phone_e164`），本轮重写页面时改用新接口 `/buyers/accounts`，旧接口也顺手修了。
  2. 新增路由必须放在 `api/v1/<path:unmatched>` 之前 —— `merchant_ops/urls.py` 在 `config/urls.py` 里是 `*merchant_ops_urlpatterns` 展开，位置已在兜底路由之前，安全。
  3. `home_banner` 的图片只存 URL（本地媒体库路径或 https），**没有做上传**，与文档「正式存对象存储」的差距仍在。
- **验证（按纪律仅针对性）**：
  - `manage.py test merchant_ops` → **55 passed**（第二轮新增 26 例：只读账号可读不可写、轮播图校验/开关/删除、通知群发与好评归属校验、回复重新未读、客服会话幂等与状态流转、白名单充值/移出/负数/幂等/停用拦截、关注曝光累加、账号创建校验与保护、审计查询与导出）。
  - 13 个新 GET 接口实库巡检全部 **200**。
  - **浏览器实测**：8 个新页面逐个访问，标题正确、**0 console 错误 / 0 失败请求**，侧栏 17 项；实测「新增轮播图」写入成功、创建只读账号后用该账号登录**侧栏只剩「首页轮播图」且能看列表**（写操作由后端 403 兜底）；测试数据已清理。
  - `ruff check/format`、`prettier --check`、`eslint`、`vitest`（9 passed）、`vite build` 全通过；后端已重启（8000）。

### 2026-11-05（配色纠正）：管理端主题改为深色导航 + 蓝色操作

- **用户反馈**：主题配色不对，要按文档里管理平台的主题配色。
- **根因**：`海外电商平台管理后台.html` 的单个 `<style>` 块里塞了**两套主题**。前段（偏移 0 起）是废弃的红白版：`--red:#dc2638`、`aside{background:#fff;width:222px}`、`.primary{background:#dc2638}`。**后段偏移 12593 处**有一整块 `/* Platform operations console */` 把它整体覆盖。上一轮我只 grep 了第一个匹配，于是照着废弃主题做了白底红字。
- **真实生效主题（已用 getComputedStyle 采样核对）**：
  - `--primary:#2563eb`、`--red` 被改名复用为蓝色、`--ink:#18263b`、`--muted:#78869a`、`--border:#e2e8f0`、`--green:#16856a`、`--bg:#eef2f6`、`--sidebar-width:236px`
  - 侧栏 `#111d32` 深色，品牌区 76px，品牌方块 `#2f6df6` 34×34 radius 7
  - 导航项 `#b7c3d7`，hover `#1b2c47`，选中 `#2456ac` + `inset 3px 0 #73a7ff`
  - 顶栏白色 56px，body 底色 `#eef2f6`，内容区 `padding:22px 24px 32px`
  - 表头 `#f0f4f9` / `#61738e` / 11px；表格斑马 `#fcfdff`，hover `#f3f7ff`
  - 按钮 12px / padding 6px 12px / radius 3；`.primary` = `#2563eb`，hover `#1d4ed8`
  - 标签默认灰 `#f0f3f7/#7b899f`，另 warn / bad / ok 三档
- **改动文件**：`admin-web/src/styles/main.css`（令牌全量替换 + 补回 `page-container/foundation-card/status-grid` 等旧视图依赖的类）、`styles/admin.css`（侧栏/顶栏/卡片/按钮/表格/标签/抽屉/弹窗/时间线全部按采样值重写）、`layouts/AdminLayout.vue`（深色侧栏 + 顶栏头像）、`views/LoginView.vue`（原型登录页：深色径向渐变 + 410px 白卡 + 蓝色按钮，不回显演示密码）。
- **顺带修掉一个预先存在的 500**：`common/admin_views.py` 的 `AdminBuyersView` 用了 `account.phone` / `Q(phone__...)`，但模型字段是 `phone_e164`，`/api/v1/admin/buyers` 一直 500（不是本轮引入，是本轮巡检 `/buyers` 才暴露）。已改字段名并补 `purchase_whitelisted`。
- **验证（按纪律仅针对性）**：
  - **色值对拍**：浏览器 `getComputedStyle` 同时采样原型与本实现，`aside` 背景/宽度、品牌方块、导航选中、顶栏高度、主按钮、body、表头、内容区 padding、`--primary`、`--sidebar-width` **全部逐项一致**。
  - 11 个路由（8 个新页 + 爬虫/内容/买家）逐个访问：标题正确、**0 条 console 错误 / 0 个 4xx-5xx 请求**。
  - 抽屉层叠：宽 880px、白底、遮罩 `rgba(12,24,43,.46)`。
  - `manage.py test merchant_ops orders` → **38 passed**；`prettier --check` / `eslint` / `vitest`（9 passed）/ `vite build` 全通过。
  - 后端已重启（8000），前端 5173 热更新。

### 2026-11-05（商家/平台后台重构 · 第 1 轮）：数据模型 + 平台 A02–A09

- **用户要求**：读 `商家端及平台管理端文档/` 的 `01_商家端开发文档.md`、`02_管理后台开发文档.md`，按 `海外电商平台管理后台.html` / `海外电商商家后台.html` 的设计写两套后台；**文档里的表不能照抄，要按现有 Joybuy 数据结构合并**（已有表就补字段，覆盖不了才新建）。
- **4 个已拍板口径（不要推翻）**：
  1. 商品池 = `catalog.spu`（补 `cost_price`/`retail_price`/`is_activity`/`description`/`image_urls`/`specs`），**不新建 product 表**；
  2. 店铺商品关系 = `offers.offer`（补 `cost_price`/`listed_at`/`removed_at`/`removed_by_platform`），**不新建 merchant_product 表**；
  3. 订单 = 保留 `order` 作买家父单，**新增 `orders.merchant_order`** 按商家拆子单（成本快照、3 状态、8 节点、回款都在子单上）；
  4. 商家端将新建独立 `merchant-web`（**第 2/3 轮做**），登录复用 `staff_account` + `merchant_membership` 判店，不新建商家账号表。
- **新增 11 张表**：`merchant_order`（orders）+ `merchant_wallet_entry`、`merchant_withdrawal`、`merchant_deposit_entry`、`after_sale`、`after_sale_event`、`merchant_activity`、`merchant_activity_participation`、`referral_program`、`merchant_referral`、`referral_commission`（新应用 `merchant_ops`）。文档里的「商家与入驻」合并进 `merchant`（钱包/保证金/信誉/关注/曝光/推荐码等 20 个字段），不单开表。
- **资金口径（后续别再改）**：
  - 所有余额变更只能走 `merchant_ops/services.record_wallet_entry`，余额与流水同事务、`wallet_balance` 有 CHECK ≥ 0；
  - 幂等键统一为 `ship:{子单}` / `settle:{子单}` / `withdrawal-reserve:{申请}` / `withdrawal-return:{申请}` / `commission:{核算}`，**回款、返佣到账、提现退回都只发生一次**；
  - 提现申请时记一笔负向 PENDING 流水占用余额，打回/失败退回一次，**实际出款不再扣一次余额**；
  - 保证金余额可以为 0 或负数、且**不触发封店**（文档明确要求）。
- **接口（全部 `/api/v1/admin` 下，权限码逐个校验 + 写审计）**：
  `merchants`（列表/详情/PATCH/actions/export）、`categories`、`products`（含 actions）、`merchant-options`、`merchant-listings`（actions）、`merchant-orders`（列表/详情/PATCH/actions/export）、`finance/summary|withdrawals|withdrawals/<id>/actions|recharges|ledger|ledger/export|merchants`、`deposits`（actions/entries）、`after-sales`（详情/actions）、`activities`（详情/actions/participations）、`referrals`（program/calculate/commissions/commissions/actions）。
- **新增权限码 14 个 + 3 个角色模板**（`platform_finance`/`platform_operator`/`platform_support`），迁移 `accounts_staff/0003_seed_commerce_permissions`；`platform_admin` 只做权限并集，不回收既有授权。
- **前端重构**：`admin-web` 按原型重做外壳——**236px 深色侧栏 `#111d32`**、76px 品牌区（`#2f6df6` 蓝底方块 + 「寰球优选 / PLATFORM CONSOLE」）、56px 白色顶栏（面包屑 + 标题 + 头像）、`#eef2f6` 底色、**蓝色主操作 `#2563eb`**；新增 `styles/admin.css`（panel/table/tag/drawer/modal/tabs/stat 等）+ `AppDrawer`/`AppModal`/`AppPager`/`StatusTag` 四个通用组件；新增 8 个页面 `MerchantsView`/`ProductPoolView`/`MerchantListingsView`/`MerchantOrdersView`/`FinanceView`/`DepositsView`/`AfterSalesView`/`ActivitiesView`；路由改为「登录后进入第一个有权限模块」，旧页面（爬虫/内容/买家/评价/商品目录）保留可用。
- **踩过的坑（务必不要再踩）**：
  1. **Prettier 会把 `@click="a; b"` 重排成多行、且丢掉分号**，Vue 模板编译器直接报 `Error parsing JavaScript expression`。所有多语句事件处理必须写成**具名函数**（`@click="selectTab(tab.key)"`），不要写内联多语句。
  2. `status` 字段语义在两张表里不同：`spu.status=ACTIVE` 是**可售**，`merchant.onboarding_status=ACTIVE` 是**接单中**。`StatusTag` 默认把 ACTIVE 映射成「接单中」，商品池必须传 `:labels="PRODUCT_STATUS_LABELS"` 覆盖，否则商品列表显示「接单中」。
  3. 商家列表**不能按 `is_system` 过滤**——爬虫识别出的来源店铺也是 `is_system=True`，全过滤会让「全部商家」在新库上一片空白。只排除 `merchant_type=IMPORT_FALLBACK`（技术收纳桶）。
  4. `OpsAPIView` 的域错误翻译必须挂在 `handle_exception`，挂 `dispatch` 会在 DRF 异常链之后抛 `StaffApiError`，没人接住 → 500。
  5. 管理端动作里「发货」是**商家端**职责（`ship_merchant_order` 扣成本、进度到 0），平台 A05 只能对已发货订单推进节点；别在 A05 里加发货按钮。
  6. 改后端代码后必须重启 `runserver --noreload`，否则新路由 404（本次已重启，端口 8000）。
  7. **原型 HTML 的 `<style>` 里有 TWO 套主题，前一套是废弃的**：`海外电商平台管理后台.html` 的 style 块前段是旧红白主题（`--red:#dc2638`、`aside{background:#fff;width:222px}`），**后段 12500 字符处**有一整块 `/* Platform operations console */` 把它整体覆盖成 `--primary:#2563eb` / `--ink:#18263b` / `--bg:#eef2f6` / `--sidebar-width:236px` / `aside{background:#111d32}`。`--red` 这个变量名被保留但值改成了蓝色。**只读前 3000 字符或只取第一个匹配会得到完全错误的白底红字**——这次就是这么错的，用户指出后才纠正。取色必须用浏览器 `getComputedStyle` 采样，不要靠 grep 源码。文档 02 第 11 行「后台采用深色导航与蓝色操作风格」是这条的书面佐证。
  8. 商家端 HTML（`海外电商商家后台.html`）是**另一套**主题（216px 侧栏、`--red:#df2636`），不要和管理端混用。
- **验证（按纪律仅针对性）**：
  - `manage.py test merchant_ops` → **29 passed**（商家审核/保证金/信誉/封店解封、商品池价格校验、下架幂等、发货扣成本、一键完成只回款一次、节点不可回退、下单时间≤首节点、提现打回只退一次、出款不再扣余额、保证金负值、售后结案与退货限制、返佣阶梯校验与发放幂等、幂等键、权限 403）。
  - `ruff check` + `ruff format` 通过；`prettier --check` / `eslint` / `vitest`（9 passed）/ `vite build` 通过。
  - **真实接口巡检**：用临时员工会话对 17 个新 GET 接口逐个请求，全部 200；商家列表返回 7 条（含待发货聚合）。
  - **浏览器实测（Playwright 驱动本机 Chrome）**：登录后 8 个页面逐个访问，侧栏实测 `222px`、标题正确、表格有数据或正确空态、**0 条 console 错误**；并实测「创建活动」「新增商品」两个写链路成功（CSRF 正常），测试数据已清理。
- **遗留 / 下一轮**：
  - 第 2 轮：A10 轮播图、A11 通知推送、A12 客服中心、A13 用户端管理、A14 白名单、A15 关注曝光、A16 账号与权限（逐模块 read/write UI）、A17 操作日志；
  - 第 3 轮：`merchant-web` 新建（端口 5174，216px 侧栏）+ 商家端 M01–M10 + `/api/v1/merchant/*` 与商家上下文中间件；
  - 商品池详情页的 SKU/图片仍以媒体库为准，后台只维护 `image_urls`/`specs` 文本，图片上传到对象存储尚未做；
  - `AdminOrdersView`（旧 `/admin/orders`）与新的 `merchant-orders` 并存，前者是买家订单视角，本轮未改。

### 2026-11-05（补充 11）：运行日志细化到「URL → 拿到的数据 → 处理结果 → 落盘路径」

- **用户要求**：运行日志不够详细，希望把访问的 URL、获取到的数据、处理过的数据、存入路径都打出来。
- **新增 4 条日志（每个商品固定 3 条，形成完整链路）**：
  - `LISTING_FETCHED`（列表页）：URL、HTTP 状态、响应大小 KB、耗时、卡片数、本轮入队/重复跳过/超上限/非商品卡片数、累计入队进度；
  - `PRODUCT_PARSED`（详情页）：URL、HTTP 状态、响应大小、耗时、商品 ID + 标题、原价 + 币种、SKU 数、图片数、评分/条数（或"暂无评分"）、分类路径、AI 摘要字数；
  - `DATASET_SAVED`：`var/crawl_exports/{任务目录}/{类目}/{商品ID}`、`product.json`、主图/详情图张数、失败图片数、内容是否变化；
  - `PRODUCT_IMPORTED`（增强）：SPU（新建/更新）、SKU 数、Offer 数、暂存记录 ID。
- **配套**：`dataset.save_product` 返回值新增 `product_dir`；详情接口事件条数 50 → **200**，前端标题同步「最近 200 条」；`locale.js` 补 `LISTING_FETCHED` / `PRODUCT_PARSED` / `DATASET_SAVED` 中文标签，`PRODUCT_IMPORTED` 改叫「商品已入库」。
- **顺手修掉一个会致命 bug**：`parse_detail` 里 `record_run_event` 在 `if` 分支内被导入，导致它是函数局部变量、成功路径未赋值 → **每个详情页都会 `UnboundLocalError`**。已改为函数顶部导入，并加回归测试（`SpiderLoggingTests` 覆盖详情/列表两条路径）。
- **验证（按纪律仅针对性）**：
  - `manage.py test crawler_control` → **166 passed**（新增 3 例：`DATASET_SAVED` 带落盘路径、`PRODUCT_PARSED` 带 URL 与字段概要、`LISTING_FETCHED` 带卡片计数）。
  - **真实页面实测**：用归档详情页跑 `parse_detail`，产出日志「详情页已解析 https://…/100026175251161（HTTP 200，687.4 KB，耗时 3.4s）；商品 100026175251161「3000W 1.7L Rapid Boil Kettle…」，原价 179.99 GBP，SKU 1 个，图片 20 张，暂无评分，分类 Home Appliances / Small Kitchen Appliances。」
  - ruff / format / prettier / eslint / `vite build` 全通过；后端已重启。
- **注意**：日志粒度变细后事件量约为「每商品 3 条」，任务详情仍按 `created_at` 倒序取最近 200 条；长任务早期的日志会被挤出这个窗口（数据仍在库里，可直接查 `CrawlRunEvent`）。

### 2026-11-05（补充 10）：任务仍报「登录墙」——查出两个真 bug

- **用户反馈**：最新任务仍然检测到登录墙，怀疑到底有没有带 Cookie。
- **先证明 Cookie 是真的**：把最新运行（`3ba556b3`，19:37）账号 `任务账号01` 的会话解出来，用同一批 Cookie 直接 curl 列表页 → **200**；不带 Cookie → 307 跳 `/login`。所以账号会话有效，问题不在凭据。
- **Bug A（根因）：HTTP 缓存把匿名请求的 307 缓存了。**
  - Scrapy 默认 `DummyPolicy` 会缓存除 5xx 外的所有状态码，**包括 307**；而缓存键是 URL fingerprint，**不含 Cookie**。
  - 17:50 那次匿名运行把 `307 → /login` 存在 `https://www.joybuy.co.uk/s?k=Kettles%20%26%20Toasters` 上，有效期 6 小时。19:37 那次带着有效 Cookie 运行，**直接命中缓存、一次网络请求都没发**，于是继续报"登录墙"，`RENDERED_OK` 渲染的还是缓存里的登录页。
  - 证据：`var/cache/scrapy/joybuy_run/` 的 `meta` 里有 `'status': 307` 的条目；19:37 那次运行没有产生任何新缓存条目。
  - 修复：新增 `crawler/joybuy_crawler/cache_policy.py::SuccessOnlyCachePolicy`（只缓存 200，且不缓存被判为登录墙/风控页的响应），`settings` 里挂 `HTTPCACHE_POLICY`；并清掉了 4 条中毒缓存（2 条 307 + 2 条登录页）。
- **Bug B：列表页改版导致解析出空标题/无价格。**
  - 新布局里卡片是 `div[class*="product_card"]`，`a[class*="image_wrapper"]` **内部没有文字**，标题在 `[class*="style_title"]`、价格在 `[class*="crossOffPrice"]` / `[class*="mainPriceText"]`（而且价格被拆成 `£ 32 . 33` 多个文本节点）。
  - 旧解析器只遍历 `a[href*="/dp/"]`，于是 40 张卡片全是空标题、无价格（`check_listing_entry` 随后按"标题过短"把它们全丢掉）。
  - 修复：`parse_uk_listing` 改为**卡片优先 + 锚点回退**双布局；`_price` 先合并小数间空格；新增 fixture `crawler/fixtures/listing_cards_v2.html`。
- **端到端验证（真实网络）**：用该运行的同一套 settings（账号池 + Cookie 中间件 + 新缓存策略）实抓 `https://www.joybuy.co.uk/s?k=Kettles`：
  - `status=200`、`Cookie` 请求头 2599 字节、`httpcache/miss=2`（真的发了网络请求）；
  - 解析 **40 张卡片，40/40 有标题、40/40 有原价**（如 `KOMORE 2000W… | 35.99`）。
- **测试**：`crawler_control` **163 passed**（新增缓存策略 4 例 + 列表卡片布局 3 例）；ruff / format 通过。
- **文档**：`docs/05` §8 增"只缓存 200"及事故说明、新增 §8.1 缓存策略与排查提示、新增 §9.3 列表两套布局。
- **安全**：排查时落盘的明文 Cookie 临时文件与页面快照已删除（`var/joybuy_demo/bin/_cookie_header.txt`、`_listing.html`）。
- **待用户处理**：直接重跑任务即可（缓存已清、策略已换、解析器已修）。若仍失败，先在任务详情看第一条事件：出现 `LOGIN_WALL_FALLBACK` 且 URL 是 `/login?...` 说明是服务端判定，需要确认账号是否在网页端被登出。

### 2026-11-05（补充 9）：账号组实体化 + 账号可编辑/可删除

- **用户要求**：账号可编辑、可改账号组；新增账号时账号组要下拉选择；要有「新增账号组」；账号要能删除。
- **改动**：
  - 迁移 `0007_crawler_account_groups_and_soft_delete`：新增 `CrawlerAccountGroup`（`name` 唯一 + `note`）、`CrawlerAccount.deleted_at`；`0008_seed_crawler_account_groups` 把历史账号的组名回填成组记录（含 `default`）。实库已执行，组 = `['default', '数据抓取']`。
  - 服务层：`ensure_account_group` / `create_account_group` / `list_account_groups` / `update_crawler_account` / `delete_crawler_account`；`create_crawler_account` 现在会补建组记录（API/脚本传新组名不会失败）。
  - 删除是**软删除**：`deleted_at` 置位、状态 `DISABLED`、`session_cipher` 清空、会话状态回 `UNKNOWN`；行保留（`CrawlRun.account` 是 SET_NULL，硬删会让历史运行丢失"当时用哪个账号"）；运行中的任务占用该账号时拒绝删除（409）。
  - 选号/账号池/列表/动作/登录命令全部加 `deleted_at__isnull=True` 过滤。
  - 接口：`GET/POST /crawlers/account-groups`、`PUT|PATCH /crawlers/accounts/<uuid>`、`DELETE /crawlers/accounts/<uuid>`，全部写审计。
  - 管理端：新增/编辑账号的「账号组」改下拉（显示每组账号数）+「新增账号组」内联表单；账号行加「编辑」「删除」；编辑用表格上方的内联表单。**另外给「新建任务」表单补了「账号组」下拉**——否则新建的组在任务侧用不上（任务原本只会落 `default`）。
- **验证（按纪律仅针对性）**：
  - `manage.py test crawler_control` → **156 passed**（新增 8 例：组列表/建组/重名拒绝/空名拒绝、编辑 label+组+备注、空名拒绝、删除后列表消失且会话清空、删除后编辑与动作 404、运行中拒绝删除、软删除保留运行归属）。
  - `ruff check` / `ruff format` 全部通过；`prettier`、`eslint`、`vitest` 9 passed、`vite build` 通过。
  - 迁移已在实库执行；后端已重启，`/api/v1/health` 正常，未登录访问 `account-groups` 返回 401（说明路由已注册、鉴权生效）。
- **设计取舍**：账号组仍以**名称**软引用（`CrawlerAccount.account_group` 与 `CrawlJob.account_group` 都是字符串），没有改成外键——任务侧改 FK 牵扯面大且没有收益；改组名不会级联，需要时先改组内账号。

### 2026-11-05（补充 8）：多账号不定时换号抓取

- **用户决定**：本地对话确认「账号有很多，需要利用多个账号不定时换号抓取数据」，并要求把 `docs/05` 里冲突的条目改掉、以对话口径为准。**注意**：上一轮我建议不做"换号规避风控"，用户已明确否决该建议并拍板，本实现按其决定落地；后续会话不要再按旧文档口径劝阻。
- **实现**：
  - 新模块 `crawler/joybuy_crawler/account_rotation.py`：`AccountPool` 管理「一段班次」的随机预算——时间 `CRAWL_ACCOUNT_ROTATE_MIN/MAX_SECONDS`（默认 300~900 秒）与请求数 `MIN/MAX_REQUESTS`（默认 20~60），**先到者触发换号**，每段重新抽取所以节奏不固定；每次换号重置该账号的班次计数（否则回到旧账号会立刻再触发）。
  - `account_session.load_account_pool()`：从 `services.usable_accounts_for_run()` 取池（指定账号优先 → 同组 ACTIVE+VALID 且会话里真有 Cookie 的账号，LRU 序，上限 50），解密后转成纯 dict 记录（便于单测，不依赖 ORM）。
  - `middlewares.AccountCookieMiddleware` 重写：优先 550、按 pool 注入**当前活跃账号**的 Cookie；换号时写 `ACCOUNT_ROTATED`；池空写 `ACCOUNT_POOL_EMPTY`；池就绪写 `ACCOUNT_POOL_READY`。
  - **Scrapy 全局 CookieJar 关闭**（`runner` 里 `COOKIES_ENABLED=False`）：否则两个账号的 Cookie 会混进同一个 jar 一起发出去，这是换号最容易踩的坑。
  - **连带坑（已踩）**：`CookiesMiddleware` 关掉后，`Request.cookies` 不再被翻译成 `Cookie` 请求头，中间件必须自己写头。第一版写成 `request.cookies = merged`，等于抓取静默变匿名；已改为直接写 `request.headers["Cookie"]`，测试也改成断言请求头。
  - 风控命中即换号：`RiskControlRenderMiddleware` 判定风控页后把当前账号 `mark_blocked()` 移出本轮池子并切到下一个，写 `ACCOUNT_RISK_ROTATED`(WARNING)；全池 blocked 写 `ACCOUNT_POOL_EXHAUSTED`(ERROR)。浏览器回退改用**当前活跃账号**的 Cookie，保证同一页面 HTTP 与浏览器是同一个身份。
  - 前端 `locale.js` 补 5 个事件码中文标签（账号池就绪/已换号/命中风控已换号/账号池已耗尽/无可用账号）。
- **文档（用户要求以对话为准）**：
  - `docs/05` §7.2 用户已自行改为「被中断任务**能**自动切换其他账号接管」；
  - §8「不为提高吞吐量轮换账号、代理或指纹」→ 改为「账号可在池内轮换，但只换身份：不轮换代理、不伪造设备指纹、不提高全局总速率」；
  - 新增 §7.5 账号池轮换（目标、池构成、换号时机、隔离与安全、风控处理、事件表、环境变量、**已知限制**）；
  - §7.4 关于 Cookie 注入/解密的描述同步为"当前活跃账号 / 按账号各解一次"；`crawler/README.md` 采集口径补账号轮换一条。
- **验证（按纪律仅针对性）**：
  - `manage.py test crawler_control` → **146 passed**；新增 `AccountRotationTests`（按请求预算换号、按时间预算换号、每段预算会变、Cookie 不串号、blocked 账号永不复用、全 blocked 返回 None、单账号不轮换）与改写的 `AccountCookieTests`（活跃账号 Cookie 注入、请求级 Cookie 优先、无账号不发 Cookie）。
  - `ruff check` / `ruff format` 全部通过。
  - **真实库探针**：`default` 组 → 无可用账号；`数据抓取` 组 → `['任务账号01']`，池大小 1、不可轮换（符合预期，单账号不换号）。
  - 后端已重启，`/api/v1/health` 正常。
- **实际生效前提（重要）**：现在库里只有 1 个可用账号，所以**轮换还不会发生**。要真正跑起来多账号：把多个账号归到同一 `account_group`（或建任务时选同一组的账号），并各自完成一次人工登录让会话里带 Cookie；任务详情里看到 `ACCOUNT_POOL_READY` 且账号数 > 1 才说明池子生效。
- **已知限制**（已写进 §7.5，别再当 bug 排查）：所有账号共用同一出口 IP 与浏览器指纹；会话 Cookie 用登录快照、抓取中不跟随 `Set-Cookie` 更新（宁可少刷新也不让令牌串号）。

### 2026-11-05（补充 7）：爬虫账号是否真的在访问中被使用（账号绑定修复）

- **用户提问**：抓取时有没有带爬虫账号？建任务时也没让选账号。
- **排查结论（三个真问题，全部已修）**：
  1. **建任务没有账号入口**：`AdminCrawlJobsView.post` 完全忽略了 `account_group`，所有任务都被写成 `default` 组；界面上也没有任何账号字段。
  2. **HTTP 请求是匿名的**：`RiskControlRenderMiddleware._load_account_cookies` 只在"检测到登录墙 → 换 DrissionPage 重抓"这一步把 Cookie 给浏览器；Scrapy 的普通 HTTP 请求从来不带你账号的 Cookie。所以每页都先撞一次 307 → `/login`，再开浏览器重抓，慢且触发风控。
  3. **"假 VALID"账号**：`Joybuy homepage demo` 的会话载荷是 `{"joybuy_session": "public-homepage-demo"}`（演示命令伪造的占位串），却被标记 `session_status=VALID`。默认组里只有它"有效"，于是所有任务都绑到一个**实际 0 条 Cookie** 的账号上。真正可用的 `任务账号01`（数据抓取组，42 条 Cookie）从来没被任何任务用过。
- **改动**：
  - 迁移 `crawler_control/0006_crawljob_pinned_account`：`CrawlJob.account` FK（null=True），建任务可指定账号；不指定则按 `account_group` 自动选。
  - `services._resolve_account_for_run` / `_account_is_usable` / `_account_unusable_reason`：指定账号可用就用；不可用**不静默失败**，写 `ACCOUNT_FALLBACK`(WARNING) 说明具体原因再回退组内选号；选到账号写 `RUN_ACCOUNT_SELECTED`(INFO)「本轮使用爬虫账号「X」（账号组 Y）」。
  - **可用性判定加严**：`ACTIVE` + `VALID` + 有密文 **+ 解出来真的含 Cookie**。占位会话不再会被选中。
  - `AdminCrawlJobsView.post` 接收 `account_public_id`/`account_group`（未知账号 404、非 ACTIVE 400），`GET` 列表与详情返回账号；详情每个 run 带 `account_label`。
  - **抓取侧**新增 `crawler/joybuy_crawler/account_session.py`（`load_account_cookies` / `joybuy_cookie_pairs`）+ `middlewares.AccountCookieMiddleware`（优先级 550，早于 Scrapy CookiesMiddleware 700），把账号 Cookie 注入**每一个请求**；只回放 `joybuy` 域 Cookie，第三方（Facebook）绝不发给源站；浏览器回退复用同一份 Cookie。
  - 演示命令 `load_joybuy_demo` / `load_uk_bestsellers_demo` **不再伪造 VALID 会话**（它们只导入 fixture、从不抓取；`start_run` 本来支持无账号运行）。
  - 管理端：建任务表单加「爬虫账号」下拉（默认「自动（按账号组挑可用账号）」，列出 ACTIVE 账号及其会话状态），任务详情加「爬虫账号」，运行记录表加「账号」列。
- **实测（真实库数据）**：
  ```
  Joybuy homepage demo  group=default  session=VALID   -> 会话里没有可用 Cookie，需要重新登录（实际 0 条）
  FB 主账号              group=default  session=UNKNOWN -> 会话状态为 UNKNOWN（实际 0 条）
  任务账号01             group=数据抓取  session=VALID   -> 可用（实际可回放 30 条 joybuy Cookie）
  组 default: 【无可用账号 → 匿名抓取】     组 数据抓取: 任务账号01
  ```
- **验证（按纪律仅针对性）**：
  - `manage.py test crawler_control` → **139 passed**（新增 `test_crawler_account_binding.py` 17 例：指定账号优先、过期/占位账号回退并说明原因、组内无号匿名启动、第三方 Cookie 不回流、请求级 Cookie 优先、API 指定/拒绝账号）。
  - `ruff check` / `ruff format` 全部通过；`prettier --check`、`eslint`、`vitest` 9 passed；`vite build` 通过。
  - 迁移已执行（`crawler_control.0006` 应用成功）；后端已用新代码重启，三端口（8000/5173/3000）与 `/api/v1/health` 正常。
- **待用户处理（不是代码问题）**：
  - `default` 组目前**没有可用账号**，跑任务会匿名抓取。若要用登录态抓取，给任务选 `任务账号01`（数据抓取组），或给 default 组账号重新走一次「登录」。
  - `Joybuy homepage demo` 这个占位账号建议删除或重新登录；它现在会被判定为"会话里没有可用 Cookie"并拒绝选中。
  - `docs/05` §7.3 写着"所有页面抓取优先走真实 Chrome"，与实现（Scrapy HTTP 优先、撞墙才回退浏览器）不一致，属历史遗留口径，本次未改。

### 2026-11-05（补充 6）：任务详情「运行日志」中文化

- **用户反馈**：爬虫任务的任务详情里，日志打印的是英文，要改成中文。
- **改法分两层**（这是以后加事件时必须遵守的约定）：
  - **后端 `message` 全部改中文**：`crawler/joybuy_crawler/{pipelines,runner,middlewares,spiders/joybuy_run,quality}.py`、`backend/crawler_control/{services,import_services}.py` 里所有 `record_run_event(message=...)`、`complete_run_failed(reason=...)`、`logger.*` 文案。覆盖 20 个事件码（`RUN_STARTED`/`RUN_UNAUTHENTICATED`/`RUN_FAILED`/`RECORD_REJECTED`/`RECORD_FLAGGED`/`PRODUCT_IMPORTED`/`DATASET_SUMMARY`/`DATASET_WRITE_FAILED`/`STAGING_FAILED`/`IMPORT_REJECTED`/`IMPORT_FAILED`/`LISTING_*`/`DETAIL_*`/`RENDER*`/`RISK_CONTROL_FALLBACK`/`LOGIN_WALL_FALLBACK`/`PRICE_ANOMALY_*`）。
  - **`code` 与字段名保持英文常量**：code 是排障检索标识，字段名是 payload 键，翻译会毁掉可检索性。中文短标签放前端 `admin-web/src/lib/locale.js` 的 `EVENT_CODE_LABELS` + `eventCodeLabel()`，原始 code 挂在 `title` 提示里；事件级别 `INFO/WARNING/ERROR` 用 `valueLabel()` 显示为「信息/警告/错误」。
- **前端**：`CrawlersView.vue` 详情抽屉标题「事件流（最近 50 条）」→「运行日志（最近 50 条）」，空态「暂无事件」→「暂无日志」，级别与事件码中文化。
- **顺带**：`quality.Violation.as_log_line()` 改成中文格式 `[CODE] 字段：说明（致命/警告）`，因此单条被拒商品的日志整行可读；`StagingImportRejected` 与 `staging.error_message`（缺必填字段）也一并中文化。
- **边界（有意为之）**：`crawler/joybuy_crawler/core/http_client.py`、`core/browser.py` 的传输级日志仍是英文——那是请求/响应 dump，不是运维事件流；已在 `docs/05` §11.3 写明这条界线。
- **验证（按纪律仅针对性）**：
  - `manage.py test crawler_control` → **124 passed**（含把 `OutcomeReportingTests` 的断言改成中文格式）。
  - `ruff check` + `ruff format` 8 个改动 Python 文件通过；`prettier --check` + `eslint` 两个前端文件通过。
  - `vitest run --config admin-web/vitest.config.js` → 9 passed；`npx vite build`（admin-web）→ 53 modules，构建通过（证明模板/导入无语法问题）。
  - 文案抽查：守卫告警输出「3/3 个商品拿不到可用价格。价格选择器很可能在页面改版后失效…」；记录汇总输出「[TITLE_TOO_SHORT] title：标题 'Buy' 少于 5 个字符（致命）；[PRICE_NOT_POSITIVE] current_price：解析出的价格为 0…」；前端 `valueLabel('INFO')→信息`、`eventCodeLabel('RECORD_REJECTED')→记录被拒（未入库）`、未知码原样透传。
  - **后端已用新代码重启**（`--noreload` 必须重启），重启后 `/api/v1/health` 正常。
- **遗留**：数据库里 **43 条历史事件中有 35 条是英文**（改动前产生的），界面打开旧运行记录仍会看到英文。是否按事件码回填翻译属于"改历史数据"，**未做**，需用户确认；新产生的日志一律中文。

### 2026-11-05（补充 5）：本机全服务启动（运维，无代码改动）

- 启动前核过端口：8000 / 5173 / 3000 均空闲，没有残留 runserver（避免又踩"改了没生效"的坑）。
- 基础设施已在跑（`docker ps`）：`joybuy-dev-mysql-1`（127.0.0.1:33060）、`joybuy-dev-redis-1`（127.0.0.1:63790）、`joybuy-dev-mailpit-1`（8025/1025），均 healthy，本次未重启。
- 启动命令（三条，均为后台任务）：
  - 后端：`./.venv/Scripts/python.exe backend/manage.py runserver 127.0.0.1:8000 --noreload`
  - 管理端：`pnpm --filter @joybuy/admin-web dev`（vite 127.0.0.1:5173）
  - 商城端：`pnpm --filter @joybuy/storefront dev`（nuxt 127.0.0.1:3000，`predev` 会先 `nuxt cleanup`，首启约 30s）
- 验证：
  - `netstat` 三个端口都在 LISTENING（8000→PID 31876，5173→39616，3000→19768）；
  - `curl --noproxy '*'`：`/admin/login/` 200、`127.0.0.1:5173/` 200、`127.0.0.1:3000/` 200；
  - `/api/v1/health` 返回 `{"status":"ok", database ok, cache ok}`；
  - 商城端首页渲染时已实际打通后端：`/api/v1/storefront/home` 200、`/api/v1/categories` 200、`/api/v1/search` 200。
- 容易踩的点：**健康检查路径是 `/api/v1/health`，不带尾部斜杠**（带斜杠会 404，别误判成服务没起）；本机调 localhost 必须 `curl --noproxy '*'`，否则会被环境里的死代理劫持。

### 2026-11-05（补充 4）：评价只采聚合 + 分类只到二级

- **用户两条口径**：① 不再爬评价内容，只爬评分聚合（1~5 分各自数量、平均分、x 条评价）与右侧【内容由人工智能总结自用户评价】的内容（**有就爬，没有就不写**）；② 商品子分类展示过多时只保留前两级（`首页/母婴用品/健康护理/湿巾及配件/湿巾/商品名` → `母婴用品/健康护理`）。
- **现场结构（靠归档页确认，不是猜的）**：参考页 `…/dp/…/10524192` 匿名访问 **307 跳 /login**，抓不到；改用 `var/raw/2026/11/04/…/8dd804f5….gz`（真实 kettle 详情页 702KB）逆向出评价结构：
  - 评价区块是 flight 里的**一个扁平对象**，形如 `{"commentCount":…,"star":"4.8","starShow":"4.8","aiSummary":null,"aiTagTitle":null,"aiTagList":null,"totalCommentCount":47,"ratingInfo":"$19c"}`；
  - `ratingInfo` **不是内联对象而是引用** `"$19c"`，真值在同文件的 `19c:{…}` 槽位；槽内字段 `score1Count`…`score5Count`、`averageScore`、`commentCount` 就是需求要的 1~5 分数量/平均分/条数；
  - `aiSummary` 就是"内容由人工智能总结自用户评价"的正文，`aiTagTitle`/`aiTagList` 是标题与标签；无评价的页面这几项为 `null`。
- **解析器改动（`crawler/joybuy_crawler/parsers/joybuy_uk.py`）**：
  - 新增 `_flight_text()`（改用 `json.loads('"…"')` 解码，**不再用 `unicode_escape`**，否则中文摘要会乱码）、`_flight_ref()`（解析 `$19c` 槽位引用，支持多跳）、`_flight_key()`；
  - 新增 `_extract_flight_review()`：**锚定"包含 `ratingInfo` 的那个大括号对象"**再读字段。**不要全局搜 `aiSummary`**——i18n 文案里有同名字段，会取到错值；
  - 平均分取 `star`/`starShow`，只有 count>0 时才回落 `averageScore`（**真实页面在 0 条评价时把 `averageScore` 默认成 5**，直接取会凭空造出 5 分）；
  - `_extract_dom_review()` 只兜底 AI 摘要正文；**星分布明确不做 DOM 猜测**（宁可留空也不按进度条宽度推算）；
  - `truncate_breadcrumbs()`（`BREADCRUMB_DEPTH=2`）在解析阶段截断，按 `home/首页/主页/首頁` 丢掉站点根；
  - payload 新增 `rating_distribution` / `rating_source` / `ai_summary` / `ai_summary_title` / `ai_summary_tags`，native 块里 `rating` 带 `distribution`，摘要只在非空时挂 `aiReviewSummary`（**没有就是不存在这个 key，不留空壳**）。
- **新增 fixture**：`crawler/fixtures/product_detail_reviews_v2.html`（按归档页结构构造：6 级面包屑 + `$19c` 引用 + 中文摘要 + 标签，数值 47 条 / 4.8 分 / 1-1-2-9-34）。生成脚本在 `var/joybuy_demo/bin/gen_review_fixture.py`（临时，不入库）。
- **新增测试** `backend/crawler_control/tests/test_crawler_review_aggregates.py`（9 例）：星分布且**各档之和 == 总条数**、无评价时不造平均分、摘要存在/不存在两态、无评价正文进入 payload、面包屑 2 级截断（中英站点根、短 trail、payload 里深层分类消失）。
- **文档**：`docs/05` §4（评价目标数/评价媒体标注停用）、§9.2（类目层级口径）、§10（评价采集口径整节重写）；`crawler/README.md` 增"采集口径（2026-11-05）"。
- **验证（按纪律仅针对性）**：
  - `manage.py test crawler_control.tests.test_crawler_review_aggregates` → **9 passed**。
  - `manage.py test test_crawler_review_aggregates test_crawler_field_rules test_crawler_rebuild test_crawler_runtime test_crawl_jobs_api` → **71 passed**。
  - **真实归档页回放**（不靠构造数据）：kettle 详情页解析出 `Home Appliances / Small Kitchen Appliances` 两级、`rating_source=flight`、`count=0` 且分布全 0、`aiSummary=''`（该页确实无评价无摘要）——与页面实际状态一致，没有编造。
  - `ruff check` 3 个改动文件通过，`ruff format` 已执行。
- **未做 / 下次注意**：
  - **没有真实跑在线抓取**（站点 307 登录墙），"有评价+有摘要"的形态是用归档结构构造的 fixture 验证的；等有登录态账号实抓一次后应核对一次真值。
  - 后端 `reviews` 应用与 `joybuy_crawler/sampling.py`（WP-17 评价导入/抽样）**代码仍在**，只是爬虫不再供数；是否整体下线评价模块属于另一个决策，未在本次范围内，**不要顺手删**。
  - `CrawlJob.review_target` / `download_review_media` 两个模型字段仍在库和迁移里（只改了文档口径），清理需要新迁移，未做。
  - 面包屑的 `cid` 提取在真实页面上一直为空（href 里没有 `l1/cid` 参数），所以 `source_category_id` 实际为空、导入走兜底类目——这是**旧有现状**，本次截断不改变它。

### 2026-11-05（补充 3）：爬虫记录级质量层（文章对照后补的缺口）

- **来源**：用户给了一篇商城爬虫实战文章（`https://blog.csdn.net/weixin_29913663/article/details/166029197`），要求"结合当前框架优化"。对照后发现项目**已有**这些：原始响应 gzip 归档（`RawArchivePipeline` + 中间件里 `record_raw_response`，30 天）、退避重试（`RETRY_HTTP_CODES` + `core/policies.py`）、批级缺失率闸门（`evaluate_batch_quality`）、列表页 `seen_product_ids` 去重、带宽/并发克制（`CONCURRENT_REQUESTS=2`）。**真正的缺口**是文章强调的另外三件事，本次已补。
- **新文件 `crawler/joybuy_crawler/quality.py`**（纯函数，无 Scrapy/Django 依赖，可脱离数据库单测）：
  - `apply_product_rules(payload, source_url=)` 返回 `(清洗后的 payload, RuleOutcome)`；**输入 dict 永不被修改**。
  - 致命项（丢弃）：`source_id` 缺失/不合规、标题去空白后 < 5 字、`current_price` 解析不出数字、**价格为 0 或负**、价格超出 `0.01~100000`、币种不是 3 位字母、`skus` 为空、来源 URL host 不是 `joybuy.co.uk` 或路径不含 `/dp/`。
  - 警告项（放行并上报）：标题 > 500 字、标题含广告词（`sponsored`/`advertisement`/`hot sale`/`为你推荐`/`热推`/`广告`）、个别 SKU 价格坏、非 `joy-sourcing.com` 域的图片（**并且真的从 payload 里删掉**，不会写入 dataset、不会从陌生源下载）、`mainPrice > crossOffPrice`（两个价格选择器串位）。
  - `check_listing_entry(title=, source_url=)`：列表页卡片级判定，标题过短 / 含广告标记 / URL 取不到商品 ID 的卡片丢弃，**不再占用每个类目的商品配额**（文章提到的"推荐位污染选择器"在本站的具体形态就是这类 `/dp/` 广告砖）。
  - `PriceDistributionGuard`：运行级守卫，样本 ≥3 且不可用价格 ≥50% → `PRICE_ANOMALY_MISSING`(ERROR)；样本 ≥3 且所有有效价格相同 → `PRICE_ANOMALY_UNIFORM`(WARNING)。
- **新管线 `pipelines.RecordRulePipeline`**（`runner._run_settings` 注册优先级 **150**，`StagingPipeline` 是 200）：
  - 致命违规 → `update_run_progress(failed=1)` + `RECORD_REJECTED`(ERROR) 事件 + `raise DropItem`，item 不会到达 dataset/staging/业务表；
  - 警告 → `RECORD_FLAGGED`(WARNING) 事件，`payload["rule_warnings"]` 带上违规码继续走；
  - `spider_closed` 里把守卫判词写成一条运行级事件。**只上报事件、不改变任务状态**——"这一轮是否算失败"仍由 `complete_run_failed` 既有规则决定，避免把"价格可疑但可用"直接判死。
- **列表页**（`spiders/joybuy_run.py`）：`parse_listing` 先用 `check_listing_entry` 过滤，被丢的条数与原因汇总成 `LISTING_CARDS_REJECTED`(WARNING) 事件。
- **数据集增量**（`dataset.py`）：每个商品目录新增 `meta.json`（`payload_sha256`/`first_captured_at`/`last_captured_at`/`capture_count`/`changed`）；`product.json` 与图片**每次都重写**（原始快照永不丢），`dataset_index.jsonl` **只在指纹变化或首次落盘时追加**，重复抓同一商品不再刷重复行。`StagingPipeline` 收尾写 `DATASET_SUMMARY` 事件汇报"刷新 N 个目录 / 其中 M 条真的变了"。
- **`settings.py`**：显式写明 `RANDOMIZE_DOWNLOAD_DELAY = True`（Scrapy 默认就是 True，之前靠隐式默认）。**没有**再加一层自定义 jitter 中间件——`DOWNLOAD_DELAY` 已经被随机成 0.5~1.5x，再叠一层只是在 reactor 里多一次无意义等待。
- **实测（真实数据回放，最有说服力的一条）**：`var/joybuy_demo/bin/probe_record_rules.py`（临时探针，`var/` 不入库）遍历 `var/crawl_exports/*/*/*/product.json` 共 9 份真实抓取 payload → **6 份正常商品（米家咖啡机 92.99、ochama 咖啡机 49.99、Kettle 29.99 等）零违规通过；3 份被拒的正是历史上那批空解析（title/price/currency 全空、`missing_fields` 非空）的脏数据**。无误杀、无漏放。
- **验证（按纪律仅针对性）**：
  - `manage.py test crawler_control.tests.test_crawler_field_rules` → **30 passed**（新增：价格解析形态、8 类致命规则、4 类警告规则、列表卡片 4 例、守卫 4 例、管线丢弃/放行/运行级告警、数据集增量 3 例）。
  - `manage.py test crawler_control.tests.test_crawler_rebuild crawler_control.tests.test_crawler_runtime crawler_control.tests.test_crawl_jobs_api crawler_control.tests.test_crawler_field_rules` → **62 passed**（回归未破）。
  - `ruff check` 本次改动 7 个文件 → All checks passed；`ruff format` 已执行。
  - `docs/05` §5.1、§11.1、§11.2 与 `crawler/README.md` 已同步新口径。
- **已知遗留 / 下次注意**：
  - `crawler/joybuy_crawler/settings.py` 有一处**既有**格式问题（`HTTPCACHE_ENABLED` 那行超出 ruff format 习惯换行，非本次引入），`ruff format --check` 会对该文件报 1 处，未顺手改以免混入无关 diff。
  - 规则阈值是常量写在 `quality.py` 顶部（`TITLE_MIN_LENGTH`/`PRICE_MIN`/`PRICE_MAX`/`IMAGE_HOST_SUFFIXES` 等）。真实站点如果出现合法低价配件（< 0.01）或新 CDN 域名，需要调这里，别去改调用点。
  - `PRICE_ANOMALY_*` 只发事件不改状态，管理端事件流能看到；如果后续希望"价格异常自动暂停任务"，要接到 `apply_quality_failure_policy` 上，属于策略变更，需用户确认。
  - 本轮**没有**跑真实 Joybuy 在线抓取（站点要求登录态 + 有风控），验证靠"真实历史 payload 回放 + 单测"，不要写成"线上抓取已验证"。

### 2026-11-05（补充 2）：类目双语「界面还是英文」的排查结论

- **现象**：管理端【爬虫任务】→【新建任务】→【选择 Joybuy 类目】只显示英文。
- **根因不是前端**：本机 `127.0.0.1:8000` 上有 **4 个 `manage.py runserver ... --noreload` 进程**（30808 / 29852 / 12352 / 32128，只有 32128 真正占着端口），`--noreload` 不加载新代码，接口返回的 `source-tree` 节点**没有 `name_zh` 字段**，前端自然只能显示英文。用临时员工会话直连接口核对：修复前 `has name_zh: False`，重启后 `has name_zh: True | Home Appliances | 家用电器`。
- **处理**：`taskkill` 掉 4 个旧进程，重新起一个 `runserver 127.0.0.1:8000 --noreload`（后台任务）。浏览器实测（用户自己的 Chrome，已登录 admin）：类目行显示「家用电器 Home Appliances minihome:…」，展开后子类目显示「热水壶 & 烤面包机 Kettles & Toasters l2:1405」等，中英双语正常；任务列表类目列也已变成中文（热水壶 & 烤面包机）。
- **教训**：改后端代码后必须重启 `--noreload` 开发服务器；`runserver` 默认的自动重载在本机不可用（`RuntimeError: Script backend\manage.py does not exist.`，因为启动参数是相对路径 `backend/manage.py`），要自动重载需用**绝对路径**启动：`python E:\code\AgentProject\Joybuy\backend\manage.py runserver 127.0.0.1:8000`。
- **别再多开**：`runserver` 重复启动不会报错（后起的占不到端口但仍在跑），排查「改了没生效」时先 `netstat -ano | grep 8000` 看监听 PID，再核对进程命令行。

### 2026-11-05（补充）：一个任务只用一个爬虫浏览器，用完必关

- **问题（用户反馈）**：跑一个任务会打开几十个浏览器且不关闭。根因是 `render_page` 每抓一个 URL 就
  `ChromiumPage(...)` 新开一个实例（类目树 15 页 = 15 个浏览器），而 `page.quit()` 在部分情况下并没有
  真正结束进程；Scrapy 风控/登录墙回退也是每页一个浏览器。
- **改法**：
  - `crawler/joybuy_crawler/render.py` 新增 `BrowserSession`（`open/get/close` + 上下文管理器）：
    一次 open、可连续 `get` 多页（每次 `listen.stop()`→`listen.start()` 复用 SSR 抓取），`close()` 先
    `page.quit()` 再显式回收进程。`render_page()` 保留原签名，内部改成「开一个临时 session、用完必关」。
  - `_kill_stale_crawler_browsers()` 重写：用一条 PowerShell 查询匹配 **`browser_profiles` 路径**或
    **调试端口 9333/9334** 的 chrome 进程，`taskkill /T /F` 并返回数量；`_crawler_chrome_pids()` 可单独列 PID。
    open 前和 close 后都跑一次，任何残留都会被收掉。
  - `capture_category_tree()` 全程使用同一个 session（`finally` 里 close），所以类目树 15 页只开 1 个浏览器。
  - `RiskControlRenderMiddleware` 改成复用同一个 session（cookie 变化时才重建），并连接
    `spider_closed` 信号关闭；渲染失败会丢掉 session，下次回退自动重建。这样商品任务里的登录墙回退
    不再「一页一个浏览器」。
  - `crawler_account_login` 的 `finally` 除了 `quit()` 也调用回收，避免登录窗口残留。
  - 新命令 `manage.py close_crawler_browsers`：随时回收残留爬虫浏览器（只匹配爬虫 profile / 9333、9334）。
- **验证（针对性）**：
  - `var/joybuy_demo/bin/verify_browser_lifecycle.py`（临时探针，不入库）：开 session 连抓 2 页，
    期间调试端口浏览器主进程数 = **1**，`close()` 后 = **0**，爬虫 PID = **0**。
  - `manage.py test crawler_control.tests.test_crawler_rebuild crawler_control.tests.test_crawl_jobs_api`
    → 21 passed；`ruff check`/`ruff format --check` 本次 5 个改动文件通过。
  - `manage.py close_crawler_browsers` 在无残留时输出 "No crawler browser was running."。

### 2026-11-05：管理端类目选择器「中文名 / English name」双语展示

- **目标**：`新建任务 → 选择 Joybuy 类目` 原本只有英文名；现在每个节点同时显示中文名与英文名，搜索框支持中文/英文/来源 ID。中文名必须来自 joybuy.co.uk 真实中文页面，按 source id 与英文严格一对一，不伪造译名。
- **语言开关（现场核实）**：joybuy.co.uk 用 `_lang` Cookie 控制界面语言（默认 `en_GB`），设成 `zh_CN` 后整站（含类目菜单、频道页类目磁贴）变中文，URL 与 source id 不变。
- **登录墙（新踩的坑）**：2026-11-05 起，未登录访问首页/频道页会 **307 跳 `/login`**（`Location: /login?returnUrl=...`），匿名爬取/无头/有头都被拦，`/minihome/` 页拿不到类目链接。抓取必须带已登录账号的会话。
- **后端存储**：`catalog` 迁移 `0008_source_category_chinese_names` 给 `SourceCategory` 和 `SourceCategorySnapshot` 各加 `name_zh`。`SourceCategory.name_zh` 是 source id 维度的持久映射；`SourceCategorySnapshot.name_zh` 是版本内展示名；`tree_sync.sync_category_tree` 建快照时优先取节点自带中文名、否则继承 `SourceCategory.name_zh`，**重建英文树不会丢中文名**。`catalog/services.save_source_category_version` 同步支持 `name_zh`（不参与结构哈希与版本判定）。
- **新命令** `manage.py sync_joybuy_category_names_zh`：`--from-json` 回放 / `--dump-json` 落盘 / `--account <public_id>` 用账号会话抓取 / `--profile` 复用某个浏览器 profile / `--channel` 按频道分块 / `--merge-json` 分块合并 / `--pause` 控速 / `--no-reset-profile` 跳过删 profile（本机 safe-delete 会拦批量删除）。命令输出 `matched / categories_updated / snapshots_updated / unknown / still_missing` 五项，**unknown 与 still_missing 只报告不猜译名**。
- **爬虫层**：`category_menu.py` 新增 `locale_cookies()` 与 `capture_category_tree(locale=, cookies=, profile_dir=, only_channels=)`；`render.py` 的 `_build_options/render_page` 支持指定 `profile_dir`；风控特征串补了中文站实际出现的 `403 页面 / 服务暂时中断 / 系统当前负载过高`。
- **登录命令修复（真 bug）**：`crawler_account_login` 原来的「出现新 Cookie 就算登录成功」会在用户停在 facebook.com 授权页时误判，把 **facebook.com 的 7 条 Cookie 存成了账号会话**。现改为：当前 URL 必须是 joybuy.co.uk 且不在 `/login`、可见正文 ≥2000 字符、且只采集 `joybuy` 域 Cookie。
- **管理端接口**：`tree_to_payload()` 每个节点返回 `name_zh`；任务列表类目列优先显示中文名；任务详情 `categories[]` 增加 `name_zh` 字段。
- **前端**：`CategoryTreePicker.vue` 每行渲染「中文名（加粗）+ 英文名（次要色）」，没有中文名时只显示英文；搜索同时匹配中英文与 source id；选中项带上 `name_zh`；表单标题下加了说明文案。`CrawlersView.vue` 补 `.create-form__tree-hint` 样式。
- **数据现状**：14 个一级频道 100% 有中文名；163 个二级类目 **156 个有中文名（95.7%）**，缺 7 个：`l2:3505 Gaming Steering Wheels`、`l2:1384 Learning, Discovery & Science`、`l2:1376 Vehicles & Remote Control`、`l2:1380 Electronic Toys & Music`、`l2:1378 Soft Toys`、`l2:1474 Baby Clothing`、`l2:1478 Safety Equipment`（这 7 个在频道页的类目轮播里不在首屏，浏览器 DOM 快照拿不到；爬虫侧当天被风控限流）。
- **数据文件**：`var/joybuy_demo/data/category_menu_zh.json`（英文名+中文名+来源 URL，可直接 `--from-json` 回放）；`category_menu_zh.tsv` 是抓取原始对照（channel / source_id / 中文名）。
- **验证（按纪律仅针对性）**：
  - `manage.py test crawler_control.tests.test_crawler_rebuild.TreeSyncTests crawler_control.tests.test_crawl_jobs_api` → 7 passed（新增 2 个用例：中文名按 source id 匹配且重建版本仍继承；unknown/still_missing 报告正确）。
  - `npx vitest run --config admin-web/vitest.config.js` → 9 passed（`CategoryTreePicker` 6 个用例，含「中英同时显示」与「中文关键词过滤」）。
  - `npx prettier --check` + `npx eslint` 三个改动前端文件 → 通过；`ruff check` / `ruff format --check` 本次改动的 9 个 Python 文件 → 通过。
  - 实库：`manage.py migrate catalog` 已执行；`sync_joybuy_category_names_zh --from-json` 结果 `tree=joybuy-uk-20261104-4dcfbbe5 matched=170 categories_updated=170 snapshots_updated=184 unknown=0 still_missing=7`；`tree_to_payload` 抽查 Electronics/Pets 中英对照正确、14 个 L1 全部有中文名。
  - **未做**：管理端页面人工登录截图核对（当时不知密码；**2026-11-05 夜已解决**：`admin@joybuy.test` 密码已重设为 `Admin@123456`，见下方「本地开发登录凭据」）。

### 2026-11-05：数据库说明文档（docs/13）

- 数据来源：`information_schema.COLUMNS` 全量快照（79 表 759 字段，TSV 存 `var/joybuy_demo/data/db_columns.tsv`）+ 通读 `backend/` 全部 14 个 models.py 确认字段语义。
- 产出 `docs/13-database-schema.md`：通用约定（id/public_id/外键/时间戳/枚举/金额规则）、按 15 个业务域的表清单、每张表用途说明 + 逐字段表（列名/类型/说明，含唯一约束、CHECK 约束、枚举取值）、Django 内置表一节。关键业务规则均就地标注（如 offer 价格 CHECK、staging 幂等键、fingerprint HMAC、purchase_whitelisted 白名单）。
- 文档编号注意：`docs/12` 已被 UI 规格文档占用，本任务新建文档顺延为 13；`docs/README.md` 索引补齐 11/12/13。
- 验证（按纪律仅针对性）：prettier --check 两份文档通过；无代码改动，无后端/前端验证需要。

### 2026-11-04：畅销榜单 11 类公开数据补齐

- 新增受版本控制的 `backend/catalog/fixtures/bestseller_demo_2026_11_04.json`：11 个标准类目各 3 条，共 33 条；保存来源父榜/子榜、固定 URL、来源语言、榜单位置、Joybuy SKU、标题、品牌、商品 URL、图片 URL、原价和库存。前 6 组来自中文浏览器会话（`zh-CN`），后 5 组来自公开英文服务端页（`en-GB`），均按实际来源标记，没有伪造翻译。
- 现场映射：家居生活→家居用品/清洁用品；电子产品→数码电子/办公设备；美妆→美妆/彩妆；小家电→家用电器/小型厨房电器；健康→健康与保健/营养品；电脑→电脑及配件/电子配件；户外→运动户外/运动器材；宠物→宠物用品/猫咪必备；母婴→母婴用品/哺育喂养；游戏→游戏娱乐/游戏主机；服装→时装配饰频道/爆款直降（替代来源）。
- 新增幂等命令 `backend/catalog/management/commands/load_bestseller_demo.py`：支持 `--fixture`、`--per-category`、`--skip-images`、`--only-category`；建立 `bestseller:<local-slug>` 来源类目和主映射，调用 `ingest_product_payload()` → `import_staging_product()`，显式修正既有 SPU 的本地类目/品牌，激活 SPU/Offer，按来源层/本地覆盖层解析有效标题，下载本地图并重建搜索文档。fixture 价格作为 `current_price` 保存，`list_price=None`，不保存促销文案。
- `backend/catalog/search_services.py`：搜索页批量读取当前页 SPU 的第一张 `gallery` 本地图，返回 `image_path`；同时 `select_related("spu", "local_category")`，避免商品逐条查询。商城现有 `ProductCard` 已消费 `image_path`，无需改前端。
- 新增测试 `backend/catalog/tests/test_bestseller_demo.py`；扩展 `test_search.py` 覆盖本地首图与查询数上限。
- 实库执行：首次导入 33 条（30 个新 SPU，另 3 个命中既有来源身份），一次源图失败；确认 CDN 对失败资源稳定返回 HTTP 400 后，改用同一“爆款直降”楼层真实第 4 名 PUMA 商品，重跑服装类 3 条后 0 图片失败。失败样本 `10489708` 已置 SPU=DRAFT、GB Offer=INACTIVE 并重建索引（未物理删除历史）。最终 fixture 33 个 SPU 全部可搜索、33/33 有本地图。
- 最终 API 总量（含此前数据）：home-living 46、electronics 6、beauty 3、small-home-appliances 10，其余 7 类各 3；本轮 fixture 在每个类目严格各 3 条。

### 2026-11-04（补充）：头部 logo 换成本地真实字标图片

- 按用户给出的真实站 logo 结构（110×30 图片按钮），把 `st.joy-sourcing.com/website/home/m_logo.png`（264×73 高清源）下载到 `storefront/public/images/logo.png`（项目内本地托管，无 CDN 引用）。
- `AppHeader.vue` 品牌区从红色文字字标改为 `<img class="brand__logo">`（110×30，object-fit contain）；src 用运行时常量绑定而非静态属性——静态 `/images/...` 会被 vite 的模板资源转换当成模块 import 解析失败（vitest 下报 `file:///images/logo.png` 错误，Nuxt dev 下报 Failed to resolve import）。vitest 配置同时加了 `vue({ template: { transformAssetUrls: false } })` 兜底。
- 验证：vitest 42/42、eslint/prettier 通过；浏览器确认 logo 加载（natural 264px、显示 110×30）。

### 2026-11-04（第二轮反馈）：首页头部/活动区按真实站样式精修（15 项）

- 用户给出 15 项首页优化点并要求打开真实 joybuy.co.uk 参考样式；已在内置浏览器实测真实站并逐项测量（通告条 40px、搜索行 52px+14px 内边距、搜索按钮 64×44 深色圆角在框内、圆形图标按钮 52px、卡片 277×277 两行、活动区全幅 1512×698 带背景图）。
- **AppHeader 重写**：通告条内容改用与页面一致的居中容器（max-width 90rem + container-pad），高度 40px、颜色 #17202A（用户指定值，实测真实站为 #1A1A1A）；分类按钮改为"☰ Categories/分类"浅灰胶囊（bg #F5F6F7，radius 50px）；悬停/点击展开分类面板（150ms 关闭延迟防抖）；搜索框改浅灰底 #F5F6F7 + 1px #C2C4CC 描边胶囊，深色 #17202A 圆形搜索按钮（64×44）嵌在框内右侧（宽度 flex 自适应，1512 视口下约 898px）；配送至 hover 背景 #F0F1F4；个人/购物车改为 52px 圆形图标按钮（含角标）；类目行 space-between 平均占满、hover 下划线无背景；搜索行与类目行之间去掉分割线，仅保留实测阴影 `rgba(0,0,0,.04) 0 2px 12px, rgba(0,0,0,.06) 0 1px 4px`。
- **AppCategoryPanel**：去掉 Teleport 与全屏遮罩，改为锚定在分类按钮正下方、与按钮左对齐（left 对齐实测一致）的下拉面板；父容器 mouseenter/mouseleave 控制开关；点击只负责打开（避免与 hover 冲突）。
- **CmsCampaignGrid**：去掉"为你推荐"标题（真实楼层无标题）；改为全幅楼层（width 100vw + margin 反抗容器），min-height 600px；新增 `background_path` 背景图层（payload 提供时用背景图，否则回退浅色蒙版）；卡片改 5 列正方形网格。
- **loader**：新增 `CAMPAIGN_BG_URL`（实测真实站活动区背景图 URL），下载进本地 CMS 媒体库并写入 payload——首页活动区背景为真实素材本地化，非外链。
- **其它**：`main.css` 给 `.app-main` 加 `overflow-x: clip`（修复 100vw 全幅导致的 8px 横向滚动）；首页内容区 `margin-block: 24px`；分类按钮补 aria-label（移动端隐藏文字后保持可访问名）。
- e2e 断言同步：`foundation.spec.js` 与 `purchase-funnel.spec.js` 首页断言从 "Offers for you" 标题改为活动区 Welcome Offers 链接（标题已按需求 12 删除）；首页 4 视口快照重新基线化。

### 2026-11-04：docs/12 目标状态改造第 1 轮（i18n + 全局头部 + 11 类目体系 + 首页 CMS）

- **后端类目双语**：`LocalCategory` 新增 `name_en`/`name_zh`（迁移 `catalog/0007`）+ `display_name(locale)`；`GET /api/v1/categories` 改为返回嵌套树（roots + 一级 children，按 `sort_order` 排序），每级带 `name_en`/`name_zh`（`search_views.category_tree` 重写）。
- **种子命令** `backend/catalog/management/commands/seed_standard_categories.py`：幂等创建 11 个标准一级类目（家居生活/电子产品/美妆个人护理/小家电/健康与保健/计算机与配件/服装与配饰/户外运动/宠物用品/婴幼儿用品/游戏及配件，双语 + slug + 42 个子类目），把不在标准清单内的旧 ACTIVE 根类目置 HIDDEN；`--assign-demo-products` 按标题关键词把演示商品归入类目（厨电→kitchen-appliances、纸品→cleaning-supplies、电子→electronics、其余食品→groceries-food 兜底）并重建搜索文档。已执行：11 根类目 + 42 子类目，53 个演示商品归位（家居生活 43 / 小家电 10 / 电子产品 3 条可搜索文档；其余类目暂空，等第 2/3 轮后台配置与真实品类数据）。
- **商城端 i18n**：`storefront/locales/messages.js`（EN/ZH 字典 + `pickName` 双语取值）+ `composables/useLocale.js`（cookie `joybuy-locale` 持久化，默认 en，`t()/toggleLocale()/categoryName()`）+ `composables/useCategoryTree.js`（SSR 直连/客户端代理）。通告条左端 "UK | English" 即语言切换按钮。
- **AppHeader 改造**（需求 1-1/1-4/1-5/1-6）：通告条去掉 "Download Joybuy"，轮播仅剩 Welcome Offers / Quality Guaranteed / 24/7 / Free returns 四条（‹›箭头切换+自动轮播）；类目行改读 categories API 的 11 个标准类目（链接 `/c/<slug>`）；新增汉堡按钮 + `AppCategoryPanel.vue`（左栏 11 根类目、右栏仅当前选中类目的子类目，严格联动）；新增登录态头像下拉（用户名 + My orders / Reviews and Q&A(/account) / Wishlist(/account/favourites) / Addresses(/account/addresses) / Sign out，**无 My JoyPlus**）。
- **新页面**：`pages/s.vue`（/s?k=→关键词搜索、/s?category=→类目列表，复用 ProductListing；`ProductListing.vue` 的 searchText 增加 `route.query.k` 兜底）；`pages/account/addresses.vue`（只读地址列表）。
- **首页 CMS**（需求 2/3）：`load_joybuy_demo.py` 删除快捷入口图标行模块（连带删除 extract_quick_entries/extract_category_discovery 死代码）；品类发现改为固定 6 品类（家居/电子产品/服装以及配饰/游戏/户外运动/小家电，双语 label）落地 `/s?category=<slug>`；campaign_grid/发现楼层标题带 `title_zh`。已重跑发布 home v5（10 模块，0 图片失败，用已保存 HTML 未新抓取）。
- **CMS 组件双语**：`CmsLinkGrid.vue`/`CmsCampaignGrid.vue` 支持 `title_zh`/`label_zh`/`title_zh`+`subtitle_zh`，按 locale 取值回退英文 base 字段。
- 浏览器实测：中文首页（黑通告条+红色搜索头+11 中文类目行+为你推荐+品类发现 6 品类）、分类面板联动（Electronics 右栏仅 4 子类目）、中文/英文切换、`/s?category=electronics`（3 商品）均正常；4 视口首页快照已重新基线化。

### 2026-11-03：首页对齐真实 Joybuy 结构（活动砖石/快捷入口/品类发现/通知条）

- 用户给出真实首页截图指出缺项后补齐。新 CMS 模块类型 `campaign_grid`（item 必填 title，带 subtitle/image_path/href）：`content/schemas.py` + `CmsModule.Type` + 迁移 `content/0003`；`link_grid` payload 增加 `variant`（`quick_entries` 圆形图标入口 / `tiles` 品类发现浅底磁贴），item 支持可选 `icon_path`；前端新增 `CmsCampaignGrid.vue` 并扩展 `CmsLinkGrid.vue`。
- `load_joybuy_demo.py` 新增三个提取器（全部来自已保存 flight 数据，无新增抓取）：`extract_campaign_tiles`（floorInfo 中含 subTitle 且 floorType≠"icon" 的 eventInfo，标题取 titleView.title="Offers for you"，前 10 块）、`extract_quick_entries`（floorType=="icon"，iconImage 120×120 图标，前 6 个）、`extract_category_discovery`（`externalKey=="EXT_POPULAR_CATEGORIES_V3"` 的 data 列表，7 块）。
- 图片本地化规则：活动瓦片 `https://images3.joy-sourcing.com/product/s384x384_{path}.webp`、缩略图 s240x240、入口图标为 `//images3.../da/...` 完整 URL 补 https；统一 `store_bytes(kind="CMS")`。本轮新增 23 张图 0 失败。
- 首页模块序对齐真实站（home v4，11 模块）：campaign_grid → 快捷入口 → 品类发现 → 6 个商品楼层 → 品牌墙 → rich_text；**移除红色 hero**（真实首页没有）。瓦片/入口的站外跳转统一替换为本地 `/search`。
- 头部：新增黑色顶部通知条（真实文案 "Unlock Your Welcome Offers: FREE Delivery | Up to 80% OFF | Free 30-day JoyPlus trial"，窄屏只留通知文案）；logo 改红色 Joybuy 字标；搜索框红描边+圆形放大镜按钮（内联 SVG）；新增 "Deliver to SW1A 1AA"。
- e2e 断言同步为 "Offers for you"；首页 4 视口快照重新基线化。
- 已知剩余差异（真实站有、本地未做）：通知条/活动砖石的轮播箭头与分页、右侧悬浮按钮（下载/消息/客服/反馈）、"分类"下拉菜单、顶栏图标资源（已用文字替代）。

### 2026-11-03：真实 Joybuy 站点产品功能分析（浏览器实测）

- 用内置浏览器只读遍历 joybuy.co.uk：首页、Categories 弹出菜单（15 个一级类目 + Electronics 二级/品牌/活动实测）、顶部 13 个频道页（Electronics 与 Food & Drinks 抽样实测，结构统一）、搜索/类目列表页（JoyExpress/Bestsellers/Welcome offer/Lightning offers/Outlet 快捷筛选、价格双滑块、评分、排序、商品卡加购/收藏）、商品详情页（面包屑、规格、数量、Buy now/Add to cart、卖家店铺、分享、3 个信息 Tab）、购物车页（Delivery/Pickup 切换、空态）。
- 产出 `docs/11-joybuy-co-uk-product-features.md`（按模块分组的功能表格）。
- 边界：未登录、未提交任何数据；登录后功能、页脚（站点自绘滚动无法滚到）、Deliver to 弹窗未覆盖，已在文档"无法访问的页面"注明。
- 已知坑：站点懒加载/自绘滚动导致滚轮滚动无效、DOM 快照只含视口内容；无头抓取 HTML 会命中 Joybuy 风控页（Risk Control），须用真实浏览器访问。

### 2026-11-03：Joybuy 主页复刻效果展示（爬真实内容 + 首页改版）

- 抓取方式：仅一次礼貌抓取 `https://www.joybuy.com/` 公开主页（保存于 `var/joybuy_demo/data/home_raw.html`），解析其 Next.js RSC flight 流拿到公开数据：10 个热卖楼层（每层 10 SKU）、楼层标题、活动入口（Lightning Offers/Outlet/Mix & Match/JoyPlus/New Arrivals）、品牌墙、承诺文案；解析脚本脚手架在 `var/joybuy_demo/bin/`（不入库、不提交）。
- 新增管理命令 `backend/content/management/commands/load_joybuy_demo.py`：解码 flight 流 → 每个商品只取**原价**（`crossOffPrice`，`mainPrice` 优惠价丢弃）→ 走既有 `ingest_product_payload` + `import_staging_product` 幂等导入 53 个真实商品（60 条去重后）→ 图片经 CDN s360x360 规则下载并用 `store_bytes` 存入本地媒体库 `var/media`（60/60 成功，`MediaUsage` role=gallery 挂到 SPU，详情页画廊可用）→ 逐 SPU 重建 GB 搜索文档 → 生成并发布 CMS 首页（hero、`Explore Joybuy` 入口磁贴、6 个真实楼层 `product_pool`、`Brands we love` 品牌墙、说明 rich_text），同时把生成的页面 JSON 落盘 `var/joybuy_demo/data/generated_home_fixture.json`。命令幂等可重跑。
- 演示特例（已注明在命令 docstring）：导入的 SPU/Offer 被命令直接置 ACTIVE——真实站点在售热卖品跳过 curation 草稿态；生产链路仍应走质量闸门/审核。
- CMS 新模块类型 `link_grid`（入口/品牌磁贴，label 必填、href 可选）：`content/schemas.py`、`CmsModule.Type` + 迁移 `content/0002`、前端 `CmsLinkGrid.vue` + `CmsRenderer` 注册。
- 商城端：`ProductCard.vue` 支持 `image_path` 真图（否则骨架兜底）；`nuxt.config.js` devProxy 增加 `/media` → Django（生产由 Nginx 伺服，设置注释已注明）；`AppHeader.vue` 导航改为真实 Joybuy 一级类目（docs/09 证据），每项链接到能命中已导入库存的搜索词。
- e2e 同步：`foundation.spec.js` 与 `purchase-funnel.spec.js` 首页断言改为新 hero 标题 "Don't just buy, Joybuy" + "Food Cupboard"；4 个视口首页视觉快照已按新首页重新基线化。
- 浏览器实测：首页（1440px 截图）红色主题、搜索栏、真实类目导航、hero、入口磁贴、真实图片+红色 `$` 原价楼层、品牌墙、页脚均正常；详情页画廊图片、`$6.99`、`999+ in stock` 正常；`/search?q=noodles` 返回 10 个真实商品。
- 已知边界：楼层点击 "View all" 与入口磁贴多为静态展示（无真实落地页）；品牌墙磁贴不带链接；详情页无描述/评分（公开主页数据不含这些字段）。

### 2026-11-03：原价采集、送达标签过滤与美元展示（需求优化）

- 爬虫（R1）：`crawler/joybuy_crawler/parsers/product_detail.py` 改为只采集原价——页面同时有优惠价（`.price .current`）与原价（`.price .list`）时 `current_price` 取原价、`list_price` 恒为 `None`；页面存在原价时所有 SKU 的 `data-price`（属展示优惠价）统一归一为原价，页面没有原价时唯一价格视为原价、SKU 各自价格保留。契约注释已写明该业务规则。
- 商城端展示层（R2+R3）：新增 `storefront/utils/display.js`，提供 `formatDisplayPrice`（一律 `Intl.NumberFormat('en-US', { currency: 'USD' })`，即 `$` 符号，不改存储币种）与 `isDeliveryLabel`（中英文配送预估关键词正则，如“今日/明天/送达/delivery/arrives/ships/get it by”）。
- R1 展示配套：`storefront/pages/p/[id].vue` 移除划线价（listPrice computed、模板与样式），只渲染单一原价；详情页促销徽章与 `ProductCard.vue` 的 `badge` 徽章渲染前经 `isDeliveryLabel` 过滤（爬虫仍抓 `promotion_label`，过滤只发生在渲染时）。
- `$` 符号覆盖：`ProductCard.vue`、`p/[id].vue`、`composables/useCart.js`（formatMoney）、`pages/checkout/index.vue`（formatMoney 并去掉 currency 入参）、`pages/account/orders.vue`（原来是 `GBP 39.50` 文本）、`pages/account/favourites.vue` 与 `recently-viewed.vue`（原来手拼 `£` 且会显示 `19.9900` 四位小数，现统一走 `formatDisplayPrice`）、`ProductListing.vue` 价格筛选标签 `Min/Max £→$`、详情页配送文案 `£20→$20`。
- 文档同步：`docs/06-api-and-workflows.md` 第 6 节新增三条展示与采集口径；`docs/05-crawler-and-ingestion.md` 新增 9.1 价格采集口径；`docs/02-pages-and-visual-acceptance.md` 状态矩阵改为“单一原价（$ 符号、无划线价）”。
- 测试同步：`backend/crawler_control/tests/test_crawler_import.py` 契约断言改为 `current_price="29.99"`、`list_price is None`、三个 SKU 价格均为 `29.99`；`storefront/components/cms/CmsRenderer.test.js` 改断言 `$19.99` 并新增“送达类徽章被抑制”用例；新增 `storefront/utils/display.test.js`（9 个用例覆盖 $ 格式与标签过滤）。
- 运行验证：后端全量 216 项、商城组件 33 项、平台端组件 2 项、eslint、全部改动文件 Prettier、e2e 15/15 全部通过；e2e 首页视觉快照已按 $ 价格重新基线化。浏览器实测：首页/搜索/详情页渲染 `$19.99` 等价格，详情页只有单一原价。

### 2026-11-03：Joybuy 中文会话与多语言内容方案

- 根据用户澄清修订方案：撤回“缺少德文则隐藏商品”和“评价点击后按需翻译”的建议，改为自动切换、来源忠实、逐字段混合语言模型。
- 明确 `requested_locale` 只代表用户选择的语言环境，不代表每个字段实际都是该语言；每个字段需要额外记录 `actual_locale`。
- 明确机器翻译不属于默认复刻链路；未来如需本地增强翻译，必须与 Joybuy 来源内容分层并单独立项。
- 在 Joybuy 公开页面“Custom settings”中选择并保存 `中文(简体) - ZH`；验证页面标题变为“Joybuy | 一站式购物平台”，导航、活动入口和商品标题均显示中文。
- 保留该中文浏览器会话供后续类目分析使用；本轮按用户要求不继续分析类目。
- 新增 `docs/10-multilingual-content-and-market-design.md`：定义来源语言、展示语言和国家市场三个独立维度；整理需要本地化的商品/类目/属性/CMS/评价内容；设计翻译生成、审核、失效重生成、发布、回退和搜索索引规则。
- 更新 `docs/01-requirements.md`、`docs/04-data-model-and-storage.md`、`docs/05-crawler-and-ingestion.md` 与文档索引，明确中文来源优先、多 locale 内容、市场与语言分离以及翻译来源可追溯。
- 更新 `docs/09-crawler-category-task-redesign.md` 状态：英文类目证据只保留为历史参考，不得直接生成最终 seed；后续必须从中文页面重新分析。
- 代码现状核对：已有 `SpuTranslation(spu, locale, title, subtitle, description)` 和 `Market.default_locale/default_currency` 基础，但详情 API 仍取第一条翻译、搜索文档仍是一 SPU 一行、爬虫导入依赖调用方 locale，尚未形成多市场多语言闭环。

### 2026-11-03：爬虫品类与配额任务现场分析及方案文档

- 使用公开页面现场分析 `https://www.joybuy.co.uk/`，展开首页 `Categories` 菜单，确认当前 22 个一级入口，并读取页面公开的一级/二级类目标识。
- 逐项核对本次业务涉及的 Jewellery、Watches、Phones、Wearables、Camera & Photo、Coffee Machines、女装、男装、箱包、鞋靴、美妆、户外、运动和 DIY 等页面，记录页面公开的下一级筛选节点及层级前缀。
- 确认示例：`Clothes, Shoes & Watches=1876`、`Watches=1881`、男士手表筛选 `cid2:13159`；`Electronics=1409`、`Camera & Photo=1416`、无人机系统 `cid2:10870`。
- 确认活动入口不是商品类目：首页当前公开 Lightning Offers、Outlet、Mix & Match、New Arrivals，应作为活动页来源建模，不能伪造一个 Joybuy“活动商品”类目。
- 新增 `docs/09-crawler-category-task-redesign.md`：记录现场证据、10 个业务分组到 Joybuy 来源节点的建议映射、字段语义、简单页面布局、去重/配额规则、数据模型/API 改造建议、验收标准和待确认决策。
- 更新 `docs/README.md` 文档索引，并在 `docs/05-crawler-and-ingestion.md` 将新方案标记为最新设计基线。
- 明确“来源类目公开标识”是内部稳定来源 ID，创建页不应让运营手填；明确“商品数量上限”应改名为“本任务最多成功入库商品数”，按去重且通过质量闸门的成功入库商品统计。
- 页面方案已收敛为单页：顶部总量与摘要、中部 10 行配额表、按行打开树形选择侧栏、高级参数默认折叠；不使用复杂多步向导。

### 2026-11-03：平台管理端全面中文化

- 修改 `admin-web/index.html` 和路由标题：页面语言改为简体中文，浏览器标题仅保留 `Joybuy` 品牌名为英文。
- 修改登录、仪表盘、商品目录、评价管理、爬取任务、内容页面、买家与订单、404 和基础状态页的可见固定文案。
- 新增 `admin-web/src/lib/locale.js`：将状态、同步模式、排序方式、覆盖字段、动作、币种和布尔值统一映射为中文。接口请求仍使用原始英文枚举，只在展示层汉化。
- 修改 `admin-web/src/lib/api.js`：网络错误、权限错误及常见业务错误对用户展示中文消息，不再直接暴露英文后端消息。
- 同步更新组件测试和平台端浏览器测试的中文断言。
- 扩展管理员浏览器测试：登录后逐一打开商品目录、评价管理、爬取任务、内容页面、买家与订单五个管理页面，并断言中文标题可见。
- 新增根目录 `AGENTS.md`，并更新 `README.md` 与 `docs/08-implementation-work-packages.md`，将“每次执行结束前更新 `HANDOFF.md`”固化为项目纪律。

### 本地开发登录凭据（2026-11-05 夜更新）

- **商家端演示数据**：`manage.py seed_merchant_demo --merchant HOMCOM --reset` / `--merchant CHiQ --reset --with-deposit`（幂等，可反复跑）
- **商家端（merchant-web，http://127.0.0.1:5174/login）**
  - 同一套账号：`admin@joybuy.test` / `Admin@123456`（已绑定 HOMCOM + CHiQ 两家店）
  - 商家端复用 `/api/v1/admin/auth/*` 登录，店铺归属靠 `merchant_membership`
  - 绑定店铺的命令（在仓库根目录执行）：
    ```
    ./.venv/Scripts/python.exe backend/manage.py shell -c "from merchants.models import Merchant,MerchantMembership,MerchantRole; from accounts_staff.models import StaffAccount; s=StaffAccount.objects.get(email='admin@joybuy.test'); m=Merchant.objects.get(display_name='CHiQ'); MerchantMembership.objects.get_or_create(merchant=m, staff=s, defaults={'role':MerchantRole.objects.get(code='merchant_owner'),'status':'ACTIVE'})"
    ```
- **管理端（admin-web，http://127.0.0.1:5173）**
  - 账号 `admin@joybuy.test` / 密码 `Admin@123456`（`platform_admin` 角色，21 个权限码全含，TOTP 未启用）
  - 次要账号 `auditor@joybuy.test`（`platform_auditor`，只有审计只读权限，密码未重置、不可用）
  - **仅本地开发库**。正式环境必须改密码并走初始化流程，不得沿用。
- **登录页只校验邮箱 + 密码**，不再要求 TOTP 验证码；会话 Cookie 名 `joybuy_staff_session`，写操作必须带 `X-CSRFToken`（先 GET `/api/v1/admin/auth/session` 拿 `csrf_token`）。
- 密码遗忘时的重置方式（在仓库根目录执行）：
  ```
  ./.venv/Scripts/python.exe backend/manage.py shell -c "from accounts_staff.models import StaffAccount; s=StaffAccount.objects.get(email='admin@joybuy.test'); s.set_password('新密码'); s.save()"
  ```

## 3. 当前卡在哪里

- **开发服务器（2026-11-05 15:59 起）由助手在后台启动**：`python backend/manage.py runserver 127.0.0.1:8000 --noreload`。此进程若随会话结束退出，重新启动即可；**改后端代码后必须重启**，否则接口还是旧结构（类目双语那次就是被 4 个残留 `--noreload` 进程挡住）。admin 前端在 5173（vite dev，源码热更新，浏览器 Ctrl+F5 即可）。
- **7 个二级类目还没有中文名**（`l2:3505/1384/1376/1380/1378/1474/1478`），UI 上这些节点只显示英文名。补法：等 joybuy 风控窗口过去后跑一次
  `manage.py sync_joybuy_category_names_zh --account <账号public_id> --merge-json --dump-json var/joybuy_demo/data/category_menu_zh.json`
  （全量）或按 `--channel minihome:UK-Mini-HP-Toys-Baby-and-Kids --channel minihome:UK-Mini-HP-Gaming` 分块补；命令会自动合并并汇报 `still_missing`。
- **joybuy.co.uk 2026-11-05 起对未登录访问强制跳登录**：`sync_joybuy_category_tree` 这类匿名抓取现在会拿到 `/login` 或 `Joybuy Risk Control` 页，必须有有效账号会话（`--account`）才能跑。
- **当天爬虫浏览器已被风控限流**：频道路径 `/minihome/*` 连续抓 10+ 页后返回 `Joybuy Risk Control`（`evApi=color_guide_homepage_getPageAllData`）。已确认不是登录态问题（账号会话 42 条 Cookie 有效），冷却后放慢 `--pause 20`+ 分块可恢复；用户自己的 Chrome 同时段正常。
- **`reset_browser_profile()` 在本机被 safe-delete 拦截**（656 个文件批量删除需要确认，报 `SAFE_DELETE_BULK_CONFIRM_REQUIRED`）→ 命令新增 `--no-reset-profile`，复用现有 profile 绕过；需要干净 profile 时要人工清 `var/browser_profiles/profile`。
- **账号 profile 未必能过风控**：`--profile account-9b189970` 实测直接 403（该 profile 做过 Facebook OAuth），通用 profile + 注入会话 Cookie 反而正常，选择 profile 时要先小样本验证。

- 本轮畅销榜数据补齐没有阻塞。正式 `RankingList/RankingEntry` 后台配置仍未实现，当前 `/promo/best-seller` 和首页楼层继续读取 `/api/v1/search?category=<slug>&sort=rating_desc`；这是既有第 2 轮范围，不应把本轮演示数据导入误写成正式榜单模型已完成。
- 商品多语言索引仍是已知架构欠账：`ProductSearchDocument` 每 SPU/市场只有一行且 `rebuild_search_document()` 取第一条翻译。本轮只如实保存来源 locale，不顺手伪造翻译或宣称已实现按界面语言切换商品文本。
- “是否强制全德文/是否由用户触发翻译”的产品口径已经闭合，不再是阻塞。
- 后续仍需现场分析德国市场：默认/可选语言、币种、配送上下文，以及首页、类目、商品、属性、活动和评价分别为德文还是英文；本轮按用户要求暂不继续分析类目。
- 国际化实现不能只改 `SpuTranslation`：现有 `ProductSearchDocument` 每个 SPU 只有一行，商品详情取第一条翻译，搜索和详情市场基本固定为 GB；实现前必须一起重构市场/请求语言解析、字段实际语言和 `(spu, market, requested_locale)` 搜索索引。
- 本次不是技术阻塞，而是四个必须闭合的产品口径：高价最低价格（建议 `£300`）、机械手表的关键词/属性识别规则、任务总商品数是否预填默认值（建议候选 `1000`）、活动商品是否默认全选当前四个公开入口。
- 现有 `CrawlJob` 只有一个 `source_category` 和一个 `product_limit`，无法表达 10 个业务分组、多选类目树和活动页来源；确认方案后需要新增配额与来源选择关联模型，不能只改前端表单。
- Joybuy 二级结果页展示的下一层有时是性别或跨目录筛选维度，不总是传统子类目；实现时必须原样保存 `cid1/cid2/cid3/cid4` 前缀和来源 ID，不能只按深度猜层级。
- 商家端页面不存在，这不是本次遗漏，而是已确定的需求边界。如果后续需要商家端，必须先由用户提供参考页并重新评审需求，不能自行复制平台管理端。
- Git 基线（2026-11-04）：全部项目已提交并推送 GitHub（origin=LeeYX123/JoybuyDemo，main 分支，初始提交 1a76a99，362 文件；var/ 数据与工具状态目录已 gitignore）。后续改动基于此基线正常提交即可。

## 4. 下一步计划

1. 用户若继续第 2 轮，先实现正式 `RankingList/RankingEntry`、平台端榜单配置和对应 API，再把商城榜单从搜索排序切到运营榜单；本轮 fixture 可作为初始化候选数据。
2. 多语言商品内容另拆工作包，重构 `(spu, market, requested_locale)` 搜索索引和详情翻译选择；不要在榜单 loader 里补机器翻译。
3. 若要刷新演示数据，先用保存 fixture/低频公开页证据更新，再执行 `load_bestseller_demo`；单类重试用 `--only-category <slug>`，不要全量重复下载。
4. 继续与用户讨论剩余多市场行为；在用户允许现场分析后，依次核对德国市场和其他目标市场/语言组合。
5. 证据闭合后，把国际化改造拆成独立小工作包：MarketLocale、市场本地化内容与字段语言元数据、API 上下文切换、搜索索引、购物端自动刷新和管理端来源对比。
6. 再使用已保存的 Joybuy 中文会话重新分析类目；不直接复用英文名称生成最终 seed。
7. 中文类目完成后，再回到 `docs/09-crawler-category-task-redesign.md` 第 10 节的四个品类口径和配额页面实现。
8. 任何后续任务结束前，继续按 `AGENTS.md` 更新本文档。

## 5. 已踩过且绝对不能再踩的坑

### 2026-11-05 爬虫重建（第 1 轮）

- **风控/登录判定只能匹配页面标题+可见文本**（先剥掉 script/style 再匹配）：正常首页的 i18n 文案包里有 `"error403":"403 Forbidden"`，页脚有 "protected by reCAPTCHA"——直接匹配整段 HTML 必然误判（两次踩坑实测）。
- **joy-sourcing 图片 CDN 对 bot UA 返回 403**：图片探测/下载必须带浏览器 User-Agent（media 库导入用浏览器 UA 成功、`JoybuyResearchBot` 全部 400）。
- **Scrapy 2.13.4 自带 bug**：`ProtegoRobotParser.allowed()` 把 `can_fetch(url, user_agent)` 参数传反，任意 URL 随机 Forbidden（已实测证明）。必须用 `ROBOTSTXT_PARSER = joybuy_crawler.robots.FixedProtegoRobotParser` 修正；不可因此关掉 ROBOTSTXT_OBEY。
- **Scrapy 2.13 管道钩子**：item pipeline `close_spider(spider)` 不再传 reason（终态原因从 stats 的 finish_reason 读）；asyncio reactor 里调 Django ORM 会抛 `SynchronousOnlyOperation`——执行器进程必须 `DJANGO_ALLOW_ASYNC_UNSAFE=true`（runner.py 已内置）。
- **joybuy.co.uk robots.txt（2026-11-05 实测）**：`/s?k=<纯净关键词>` 允许；带 `&l1=/l2=/l3=/page=/sortType=` 一律禁止；`/dp/<slug>/<id>` 详情页允许。列表目标必须规范化成 `/s?k=<k>`，**分页不可爬**（缺口用 LISTING_SHORTFALL 事件如实记录）。
- **joybuy.co.uk 当前结构（2026-11-05）**：一级类目 = 14 个 `/minihome/<pagecode>` 频道链接；子类目 = `/s?k=...&l2=/l3=` 列表链接（如 Kettles & Toasters = `l2:1405`）。docs/09 里的 `l1=1409` 数字 ID 已不在现 UI，只作历史证据。
- **热浏览器 profile 会拿到降级版首页**（无类目行、minihome 链接只剩 1 个）；全新 profile 拿完整 SSR（1.9MB）。所以 `sync_joybuy_category_tree` 每次运行前重置爬虫 profile（`render.reset_browser_profile`）。SSR 内容在水合后会被替换——**必须用 `page.listen` 网络层捕获文档响应**（`render_page(capture_ssr=True)`），读 DOM 是时序竞争。
- **DrissionPage 浏览器隔离**：固定调试端口（9333）会连接到已存在的实例。`render_page` 启动前杀掉带 `browser_profiles` 标记的残留爬虫浏览器，连接后校验 9333 端口上的 chrome 进程必须带爬虫专属 user-data-dir，否则拒绝导航。绝不能让爬虫操作到运营者本体浏览器。
- **连接失败先排查 VPN/系统代理**（本机 127.0.0.1:7890）：Chrome 报 ERR_CONNECTION_CLOSED 时 curl 直连可能正常——先分清是网络断了还是被站点 403。
- **连续快速渲染会触发站点 403 限流**：类目同步页间 5s 间隔 + 403 后 60s 冷却重试（命令内置 3 次），不要连续重试硬撞。
- `fetch_url` 的参数名是 `timeout_seconds`，不是 `timeout`（传错会 TypeError "unexpected keyword"）。
- `Path("")` 是真值——`dataset_root` 曾因此返回相对路径把数据集散落在 cwd。目录解析要用显式 `if configured` 分支。
- 树同步幂等：同日同结构哈希会生成相同 `version_key`，`sync_category_tree` 对已存在版本原地重建快照（否则撞唯一约束）；同一 l2/l3 ID 会挂在多个频道下，快照去重"首次出现为准"。
- **登录检测不能只靠页面渲染**（2026-11-05 二次踩坑）：站点会持续给渲染器返回"temporary service interruption"限流页（可见文本仅几百字符），登录成功与否页面看不出来。`_is_logged_in` 必须加 **Cookie 新增信号**（profile 出现初始快照没有的新 Cookie = 登录动作发生，Cookie 是持久化的不受拦截页影响）；拦截页标记 `temporary service interruption` 已加入 render.RISK_CONTROL_MARKERS。
- **DrissionPage 浏览器隔离双层防线**：① 进程校验（9333 端口进程必须带 browser_profiles user-data-dir）；② **标签页指纹**（连接后已打开的标签若存在非空白页 → 立即 quit + 拒绝导航）。实测干净专用实例 = 1 个 `chrome://newtab/` 标签；运营者本体浏览器必然有多条真实标签页。变量命名禁忌：`crawler_account_login` 里 `options` 既是命令参数字典又是 ChromiumOptions——ChromiumOptions 必须另命名（曾致登录窗口秒退）。
- 爬虫账号 = 用户自己的 Facebook 账号（docs/05 §7.1 设计），登录后 Joybuy 显示的就是用户本人的账号——这不是隔离失败；隔离的对象是**浏览器实例**（专用 profile 无书签、独立调试端口），不是账号身份。用户曾三次误报"弹出的浏览器显示的是我正常账户"：Joybuy 按 Facebook 身份识别账号，OAuth 登录谁的 FB 就进谁绑定的 Joybuy 账号。**要独立小号必须用另一个 Facebook 账号登录**（首次登录自动建新 Joybuy 账号）。账号 Tab 已加身份说明文案，向用户解释时先讲这个模型。

- Joybuy 卡片 DOM 可能把划线价与折扣百分比无空格拼接，例如 `£2.797% off`；金额正则必须限制为最多两位小数，否则会把 `£2.79` 错存成 `2.797`。证据解析脚本已修为 `£\s*([\d,]+(?:\.\d{1,2})?)`。
- 不能只信 JSON-LD 的 `offers.price`：它通常是当前优惠价。原价必须优先读可见卡片 `[class*="crossOffPrice"]`，没有划线价才回退 `[class*="mainPrice"]`/唯一价格。
- `get_or_create_spu_from_source()` 命中既有来源身份时不会更新 `Spu.local_category`、品牌或既有翻译实体字段；演示 loader 必须显式修正类目/品牌，并用来源层+本地覆盖层的有效值同步索引读取字段，再重建搜索文档。
- 搜索接口过去完全没返回图片，即使媒体库有图也只显示骨架；图片必须按当前页 SPU 批量查 `MediaUsage(role="gallery")`，不能在序列化器里逐商品 N+1。
- `--noreload` 的 Django 开发服务器不会自动加载后端改动。本轮实库导入后 HTTP 仍无 `image_path`，确认 8000 监听 PID 后只重启了明确的后端进程；后续后端改动浏览器验证前必须先确认运行进程已加载新代码。
- CDN 单图 HTTP 400 时不得拿其他商品图片冒充。应换用同一公开楼层的下一条真实商品，保留原排名/来源证据，并把失败样本退出可搜索状态；本轮 `10489708` 已按此处理。
- Joybuy 公开榜单连续浏览器导航会偶发重定向登录页；不要反复撞登录/风控。固定子榜 URL 可低频读取服务端公开 HTML；服装不在榜单侧栏，必须明确记录替代来源。
- 详情页白名单拦截会改变既有 e2e 流程：`purchase_whitelisted` 后端默认 True 是有意设计（开发阶段放行），若把默认改 False 必须同步重写 purchase-funnel（先做 admin 白名单再购买）。
- Playwright fill 后水合重置输入属 dev 模式已知竞态（helpers.js 有注）：结算表单用"fill+click+查 Pay now"自愈循环应对；生产构建不受影响。
- 组件模板里静态 `src="/images/..."`（根绝对路径）会被 vite 模板资源转换当成模块 import：vitest 下报 `file:///images/logo.png` 参数错误，Nuxt dev 下报 Failed to resolve import。改用运行时绑定（`:src="常量"`），vitest 配置再加 `transformAssetUrls: false` 兜底。
- 新建 `storefront/public/` 子目录/文件后必须重启 Nuxt dev 才能被静态伺服（sirv 启动时扫描）；且杀 3000 端口进程后要确认真的杀掉了（`Get-NetTCPConnection` 看进程启动时间），否则新起的 dev 会静默失败、旧进程继续 404。
- 分类面板的触发按钮**不要同时实现"点击切换"+"悬停打开"**：鼠标点击前必先 hover，hover 已打开面板后 click 的 toggle 会把它关上，表现为"点了没反应"。click 只做打开，关闭交给 mouseleave（150ms 延迟）和关闭按钮。
- 全幅楼层用 `width: 100vw + margin-inline: calc(50% - 50vw)` 逃出容器会在有滚动条时产生 ~8px 横向溢出；在 `.app-main` 上加 `overflow-x: clip` 解决（sticky 头部在 main 外，不受影响；不要加在 body 上，会破坏 sticky）。
- e2e 断言里已没有 "Offers for you" 标题（需求 12 删除了活动区标题）；首页断言用活动区 Welcome Offers 链接。改首页可见元素时两个 spec（foundation/purchase-funnel）的断言和快照要一起同步。
- 真实站 joybuy.co.uk 实测值与用户给定值冲突时以用户为准（如通告条颜色用户指定 #17202A，实测 #1A1A1A）；差异写进 HANDOFF 备查。
- `LocalCategory` 的模型 Meta ordering 是 `["path", "sort_order", "pk"]`，而 path 是 `/<uuid pk>/` 前缀——按 path 排出来的根类目顺序≠需求要求的 11 类目固定顺序；凡展示类目清单必须显式 `order_by("sort_order")`（categories API 已这样写，测试断言也要）。
- `get_or_create_spu_from_source` 没有 `merchant` 参数（签名是 source_system/source_id/title/local_category 等）；演示商品归类直接改 `Spu.local_category` + `rebuild_search_document` 即可，不必走 CategoryMapping。
- storefront 组件测试里 mock `useCategoryTree` 要返回 `ref([...])`（或 `computed(() => [...])`），不能 `computed([...])`——computed 需要 getter 函数，传数组会报 `computed.fn is not a function`。
- 44px 最小可点击高度是硬性设计规则（AppHeader.test.js 会扫描所有 input/button/a 的 computed minHeight）：新增交互元素 CSS 要给 `min-height ≥ 2.75rem`（account-menu__item、category-panel__child 已设 2.75rem）。
- CMS 双语字段约定：base 字段（title/label）恒为英文，中文放可选 `title_zh`/`label_zh`/`subtitle_zh`；`pickName(item, locale, prefix)` 统一取值回退，不要在组件里手写 locale 分支。
- 通告条现在有自动轮播 interval（6s），AppHeader 组件测试挂载后不 unmount 会有 open handle 警告但不断言失败；如后续测试超时先怀疑它。

- Joybuy flight 流里区分"活动砖石"与"快捷入口"：快捷入口的 eventInfo 有 `floorType=="icon"` 和 120×120 `iconImage`；活动砖石带 `subTitle` 且无 floorType。品类发现数据认准 `externalKey=="EXT_POPULAR_CATEGORIES_V3"`。图片 URL 规则：`-com/-product` 相对路径拼 `https://images3.joy-sourcing.com/product/s{尺寸}_{path}`，png 补 `.webp`、jpg 补 `!q70.webp`；`/da/` 开头的是完整 URL 直接补 `https:`。
- 活动瓦片/入口/品牌墙的真实跳转链接都是 Joybuy 站外或本地不存在的营销页，CMS 里一律改填本地 `/search`，不要原样入库把用户带出站。
- 验证纪律（2026-11-03，用户确定）：开发阶段每轮只做针对性验证（只跑受影响的单测/检查/相关 e2e），不跑全量；全量验证留到功能全部开发完成或用户明确要求。不要在 HANDOFF 里把针对性验证写成"全量通过"。
- 改 `nuxt.config.js`（如 devProxy）后必须重启 Nuxt dev 服务器，配置不会热加载；重启用 PowerShell 杀 3000 端口进程后在 storefront 目录后台重启。
- 新爬商品默认 DRAFT（SPU/Offer 都是）：`get_or_create_spu_from_source` 与 offer 导入都不会自动 ACTIVE；演示命令里显式激活后必须再重建搜索文档，否则详情 404、搜索为空。
- `ingest_product_payload` 在爬虫包 `joybuy_crawler.ingest`（仓库根 /crawler，需 sys.path 注入），不在 `crawler_control` 里。
- `start_run` 要求 job 的 account_group 里存在 session_status=VALID 的爬虫账号；演示命令里先 get_or_create 账号并写入标记会话（非真实凭据）。
- 新增 CMS 模块类型要同时改三处：`content/schemas.py`（MODULE_TYPES+SCHEMAS+校验）、`CmsModule.Type` + 迁移、前端 `CmsRenderer` 注册（+组件）；漏掉模型枚举会在 publish 时报 Unknown module type。
- e2e 断言首页标题的规格有两个：`foundation.spec.js` 和 `purchase-funnel.spec.js`（visual baselines），改首页文案时两个都要同步；重首页在多 worker 并行下会让 funnel 用例超时，受影响 spec 用 `--workers=1` 跑。
- `$` 美元符号是展示层规则：`storefront/utils/display.js` 统一格式化，不改动任何存储币种（本地种子数据仍为 GBP）；新增价格展示必须走 `formatDisplayPrice`，不要再手写 `Intl.NumberFormat` 或手拼 `£/€`。
- “今日送达”类标签的过滤发生在渲染时（`isDeliveryLabel`）；爬虫仍照常抓 `promotion_label`，不要为了去标签去改爬虫或数据库数据。
- 商城端 vitest 没有配置 `~` 别名（只有 `#imports` stub）；组件里引用新工具必须用相对路径导入，`~/utils/...` 在 vitest 下解析失败。
- `crawler/fixtures/product_detail_v1.html` 里的 `£` 是模拟真实 Joybuy 来源页，必须保留；解析器读 `data-price` 属性，不读符号。
- 仓库 ruff 全仓检查有 47 个既有报错（多为 import 排序），不属于新任务范围，不要顺手全仓修复污染 diff；只保证自己改动的 Python 文件干净。
- CMS 首页 fixture 里的 `/p/01926c1e-...` 是不存在的假 ID，详情页 404“not available”是既有行为，不是本次或后续改动造成的回归。
- e2e 首页视觉基线已按 `$` 价格重新生成（`purchase-funnel.spec.js-snapshots`）；再改首页可见内容后必须 `--update-snapshots` 重新基线，否则视觉用例必挂。
- 不要把国家市场和语言合成一个字段；德国市场决定 EUR、价格和配送，`de-DE` 决定文本，两者默认联动但必须可独立配置。
- 不要认为页面按钮翻译完成就实现了多语言；切换后商品标题、详情、类目、属性、活动、评价、搜索索引和 CMS 必须自动一起刷新。
- 不要用“第一条 SpuTranslation”作为展示内容；必须按请求 locale 精确选择已发布版本。
- 不要强制把德国页面全部翻成德文；Joybuy 实际仍显示英文的字段必须保留英文，混合语言是正确来源状态。
- 不要要求用户点击“翻译”商品或评价；国家/语言切换后由系统自动加载对应来源快照。
- 不要把 `requested_locale=de-DE` 当作每个字段都是德文；必须逐字段记录 `actual_locale`。
- 不要把机器翻译写成 Joybuy 来源值；默认复刻链路不做强制机器翻译。
- 不要在中文来源变化时直接覆盖人工审核译文；先标记过期、生成候选、展示差异并复审。
- 不要翻译品牌、型号、GTIN、规格数值或虚构来源没有的功效/认证；法规、安全、成分和过敏原必须人工审核。
- 不要直接使用现有英文 FULLTEXT 方案承诺中文搜索；中文需要 MySQL ngram 或经验证的分词列。
- 不要继续用上一轮英文页面结果生成最终类目；后续必须在已保存的 Joybuy 简体中文会话中重新分析。
- 不要把“业务分组”当作 Joybuy 来源类目；高奢高价、电器与家装、活动商品都不是 Joybuy 当前公开菜单中的单一原生类目。
- 不要让运营手填 `source_category_public_id`；ID 必须来自已版本化的树节点选择，页面最多只读展示。
- 不要把商品数量上限解释为请求数、页面数或发现 URL 数；它是去重、通过质量闸门并成功入库的来源商品数。
- 不要把活动商品塞进类目树；活动页是独立来源类型，商品导入后仍归真实商品类目。
- 不要只保存节点中文名或假设固定三级深度；Joybuy 公开节点包含 `firstcid`、`second_product_category` 和 `cid1/cid2/cid3/cid4` 等不同层级前缀。
- 不要把勾选父节点理解为永久自动包含未来新子节点；任务创建时必须冻结类目树版本，新增节点经差异确认后才能纳入。
- 不要只改前端做“多选”；当前后端单 `source_category` 模型无法正确保存多组配额与活动来源。
- 不要把“商家基础领域模型已实现”误读为“商家端 UI 已实现”；两者不是一回事。
- 不要为了中文展示直接修改发往后端的状态、动作或排序枚举；必须保留 `ACTIVE`、`PENDING_PAYMENT`、`start` 等接口契约，仅对页面展示值做映射。
- 状态列汉化后，按钮显隐判断不能再读已汉化的 `status`；需要额外保留 `raw_status` 做业务判断。
- 登录页是公开路由，路由守卫不会预先加载会话；登录请求前必须先获取会话与防跨站令牌。
- 员工权限在会话响应的 `staff.permissions` 中，不在顶层 `permissions`；读错会导致登录成功但所有菜单被隐藏。
- 不要把 Vue 格式样式规则与 Prettier 重复启用；项目已由 Prettier 统一格式，否则会产生互相冲突的检查结果。
- 不要并行执行 Nuxt 生产构建与 Playwright 浏览器测试：构建开始时会清理 `.nuxt`，可使复用中的开发服务器短暂丢失开发清单并导致水合竞态。正确顺序是先完成 `pnpm build:frontends`，再单独运行 `pnpm test:e2e`。
- 所有前端资源必须本地托管，不得引用 CDN。

### 2026-11-05（续 3）：排序触发器不换行 + 侧栏选中色去红

- 触发器 `width: 172px` → `min-width: 172px + white-space: nowrap`（"Price: High to low" 单行显示，高度保持 40px）。
- 侧栏选中类目去红：`--colour-accent-soft/--colour-accent` → bg #F7F7F7 + color #1A1A1A + font-weight 700（与分类面板 hover 一致）。
- 验证：vitest 45/45；浏览器复核 noWrap/40px、选中 rgb(26,26,26)/rgb(247,247,247)/700 ✓（截图）。

### 2026-11-05（续 2）：排序控件改自定义下拉（左置/去蓝色）

- 用户反馈：排序应在左侧（原右对齐）；外边框与选项 hover/选中出现蓝色——根源是原生 `<select>` 的下拉弹层由 OS 渲染（Windows Chrome 蓝色高亮），CSS 无法自定义。
- 重做为自定义下拉：trigger（"Sort by:" 16px/500 + 172×40 深色描边按钮 + ⌄）左置（删除右侧 spacer）；菜单白底 1px 灰边 + overlay 阴影，选项 40px 行、hover #F0F1F4 灰、选中 #EEF1F5 灰加粗（全灰系无蓝）；点击选项 updateQuery、点击外部自动关闭（document click 监听，onMounted/onBeforeUnmount 挂载）。
- 验证：vitest 45/45；浏览器复核 triggerOnLeft ✓、菜单白底、hover rgb(240,241,244) 无蓝、选中项高亮 ✓（截图）。

### 2026-11-05（续）：列表页排序控件对齐真实站

- 实测真实站（/s?k=noodles）：标签 "Sort by:" 16px/500 #1A1A1A；触发器白底 **1px #1A1A1A 深色描边**、radius 4、高 40、16px 字；展开菜单白底、选中项浅灰高亮；选项顺序 Relevance → Price: High to low → Price: Low to high（→ Sales: High to low，后端无销量排序）。
- ProductListing：标签 16px/500 深色（原 14px 灰）；select 描边改 #1A1A1A（原浅灰）、16px 字、cursor pointer；选项文案与顺序对齐（price_desc 提前，"Price: High to low/Low to high" 大小写对齐真实站），保留 Top rated/Newest（真实站有 Sales 排序但后端暂无——差异记录）。
- 验证：vitest 45/45；浏览器复核 label/trigger/选项序列 ✓（截图）。

### 2026-11-05（续）：列表页三处（头部无缝/图区四角圆角/侧栏分割线）

- 头部与页面间隙：原 `.listing-page-bg` margin-top:0 未压过 `.app-main > *`（实测 bgTop 184 vs header 160，灰缝来自 app-main）。改为"一整块+内边距"：wrapper `margin-block: 0`（`.listing-page-bg.listing-page-bg` 双类名提权重）+ `padding-block: 32px 24px`，`.listing-layout` margin 归零。实测 bgTop==headerBottom==160 ✓。
- 图片区四角圆角遗漏点：`.product-card__media` 容器（#F5F5F5 底）自身 radius 0——img 虽 12px 但灰底方块外露。补容器 radius 12px。其它位置已排查：发现卡 12px、榜单页共用 ProductCard ✓。
- 侧栏 Category/Price 之间加 1px 分割线（`.filter-card + .filter-card` border-top）。
- 验证：vitest 45/45；浏览器复核三项 ✓（截图）。

### 2026-11-05：/s 列表页全幅白底

- 用户要求 /s?category= 页面背景 #FFFFFF。ProductListing 根部加全幅包裹 `.listing-page-bg`（margin-inline calc(50%-50vw)、bg #FFFFFF、覆写 .app-main 子项顶距）——/s、/search、/c 三个路由统一生效。
- 踩坑：脚本对 .vue 先 ast.parse 校验会在写入前中断（.vue 非 Python），导致模板替换丢失——改为先写文件再校验/或只校验 .py。
- 验证：vitest 45/45；浏览器复核 bg rgb(255,255,255)、全幅 1512、无横向滚动 ✓。

### 2026-11-04（续 11）：详情页五项（隐藏类目行/加粗面包屑/白底/#EEEFF0/粗边框）

- 详情页隐藏全局类目行：AppHeader `useRoute` 判 `/p/` 前缀时 v-if 关闭 category-nav（真实站行为）；vitest stub 的 useRoute 补 `path: '/'`（此前桩缺 path 导致 AppHeader 测试 5 连挂）。
- 面包屑加粗：14px 不变 + font-weight 700（用户参考图观感加粗）。
- 详情页整页背景 #FFFFFF：新增全幅包裹 `.detail-page-bg`（margin-inline calc(50%-50vw)）。
- 图片区背景 #EEEFF0：主图容器/img/放大面板底色统一（原 #F5F5F5）。
- 缩略图边框 1px→2px（激活态仍深色 #17202A 覆盖）。
- 验证：vitest 45/45；e2e 快照重基线 9/10（funnel 仍 D-14）；浏览器复核五项 computed 全过（截图）。

### 2026-11-04（续 10）：主图蓝色网点遮罩 + 面包屑 14px

- 用户提供真实站参考图：hover 主图时主图上出现**蓝色网点选择遮罩**（配合右侧放大图）。实现：`.detail__zoom-mask`（40%×40% = 1/2.5 放大倍率反算、中心跟随光标并 clamp 图内、蓝色半透明底 rgba(26,115,232,.14) + radial-gradient 蓝色点阵 7px 网格、pointer-events none）；onZoomMove 同步遮罩位置。
- 面包屑字号 14px（原 16px，用户参考图为 14px）、分隔符灰、去重 hover 规则。
- 验证：vitest 45/45；浏览器实测遮罩 247×247（617×0.4）、点阵/底色正确、跟随光标、右侧放大图同步（截图）✓。

### 2026-11-04（续 9）：首页榜单四项 + 详情页面包屑/布局/放大镜

- 首页（实测 18px 规格）：榜单 tab 18px（未选中 400/选中 700 #1A1A1A）、间距 32px、高 42px；View all 18px/600 下划线；榜单卡图自带四角 12px 圆角（img 自身 radius，不再依赖卡裁切）；心选品牌→畅销榜单楼层间距 48px（原 24）；【About this study build】尾注模块删除（loader 不再 append rich_text，index.vue 移除 tail 渲染，home v9=3 模块）。
- 详情页：顶部导航改真实站式可点击面包屑——Home / 类目树父链（useCategoryTree 反查 category_slug，双语 categoryName）/ 商品名，16px #1A1A1A、hover 下划线；布局列宽对齐实测（56px 缩略图轨 + 流体主图 + 671px 购买面板，主图≈617 vs 真实 591）；主图 hover **放大镜**——右侧浮出 617×617 面板（background-size 250%、position 跟随光标百分比、z-20 覆盖购买面板侧、mouseleave 关闭）。
- 验证：vitest 45/45；eslint/prettier 通过；e2e 快照重基线 9/10（funnel 仍 D-14）；浏览器复核全部通过（截图）。期间后端 runserver 再次静默退出（本日第 3 次，后台任务稳定性问题）已重启；HomeBestsellers/Promo 排序 sort=newest 同步。

### 2026-11-04（续 8）：首页整行背景 #FFFFFF

- 用户指定 `.home-page`（畅销榜单/品类发现/心选品牌模块外围）背景为 #FFFFFF。原页面继承 canvas 灰底，且容器 max-width 1440 居中后超宽视口两侧仍露灰条。
- index.vue 模板加全幅包裹层 `.home-page-bg`（margin-inline calc(50%-50vw) 撑满视口、bg #FFFFFF、覆写 .app-main 子项顶距），原容器嵌套其内。复核：bg rgb(255,255,255)、全幅 1512=viewport、无横向滚动、活动区仍与头部无缝。

### 2026-11-04（续 7）：榜单卡透明图数据源（UK 商品入库）+ multiply 底色

- 诊断：用户指出商品图背后应为 #F5F5F5 透明效果。查证：代码侧 #F5F5F5 已生效；白底来自数据——原 load_joybuy_demo 的商品图是 joybuy.com flight 的 **jpg 白底图（无 alpha）**，且 CDN 上该批图**无透明变体**（.png.webp 404 实测）。真实站榜单卡 img 无 mix-blend-mode、直接白底显示（240px jpg）。
- 修复（数据源切换）：真实站首页 Bestsellers 楼层商品的 **s480x480 `.png.webp` 透明图**有效。浏览器逐 tab 爬取真实楼层 10 tab×5 卡（title/price/透明图 URL）→ `var/joybuy_demo/data/uk_bestsellers_raw.json`（44 卡，来源 https://www.joybuy.co.uk/ 2026-11-04）；新命令 `load_uk_bestsellers_demo` 导入 44 商品（source_system=joybuy_uk，幂等 source_id=title+img md5），UK tab→我们 11 类目子树映射（Kitchen Roll→cleaning-supplies、Small Kitchen Appliances→kitchen-appliances、其余食品类→groceries-food），£ 价格存 GBP，透明图 store_bytes 本地化（43/44 成功，1 张 URL 永久失败已用 shell 手工补挂）。
- 楼层/榜单页排序 rating_desc→**newest**（新导入透明图商品排前；MySQL DESC 下无 rating 的 NULL 排序不稳）；HomeBestsellers 测试断言同步。
- ProductCard 图区：容器 bg #F5F5F5 + img **mix-blend-mode: multiply**——白底烘焙图乘底色后白→#F5F5F5，透明图直接透出，产品色几乎无损（真实站未用此法，属实现选择）。
- 验证：vitest 45/45；e2e 快照重基线 9/10（funnel 仍 D-14）；浏览器截图确认榜单为 UK 真实商品透明图、图区底色 #F5F5F5 ✓。旧 .com 白底商品仍在库（其它 tab 混排时可能出现白底图——multiply 会将其转为 #F5F5F5）。

### 2026-11-04（续 6）：榜单卡三处颜色/字号按用户指定修正

- 图片区域背景 #F5F5F5（原 surface-soft #F5F6F7）；标题字号 16px（原 --font-size-md=14px，真实站实测 16px，用户指出的字号问题根源即 token 差异）+ 颜色 #1A1A1A（原 #17202A）；价格颜色 #1A1A1A（用户指定深色，替换此前误加的红色——真实站红价是折扣价语义，我们单一原价按用户口径用深色）。
- 浏览器复核：imgBg rgb(245,245,245)、title 16px/#1A1A1A/clamp 2、price #1A1A1A ✓；vitest 45/45。

### 2026-11-04（续 5）：商品卡对齐真实榜单卡（两行省略/图贴顶）

- 实测真实站 Bestsellers 卡（首页楼层 261 宽 + 列表卡 267）：图全宽贴卡顶（无内边距、radius 由卡整体裁切）、文字区 6px 内边距、品牌粗体、标题 16px/500 行高 22px **两行截断（h44）**、红色价格粗体、40px 圆形加购钮、榜单卡无星级。
- ProductCard 重写：结构改为图贴顶（`.product-card` overflow hidden radius 12，图 radius 0）+ `product-card__body` 内边距 8/6/6；标题 clamp 移入组件自身样式（`-webkit-line-clamp: 2`、line-height 22px、min-height 44px——此前依赖全局 `.truncate-2`，实测在卡内未生效出现三行硬切）；价格改红色（--colour-accent，1.125rem/700，与真实站红价一致，仍为单一原价规则）；榜单模式（rank>0）隐藏星级、可选 `viewed_count` 渲染 "x people viewed in 72 hours" 行（搜索接口暂无该字段=数据缺失，不编造）；徽章降级为价格旁小灰签。
- 验证：vitest 45/45；eslint/prettier 通过；浏览器复核 titleClamp=2/标题高 44/五卡全部省略号结尾/红价/图贴顶/无星级 ✓；e2e 首页快照重基线 9/10（funnel 仍 D-14）。注意：dev 模式组件 CSS 经客户端 JS 注入，SSR HTML 中 grep 不到样式属正常；HMR 对样式改动偶发陈旧需重启 dev（今日两次）。

### 2026-11-04（续 4）：独立商品楼层并入畅销榜单（home v8）

- 用户指出：心选品牌与畅销榜单之间的 6 个独立商品楼层（Kitchen Roll…/Food Cupboard/Beverages/Rice…/Small Kitchen Appliances/Instant Noodle——即爬取的 bestseller 分区）应属畅销榜单数据，不应单独铺开；真实站这些分区本来就是 Bestsellers 楼层的 tab 分区。
- loader build_modules：删除 product_pool 楼层循环与旧文字品牌墙（"Brands we love" pills——被心选品牌 brand_logos 取代，二者重复）；保留 import（商品仍在库，畅销榜单经搜索接口消费）。发布 home v8：4 模块（campaign/discovery/brands(心选)/rich_text）。
- index.vue：拆分 CMS 渲染——rich_text 尾注排到畅销榜单之后（真实顺序：…心选品牌 → 畅销榜单 → 尾注），SSR h2 序实测 Category discovery→Brands we love→Bestsellers→About ✓，.cms-pool=0。
- foundation.spec 首页断言更新：'Food Cupboard' 楼层标题断言改为畅销榜单标题（/Bestsellers|畅销榜单/）+ 首个类目 tab 可见；e2e 快照重基线 9/10（funnel 仍 D-14），foundation 复跑 5/5。vitest 45/45。

### 2026-11-04（续 3）：配送至/通告条字体/首页畅销榜单楼层

- Barlow 站点字体本地化：实测 joybuy.co.uk 全站字体为 Barlow（Next local font），下载 400/600/700 三个 woff2 到 storefront/public/fonts/（自托管合规），base.css 注入 @font-face，tokens --font-stack 前置 'Barlow'（design-tokens 测试允许：禁 @font-face 仅限 tokens.css、禁 http 外链，相对路径 /fonts/ 均合规）。
- 配送至（实测修正）：左侧新增 24px 定位图钉 SVG（灰 #55565b，对应真实站 icon-font 字符）、文本 16px/600 min-width 110px；hover 改为实测的 rgba(0,16,71,0.06) 胶囊（radius 50px，无阴影）——替换原 #F0F1F4+radius 8。
- 通告条字号 14px（实测，原 12px xs）。
- 首页畅销榜单楼层（docs/12 §1 落地）：新组件 `components/home/HomeBestsellers.vue` 接在首页 CMS 楼层之后——标题"Bestsellers/畅销榜单"+右侧 View all（→/promo/best-seller?category=<active>）；标题下方 11 个标准类目 tab（横排可滚，选中=黑粗+2px 黑下划线，点击客户端 $fetch `/api/v1/search?category=&sort=rating_desc` 刷新）；下方 5 列榜单卡（ProductCard+排名徽章）。SSR 首屏拉默认 tab（home-living）。真实站同楼层位置在页面中下（discovery/brands/JoyPlus 之后），与我们 CMS 尾部位置一致。
- 验证：vitest 45/45（新增 HomeBestsellers 2 用例：tab 渲染/点击切换 $fetch 断言）；eslint/prettier 通过；e2e 首页快照重基线 9/10（funnel 仍 D-14）。浏览器复核：Barlow document.fonts.check=true、通告条 14px Barlow、配送至 16px/600+icon+胶囊、楼层 11 tabs/选中态/5 卡排名徽章、点击"电子产品" tab 数据刷新（3 商品）✓。重启 Nuxt 后楼层才出现在 SSR（新组件目录 HMR 未生效的坑：新增组件文件后需重启 dev）。

### 2026-11-04（续 2）：发现卡凸起高度按真实站实测修正

- 用户反馈 -12px 凸起太低且整卡层级抬升突兀；实测真实站：悬停 translateY(-40px)、邻卡 -8px（次邻 0）、z-index 固定按位置序号（1..6）恒定不变。
- 修正：hover -40px；邻卡 -8px（删除 -6/-3 两阶波浪，保留一阶）；li 按 nth-child 固定 z-index 1..12（不再依赖 hover 改层级）——凸起后右侧仍被右卡压住（elementFromPoint 复核 topCard=4 ✓）。
- vitest 43/43；浏览器量测 wave=[0,-8,-40,-8,0,0]、z auto（card 层）/li 层固定序号 ✓，截图与用户参考图一致。

### 2026-11-04（续）：品类发现叠层卡 + 心选品牌跑马灯

- 品类发现（tiles 变体）：改为叠层甲板布局——卡片定宽 289×366，`li + li { margin-left: -72px }` 右卡压左卡（真实站步进 222≈压 67px），每卡 box-shadow，DOM 后序卡自然在上；悬停 translateY(-12px)+阴影加深+`z-index: 10` 上浮盖住邻卡（transition 0.25s）。窄屏（<80rem）回退 3/2 列网格去掉叠层。
- 心选品牌（brand_logos 变体）：改单行跑马灯——内容渲染两份（第二份 aria-hidden），flex track `translateX(0→-50%)` 48s 线性无限循环实现右→左慢滚（两份等宽保证无缝）；容器 `mask-image: linear-gradient(to right, transparent→black 8%→black 92%→transparent)` 两缘渐隐；hover 暂停滚动；`prefers-reduced-motion` 停用动画。
- 测试：CmsRenderer 用例更新（brand-marquee track 存在、卡片 ×2 复制断言）；vitest 43/43；e2e 首页快照重基线 9/10（funnel 仍 D-14）。
- 浏览器复核：叠层步进 229（压 72px）、阴影/悬停 transform -12px/z10 ✓；跑马灯 animation 48s、mask 渐隐、24 卡（12×2）滚动 ✓（截图已核）。

### 2026-11-04（下午）：首页七项样式与数据优化（参照 joybuy.co.uk 实测）

- 通告条：内容垂直居中（inner min-height 40px）、bg #1A1A1A（实测值，替代此前误用的 #17202A）、左侧标签中文态改 "UK | 中文(简体)"（英文态仍 "UK | English"）；搜索按钮同步 #1A1A1A。
- 分类面板（AppCategoryPanel 重做）：面板宽 800px；左栏 184px、行高 36px、项间距 16px、label 14px；悬停/选中 = bg #F7F7F7 radius 8 + 字重 600 **黑色**（去掉原 accent 红）；根项 mouseenter/@focus/@click 三方式均可切换右侧子类目（悬停+点击双联动）。
- 活动区无缝：index.vue 页面容器 margin-top 清零（scoped `.home-page` 覆盖 `.app-main > *` 的 24px），实测 campaign top=header bottom=160px 零缝隙。
- 品类发现（CmsLinkGrid tiles 重做）：竖卡布局（名称左上+产品图下，bg #F5F6F7 radius 16，比例 289:366 同真实站）；6 张图从 joybuy.co.uk 发现轮播实测采样（s624x624）下载本地化（loader CATEGORY_DISCOVERY_TILES 附 URL）；CMS payload 即后台配置入口（admin-web CMS 页可改 icon_path/label/href）。
- 心选品牌（新增 link_grid variant `brand_logos`）：圆形灰底 logo（160px）+下方名称，**不可点击**（纯 span），位于品类发现下方（真实站顺序）；20 个品牌名+s220x220 logo 实测采样，loader 取前 12 个入 payload（MAX_FEATURED_BRANDS）；title "Brands we love"/"心选品牌"。
- loader 重跑发布 home v7（11 模块，新增 26 张图 0 失败）；发现卡图片映射为源站轮播顺序占位（源站当前无电子/游戏/运动卡），语义错位已记录，后台可配。
- 测试：vitest 43/43（面板 hover 联动+非红断言、discovery 图卡、brand_logos 静态渲染新用例）；eslint/prettier 通过；e2e foundation+视觉 9/10（funnel 仍 D-14 dev 水合竞态）。
- 浏览器量测复核：strip 40px 居中/#1A1A1A/标签 ✓、campaign y160==header bottom ✓、发现卡 radius16 带图 ✓、品牌 12 圆卡 50% 不可点击图加载 ✓、面板 hover bg #F7F7F7 fw600 黑色 + 子类目联动 ✓。

## 6. 验证记录

### 2026-11-05 账号隔离加固（按验证纪律仅做针对性验证）

- 用户实测反馈两问题：① 登录窗口弹出后闪退（`crawler_account_login` 里 ChromiumOptions 遮蔽 `options` 参数字典，已修复）；② 登录成功但长时间未保存（站点持续返回限流页导致页面信号检测失败）+ 对"验证会话用哪个浏览器"的疑虑。
- 修复/加固：`render_page` 新增标签页指纹防线 `_assert_clean_browser`（干净实例=1 个 chrome://newtab/ 标签，实测确认；已有真实标签页的浏览器立即 quit 拒绝导航）；`RISK_CONTROL_MARKERS` 加 "temporary service interruption"；登录检测加 Cookie 新增信号（初始快照 diff，忽略 _ga/_uet 等噪声）；verify 返回 cookie_count+detail 证据，UI 成功提示改为"在隔离无头浏览器中用该账号存储的 N 条加密 Cookie 验证"。
- 实测：任务账号01（用户自行登录成功，10 条 Cookie 已入库 VALID）真实验证跑通——隔离无头浏览器加载其 Cookie，被站点限流页拦截 → 正确返回 RISK_CONTROL_BLOCKED 且**不误标过期**（session_status 保持 VALID）；ruff 干净；账号 API 13/13。
- 遗留：站点对本机限流未解除，`verified=true` 的 UI 展示待用户稍后自行点"验证会话"确认；"验证打开本体浏览器"未能在代码路径上复现（当时账号无会话，verify 应直接返回 NO_SESSION 不开浏览器），最可能是登录等待期的有头窗口被误认——现已有双防线兜底。

### 2026-11-05 爬虫重建第 2 轮：账号管理 + 管理端 UI（按验证纪律仅做针对性验证）

- 服务启动：Docker Desktop → joybuy-dev-mysql/redis/mailpit 全部 healthy → migrate（无缺失）→ 后端/storefront/admin 三个 200。
- 后端：`manage.py test crawler_control` **83/83 通过**（新增 `test_crawler_accounts_api.py` 11 项：创建/列表（不暴露 session_cipher）/启停/风控拦截 enable/登出过期/verify 有效与过期/无会话/login 派生/权限门/404；`test_crawl_jobs_api.py` 2 项 HTTP 建任务）；ruff 全部改动文件干净。
- 前端：admin-web vitest **7/7**（CategoryTreePicker 4 项：展开/勾选 v-model/含子类目切换/搜索过滤）；eslint 0 错误；prettier 通过；locale.js 补映射。
- **浏览器实测（内置浏览器，admin@joybuy.test 登录）**：① 任务 Tab 类目树显示 14 频道+子类目计数，搜索 "Kettles" 过滤并勾选 → 创建任务「UI 实测-壶类目-2件」成功（就绪，列表类目列显示 Kettles & Toasters）；② 详情抽屉：状态/类目选择（含子类目标记）/树版本/运行记录/事件流全部正确；③ 账号 Tab：新增「FB 主账号」成功（启用/未知会话/备注正确），验证会话返回友好提示"尚未登录保存过会话"，停用→已停用（按钮变启用）→恢复启用。
- **实测抓出并修复的真 bug**：任务创建 API 用不存在的 `SourceCategory.public_id` 查类目 → 500。修复为按 `source_id` 查找（前端 `source_ids` payload），补 HTTP 层测试防回归。教训：第 1 轮只测了服务层，API 层接线错误未被捕获——以后 API 改动必须补 HTTP 级测试。
- 清理：昨天实测中断的 3 个僵尸 RUNNING run 用服务层 `cancel_run` 收尾（已变"已取消"）。
- 遗留待人工：账号"登录"流程需用户本人在弹出的 Chrome 里完成 Facebook 登录（检测/存储逻辑已实现并有单测，端到端 Cookie 落库待用户实测）。
- 按纪律未跑全量后端、全部组件或全部 e2e。

### 2026-11-05 爬虫重建第 1 轮（按验证纪律仅做针对性验证）

- ruff check + format：全部改动 Python 文件（crawler/joybuy_crawler 全部新模块、backend/crawler_control、common/admin_views.py、config/urls.py）通过；既有无关文件的 2 个旧告警（browser.py PYI034、ingest.py RUF059）未顺手修复。
- 后端 `manage.py test crawler_control`：**70/70 通过**（终版回归，含 close_spider 全失败→FAILED 新用例）（新增 test_crawler_rebuild.py 13 项：树同步 3、多类目任务 4、解析器/图片阶梯 4、数据集 2、StagingPipeline 4）；`test_crawler_import` 8/8 通过。既有测试 2 处按新语义更新：无可用账号时 start_run 改为未登录启动（不再抛错）；熔断测试改为标记 2 个账号真正触发熔断。
- **实测终验（真实爬取，小规模）**：
  1. `sync_joybuy_category_tree --publish` → 版本 `joybuy-uk-20261104-4dcfbbe5` PUBLISHED：14 一级频道 + 177 快照（163 个子类目，l2/l3 ID 原样保存 + 真实列表 URL）。
  2. 建任务（类目 l2:1405 Kettles & Toasters，product_limit=3）→ `start_run` → `run_crawl_run` 独立进程执行：列表页 `/s?k=Kettles%20%26%20Toasters`（robots 合规规范化）+ 3 个 `/dp/` 详情页全部 200。
  3. 结果：**3/3 商品 IMPORTED**（SPU/SKU/Offer 各 3）、gallery 图片 15+17+20 张全部下载 0 失败、run→SUCCEEDED、job→COMPLETED；事件流 RUN_STARTED/PRODUCT_IMPORTED 完整。
  4. 数据集落盘核对：`var/crawl_exports/d76a930e-3-2/kettles-toasters/home-appliances/{商品ID}/product.json + images/main/01.webp + images/detail/*.webp + dataset_index.jsonl`；主图实测 **1248×1248**（站点最高清规格）；product.json 含 joybuy 原生字段块（productId/priceInfo.crossOffPrice/skus[].skuId/seller/gallery 等一一对应）。
- 迭代过程中修复并复验的问题：robots 解析器参数反序（Scrapy 上游 bug）、close_spider 签名（Scrapy 2.13 变更）、asyncio 下 ORM 调用、JSON-LD image 字符串迭代 bug、CDN bot UA 403、dataset_root 相对路径、面包屑分层（选中类目为第一层）。
- docs/05（§1/§7.3/§8）与 docs/09（类目结构现状）已更新；`DrissionPage` 已装入 `.venv`（4.1.1.4）。
- 按纪律未跑全量后端、全部组件或全部 e2e；admin-web UI 属第 2 轮未动。

### 2026-11-05 管理端登录移除验证器（按验证纪律仅做针对性验证）

- ruff check --fix + format：`accounts_staff/views.py`、`serializers.py`、`tests/test_staff_auth_api.py`、`config/settings.py` 全部干净（顺带修复两个文件既有 import 顺序，最终 0 error）。
- `APP_ENV=development DEBUG=true DJANGO_DATABASE_ENGINE=mysql DJANGO_CACHE_BACKEND=redis ./.venv/Scripts/python.exe backend/manage.py test accounts_staff --verbosity 1`：11/11 通过（含新增"密码直登"与"忽略多余 totp_code"两用例）。
- `./node_modules/.bin/vitest.CMD run --config admin-web/vitest.config.js`：3/3 通过（LoginView 2 用例重写 + 路由守卫 1 项）。
- eslint（LoginView.vue/LoginView.test.js/useStaffAuth.js/admin-login.spec.js）：0 错误；prettier --check 全部改动前端文件 + README/docs：通过（`.env.example` 无 parser，不适用 prettier，人工核对仅删除 2 行）。
- e2e `./node_modules/.bin/playwright.CMD test tests/e2e/admin-login.spec.js`：首跑 1 失败——8000 端口是 21:51 启动的旧 `--noreload` 后端，仍在返回 STAFF_TOTP_REQUIRED；杀掉 38960 进程并重启后端后复跑 **2/2 通过**（管理员邮箱+密码直登到仪表盘并遍历五个管理页、审计员 RBAC 菜单隐藏）。curl 直测登录接口确认 200 返回 staff payload。
- 按纪律未跑全量后端、全部组件或全部 e2e。

### 2026-11-04 畅销榜单 11 类数据补齐（按验证纪律仅做针对性验证）

- `ruff format` + `ruff check`（仅 4 个改动 Python 文件）：通过；顺带修复 `search_services.py`/`test_search.py` 原有 import 顺序，最终 `All checks passed`。
- `.venv/Scripts/python.exe -m json.tool backend/catalog/fixtures/bestseller_demo_2026_11_04.json`：通过。
- `.venv/Scripts/python.exe backend/manage.py test catalog.tests.test_search catalog.tests.test_bestseller_demo --verbosity 2`：11/11 通过；MySQL 仅输出既有 3 条条件唯一约束警告。
- 命令参数/fixture 调整后复跑 `.venv/Scripts/python.exe backend/manage.py test catalog.tests.test_bestseller_demo --verbosity 1`：1/1 通过，重复执行第二次为 0 new SPUs。
- `vitest run storefront/components/home/HomeBestsellers.test.js --config storefront/vitest.config.js`：2/2 通过。
- 实库 `load_bestseller_demo --per-category 3`：33 条导入成功，初次 1 图失败；修正坏源后 `--only-category clothing-accessories --per-category 3`：3 条、0 图失败。最终 ORM 核对：fixture 每类 3、33 个 SPU、33/33 gallery、本地图片缺失 `[]`。
- 重启旧 `--noreload` 后端后，`GET /api/v1/search?category=beauty-personal-care&sort=rating_desc&page=1` 返回 3 条且每条 `image_path=/media/...`。
- 内置浏览器抽查 `/promo/best-seller?category=beauty-personal-care`：3 个中文商品标题和 3 张本地图均可见，图片 `complete=true`、`naturalWidth=135`；抽查 `games-accessories`：3 个 PlayStation 标题和 3 张本地图均加载成功。
- 续验（用户说“继续”后）：确认当前 8000 端口已经是 2026-11-04 18:03 启动的新后端进程，没有重复重启；再次请求美妆榜接口仍为 3 条、3 条均带本地 `/media/...` 首图；内置浏览器再次核对游戏榜 3 张图均 `complete=true`、`naturalWidth=135`；复跑 `.venv/Scripts/python.exe backend/manage.py test catalog.tests.test_search catalog.tests.test_bestseller_demo --verbosity 1`，11/11 通过（仅既有 3 条 MySQL 条件唯一约束警告）。
- 按纪律未跑全量后端、全部组件或全部 e2e。

### 2026-11-05（续 3）：排序触发器不换行 + 侧栏选中色去红

- 触发器 `width: 172px` → `min-width: 172px + white-space: nowrap`（"Price: High to low" 单行显示，高度保持 40px）。
- 侧栏选中类目去红：`--colour-accent-soft/--colour-accent` → bg #F7F7F7 + color #1A1A1A + font-weight 700（与分类面板 hover 一致）。
- 验证：vitest 45/45；浏览器复核 noWrap/40px、选中 rgb(26,26,26)/rgb(247,247,247)/700 ✓（截图）。

### 2026-11-05（续 2）：排序控件改自定义下拉（左置/去蓝色）

- 用户反馈：排序应在左侧（原右对齐）；外边框与选项 hover/选中出现蓝色——根源是原生 `<select>` 的下拉弹层由 OS 渲染（Windows Chrome 蓝色高亮），CSS 无法自定义。
- 重做为自定义下拉：trigger（"Sort by:" 16px/500 + 172×40 深色描边按钮 + ⌄）左置（删除右侧 spacer）；菜单白底 1px 灰边 + overlay 阴影，选项 40px 行、hover #F0F1F4 灰、选中 #EEF1F5 灰加粗（全灰系无蓝）；点击选项 updateQuery、点击外部自动关闭（document click 监听，onMounted/onBeforeUnmount 挂载）。
- 验证：vitest 45/45；浏览器复核 triggerOnLeft ✓、菜单白底、hover rgb(240,241,244) 无蓝、选中项高亮 ✓（截图）。

### 2026-11-05（续）：列表页排序控件对齐真实站

- 实测真实站（/s?k=noodles）：标签 "Sort by:" 16px/500 #1A1A1A；触发器白底 **1px #1A1A1A 深色描边**、radius 4、高 40、16px 字；展开菜单白底、选中项浅灰高亮；选项顺序 Relevance → Price: High to low → Price: Low to high（→ Sales: High to low，后端无销量排序）。
- ProductListing：标签 16px/500 深色（原 14px 灰）；select 描边改 #1A1A1A（原浅灰）、16px 字、cursor pointer；选项文案与顺序对齐（price_desc 提前，"Price: High to low/Low to high" 大小写对齐真实站），保留 Top rated/Newest（真实站有 Sales 排序但后端暂无——差异记录）。
- 验证：vitest 45/45；浏览器复核 label/trigger/选项序列 ✓（截图）。

### 2026-11-05（续）：列表页三处（头部无缝/图区四角圆角/侧栏分割线）

- 头部与页面间隙：原 `.listing-page-bg` margin-top:0 未压过 `.app-main > *`（实测 bgTop 184 vs header 160，灰缝来自 app-main）。改为"一整块+内边距"：wrapper `margin-block: 0`（`.listing-page-bg.listing-page-bg` 双类名提权重）+ `padding-block: 32px 24px`，`.listing-layout` margin 归零。实测 bgTop==headerBottom==160 ✓。
- 图片区四角圆角遗漏点：`.product-card__media` 容器（#F5F5F5 底）自身 radius 0——img 虽 12px 但灰底方块外露。补容器 radius 12px。其它位置已排查：发现卡 12px、榜单页共用 ProductCard ✓。
- 侧栏 Category/Price 之间加 1px 分割线（`.filter-card + .filter-card` border-top）。
- 验证：vitest 45/45；浏览器复核三项 ✓（截图）。

### 2026-11-05：/s 列表页全幅白底

- 用户要求 /s?category= 页面背景 #FFFFFF。ProductListing 根部加全幅包裹 `.listing-page-bg`（margin-inline calc(50%-50vw)、bg #FFFFFF、覆写 .app-main 子项顶距）——/s、/search、/c 三个路由统一生效。
- 踩坑：脚本对 .vue 先 ast.parse 校验会在写入前中断（.vue 非 Python），导致模板替换丢失——改为先写文件再校验/或只校验 .py。
- 验证：vitest 45/45；浏览器复核 bg rgb(255,255,255)、全幅 1512、无横向滚动 ✓。

### 2026-11-04（续 11）：详情页五项（隐藏类目行/加粗面包屑/白底/#EEEFF0/粗边框）

- 详情页隐藏全局类目行：AppHeader `useRoute` 判 `/p/` 前缀时 v-if 关闭 category-nav（真实站行为）；vitest stub 的 useRoute 补 `path: '/'`（此前桩缺 path 导致 AppHeader 测试 5 连挂）。
- 面包屑加粗：14px 不变 + font-weight 700（用户参考图观感加粗）。
- 详情页整页背景 #FFFFFF：新增全幅包裹 `.detail-page-bg`（margin-inline calc(50%-50vw)）。
- 图片区背景 #EEEFF0：主图容器/img/放大面板底色统一（原 #F5F5F5）。
- 缩略图边框 1px→2px（激活态仍深色 #17202A 覆盖）。
- 验证：vitest 45/45；e2e 快照重基线 9/10（funnel 仍 D-14）；浏览器复核五项 computed 全过（截图）。

### 2026-11-04（续 10）：主图蓝色网点遮罩 + 面包屑 14px

- 用户提供真实站参考图：hover 主图时主图上出现**蓝色网点选择遮罩**（配合右侧放大图）。实现：`.detail__zoom-mask`（40%×40% = 1/2.5 放大倍率反算、中心跟随光标并 clamp 图内、蓝色半透明底 rgba(26,115,232,.14) + radial-gradient 蓝色点阵 7px 网格、pointer-events none）；onZoomMove 同步遮罩位置。
- 面包屑字号 14px（原 16px，用户参考图为 14px）、分隔符灰、去重 hover 规则。
- 验证：vitest 45/45；浏览器实测遮罩 247×247（617×0.4）、点阵/底色正确、跟随光标、右侧放大图同步（截图）✓。

### 2026-11-04（续 9）：首页榜单四项 + 详情页面包屑/布局/放大镜

- 首页（实测 18px 规格）：榜单 tab 18px（未选中 400/选中 700 #1A1A1A）、间距 32px、高 42px；View all 18px/600 下划线；榜单卡图自带四角 12px 圆角（img 自身 radius，不再依赖卡裁切）；心选品牌→畅销榜单楼层间距 48px（原 24）；【About this study build】尾注模块删除（loader 不再 append rich_text，index.vue 移除 tail 渲染，home v9=3 模块）。
- 详情页：顶部导航改真实站式可点击面包屑——Home / 类目树父链（useCategoryTree 反查 category_slug，双语 categoryName）/ 商品名，16px #1A1A1A、hover 下划线；布局列宽对齐实测（56px 缩略图轨 + 流体主图 + 671px 购买面板，主图≈617 vs 真实 591）；主图 hover **放大镜**——右侧浮出 617×617 面板（background-size 250%、position 跟随光标百分比、z-20 覆盖购买面板侧、mouseleave 关闭）。
- 验证：vitest 45/45；eslint/prettier 通过；e2e 快照重基线 9/10（funnel 仍 D-14）；浏览器复核全部通过（截图）。期间后端 runserver 再次静默退出（本日第 3 次，后台任务稳定性问题）已重启；HomeBestsellers/Promo 排序 sort=newest 同步。

### 2026-11-04（续 8）：首页整行背景 #FFFFFF

- 用户指定 `.home-page`（畅销榜单/品类发现/心选品牌模块外围）背景为 #FFFFFF。原页面继承 canvas 灰底，且容器 max-width 1440 居中后超宽视口两侧仍露灰条。
- index.vue 模板加全幅包裹层 `.home-page-bg`（margin-inline calc(50%-50vw) 撑满视口、bg #FFFFFF、覆写 .app-main 子项顶距），原容器嵌套其内。复核：bg rgb(255,255,255)、全幅 1512=viewport、无横向滚动、活动区仍与头部无缝。

### 2026-11-04（续 7）：榜单卡透明图数据源（UK 商品入库）+ multiply 底色

- 诊断：用户指出商品图背后应为 #F5F5F5 透明效果。查证：代码侧 #F5F5F5 已生效；白底来自数据——原 load_joybuy_demo 的商品图是 joybuy.com flight 的 **jpg 白底图（无 alpha）**，且 CDN 上该批图**无透明变体**（.png.webp 404 实测）。真实站榜单卡 img 无 mix-blend-mode、直接白底显示（240px jpg）。
- 修复（数据源切换）：真实站首页 Bestsellers 楼层商品的 **s480x480 `.png.webp` 透明图**有效。浏览器逐 tab 爬取真实楼层 10 tab×5 卡（title/price/透明图 URL）→ `var/joybuy_demo/data/uk_bestsellers_raw.json`（44 卡，来源 https://www.joybuy.co.uk/ 2026-11-04）；新命令 `load_uk_bestsellers_demo` 导入 44 商品（source_system=joybuy_uk，幂等 source_id=title+img md5），UK tab→我们 11 类目子树映射（Kitchen Roll→cleaning-supplies、Small Kitchen Appliances→kitchen-appliances、其余食品类→groceries-food），£ 价格存 GBP，透明图 store_bytes 本地化（43/44 成功，1 张 URL 永久失败已用 shell 手工补挂）。
- 楼层/榜单页排序 rating_desc→**newest**（新导入透明图商品排前；MySQL DESC 下无 rating 的 NULL 排序不稳）；HomeBestsellers 测试断言同步。
- ProductCard 图区：容器 bg #F5F5F5 + img **mix-blend-mode: multiply**——白底烘焙图乘底色后白→#F5F5F5，透明图直接透出，产品色几乎无损（真实站未用此法，属实现选择）。
- 验证：vitest 45/45；e2e 快照重基线 9/10（funnel 仍 D-14）；浏览器截图确认榜单为 UK 真实商品透明图、图区底色 #F5F5F5 ✓。旧 .com 白底商品仍在库（其它 tab 混排时可能出现白底图——multiply 会将其转为 #F5F5F5）。

### 2026-11-04（续 6）：榜单卡三处颜色/字号按用户指定修正

- 图片区域背景 #F5F5F5（原 surface-soft #F5F6F7）；标题字号 16px（原 --font-size-md=14px，真实站实测 16px，用户指出的字号问题根源即 token 差异）+ 颜色 #1A1A1A（原 #17202A）；价格颜色 #1A1A1A（用户指定深色，替换此前误加的红色——真实站红价是折扣价语义，我们单一原价按用户口径用深色）。
- 浏览器复核：imgBg rgb(245,245,245)、title 16px/#1A1A1A/clamp 2、price #1A1A1A ✓；vitest 45/45。

### 2026-11-04（续 5）：商品卡对齐真实榜单卡（两行省略/图贴顶）

- 实测真实站 Bestsellers 卡（首页楼层 261 宽 + 列表卡 267）：图全宽贴卡顶（无内边距、radius 由卡整体裁切）、文字区 6px 内边距、品牌粗体、标题 16px/500 行高 22px **两行截断（h44）**、红色价格粗体、40px 圆形加购钮、榜单卡无星级。
- ProductCard 重写：结构改为图贴顶（`.product-card` overflow hidden radius 12，图 radius 0）+ `product-card__body` 内边距 8/6/6；标题 clamp 移入组件自身样式（`-webkit-line-clamp: 2`、line-height 22px、min-height 44px——此前依赖全局 `.truncate-2`，实测在卡内未生效出现三行硬切）；价格改红色（--colour-accent，1.125rem/700，与真实站红价一致，仍为单一原价规则）；榜单模式（rank>0）隐藏星级、可选 `viewed_count` 渲染 "x people viewed in 72 hours" 行（搜索接口暂无该字段=数据缺失，不编造）；徽章降级为价格旁小灰签。
- 验证：vitest 45/45；eslint/prettier 通过；浏览器复核 titleClamp=2/标题高 44/五卡全部省略号结尾/红价/图贴顶/无星级 ✓；e2e 首页快照重基线 9/10（funnel 仍 D-14）。注意：dev 模式组件 CSS 经客户端 JS 注入，SSR HTML 中 grep 不到样式属正常；HMR 对样式改动偶发陈旧需重启 dev（今日两次）。

### 2026-11-04（续 4）：独立商品楼层并入畅销榜单（home v8）

- 用户指出：心选品牌与畅销榜单之间的 6 个独立商品楼层（Kitchen Roll…/Food Cupboard/Beverages/Rice…/Small Kitchen Appliances/Instant Noodle——即爬取的 bestseller 分区）应属畅销榜单数据，不应单独铺开；真实站这些分区本来就是 Bestsellers 楼层的 tab 分区。
- loader build_modules：删除 product_pool 楼层循环与旧文字品牌墙（"Brands we love" pills——被心选品牌 brand_logos 取代，二者重复）；保留 import（商品仍在库，畅销榜单经搜索接口消费）。发布 home v8：4 模块（campaign/discovery/brands(心选)/rich_text）。
- index.vue：拆分 CMS 渲染——rich_text 尾注排到畅销榜单之后（真实顺序：…心选品牌 → 畅销榜单 → 尾注），SSR h2 序实测 Category discovery→Brands we love→Bestsellers→About ✓，.cms-pool=0。
- foundation.spec 首页断言更新：'Food Cupboard' 楼层标题断言改为畅销榜单标题（/Bestsellers|畅销榜单/）+ 首个类目 tab 可见；e2e 快照重基线 9/10（funnel 仍 D-14），foundation 复跑 5/5。vitest 45/45。

### 2026-11-04（续 3）：配送至/通告条字体/首页畅销榜单楼层

- Barlow 站点字体本地化：实测 joybuy.co.uk 全站字体为 Barlow（Next local font），下载 400/600/700 三个 woff2 到 storefront/public/fonts/（自托管合规），base.css 注入 @font-face，tokens --font-stack 前置 'Barlow'（design-tokens 测试允许：禁 @font-face 仅限 tokens.css、禁 http 外链，相对路径 /fonts/ 均合规）。
- 配送至（实测修正）：左侧新增 24px 定位图钉 SVG（灰 #55565b，对应真实站 icon-font 字符）、文本 16px/600 min-width 110px；hover 改为实测的 rgba(0,16,71,0.06) 胶囊（radius 50px，无阴影）——替换原 #F0F1F4+radius 8。
- 通告条字号 14px（实测，原 12px xs）。
- 首页畅销榜单楼层（docs/12 §1 落地）：新组件 `components/home/HomeBestsellers.vue` 接在首页 CMS 楼层之后——标题"Bestsellers/畅销榜单"+右侧 View all（→/promo/best-seller?category=<active>）；标题下方 11 个标准类目 tab（横排可滚，选中=黑粗+2px 黑下划线，点击客户端 $fetch `/api/v1/search?category=&sort=rating_desc` 刷新）；下方 5 列榜单卡（ProductCard+排名徽章）。SSR 首屏拉默认 tab（home-living）。真实站同楼层位置在页面中下（discovery/brands/JoyPlus 之后），与我们 CMS 尾部位置一致。
- 验证：vitest 45/45（新增 HomeBestsellers 2 用例：tab 渲染/点击切换 $fetch 断言）；eslint/prettier 通过；e2e 首页快照重基线 9/10（funnel 仍 D-14）。浏览器复核：Barlow document.fonts.check=true、通告条 14px Barlow、配送至 16px/600+icon+胶囊、楼层 11 tabs/选中态/5 卡排名徽章、点击"电子产品" tab 数据刷新（3 商品）✓。重启 Nuxt 后楼层才出现在 SSR（新组件目录 HMR 未生效的坑：新增组件文件后需重启 dev）。

### 2026-11-04（续 2）：发现卡凸起高度按真实站实测修正

- 用户反馈 -12px 凸起太低且整卡层级抬升突兀；实测真实站：悬停 translateY(-40px)、邻卡 -8px（次邻 0）、z-index 固定按位置序号（1..6）恒定不变。
- 修正：hover -40px；邻卡 -8px（删除 -6/-3 两阶波浪，保留一阶）；li 按 nth-child 固定 z-index 1..12（不再依赖 hover 改层级）——凸起后右侧仍被右卡压住（elementFromPoint 复核 topCard=4 ✓）。
- vitest 43/43；浏览器量测 wave=[0,-8,-40,-8,0,0]、z auto（card 层）/li 层固定序号 ✓，截图与用户参考图一致。

### 2026-11-04（续）：品类发现叠层卡 + 心选品牌跑马灯

- 品类发现（tiles 变体）：改为叠层甲板布局——卡片定宽 289×366，`li + li { margin-left: -72px }` 右卡压左卡（真实站步进 222≈压 67px），每卡 box-shadow，DOM 后序卡自然在上；悬停 translateY(-12px)+阴影加深+`z-index: 10` 上浮盖住邻卡（transition 0.25s）。窄屏（<80rem）回退 3/2 列网格去掉叠层。
- 心选品牌（brand_logos 变体）：改单行跑马灯——内容渲染两份（第二份 aria-hidden），flex track `translateX(0→-50%)` 48s 线性无限循环实现右→左慢滚（两份等宽保证无缝）；容器 `mask-image: linear-gradient(to right, transparent→black 8%→black 92%→transparent)` 两缘渐隐；hover 暂停滚动；`prefers-reduced-motion` 停用动画。
- 测试：CmsRenderer 用例更新（brand-marquee track 存在、卡片 ×2 复制断言）；vitest 43/43；e2e 首页快照重基线 9/10（funnel 仍 D-14）。
- 浏览器复核：叠层步进 229（压 72px）、阴影/悬停 transform -12px/z10 ✓；跑马灯 animation 48s、mask 渐隐、24 卡（12×2）滚动 ✓（截图已核）。

### 2026-11-04（下午）：首页七项样式与数据优化（参照 joybuy.co.uk 实测）

- 通告条：内容垂直居中（inner min-height 40px）、bg #1A1A1A（实测值，替代此前误用的 #17202A）、左侧标签中文态改 "UK | 中文(简体)"（英文态仍 "UK | English"）；搜索按钮同步 #1A1A1A。
- 分类面板（AppCategoryPanel 重做）：面板宽 800px；左栏 184px、行高 36px、项间距 16px、label 14px；悬停/选中 = bg #F7F7F7 radius 8 + 字重 600 **黑色**（去掉原 accent 红）；根项 mouseenter/@focus/@click 三方式均可切换右侧子类目（悬停+点击双联动）。
- 活动区无缝：index.vue 页面容器 margin-top 清零（scoped `.home-page` 覆盖 `.app-main > *` 的 24px），实测 campaign top=header bottom=160px 零缝隙。
- 品类发现（CmsLinkGrid tiles 重做）：竖卡布局（名称左上+产品图下，bg #F5F6F7 radius 16，比例 289:366 同真实站）；6 张图从 joybuy.co.uk 发现轮播实测采样（s624x624）下载本地化（loader CATEGORY_DISCOVERY_TILES 附 URL）；CMS payload 即后台配置入口（admin-web CMS 页可改 icon_path/label/href）。
- 心选品牌（新增 link_grid variant `brand_logos`）：圆形灰底 logo（160px）+下方名称，**不可点击**（纯 span），位于品类发现下方（真实站顺序）；20 个品牌名+s220x220 logo 实测采样，loader 取前 12 个入 payload（MAX_FEATURED_BRANDS）；title "Brands we love"/"心选品牌"。
- loader 重跑发布 home v7（11 模块，新增 26 张图 0 失败）；发现卡图片映射为源站轮播顺序占位（源站当前无电子/游戏/运动卡），语义错位已记录，后台可配。
- 测试：vitest 43/43（面板 hover 联动+非红断言、discovery 图卡、brand_logos 静态渲染新用例）；eslint/prettier 通过；e2e foundation+视觉 9/10（funnel 仍 D-14 dev 水合竞态）。
- 浏览器量测复核：strip 40px 居中/#1A1A1A/标签 ✓、campaign y160==header bottom ✓、发现卡 radius16 带图 ✓、品牌 12 圆卡 50% 不可点击图加载 ✓、面板 hover bg #F7F7F7 fw600 黑色 + 子类目联动 ✓。

## 6. 验证记录

### 2026-11-04（夜间）逐元素视觉对齐全部文档页面（按验证纪律：仅针对性验证）

- 真实站基准采集：joybuy.co.uk 列表页/详情页/榜单页实测（元素坐标/尺寸/颜色/字号/圆角），列表页左栏 234px、商品卡 274×576 radius 12、详情双 CTA 331×48 及 hover 色（#D14335/#282828）、榜单 hero 384px、排名徽章 32×32 #E4E6EB radius 8px 0；悬停遍历含卡片/按钮/缩略图/保障行。
- 商城组件：vitest 42/42；eslint+prettier 全部改动文件通过。
- 后端：accounts_buyers+checkout 14/14 通过；迁移 0004 应用；ruff 改动文件干净。
- e2e：foundation + funnel 视觉基线重基线后 9/10 通过（funnel 主流程 dev 水合竞态超时，记 D-14；功能浏览器人工全链路验证：登录→加购→3 字段地址→Save→支付步骤→Pay now→订单页 Pending payment，POST /orders 201）。
- 浏览器逐页量测复核：列表页（侧栏 234/卡 274/加购 40 圆钮/排序 h40）、详情页（标题 24/700、双 CTA 48px、步进器 47×34、保障行 54、弹窗中英文案）、榜单页（hero 384、11 品类 h48、徽章 32×32）、结算页（截图核对支付步骤+精简页脚）、首页楼层新卡。

### 2026-11-04（第二轮反馈）头部/活动区精修（按验证纪律：仅针对性验证）

- 真实站实测：joybuy.co.uk 在内置浏览器打开并逐项测量（未登录、只读）；量得通告条 40px/#1A1A1A、搜索框 #F5F6F7+1px #C2C4CC 胶囊+64×44 深色按钮、圆形按钮 52px、卡片 277×277、活动区全幅带背景图（URL 已采样）。
- 商城组件针对性：`vitest run --config storefront/vitest.config.js` 42/42 通过（AppHeader/AppCategoryPanel/CmsRenderer 用例已随新交互更新）；eslint 改动文件 0 错误；prettier 改动文件全部通过。
- e2e 针对性：foundation + purchase-funnel（`--workers=1`）：`--update-snapshots` 重基线 10/10，复跑确认 10/10。
- `load_joybuy_demo` 重跑：发布 home v6，活动区背景图下载本地 0 失败；ruff 改动 Python 文件通过。
- 浏览器实测（1512 视口量测）：通告条 40px/#17202A 居中；搜索框 898×52（flex 自适应，接近目标 879px）；搜索按钮 64×44 框内右嵌；分类/购物车/个人按钮 52px；类目行 40px 平均分布；活动区 1512×600 全幅背景图、无标题；面板与分类按钮左对齐（x 坐标一致）、紧贴按钮下方；无横向滚动（scrollWidth == clientWidth）。

### 2026-11-04 docs/12 改造第 1 轮（按验证纪律：仅针对性验证）

- 后端针对性：`manage.py test catalog content` 43 项全部通过（含新增 `test_standard_categories.py` 5 项：11 类目顺序/双语/隐藏旧根类目/幂等/演示商品归类+搜索文档重建，以及 categories API 嵌套双语断言）；`makemigrations --check --dry-run` 无缺失迁移；ruff 只查改动 Python 文件（含迁移 0007）全部通过。
- 商城组件针对性：`vitest run --config storefront/vitest.config.js` 41/41 通过（重写 AppHeader.test.js 5 项、新增 AppCategoryPanel.test.js 2 项与 tests/use-locale.test.js 3 项）；eslint 只查改动前端文件无错误；prettier 对全部改动前端文件 `--write` 后格式通过。
- e2e 针对性：只跑受影响的 `foundation.spec.js` + `purchase-funnel.spec.js`（`--workers=1`）：先 `--update-snapshots` 重基线首页 4 视口 10/10 通过，再复跑确认 10/10 通过。其余 e2e 未受影响未跑。
- 数据命令实跑：`seed_standard_categories --assign-demo-products`（11 根类目+42 子类目，53 商品归位，0 失败）；`load_joybuy_demo` 重跑发布 home v5（10 模块、53 商品、0 图片失败）。
- 浏览器实测：英文/中文首页（通告条无 Download Joybuy、类目行 11 项、为你推荐/品类发现双语）、Categories 面板（11 根类目 + 严格父子联动）、`/s?category=electronics`（3 商品）、语言切换 cookie 均正常，截图核对通过。

### 2026-11-03 首页对齐真实 Joybuy 结构（按新验证纪律：仅针对性验证）

- 后端针对性：`manage.py test content` 5 项通过；`makemigrations --check --dry-run` 无缺失迁移（含新 `content/0003`）；ruff 仅查改动文件全部通过。
- 商城组件针对性：`vitest run --config storefront/vitest.config.js` 35/35 通过（含 campaign_grid 与 link_grid variant 新用例）；平台端组件未改动，未跑。
- lint/format 针对性：eslint 只查改动前端文件（通过）；prettier 只查改动文件（通过）。
- e2e 针对性：只跑受影响的 `foundation.spec.js` + `purchase-funnel.spec.js`（`--workers=1`）：`--update-snapshots` 重基线 10/10 通过，复跑确认 10/10 通过。其余 e2e 未受影响，未跑。
- `load_joybuy_demo` 重跑：提取 10 活动瓦片 + 6 快捷入口 + 7 品类发现磁贴，新增 23 张本地图片 0 失败，发布 home v4（11 模块）。
- 浏览器截图对比：顶部通知条/红色搜索头部/活动砖石区/圆形入口/品类发现与用户提供的真实截图逐块对齐；商品楼层 `$` 原价不变。

### 2026-11-03 Joybuy 主页复刻效果展示（按新验证纪律：仅针对性验证）

- 后端针对性：`manage.py test content` 5 项通过；`makemigrations --check --dry-run` 无缺失迁移；ruff 仅查改动文件（`load_joybuy_demo.py` 修掉自身 I001 后）全部通过。
- 商城组件针对性：`vitest run --config storefront/vitest.config.js` 34/34 通过（含新 link_grid 用例）；平台端组件本轮未改动，未跑。
- lint/format 针对性：eslint 只查改动前端文件（通过）；prettier 只查全部改动文件（通过）。
- e2e 针对性：只跑受影响的 `foundation.spec.js` + `purchase-funnel.spec.js`（`--workers=1`）：先 `--update-snapshots` 重基线 10/10 通过，再不带更新复跑确认 10/10 通过。其余 e2e（auth、admin-login）未受本轮改动影响，未跑。
- 浏览器实测：首页顶部/商品楼层/底部（品牌墙+页脚）、详情页、搜索页截图与内容断言均正常；图片统计 60 张 0 失败（46 张为视口外懒加载）。
- 上一轮"原价/送达标签/$ 展示"任务曾按旧纪律做过一次全量验证（后端 216、e2e 15），结果见下一条目；按新纪律后续轮次不再默认全量。

### 2026-11-03 原价采集、送达标签过滤与美元展示

从仓库根目录实际执行（后端测试需 `APP_ENV=development DEBUG=true DJANGO_DATABASE_ENGINE=mysql DJANGO_CACHE_BACKEND=redis` 前缀，走 `.venv/Scripts/python.exe`）：

- `./.venv/Scripts/python.exe backend/manage.py test crawler_control.tests.test_crawler_import`：8 项通过（含新的原价契约断言）。
- `./.venv/Scripts/python.exe backend/manage.py test`：216 项全部通过。
- `./node_modules/.bin/vitest.CMD run --config storefront/vitest.config.js`：33 项通过（7 个文件，含新增 `utils/display.test.js`）。
- `./node_modules/.bin/vitest.CMD run --config admin-web/vitest.config.js`：2 项通过。
- `./node_modules/.bin/eslint.CMD storefront admin-web playwright.config.js tests/e2e`：无错误。
- `./node_modules/.bin/prettier.CMD --check <全部改动文件>`：通过（ProductCard.vue 曾报格式问题，已 `--write` 修复后复检通过）。
- `./node_modules/.bin/playwright.CMD test tests/e2e/purchase-funnel.spec.js --update-snapshots`：5 项通过，首页 4 个视口快照按 $ 价格重新基线化。
- `./node_modules/.bin/playwright.CMD test`：15/15 全部通过。
- 浏览器实测：`http://127.0.0.1:3000/` 首页渲染 `$19.99 / $39.50 / $4.99 / $54.00`；`/search` 全为 `$` 价格；真实商品详情页渲染单一 `$19.99` 与配送文案 `$20`，无划线价元素。
- ruff：改动的 `crawler/joybuy_crawler/parsers/product_detail.py` 干净；`test_crawler_import.py` 仅剩既有 I001（import 块，非本次改动引入）。

### 2026-11-03 中文来源与多语言方案

- Joybuy 设置验证：已选择并保存 `中文(简体) - ZH`，页面标题、导航、活动入口和商品标题已实际显示中文；中文浏览器会话已保留。
- 用户澄清后的文档复验：已扫描并移除“缺德文隐藏商品”“用户点击翻译”等冲突方案；德国页面允许按 Joybuy 来源呈现德英混合。
- 本轮只修改 Markdown 文档，业务代码和数据库均未修改。
- `pnpm exec prettier --check docs/10-multilingual-content-and-market-design.md docs/09-crawler-category-task-redesign.md docs/README.md docs/01-requirements.md docs/04-data-model-and-storage.md docs/05-crawler-and-ingestion.md HANDOFF.md`：通过。
- PowerShell 相对文档链接检查：通过，`docs/*.md` 中所有相对链接均能解析。

### 2026-11-03 爬虫品类方案

- Joybuy 现场分析：已在公开首页及相关公开类目页逐项读取页面元素、类目标识和活动链接；未登录、未提交数据、未绕过验证码或风控。
- 本轮只修改 Markdown 文档，业务代码和数据库均未修改。
- `pnpm exec prettier --check docs/09-crawler-category-task-redesign.md docs/README.md docs/05-crawler-and-ingestion.md HANDOFF.md`：通过。
- PowerShell 相对文档链接检查：通过，`docs/*.md` 中所有相对链接均能解析。
- `pnpm format:check`：通过；该命令覆盖既有前端/配置格式范围，文档另由上一条 Prettier 命令单独验证。

### 2026-11-03 平台端中文化（历史）

从仓库根目录实际执行：

- `pnpm format:check`：通过，所有纳入检查的文件符合 Prettier 格式。
- `pnpm lint:frontends`：通过，ESLint 无错误。
- `pnpm test:components`：通过，购物端 27 项 + 平台端 2 项，共 29 项。
- `pnpm build:frontends`：通过，Nuxt 购物端与 Vite 平台端均完成生产构建。
- `pnpm test:e2e`：最终串行复验通过，15/15 Chromium 浏览器测试全部通过；管理员测试已遍历五个管理页面的中文标题。
- 浏览器日志中支付尝试接口的 HTTP 422 是既定的“当前地区暂不支持”业务占位语义，对应购物漏斗断言通过，不是本次失败。
