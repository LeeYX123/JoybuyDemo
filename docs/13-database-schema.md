# 数据库表结构与字段说明

基线日期：`2026-11-05`（以本地开发库实际结构为准，共 98 张表；第一轮新增商家经营域 11 张，第二轮新增 6 张）

- 数据库：MySQL 8.4，库名 `joybuy`（容器 `joybuy-dev-mysql-1`，主机端口 `33060`）。
- 全部表由 Django models + migrations 生成（`backend/*/models.py`），本文与代码同步维护。
- 连接凭据见本地 compose 配置（仅开发环境使用）。
- 结构如有演进，以 `backend/*/models.py` + migrations 为准；本文基线为 2026-11-05 快照。

## 通用约定

- 每张业务表都有 `id`：`bigint unsigned` 自增主键（Django 内部主键，不对外暴露）。
- 带 `public_id` 的表：`char(32)`，无横线 UUID，是该实体的**对外标识**（API、URL 中使用，如 `/p/<public_id>`）。
- 外键在数据库中存储为 `<字段名>_id` 列（如 `spu_id`、`market_id`）；本文按模型字段名描述。
- `created_at` / `updated_at`：`datetime(6)`，Django 自动维护（创建时间 / 最后更新时间），下文不再重复说明。
- 枚举一律存字符串字面量（如 `ACTIVE`、`PENDING`），展示层负责翻译。
- 金额统一 `decimal(18,4)`；数据库 CHECK 约束保证金额非负、划线价 ≥ 现价（相关表单独注明）。

## 表清单（按业务域）

| 业务域 | 表 |
| --- | --- |
| 商品目录与来源 | `source_catalog`、`source_category`、`source_category_tree_version`、`source_category_snapshot`、`local_category`、`category_mapping`、`brand`、`attribute_definition`、`attribute_option`、`category_attribute_definition`、`spu`、`spu_translation`、`spu_source_identity`、`sku`、`sku_source_identity`、`product_search_document` |
| 来源值与本地覆盖 | `source_field_value`、`local_field_override`、`local_field_override_version` |
| 币种、市场与价格库存 | `currency`、`market`、`offer`、`offer_source_identity`、`price_snapshot`、`inventory_ledger` |
| 媒体 | `media_asset`、`media_variant`、`media_usage` |
| CMS 内容 | `cms_page`、`cms_module`、`home_banner` |
| 爬虫控制 | `crawler_account`、`crawl_job`、`crawl_job_source_selection`、`crawl_run`、`crawl_run_event`、`raw_response`、`staging_product`、`quality_gate_report`、`crawler_circuit_breaker` |
| 买家 | `buyer_account`、`buyer_session`、`buyer_verification_code`、`buyer_address`、`buyer_favourite`、`buyer_recently_viewed`、`buyer_wallet_entry` |
| 购物车与结算 | `cart`、`cart_item` |
| 订单与库存占用 | `order`、`order_item`、`merchant_order`、`inventory_reservation` |
| 评价 | `virtual_reviewer`、`review`、`review_version`、`review_media` |
| 商家与经营 | `merchant`、`merchant_permission`、`merchant_role`、`merchant_role_permissions`、`merchant_membership`、`merchant_source_mapping`、`merchant_wallet_entry`、`merchant_withdrawal`、`merchant_deposit_entry`、`merchant_activity`、`merchant_activity_participation`、`merchant_referral`、`referral_program`、`referral_commission`、`after_sale`、`after_sale_event`、`support_conversation`、`support_message` |
| 员工与权限 | `staff_account`、`platform_permission`、`platform_role`、`platform_role_permissions`、`staff_role_assignment`、`staff_totp_device`、`staff_session` |
| 通知 | `notification_template`、`notification_message`、`merchant_notification`、`merchant_notification_reply` |
| 审计 | `audit_log` |
| Django 内置 | `auth_group`、`auth_group_permissions`、`auth_permission`、`auth_user`、`auth_user_groups`、`auth_user_user_permissions`、`django_admin_log`、`django_content_type`、`django_migrations`、`django_session` |

---

## 1. 商品目录与来源

### source_catalog — 来源商城目录

爬取目标站点的顶层注册表，每个来源系统一行（当前仅 `joybuy`）。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| source_system | varchar(50) 唯一 | 来源系统标识（`joybuy`），staging/导入都以它做命名空间 |
| display_name | varchar(120) | 管理端展示名（"Joybuy"） |
| current_version_id | bigint 可空 | 当前生效的类目树版本（FK `source_category_tree_version`，可空） |

### source_category — 来源类目

来源站点公开类目节点的稳定标识（ID 来自 Joybuy 页面，如 `926`、`l3-phones`）。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| catalog_id | bigint | 所属来源目录（FK `source_catalog`） |
| source_id | varchar(160) | 来源类目公开标识；与 catalog 组成唯一约束 |
| is_active | tinyint(1) | 是否仍活跃（增量同步时标记失效） |
| first_seen_at / last_seen_at | datetime(6) | 首次/最近一次在来源页观察到的时间 |

### source_category_tree_version — 来源类目树版本

一次抓取冻结的整棵类目树版本；任务创建时绑定版本，后续树变化不影响已建任务。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| public_id | char(32) 唯一 | 对外标识 |
| catalog_id | bigint | 所属来源目录 |
| version_key | varchar(100) | 版本键；与 catalog 组成唯一约束 |
| structure_hash | varchar(64) | 树结构哈希，用于识别结构变化 |
| status | varchar(16) | `DRAFT` / `PUBLISHED` / `FAILED` |
| captured_at | datetime(6) | 抓取时间 |
| published_at | datetime(6) 可空 | 发布时间 |
| metadata | json | 抓取附注（页数、来源 URL 等） |

### source_category_snapshot — 来源类目树节点快照

版本内的每个类目节点（含层级/排序/路径），组成可回放的整棵树。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| tree_version_id | bigint | 所属树版本；与 category 组成唯一约束 |
| category_id | bigint | 指向 `source_category` |
| parent_id | bigint 可空 | 父节点（同表自关联） |
| name | varchar(200) | 节点名称（来源页原文） |
| source_url | varchar(1000) | 来源页链接 |
| sort_order | int unsigned | 同层排序 |
| depth | smallint unsigned | 层级深度（0 起） |
| path | varchar(700) 索引 | 物化路径，按路径排序即可还原整棵树 |

### local_category — 本地类目

商城自己的类目树（商城端 `/c/<slug>` 用的就是它），与来源类目通过映射关联。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| public_id | char(32) 唯一 | 对外标识 |
| parent_id | bigint 可空 | 父类目（自关联，PROTECT） |
| name | varchar(160) | 默认名称（回退值） |
| name_en / name_zh | varchar(160) | 英文/中文名（docs/12 双语约定；缺省回退 `name`） |
| slug | varchar(120) 唯一 | URL slug（`/c/electronics`） |
| status | varchar(16) | `ACTIVE` / `HIDDEN` |
| sort_order | int unsigned | 排序 |
| depth | smallint unsigned | 层级深度 |
| path | varchar(700) 索引 | 物化路径（子孙查询用） |

### category_mapping — 来源类目 ↔ 本地类目映射

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| local_category_id | bigint | 本地类目 |
| source_category_id | bigint | 来源类目；两者组成唯一约束 |
| is_primary | tinyint(1) | 是否主映射（爬虫导入时按主映射落 `spu.local_category`） |
| confidence | decimal(5,4) 可空 | 映射置信度（自动映射时使用） |

### brand — 品牌

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| public_id | char(32) 唯一 | 对外标识 |
| name | varchar(160) | 展示名 |
| normalized_name | varchar(160) 唯一 | 规范化名（去多余空格 + casefold），用于品牌去重合并 |
| slug | varchar(120) 唯一 | URL slug |
| website_url | varchar(1000) | 品牌官网（可空串） |
| status | varchar(16) | `ACTIVE` / `INACTIVE` |

### attribute_definition — 属性定义

类目属性的注册表（如颜色、容量），爬虫导入的 SKU 规格走免注册的规范化签名路径，不强制在此登记。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| code | varchar(100) 唯一 | 属性代码（slug） |
| name | varchar(160) | 展示名 |
| data_type | varchar(24) | `TEXT` / `INTEGER` / `DECIMAL` / `BOOLEAN` / `CHOICE` / `MULTI_CHOICE` |
| scope | varchar(16) | 作用域：`SPU` / `SKU` / `BOTH` |
| unit | varchar(32) | 单位（kg、mm 等，可空串） |
| is_filterable | tinyint(1) | 是否作为列表页筛选项 |
| is_variant_axis | tinyint(1) | 是否作为 SKU 变体轴 |
| is_active | tinyint(1) | 是否启用 |

### attribute_option — 属性选项

CHOICE 类属性的可选值。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| attribute_id | bigint | 所属属性 |
| value | varchar(120) | 存储值；与 attribute 组成唯一约束 |
| label | varchar(160) | 展示标签 |
| sort_order | int unsigned | 排序 |
| is_active | tinyint(1) | 是否启用 |

### category_attribute_definition — 类目-属性关联

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| category_id | bigint | 本地类目 |
| attribute_id | bigint | 属性；两者组成唯一约束 |
| is_required | tinyint(1) | 该类目下是否必填 |
| sort_order | int unsigned | 排序 |

### spu — 商品（SPU）

标准产品单元；爬虫导入的商品先落 `DRAFT`，审核后置 `ACTIVE`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| public_id | char(32) 唯一 | 对外标识（详情页 URL） |
| brand_id | bigint 可空 | 品牌（PROTECT） |
| local_category_id | bigint 可空 | 本地类目（PROTECT，由主映射自动落） |
| model_number | varchar(120) | 型号 |
| gtin | varchar(14) | 全球贸易项目代码（可空串） |
| status | varchar(16) | `DRAFT` / `ACTIVE` / `INACTIVE`；仅 ACTIVE 在商城可见 |
| cost_price / retail_price | decimal(18,4) 可空 | 商品池成本价 / 零售价（CHECK：成本非负、零售价 ≥ 成本） |
| is_activity | tinyint(1) | 活动商品标记（A03 品类选择「活动商品」时置真） |
| description | text | 后台录入的商品描述 |
| image_urls | json | 后台录入的图片 URL 列表（最多 5 张，首张为主图） |
| specs | json | 后台录入的规格文本 `[{name, value}]`；真实 SKU 组合仍在 `sku.specification` |

> 说明：商品池（A03）刻意复用 `spu`，不另建 `product` 表——否则爬虫导入的 7000+ 商品、商城详情页与搜索都要维护两套主档。`image_urls` / `specs` 只服务后台表单，商城展示仍读媒体库与 SKU。

### spu_translation — SPU 多语言内容

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| spu_id | bigint | 所属 SPU；与 locale 组成唯一约束 |
| locale | varchar(16) | 语言（`en-GB` 等） |
| title | varchar(500) | 标题 |
| subtitle | varchar(500) | 副标题（可空串） |
| description | longtext | 详情描述（可空串） |

### spu_source_identity — SPU 来源身份

`source_system + source_id` 唯一，保证同一来源商品重复爬取不重复建 SPU，且不可换绑到其他实体。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| spu_id | bigint | 所属 SPU（PROTECT） |
| source_system | varchar(50) | 来源系统 |
| source_id | varchar(160) | 来源商品 ID；两者组成唯一约束 |
| source_url | varchar(1000) | 来源页 URL |
| source_category_id | bigint 可空 | 最近一次观察到的来源类目 |
| first_seen_at / last_seen_at | datetime(6) | 首次/最近观察时间 |

### sku — 商品规格（SKU）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| public_id | char(32) 唯一 | 对外标识 |
| spu_id | bigint | 所属 SPU |
| specification | json | 规格键值（如 `{"Colour":"Black"}`） |
| specification_signature | varchar(64) | 规范化规格签名；与 spu 组成唯一约束（SPU 内规格组合唯一） |
| gtin | varchar(14) | SKU 级条码（可空串） |
| merchant_sku | varchar(120) | 商家侧 SKU 编号（可空串） |
| weight_grams | decimal(12,3) 可空 | 重量（克） |
| length_mm / width_mm / height_mm | int unsigned 可空 | 尺寸（毫米） |
| status | varchar(16) | `ACTIVE` / `INACTIVE` |

### sku_source_identity — SKU 来源身份

结构同 `spu_source_identity`：`source_system + source_id` 唯一（来源 SKU ID，如 `1001-black`），绑定 SKU 后不可换绑。

### product_search_document — 搜索文档

每个 (SPU, market) 一行的扁平化搜索行；商城搜索/类目列表 API 只读这张表（MySQL FULLTEXT + 复合索引），由导入/评价变化时重建。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| spu_id | bigint 唯一 | 所属 SPU |
| market_id | bigint | 市场 |
| title | varchar(500) 索引 | 标题（FULLTEXT 搜索列） |
| brand_name | varchar(160) 索引 | 品牌名冗余 |
| local_category_id | bigint 可空 | 本地类目冗余（类目过滤） |
| min_price / max_price | decimal(18,4) 可空 | ACTIVE offer 的价格区间（价格过滤/排序） |
| currency_code | varchar(3) | 币种代码 |
| rating_average | decimal(3,2) 可空 | 平均评分（评分排序） |
| rating_count | int unsigned | 评价数 |
| is_searchable | tinyint(1) | 是否可搜索（有 ACTIVE offer 且 SPU ACTIVE） |
| published_at | datetime(6) 可空 | 首次可搜索时间（"最新"排序用） |

## 2. 来源值与本地覆盖

### source_field_value — 来源字段观察值

爬虫对可覆盖字段（标题、促销标签、价格等）的最新来源值只写这里，永不直接改业务字段。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| content_type_id + object_id | int + bigint unsigned | 通用外键（目标实体：SpuTranslation / Offer 等） |
| field_code | varchar(100) | 字段代码（`title`、`promotion_label`…）；三者组成唯一约束 |
| value | json 可空 | 最新来源值 |
| source_system | varchar(50) 索引 | 来源系统 |
| observed_at | datetime(6) | 本次观察时间 |
| first_seen_at / last_seen_at | datetime(6) | 首次/最近观察 |
| is_missing | tinyint(1) | 来源页该字段缺失 |

### local_field_override — 本地字段覆盖（审核制）

人工修改值；`APPROVED` 后永远压过来源值（爬虫重导入不会遮蔽它）。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| content_type_id + object_id | 通用外键 | 目标实体 |
| field_code | varchar(100) | 字段代码；三者组成唯一约束 |
| value | json 可空 | 覆盖值 |
| status | varchar(16) 索引 | `PENDING` / `APPROVED` / `REJECTED` / `CLEARED` |
| version | int unsigned | 当前版本号 |
| reason | varchar(500) | 修改原因（必填） |
| proposed_by_id | bigint 可空 | 提交人（staff） |
| reviewed_by_id | bigint 可空 | 审核人（staff） |
| reviewed_at | datetime(6) 可空 | 审核时间 |

### local_field_override_version — 覆盖历史版本

每次创建/更新/审核/清除追加一行（`override + version` 唯一），记录 change_kind（`CREATE`/`UPDATE`/`REVIEW`/`CLEAR`）、当时 value/status/reason、操作人 actor_id 与 request_id。

## 3. 币种、市场与价格库存

### currency — 币种

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| code | varchar(3) 唯一 | ISO 代码（GBP/USD…） |
| name | varchar(80) | 名称 |
| symbol | varchar(8) | 符号（$ 符号是商城展示层规则，与此无关） |
| exponent | smallint unsigned | 小数位（默认 2） |
| is_active | tinyint(1) | 是否启用 |

### market — 市场

国家市场维度（决定币种/时区/默认语言）；当前仅 `GB`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| code | varchar(8) 唯一 | 市场代码（`GB`） |
| name | varchar(100) | 名称 |
| default_locale | varchar(16) | 默认语言 |
| time_zone | varchar(64) | 时区 |
| default_currency_id | bigint | 默认币种（PROTECT） |
| is_active | tinyint(1) | 是否启用 |

### offer — 报价（可售 offer）

(merchant, sku, market, currency) 唯一；CHECK：`current_price >= 0`、`list_price >= current_price`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| public_id | char(32) 唯一 | 对外标识（加购即加 offer） |
| merchant_id | bigint | 卖家（PROTECT；无卖家回退"Joybuy 自营导入"） |
| sku_id | bigint | SKU（PROTECT） |
| market_id / currency_id | bigint | 市场/币种（PROTECT） |
| current_price | decimal(18,4) | 当前售价（爬虫只采原价，即这里存原价） |
| list_price | decimal(18,4) 可空 | 划线价（2026-11-03 起爬虫不再保存，恒 NULL） |
| promotion_label | varchar(120) | 促销标签（展示层过滤"今日送达"类文案） |
| local_inventory | int unsigned | 本地库存（导入初始 9999；≥999 展示 "999+"） |
| source_availability | varchar(24) | 来源可售状态：`UNKNOWN`/`IN_STOCK`/`OUT_OF_STOCK`/`UNAVAILABLE` |
| suspected_stale_since | datetime(6) 可空 | 完整刷新未见到该 offer 的起始时间（疑似失效） |
| stale_confirmations | smallint unsigned | 连续确认失效次数 |
| status | varchar(16) | `DRAFT` / `ACTIVE` / `INACTIVE`；店铺商品关系里 `ACTIVE` = 已上架、`INACTIVE` = 已下架 |
| cost_price | decimal(18,4) 可空 | 商家上架时从商品池快照的成本价（发货扣款与利润依据） |
| listed_at / removed_at | datetime(6) 可空 | 上架 / 下架时间 |
| removed_by_platform | tinyint(1) | 是否由平台下架（A04） |

> 说明：「店铺商品关系」不另建表。`offer` 本来就是「商家 × SKU × 市场 × 币种」的唯一关系，天然承担文档里 merchantId + productId 的语义，且商城详情/加购已经按它工作。

### offer_source_identity — offer 来源身份

`source_system + source_id` 唯一（来源 offer ID 形如 `<商品>#<SKU>`），幂等导入的锚点；字段同 sku_source_identity。

### price_snapshot — 价格快照

每次观察追加（offer + observed_at 唯一，不覆盖历史）；字段：offer_id、currency_id、current_price、list_price、promotion_label、observed_at、source_url。CHECK 约束同 offer。

### inventory_ledger — 库存流水

一切库存变化的唯一事实来源（导入初始、人工调整、下单预占、取消释放）；余额不可为负，写入必须带幂等键或可追溯引用。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| offer_id | bigint | 所属 offer |
| quantity_delta | int | 变动量（正/负） |
| balance_after | int unsigned | 变动后余额 |
| reason | varchar(32) | `INITIAL_IMPORT` / `MANUAL_ADJUSTMENT` / `RESERVATION` / `RELEASE` / `CORRECTION` |
| idempotency_key | varchar(100) 唯一可空 | 幂等键（人工调整必填；初始导入固定 `offer-initial:<public_id>`） |
| actor_id | bigint 可空 | 操作员工 |
| request_id | char(32) 可空 | 请求追踪 ID |
| reference_type / reference_id | varchar(50)/varchar(100) | 关联对象（如 order） |
| note | varchar(500) | 备注 |

## 4. 媒体

### media_asset — 媒体资产

内容寻址（sha256 唯一，相同字节只存一份）；文件落 `var/media/<kind>/original/<aa>/<bb>/<sha256>.<ext>`，数据库只存相对路径，对外由 `/media/<相对路径>` 访问（开发由 `serve_media_file` 提供，生产由 Nginx 直接服务该前缀）。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| public_id | char(32) 唯一 | 对外标识 |
| sha256 | varchar(64) 唯一 | 内容哈希 |
| kind | varchar(16) 索引 | `PRODUCT`（商品池图）/ `REVIEW`（好评图、售后凭证）/ `CMS`（轮播图、活动图）/ `MERCHANT`（店铺头像）/ `ICON` / `FONT` |
| relative_path | varchar(255) 唯一 | 存储相对路径 |
| mime_type / extension | varchar(100)/varchar(16) | MIME 与扩展名 |
| byte_size | bigint unsigned | 字节数 |
| width / height | int unsigned 可空 | 图片尺寸 |
| duration_ms | int unsigned 可空 | 视频时长 |
| source_url | varchar(1000) | 来源 URL（爬取的图片留档） |
| first_seen_at / last_seen_at | datetime(6) | 首次/最近观察 |
| download_status | varchar(16) 索引 | `PENDING` / `DOWNLOADED` / `FAILED` |
| process_status | varchar(16) 索引 | `PENDING` / `PROCESSED` / `FAILED` / `SKIPPED` |
| error_message | varchar(500) | 处理错误信息 |

### media_variant — 媒体变体

处理管线产出的尺寸/格式变体（asset + preset + format 唯一）：preset（预设名）、format（`JPEG`/`WEBP`/`AVIF`/`MP4`/`HLS`）、width、relative_path、byte_size、status（`PENDING`/`READY`/`FAILED`）、error_message。

### 后台上传（A03/A10/A11 · M02/M03/M07）

图片由 `POST /api/v1/admin/media`（管理端）与 `POST /api/v1/merchant/media`（商家端）上传，
统一走 `media.uploads.store_upload`：按 `purpose` 决定 kind 与大小上限，落盘后返回可直接入库的 URL。

| purpose | kind | 大小上限 | 谁能传（管理端） | 谁能传（商家端） |
| --- | --- | --- | --- | --- |
| `product` | PRODUCT | 1MB | `catalog.pool.manage` | `merchant.listings.manage` |
| `review` | REVIEW | 1MB | `notifications.manage` | `merchant.aftersales.manage`（售后凭证） |
| `banner` | CMS | 2MB | `cms.banners.manage` | 不开放 |
| `activity` | CMS | 2MB | `activities.manage` | 不开放 |
| `avatar` | MERCHANT | 2MB | `merchants.manage` | `merchant.store.manage` |

校验口径（**不信任客户端的 Content-Type 与文件名**）：Pillow 先 `verify()` 再重新解码取尺寸，
格式白名单只有 JPEG / PNG / WebP，像素上限 4000 万（防解压炸弹），大小按上表硬限制。
返回体含 `url`、`sha256`、`width`/`height`、`byte_size`、`deduplicated`；
相同字节重复上传返回同一 URL（内容寻址天然去重）。

> 业务表里仍然只存 URL 字符串（`spu.image_urls`、`home_banner.image_url`、`merchant.avatar_url`、
> `merchant_notification.images`、`after_sale.proof`），不存二进制、不存 asset 外键——
> 这样换存储/加 CDN 时只改 `media_url()`，不用迁移业务表。

### media_usage — 媒体使用关系

把资产挂到任意业务对象（通用外键 content_type_id + object_id）并带展示角色；`(asset, content_type, object_id, role)` 唯一。常见 role：`gallery`（SPU 详情图）、`review_image`、`cms_banner`。另含 sort_order。

## 5. CMS 内容

### cms_page — CMS 页面（版本化）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| public_id | char(32) 唯一 | 对外标识 |
| page_key | varchar(100) 索引 | 页面键（`home`）；与 version 组成唯一约束 |
| version | int unsigned | 版本号（每次发布 +1，旧版本归档保留可回滚） |
| title | varchar(200) | 页面标题 |
| status | varchar(16) | `DRAFT` / `PUBLISHED` / `ARCHIVED` |
| published_at | datetime(6) 可空 | 发布时间 |

### cms_module — CMS 页面模块

页面内一个楼层；按 position 自上而下渲染，payload 结构按 module_type 定义在 `content/schemas.py`（坏模块降级展示，不炸整页）。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| page_id | bigint | 所属页面 |
| module_type | varchar(32) | `hero` / `banner` / `product_pool` / `rich_text` / `link_grid` / `campaign_grid` |
| position | int unsigned | 楼层序号；与 page 组成唯一约束 |
| payload | json | 类型化载荷（各类型的必选/可选字段见 schemas） |

## 6. 爬虫控制

### crawler_account — 爬虫账号

只存加密会话 blob，绝不存密码。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| public_id | char(32) 唯一 | 对外标识 |
| label | varchar(120) | 展示名 |
| account_group | varchar(100) 索引 | 账号组（任务按组选号） |
| status | varchar(32) | `ACTIVE` / `PAUSED_RISK_CONTROL` / `DISABLED` |
| session_status | varchar(16) | `UNKNOWN` / `VALID` / `EXPIRED`；ACTIVE+VALID 才可被选中执行 run |
| session_cipher | longtext | Fernet 加密的 Joybuy 会话 blob |
| session_updated_at / last_login_at / last_verified_at / last_used_at | datetime(6) 可空 | 会话与使用时间线 |
| risk_flagged_at | datetime(6) 可空 | 被风控标记时间 |
| risk_reason | varchar(500) | 风控原因 |
| rate_limit_per_minute / concurrency_limit | int/smallint 可空 | 账号级限速/并发上限 |
| note | varchar(500) | 备注 |

### crawl_job — 爬取任务

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| public_id | char(32) 唯一 | 对外标识 |
| name | varchar(200) | 任务名 |
| priority | int unsigned | 队列优先级 |
| status | varchar(16) 索引 | `DRAFT`→`READY`→`RUNNING`→`PAUSED`/`COMPLETED`/`CANCELED`/`FAILED` |
| market_id / currency_id | bigint（currency 可空） | 市场/币种（默认取市场币种） |
| locale | varchar(16) | 请求语言（默认 `en-GB`） |
| source_catalog_id / source_category_id | bigint | 来源目录与主类目（旧单类目字段，多选走 source_selection） |
| source_tree_version_id | bigint 可空 | 绑定的类目树版本（可空） |
| category_mode | varchar(24) | `CURRENT_ONLY` / `INCLUDE_SUBCATEGORIES` |
| product_limit | int unsigned | 本任务最多成功入库商品数（去重+过闸门后计数） |
| listing_sort | varchar(24) | `SOURCE_DEFAULT`/`BEST_SELLING`/`TOP_RATED`/`NEWEST`/`RANDOM` |
| random_seed | bigint 可空 | RANDOM 排序的持久化种子（可复现） |
| sync_mode | varchar(16) | `INCREMENTAL` / `FULL_REFRESH` |
| review_target | smallint unsigned | 抽检比例目标（默认 50） |
| download_product_media / download_review_media / download_detail_media | tinyint(1) | 三类媒体下载开关 |
| scheduled_at | datetime(6) 可空 | 计划启动时间 |
| concurrency | smallint unsigned | 并发（默认 1） |
| rate_limit_per_minute | int unsigned 可空 | 任务级限速 |
| account_group | varchar(100) | 使用的账号组 |
| failure_strategy | varchar(16) | 失败策略：`PAUSE` / `CONTINUE` |
| allow_manual_resume | tinyint(1) | 是否允许人工恢复 |
| created_by_id | bigint 可空 | 创建员工 |

### crawl_job_source_selection — 任务多类目选择

任务保存时冻结的每个来源类目选择（job + source_category 唯一）：source_tree_version（PROTECT，版本冻结）、include_descendants（是否含子类目）、sort_order。

### crawl_run — 爬取执行轮次

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| public_id | char(32) 唯一 | 对外标识 |
| job_id | bigint | 所属任务 |
| account_id | bigint 可空 | 启动时锁定的账号（run 不中途换号） |
| status | varchar(16) 索引 | `PENDING`/`RUNNING`/`PAUSED`/`SUCCEEDED`/`FAILED`/`CANCELED` |
| pause_reason | varchar(24) | `NONE`/`MANUAL`/`RISK_CONTROL`/`FAILURE_POLICY` |
| params_snapshot | json | 启动时任务参数快照（后续改任务不影响本 run） |
| discovered_count / downloaded_count / succeeded_count / failed_count | int unsigned | 发现/下载/成功/失败计数 |
| started_at / finished_at | datetime(6) 可空 | 起止时间 |

### crawl_run_event — run 事件流

执行器实时进度/诊断事件（管理端"发生了什么"来源）：run_id、level（`INFO`/`WARNING`/`ERROR`）、code、message(varchar 1000)、source_url、created_at。

### raw_response — 原始响应索引

归档的 HTTP 原始响应索引（gzip 文件在 raw 存储根，按日期/run/哈希落盘；到期删文件留行）。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| job_id / run_id | bigint（run 可空） | 归属任务/轮次 |
| url | varchar(2000) | 请求 URL |
| status_code | int unsigned | 响应码 |
| content_type | varchar(100) | 响应类型 |
| response_hash | varchar(64) 索引 | 内容哈希 |
| byte_size | bigint unsigned | 原始大小 |
| relative_path | varchar(255) 唯一 | 归档相对路径 |
| crawled_at | datetime(6) | 抓取时间 |
| expires_at | datetime(6) 索引 | 保留到期时间（默认 30 天） |
| file_deleted / deleted_at | tinyint(1) / datetime(6) 可空 | 文件是否已删/删除时间 |

### staging_product — 暂存商品

解析产物等待受控导入；爬虫不直接写业务表。`(source_system, source_id)` 唯一，重复摄取刷新 payload 并重置 PENDING。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| run_id | bigint 可空 | 来源 run |
| source_system / source_id | varchar(50)/varchar(160) | 来源身份（唯一约束） |
| source_url | varchar(1000) | 来源页 URL |
| payload | json | 解析规范化载荷（含只含原价的价格、SKU 列表等） |
| parser_version / structure_version | varchar(32)/int unsigned | 解析器版本/页面结构版本 |
| missing_fields | json | 缺失必填字段列表 |
| status | varchar(16) 索引 | `PENDING` / `IMPORTED` / `REJECTED` |
| error_message | varchar(500) | 拒绝原因 |
| imported_refs | json | 导入结果（spu_public_id、sku/offer 数） |
| first_seen_at / last_seen_at / imported_at | datetime(6) | 观察/导入时间线 |

### quality_gate_report — 质量闸门报告

一次闸门评估结果：run_id、page_type（`listing`/`product_detail`）、structure_version、checked_count、field_missing_rates（json）、thresholds（json）、status（`PASSED`/`FAILED`）、failure_detail、paused_job（是否触发任务暂停）。FAILED 冻结批次：staging 保持 PENDING，绝不覆盖已有数据。

### crawler_circuit_breaker — 全局熔断器

多账号在窗口内同时触发风控时全局熔断（单行表）：is_tripped、tripped_at、reason、window_minutes（默认 30）、account_threshold（默认 2）、reset_at、reset_reason。熔断期间任何任务不能启动 run，仅人工重置。

## 7. 买家

### buyer_account — 买家账号

CHECK：email 或 phone 至少一项非空。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| public_id | char(32) 唯一 | 对外标识 |
| email | varchar(254) 唯一可空 | 邮箱 |
| phone_e164 | varchar(16) 唯一可空 | 手机号（E.164） |
| password | varchar(128) | Django 哈希密码 |
| status | varchar(16) 索引 | `ACTIVE` / `DISABLED` |
| email_verified_at / phone_verified_at | datetime(6) 可空 | 验证时间 |
| last_login_at | datetime(6) 可空 | 最近登录 |
| disabled_at / disabled_reason | datetime(6) 可空 / varchar(255) | 禁用时间/原因 |
| purchase_whitelisted | tinyint(1) | 购买白名单（docs/12 需求 6-6；演示默认全 true） |

### buyer_session — 买家会话

token 只存摘要（token_digest 唯一）：account_id、expires_at（索引）、revoked_at、last_seen_at、ip_address、user_agent。

### buyer_verification_code — 买家验证码

验证码只存摘要：channel（`EMAIL`/`PHONE`）、target（varchar 254，索引组合）、purpose（`REGISTER`）、code_digest、expires_at、consumed_at、failed_attempts。

### buyer_address — 买家地址

public_id、account_id、full_name、phone、line1、line2（可空串）、city、county（可空串）、postcode（varchar 10）、country_code（默认 `GB`）、is_default。`is_serviceable` = GB + 英邮编格式（一期仅英国）。

### buyer_favourite — 买家收藏

(account, spu) 唯一，created_at 排序展示。

### buyer_recently_viewed — 买家浏览记录

(account, spu) 唯一，重复浏览只 bump viewed_at（不存历史）。

## 8. 购物车与结算

### cart — 购物车

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| public_id | char(32) 唯一 | 对外标识 |
| account_id | bigint 可空 | 登录买家；匿名车为 NULL |
| anonymous_token | varchar(128) | 匿名车令牌（48 字节随机串，浏览器 cookie 持有） |
| status | varchar(16) | `OPEN` / `MERGED` / `CHECKED_OUT` / `ABANDONED` |

条件唯一约束：每个买家/每个匿名令牌同时只能有一个 OPEN 购物车（登录合并匿名车）。

### cart_item — 购物车行

public_id、cart_id、offer_id、quantity（1–99，(cart, offer) 唯一）、added_at。

## 9. 订单与库存占用

### order — 订单

一期只有待支付与取消两个状态（支付不可用，超时自动取消）。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| public_id | char(32) 唯一 | 对外标识 |
| account_id | bigint | 买家（PROTECT） |
| status | varchar(24) 索引 | `PENDING_PAYMENT` / `CANCELED` |
| currency_id | bigint | 结算币种 |
| items_subtotal / shipping_cost / total | decimal(18,4) | 小计/运费/总额 |
| shipping_address | json | 下单时地址快照 |
| payment_expires_at | datetime(6) 索引 | 支付截止（60 分钟） |
| canceled_at / cancel_reason | datetime(6) 可空 / varchar(100) | 取消时间/原因 |

### order_item — 订单行

下单时的商品快照（不随 catalog 后续变化）：order_id、merchant_order_id（可空，指向商家履约子单）、offer_id（PROTECT）、spu_public_id、title（varchar 500）、quantity、unit_price、**unit_cost**（单位成本快照，发货扣款与商家利润依据）、currency（varchar 3）。

### merchant_order — 商家履约子单

买家侧 `order` 仍是一次支付的整体（可跨商家）；商家端只看自己的子单，发货扣成本、8 个物流节点与回款都落在子单上。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| public_id | char(32) 唯一 | 子单号 |
| order_id | bigint | 父订单（CASCADE） |
| merchant_id | bigint | 所属商家（PROTECT），(order, merchant) 唯一 |
| currency | varchar(3) | 记账币种 |
| items_total / cost_total | decimal(18,4) | 成交额 / 成本合计 |
| status | varchar(16) 索引 | `PENDING`/`SHIPPED`/`COMPLETED`（只有 3 种，超时是履约事件不是状态） |
| progress | smallint | -1 = 未发货，0–7 = 已到达节点下标（CHECK -1..7） |
| node_times | json | 8 个节点时间数组，元素可为 null |
| payment_method / recipient_region / tracking_reference | varchar | 支付方式快照 / 收件地区 / 物流凭证 |
| settled / settled_at / shipped_at / fulfillment_reset_at | tinyint / datetime 可空 | 回款标记与时间、发货时间、解封后履约起算时间 |

### inventory_reservation — 库存占用

每个订单行一条：public_id、order_id、offer_id、quantity、released（是否已释放；取消时释放并写一条库存流水）。

## 10. 评价

### virtual_reviewer — 虚拟评价者

来源评价者的本地展示身份：`fingerprint = HMAC-SHA256(密钥, 来源系统+稳定公开标识)`，不存可逆来源标识，不与真实买家合并。字段：public_id、source_system（+fingerprint 组成唯一约束）、fingerprint（varchar 64 唯一）、display_name、avatar_id（媒体）、display_attributes（json）、first_seen_at/last_seen_at。

### review — 评价

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| public_id | char(32) 唯一 | 对外标识 |
| spu_id | bigint | 所属 SPU（PROTECT） |
| origin | varchar(16) | `SOURCE`（来源评价）/ `LOCAL`（本地评价） |
| source_system / source_id | varchar(50)/varchar(160) | 来源身份；SOURCE 评价两者唯一 |
| source_url | varchar(1000) | 来源链接 |
| reviewer_id | bigint 可空 | 虚拟评价者 |
| guest_display_name | varchar(120) | 无稳定身份时的展示昵称快照（永不合并） |
| rating | smallint unsigned | 1–5（CHECK 约束） |
| title / body | varchar(300) / longtext | 标题/正文 |
| locale | varchar(16) | 评价语言 |
| variant_text | varchar(300) | 购买规格文本 |
| likes_count | int unsigned 可空 | 来源点赞数 |
| source_reviewed_at | datetime(6) 可空 | 来源评价时间 |
| source_position | json | 来源页位置（采样追溯） |
| content_hash | varchar(64) | 内容哈希（变更检测） |
| status | varchar(16) | `ACTIVE` / `DELETED`（来源删除）/ `HIDDEN`（平台隐藏） |
| first_seen_at / last_seen_at / deleted_at | datetime(6) | 观察与删除时间线 |

### review_version — 评价版本

来源内容变化时追加版本（不覆盖）：review_id、content_hash、rating、title、body、variant_text、likes_count、change_kind（`CREATED`/`UPDATED`/`DELETED`）、observed_at。

### review_media — 评价媒体

评价图/视频关联：(review, asset) 唯一；media_kind（`IMAGE`/`VIDEO`）、position、source_url、first_seen_at/last_seen_at。

## 11. 商家与商家经营域

> 2026-11-05 扩展：对接《商家端 / 管理后台开发文档》时，文档里的「商家与入驻」「钱包资金明细」「商家提现」「保证金记录」「售后」「平台活动」「推荐返佣」七组表**没有各建一张**，而是按「能合并就合并」的原则落在 `merchant` 与 `merchant_ops` 应用里；文档的「店铺商品关系」直接复用 `offer`，「商品池」复用 `spu`（见 §1、§4）。

### merchant — 商家

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| public_id | char(32) 唯一 | 对外标识（店铺 ID） |
| slug | varchar(100) 唯一 | URL slug |
| display_name / legal_name / avatar_url | varchar(160)/varchar(200)/varchar(1000) | 店铺名称 / 法定名 / 头像 |
| merchant_type | varchar(24) | `STANDARD` / `SOURCE_VIRTUAL`（来源卖家虚拟商家） / `IMPORT_FALLBACK`（"Joybuy 自营导入"兜底，商家列表默认不展示） |
| onboarding_status | varchar(24) 索引 | `DRAFT`/`PENDING_REVIEW`/`PENDING_DEPOSIT`/`ACTIVE`/`REJECTED`/`SUSPENDED` |
| requires_staff_totp | tinyint(1) | 该商家员工是否强制 TOTP |
| is_system | tinyint(1) | 系统内置（兜底商家） |
| activated_at / suspended_at / suspended_reason | datetime 可空 / datetime 可空 / varchar(255) | 激活、封店时间与封店原因 |
| **currency** | varchar(3) | 记账币种，默认 `CNY` |
| **wallet_balance** | decimal(18,4) | 钱包可用余额，CHECK ≥ 0 |
| **deposit_balance** | decimal(18,4) | 保证金余额，允许 0 或负数 |
| **credit_score** | decimal(5,2) | 信誉分，CHECK 0–100 |
| **wallet_password_hash / wallet_password_failures / wallet_password_locked_until** | varchar(128) / smallint / datetime 可空 | 6 位钱包密码摘要、连续错误次数、锁定截止 |
| **admission_approved / admission_reviewed_at** | tinyint(1) / datetime 可空 | 入驻审核结果与审核时间（有值即锁定保证金规则） |
| **deposit_enabled / deposit_required / deposit_initial_paid** | tinyint(1) / decimal 可空 / tinyint(1) | 是否启用保证金、应缴额、首次是否已缴足 |
| **ban_after_days** | smallint | 未发货封店天数，默认 4 |
| **followers / follow_delta / follow_day** | int / int / date 可空 | 总关注、当天高亮增量、增量业务日（跨日归零） |
| **exposure** | int | 曝光量（后台正向累加） |
| **last_online_at** | datetime 可空 | 商家最近操作时间 |
| **referral_code** | varchar(32) 唯一可空 | 推荐码（= 开店邀请码），下单/入驻时绑定推荐关系 |

### merchant_permission / merchant_role / merchant_role_permissions

商家侧 RBAC：permission（code 唯一、name、description）；role（code 唯一、is_system，M2M permissions，经 `merchant_role_permissions` 关联表）。

### merchant_membership — 商家成员

商家↔员工↔角色绑定（merchant + staff 唯一）：status（`INVITED`/`ACTIVE`/`DISABLED`）、joined_at。商家端登录复用 `staff_account`，归属店铺由本表判定。

### merchant_source_mapping — 来源卖家映射

`source_system + source_seller_id` 唯一（CHECK 非空），把来源卖家映射到本地 merchant（导入时的 `resolve_import_merchant` 依赖它）：merchant_id、source_name、source_url、last_seen_at。

### merchant_wallet_entry — 统一资金明细

一张表承载「商家端统一资金明细」与「管理端资金流水」，不按业务拆表，保证统计口径一致。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| public_id | char(32) 唯一 | 业务单号 |
| merchant_id | bigint | PROTECT |
| kind | varchar(32) 索引 | `RECHARGE`/`WITHDRAWAL`/`ORDER_SHIPPING`/`ORDER_SETTLEMENT`/`REFERRAL_COMMISSION`/`ADJUSTMENT` |
| state | varchar(16) | `COMPLETED`/`PENDING`/`FAILED`（提现占用为 PENDING） |
| currency | varchar(3) | 记账币种 |
| amount | decimal(18,4) | 收入为正、支出为负 |
| balance_before / balance_after | decimal(18,4) | 变动前/后余额，用于对账 |
| order_id | bigint 可空 | 关联 `merchant_order`（SET_NULL） |
| withdrawal_id | bigint 可空 | 关联提现申请（SET_NULL） |
| note | varchar(255) | 摘要 |
| idempotency_key | varchar(120) 唯一可空 | 幂等键：回款、返佣到账、提现退回、发货扣成本的唯一防线 |
| occurred_at / created_by_id | datetime 索引 / bigint 可空 | 业务发生时间 / 操作管理员 |

### merchant_withdrawal — 商家提现

public_id（申请号）、merchant_id、method（`BANK`/`CHAIN`）、currency、amount（CHECK > 0）、fee（CHECK ≥ 0）、net_amount、state（`PENDING`/`REJECTED`/`APPROVED`/`TRANSFERRING`/`FAILED`/`PAID`）、银行卡五项（name/account/holder/branch/code，编号按字符串保前导 0）、链上三项（coin/network/address）、reference（出款凭证）、reason、balance_reserved、returned（只退回一次）、approved_at/paid_at/reviewed_by_id。

### merchant_deposit_entry — 保证金记录

merchant_id、kind（`INITIAL` 首次缴纳 / `RECHARGE` 充值 / `ADJUSTMENT` 余额调整）、amount（差额，可负）、balance_before/balance_after、currency、related_id、note、created_by_id、occurred_at。余额本身存在 `merchant.deposit_balance`。

### after_sale / after_sale_event — 售后与处理时间线

售后：public_id、merchant_id、order_id、merchant_order_id（可空）、kind（`COMPLAINT`/`RETURN`）、state（`PENDING`/`PROCESSING`/`PLATFORM`/`COMPLETED`/`REJECTED`）、issue、progress、result、platform_decision（`INVESTIGATE`/`COMPLETE`/`REJECT_RETURN`）、proof（json URL 列表）、completed_at。
事件：after_sale_id、actor（`MERCHANT`/`PLATFORM`/`BUYER`/`SYSTEM`）、actor_label、action、content、created_at。

### merchant_activity / merchant_activity_participation — 平台活动

活动：public_id、title、kind（`PERMANENT`/`LIMITED`）、state（`ONGOING`/`ENDED`）、start_date、end_date（可空，CHECK ≥ start_date）、description、image_url、is_referral（推荐返佣常驻活动，全平台唯一）、sort_order。
参与：activity_id + merchant_id 唯一、joined_at、exposure_added。

### referral_program / merchant_referral / referral_commission — 推荐返佣

- `referral_program`：单行配置。tiers（json `[{min, rate}]`，首档 0、严格递增）、valid_months（默认 12）、updated_by_id。
- `merchant_referral`：referrer_id + referee_id（一对一，CHECK 不可自荐）、code_used、created_at。
- `referral_commission`：referral_id + period（`YYYY-MM`）唯一、shipped_amount、rate（核算时快照）、amount、state（`PENDING_CALC`/`PENDING_PAY`/`PAID`）、calculated_at、paid_at、paid_by_id、wallet_entry_id。

## 12. 员工与权限（平台管理端）

### staff_account — 员工账号

public_id、email（varchar 254 唯一）、display_name、password（Django 哈希）、status（`ACTIVE`/`DISABLED`）、totp_required、last_login_at、disabled_at/disabled_reason。`requires_totp` 属性 = 自身标记 ∨ 平台管理员角色 ∨ 活跃商家要求 TOTP。注：登录已改为仅邮箱+密码（TOTP 登录 2026-11-05 移除），TOTP 模型保留但处于休眠。

### platform_permission / platform_role / platform_role_permissions

平台 RBAC：permission（code 唯一）；role（code 唯一、is_platform_admin、is_system、M2M permissions 经 `platform_role_permissions`）。员工会话响应中的 `staff.permissions` 即从这里解析。

### staff_role_assignment — 员工角色分配

(staff, role) 唯一；assigned_by_id 记录分配人。

### staff_totp_device — 员工 TOTP 设备（休眠）

staff 一对一：secret_ciphertext（加密密钥）、confirmed_at、disabled_at、last_verified_counter（防重放计数器）。

### staff_session — 员工会话

token_digest 唯一、expires_at（索引）、revoked_at、last_seen_at、totp_verified_at（可空，兼容历史）、ip_address、user_agent。

## 13. 通知

### notification_template — 通知模板

(key, channel, event) 唯一：channel（`EMAIL`/`SMS`/`INBOX`）、event（`ORDER_CANCELED`/`ACCOUNT_SECURITY`）、subject、body（`{{var}}` 占位，未知变量原样保留）、is_active。

### notification_message — 通知消息

已渲染待发/已发消息：public_id、template_id（PROTECT）、channel、recipient（varchar 254）、subject、body、status（`PENDING`/`SENT`/`FAILED`，索引组合）、error_message、sent_at。

## 13.5 第二轮新增表（A10–A17）

### home_banner — 商城首页轮播图

`public_id`、`title`（≤40）、`description`（≤100）、`image_url`、`href`、`sort_order`、`enabled`、时间戳。
索引 `(enabled, sort_order)`。**没有并进 `cms_module`**：CMS 是整页版本快照（发布/回滚），轮播图是单条独立开关 + 排序的高频运营对象，塞进版本化页面会让「改一张图」变成「发一个新版本」。

### merchant_notification / merchant_notification_reply — 平台通知与多轮回复

- 通知：`public_id`、`merchant_id`、`kind`（`NORMAL`/`REVIEW`）、`title`、`content`、`spu_id`（可空）、`product_snapshot`（json 商品快照）、`rating`、`images`（json）、`read_at`（可空，平台回复后清零重新未读）、`created_by_id`。
  索引 `(merchant, read_at, created_at)`、`(kind, created_at)`。
- 回复：`notification_id`、`role`（`MERCHANT`/`PLATFORM`）、`author_label`、`content`（≤1000）、`created_at`。
- 与 `notification_template`/`notification_message` 分工：那两张是「按模板外发邮件/短信」的出站队列，这里是商家端站内信，需要已读、多轮回复和商品快照。

### support_conversation / support_message — 客服会话

- 会话：`public_id`、`merchant_id`、`kind`（`BUYER` 买家咨询 / `PLATFORM_SUPPORT` 平台客服，每商家一条）、`state`（`PENDING`/`PROCESSING`/`RESOLVED`）、`buyer_id`、`peer_name`、`spu_id`、`order_id`、`merchant_last_read_at`、`platform_last_read_at`、`last_message_at`。
- 消息：`conversation_id`、`sender`（`BUYER`/`MERCHANT`/`PLATFORM`）、`author_label`、`text`、`created_at`。
- 文档明确「客服会话与好评通知是两套业务，不共享消息列表」，所以各建各的表。

### buyer_wallet_entry — 买家余额流水

`public_id`、`account_id`、`kind`（`RECHARGE`/`PURCHASE`/`ADJUSTMENT`）、`amount`（收入正、消费负）、`balance_before`/`balance_after`、`currency`、`order_id`（可空）、`operator_label`、`note`、`idempotency_key`（唯一可空）、`occurred_at`。
`buyer_account` 同时新增 `balance`（decimal，CHECK ≥ 0）与 `region`。
**刻意与 `merchant_wallet_entry` 分开**：文档要求「白名单余额消费与商家钱包成本/回款为不同账户，不可相互覆盖」。

### 权限模型的读/写拆分（A16）

不新增表：`platform_permission` 里为每个模块补 `<模块>.view`，`<模块>.manage` 隐式包含 view（`get_staff_permission_codes` 统一补齐，升级后历史角色不会掉菜单）。前端按 `canView(module)` 决定菜单可见性，写接口仍要求 `manage`。

## 14. 审计

### audit_log — 审计日志

员工敏感操作留痕（追加不改）：actor_id（SET_NULL）、action（varchar 100）、target_type/target_id、request_id、ip_address、tenant_type/tenant_id（租户维度，可空串）、reason（必填）、before_state/after_state（json 前后状态快照）。

## 15. Django 内置表

框架自动生成，业务代码不直接使用：

- `auth_group` / `auth_group_permissions` / `auth_permission` / `auth_user` / `auth_user_groups` / `auth_user_user_permissions`：Django auth 全套（本项目用户体系是自定义的 buyer/staff，这套仅由 Django admin 使用；auth_permission 现有 288 行是各模型的默认权限）。
- `django_content_type`：通用外键的类型注册表（67 行），`source_field_value`、`local_field_override`、`media_usage` 依赖它。
- `django_migrations`：迁移执行记录（43 行）。
- `django_session`：Django 会话后端表（本项目用自定义会话，未使用）。
- `django_admin_log`：Django admin 操作日志（未使用）。
