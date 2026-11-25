# 20 — 手机版第 2/3 期规格（列表/详情/购物车/结算/账号子页）

> 2026-11-25。实测结论：Wayback 对 m. 站 `/s`（URL 索引截断不可回放）、`/dp`（存档为错误页）、
> `/cart`、`/checkout`（无存档）均无法提供可用参照 → 按用户决策「实测优先，缺的自设」，
> 全部页面采用 **m. 设计语言自设**（复用 docs/19 实测体系：390 基准、16px 正文、#F5F6FA 浅灰、
> #1A1A1A 主色、圆角 12 卡片、57px 行、16px/700 选中态 + 2px 黑下划线、#E1251B 红价）。
> 内容结构与数据全部复用桌面端现有实现。

## 0. 通用约定

- 移动布局分支：页面内 `useMobileView().isMobileHost` → 渲染 `components/mobile/MobileXxx`，桌面分支逐字不动。
- 子页头：`MobilePageHeader`（返回 + 17px/700 居中标题，48px 高，1px #F0F1F2 下边线）。
- 商品卡：2 列网格，间距 12，白卡 radius 12，图 1:1 cover，标题 14px 两行截断，红价 16px/700。
- 底部悬浮购买条（详情/购物车/结算）：56px 高，白底 + 上边线，主按钮 48px 圆角 24 黑/红。
- i18n：新文案加 `mobile.*` 键（en+zh），复用已有键优先。
- 每个 Mobile 组件不复制桌面业务逻辑：数据用同接口（apiBaseInternal SSR 模式照抄现有页面）。

## 1. 商品列表 `/c/[slug]` 与搜索 `/s`

- 头部三段照常（品类 tab 行选中态高亮当前类目）。
- 工具行：结果数（16px）+ 排序下拉（综合/价格↑/价格↓/评分，复用 listing.sort* 键）。
- 商品 2 列网格（复用 ProductCard 数据形状，新 MobileProductCard 或直接复用 ProductCard？→ 用独立 MobileProductCard 按本规格画）。
- 分页：页码（上一页/下一页胶囊 + 当前 x/y）。
- 分页控件、排序参数沿用桌面 listing 现有 query/接口。

## 2. 商品详情 `/p/[id]`

- 画廊：全宽方图（aspect-ratio 1，多图圆点指示，暂用单图静态展示不实现滑动切换）。
- 信息块：标题 16px/700 两行、红价 22px/700（retail_price → price_min 回退）、促销标签 badge。
- 规格：变体轴按钮（.detail__variant 同语义，移动样式胶囊 32px）；数量步进器。
- 底部悬浮购买条：加入购物车（描边红）+ 立即购买（实底红）两钮各 50%。
- 详情区：规格表折叠（点击展开）；服务保障行（复用 detail.guarantee* 文案）。
- 数据同桌面 detail 接口。

## 3. 购物车 `/cart`

- 行卡：图 72px 方、标题两行、单价红、数量步进、删除；白卡 radius 12 分隔 8。
- 全选行 + 合计区：总价红 20px/700、去结算按钮 48px 实底红全幅。
- 空车态复用 cart.empty 文案 + 去逛逛按钮。
- 数据/操作复用 useCart（桌面同源）。

## 4. 结算 `/checkout`

- 地址卡（已有地址显示 + 新增表单复用桌面 3 字段逻辑，新账号默认展开表单——与 e2e 行为一致）。
- 商品清单（图 48px + 数量）、金额小结（小计/运费/合计）。
- 支付方式选择行（复用 checkout.paymentMethod 数据，卡片/支付平台行）。
- 底部悬浮条：合计 + Pay now 实底红 48px。
- 自提/配送 tab 如桌面有则保留精简。

## 5. 账号子页（第 3 期全量）

统一壳：MobilePageHeader + 浅灰底白卡列表/网格；数据接口与桌面同名页面一致。

1. **订单列表 `/account/orders`**：tab 行（复用 AccountTabs 语义，16px 选中下划线）+ 订单卡（状态 badge、首商品图、单号/时间/合计、查看详情）。
2. **订单详情 `/account/orders/[id]`**：状态卡 + 收货信息 + 商品行 + 金额明细 + 支付方式。
3. **心愿单 `/account/favourites`**：2 列商品卡 + 移除。
4. **地址簿 `/account/addresses`**：地址卡列表（默认标记）+ 新增/编辑表单（复用桌面字段与校验）+ 配送/自提 tab。
5. **售后 `/account/returns`**：tab 行 + 记录卡。
6. **评价 `/account/reviews`**：按用户决定只保留「评论」语义——页头「我的评价」，待评价/已评价两 tab（复用桌面 reviews 数据），**不显示问答 tab**。
7. **消息页 `/account/messages`（新路由）**：两个 tab——【客服】（入口到 /help/customer-service + SupportChatLauncher 触发）与【订单】（订单通知列表，占位数据来自订单接口状态变更）。抽屉「消息」行指向本页。

## 6. 验证与提交纪律（每个子 agent 遵守）

- eslint + prettier 全过；vitest 目标目录全过（新组件至少 1 个用例）。
- Playwright 冒烟（m.localhost:3000，dev server 已在跑）：渲染断言 + 截图存 var/。
- 每页一个 commit（中文短句，格式沿用现有 log）。
- 桌面分支逐字不动；locales 只追加键。
