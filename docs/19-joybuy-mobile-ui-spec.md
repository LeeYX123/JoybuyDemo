# 19 — Joybuy 手机版（m. 站）UI 实测规格

> 实测来源：Wayback Machine 2026-05-20 快照（`m.joybuy.co.uk` 首页，iPhone 13 390×844 渲染）。
> 现网 m. 站有风控门禁（`risk605_login`，未登录强制跳登录页），匿名无法直接访问；
> 存档中懒加载图片为灰色占位，涉及占位图的颜色为近似值，实现时优先复用桌面版 design tokens。
> 原始采集物：`var/mjoybuy_survey_20261124/`（截图、HTML、outline/floors JSON）。

## 0. 全局

- 视口基准：390×844（iPhone 13），页面总高 4910px。
- **无底部 tab 栏**（唯一固定元素是右下 40×40 反馈悬浮钮）。
- 站点红：`#E1251B`（徽章/角标色，与桌面 tokens 的 accent 一致族）。
- 字体沿用桌面 Barlow 栈；正文基准 16px。
- **APP 下载条（顶部 73px）按用户决定排除，不复刻。**

## 1. 头部（总高 147px，三段，全部白底）

### 1.1 主行（56px）

| 元素 | 尺寸 | 位置 | 样式 |
|---|---|---|---|
| 汉堡按钮 | 24×28 | x16 | ≡ 带点图标，黑 |
| Joybuy logo | 88×24 | x44 | 红色文字 logo |
| Ship-to 胶囊 | 78×28 | x136 | bg #F5F6FA，圆角胶囊（真站为地址入口） |
| 账户图标 | 24×24 | x302 | 线性笑脸 icon |
| 购物车图标 | 24×24 | x350 | 线性购物车 icon |

本项目替换：真站的 Ship-to 胶囊位置改为**【申请店铺】入口**（复用 AppHeader 三态逻辑：未登录→登录后回申请页；已批准卖家→切商家控制台；否则→/account/apply-shop），样式用同规格胶囊（bg #F5F6FA、h28、圆角）。

### 1.2 搜索行（52px）

- 搜索胶囊 358×44 @x16，bg #F5F6FA，圆角 22（全胶囊），placeholder "Search on Joybuy" 16px 灰，右侧放大镜 24×24。
- 点击进手机版搜索页（Phase 2 实现，先占位桌面路由）。

### 1.3 品类 tab 行（39px，横向滚动）

- tab 高 38，文字 16px；**选中态 700 + #1A1A1A + 2px 黑下划线**；未选中 400 黑。
- 真站 12 个 tab（Home + 11 类目）；本项目用 **Home + 我们的 11 个根类目**，点击 → 类目页 `/c/[slug]`（Phase 2 前可先落列表页 `/s?category=`）。

### 1.4 品类落地页 `/categories`（用户 2026-11-24 展开态截图实测）

- 真站点抽屉/头部的「分类」后进入**独立品类落地页**，不是抽屉内展开。
- 头部主行左上角汉堡换成 **← 返回**；搜索行照常。
- 页面浅灰底 `#F5F6FA`，两个分区，均为 **2 列白卡网格**（卡 radius 12、标题 16px/600 左上、商品图居中偏下、卡高 ~148）：
  1. **为你推荐**——带商品图的精选类目卡（本项目取有本地图的前 8 个根类目）
  2. **全部分类**——全部根类目
- 本项目路由 `/categories`（`pages/categories.vue` + `components/mobile/MobileCategories.vue`），数据 = 11 根类目 + `assets/category-images.js` 本地类目图。

## 2. 首页楼层（自上而下）

### 2.1 Welcome to Joybuy

- 标题 28px/600 居中；下方三圆图标（~76px 灰圆）+ 16px 文字（Speedy delivery / Trusted quality / 24/7 service）；黑色 CTA 条 358×36，bg #1A1A1A、圆角 0、白字 16px；"Learn more" 16px 居中下划线。
- 数据映射：复用桌面「心选品牌/保障」语义，或按真站三项固定文案；注册 CTA 指向 `/auth/register`。

### 2.2 Offers for you（对应桌面 campaign 活动）

- 标题 ~28px/700 + 内容横滚（第一卡外右侧露卡边）；卡 ~248×267，圆角 16，bg #F4F5F9 近似，文案 24px 深色在顶部，"Shop now" 下划线在底部。
- 数据映射：桌面 CMS campaign 楼层瓦片，按 m. 卡式渲染。

### 2.3 Category discovery（对应桌面品类发现）

- 标题 28px/700 + 右侧 56px 圆形 chevron 按钮（浅灰底）；内容为**横滚大圆**（~95px 浅灰圆内嵌商品图），圆下 label 居中。
- 数据映射：桌面 CATEGORY_DISCOVERY_TILES 同一份数据。

### 2.4 Bestsellers（对应桌面畅销榜单）

- 标题 28px/700 + 右侧 56px 圆 chevron；下方**子品类 tab 行**（16px，选中 700 + 黑下划线，未选中 400）。
- 榜单卡**横滚**：146×250、间距 8；排名徽章左上角（灰底白字圆角方块 ~32×32），收藏心形右上角，商品图 ~146 方形，标题两行截断，红色价格（#E1251B 族）。
- 数据映射：复用桌面 Bestsellers 数据（搜索接口 sort=rating_desc），tab 用其子类目。

### 2.5 Shop and save with JoyPlus Perks（对应桌面 joyplus）

- 全幅淡紫渐变底；标题 32px/700；3 行卖点（白底小方图标 + 20px 文字）；黑色 CTA 358×44 圆角 8，白字粗体 "Join JoyPlus"。

### 2.6 Brands we love（对应桌面心选品牌）

- 标题 28px/700；圆 logo 横滚（~96px 灰圆 + 名称），跑马灯/横滚。

### 2.7 Shop by look / 尾注（rich_text）

- 暗色 banner 区（存档图缺失，实现时按桌面 rich_text/尾注内容 + 暗底样式呈现）。

### 2.8 Recommended for you（对应桌面 HomeRecommended）

- 标题 28px/700；**2 列网格**商品卡（卡宽 ~178，16px 边距/间距），灰底占位图 + 标题 + 红价。

### 2.9 About Joybuy（页尾保障区，bg #F5F6FA）

- 标题 24px/700；3 行「图标 + 16px 文字」卖点；"Learn more" 下划线；细分割线收尾。

### 2.10 页脚

- 极简：Trustpilot 徽章行，无链接列、无版权大块。
- 本项目页脚放**「电脑版」切换链接**（方案决定）+ 必要政策链接（复用 web `/help/[slug]`）。

## 3. 汉堡菜单（左上角三条横杠）——用户已提供真站截图（2026-11-24）

真站抽屉（登录态截图，存 `C:\Users\lyx\.workbuddy\clipboard-images\clipboard-2026-11-24T14-40-56-257Z-88b83d78.png`）实测：

- **面板**：左侧滑出宽 **320px** 全高白底，右侧主页面暗化遮罩；面板右上角灰色细 × 关闭钮。
- **用户区**（顶部，浅灰底 #F7F8FA 带底分割）：48px 圆形浅灰头像（笑脸图标）+ 用户名 16px/700 + 右侧「登出」按钮（约 72×36、白底、1px #E0E1E5 边、圆角胶囊、14px 灰字）。
- **粗体行**（17px/700 + 右 chevron，行间粗分割）：
  1. 「分类」——点开展开品类树（或跳类目页）
  2. 「Joybuy 首页」
- **菜单项列表**（行高 **57px**，1px #F0F1F2 分隔线；左 24px 线性图标 + 16px/400 文字 + 右侧数字徽标 + 灰 chevron）：
  - 订单（右 "0"）、消息、心愿单、优惠券（右 "1"）、地址、国家/地区和语言、设置
- 列表结束后为 #F5F6FA 空白区直至底部。

本项目内容映射（决策 2026-11-24，复用 web 已有资源）：
- 用户区：头像+用户名+登出（未登录态显示 登录/注册）；补充【申请店铺】入口（三态，方案既定）。
- 分类 → **跳转独立品类落地页 `/categories`**（真站实测，见 §1.4，非抽屉内展开）；Joybuy 首页 → `/`。
- 订单 → `/account/orders`；心愿单 → `/account/favourites`；地址 → `/account/addresses`。
- 消息 → 客服对接 `/help/customer-service`；真消息页 tab 只保留【客服】和【订单】（待用户消息页截图后补页面）。
- 优惠券 → **去掉**（web 无对应）。
- 国家/地区和语言 → 抽屉内子视图（复用 locale 切换，当前语言打勾）。
- 设置 → 抽屉内子视图：账户安全（→/account）、消息通知/个性化设置/管理Cookies（**仅开关 UI，不实现逻辑**）、法律信息（展开：使用条款/Cookie 政策/隐私政策/销售政策/无障碍声明 → 复用 web `/pages/[slug]`）、退出登录（真实登出）。

## 4. 切换/跳转行为（见 ADR-0001）

- 阈值 ≤768px 双向自动跳转，保留完整路径；`?nomobile=1` 测试旁路；页脚双向手动链接，localStorage 永久优先。

## 5. 账号页 `/account`（用户 2026-11-24 五张截图实测，已实现）

- 组件 `components/mobile/MobileAccount.vue`，`pages/account/index.vue` 按 host 分支渲染（桌面版式未动）。
- 结构（自上而下，浅灰页底 + 白卡分区）：
  1. 用户卡：52px 圆头像 + 18px/700 用户名（display_name 优先）。
  2. **订单**：标题行 → `/account/orders`；三瓦片 待付款(`?tab=pending_payment`)/待收货(`?tab=to_receive`)/售后单(`/account/returns`)。
  3. **收藏**：两卡 我的收藏(`/account/favourites`)/再次购买(`/account/recently-viewed`)。
  4. **活动与奖励**：仅「评价」→ `/account/reviews`（按用户决定：优惠券不要、积分&任务/邀请有礼无 web 对应不保留）。
  5. **获取帮助**：24/7在线支持 → `/help/customer-service`（复用 web 客服页）；反馈 → `/pages/contact-us`。
  6. **更多**：语言 → `/account/language`（新页，语言列表+当前打勾）；设置&隐私 → `/account/settings`。**国家/地区按用户决定去掉**。
  7. About Joybuy 灰带（3 卖点 + 了解更多）+ 页脚（电脑版切换 + 政策链接）。
- 未登录态：登录/注册入口 + 在线支持 + 语言行。
- **排除项（用户决定）**：JoyPlus 会员免费试用横幅、优惠券行、评价与问答改仅评价、更多里的国家/地区。

## 6. 设置&隐私 `/account/settings`（独立页面，非抽屉子视图）

- `MobileAccountSettings`：5 行（账户安全/消息通知/个性化设置/管理Cookies/法律信息）+ 退出登录（真实登出）。
- 开关类模块进入 `/account/settings/[key]`（`MobileSettingToggle`）：说明 + 开关 UI，**背后逻辑不实现**（用户决定）；法律信息 → `MobileLegalLinks`（5 个政策链接复用 web `/pages/[slug]`）。
- 抽屉内原语言/设置子视图改为跳转这两页（抽屉不再有子视图）。
