# 爬虫任务品类与配额页面改造方案

版本：`v0.1-draft`  
现场分析日期：`2026-11-03`  
状态：类目分析暂停，先讨论多语言内容方案；尚未开始业务代码改造

> 2026-11-03 用户要求先把 Joybuy 来源页面切换为简体中文，再继续分析类目。
> 本文第 2 节的英文页面证据保留作历史参考，但不得直接生成最终类目 seed；后续以中文页面重新分析的结果为准。
> 多语言内容设计见 [多语言商品内容与国家市场设计](./10-multilingual-content-and-market-design.md)。

## 1. 本次目标

把现有“输入来源类目公开标识后创建单类目任务”的表单，改造成运营人员可以直接使用的品类配额页面：

- 创建任务时从 Joybuy 当前公开类目树选择来源范围；
- 页面按 10 个业务分组展示占比、目标商品数和已选类目；
- 一、二、三级节点使用树形复选框选择，不再要求运营手填标识；
- 明确“商品数量上限”的统计口径；
- 活动商品使用活动页来源，不伪装成 Joybuy 商品类目；
- 页面保持简单，默认只展示日常所需字段，高级抓取参数折叠收起；
- 管理端可见文案全部为中文，仅 `Joybuy` 品牌标识保留英文。

## 2. Joybuy 公开页面现场分析

### 2.1 分析方法与边界

本次只读取 `https://www.joybuy.co.uk/` 的公开页面元素、公开链接和页面已经暴露的类目标识，没有登录、提交表单、绕过验证码或规避风控。

Joybuy 首页 `Categories` 菜单当前公开 22 个一级入口：

1. For you
2. Electronics
3. World Food
4. Large Home Appliances
5. Computers & Tablets
6. Gaming
7. Small Home Appliances
8. Home & Living
9. Toys
10. Beauty & Personal Care
11. Beer, Wines & Spirits
12. Baby
13. Food Cupboard
14. Soft Drinks, Tea & Coffee
15. Household, Laundry & Cleaning
16. Pets
17. Clothes, Shoes & Watches
18. Outdoor, Sports & DIY
19. Automotive
20. Health & Wellness
21. Frozen Food
22. Stationery & Office Supplies

页面元素公开了稳定来源标识，例如：

- `Electronics`：一级标识 `1409`；
- `Clothes, Shoes & Watches`：一级标识 `1876`；
- `Watches`：二级标识 `1881`；
- `Coffee Machines`：二级标识 `1407`；
- `Camera & Photo`：二级标识 `1416`；
- `Outdoor, Sports & DIY`：一级标识 `1582`。

进入二级类目页后，页面还公开了带层级前缀的筛选节点，例如：

- `Watches` 下：男士 `cid2:13159`、女士 `cid2:13102`、中性 `cid2:13202`；
- `Wearables` 下：智能手表 `cid3:5259`、智能眼镜 `cid3:6143`、智能手环 `cid3:6147`、智能戒指 `cid3:6145`；
- `Camera & Photo` 下：相机摄影 `cid2:1858`、无人机系统 `cid2:10870`；
- `Phones` 下：智能手机 `cid4:5204`；
- `Coffee Machines` 下：意式 `cid4:8499`、全自动 `cid4:8497`、泵压式 `cid4:8498`、胶囊式 `cid4:8501`、滴滤式 `cid4:8500`；
- `Footwear` 下：男士 `cid2:13159`、中性 `cid2:13202`、女士 `cid2:13102`、女童 `cid2:13221`、男童 `cid2:13252`；
- `Sports & Leisure` 下：健身器材 `cid3:2886`、瑜伽 `cid3:13564`、滑板车 `cid3:8369`、护具 `cid3:13449`、球拍运动器材 `cid3:2891`。

注意：二级类目页展示的下一层有时是性别或跨目录筛选维度，并不总是传统意义上的“子类目”。系统必须原样保存 Joybuy 的层级前缀与 ID，不能只保存中文名称，也不能假设所有三级节点都属于同一种层级。

### 2.2 活动入口不是商品类目

首页当前公开的活动入口包括：

- `Lightning Offers`：`https://www.joybuy.com/marketing/lightning-offers?renderStyle=bottom_flow`
- `Outlet`：`https://www.joybuy.com/marketing/outlets?renderStyle=bottom_flow`
- `Mix & Match`：`https://www.joybuy.com/marketing/mix_and_match?renderStyle=bottom_flow`
- `New Arrivals`：`https://www.joybuy.co.uk/campaign/active/2mCXshxnv48vjq5mdheSfBVfAR92`

因此“活动商品 5%”应建模为业务分组下的活动页来源，导入商品后仍按商品自身的 Joybuy 类目归档；不能创建一个假的 Joybuy“活动商品”类目。

## 3. 两层概念必须分开

### 3.1 业务分组

业务分组用于配额、统计和运营表达。本次固定为 10 组，总占比必须为 100%。

### 3.2 Joybuy 来源节点

来源节点是一一对应 Joybuy 公开页面的类目或筛选节点，用来生成抓取范围。一个业务分组可以选择多个来源节点，一个来源节点也必须保留其来源树版本和公开标识。

“高奢高价”“电器”“活动商品”都不是 Joybuy 当前公开菜单中的单一原生类目，所以不能把业务分组名称直接当作来源类目名称。

## 4. 建议的业务分组与 Joybuy 映射

| 业务分组 | 占比 | 建议的 Joybuy 来源范围 | 说明 |
| --- | ---: | --- | --- |
| 奢侈品与贵重商品 | 10% | `Clothes, Shoes & Watches(1876)` → `Jewellery(1889)`、`Watches(1881)` | Joybuy 没有“奢侈品”原生类目；贵重与机械属性需要价格/关键词或商品属性过滤。 |
| 科技数码 | 10% | `Electronics(1409)` → `Phones(1420)`、`Wearables(1410)`、`Camera & Photo(1416)` → 智能手机、智能手表、相机摄影、无人机系统 | 与用户给出的手机、智能手表、无人机、相机范围一致。 |
| 电器与家装 | 10% | `Small Home Appliances(1396)` → `Coffee Machines(1407)`；`Home & Living(1563)` → `Home Decor(1566)`；`Outdoor, Sports & DIY(1582)` → `DIY(1584)` | “咖啡机”和“家装用品”来自不同 Joybuy 一级目录，业务分组允许跨树选择。 |
| 女装 | 15% | `Clothes, Shoes & Watches(1876)` → `Women's Clothing & Accessories(1877)` → `Clothing(cid3:13105)` | 不把女装配饰重复计入箱包或贵重商品。 |
| 箱包 | 10% | `Clothes, Shoes & Watches(1876)` → `Bags & Luggage(1885)` → 中性、女士、男士 | 默认全性别。 |
| 男装 | 10% | `Clothes, Shoes & Watches(1876)` → `Men's Clothing & Accessories(1879)` → `Clothing(cid3:13162)` | 不把男装配饰重复计入箱包或贵重商品。 |
| 美妆与美容器械 | 10% | `Beauty & Personal Care(2709)` 下的 `Premium Beauty(5316)`、`Face Care(2747)`、`Hair(2729)`、`Shaving & Hair removal(2731)`；必要时补充 `Small Home Appliances` 下的 `Female Hair Removal(2557)` | 页面公开了 `Personal Care Devices(cid1:159)` 筛选，可覆盖美容器械。 |
| 鞋靴 | 10% | `Clothes, Shoes & Watches(1876)` → `Footwear(1883)` → 男士、中性、女士、女童、男童 | 按“不分性别”默认全选。 |
| 户外用品 | 10% | `Outdoor, Sports & DIY(1582)` → `Outdoors(1585)`、`Sports & Leisure(1587)`、`Sports apparel, Shoes & Accessories(5332)` | 户外照明、健身、瑜伽、护具等可按三级节点细选。 |
| 活动商品 | 5% | Lightning Offers、Outlet、Mix & Match、New Arrivals 活动页 | 来源类型为活动页，不进入商品类目树。 |

## 5. 三个表单字段的最终语义

### 5.1 子类目范围

废弃当前“按层级自动判断 / 包含子类目 / 仅当前类目”的下拉框，改为：

- 展示 Joybuy 一、二、三级树；
- 节点使用三态复选框：未选、部分选择、全部选择；
- 勾选父节点时默认选中当前类目树版本中已知的全部后代；
- 保存任务时冻结类目树版本，后续 Joybuy 新增子节点不会悄悄进入旧任务；
- 新版本出现变化时展示差异，由运营确认是否纳入；
- 已选节点以中文名称展示，原英文名称和公开标识放在详情或悬浮提示中。

### 5.2 商品数量上限

页面改名为“本任务最多成功入库商品数”，定义为：

- 统计去重后的 Joybuy 来源商品 ID；
- 只有通过质量闸门并成功写入 staging/业务表的商品才计数；
- 不等于请求数、页面数、发现链接数或下载尝试数；
- 同一商品命中多个分组只计一次，按页面中的分组优先顺序归属；
- 某组因重复或质量失败不足时，只从该组来源范围继续补齐，不挪用其他组配额；
- 总入库数不超过任务总上限。

各组目标数由“总上限 × 占比”计算。总数不能整除时使用最大余数法分配，保证各组整数目标之和严格等于总上限。例如总上限为 1000 时，各组目标依次为 `100/100/100/150/100/100/100/100/100/50`。

### 5.3 来源类目公开标识

这是系统内部用于稳定识别 Joybuy 节点的来源 ID，不是运营应该手填的 UUID。建议统一显示格式：

- 一级：`joybuy:l1:1876`
- 二级：`joybuy:l2:1881`
- 页面筛选节点：`joybuy:cid2:13159`
- 活动页：`joybuy:campaign:lightning-offers`

创建页隐藏该字段；仅在“来源详情”中只读展示，便于排错和审计。

## 6. 页面功能规划

采用单页配置，不做多步向导，减少来回切换。

### 6.1 页面顶部

- 任务名称；
- 本任务最多成功入库商品数；
- 同步模式（增量同步 / 完整刷新）；
- 三张摘要卡：已分配占比、预计商品数、已选来源节点数。

### 6.2 中部配额表

固定展示 10 行业务分组，每行包含：

- 分组名称；
- 占比（默认使用用户给出的比例，可编辑）；
- 自动计算的目标商品数；
- 已选 Joybuy 类目摘要；
- “选择类目”按钮；
- 校验状态。

占比合计不是 100% 时禁用创建按钮，并直接显示差额。

### 6.3 类目选择侧栏

- 顶部搜索框，可按中文名、Joybuy 英文名或公开标识搜索；
- 左侧树展示一级、二级、三级节点；
- 父节点可展开和三态勾选；
- 右侧或底部展示“已选择”标签，支持单项移除和清空；
- 活动商品行打开独立的“活动来源”列表，不混入类目树；
- 默认不展示原始 ID，点击“来源详情”才展开。

### 6.4 高级设置

默认折叠，包含排序方式、评价目标数、媒体下载、速率、并发、账号组和失败策略。首次使用页面不应被这些字段淹没。

## 7. 后端与数据模型改造建议

现有 `CrawlJob` 只有一个 `source_category` 和一个 `product_limit`，无法表达 10 个配额分组和多选树。建议保留旧字段用于兼容历史任务，新增：

- `CrawlJobAllocation`
  - `job`
  - `business_group`（固定 10 组枚举）
  - `quota_percent`
  - `target_product_count`
  - `sort_order`
- `CrawlJobSourceSelection`
  - `allocation`
  - `source_kind`：`CATEGORY` / `CAMPAIGN`
  - `source_category`（类目来源时使用现有 `SourceCategory`）
  - `source_tree_version`
  - `selection_mode`：`EXACT` / `INCLUDE_DESCENDANTS`
  - `facet_level` 与 `facet_source_id`（Joybuy 页面筛选节点）
  - `campaign_key` 与 `source_url`（活动页来源时使用）
  - 可选的价格、关键词或属性过滤配置

新增管理 API：

- `GET /api/v1/admin/crawlers/source-tree?version=current`：返回中文名、原名、层级、公开标识和子节点；
- `GET /api/v1/admin/crawlers/source-campaigns`：返回允许使用的活动入口；
- `POST /api/v1/admin/crawlers/jobs`：接收总上限、10 个配额和每组来源选择；
- 服务端重新计算各组目标数并校验占比，不能信任前端计算结果。

类目数据继续复用 `SourceCatalog`、`SourceCategory`、`SourceCategoryTreeVersion` 和 `SourceCategorySnapshot`。增加 Joybuy 类目快照同步/导入命令，先把本次现场证据保存为 fixture；后续同步必须版本化并经过差异确认。

## 8. 去重与配额规则

1. 先按分组优先顺序建立来源队列；
2. 分组内部按用户选择的排序方式抓取；
3. 以 Joybuy 稳定商品 ID 做全任务去重；
4. 首次成功命中的分组获得归属，其他分组跳过该商品；
5. 被跳过、解析失败或质量闸门拒绝的商品不占配额；
6. 当前分组继续向后补抓，直到达到该组目标或来源耗尽；
7. 来源耗尽时明确显示“目标 / 实际 / 缺口”，不伪造补足。

## 9. 验收标准

- 创建页不再出现可编辑的“来源类目公开标识”；
- 类目树能展示并勾选一、二、三级节点，父子三态正确；
- 10 个业务分组默认占比之和为 100%，改错后不能提交；
- 输入总上限后各组整数目标自动计算且总和完全一致；
- 活动商品使用活动来源列表，不出现在类目树中；
- 后端拒绝未知、失效、跨版本不一致的来源节点；
- 同一商品跨类目、跨活动命中时只成功入库一次；
- 任务详情能追溯类目树版本、来源公开标识、分组目标和实际完成数；
- Vue 组件测试、后端 API/领域测试和管理员 E2E 覆盖创建与校验流程；
- 页面可见文案全部为中文，仅 `Joybuy` 品牌标识保留英文。

## 10. 尚需用户确认的产品决策

以下问题不能由类目树本身推导，需要业务口径：

1. “高价”最低价格。建议默认 `£300`，且只对奢侈品与贵重商品分组生效；用户也可以改为其他阈值。
2. “机械手表”的识别方式。建议先使用 `Watches` 类目加“mechanical / automatic”关键词与商品属性，命中后人工抽样校验；Joybuy 当前没有独立的“机械手表”公开类目节点。
3. 任务总商品数的常用默认值。页面必须由运营填写总上限；是否预填 `1000` 需用户确认。
4. 活动商品的默认来源。建议首期默认全选当前四个公开活动入口，并在每次执行前检查入口是否仍有效。

在上述决策确认前，只实施类目树、配额模型和页面骨架会造成二次返工，因此本方案先完成需求闭合，再开始业务代码。
