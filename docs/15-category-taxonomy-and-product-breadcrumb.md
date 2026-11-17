# 15 类目体系与商品面包屑（2026-11-09 初版；2026-11-11 一对一修订）

> 本文记录 Joybuy 三套类目的关系、11 个一级类目的二级类目来源、商品类目表
> （最多两级）和购物端面包屑契约。
> **2026-11-11**：二级类目口径从「合并补全（多对一桶）」修订为「与 Joybuy
> 一对一」（§2），多对一桶口径作废。

## 1. 三套类目

| 体系 | 例子 | ID 形态 | 用途 |
|---|---|---|---|
| **LocalCategory（我们）** | 家居生活 → 厨房与餐厅用品/家具/整理收纳… | slug + `path=/pk/pk/` | 购物端导航、商品池筛选 |
| **Joybuy 频道菜单树** | 家居生活 → 厨房与餐厅用品/家具/…；14 频道 163 二级 | `minihome:*`、`l2:*`、`l3:*` | 爬虫任务选类目、抓取范围 |
| **Joybuy 商品后台类目树** | 厨具餐具(288) → 锅具(361) → 炒锅(372) | 数字 ID | 商品自身归属类目、面包屑 |

要点：

- 商品面包屑里的「商品名称」不是类目，是前端把商品标题拼在路径末尾。
- 商品类目 ID 与频道菜单 ID 是两套空间：`SourceCategory` 里查不到 288/361/372。
- 我们的本地类目只有两级；Joybuy 商品类目可能 3~4 级，导入时**只保留前两级**。

## 2. 11 个一级类目的二级类目（2026-11-11 一对一对齐）

> **2026-11-11 修订（当前口径）**：购物端二级品类与 Joybuy 完全一对一——
> 11 个一级下的二级集合与 Joybuy 菜单一模一样，**2026-11-09 的多对一合并桶
> 口径（食品杂货/手机与平板/笔记本与台式机/电脑配件/音响&家庭影院/宠物食品/
> 宠物玩具/玩具早教等 `PRESERVE_BUCKET_SLUGS`）已整体推翻**。

数据源：最新 PUBLISHED 的 `joybuy_uk` 类目树（`joybuy-uk-20261104-4dcfbbe5`）。
口径：

- **一对一**：每个 Joybuy 二级 → 恰好一个本地二级；156 个菜单节点
  （163 − 6 汽车 − 1 活动）对应 156 个本地二级，无任何多对一桶；
- **名称**：一对一子类目名称用 Joybuy 原名（zh 用中文菜单翻译、en 用英文
  原文）；跨频道 union 后同一父类目下的重名二级按 `NAME_OVERRIDES` 消歧：
  - 游戏 `l3:1437` 显示器 → 「游戏显示器 / Gaming Monitors」（`gaming-monitors`，
    电子产品 `l2:1436` 保留「显示器 / Monitors」`monitors`）；
  - 电视与影音 `l3:1500` 电子配件 → 「影音电子配件 / Electronic Accessories
    (TV & Audio)」（`tv-audio-accessories`；`l2:1499` 保留「电子配件 /
    Electronics Accessories」`electronics-accessories`）；
  - 电视与影音 `l3:1430` 游戏机 → 「影音游戏机 / Consoles (TV & Audio)」
    （`consoles-tv-audio`；游戏 `l2:1429` 保留「游戏机 / Consoles」`consoles`）；
- **拆桶**：原多对一桶全部拆开并退役旧 slug——
  `groceries-food`→24 个食品子类目（如 `rice-pasta-pulses`/`wine`/`chinese`…）、
  `phones-tablets`→`mobile-phones`/`tablets`、`laptops-desktops`→`laptops`/
  `desktop-pcs`、`pc-components`→`gaming-pc-components`/`gaming-memory-storage`、
  `tv-audio`→`soundbars-home-cinema`/`tv-audio-accessories`、`pet-food`→
  `dog-food`/`cat-food`/`cat-treats`、`pet-toys`→`cat-toys`、
  `toys-early-learning`→`infant-pre-school-toys(-activities)`；
- **基座二级退役**：6 个不在 Joybuy 菜单里的历史基座二级（`networking`/
  `cycling`/`water-sports`/`personal-care-appliances`/`gaming-accessories`/
  `board-card-games`）一并移除；
- **按二级拆分（保留不变）**：电子产品里的计算机硬件 → 计算机与配件；
  个护家清里个人护理 → 美妆个人护理、清洁/纸品 → 家居生活；家居生活里的
  运动/户外 → 户外运动；电视与影音里的游戏机 → 游戏及配件；大家电仍归小家电；
- **不映射**：汽车及零配件（6 个节点）。

映射数据在 `backend/catalog/joybuy_menu_crosswalk.py`：

- `CHANNEL_PARENT`：14 频道 → 11 一级（汽车为 `None`）；
- `NODE_PARENT`：跨类目拆分（保留不变）；
- `MERGE_INTO_EXISTING`：历史基座 slug 改名复用（一对一，每个 slug 只收一个节点）；
- `NODE_SLUG`：一对一固定 slug；
- `NAME_OVERRIDES`：同父类目重名二级的消歧名；
- `RETIRED_LOCAL_SLUGS`：拆桶后的旧 slug + 退役基座二级（同步命令在
  无商品/无子类目/无商品类目/无搜索文档引用时删除，否则保留并警告）。

同步命令：

```bash
./.venv/Scripts/python.exe backend/manage.py sync_local_categories_from_joybuy --dry-run \
  --report var/split_categories_20261111/sync_report.json
./.venv/Scripts/python.exe backend/manage.py sync_local_categories_from_joybuy
```

2026-11-11 执行结果（`var/split_categories_20261111/`，一次性迁移
`split_categories.py` 先 DRY_RUN 再正式）：

- 新建 40 个一对一二级，二级映射 156 条，频道映射 13 条，错误 0；
- 拆开 8 个多对一桶、退役 14 个本地二级（8 桶 + 6 基座）；
- 76 个挂桶 SPU 重映射（62 食品 → 10 个食品子类目；14 手机 → `mobile-phones`），
  0 个人工待办；重映射 SPU 逐个 `refresh_spu_search_documents`；
- 本地类目 141 → **167**（11 一级 + 156 二级）；各一级下二级数：
  家居生活 47、电子产品 13、美妆个人护理 16、小家电 17、健康与保健 9、
  计算机与配件 9、服装与配饰 6、户外运动 2、宠物用品 8、婴幼儿用品 24、游戏及配件 5。

注意：

- 一对一改名/新建不迁移 URL：退役 slug 的 `/c/<旧 slug>` 链接会 404
  （购物端导航数据驱动，立即显示新集合）；
- `seed_standard_categories` 的基座子类目已与一对一集合对齐（38 个），
  且不再覆盖既有二级的 `sort_order`（排序归 Joybuy 同步管）；
- 7 个 Joybuy 节点没有中文名（`l2:3505`、`l2:1384`、`l2:1376`、`l2:1380`、
  `l2:1378`、`l2:1474`、`l2:1478`），当前用英文名兜底；
- 历史 2026-11-09 执行记录（多对一口径：新建 89、二级映射 157、类目 141）
  见 git 历史与本文件旧版，不再适用。

### 2.1 活动商品：节庆装饰品

「活动商品」不是类目，是 `Spu.is_activity` 标记（见 `catalog.models.Spu` 注释）。

- Joybuy 菜单 `l2:1580 节庆装饰品` 不再映射/创建本地二级；`seasonal-decor`
  由 `sync_local_categories_from_joybuy` 在**没有商品/子类目/商品类目引用**时删除；
- 抓取任务选中 `l2:1580` 时，spider 会把 `crawl_source_category_id` /
  `crawl_source_category_name` 写进 payload；
- 导入判定活动商品（满足任一即可）：
  1. `crawl_source_category_id == "l2:1580"` 或名称 `节庆装饰品`；
  2. 商品类目路径包含 `节日与活动(4945)`（兜底，父频道抓取时也能识别）；
- 命中后 `Spu.is_activity=True` 且 `local_category=None`；商品类目表仍保存两级
  （如 `节日派对(4909)/节日与活动(4945)`），面包屑照常显示；
- 「派对装饰品 `l2:4663` / 派对用品(4910)」**不**标活动商品；
- `is_activity` 只加不清：导入只会把标记设为 True，取消由管理端【活动商品管理】操作。

## 3. 商品类目表（ProductCategory，最多两级）

模型：`backend/catalog/models.py::ProductCategory`

| 字段 | 说明 |
|---|---|
| `catalog` | `SourceCatalog` FK（当前 `joybuy`） |
| `source_id` | Joybuy 商品类目数字 ID，如 `288`、`361` |
| `parent` | 自关联；只允许 0/1 两级 |
| `name` | 类目名（先存中文；缺中文时用英文） |
| `depth` | 0 或 1；DB `CheckConstraint(depth <= 1)` |
| `path` | `/288/`、`/288/361/` |
| `local_category` | 可空 FK 到 LocalCategory；本轮不自动填 |

`Spu.product_category` 关联最深一级（如 `锅具`）。历史 SPU 为空，面包屑回退本地类目。

## 4. 爬虫解析与 payload

`crawler/joybuy_crawler/parsers/joybuy_uk.py`：

- `_extract_flight_product_categories()` 读
  `productBreadCrumbFloor.data["C-M#viewBreadCrumbItem&core"].categories`；
- `PRODUCT_CATEGORY_DEPTH = 2`，只取前两级；第三级及更深丢弃；
- DOM 面包屑仅作兜底，仍截断到两级；
- payload 新增：

```json
{
  "product_category_path": [
    {"id": "288", "name": "厨具餐具", "depth": 0},
    {"id": "361", "name": "锅具", "depth": 1}
  ],
  "product_category_id": "361",
  "joybuy": {
    "breadcrumbs": [{"name": "厨具餐具", "cid": ""}, {"name": "锅具", "cid": ""}],
    "productCategoryPath": [ ...同上... ]
  }
}
```

- `source_category_id` 保持菜单类目语义（不复用商品类目 ID）。

## 5. 导入

`backend/crawler_control/import_services.py::_sync_product_categories()`：

- 读 `product_category_path`，强制 `[:2]`；
- 按 `(catalog, source_id)` upsert，写 parent/name/depth/path；
- 返回最深节点，传给 `get_or_create_spu_from_source(product_category=...)`；
- 已存在的 SPU 也会刷新 `product_category`；`local_category` 只在为空且
  `ProductCategory.local_category` 有值时补，不覆盖人工维护值；
- 重复导入幂等，第三级永不落库。

## 6. 商品详情 API 与面包屑

`backend/catalog/detail_views.py::product_detail` 新增：

```json
"category_breadcrumb": [
  {"id": "288", "name": "厨具餐具", "depth": 0},
  {"id": "361", "name": "锅具", "depth": 1}
]
```

`storefront/pages/p/[id].vue`：

- 有 `category_breadcrumb` 时显示 `Home / 厨具餐具 / 锅具 / 商品名称`；
- 商品类目暂渲染为不可点击文本（没有本地 slug）；
- 历史商品没有商品类目时回退到原「Home / 本地一级 / 本地二级 / 商品名称」。

## 7. 验证记录（2026-11-09）

- `manage.py test catalog.tests.test_standard_categories catalog.tests.test_joybuy_menu_crosswalk catalog.tests.test_product_detail_api catalog.tests.test_catalog_domain crawler_control.tests.test_crawler_product_category crawler_control.tests.test_crawler_review_aggregates crawler_control.tests.test_crawler_import` → **50 passed**。
- 同步命令 dry-run/正式执行 → 新建 89、更新 67、二级映射 157、频道映射 13、活动商品节点 1、未映射 6、错误 0；再次执行后 `seasonal-decor` 已删除，本地类目 141（家居生活 24）。
- 活动商品测试：任务来源 `l2:1580` → `is_activity=True`、`local_category=None`；商品类目 `节日与活动(4945)` 兜底同样命中；`派对用品(4910)` 不命中。
- 真实商品 `10003152`（Ochama 炒锅）解析：
  `product_category_path = [厨具餐具(288), 锅具(361)]`，`product_category_id=361`，没有 `炒锅(372)`。
- storefront prettier/eslint 通过；`nuxt build storefront` 通过。

## 8. 边界

- 商品类目名先存中文；EN 界面临时显示中文，后续补翻译。
- `ProductCategory.local_category` 只建可空外键，本轮不自动填。
- 历史 SPU 不回填商品类目（可从原始响应归档后续补）。
- 汽车类不进入 11 个一级；报告会列出未映射节点。
