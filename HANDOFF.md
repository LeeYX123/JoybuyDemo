# Joybuy 新会话交接文档

> 本文档是新会话的第一入口。每次任务结束前必须更新；详细纪律见 `AGENTS.md`。

## 1. 我们在做什么

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
- 新验证纪律（用户 2026-11-03 确定，已写入 `AGENTS.md`）：开发阶段每次任务只做针对性验证（仅覆盖本次改动的模块/文件），全量验证只在功能全部开发完成或用户明确要求时跑。不得每轮默认全量。
- 用户明确分工（上一轮）：原价规则是爬虫职责；“今日送达”标签过滤与 `$` 符号只是页面展示层职责，与爬虫无关。
- 此前任务“Joybuy 中文会话与多语言内容方案”的口径仍然有效：切换国家/语言后所有内容自动刷新，德英混合是正确来源状态；类目分析仍暂停，须用已保存的中文会话重新分析。
- 上一任务“平台管理端全面中文化（仅保留 Joybuy 标识）”已完成并通过验证，历史记录保留在下方。

## 2. 已经完成了什么

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

## 3. 当前卡在哪里

- “是否强制全德文/是否由用户触发翻译”的产品口径已经闭合，不再是阻塞。
- 后续仍需现场分析德国市场：默认/可选语言、币种、配送上下文，以及首页、类目、商品、属性、活动和评价分别为德文还是英文；本轮按用户要求暂不继续分析类目。
- 国际化实现不能只改 `SpuTranslation`：现有 `ProductSearchDocument` 每个 SPU 只有一行，商品详情取第一条翻译，搜索和详情市场基本固定为 GB；实现前必须一起重构市场/请求语言解析、字段实际语言和 `(spu, market, requested_locale)` 搜索索引。
- 本次不是技术阻塞，而是四个必须闭合的产品口径：高价最低价格（建议 `£300`）、机械手表的关键词/属性识别规则、任务总商品数是否预填默认值（建议候选 `1000`）、活动商品是否默认全选当前四个公开入口。
- 现有 `CrawlJob` 只有一个 `source_category` 和一个 `product_limit`，无法表达 10 个业务分组、多选类目树和活动页来源；确认方案后需要新增配额与来源选择关联模型，不能只改前端表单。
- Joybuy 二级结果页展示的下一层有时是性别或跨目录筛选维度，不总是传统子类目；实现时必须原样保存 `cid1/cid2/cid3/cid4` 前缀和来源 ID，不能只按深度猜层级。
- 商家端页面不存在，这不是本次遗漏，而是已确定的需求边界。如果后续需要商家端，必须先由用户提供参考页并重新评审需求，不能自行复制平台管理端。
- Git 基线（2026-11-04）：全部项目已提交并推送 GitHub（origin=LeeYX123/JoybuyDemo，main 分支，初始提交 1a76a99，362 文件；var/ 数据与工具状态目录已 gitignore）。后续改动基于此基线正常提交即可。

## 4. 下一步计划

1. 继续与用户讨论剩余多市场行为；在用户允许现场分析后，依次核对德国市场和其他目标市场/语言组合。
2. 证据闭合后，把国际化改造拆成独立小工作包：MarketLocale、市场本地化内容与字段语言元数据、API 上下文切换、搜索索引、购物端自动刷新和管理端来源对比。
3. 再使用已保存的 Joybuy 中文会话重新分析类目；不直接复用英文名称生成最终 seed。
4. 中文类目完成后，再回到 `docs/09-crawler-category-task-redesign.md` 第 10 节的四个品类口径和配额页面实现。
5. 任何后续任务结束前，继续按 `AGENTS.md` 更新本文档。

## 5. 已踩过且绝对不能再踩的坑

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
