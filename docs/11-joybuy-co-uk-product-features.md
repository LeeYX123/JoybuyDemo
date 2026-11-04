# Joybuy（joybuy.co.uk）产品功能分析文档

- **产品名称**：Joybuy（JD 旗下英国一站式中超/综合电商，口号 "Don't just buy, Joybuy"）
- **URL**：https://www.joybuy.co.uk/
- **分析方式**：浏览器实际遍历（2026-11-03，19:46–20:01 GMT+8，约 15 分钟内完成）
- **探索范围**：首页、Categories 全部一级类目弹出菜单、顶部 13 个频道导航、搜索/类目列表页、商品详情页、购物车页；未进入任何需要登录或需要提交数据的页面。

## 一、全局功能（所有页面共享）

| 模块 | 功能名称 | 功能描述 | 关键操作 |
|---|---|---|---|
| 全局-顶栏 | 切换语言/国家/货币 | 顶部横幅左侧提供语言（English/中文简体）、货币（GBP £）、国家/地区（United Kingdom）的切换入口 | 顶栏 "UK \| English" 按钮、Change currency / Change country 链接 |
| 全局-顶栏 | 查看服务承诺轮播 | 顶部横幅滚动展示 Quality Guaranteed、Same-day & Next-day Delivery、24/7 Customer Support、Free returns、Welcome Offers 等承诺文案 | 横幅及 previous / next 切换箭头 |
| 全局-顶栏 | 下载 APP | 引导下载 Joybuy iOS / Android 应用，弹出含 App Store 与 Google Play 下载链接的面板 | "Download the APP" 按钮、App Store / Google Play 链接 |
| 全局-页头 | 打开分类菜单 | 打开全站类目树弹出面板（详见"分类导航"模块） | "Categories" 按钮 |
| 全局-页头 | 搜索商品 | 在全站搜索框输入关键词，点击搜索图标跳转到搜索结果页（/s?k=关键词） | 搜索输入框（placeholder "Search on Joybuy"）、搜索按钮 |
| 全局-页头 | 设置配送地址 | 查看并修改配送邮编（当前示例 SW1A 1AA），影响可购商品与配送方式（本轮按约束未修改） | "Deliver to SW1A 1AA" 按钮 |
| 全局-页头 | 查看购物车 | 进入购物车页面 | 头部购物车图标（链接 /cart） |
| 全局-页头 | 登录/注册账号 | 进入登录/注册流程（本轮按约束未进入登录后页面）；首页另有 "Register now for a £5 bonus" 新客注册入口 | "Sign in" 按钮、"Register now for a £5 bonus" 按钮 |
| 全局-侧边悬浮 | 使用快捷工具条 | 页面右侧固定悬浮条：下载 APP、消息通知、在线聊天、意见反馈 | Download、Notifications、Chats、Feedback 四个悬浮按钮 |
| 全局-信任组件 | 查看 Trustpilot 评分 | 首页内嵌 Trustpilot 评价组件，展示 4.5/5（20,320 条评价）并链接到 Trustpilot 页面 | Trustpilot 评分条（外链） |

## 二、首页模块

| 模块 | 功能名称 | 功能描述 | 关键操作 |
|---|---|---|---|
| 首页 | 浏览促销活动入口 | 多屏轮播的活动 banner 区：Welcome Offers、XGIMI 新品、MAXCOOK 厨房好物（£10 以下）、Bonfire night、Cosy up this winter、Hosting at yours、Oral-B iO（60% off）、Bring home the fun（30% off）等，点击进入活动页（/campaign/active/...）或店铺页（/store/...） | 8 个活动卡片、previous/next 轮播箭头、底部圆点分页 |

## 三、分类导航模块（Categories 弹出菜单）

点击页头 "Categories" 展开类目树，左侧为一级类目，悬停/点击后右侧展开二级子类目、品牌与活动入口。

一级类目共 15 个：For you、Electronics、World Food、Large Home Appliances、Computers & Tablets、Gaming、Small Home Appliances、Home & Living、Toys、Beauty & Personal Care、Beer, Wines & Spirits、Baby、Food Cupboard、Soft Drinks, Tea & Coffee、Household, Laundry & Cleaning。

| 模块 | 功能名称 | 功能描述 | 关键操作 |
|---|---|---|---|
| 分类导航 | 按一级类目浏览 | 选择一级类目，右侧展示该类目的二级分类、代表品牌与相关活动入口（以 Electronics 实测为例） | 左侧 15 个一级类目条目 |
| 分类导航 | 查看类目下二级分类 | Electronics 下展示：TVs、Phones、Headphones、Camera & Photo、Tablets、Robotics、Wearables 等，点击进入对应筛选后的列表页 | 二级类目条目、"View more" 按钮 |
| 分类导航 | 查看类目下品牌 | Electronics 下展示品牌快捷入口：Coocaa、Hisense、HONOR、TECLAST、Unihertz、Unitree、TeeView 等 | 品牌条目 |
| 分类导航 | 查看类目促销活动 | 类目级活动入口（如 Electronics "Buy 2 Save 5% Shop now"） | 活动入口卡片 |
| 分类导航 | 查看类目全部商品 | 进入该一级类目的完整商品列表页（/s?k=Electronics&l1=1409） | "View all Electronics" 入口 |

其他一级类目抽样到的二级内容（同结构）：World Food（Frozen World Food、Fish & Squid、Pasta Rice & Noodles、Noodles、Home-Style Dishes、World Spirits、Sweets、Frozen Beef、Ice Cream Tubs 等）、Gaming（Consoles、Controllers 等）、Beauty & Personal Care（Fragrance、Premium Fragrance、Woman's Fragrance）、Soft Drinks, Tea & Coffee（Fizzy Drinks、Energy Sports & Health Drinks）、Home & Living（Candles, Cases & Bakeware、Christmas）、Toys（Play Figures & Accessories）、Small/Large Home Appliances（Rice Cookers 等）。

## 四、频道导航模块（顶部频道页 /minihome/...）

顶部横向导航含 13 个频道，每个频道是一个独立落地页，结构统一：活动 banner + 店铺入口 + 二级类目快捷链接（点击进入 /s?k= 列表页）。

频道清单：Home Appliances、Electronics、Pets、Beauty、TV & Audio、Gaming、Food & Drinks、Home & Living、Everyday Essentials、Toys, Baby and Kids、Clothing, Footwear & Acc.、Health & Wellness、Automotive。

| 模块 | 功能名称 | 功能描述 | 关键操作 |
|---|---|---|---|
| 频道页（Electronics 实测） | 浏览频道促销位 | 频道头图/活动 banner（外链到 /campaign/active/...） | 频道 banner |
| 频道页（Electronics 实测） | 按二级类目逛频道 | 16 个二级类目快捷入口：Phones、Headphones、Tablets、Speakers、Wearables、Mouse/Keyboard & Accessories、Desktop PCs、Laptops、Gaming PC components、Camera & Photo、Home & Office Electronics、Electronics Accessories、Monitors、Soundbars & Home Cinema、Smart Home、Batteries | 二级类目链接 |
| 频道页（Food & Drinks 实测） | 逛超市频道 | 同结构；活动 banner 之外还带店铺入口（/store/100002206）；二级类目含 Chocolate & Sweets、Crisps Snacks & Nuts、Wine、Fizzy Drinks、Energy/Sports/Health Drinks、Water、Tea Coffee & Hot Drinks、Beer、Spirits、Cider、Tins & Cans、Table Sauces/Condiments & Dressings、Cereals、Cooking Ingredients、Biscuits、Rice Pasta & Pulses | 频道 banner、店铺入口、16 个二级类目链接 |

## 五、搜索/类目列表页模块（/s?k=...）

| 模块 | 功能名称 | 功能描述 | 关键操作 |
|---|---|---|---|
| 列表页 | 快捷场景筛选 | 一键切换 JoyExpress、Bestsellers、Welcome offer、Lightning offers、Outlet 五种场景商品集 | 5 个顶部筛选 Tab |
| 列表页 | 按价格区间筛选 | 输入最低/最高价，或拖动双滑块设定区间 | £Min./£Max. 数字输入框、Min/Max 两个 range 滑块 |
| 列表页 | 按评分筛选 | 只看评分 4 星及以上的商品 | "& Up" 评分筛选项 |
| 列表页 | 按类目细分 | 在当前结果内按子类目收敛（如 Home Appliances），并提供 Home 面包屑返回 | Category 筛选组、面包屑链接 |
| 列表页 | 商品排序 | 按相关性/价格从高到低/价格从低到高/销量/新品排序 | "Sort by" 下拉（Relevance、Price: High to low、Price: Low to high、Sales: High to low、New Arrivals） |
| 列表页 | 浏览商品卡并快捷加购 | 商品卡展示图片、标题、价格；支持收藏与直接加购，点击卡片进入详情页 | 商品卡链接（/dp/...）、Wishlist 心形按钮、Add to Cart 按钮 |

**类目子页面差异（补充实测）**：所有二级类目/品类发现图块点击后均落入同一列表页模板，但筛选面板随类目变化——Noodles（食品）多一个 "Repeat & Save" 快捷筛选且价格区间 £0–£50；Fragrance（美妆）价格区间 £0–£700、Category 显示跨类目收敛链接；Womens Clothing（服装）仅 3 个快捷筛选（无 Bestsellers/Welcome offer）。详见界面还原规格文档 4.1 节。

## 六、商品详情页模块（/dp/...）

| 模块 | 功能名称 | 功能描述 | 关键操作 |
|---|---|---|---|
| 详情页 | 定位商品层级 | 面包屑展示 Home > 一级 > 二级 > 三级 > 四级类目路径，每级可点击跳转对应列表页 | 面包屑链接（/s?b1=...） |
| 详情页 | 浏览商品图片 | 主图 + 缩略图画廊切换 | 主图区、多张缩略图 |
| 详情页 | 选择商品规格 | 选择颜色等变体（如 Black） | 规格选项（如 "Black"） |
| 详情页 | 调整购买数量 | 设置一次加入的数量 | Quantity 数字选择器（含 +/- 步进） |
| 详情页 | 加入购物车 / 立即购买 | 把商品加入购物车，或跳过购物车直接进入下单流程（下单需登录，本轮未执行） | "Add to cart" 按钮、"Buy now" 按钮 |
| 详情页 | 查看卖家店铺 | 查看第三方卖家（如 xiablaqa）及其店铺页 | 卖家名称链接、"View store" 链接（/store/...） |
| 详情页 | 分享商品 | 通过 WhatsApp、Facebook、邮件、X 分享商品链接 | 4 个分享图标（外链） |
| 详情页 | 查看商品信息标签页 | 切换查看 Product Description（商品描述）、Important Information（重要信息）、Specifications（规格参数） | 3 个 Tab（role=tab） |

## 七、购物车模块（/cart）

| 模块 | 功能名称 | 功能描述 | 关键操作 |
|---|---|---|---|
| 购物车 | 查看购物车 | 查看已加入的商品与结算入口（本轮为空车状态，仅展示空态与配套组件） | /cart 页面 |
| 购物车 | 切换配送方式 | 在快递配送（Delivery）与自提（Pickup）之间切换 | "Delivery"、"Pickup" 两个切换 Tab |
| 购物车 | 查看站点设置 | 页内展示当前语言（English - EN）、货币（£-GBP-British Pound）、国家（United Kingdom） | 3 个只读展示项 |
| 购物车 | 查看服务承诺 | 展示当日/次日达、精选品牌、24/7 客服三条服务说明 | 3 个承诺卡片 |

## 八、账户与未覆盖范围

| 模块 | 功能名称 | 功能描述 | 关键操作 |
|---|---|---|---|
| 账户 | 登录/注册 | "Sign in" 按钮进入登录流程；新客注册赠 £5。按任务约束（不登录、不提交数据）未进入，登录后功能（订单、地址、JoyPlus 会员等）不在本次范围 | Sign in 按钮 |
| 会员 | JoyPlus 试用 | 顶栏促销提及 "Free 30-day JoyPlus trial"，属于登录后会员体系，未展开 | 促销文案入口 |

## 无法访问的页面

- **登录后的页面**（账户中心、订单、Wishlist 列表页、Notifications/Chats 内容页、JoyPlus 会员页、结算流程）：按任务约束"不登录、不提交数据"主动跳过，非站点故障。
- **页脚链接区**（帮助中心、隐私政策等）：站点为自绘滚动/懒加载，自动化滚轮无法滚动到页脚，DOM 快照始终只返回视口内容，故页脚信息未采集到。
- **"Deliver to" 邮编修改弹窗**：属于修改站点设置的交互，按任务约束未操作。
- **说明**：整个过程站点页面均可正常打开，无报错页；此前用无头方式抓取首页 HTML 时命中过 Joybuy 风控拦截页（"Joybuy Risk Control"），正常浏览器访问不受影响。
