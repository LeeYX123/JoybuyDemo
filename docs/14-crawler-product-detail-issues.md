# 14 爬虫商品详情问题汇总与解决方案（2026-11-08）

> 调试对象：`https://www.joybuy.co.uk/dp/zspeed-适用于-ipad-的无线充电触控笔带防误触倾斜感应的平板笔适用于-ipad-pro/100016395115375?requestIdentity=searchKeyWord`
>
> 脚本位置：`crawler/debug_crawl.py`（**尚未同步到正式爬虫**）
>
> 正式同步目标：`crawler/joybuy_crawler/parsers/joybuy_uk.py`、`crawler/joybuy_crawler/pipelines.py`
>
> 本文档记录 2026-11-08 这一轮用户反馈的 7 个问题、根因、调试脚本中的实现，以及后续同步回正式爬虫的步骤。

## 0. 输入 URL 支持（2026-11-08 追加）

`debug_crawl.py` 的 `LISTING_URLS` / `--listing-url` 现在同时接受两类输入（可混传）：

| 输入 | 行为 |
|---|---|
| 搜索/列表页 `https://www.joybuy.co.uk/s?k=electronics` | 照旧：解析列表卡片，按 `--limit` 逐个抓详情 |
| 商品详情页 `https://www.joybuy.co.uk/dp/<slug>/<id>` | 跳过列表页，直接分析该商品（`--limit` 不生效） |
| 两类混传 | 按输入顺序执行；同一个商品 ID 只抓一次，后续输入会打印“已抓过，跳过” |

- 类型判断：`is_product_url()`（`UK_PRODUCT_URL_PATTERN`，匹配 `/dp/<slug>/<id>`）；
- 两种入口共用 `process_product()`，落盘的 `product.json` 完全一致；
- `summary.json` 新增 `direct_products: {total, saved}`，运行结束日志会分别打印“列表页”和“直接商品 URL”的计数；
- 验证：详情 URL 单跑 → `直接商品 URL：输入 1 个，落盘 1 个`；搜索 URL 单跑 → 45 卡 → 落盘 1；混合跑 → 先详情落盘 1，搜索页跳过重复商品后再落盘 1（共 2 个）。

## 1. 问题与结论速览

| # | 问题 | 根因 | 调试脚本解法 | 正式爬虫待办 |
|---|---|---|---|---|
| 1 | 日志没有代码行号 | 日志格式只有时间/级别/消息 | 格式改为 `%(name)s:%(lineno)d` | 不需要同步（调试脚本专用） |
| 2 | 图 3~6 是服务/保障 icon | 旧逻辑把所有 `joy-sourcing.com` 图片都收进 gallery | 只从 flight `productMainImageFloor.mediaData` 取商品图；过滤 `-000-com` / s32 / s64 / s96 | 替换 `gallery` 解析段 |
| 3 | 只拿到第一张缩略图的大图 | 旧逻辑只看 DOM 上的 `bigImg`（当前选中图）；5 个 s128 缩略图没有映射到 s1248 | flight `mediaData` 本身就有 5 个大图；DOM 兜底时把 s128/s598/s180 统一升级成 s1248 并去重 | 同上 |
| 4 | 商品描述为空 | 旧选择器只找 `[class*="description"]`，实际容器是 `productDetailFloor_content` | 解析 `[class*="productDetailFloor_content"] [aria-label="rich text container"]`，按 `<li>` 分行 | 替换 `description` 选择器 |
| 5 | 规格没解析出来（颜色：白色） | 旧逻辑只找 `[data-sku-id]`，页面没有这个属性；规格在 flight `productSelectedFloor.colorSizePartList` | 解析维度名/值/规格图 s96/SKU 映射，写入 `spec_options` 与 `skus[].specs` | 新增 `spec_options` 字段并接入 `to_payload` |
| 6 | 页面下方【规格参数】为空 | PC 端这段是客户端渲染（SSR 里是 `BAILOUT_TO_CLIENT_SIDE_RENDERING` 占位） | 额外抓移动端 `https://m.joybuy.co.uk/dg/<sku>`，解析 `graphDetailListN` | 正式链路需决定：加一次移动端请求，或找到客户端调用的 API |
| 7 | 有 4 条评价/5 星但没解析出来 | `ratingInfo` 在本页是**内联对象**，旧正则要求“扁平对象里直接有 `ratingInfo`”，匹配失败 | 用 `raw_decode` 直接解 `"ratingInfo":` 后的值（dict 或 `$ref`），并兜底 `productCommonFloor` | 修 `_extract_flight_review` |

## 2. 逐条问题、证据与实现

### 问题 1：日志打印代码行号

**要求**：每条日志带源码行号。

**实现**（`debug_crawl.py::setup_logging`）：

```python
formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d %(message)s",
    "%Y-%m-%d %H:%M:%S",
)
```

控制台和 `logs/crawl-debug.log` 都生效，例如：

```
2026-11-08 22:50:24 [INFO] debug_crawl:790 图片清单：主图 1 张，详情/画廊 4 张
```

复用模块的日志（如 `joybuy_crawler.http`）也会带上自己的行号。

### 问题 2、3：图片 —— 排除 icon、补齐全部大图

**页面结构（实测）**

- 左侧缩略图容器：`class="mainImageFloor_imgShowThumbnailsList___erCg"`，每个缩略图是
  `mainImageFloor_imgShowThumbnail__HcWh4`，`src` 为 `s128x128_...`。
- 右侧大图：`class="mainMedia_bigImg__gX1oN"`，`src` 为 `s1248x1248_...`。
- 服务/保障 icon：`class="benefitBar_tag__QQwCH"`，URL 形态为
  `https://images3.joy-sourcing.com/product/s32x32_jfsintlpro-000-com/...png.webp`。
- 规格小图：`s96x96_...`，在规格区域，不属于商品画廊。

**旧实现的问题**

1. `gallery` 用 `img[src*="joy-sourcing.com"]` 全收，icon、缩略图、多尺寸重复图全部进 gallery；
2. 只看到 DOM 当前选中的 `bigImg`，其余 4 张缩略图没有升级成 s1248；
3. `dataset.save_product` 又把 `image_urls[0]` 当主图、其余当详情图，于是图 3~6 变成 icon。

**调试脚本解法**（`debug_crawl.py`）

- `decode_server_product()`：从 `self.__next_f` flight 流解出完整 `serverProduct`；
- `extract_flight_gallery()`：优先取
  `serverProduct.data.floors[productMainImageFloor].data.mediaData[*].bigImageUrl`，
  5 个媒体项一次拿全；
- `product_image_url(path, size)`：把 flight 里的裸路径拼成
  `https://images4.joy-sourcing.com/product/s1248x1248_<path>!q70.webp`；
- `clean_gallery()` 过滤规则：
  - 丢弃非 `/product/` 或非 `joy-sourcing.com` 的 URL；
  - 丢弃路径含 `-000-com` 的服务 icon；
  - 丢弃原尺寸 `< 180`（s32/s64/s96）的图；
  - 按“去掉尺寸后的路径”去重，统一升级为 s1248；
- DOM 兜底：没有 flight 数据时，把 `fallback_gallery`（正式解析器结果）按同样规则清洗。

**验证结果（本次商品）**：5 张图，全部 `s1248x1248`，无 `-000-com`；落盘 `images/main/01.webp` + `images/detail/01~04.webp`。

### 问题 4：商品描述

**页面结构**

- 描述在 `class="Accordion_accordionDetails__X7LoE"` → `productDetailFloor_innerContent__EK0ag`
  → `productDetailFloor_content__lDX1J` → `[aria-label="rich text container"]`，内容为
  `<ul><li>…</li></ul>`。
- 实测文本 1009 字；本商品描述里没有图片。

**旧实现**：只找 `[class*="description"] ::text`，匹配不到 `productDetailFloor_content`，结果空串。

**调试脚本解法**（`extract_description`）：

```python
container = selector.css(
    '[class*="productDetailFloor_content"] [aria-label="rich text container"]'
)
```

按 `<li>` 逐条取文本并用 `\n` 连接；同时收集容器内 `img[src]` / `img[data-src]` 作为描述图。

**同步正式爬虫**：替换 `parse_uk_product_detail` 里的 `description_parts` / `detail_images` 两段即可。

### 问题 5：规格（颜色：白色，规格图 s96x96）

**页面数据**（flight `productSelectedFloor`）

```json
{
  "colorSizePartList": [{
    "C-P#dimension&dimension": {"dimTitle": "颜色", "dimensionNumber": 1},
    "buttonPartList": [{
      "C-P#dimensionButton&dimensionButton": {
        "text": "白色",
        "imgUrl": "jfsintlpro-000-product/t1/.../xxx.jpg",
        "skuList": ["100016395115375"],
        "stockState": 33
      }
    }]
  }],
  "skuStatus": {"100016395115375": "0"}
}
```

规格图在 DOM 里是 `s96x96_...`；有些商品的规格没有 `imgUrl`，只有文字。

**旧实现**：只找 `[class*="sku"] [data-sku-id]`，页面没有 `data-sku-id`，于是退化成“一个隐式 SKU、specs=[]”。

**调试脚本解法**

- `extract_spec_options()` → `spec_options`：

```json
[{
  "name": "颜色",
  "values": [{
    "value": "白色",
    "image_url": "https://images4.joy-sourcing.com/product/s96x96_...jpg!q70.webp",
    "sku_ids": ["100016395115375"]
  }]
}]
```

- `sku_specs_from_options()` → `skus[i].specs = [{"name": "颜色", "value": "白色"}]`；
- 单规格商品若 `skuList` 对不上，会把“只有一个可选值”的维度直接挂到唯一 SKU 上；
- 规格图不下载，只保留 URL；无图片的规格 `image_url` 为空字符串。

**同步正式爬虫**：`UkProduct` 需要新增 `spec_options` 字段，或在 `to_payload` 里直接加 `spec_options`；`skus[].specs` 用同一映射补齐。

### 问题 6：【规格参数】

**根因（实测）**

- PC 端详情页这段是客户端渲染，SSR HTML 里是：
  `<template data-dgst="BAILOUT_TO_CLIENT_SIDE_RENDERING"></template>`，所以静态 HTML 里没有表格。
- 移动端详情页 `https://m.joybuy.co.uk/dg/<sku>`（`m.joybuy.com` 会 302 到这里）的 SSR
  flight 数据里有：

```
"logData": {
  "trade_item_getDescription": {
    "data": {
      "graphDetailsModule": {
        "specificationPartList": [{
          "C-P#Specification&specificationBasic": {
            "specificationGroupName": "规格参数"
          }
        }],
        "graphDetailList1": [
          {"C-P#Attribute&attributeBasic": {"attributeName": "电池特性", "attributes": "可充电电池"}},
          {"C-P#Attribute&attributeBasic": {"attributeName": "原产国", "attributes": "中国"}},
          {"C-P#Attribute&attributeBasic": {"attributeName": "型号", "attributes": "ID766"}},
          {"C-P#Attribute&attributeBasic": {"attributeName": "品牌", "attributes": "ZSPPED"}}
        ]
      }
    }
  }
}
```

**调试脚本解法**

- `fetch_mobile_specifications()`：对每个商品额外请求
  `https://m.joybuy.co.uk/dg/<sku>`（复用同一套 headers/Cookie），原始 HTML 存
  `raw_html/mobile/<sku>.html`；
- `extract_mobile_specifications()`：扫描所有 `"graphDetailListN":`，解码数组，
  取 `C-P#Attribute&attributeBasic.attributeName / attributes`，按 (name, value) 去重；
- 开关：`FETCH_MOBILE_SPECS = True` / 命令行 `--no-mobile-specs`；
- 失败只记 `mobile_specs.failed`，不影响商品落盘。

**验证结果**：4 条（电池特性/原产国/型号/品牌）。

**同步注意**：这是“每商品多一次请求”的成本。正式链路若不想加请求，需要从浏览器
DevTools 找到客户端调用的规格参数 API（本轮未继续追）；或只在调试/补数据时开。

### 问题 7：评价（4 条，5 星，无 AI 摘要）

**页面数据**（flight 内联，不再是 `$ref`）

```json
"ratingInfo": {
  "commentCount": 4,
  "goodCount": 4,
  "generalCount": 0,
  "poorCount": 0,
  "goodRate": 1,
  "goodRateShow": 100,
  "averageScore": 5,
  "score1Count": 0,
  "score2Count": 0,
  "score3Count": 0,
  "score4Count": 0,
  "score5Count": 4
}
```

**旧实现失败原因**：`_extract_flight_review` 用
`re.search(r'\{[^{}]*"ratingInfo"[^{}]*\}', text)` 找“扁平容器”，本页 `ratingInfo`
前面有 `"tnInfo":null}` 这种嵌套闭合，正则匹配不到；且本页没有 `totalCommentCount`
之外的包装字段。

**调试脚本解法**（`extract_flight_rating`）

1. `decode_json_after(text, "ratingInfo")`：直接 `raw_decode` 冒号后的值；
   值若是 `"$19c"` 继续用 `resolve_flight_ref` 跟槽位；
2. 平均分：`averageScore`（有评价时才采信；0 条时返回空）；
3. 条数：`commentCount`；兜底 `productCommonFloor…commonCore.commentCount`；
4. 星级分布：`score1Count` ~ `score5Count`；
5. AI 摘要：本页没有，保持空；不伪造。

**结果**：`average=5.0，count=4，distribution={"1":0,"2":0,"3":0,"4":0,"5":4}`，来源 `flight.ratingInfo`。

**同步正式爬虫**：把 `_extract_flight_review` 的正则容器解析替换为
`raw_decode` + `_flight_ref`；DOM 兜底逻辑可保留。

## 3. 调试脚本新增的 payload 字段

除原有字段外，`product.json` 新增：

```json
{
  "spec_options": [
    {
      "name": "颜色",
      "values": [
        {
          "value": "白色",
          "image_url": "https://images4.joy-sourcing.com/product/s96x96_...jpg!q70.webp",
          "sku_ids": ["100016395115375"]
        }
      ]
    }
  ],
  "specifications": [
    {"name": "电池特性", "value": "可充电电池"},
    {"name": "原产国", "value": "中国"},
    {"name": "型号", "value": "ID766"},
    {"name": "品牌", "value": "ZSPPED"}
  ],
  "skus": [
    {
      "source_id": "100016395115375",
      "price": "25.99",
      "availability": "UNKNOWN",
      "specs": [{"name": "颜色", "value": "白色"}]
    }
  ],
  "image_urls": ["…5 张 s1248 大图…"],
  "detail_image_urls": [],
  "description": "…1009 字…",
  "rating_average": "5.0",
  "rating_count": 4,
  "rating_distribution": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 4},
  "debug_sources": {
    "gallery": "flight.productMainImageFloor.mediaData",
    "spec_options": "flight.productSelectedFloor.colorSizePartList",
    "specifications": "mobile.graphDetailListN",
    "description": "dom.productDetailFloor",
    "rating": "flight.ratingInfo"
  }
}
```

`joybuy` 原生块同步增加 `specOptions` / `specifications`。

## 4. 验证记录（按验证纪律仅做针对性验证）

```bash
# 1) 静态检查
.venv/Scripts/python.exe -m ruff check crawler/debug_crawl.py
.venv/Scripts/python.exe -m ruff format --check crawler/debug_crawl.py
.venv/Scripts/python.exe -m py_compile crawler/debug_crawl.py

# 2) 用落盘的详情页 HTML 做离线断言
# 结果：gallery=5（全 s1248）、spec_options=颜色/白色 + s96 图、
#       description=1009 字、rating=5.0/4/{"5":4}、
#       specifications=4 条；断言全部通过

# 3) 真实链路（--limit 1，带图片）
.venv/Scripts/python.exe crawler/debug_crawl.py --limit 1 --delay 1 --timeout 30 \
  --no-browser-fallback --output-dir "<临时目录>"
# 结果：列表 45 卡 → 详情解析 1 → 落盘 1
#       图片 成功 5 / 失败 0（main 1 + detail 4，全部 s1248）
#       移动端规格参数 尝试 1 / 成功 1 / 失败 0
#       product.json 字段见第 3 节
```

命令行输出已带行号，例如 `debug_crawl:790 图片清单…`。

## 5. 同步回正式爬虫的步骤

1. **图片**（`joybuy_uk.py::parse_uk_product_detail`）：
   - 新增 `_decode_server_product` / `_floors_by_id` / `_flight_gallery`（可复用已有 `_flight_text`）；
   - gallery 改为 flight `productMainImageFloor.mediaData[*].bigImageUrl`，
     统一 s1248，过滤 `-000-com` / 尺寸 <180 / 去重；
   - 保留 DOM 兜底（清洗后）。
2. **描述**：把 `[class*="description"]` 换成
   `[class*="productDetailFloor_content"] [aria-label="rich text container"]`，按 `<li>` 分行。
3. **规格**：新增 `UkProduct.spec_options`；从 `productSelectedFloor.colorSizePartList`
   解析；`to_payload` 输出 `spec_options`，并把值映射进 `skus[].specs`。
4. **规格参数**：决定是否加移动端请求
   `https://m.joybuy.co.uk/dg/<sku>`；解析所有 `graphDetailListN`
   （`C-P#Attribute&attributeBasic`）。若不接受额外请求，先只保留调试脚本路径，
   正式链路暂不产出该字段。
5. **评价**：`_extract_flight_review` 改为 `raw_decode` 读 `ratingInfo`（支持内联与 `$ref`），
   兜底 `productCommonFloor.commonCore.commentCount/commentStar`。
6. **回归**：
   - `crawler/joybuy_crawler/parsers` 的 fixture 契约测试；
   - `merchant_ops` 相关导入测试不受影响（payload 只增字段）；
   - 用同一商品 URL 跑一轮真实抓取，对比 `product.json` 的 5 图/描述/规格/规格参数/评价；
   - 重点确认 `image_urls` 不再含 `-000-com`、不再重复尺寸。

## 6. 已知边界 / 后续

- **移动端规格参数 = 每商品多一次请求**。这是当前唯一稳定来源；正式链路若要省请求，
  需要继续找客户端调用的规格参数 API。
- **规格图只存 URL，不下载**；正式入库时如需要，可作为 `sku`/`option` 图片字段。
- **AI 评价摘要**：本商品没有该区块，保持空；不伪造。
- **规格无图片**：`image_url` 为空字符串，属于正常情况。
- **分类目录 slug**：仍沿用正式 `dataset.py` 的 ASCII slug 规则，中文面包屑会落到
  `uncategorized/uncategorized/`；完整面包屑在 `product.json` / `dataset_index.jsonl` 里。
- 以上增量逻辑目前只在 `crawler/debug_crawl.py`；正式爬虫未改动。

## 7. 第二轮（2026-11-09）：系列规格 / 图文详情 / AI 摘要 / 视频

调试对象：

- `100006995081936` 小绿锅
- `10003152` 中式蜂窝炒锅
- `100828902` PURE COOK 双层蒸锅
- `10404455` Apple iPhone 17 Pro 256GB

### 7.1 问题与根因

| # | 问题 | 根因 / 数据位置 |
|---|---|---|
| 1 | 规格漏了「系列」 | 系列不在 `productSelectedFloor.colorSizePartList`，在 `productSeriesFloor.series`（`{title, series:[{name, skus, id}]}`）。旧解析只看 colorSizePartList，所以小绿锅/炒锅/iPhone 的系列规格全空。 |
| 2 | 商品描述/图文详情漏 | PC 端折叠区块标题因商品而异：商品描述/重要信息、核心卖点与优势/产品详情、主要特点与优势/商品详情/设置使用与兼容性…；旧解析只认 `productDetailFloor_content`。完整图文在移动端 `structuredFloors`（`data.structuredName + modules`），图片在 `imageUrl`。 |
| 3 | 规格参数/材质与规格/技术规格漏 | 这些是 `mode=8, moduleType=3` 的 `structuredFloors`，属性在 `moduleData.extendPartList[].attributePartList[]` 与 `specificationPartList[]` 的 `C-P#Attribute&attributeBasic`。旧解析只扫 `graphDetailListN`。 |
| 4 | AI 评价摘要漏 | flight 里是内联 `"aiSummary":{"summaryContent":"…","summaryText":"…"}`，还有 `aiTagList[].tagName`；旧逻辑没有读取。 |
| 5 | 视频没解析/保存 | 画廊 `productMainImageFloor.mediaData` 里 `mediaType=2, video=true` 的项带 `videoUrl/duration/coverImageUrl`；旧逻辑只收图片。 |

### 7.2 调试脚本实现（`crawler/debug_crawl.py`）

- **规格**：`extract_spec_options()` 增加 `productSeriesFloor.series`（标题取 `title`，值取 `name`，SKU 取 `skus`），放在颜色/尺寸前面；`sku_specs_from_options()` 自动写进 `skus[].specs`。
- **PC 图文**：`extract_dom_sections()` 解析所有 `MuiAccordion-root`，保留标题/文本/图片；文本优先按 `<li>` 分行。
- **移动端详情**：`extract_mobile_detail()`：
  - `structuredFloors` → 非 mode 8 区块收集 `text/title/imageUrl` 成 `content_sections`；
  - mode 8 → `_attribute_groups()` 收集 `{group, name, value}` 规格参数；
  - 旧版结构 `graphDetailsModule`（商品 1）同样解析；最后用 `graphDetailListN` 兜底。
- **合并策略**：移动端 `structuredFloors` 优先；PC DOM 补它没有的区块（如商品 1 的「重要信息」10 张图）。
- **AI 摘要**：`extract_ai_summary()` 读 `aiSummary.summaryContent/summaryText` + `aiTagList[].tagName`，写回 `product.ai_summary/_title/_tags`。
- **视频**：`extract_videos()` 从 mediaData 取 `videoUrl/duration/coverImageUrl`；`save_product()` 用 `download_binary()` 保存到 `<商品目录>/videos/01.mp4`；`--no-videos` 可关。
- **payload 新增**：`content_sections`、`videos`、`video_urls`、`specifications[].group`、`joybuy.contentSections/videos`。
- **日志正文预览**：每个图文区块在「N 字，N 图」汇总行下打印正文，最多 300 字，超出显示 `…（已截断，原文 N 字）`；`商品描述` 也打印前 300 字；子标题（如「卫星功能」）排在正文前。

### 7.3 实测结果

| 商品 | 规格 | 规格参数 | 图文区块 | AI 摘要 | 视频 |
|---|---|---|---|---|---|
| `100006995081936` 小绿锅 | 系列：【留学生必备】1.8L小绿锅 | 13 条（规格参数） | 商品描述 622 字 + 重要信息 10 图 | 有 | 无 |
| `10003152` 蜂窝炒锅 | 系列：蜂窝炒锅 30cm / 精铁锅 32cm | 7 条（材质与规格） | 核心卖点 191 字 + 产品详情 9 图 | 有（5 个标签） | 无 |
| `100828902` 双层蒸锅 | 无（仅数量，正常） | 8 条（材质与规格） | 核心卖点 333 字 + 产品详情 807 字/7 图 + 使用说明 96 字 | 有 | 1 个，23s，7,102,340 字节已落盘 |
| `10404455` iPhone 17 Pro | 系列 1TB/512gb/256GB + 颜色 3 色 | 15 条（技术规格） | 主要特点 119 字 + 商品详情 997 字/5 图 + 设置使用兼容 124 字 | 有（6 个标签） | 无 |

- 小绿锅/炒锅/iPhone 的当前 SKU 都正确带上「系列」；iPhone 当前 SKU `10404455` = 系列 256GB + 颜色 星宇橙色。
- 蒸锅的「安全警告」文字包含在「产品详情」区块内（页面没有独立折叠标题），已随 `产品详情` 文本解析。
- 回归：之前 ZSPEED `100016395115375` 仍解析出颜色/白色、4 条规格参数、1009 字描述，无 AI（该商品没有）。

### 7.4 同步回正式爬虫（第二轮）

1. `joybuy_uk.py::parse_uk_product_detail` 增加 `productSeriesFloor.series` 规格解析（与 colorSizePartList 合并，系列在前）。
2. 移动端详情抓取改为“规格 + 图文”：解析 `structuredFloors` 的 `structuredName/modules`；mode 8 走属性组；旧版走 `graphDetailsModule`。
3. `aiSummary` 内联对象解析，写 `ai_summary/ai_summary_title/ai_summary_tags`。
4. `mediaData` 的 video 项：解析 `videoUrl/duration/coverImageUrl`；数据集落盘 `videos/`；业务表是否存视频需另定字段。
5. payload 新字段为增量字段，导入端可先忽略；`specifications` 增加 `group` 时注意旧消费者兼容。
6. **表格展示**：`specifications` 按 group 转成 `specification_tables`
   （`{title, columns:["属性","值"], rows}`）保存/返回；前端每个 group 用
   两列 `<table>` 展示，不能拼成文本（见 §7.6）。
7. 移动端详情是每商品多一次请求；正式链路需评估成本，或找客户端 API。

### 7.5 验证

```bash
# 四个商品端到端（不下载图片，下载视频）
./.venv/Scripts/python.exe crawler/debug_crawl.py \
  --listing-url "<四个商品 URL>" --no-images --timeout 45 --output-dir "<临时目录>"
# 结果：4/4 解析落盘；视频 1/0；移动端详情 4/4
```

- `product.json` 字段逐个核对（规格/规格参数/图文区块/描述图/AI/视频）通过。
- `ruff check` / `ruff format --check` / `py_compile` 通过。

### 7.6 表格展示口径（2026-11-09 用户确认）

- Joybuy 的**【规格参数】/【材质与规格】/【技术规格】都是两列表格**：
  第一列「属性」（如 材质/型号/原产国），第二列「值」。
- 解析必须保留：
  1. 分组标题（规格参数 / 材质与规格 / 技术规格）；
  2. 行顺序（按源站 `extendPartList` 顺序，**不要按 `attributeSort` 重排**）；
  3. 每个属性名/值原样保存，不把多值用逗号拆成多行（源站就是一个单元格）。
- payload 新增表格结构，后期展示直接按它渲染：

```json
"specification_tables": [
  {
    "title": "材质与规格",
    "columns": ["属性", "值"],
    "rows": [
      {"name": "用途", "value": "适用于陶瓷灶,适用于电陶灶,适用于燃气灶,适用于感应灶"},
      {"name": "材质", "value": "不锈钢"}
    ]
  }
]
```

- **展示要求**：每个 group 渲染成一个独立的两列表格（表头「属性 | 值」），
  不允许拼成一段文本或普通 `ul` 列表；平铺的 `specifications` 仅保留兼容，
  表格以 `specification_tables` 为准。
- 调试脚本已实现 `build_specification_tables()`，日志也按
  `| 属性 | 值 |` 逐行打印，便于核对。
- 同步正式爬虫/前端时，`Spu` 或详情 API 需要保存/返回同样的
  `{title, columns, rows}` 结构；前端用 `<table>` 渲染。

### 7.7 子标题识别与展示（2026-11-09 用户确认）

Joybuy 图文详情不是纯段落：同一区块里既有**子标题**（页面字体偏大、加粗、加黑），
也有正文段落，还可能有图片。解析必须保留这个层级，展示也要按子标题渲染。

**数据来源**

- 移动端 `structuredFloors` 的 `moduleData[]`：每项是一组内容，
  `__types__` 为 `{"title":"TEXT","text":"TEXT_AREA"}`；
  - `title` 非空 → **heading**（子标题）；
  - `text` → **paragraph**（正文）。
- PC DOM 兜底（如小绿锅）：`<strong>` / `<b>` → heading，剩余文字 → paragraph；
  `<li>`/`<p>` 无 strong 时整体是 paragraph。

**payload 结构**

```json
"content_sections": [
  {
    "title": "商品详情",
    "blocks": [
      {"type": "heading", "text": "iPhone 17 Pro"},
      {"type": "paragraph", "text": "史上最强大的 iPhone。…"},
      {"type": "heading", "text": "终极 Pro 相机系统"},
      {"type": "paragraph", "text": "— 三个先进的 4800 万像素后置摄像头…"}
    ],
    "text": "…扁平文本（兼容旧消费方）…",
    "images": ["…"]
  }
]
```

- `blocks` 是展示的权威结构；`text` 仅保留兼容；
- `description` 中 heading 以 `## ` 前缀标记，便于纯文本兜底；
- 区块标题（accordion 标题，如「商品详情」）和块内子标题（如「iPhone 17 Pro」）
  是两层概念，不要混用。

**展示要求**

- `type="heading"`：字体偏大一号、加粗、加黑（与 Joybuy 页面一致）；
- `type="paragraph"`：普通正文字号/字重；
- 图片按 `images` 位置展示；
- 不允许把所有块拼成一段纯文本。

**本轮实测到的子标题**

| 商品 | 区块 | 子标题 |
|---|---|---|
| iPhone 17 Pro `10404455` | 主要特点与优势 | 卫星功能 |
| iPhone 17 Pro | 商品详情 | iPhone 17 Pro、终极 Pro 相机系统、1800万像素人物居中前置摄像头、突破性的电池续航、专为 Apple Intelligence 打造、灵活、安全的 eSIM、安全警告、退货政策通知 |
| iPhone 17 Pro | 设置、使用与兼容性 | 使用说明 |
| 双层蒸锅 `100828902` | 核心卖点与优势 | 材质与工艺、产品特点与使用场景 |
| 双层蒸锅 | 产品详情 | 安全警告（其后制造商信息段落无子标题） |
| 双层蒸锅 | 使用说明 | 安装与维护 |
| 小绿锅 `100006995081936`（DOM） | 商品描述 | 产品特点：、1. 1.8L 小巧容量…、2. 英规插头…、3. 500W 低功率…、4. 多重安全防护…、5. 无氟陶瓷内胆…、安全提醒：、制造商：、责任人： |
| 炒锅 `10003152` | 核心卖点/产品详情 | 无子标题（核心卖点为纯文本，产品详情为纯图片） |

**日志**

每个区块打印「N 字，N 图，N 个子标题」，然后逐块打印：

```
[子标题] 终极 Pro 相机系统
[正文] — 三个先进的 4800 万像素后置摄像头…（超过 300 字截断）
```

**同步正式爬虫/前端**

- 解析端输出 `blocks`；详情 API/业务表保存同样的结构；
- 前端按 `blocks` 渲染：heading 加粗加大，paragraph 正常，图片按顺序插入；
- 不要只存 `content_sections[].text`，否则子标题层级会丢失。

## 8. 正式爬虫同步记录（2026-11-09）

调试脚本中经实测的第二轮行为已全部移植到正式爬虫，`crawler/debug_crawl.py` 未改动（仍作参考实现）。

### 8.1 落地内容

| 能力 | 正式实现 | 说明 |
|---|---|---|
| 画廊 | `joybuy_uk.extract_flight_gallery` / `clean_gallery` / `product_image_url` / `normalize_gallery_url` | flight `mediaData` 全量 s1248；按路径（去尺寸、去 `!q70.webp`）去重；丢 `-000-com`、s32/s64/s96、非 `/product/`；DOM 兜底同规则 |
| 系列 + 颜色规格 | `extract_spec_options` / `sku_specs_from_options` | 系列在前；单 SKU 无匹配时只挂单值维度 |
| 图文详情 | `parse_uk_mobile_detail` / `merge_mobile_detail` / `extract_dom_sections` / `_collect_blocks` / `_append_dom_block` | 移动端区块优先、PC 补缺；`blocks` 保留 heading/paragraph |
| 规格参数表格 | `_attribute_groups` / `build_specification_tables` | 保留 group 与源站行顺序；`{title, columns:["属性","值"], rows}` |
| AI 摘要 | `extract_ai_summary` + `_json_after` / `_resolve_flight_slot` | 内联 `aiSummary` 对象优先，`aiTagList[].tagName` 取标签 |
| 视频 | `extract_videos` + `dataset.download_video` / `save_product` | 浏览器 UA、120s 超时、3 次重试；落 `videos/01.mp4` 与 `dataset_index.jsonl` |

### 8.2 与调试脚本的偏差（有意为之）

1. **移动端域名改为 www**：`m.joybuy.co.uk/robots.txt` 明确 `Disallow: /dg/`，
   正式链路不能请求 m.。实测 `https://www.joybuy.co.uk/dg/<sku>` 返回同一份 SSR
   （`structuredFloors` 一致），www 站 robots.txt 未禁止 `/dg/`，所以
   `MOBILE_DETAIL_URL_TEMPLATE` 用 www；机器人开关 `CRAWL_MOBILE_DETAIL` 默认开。
2. **清理规则用「路径去重」而不是「整 URL 去重」**：同一张图的绝对地址会带
   `!q70.webp` 后缀、或来自 images1/3/4 不同主机，调试脚本的 key 会把它们当两张；
   正式实现只按 `/product/` 之后的路径去重。
3. **`images` 主图/详情图划分不变**：`image_urls[0]` 仍是主图；移动端图文图片进
   `detail_image_urls`，不改变 `dataset.save_product` 既有的主图语义。
4. **旧 SKU 规格补全**：2026-11-05 导入的 SKU 规格为空，签名是 `{}`；重抓后带规格会撞
   `SkuSourceIdentity`。`import_services._adopt_enriched_specification()` 只允许
   「旧规格为空 → 新规格非空」的单向补全（同一 `source_id`、同一 SPU、新签名未被占用），
   其它冲突仍抛 `ProductSourceIdentityInvalid`。
5. **视频不进媒体库**：媒体库只有图片 kind/role，本轮只落 dataset + payload，
   业务表字段另立任务（见 `docs/05` §9.4）。

### 8.3 验证（按验证纪律仅做针对性验证）

```bash
# 针对性测试：8 个模块共 113 例全过（含新增的 test_crawler_detail_extras 16 例）
# 复跑核心 6 个模块共 70 例亦全过（命令即下面这条）
./.venv/Scripts/python.exe backend/manage.py test \
  crawler_control.tests.test_crawler_detail_extras \
  crawler_control.tests.test_crawler_review_aggregates \
  crawler_control.tests.test_crawler_import \
  crawler_control.tests.test_crawler_rebuild \
  crawler_control.tests.test_crawler_product_category \
  catalog.tests.test_product_detail_api
# 另外一起跑过（计入 113）：test_crawler_field_rules、test_crawler_quality_gates

# 静态检查（改动文件）
./.venv/Scripts/python.exe -m ruff check <changed files>
./.venv/Scripts/python.exe -m ruff format --check <changed files>
./.venv/Scripts/python.exe -m py_compile <changed files>
```

真实页面离线复核（正式解析器 + 已保存的页面，非单测）：

| 商品 | 画廊 | 规格 | 规格表格 | 图文/子标题 | AI | 视频 |
|---|---|---|---|---|---|---|
| ZSPEED `100016395115375` | 5 张全 s1248，无 `-000-com` | Colour / White | Technical Specifications 3 行 | 商品描述 + 重要信息 7 图 | 无（不编造） | 无 |
| 小绿锅 `100006995081936` | 10 张 | Series 1 值 | 15 行 | 商品描述 23 块（9 个子标题）+ 重要信息 10 图 | 有 657 字 | 无 |
| 炒锅 `10003152` | 10 张 | Series 2 值（30cm/32cm） | 6 行 | 核心卖点 + 产品详情 9 图 | 有 557 字 / 5 标签 | 无 |
| 蒸锅 `100828902` | 9 张 | 无（仅数量，正常） | 7 行 | 核心卖点 4 块 + 产品详情 7 图 + 使用说明 | 有 619 字 | 1 个 23s，7,102,340 字节已落盘 |
| iPhone `10404455` | 7 张 | Series 3 + Color 3；当前 SKU 256GB + Cosmic Orange | 15 行 | 产品详情 16 块（含子标题）+ 5 图 | 有 588 字 / 5 标签 | 无 |

- 说明：这次抓取使用 `Accept-Language: zh-CN` 匿名会话，所以区块/属性名是英文；
  带账号 Cookie 的中文会话仍显示中文（`docs/14` §7.3 的中文实测）。
- 蒸锅视频用的是真实 CDN：`save_product` 实际下载 7,102,340 字节到 `videos/01.mp4`，
  索引 `videos` 字段正确。

### 8.4 仍然存在的边界

- 每个商品多 1 次 `/dg/` 请求；若站点对 `/dg/` 收紧 robots，关掉开关即回到 PC-only。
- 视频只落 dataset，未进媒体库/业务表。
- 规格/区块名随语言变化（EN/ZH），不是爬虫 bug；前端展示需容忍两种语言。
- 商品名/属性名的英文版本尚未做翻译落库（本任务不涉及前端与翻译）。

## 9. 正式存储 + 购物端渲染（2026-11-09）

把 §7/§8 解析出的详情增量正式落进业务表，并由详情 API / 购物端渲染。
**不改爬虫契约**（payload 字段仍是 §8 的增量字段），`crawler/debug_crawl.py` 未改动。

### 9.1 业务模型（迁移 `catalog/0014`、`media/0004`）

| 模型/字段 | 用途 |
|---|---|
| `MediaAsset.Kind.VIDEO` + `backend/media/storage.py KINDS` | 视频字节进媒体库（内容寻址、本地 `/media/videos/original/...`），复用现有 `MediaAsset.duration_ms` / `MediaVariant` 能力 |
| `catalog.SpuDetail`（OneToOne ↔ Spu） | `content_sections` / `specification_tables` / `specifications` / `spec_options` 四个 JSONField + `ai_summary` / `ai_summary_title` / `ai_summary_tags` + `source_observed_at` |
| `catalog.SpuVideo`（FK ↔ Spu / MediaAsset） | `video`（VIDEO 资产）、`poster`（图片资产）、`duration_ms`、`source_video_id`、`source_url`、`sort_order` |

- 视频字节**不进数据库**；数据库只存资产关联与元数据。
- `SpuDetail` 与 `Spu.description` / 管理端手工 `image_urls` / `specs` 并存，不互相覆盖。
- 历史商品没有 `SpuDetail` 行，API 返回空数组/空串，购物端回退 `description`。

### 9.2 导入（`crawler_control.import_services`）

- `_sync_spu_detail()`：只写入非空字段（失败/旧版解析不会清空已入库详情）；区块图片与
  `spec_options[].values[].image_url` 下载到本地媒体库后替换成 `/media/...`，下载失败的
  CDN 图直接丢弃，运行时不再请求第三方 CDN；`specifications` 有值但缺
  `specification_tables` 时后端按 group 兜底生成两列表格。
- `_import_spu_videos()`：按 `video_id` / `url` 匹配已有 `SpuVideo`，命中且文件仍在时复用；
  否则下载进媒体库。`videos` 非空时删除源站已不存在的旧视频；`videos` 为空或字段缺失时
  保留已有数据（避免下载失败/旧解析把视频清空）。
- 海报 `coverImageUrl` 同样下载成本地图片资产。
- 重复导入：`SpuDetail` 单行 upsert、`SpuVideo` 按源身份更新、媒体资产内容寻址去重；
  测试断言重复导入不新增 `SpuDetail` / `SpuVideo` / `MediaAsset`。
- `staging.imported_refs` 新增 `detail` 与 `videos` 摘要计数。

### 9.3 详情 API（`catalog.detail_views.product_detail`）

新增返回（旧字段全部保留）：

```json
{
  "videos": [{"url": "/media/videos/...", "poster": "/media/products/...",
              "duration_ms": 23000, "duration": 23.0,
              "source_video_id": "…", "sort_order": 0}],
  "content_sections": [{"title": "商品详情", "blocks": [{"type": "heading", "text": "…"}], "text": "…", "images": ["/media/..."]}],
  "specification_tables": [{"title": "技术规格", "columns": ["属性", "值"], "rows": [{"name": "型号", "value": "A3101"}]}],
  "specifications": [{"group": "技术规格", "name": "型号", "value": "A3101"}],
  "spec_options": [{"name": "系列", "values": [{"value": "256GB", "image_url": "/media/...", "sku_ids": ["<Sku.public_id>"]}]}],
  "ai_summary": "…",
  "ai_summary_title": "内容由人工智能总结自用户评价",
  "ai_summary_tags": ["…"]
}
```

- `spec_options[].values[].sku_ids` 由源 SKU id 映射为 `Sku.public_id`，供购物端直接选规格；
  映射不到时返回空数组，购物端回退按 `sku.specification` 名称/值匹配。
- `gallery` 仍只取 `MediaUsage(role=gallery)`，视频/详情图片不混进画廊。

### 9.4 购物端（`storefront/pages/p/[id].vue`）

- **画廊**：`videos` 在前、`gallery` 图片在后；缩略图支持视频封面/播放角标；主区域用
  `<video controls poster>`（本地 `/media`），视频不参与放大镜。
- **规格**：优先用 `spec_options` 渲染 chips（保留源站顺序、s96 规格图），点击通过
  `sku_ids` 映射到 SKU 并更新价格；维度名与 SKU 规格名语言不一致时用 `sku_ids` 兜底。
- **图文详情**：区块标题 → `heading`（16px/700/#1a1a1a）→ `paragraph`；区块图片按网格展示。
- **规格参数**：每个 group 一张 `<table>`，表头「属性 | 值」，`<th scope="row">` 保留行序。
- **AI 摘要**：标题 + 正文 + 标签 chips 卡片。
- **视频**：详情下方另有 `Product videos` 区块（多视频可分别播放）。
- 无 `content_sections` 时回退 `description`；无 `specification_tables` 时不渲染规格区块。

### 9.5 验证（按验证纪律仅做针对性验证）

```bash
./.venv/Scripts/python.exe backend/manage.py test \
  catalog.tests.test_product_detail_api \
  catalog.tests.test_product_detail_extras \
  crawler_control.tests.test_crawler_detail_persistence \
  crawler_control.tests.test_crawler_detail_extras \
  crawler_control.tests.test_crawler_import \
  crawler_control.tests.test_crawler_rebuild \
  media.tests
# 结果：76 tests OK
```

- 新增 `catalog/tests/test_product_detail_extras.py`（2 例：视频/结构化详情 API、历史商品空结构）；
  `crawler_control/tests/test_crawler_detail_persistence.py`（4 例：本地化落盘、幂等、空 payload 不清空、源站删除视频）。
- 迁移已在 dev 库执行：`media.0004_alter_mediaasset_kind`、`catalog.0014_spudetail_spuvideo`。
- `ruff check` / `ruff format --check`（改动 py 文件）通过。
- 购物端 `prettier --check` / `eslint` / `nuxt build` 通过。
- 浏览器实测（临时在 `947910f2…` Wireless Earbuds Pro 上挂详情/视频，测后已删除）：
  视频 `readyState=4`、`duration=2`、无错误，`currentSrc` 为本地 `/media/videos/...`；
  视频位于画廊第一位；规格 chips 带图、点击 Blue 后价格 `$19.99 → $23.49`；
  heading 计算样式 16px/700/`rgb(26,26,26)`；表格表头 `属性 | 值`、两组表格行序正确；
  AI 摘要标题/正文/3 个标签完整渲染。

### 9.6 仍然存在的边界

- 开发环境 `/media/` 由 Django `static_serve` 兜底，**未实现 HTTP Range**；生产 Nginx 需配置
  Range 支持，否则大视频拖动进度条可能只能整段加载。
- 历史商品（本次之前导入）没有 `SpuDetail` / `SpuVideo`，页面只显示原有 `description` /
  gallery；需重抓重导后才有图文区块、规格表、AI 与视频。
- 区块图片/规格图在导入时同步下载（best-effort）；下载失败的图片被丢弃，只保留文字，
  不保留第三方 CDN 兜底。
- `videos` 为空或字段缺失时不清空既有视频（安全优先，避免下载失败/旧解析误删）；只有
  非空 `videos` 列表才会按源身份清理源站已删除的视频。
- `.gitignore` 已修正：原 `media/` 规则误伤 `backend/media/` 源码目录，已改为
  `/media/` 并删除 `backend/media/` 行；运行时媒体仍在 `var/media`（由 `var/*` 忽略），
  `backend/media/` 的 `models.py` / `storage.py` / `migrations/0004` 现在会出现在
  `git status`。

### 9.7 管理端商品池暴露爬虫详情（2026-11-09）

§9 的结构化详情此前只在购物端可见；本轮把它暴露到平台管理端商品池
（列表摘要 + 详情抽屉只读展示）。爬虫契约、`crawler/debug_crawl.py`、购物端页面均未改动。

#### 9.7.1 后端（`merchant_ops/views_catalog.py`，增量字段、无破坏性变更）

| 字段 | 位置 | 说明 |
| --- | --- | --- |
| `has_detail` / `section_count` / `spec_table_count` / `video_count` | 列表 + 详情 | 轻量摘要；列表用 `select_related("detail")`（OneToOne 左连接）+ 一次 `SpuVideo` 计数批量查询，不在列表行携带完整 JSON 块 |
| `ai_summary` | 列表 | ≤80 字预览（超出截断加 `…`）；详情接口返回完整正文 |
| `source_updated_at` | 列表 + 详情 | `SpuDetail.source_observed_at`（缺省回退 `updated_at`） |
| `content_sections` / `specification_tables` / `specifications` / `ai_summary` / `ai_summary_title` / `ai_summary_tags` | 详情 | 原样返回 `SpuDetail` 各字段（图片已是本地 `/media/...`） |
| `spec_options` | 详情 | 复用 `catalog.detail_views._spec_options_payload`，`sku_ids` 与购物端一致映射为 `Sku.public_id` |
| `videos` | 详情 | 复用 `catalog.detail_views._video_payload`：本地可播放 URL + poster + `duration_ms`/`duration` + `sort_order` |
| `gallery` | 详情 | 全量图片：媒体库 `MediaUsage(role=gallery)`（爬虫导入）按 `sort_order` 在前，手工 `image_urls` 去重补后；手工 `images` 字段保持原语义（编辑弹窗仍只编辑手工 5 张） |
| `product_category` | 详情 | 爬到的商品类目（最多两级），`[{id, name, depth}]`，与购物端 `category_breadcrumb` 同构，只读参考 |

- 无 `SpuDetail` / `SpuVideo` 的历史商品：摘要为 `has_detail=false` + 全 0，详情增量字段为空数组/空串，不报错。
- 列表 `_spu_payload` 新增的摘要字段是增量字段，其它消费方（POST/PATCH/actions 回包）自动带默认值。

#### 9.7.2 前端（`admin-web/src/views/ProductPoolView.vue` + `admin.css`）

- **列表**：商品列名称下新增小徽标（`has_detail` 时）：`图文 N` / `表格 N` / `视频 N`；固定列宽布局不变。
- **详情抽屉**（全部只读，中文标签，无 CDN 资源）：
  - 画廊：`gallery` 全量图（爬虫 + 手工）；
  - 「商品类目（爬取）」：两级名拼接展示在详情栅格里；
  - 「图文详情」：区块标题 → `heading`（13px/700/#1a1a1a，仿 Joybuy）→ `paragraph` → 区块图片；无 `content_sections` 时回退 `description`（与之前一致）；
  - AI 摘要卡：标题 + 正文 + 标签 chips；
  - 「商品视频」：`<video controls poster>`（本地 `/media`）；
  - 「规格参数」：每组一张两列 `<table>`（表头「属性 | 值」，`<th scope="row">` 行表头左对齐，保留行序）；
  - 「规格选项」：chips 带 24px 圆形缩略图；
  - 手工「规格」表与 SKU 数等既有内容不变；爬虫区块不做编辑入口。

#### 9.7.3 验证（按验证纪律仅做针对性验证）

```bash
./.venv/Scripts/python.exe backend/manage.py test merchant_ops.tests.test_admin_commerce
# 结果：39 tests OK（新增 ProductPoolCrawledDetailTests 4 例）

./.venv/Scripts/python.exe -m ruff check backend/merchant_ops/views_catalog.py backend/merchant_ops/tests/test_admin_commerce.py
./.venv/Scripts/python.exe -m ruff format --check backend/merchant_ops/views_catalog.py backend/merchant_ops/tests/test_admin_commerce.py
# 全过

cd admin-web && npx prettier --check src/views/ProductPoolView.vue src/styles/admin.css
npx eslint src/views/ProductPoolView.vue
# 全过
```

- 回归：`merchant_ops.tests.test_wp42_discount_listing + test_admin_round2` 共 35 例，其中
  `NotificationApiTests` 2 例失败（`PRODUCT_NOT_LISTED` vs `FIELD_REQUIRED`）。已用
  `git stash` 验证：**该 2 例在本轮改动之前就失败**（旧断言未跟上 2026-11-07「好评推送改
  选店铺订单」的契约），与商品池改动无关。
- `crawler/debug_crawl.py` 未触碰；爬虫契约、storefront 页面、导入逻辑未改动。

## 9.8 爬虫商品的品类（local_category）关联（2026-11-10）

### 9.8.1 症状与根因

爬虫商品进了管理端商品池，有 `product_category`（商品后台两级面包屑），但
**没有本地类目（品类）**：dev 库 46 个 SPU 的 `local_category` 为 NULL，
购物端品类页/筛选看不到它们。

根因链（只读核查确认）：

1. 爬虫任务建任务时选了菜单类目（如 `l2:1420 手机`、`l2:2696 冰箱/冰柜`），蜘蛛把
   `crawl_source_category_id` / `crawl_source_category_name` 写进 payload，但
   **没有写 `payload["source_category_id"]`**（解析器 `to_payload()` 里该字段为空串）。
2. `import_staging_product` 只从 `payload["source_category_id"]` 解析
   `SourceCategory`，拿到空 → `_resolve_local_category(None)` → None →
   SPU 建档时 `local_category=NULL`；`crawl_source_category_id` 只被用于活动判定。
3. `get_or_create_spu_from_source` 只在**建档时**写 `local_category`；已有 SPU
   重导时只补 `product_category.local_category` 兜底，不补任务所选类目的映射结果。
4. 而任务所选的每个 SourceCategory 节点（`l2:1420` 等）都有 primary
   `CategoryMapping`（由 `sync_local_categories_from_joybuy` 创建），只是从未被用上。

### 9.8.2 修复（蜘蛛 + 导入 + 存量回填）

| 位置 | 变更 |
| --- | --- |
| `crawler/joybuy_crawler/spiders/joybuy_run.py` `_build_item` | 额外写 `payload["source_category_id"] = target["source_category_id"]`——语义仍是「任务所选 Joybuy **菜单**来源类目」（docs/05 §9.2），与商品面包屑的 `product_category_id`（数字 ID，另一套 ID 空间）不混用 |
| `backend/crawler_control/import_services.py` `import_staging_product` | `source_category` 解析优先 `payload["source_category_id"]`，缺失时兜底 `crawl_source_category_id`（旧 payload 无新字段也能关联）；活动判定逻辑不变 |
| `backend/catalog/product_services.py` `get_or_create_spu_from_source` 既有 SPU 分支 | `local_category_id is None` 且非活动商品时，用本轮解析出的 `local_category`（任务所选类目的 primary CategoryMapping）补上，兜底 `product_category.local_category`；**只填空、绝不覆盖**人工/管理端设置的品类；活动商品（`is_activity`）保持 NULL |

活动商品规则不受影响：`is_activity` 时导入传入的 `local_category=None`，
既有 SPU 分支也加了 `not spu.is_activity` 守卫——活动商品永远不挂品类。

### 9.8.3 一次性存量回填（dev 库，已执行）

脚本：`var/backfill_local_category_20261110/backfill_local_category.py`
（先 `BACKFILL_DRY_RUN=1` 干跑核对，再正式执行；写操作在单事务内；
写前快照 `snapshot_before.json`、写后 `snapshot_after.json` / `backfill_result.json`）。

回填链路：`SpuSourceIdentity → StagingProduct payload（source_category_id 兜底
crawl_source_category_id）→ SourceCategory → primary CategoryMapping → LocalCategory`，
失败时兜底 `Spu.product_category.local_category`（与导入语义一致）。

结果：**46 个 NULL 品类 SPU → 回填 14 个，32 个留 NULL**；活动商品 0 个。

| 回填结果 | 数量 | 说明 |
| --- | --- | --- |
| `category_mapping`（l2:1420 → phones-tablets 手机与平板） | 14 | SPU 146/148/151/158/167~176，全部是 2026-11-09「电子产品-手机测试」任务抓的手机 |
| `unmapped`（payload 无任何来源类目字段） | 31 | 2026-11-05 之前的老导入，staging payload 里没有 `crawl_source_category_id`；重抓重导后会被新导入逻辑自动补上 |
| `no_identity`（无 `SpuSourceIdentity`） | 1 | SPU 165（手工建档商品），按设计不回填 |

之后对 14 个受影响 SPU 调用 `refresh_spu_search_documents`：这批商品全部是
DRAFT / 无在售 Offer，因此没有生成任何 `ProductSearchDocument`（搜索文档只
为 ACTIVE 商品 + ACTIVE Offer 建立），属预期；商品上架时会自动建文档。

### 9.8.4 验证（按验证纪律仅做针对性验证）

```bash
./.venv/Scripts/python.exe backend/manage.py test \
  crawler_control.tests.test_crawler_import \
  crawler_control.tests.test_crawler_product_category \
  merchant_ops.tests.test_admin_commerce
# 结果：62 tests OK

./.venv/Scripts/python.exe -m ruff check <改动的 4 个 py 文件>          # 全过
./.venv/Scripts/python.exe -m ruff format --check <改动的 3 个 backend py 文件>  # 全过
# 注：crawler/joybuy_crawler/spiders/joybuy_run.py 存在本轮之前遗留的
# format 漂移（未触碰的行），本轮新增行不涉及，未整文件重排。
```

- 新增 `crawler_control/tests/test_crawler_product_category.py::LocalCategoryFromJobSelectionTests` 5 例：
  ①payload 带 `source_category_id` → 建档即挂品类；②旧字段 `crawl_source_category_id` 兜底；
  ③已有 SPU 品类为 NULL 时重导补上；④人工改过的品类不被覆盖；⑤活动商品即使带了有映射的
  `source_category_id` 也保持 `local_category=None`。
- 实库核对 SPU 151（`1d05f963…`，Samsung Galaxy S26 Ultra，来源 `joybuy_uk:100859032`，
  任务类目 `l2:1420`）：`local_category = phones-tablets（手机与平板，父类目 electronics）`；
  管理端商品池 payload `category = {name_zh: '手机与平板', path: '/1/9/'}`。
- `crawler/debug_crawl.py`、storefront 页面、管理端 UI 均未改动（本轮仅后端 + 蜘蛛 payload 字段）。

## 9.9 图文详情人工编辑（content_source 契约，2026-11-10）

管理端商品池编辑弹窗支持编辑图文详情（可编辑标题/子标题/段落 + 上传图片），
并保证**人工编辑过的图文区块不被爬虫重导入覆盖**。

### 9.9.1 数据模型

- `catalog.SpuDetail.content_source`（迁移 `catalog/0015_spudetail_content_source`，
  已在 dev 库执行）：
  - `crawler`（默认）：爬虫抓取；既有 24 行 dev 数据全部默认 `crawler`，历史行为不变；
  - `manual`：管理端人工编辑过。**导入器对 `manual` 行不再覆盖 `content_sections`**，
    其它字段（`specification_tables` / `specifications` / `spec_options` / `ai_summary` /
    视频）照常刷新；payload sections 为空时仍不写入（§9.2 既有规则不变）。
- 管理端保存入口：`PATCH /api/v1/admin/products/<public_id>`（与商品字段同一个 PATCH），
  请求体带 `content_sections` 键时：
  - 结构与爬虫 payload 一致（§7.7）：
    `[{title, blocks: [{type: "heading"|"paragraph", text}], images: [...]}]`；
  - 校验：区块 ≤ 50、单区块 blocks ≤ 100、图片 ≤ 20；标题 ≤ 120 字、heading ≤ 200 字、
    paragraph ≤ 5000 字；`images` 只接受本地上传返回的 `/media/...` URL
    （拒绝第三方 CDN 与含 `..` 的路径）；空文本块静默丢弃；
  - 保存后 `content_source` 置 `manual`（无 `SpuDetail` 行时自动创建）；
  - 审计：`PRODUCT_DETAIL_UPDATED`（before/after 带 `section_count`）；
  - 回包 `product.content_sections` / `product.content_source` 带保存后的值；
  - 错误码：`CONTENT_SECTIONS_INVALID` / `CONTENT_SECTIONS_TOO_MANY` /
    `CONTENT_BLOCK_TYPE_INVALID` / `CONTENT_TEXT_TOO_LONG` / `CONTENT_IMAGE_INVALID`。
- 详情 `GET /api/v1/admin/products/<id>` 新增 `content_source`（无详情行时为 `null`）。

### 9.9.2 前端（商品池编辑弹窗）

- 「图文详情」编辑区：按区块（section）组织，每区块有可编辑标题、块列表
  （子标题=text input 加粗展示 / 段落=textarea，可上移/下移/删除）、
  「+ 子标题」「+ 段落」添加按钮、区块图片列表（复用 `/api/v1/admin/media`
  上传接口与 purpose=product，10MB 上限，最多 20 张，可移除）；
  可「+ 新增图文区块」「删除区块」；无第三方富文本库、无 CDN。
- 编辑商品时打开弹窗会拉取 `/products/<id>` 载入现有 `content_sections`；
  保存时仅在确有区块时随 PATCH 发送 `content_sections`（空列表不发送，
  防止误清空后被导入器永久忽略）；新建商品先 POST 建档、再 PATCH 补写图文详情。
- 详情抽屉「图文详情」标题旁显示「人工编辑 · 爬虫不覆盖」徽标（`content_source=manual`）；
  抽屉只读渲染逻辑不变，保存后自动重新拉取即反映最新内容。
- 商品池新建/编辑弹窗移除【成本价】输入（成本价改为可选，见下）。

### 9.9.3 商品池成本价改为可选

- `POST /api/v1/admin/products`：`cost` 缺省/空 → `Spu.cost_price = NULL`；
  填了则必须 > 0；`price` 仍必填且 > 0；`price < cost` 仍拒绝（两者都有时）。
- `PATCH`：不带 `cost` 键 = 保持不变；带空值 = 清空成本价；带值必须 > 0。
- 商家上架链路的 NULL 成本行为（本节记录时**未改定价公式**；当天稍后已按用户拍板
  切换为零售价口径，见 §9.11，以下仅保留为历史）：
  - 当时 `merchant_ops/services.py::compute_listing_cost`：`spu.cost_price is None` → 返回 `None`；
  - 当时商家端商品卡 `cost=None` 且 `can_list=False`（按钮置灰）；上架 POST → 400
    `PRODUCT_PRICE_MISSING`「商家未设置折扣且商品缺少成本价，暂不能上架」；
  - **2026-11-10 最终口径已改为以零售价为基数**：`cost_price` 不再参与公式，
    成本价 NULL 不再阻止上架；改为**零售价 NULL 才不能上架**（见 §9.11）。

### 9.9.4 验证（按验证纪律仅做针对性验证）

```bash
./.venv/Scripts/python.exe backend/manage.py test --keepdb \
  merchant_ops.tests.test_admin_commerce \
  crawler_control.tests.test_crawler_import \
  crawler_control.tests.test_crawler_detail_persistence
# 结果：65 tests OK（新增 ProductPoolDetailContentTests 10 例 +
# test_manual_content_sections_survive_reimport_but_other_fields_refresh 1 例）
# 注：--keepdb 用于复用既有测试库（否则测试库存在时交互式确认在非 TTY 下报 EOF）；
# 其中一次运行出现过零星 setUpClass 连接错误（机器刚重启、MySQL 容器未稳定），
# 复跑两次均稳定通过。

./.venv/Scripts/python.exe -m ruff check <改动的 6 个 py 文件>          # 全过
./.venv/Scripts/python.exe -m ruff format --check backend/merchant_ops/views_catalog.py \
  backend/merchant_ops/tests/test_admin_commerce.py backend/catalog/models.py \
  backend/crawler_control/import_services.py \
  backend/crawler_control/tests/test_crawler_detail_persistence.py      # 全过
# 注：catalog/0015 迁移文件按 Django 生成原样保留（与 0014 等既有迁移一致，
# Django 生成的迁移文件本就不是 ruff format 输出风格）。

cd admin-web && npx prettier --check src/views/ProductPoolView.vue \
  src/components/ImageUploader.vue src/styles/admin.css   # 全过（ProductPoolView 已 --write 修正）
npx eslint src/views/ProductPoolView.vue src/components/ImageUploader.vue  # 0 错误
npx vite build                                           # 通过
```

- 迁移 `catalog/0015_spudetail_content_source` 已在 dev 库执行；
  实库核对：`SELECT content_source, COUNT(*) FROM spu_detail GROUP BY content_source`
  → `crawler: 24`（既有数据全部默认 crawler，未被改动）。
- 新增后端测试：PATCH 保存图文详情并置 manual（无详情行时创建）+ 回包/GET/审计断言；
  PATCH 更新已有详情但保留 specification_tables 等爬虫字段；外部图片 URL 400 且不落地
  SpuDetail；非法块类型/超长文本 400；POST 无成本价 → 201 且 `cost=null`；POST cost=0 → 400
  `PRICE_INVALID`；PATCH 不带 cost 保持原值；PATCH 空字符串清空成本价；PATCH 零售价低于成本价
  仍 400 `PRICE_BELOW_COST`；重导入时 manual 图文区块不被覆盖而 specification_tables 照常刷新。
- 未做：浏览器端到端实测编辑弹窗（后端契约与前端编译/静态检查已过，UI 行为待人工点验）；
  商家端上架对 NULL 成本商品的行为未改动（保持「不能上架」现状）。

## 9.10 商家端品类（父品类）推导 + 抓取原价 → 零售价 + 任务类目树父级半选（2026-11-10）

### 9.10.1 商家端品类推导（导入 + 存量回填）

§9.8 之后爬虫商品已带 `local_category`（任务所选菜单类目映射的本地二级类目），
本节补齐商家端维度：`Spu.merchant_category` 按本地类目的**父级（一级类目）**
从 `catalog.models.LOCAL_PARENT_MERCHANT_CATEGORY` 推导
（如 fridges-freezers → small-home-appliances → SMALL_APPLIANCE；
挂在一级类目本身时用自身 slug）。

| 位置 | 变更 |
| --- | --- |
| `backend/catalog/product_services.py` | 新增 `merchant_category_from_local(local_category)`；`get_or_create_spu_from_source` 建档时写入推导值；既有 SPU 分支在 `merchant_category` 为空时按 `spu.local_category` 补推导值。**只填空、绝不覆盖**人工/管理端设置的值；活动商品（无 local_category）推导不出，保持空串 |
| `backend/crawler_control/import_services.py` | 无需改动（merchant_category 的写入发生在 `get_or_create_spu_from_source` 内部） |

一次性存量回填（dev 库已执行）：脚本
`var/backfill_merchant_category_20261110/backfill_merchant_category.py`
（先 `BACKFILL_DRY_RUN=1` 干跑再正式执行，单事务，快照
`snapshot_before.json` / `snapshot_after.json` / `backfill_result.json` 在同目录）。
**结果：85 个「有 local_category 且 merchant_category 为空」的 SPU 全部回填成功，
0 个 unmapped**（groceries-food→HOME 62 / fridges-freezers→SMALL_APPLIANCE 9 /
phones-tablets→ELECTRONICS 14）；回填后分布 HOME 90 / ELECTRONICS 22 / COMPUTER 9 /
SMALL_APPLIANCE 9 / BABY 3 / BEAUTY 3 / HEALTH 3 / OUTDOOR 3 / PET 3（含回填前已有值），
全库仍为空的 29 个 SPU 均无 local_category（手工建档/活动商品），按设计不回填。
`merchant_category` 不参与 `ProductSearchDocument`，无需刷新搜索文档。
**坑与快照说明**：脚本最初用 `Path(__file__)` 定位输出目录——经
`manage.py shell -c "exec(open(...))"` 执行时 `__file__` 指向 Django `shell.py`，
快照被误写进 site-packages 且被随后的零售价回填覆盖；merchant 的原始快照已不可恢复，
目录内现有快照为**事后按 `updated_at` 时间戳精确重建**（62 行 @08:45:24Z + 23 行
@08:45:29Z 被零售回填重盖，行集与干跑 stdout 及 filled=85 完全吻合，文件内有
`_reconstruction_note`）。两个脚本现已改为硬编码 `OUT_DIR`，零售价回填的快照是
执行当时原样落盘的。

### 9.10.2 抓取原价 → 零售价（导入 + 存量回填）

既定业务规则（docs/12 修订说明、需求迭代文档 01 v2.2）：**抓取价=入库价=零售价，
爬虫只采原价**（payload `current_price`，crossOffPrice 折后价丢弃）。此前 `Spu.retail_price`
导入时从不写入，商品池里爬虫商品的零售价一直是空的。

| 位置 | 变更 |
| --- | --- |
| `backend/crawler_control/import_services.py` `_parse_spu_retail_price` | 新增纯函数：解析 payload `current_price`，按模型 `DecimalField(max_digits=18, decimal_places=4)` 量化（4 位小数、≤14 位整数）；缺失/非数字/负数/溢出返回 `None` |
| `backend/crawler_control/import_services.py` `_apply_spu_retail_price` | 新建与重导都更新（爬虫是价格唯一事实源）；价格缺失/非法**保留旧值**；DB 约束 `spu_retail_not_below_cost`（retail >= cost）会撞上时同样保留旧值，绝不为改价弄挂整次导入；**不动 `cost_price`**。在 `import_staging_product` 的 SPU get_or_create 之后调用 |

一次性存量回填（dev 库已执行）：脚本
`var/backfill_retail_price_20261110/backfill_retail_price.py`（同样先干跑后正式，
快照同目录）。回填对象是「有 `SpuSourceIdentity`（爬虫商品）且 retail_price IS NULL」
的 SPU，价格取最新 staging payload 的 `current_price`，用与导入同一个解析函数，
不覆盖任何非 NULL 零售价。**结果：52 个全部回填成功，0 invalid，0 撞成本约束**；
全库仅剩 1 个 NULL（SPU 165，手工建档无来源身份，按设计不回填）。

### 9.10.3 任务类目树父级半选（管理端 UI）

`admin-web/src/components/CategoryTreePicker.vue`（CrawlersView 新建任务用）：
勾选二级类目时，其一级父类目此前完全无状态（不勾、不高亮），层级不可见。

- 父类目 checkbox 现在显示 **indeterminate（半选）**：未勾选自身但有已勾选子类目；
  行加浅色 `--partial` 高亮并显示「子类目已选 N」。
- 顶部计数改为「已选 N 个类目（实际抓取范围）」；存在半选父级时追加
  「· M 个一级类目半选（仅其子类目参与抓取）」。
- **抓取范围语义不变**：父级半选只是展示态，不进入 `modelValue`，提交的
  `source_ids` 仍只含被勾选的节点本身；点半选父级仍是「勾选该父级自身」的原行为。

### 9.10.4 验证（按验证纪律仅做针对性验证）

```bash
# 测试库说明：dev 的 MySQL 账号只有 joybuy / test_joybuy 两库授权，无法新建隔离
# 测试库；且并行任务正在 test_joybuy 上跑测试（同库并发会互相锁表——本轮第一次
# MySQL 全量跑就因此撞出一次 1205 lock wait timeout）。为不互相干扰，本轮改用
# 独立 SQLite 测试库复跑（engine 可用 DJANGO_DATABASE_ENGINE 切换）：
cd backend && DJANGO_DATABASE_ENGINE=sqlite \
  DJANGO_SQLITE_PATH=<临时路径> \
  ../.venv/Scripts/python.exe manage.py test \
  crawler_control.tests.test_crawler_import \
  crawler_control.tests.test_crawler_product_category \
  crawler_control.tests.test_crawler_detail_persistence \
  merchant_ops.tests.test_admin_commerce
# 结果：85 tests OK（含新增 ParseSpuRetailPriceTests 2 例 +
# MerchantCategoryAndRetailPriceTests 6 例）

./.venv/Scripts/python.exe -m ruff check backend/catalog/product_services.py \
  backend/crawler_control/import_services.py \
  backend/crawler_control/tests/test_crawler_product_category.py   # 全过
./.venv/Scripts/python.exe -m ruff format --check <同上 3 个文件>   # 全过

cd admin-web && npx prettier --check src/components/CategoryTreePicker.vue  # 全过
npx eslint src/components/CategoryTreePicker.vue                            # 0 错误
```

- 新增测试（`test_crawler_product_category.py`）：建档写 merchant_category + retail_price；
  重导补空 merchant_category；人工 merchant_category 不被覆盖；重导按 payload 更新
  retail_price；价格非法保留旧值；价格缺失（必填校验拒绝）不动旧值；解析纯函数
  量化/非法输入边界。
- 边界/未做：`crawler/debug_crawl.py`、`backend/merchant_ops/*`、storefront、
  `ProductPoolView.vue` 未改动；admin-web 未跑 `vite build`（并行任务正在改
  admin-web 其它文件，避免被其未完成改动干扰）；树选择器未做浏览器实测
  （本机未起前后端服务，行为以 eslint/静态检查 + 代码推演为准）。

## 9.11 商家端成本价口径切换：零售价 × (1 − 折扣%)（2026-11-10）

用户拍板（本节为最终口径，取代 2026-11-08 及更早的全部旧口径）：

> 「比如我在管理端给商家设置了 20% 的折扣，那么商家端成本价显示应该是：
> 零售价 × 80%，而不是 20%。20% 是在管理后台设置的折扣，80% 才是真正计算的折扣。」

### 9.11.1 公式

- **成本价 = `Spu.retail_price` × (1 − 折扣%/100)，向上取整到分（ROUND_CEILING）。**
- 管理端 `Merchant.discount_rate / activity_discount_rate` 是**减免百分比**：
  设 20% → 成本价 = 零售价 × 80%。
  例：零售 200、折扣 20% → 160.00；零售 25.99、折扣 20% → 20.792 → **20.80**。
- **未设置折扣 = 减免 0% → 成本价 = 零售价**（不再回退商品池成本价）。
- 折扣取值顺序不变：`spu.is_activity` 且活动折扣非空 → 活动折扣；否则普通折扣；
  两者都空 → 0%。
- **基数是零售价，`Spu.cost_price` 完全不参与公式**；零售价 NULL → 返回 `None`
  （商家端 `can_list=False`，上架 400 `PRODUCT_PRICE_MISSING`）。
- 折扣 > 100% 时钳到 0，不产生负成本。
- 顾客看到的仍是零售价，不随折扣变化。
- 口径沿革（均已作废，勿回退）：
  1. 2026-11-08 之前：向上取整(零售价 × 折扣)；
  2. 2026-11-08：平台成本价 × (1 − 折扣%)；
  3. **2026-11-10 最终：零售价 × (1 − 折扣%)，ceil 到分。**

### 9.11.2 代码

| 位置 | 变更 |
| --- | --- |
| `backend/merchant_ops/services.py::compute_listing_cost` | 按最终口径重写：基数 `spu.retail_price`，`ROUND_CEILING` 量化到 `CENT`，未设折扣 rate=0，负值钳 0，零售 NULL → `None` |
| `backend/merchant_ops/services.py::reprice_listed_offers` | 新增：遍历 ACTIVE Offer，用**当前**折扣/零售价重算成本并 `update`；算出 `None` 时跳过、保留原快照；返回更新行数 |
| `backend/merchant_ops/views_merchant_catalog.py` | 从 services 导入 `compute_listing_cost`（保留 `__all__`，旧测试的导入路径不变）；商品卡 `discount_cost`、上架 POST 的 `listing_cost` 均走新公式 |
| 管理端改折扣 `views_merchants.py` | `discount_rate` / `activity_discount_rate` 变化后调 `reprice_listed_offers(merchant=...)`，回包 `repriced_offers` |
| 管理端改零售价 / 活动标记 `views_catalog.py` | PATCH 带 `price`/`cost`，以及 `mark_activity` / `unmark_activity` 后调 `reprice_listed_offers(spu=...)` |

### 9.11.3 存量刷新（dev 库已执行）

脚本 `var/reprice_retail_formula_20261110/reprice_retail_formula.py`
（`REPRICE_DRY_RUN=1` 干跑 → 正式执行；快照与结果同目录：
`snapshot_before.json` / `dry_run_result.json` / `snapshot_after.json` / `reprice_result.json`）。

- **ACTIVE Offer 共 131 个，全部重算（131 changed，0 个因零售 NULL 跳过）。**
- 分布：`Joybuy 自营导入`（无折扣）122 个，成本价从 NULL → 零售价；
  `HOMCOM`（普通 20% / 活动 30%）6 个；`CHiQ`（无折扣）3 个。
- 旧值核对：HOMCOM 活动商品旧成本 2799.30 = 平台成本价 3999 × 70%，
  说明旧口径（成本价基数）确实在用；新值为 4999 × 80% = 3499.30（非活动商品）。
  **错误公式（零售 × 20%）从未落库**，因此只需这一轮刷新，无需回滚重跑。
- 无折扣商家（含自营导入）成本价 = 零售价，是用户明确口径；预估利润为 0 属预期，
  若要留下利润需在管理端给这些商家设置折扣。

### 9.11.4 验证（按验证纪律仅做针对性验证）

```bash
./.venv/Scripts/python.exe backend/manage.py test --keepdb \
  merchant_ops.tests.test_wp42_discount_listing \
  merchant_ops.tests.test_merchant_modules
# 结果：46 tests OK

./.venv/Scripts/python.exe backend/manage.py test --keepdb \
  merchant_ops.tests.test_admin_commerce
# 结果：49 tests OK
```

- 测试已按新口径重写：零售 200/折扣 20% → 160.00；基数证明（cost 100/retail 200 → 160）；
  25.99 → 20.80、0.46 → 0.37（ceil 到分）；活动折扣优先（30% → 140.00）；
  活动无活动折扣回退普通；无折扣 → 零售价；零售 NULL → None；
  成本价 NULL 仍能按零售价算；改折扣后已上架 Offer 重算且顾客价不变；
  清空折扣 → 成本价回到零售价。
- 新增后端测试（`test_admin_commerce.py`）：`test_discount_change_reprices_listed_offers`、
  `test_clearing_discount_resets_cost_to_retail_price`。

## 9.12 管理端「上架」后购物端搜不到（2026-11-10）

用户反馈：管理端把商品上架后，购物端搜索该商品无结果。排查发现**两个独立 bug 叠加**。

### 9.12.1 上架只改 SPU 状态，没有激活商家报价 → 没有搜索文档

- 根因：购物端搜索只读 `ProductSearchDocument`，而文档的建立条件是
  **`Spu.status=ACTIVE` 且至少一个 `Offer.status=ACTIVE`**
  （`catalog/search_services.refresh_spu_search_documents`）。管理端「上架」
  以前只改 `Spu.status`，导入留下的 DRAFT Offer 保持 DRAFT，`refresh` 直接删除文档
  → 商品在购物端永远不可见。管理端「下架」却会级联下架 Offer，两个方向不对称。
- 实测（修复前）：SPU 170（Apple iPhone 17）状态 ACTIVE、Offer 179 DRAFT、
  搜索文档 0；同类「商品 ACTIVE、报价 DRAFT」共 **9 个 SPU**。
- 修复（`backend/merchant_ops/views_catalog.py::_activate_offers_on_publish`）：
  - 管理端上架时激活该商品的 **DRAFT Offer** 与 **`removed_by_platform=True` 的
    INACTIVE Offer**（平台下架后再上架的恢复路径）；
  - **商家自己下架**（`removed_by_platform=False`）的 Offer 不复活，尊重商家意愿；
  - 只处理 `onboarding_status=ACTIVE` 的商家（封店/关店不复活）；**不要求
    `admission_approved`**——爬虫导入的商家大多还没走完入驻审核，平台主动上架
    不应被商家自查条件拦住（否则这批商品永远上不了架）；
  - 激活时 `cost_price = compute_listing_cost(merchant, spu)`（§9.11 口径）、
    `current_price = 零售价`、`listed_at=now`、清空 `removed_at/removed_by_platform`；
  - 激活与 `Spu.status` 变更在**同一事务**内；没有可激活报价且也没有已上架报价时
    抛 400 `PRODUCT_OFFER_MISSING`；需要激活但零售价为空时抛 400 `PRODUCT_PRICE_MISSING`
    （状态不变，不会出现「显示已上架但购物端搜不到」的假成功）；
  - 审计 `after_state.activated_offers`，回包 `product.activated_offers`。
- 存量修复（dev 库已执行）：`var/publish_fix_20261110/publish_fix.py` +
  `refresh_docs.py`，**9 个商品共 9 个 Offer 已激活、9 个搜索文档已重建**。
  **踩坑：`publish_fix.py` 的 `PUBLISH_FIX_DRY_RUN=1` 只跳过了文档刷新，没有拦住
  报价激活（helper 直接写库），两次「干跑」实际写入了 Offer；且第二次干跑用 3 行
  覆盖了第一次的 9 行 `snapshot_before.json`。** 报价激活本身是目标状态、无数据丢失，
  但该快照只有最后 3 个商品；`refresh_docs.py` 的 dry run 是只读的（只读复跑已确认）。

### 9.12.2 短词让 MySQL 全文检索整条归零

- 修完 9.12.1 后 `q=iPhone` 能搜到、`q=iPhone 17` 仍是 0。
- 根因：MySQL `innodb_ft_min_token_size=3`（默认值，需重启才能改），
  布尔模式里 `+17*` 这种短词会让**整条 `MATCH` 返回 0**；直接验证：
  `+iPhone*` → 1 条，`+iPhone* +17*` → 0 条，`+iPhone* +256GB*` → 1 条。
- 修复（`backend/catalog/search_services.py`）：
  - 新增 `_search_terms`：正则去掉 `+ - < > ( ) ~ * " @` 等布尔运算符，避免语法/语义注入；
  - 长词（≥ `MIN_FULLTEXT_TOKEN=3`）继续走 `MATCH ... IN BOOLEAN MODE`；
  - 短词不进布尔表达式，改用**逐词 LIKE（AND）**：标题或品牌包含该词；
  - 长词全文结果为空时整体回退到逐词 LIKE（覆盖停用词等边界）；
  - 输入只剩运算符（如 `++`）时返回空结果，而不是全部商品；
  - 非 MySQL（SQLite）分支同样改为逐词 LIKE。
- 新增测试：`test_short_numeric_token_does_not_kill_the_match`
  （`iPhone 17` 命中、单独 `17` 也命中）、`test_operator_only_query_returns_empty`。

### 9.12.3 验证（按验证纪律仅做针对性验证）

```bash
./.venv/Scripts/python.exe backend/manage.py test --keepdb \
  merchant_ops.tests.test_admin_commerce            # 54 tests OK（新增 ProductPoolPublishTests 7 例）

# test_search 含 TransactionTestCase（会清空测试库种子行），--keepdb 复跑会让
# 后续 TestCase 的 setUp 找不到迁移预置的系统商家；必须用 --noinput 重建测试库：
./.venv/Scripts/python.exe backend/manage.py test --noinput catalog.tests.test_search
# 12 tests OK（新增 2 例）
```

- 实库/接口核对（后端重启后）：`/api/v1/search?q=iPhone%2017` → 1 条
  「Apple iPhone 17 256GB 黑色」；`q=Blackview` → 2 条；`q=4L%20Mini%20Fridge` → 1 条。
- 新增测试（`ProductPoolPublishTests`）：上架激活 DRAFT 报价并建文档（成本价按 20%
  折扣 = 160.00、成交价=零售价）、平台下架后再上架恢复可见、无报价 400、零售价缺失
  400、商家自己下架不复活、未过入驻审核的爬虫商家可激活、封店商家跳过。
- 已知边界：管理端**新建**的商品没有 SKU/Offer，上架会返回 `PRODUCT_OFFER_MISSING`
  （明确报错，不再假成功）；这类商品仍需商家端上架或先补齐报价。

## 9.13 购物端商品详情两处展示修正（2026-11-10）

用户对照 Joybuy 提出：

1. **图文详情图片要一张一行、铺满详情内容区宽度**。原样式
   `grid-template-columns: repeat(auto-fit, minmax(180px, 640px))` 会在宽屏上并排
   两张、单张最宽 640px。改为 `grid-template-columns: minmax(0, 1fr)`、间距
   `--space-4`，每张图 `width: 100%`（`storefront/pages/p/[id].vue`
   `.detail__content-images`）。
2. **没有评价时不展示 Customer reviews 区块**。`storefront/components/ProductReviews.vue`
   的 `<section id="reviews">` 加 `v-if="count > 0"`；筛选后为空（`count>0` 但
   当前星级无条目）仍保留区块并显示筛选空态。
3. **规格表格不再显示「属性 / 值」表头**。`storefront/pages/p/[id].vue` 的
   `.detail__spec-table` 删掉整个 `<thead>`，只保留两列数据行（首列仍是
   `<th scope="row">` 行表头，无障碍语义不变），并删除已无用的
   `.detail__spec-table thead th` 样式。数据契约里的 `table.columns` 保留不动
   （管理端抽屉仍按列名渲染表头）。

浏览器实测（Playwright，1440×900）：
- `/p/fd685c7b-…`（SPU 173，12 张详情图）：`grid-template-columns: 1326px`，
  容器与每张图宽度均 **1326px**，图片 top 依次为 954/1715/2476/3919（逐行堆叠）；
  `#reviews` 数量 **0**。
- `/p/947910f2-…`（SPU 1，有评价）：`#reviews` 数量 1，标题 `Customer reviews`。
- `/p/fd685c7b-…` 规格表格：`table` 1 个、`thead` **0** 个，行内容仍为
  「Cellular Technology / 4G」「Battery Properties / Rechargeable Battery」。
- `prettier --check` + `eslint`（改动文件）全过。

## 9.14 购物端商品详情布局对齐 Joybuy（2026-11-10 第二轮）

用户对照 Joybuy 提出 5 项：

1. **段落前加「·」符号**：`.detail__content-paragraph` 改为 `position:relative; padding-left:1.1em`，
   `::before { content:'·' }`；只有段落块加，heading 不加。
2. **内容区宽度对齐 Joybuy**：`--container-max` 由 `90rem`（1440）改为 **`93.75rem`（1500px，
   docs/12 §1「内容区最大宽约 1500px」）**。实测 1920 视口下容器 1500、左右各 210px。
   （dev 环境无法访问 Joybuy 实测 CSS，取值依据 docs/12 的测量记录；如仍偏窄需要现场截图再调。）
3. **左侧画廊与主图同高 + 半透明下拉按钮**：
   - 结构改为 `.detail__thumbs-rail` 包住 `.detail__thumbs`，rail 高度由 JS 量主图
     `.detail__image` 的 `clientHeight` 写入内联 `height`（**不能用 grid stretch——右侧购买面板
     通常比主图高，整行高度会把画廊拉长**）；`ResizeObserver` 跟随主图尺寸变化。
   - `.detail__thumbs` 纵向滚动、隐藏滚动条；缩略图 `flex:none`（否则会被 flex 压缩到全部显示，
     永远测不出溢出）。
   - 超出时底部显示半透明深色胶囊按钮（`rgb(26 26 26 / 62%)` + 白色 `⌄` + `backdrop-filter`），
     点击切换 `thumbsExpanded`：rail 变绝对定位浮层（白底、阴影）向下展开全部缩略图，
     点任一张缩略图自动收起。
   - 窄屏（≤64rem）缩略图改横向滚动，rail 高度 `auto !important`，下拉按钮隐藏。
4. **底部吸附购物条**：`.buy-bar` 固定底部（`position:fixed; z-index:40`），滑过**主图底部**
   （`imageEl.getBoundingClientRect().bottom < 0`）后出现，滑回顶部即消失；内容为
   左图 + 标题 + 规格（`selectedSku.specification` 值以 ` / ` 连接）+ 价格 + Buy now / Add to cart，
   按钮复用同一套白名单拦截与加购状态；≤48rem 收紧尺寸并隐藏规格行。
5. **评价区移到页面最后 + AI 摘要并入**：
   - `ProductReviews` 从购买区下方移到视频区之后（页面最后一个内容区块）；独立的
     `.detail__ai` 区块删除。
   - 区块标题 `Reviews`（zh：评价）；下方两栏：左侧 `4.7 / 5`、`3 reviews`、5→1 星分布条
     （点击仍按星级筛选，原 facets 合并进分布行）；右侧 AI 卡，标题用
     `reviews.aiSummary`（en: AI-generated summary from customer reviews /
     zh: 内容由人工智能总结自用户评价）+ 正文 + 标签。
   - **渲染条件改为 `count > 0 || aiSummary`**：爬虫商品有 AI 摘要但本地没有评价行，
     若仍按 `count>0` 会看不到 AI；只有 AI 时左栏隐藏、AI 卡独占一行。
   - `messages.js` 新增 `reviews.heading/ countSuffix/ starSuffix/ filterLabel/ aiSummary`
     （en/zh 双语）。

浏览器实测（Playwright，1600×1000 / 390×844）：
- 21 图画廊（SPU 164）：主图高 677、rail 高 **677**、`scrollHeight` 1336 → 出现下拉按钮；
  点击后 rail 展开到 1352、`aria-expanded=true`；点击缩略图自动收起。
- 段落 `::before` 计算值 `"·"`；截图确认每段前有「·」。
- 滚动 1400：`.buy-bar` 存在、`position:fixed; bottom:0`，标题/规格「Black Purple / 4GB+128GB」/
  价格 / Buy now / Add to cart 齐全；滚动回 0 后消失。
- SPU 170（只有 AI）：评价区位于规格区之后（top 11311 > 10465），标题 Reviews、
  AI 标题 `AI-generated summary from customer reviews`、无「No reviews yet」残句。
- SPU 1（3 条评价、无 AI）：`4.7 / 5`、`3 reviews`，5★ 67%（2 条）、4★ 33%（1 条）、3/2/1★ 0。
- 移动端 390：购物条固定底部，缩略图横向滚动、无下拉按钮。
- `vitest run` **47 tests OK**（更新 `design-tokens.test.js` 断言容器 1500）；
  `nuxi build` 通过；`prettier --check` + `eslint` 全过。

## 9.15 详情页宽度 / 吸附条 / 评价评分对齐 Joybuy（2026-11-10 第三轮）

网络恢复后直接对 joybuy.co.uk 实测（Playwright，1600×1000 与 1920×1000）：

| 目标 | Joybuy 实测 | 本仓库调整 |
| --- | --- | --- |
| 内容区宽度 | 商品标题/内容 1512px：1440 视口 x=48（宽 1344）、1600 视口 x=44（1512）、1920 视口 x=204（1512，居中，外层 floor 1552） | `--container-max: 100.5rem`（1608 = 1512 + 2×48）+ ≥80rem `--container-pad: 3rem`；实测 1920 内容 **1512 / left 204** 与 Joybuy 完全一致，1600 为 1504（无滚动条差 8px） |
| 底部吸附条高度 | `m.joybuy.co.uk` 的 `bottomBarFloor_bottom_bar_wrap__3J58m` 高 **68px**、通栏；内部只有 Buy now / Add to cart 两个 175×36 按钮（移动端） | `.buy-bar` 固定 `height: 68px`，内部元素垂直居中（缩略图 48、按钮 40） |
| 评价区 | 商品头部显示 4.9 (400+ reviews)；Reviews 是独立 tab，匿名访问无法展开内容（cookie 弹窗/懒加载），AI 卡样式无法实测 | 评分改为「本地评价优先，否则用源站快照」；AI 卡改为中性样式（`#F5F6F7` 底、1px 边框、radius 8、14px/700 黑标题、`#55565B` 正文），去掉蓝色主题 |

### 9.15.1 评分为什么之前不显示 / 现在怎么来

- 根因：购物端评分一直只统计本地 `Review` 行，而爬虫从不导入单条评价 → 爬虫商品 `review_summary.count` 恒为 0，评价区只剩 AI 摘要。
- 持久化：`SpuDetail` 新增 `rating_average` / `rating_count` / `rating_distribution`（迁移 `catalog/0016`，dev 库已执行）；导入 `_sync_spu_detail` 用 `_parse_rating_summary` 写入 payload 的 `rating_average / rating_count / rating_distribution`，**空 payload 不覆盖旧快照**。
- API：`catalog/detail_views` 的 `review_summary` 增加 `distribution` 与 `source`；本地有 ACTIVE 评价 → `source=local`（并聚合本地星级分布），否则回退 `SpuDetail.rating_*` → `source=crawler`。
- 前端：`ProductReviews` 接收 `review-summary`，本地评价为空时用快照显示 `4.5 / 5`、`9 reviews`、5→1 星分布条；此时不显示「No reviews yet」，也不显示分页（本地无条目）。
- 存量回填（dev 库已执行）：`var/backfill_rating_20261110/backfill_rating.py`（干跑→正式，计划/结果同目录）——**19 个有源站评分的 SPU 已回填，164 个无评分 payload 跳过**；已有评分快照的商品不覆盖。
- 注意：源站本身没有评分的商品（如 SPU 170 SONGMICS 小冰箱，payload 与线上页面都无 ratingInfo）仍然只有 AI 摘要，这是数据事实，不是展示 bug；已回填的 19 个商品当前都是 DRAFT，管理端上架后即可看到评分。

### 9.15.2 验证（按验证纪律仅做针对性验证）

```bash
./.venv/Scripts/python.exe backend/manage.py test --keepdb \
  catalog.tests.test_product_detail_api catalog.tests.test_search \
  crawler_control.tests.test_crawler_product_category \
  crawler_control.tests.test_crawler_detail_persistence
# 48 tests OK（新增：评分快照回退 / 本地评价优先 / _parse_rating_summary 3 例 /
#            导入写入 SpuDetail 且无评分 payload 不覆盖）
```

- 浏览器（临时给 SPU 170 写入 4.5/9 快照验证，**验证后已还原为 0/空**）：
  1600 视口内容 1504、1920 视口 **1512 / left 204**；吸附条 **68px**、缩略图 48；
  评价区左栏 `4.5 / 5`、`9 reviews`、5★ 78%（7）、4★ 11%（1）、1★ 11%（1）；
  AI 卡 `rgb(245,246,247)`、radius 8px、标题 `rgb(26,26,26)` / 700。
- `vitest run` 47 OK；`nuxi build` 通过；`prettier` + `eslint` 全过；5 个后端改动 py
  `ruff check` 全过、手写文件 `ruff format --check` 全过（0016 迁移按 Django 生成原样保留）。
- **踩坑**：Nuxt dev 对 `tokens.css` 的 HMR 不生效（`--container-max` 更新了、
  `--container-pad` 仍是旧值）——改全局 CSS 变量后必须重启 storefront dev server
  再量，否则会得出「改小了/改大了」的错误结论。

### 9.15.3 AI 摘要标签从购物端移除（2026-11-10）

用户指定商品 `6ce7a4ba-03f9-441a-b111-801d02473952`（SPU 183）底部 AI 卡里的
「价值与价格 / 噪音等级 / 设计与做工质量 / 配送体验」标签不需要展示。

- 购物端 `ProductReviews` 删除 `.reviews__ai-tags` 整块（markup + 样式）及
  `aiSummaryTags` prop；`pages/p/[id].vue` 不再传 `ai_summary_tags`、删除对应 computed。
- **数据未删**：`SpuDetail.ai_summary_tags` 仍由爬虫导入并在管理端商品池详情抽屉只读展示，
  只是购物端不再渲染。
- 实测 SPU 183：评价区只显示 AI 标题 + 正文，`li` 数量 0；`prettier` + `eslint` 全过，
  `vitest run` 47 tests OK。

## 10. 导入失败诊断：来源身份冲突（2026-11-09）

### 10.1 症状

正式运行里单个商品报：

```
导入失败：商品 100859032 导入失败：The source offer identity is already assigned
to a different offer.
```

### 10.2 判定规则（先分清「重复导入」与「来源身份冲突」）

来源 Offer 的身份键是 `OfferSourceIdentity(source_system, source_id)`，其中
`source_id = "<商品ID>#<SKU ID>"`。导入前会按这个身份查已有 Offer：

| 情况 | 判定 | 行为 |
| --- | --- | --- |
| 身份已存在，且 `offer.sku / merchant / market / currency` 全部与本次一致 | **普通重复导入** | 幂等：刷新价格快照与 `last_seen_at`，不报错、不新增 Offer |
| 身份已存在，但 `sku / merchant / market / currency` 任一不一致 | **来源身份冲突**，不是普通重复行 | 拒绝导入；**绝不自动改绑**已有 `OfferSourceIdentity` |

100859032 是第二种：身份 `joybuy_uk:100859032#100859032` 已绑定 Offer 159
（商家 12 `Samsung`、市场 1、币种 1），而本次 payload 的 seller 解析成
`三星 查看店铺` → 新商家 14。根因是**卖家名称/本地化漂移**，不是重复导入。
类似地，`SkuSourceIdentity` 指向另一商品或另一规格时也按冲突处理。

### 10.3 中文错误契约

- 导入层（`crawler_control.import_services`）捕获 `OfferSourceIdentityInvalid` /
  `ProductSourceIdentityInvalid`，改抛 `crawler_control.domain.ImportSourceConflict`；
  事件码固定为 **`IMPORT_SOURCE_CONFLICT`**（前端标签「来源身份冲突（未改绑）」）。
- 消息必须中文、可执行，至少包含：来源身份、现有商家/ID、现有 SKU 规格、现有市场/币种、
  本次商家/ID、本次 SKU 规格、不一致字段，以及「可能由卖家名称或本地化变化导致，系统不会
  自动改绑，请检查商家映射后再导入」。
- 示例（100859032）：

  ```
  商品 100859032 的来源 Offer「joybuy_uk:100859032#100859032」已绑定到另一个 Offer：
  现有商家 Samsung/12、SKU（内存=12GB+512GB、颜色=黑色）、市场 GB、币种 GBP；
  本次商家 三星 查看店铺/14、SKU（内存=12GB+512GB、颜色=黑色）、市场 GB、币种 GBP；
  不一致：商家。
  这通常不是重复导入，而是卖家名称/本地化变化（例如同一店铺在中英文站显示不同名称）
  导致同一来源身份解析到了不同商家。系统不会自动改绑已有 Offer，
  请检查商家映射（MerchantSourceMapping）后再导入。
  ```

  说明：100859032 的旧 SKU 149 规格是空签名 `{}`，导入时会被
  `_adopt_enriched_specification` 单向补全成内存/颜色规格，所以两侧展示的 SKU 规格相同；
  真正不一致的是商家。这正是「SKU 一样、商家不同」的典型卖家名漂移场景。

- 原始英文异常只写 `logger.debug(..., exc_info=True)`，不直接展示；`staging.error_message`
  同步写同一条中文（截断 500 字符，`StagingProduct.error_message` 上限）。
- 任务失败计数照常 +1，暂存记录保持 `PENDING`（可修数据后重试，不自动删除）。

### 10.4 卖家名归一化（`normalize_seller_name`）

- 解析器 `crawler/joybuy_crawler/parsers/joybuy_uk.py` 新增 `normalize_seller_name()`：
  大小写不敏感地剥掉中文/英文店铺卡片 UI 后缀（`查看店铺`、`进入店铺`、`查看商店`、
  `View store`、`Visit store`、`View shop`、`Visit shop`），压缩空白并去掉首尾
  `| · / , - —`。`三星 查看店铺 → 三星`、`Samsung View store → Samsung`；
  `Samsung 官方店` 这类真实店名不会被改。
- 只清洗**新抓取**的 payload；已入 staging 的旧 payload、已存在的
  `MerchantSourceMapping` 不会自动改写。
- **已知限制**：flight JSON 只有 `sellerName`，没有稳定 shop/vender ID
  （`crawler/fixtures/product_detail_reviews_v2.html` 可证）；因此 `source_seller_id`
  仍等于名称，跨语言别名（`Samsung` vs `三星`）无法自动归并。这是已知限制，不是 bug。
  后续若要做稳定映射，优先在管理端维护「来源卖家 → 商家」别名表或按 `/store/<id>`
  建立映射，而不是继续依赖名称。

### 10.5 商品 100859032 的人工恢复建议（2026-11-09 已执行：整体合并到商家 12）

需要恢复时先取得用户批准，再二选一：

1. **首选：修正映射后重导**。确认商家 14 `三星 查看店铺` 没有其它商品/Offer 后，把
   `MerchantSourceMapping(joybuy_uk, '三星 查看店铺')` 改为指向商家 12 `Samsung`，
   再重试暂存记录 `a2df75b8-365b-460b-8c41-e3042b349dfc`。Offer 159 与身份保持不变。
2. **备选：显式合并商家**（仅当 14 已被别的商品使用）。把 14 的 Offer/映射迁到 12 后再
   删/停用 14；这是管理动作，必须人工审核，不能由导入链路自动完成。

**绝对不要**直接改 `OfferSourceIdentity.offer` 指向另一个 Offer，也不要在导入器里加
「商家不一致就自动改绑」的分支——那会静默改写历史 Offer 归属。

> 2026-11-09 的核查确认商家 14 已被 Z Flip 8 占用，用户因此批准走**备选方案**；
> 实际执行记录见 §10.5.2。下面两小节保留为核查与决策依据。

#### 10.5.1 2026-11-09 执行核查：商家 14 存在业务引用，当时按约束中止

用户批准了「把 `三星 查看店铺` 映射改指商家 12 并重导 100859032」，前置条件之一是
「商家 14 没有被其它商品使用」。**只读核查发现该前提不成立，因此未执行任何写操作**
（未改映射、未新建 `三星` 映射、未重导、未删除商家 14）。

- **商家 14 的唯一业务引用（Offer）**：
  - `Offer` **161**（`120ee2dd-1934-4bc5-833b-42640b60b9d8`，DRAFT，未上架
    `listed_at=null`）→ `Sku` 151 → `Spu` 153（`7ed46b40-8824-4d1a-aaef-239da562b690`，
    《三星 Galaxy Z Flip 8 5G 256GB 石墨色》，DRAFT）。
  - 来源身份 `OfferSourceIdentity(joybuy_uk, '100006925022956#100006925022956')` 指向
    Offer 161；来源商品 100006925022956，暂存记录 `8cf5dd6f-a2d5-4959-bc9c-8c1573d33f83`
    （IMPORTED，2026-11-06 08:59:04），payload 卖家同样是 `三星 查看店铺`。
- **其它引用全部为 0**：`MerchantDailyStat`、`MerchantMembership`、`MerchantWalletEntry`、
  `MerchantWithdrawal`、`MerchantDepositEntry`、`AfterSale`、`MerchantActivityParticipation`、
  `MerchantReferral`（referrer/referee）、`SupportConversation`、`MerchantOrder`、
  `AutoOrderTask`、`MerchantNotification`，以及通用外键 `SourceFieldValue` /
  `LocalFieldOverride` / `MediaUsage`。
- **商家 12 确认**：pk 12、`display_name=Samsung`、`SOURCE_VIRTUAL`、`ACTIVE`、`is_system=true`；
  已有映射 `joybuy_uk:'Samsung' → 12`（id 11）；Offer 159 属于它。
- **映射现状**：`joybuy_uk:'三星 查看店铺'` 仅 1 条（id 13 → 14）；
  `joybuy_uk:'三星'` 0 条；`joybuy_uk:'Samsung'` 1 条（id 11 → 12）。

**为什么不能只改映射**：商家 14 正是同一家三星店铺在中文站显示名下的第二件商品
（Z Flip 8）的归属。若把 `三星 查看店铺` 映射改指 12 而不迁移 Offer 161，同一来源卖家会
分裂到两个商家：历史 Offer 161 仍在 14，未来抓取与重导（100006925022956）会解析到 12，
从而立即产生新的 `IMPORT_SOURCE_CONFLICT`（商家不一致）。这属于「14 已被别的商品使用」
的情形，必须走显式合并（迁移 Offer 161 + 映射）。

#### 10.5.2 2026-11-09 执行记录：商家 14 整体合并到商家 12（已完成）

用户拍板（明确批准）：**把商家 14 `三星 查看店铺` 整体合并到商家 12 `Samsung`**。
执行时间 2026-11-09 约 12:01–12:02 UTC，dev MySQL `joybuy`，全程 Django ORM，
**全部写操作（迁移 Offer 161、改映射、建别名、停用商家 14、两次重导）在同一个
`transaction.atomic()` 内完成**；任何一步失败即整体回滚，实际执行一次通过并提交。

**前置断言（全部通过后才写入）**：商家 14 仅 1 个 Offer（161）和 1 条映射（13）；
Offer 161 为 DRAFT、SKU 151、市场 GB(1)、币种 GBP(1)、`listed_at=null`；
SKU 151 在商家 12 / GB / GBP 下没有任何其它 Offer（无唯一约束冲突）；
Offer 161 只有来源身份 / 价格快照 / 库存流水 / 2 条 `SourceFieldValue` 引用，
**没有 MerchantOrder、购物车、钱包、售后、通知、活动等业务行**；
商家 14 除 Offer 161 与映射 13 外引用全为 0；SPU 151 / 153 均为 DRAFT。

**实际变更**：

| 对象 | 变更前 | 变更后 |
| --- | --- | --- |
| `Offer` 161 | merchant 14、SKU 151、GB/GBP、DRAFT、1149.00 | **merchant 12**，其余字段（SKU/市场/币种/价格/状态/`listed_at`）全部不变；只更新 `merchant` 一列 |
| `MerchantSourceMapping` id 13 | `joybuy_uk:'三星 查看店铺'` → 14 | → **12** |
| `MerchantSourceMapping` id 17（新建） | 无 | `joybuy_uk:'三星'` → **12**（归一化后的中文别名） |
| `MerchantSourceMapping` id 11 | `joybuy_uk:'Samsung'` → 12 | 不变 |
| `Merchant` 14 | `ACTIVE`、`is_system=true` | `onboarding_status=SUSPENDED`、`suspended_at` 已写、`suspend_reason='已合并到商家 12 Samsung（2026-11-09 数据合并，Offer 161 已迁移）'`；**未删除**，`is_system` 未改 |
| 暂存 `a2df75b8-…`（100859032） | PENDING | **IMPORTED**，`imported_at=2026-11-09 12:01:02Z` |
| 暂存 `8cf5dd6f-…`（100006925022956） | IMPORTED | 幂等重导后仍 **IMPORTED**，`imported_at=2026-11-09 12:01:31Z` |

**重导结果**（Market GB、Currency GBP、locale `en-GB`，取自两条 run 的 job）：

- 100859032：SPU 151 复用（未新建）、SKU 149 复用且规格从空签名 `{}` 单向补全为
  `{"内存": "12GB+512GB", "颜色": "黑色"}`、Offer 159 仍属商家 12；画廊 10 张全部下载成功
  （0 失败），新增 `SpuDetail`（2 个图文区块、1 张规格表、2 组 `spec_options`、AI 摘要）、
  无视频。
- 100006925022956：SPU 153 / SKU 151 / Offer 161 全部复用，SKU 151 规格仍为 `{}`；
  画廊 22 张全部下载成功（0 失败），新增 `SpuDetail`（AI 摘要；无区块/规格表/选项）、无视频。
- 无重复：两条来源身份的 `SpuSourceIdentity` / `SkuSourceIdentity` /
  `OfferSourceIdentity` 各 1 条；库总量前后一致（商家 14、Offer 178、SKU 169、SPU 168；
  映射 12 → 13）。

**后置验证（只读，全部通过）**：

- 商家 14 Offer 数 = **0**；映射指向 14 的数量 = **0**；其余引用扫描（全部模型 FK 到
  `merchant`）为空；商家 14 保留为 SUSPENDED 空壳。
- 商家 12 Offer = **8** 条，全部 DRAFT：154、155、158、159、160、**161**、167、168（按 pk 升序）。注意：执行计划里写的「商家 12 合并后 = 2 条（159、161）」与实际不符——商家 12
  在合并前就有 6 条其它三星商品的 DRAFT Offer（154/155/158/160/167/168，各自不同
  SKU/SPU），合并只是新增第 7 件商品 Offer 161，**没有任何冲突或重复**。
- Offer 161 `merchant=12`、SKU 151、GB/GBP、1149.00、DRAFT、`listed_at=null` 不变；
  `OfferSourceIdentity` 151 仍指向 Offer 161、149 仍指向 Offer 159（未改绑，仅刷新
  `last_seen_at`）；`SkuSourceIdentity` / `SpuSourceIdentity` 同样未改绑。
- 映射：`三星 查看店铺`→12、`三星`→12、`Samsung`→12；无任何映射指向 14。
- SPU 151 与 SPU 153 仍为 **DRAFT**（未激活/未发布），两者均无
  `ProductSearchDocument`（0 条），因此无需刷新搜索文档。
- 快照/脚本（临时、`var/` 已被 gitignore）：`var/merge_20261109/snapshot_before.json`、
  `snapshot_before_extra.json`、`merge_plan.json`、`merge_result.json`、
  `snapshot_after.json`，脚本 `preflight.py` / `snapshot_extra.py` / `media_coverage.py` /
  `merge_merchant14_into_12.py` / `verify_after.py`。
- 命令：
  `./.venv/Scripts/python.exe backend/manage.py shell -c "exec(open(r'var\\merge_20261109\\merge_merchant14_into_12.py', encoding='utf-8').read())"`
  （先以 `MERGE_DRY_RUN=1` 跑过只读断言），随后同一方式运行 `verify_after.py`。
  **按验证纪律仅做了针对性验证**（只读核查 + 执行后核对），未跑测试套件。

**残留与后续**：商家 14 未删除，保留为 `SUSPENDED` 且 0 Offer / 0 映射的空壳，供后续人工
清理或改名复用；它已不会出现在购物端商家搜索（`_searchable_merchants` 要求至少一件
在售商品）。`crawler/debug_crawl.py` 未触碰。**无需重启后端**（纯数据变更、无代码/迁移改动）；
若 Redis 缓存中存在旧商家/商品搜索结果，按 TTL 自然过期即可，两件商品均未上架。


## 10. 变体采集（WP-45 阶段 1，2026-11-15）

背景：PDP「规格无法选择」的根因是数据层缺失——爬虫 1 SPU = 1 SKU 导入，而
`spec_options` 的值指向未导入的源站 SKU id（见 `docs/08` §12b WP-45）。本节记录
变体级数据的调研结论与解析落地；**导入侧多 SKU/Offer 属阶段 2，尚未实现**。

### 10.1 详情 JSON 里的变体级数据（2026-11-15 实抓实测）

抓包样本：iPhone 17 Pro `10404455`（系列 3 值 × 颜色 3 值）、炒锅 `10003152`
（系列 2 值）、变体页 `10405110` / `10003147`；原始 HTML / serverProduct JSON /
完整日志在 `var/wp45_phase1/`（不入库）。

| 位置 | 内容 |
|---|---|
| `productSeriesFloor.series[]` | 每个值 `{name, id, skus[]}`——该值对应的**源 sku id 列表**（系列=兄弟商品口径，见 10.4） |
| `productSelectedFloor.colorSizePartList[]` | 每轴 `C-P#dimension&dimension.dimTitle` + `buttonPartList[]`；每个按钮 `text` / `imgUrl`（s96 规格图）/ `skuList[]`（源 sku id）/ `stockState`（原始码，实测 33/34 都对应可购商品，**语义未解读，只透传**） |
| `productSelectedFloor.skuStatus` | `{源 sku id: 原始状态码}`（实测 "0"/"-2"，与可购性关系未确认，只透传） |
| `productPriceFloor` | **只有当前浏览 sku** 的 `crossOffPrice`/`mainPrice`——单条请求拿不到其它变体的价格 |
| `productCommonFloor.C-M#viewCommonItem&commonCore` | 当前 sku 的 `skuId` / `stockState` / `skuShelvesStockStatus` |

**每个源 sku 都有自己的 `/dp/<sku>` 详情页**（slug 任意均可，实测 `/dp/x/10405110`
返回 200 且 price floor 描述该 sku：1099.00），变体价格 = 逐变体补抓该页并取
`crossOffPrice`（原价优先，与主解析的 2026-11-03 业务规则一致）。

### 10.2 落地（正式链路 + debug_crawl 同步）

- `crawler/joybuy_crawler/parsers/joybuy_uk.py`：
  - `extract_variants(spec_options, floors, *, primary_source_id, currency, primary_price)`
    —— 把 spec_options 轴值按源 sku 组合成 `specification` 名值对 dict，附规格图 /
    `stock_state` / `sku_status` / `is_primary`；主变体继承页面原价（`price_source="detail_page"`）。
  - `extract_variant_price(html)` —— 变体页原价提取（crossOff > main）；`variant_page_url(sku)`
    = `https://www.joybuy.co.uk/dp/x/<sku>`。
  - `UkProduct.variants` 字段；`to_payload()` 的 legacy 顶层与 `joybuy` native 块都带 `variants`。
- `crawler/joybuy_crawler/spiders/joybuy_run.py`：parse_detail → /dg/ 图文合并 →
  **逐变体串行**补抓价格页（`parse_variant_price` / `variant_price_failed` 链式回调），
  队列空了才产出唯一 item；单变体失败只留空价格并继续，结束写
  `VARIANT_PRICES_MERGED` 事件（带成功/失败计数）。
- 开关（`crawler/joybuy_crawler/settings.py`）：`JOYBUY_VARIANT_PRICES_ENABLED`
  （env `CRAWL_VARIANT_PRICES`，默认开）、`JOYBUY_VARIANT_PRICE_LIMIT`
  （env `CRAWL_VARIANT_PRICE_LIMIT`，默认 10/商品，防变体数失控打爆请求预算）。
- `crawler/debug_crawl.py`：`fetch_variant_prices()`（主变体继承页面价，其余逐个
  fetch_html 补抓）、`--no-variant-prices`、日志新增「变体」逐条行、summary 新增
  `variants` / `variant_prices` 计数、`debug_sources.variants` 注明来源。
- **存储无变更**：`StagingProduct.payload` JSONField 整体入库，variants 自动携带；
  质量规则/导入服务按字段读取，不认识 variants 也不破坏（有守门断言）。
  **无模型/迁移变更。**

### 10.3 payload `variants` 契约

```json
[{"source_sku_id": "10404455",
  "specification": {"系列": "256GB", "颜色": "星宇橙色"},
  "price": "1099.00", "currency": "GBP", "price_source": "detail_page",
  "image_url": "https://images4.joy-sourcing.com/product/s96x96_...",
  "stock_state": 34, "sku_status": "-2", "is_primary": true}]
```

- 轴序与 `spec_options` 一致（系列在前、颜色/尺寸在后）；变体按首次出现顺序排列。
- 无规格轴商品 `variants=[]`；老 payload 无 variants 时导入行为完全不变。

### 10.4 阶段 2 必读（边界与红线）

1. **身份冲突红线**：已导入商品的旧单 SKU 身份（指向主变体源 id）**原地升级**
   （补 specification），其余变体新建 SKU + `SkuSourceIdentity`；**不自动重绑**
   已有身份（商家绑定冲突是「冲突不是重复」，见 WP-45 阶段 2 设计注意）。
2. `price_source` 为空的变体不可用 SPU 价格冒充建 Offer。
3. **系列轴的值可能指向源站兄弟商品**（iPhone 1TB 是另一个源商品页）——导入前
   需确认「同源商品」口径（按变体页标题/类目校验或过滤）。
4. 变体 `image_url` 是源站 CDN URL，导入必须走既有本地化下载路径（失败丢弃）。

### 10.5 验证（按验证纪律仅做针对性验证）

```bash
cd backend && ../.venv/Scripts/python.exe manage.py test \
  crawler_control.tests.test_crawler_variants \
  crawler_control.tests.test_crawler_detail_extras --keepdb
# 结果：24 tests OK（新增 Variants 8 例：解析契约/空轴兼容/变体价格页/质量规则
# 透传/蜘蛛链与失败兜底/开关关闭/上限截断；detail_extras 16 例回归，其中蜘蛛
# 流程 2 例已随链式行为更新）

cd backend && ../.venv/Scripts/python.exe manage.py test \
  crawler_control.tests.test_crawler_import \
  crawler_control.tests.test_crawler_quality_gates \
  crawler_control.tests.test_crawler_field_rules \
  crawler_control.tests.test_crawler_rebuild \
  catalog.tests.test_product_detail_api --keepdb
# 结果：113 tests OK

./.venv/Scripts/python.exe -m ruff check <6 个改动文件>          # 全过
./.venv/Scripts/python.exe -m ruff format --check <同上>         # 全过

# 实抓（debug_crawl，零 Django）：
./.venv/Scripts/python.exe crawler/debug_crawl.py --listing-url \
  "https://www.joybuy.co.uk/dp/apple-iphone-17-pro-256-gb/10404455..." \
  --output-dir var/wp45_phase1/debug_run --no-images --no-videos
# iPhone：8 变体、补抓 7 次 0 失败、8 个带价（1TB=1499/512GB=1299/256GB=1099）；
# 炒锅 10003152：2 变体、带价 2 个（24.99 / 30.99）。product.json 与日志留档
# var/wp45_phase1/。
```
