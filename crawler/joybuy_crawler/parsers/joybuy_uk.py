"""Joybuy UK (joybuy.co.uk) parsers — structure version 2 (2026-11-05 rebuild).

Field rule (user requirement #4): every crawled field keeps its Joybuy
source name. The detail payload carries the native block under
``"joybuy"`` (verbatim camelCase source fields) and mirrors the values
into the legacy normalized top-level keys that the staging → quality
gate → import chain consumes.

Price rule (unchanged, HANDOFF 2026-11-03): only ORIGINAL prices are
crawled — the visible original price (``crossOffPrice``) wins over the
discounted ``mainPrice``; ``list_price`` stays None.

Review rule (2026-11-05, user requirement): review *content* is never
crawled. Only the aggregate rating is kept — the 1/2/3/4/5-star counts,
the average score and the total review count — plus the AI-written
summary block ("内容由人工智能总结自用户评价") **when the page renders
one**. A page without the block yields no summary field at all rather
than an empty placeholder.

Category rule (2026-11-05, user requirement): the breadcrumb trail is
cut to the first two category levels after the generic home crumb, so a
product nested five levels deep is recorded as ``一级/二级`` only. The
dropped levels remain available inside the archived raw response if a
deeper mapping is ever needed.

Detail pages are extracted in three tolerant layers (first hit wins):
1. embedded Next.js flight JSON (``self.__next_f`` chunks) — richest;
2. JSON-LD ``Product`` blocks;
3. DOM selectors from docs/11 §6 (breadcrumb, gallery, seller, tabs).

Any layer that fails simply reports missing fields; the quality gates
decide what may still be imported, and risk-control pages are never
parsed (callers must check :func:`joybuy_crawler.render.detect_risk_control`).
"""

import json
import re
from dataclasses import dataclass, field

from parsel import Selector

UK_STRUCTURE_VERSION = 2
UK_PRODUCT_URL_PATTERN = re.compile(r"/dp/[^/]+/(\w+)")

_PRICE_PATTERN = re.compile(r"[-+]?\d+(?:\.\d{1,2})?(?![\d])")

REQUIRED_FIELDS = ("source_id", "title", "currency", "current_price", "skus")

#: How many category levels (after the generic home crumb) are recorded.
BREADCRUMB_DEPTH = 2
#: Joybuy 商品后台类目最多保留的层级数（2026-11-09 口径：厨具餐具/锅具）。
PRODUCT_CATEGORY_DEPTH = 2
#: Breadcrumb labels that are a site root, not a category level.
HOME_CRUMB_LABELS = {"home", "首页", "主页", "首頁"}

#: Labels the page prints above the AI review summary. Used by the DOM
#: fallback to recognise the block; the flight JSON carries it as
#: ``aiSummary`` without any label.
AI_SUMMARY_LABELS = (
    "内容由人工智能总结自用户评价",
    "由人工智能总结自用户评价",
    "人工智能总结",
    "ai-generated summary",
    "ai summary",
    "summarized from customer reviews",
)

#: Star buckets, in the order the source exposes them.
STAR_LEVELS = (1, 2, 3, 4, 5)

#: Joybuy 商品图 CDN：flight 里只给相对路径，主机和 sNNNxNNN 尺寸要自己拼。
IMAGE_CDN_HOST = "images4.joy-sourcing.com"
#: 商品大图尺寸（页面 ``mainMedia_bigImg__`` 用的就是 s1248x1248）。
IMAGE_SIZE_GALLERY = 1248
#: 规格可选值的小图尺寸（``colorSizePartList[].imgUrl``）。
IMAGE_SIZE_SPEC = 96
#: 小于该尺寸的都是服务/保障 icon（s32/s64/s96），不属于商品画廊。
IMAGE_SIZE_MIN_GALLERY = 180
_SIZE_IN_PATH = re.compile(r"/s(\d+)x\d+_")
#: 服务/保障 icon 的路径标记（``jfsintlpro-000-com``）。
SERVICE_ICON_MARKER = "-000-com"

#: 移动端 / 图文详情页模板。www 与 m. 两个域名返回同一份 SSR，但
#: ``m.joybuy.co.uk/robots.txt`` 明确 ``Disallow: /dg/``，www 站没有这条限制，
#: 所以正式链路只请求 www（2026-11-09 实测，见 docs/14 §7.4）。
MOBILE_DETAIL_URL_TEMPLATE = "https://www.joybuy.co.uk/dg/{source_id}"

#: 这些折叠区块是规格参数，不进 description 正文；表格单独保存在
#: ``specification_tables``（Joybuy 上是两列表格，见 docs/14 §7.6）。
SPEC_SECTION_TITLES = {"规格参数", "材质与规格", "技术规格"}

#: 店铺卡片上卖家名旁边的界面后缀（不是店铺名）。中文站显示
#: 「三星 查看店铺」，英文站显示「Samsung View store」；旧实现只去掉英文，
#: 导致同一卖家在中英文下被识别成两个商家（见 docs/14 §10）。
SELLER_UI_SUFFIXES = (
    "查看店铺",
    "进入店铺",
    "查看商店",
    "进入商店",
    "View store",
    "Visit store",
    "View shop",
    "Visit shop",
)


def normalize_seller_name(raw: str) -> str:
    """去掉卖家名里的界面后缀与多余空白/标点。

    卖家身份目前按名称映射（``MerchantSourceMapping``），名称里的本地化
    UI 文案会直接污染身份键。这里只做保守清洗：大小写不敏感地剥掉已知
    后缀、压缩空白、去掉首尾分隔标点；其它字符一律保留，避免把真实店铺名
    改坏（例如「Samsung 官方店」保持不变）。
    """

    name = " ".join(str(raw or "").replace("\u00a0", " ").split())
    stripped = True
    while stripped and name:
        stripped = False
        for suffix in SELLER_UI_SUFFIXES:
            folded = name.casefold()
            target = suffix.casefold()
            if folded.endswith(target):
                name = name[: len(name) - len(target)].strip()
                stripped = True
            elif folded.startswith(target):
                name = name[len(target) :].strip()
                stripped = True
    return name.strip(" |·/,-—")


@dataclass
class UkListingEntry:
    source_url: str
    rank: int
    title: str
    original_price: str | None = None
    image_url: str = ""


@dataclass
class UkProduct:
    """Parsed product detail with Joybuy-native fields preserved."""

    source_id: str
    title: str
    currency: str
    current_price: str | None  # original price (crossOffPrice rule)
    list_price: str | None  # always None: the discount is never kept
    main_price: str | None  # the discounted display price, kept verbatim
    promotion_label: str
    availability: str
    brand: str
    breadcrumbs: list[dict]
    skus: list[dict]
    gallery: list[str]
    description: str
    detail_images: list[str]
    seller_name: str
    seller_url: str
    rating_average: str | None
    rating_count: int | None
    source_url: str
    #: Star counts keyed "1".."5" (review *content* is never crawled).
    rating_distribution: dict[str, int] = field(default_factory=dict)
    #: Where the rating came from: ``flight`` (page JSON) or ``dom``.
    rating_source: str = ""
    #: AI-written review summary text; empty when the page has no block.
    ai_summary: str = ""
    #: Heading the page prints above the summary, e.g.
    #: "内容由人工智能总结自用户评价".
    ai_summary_title: str = ""
    #: AI review tags ("aiTagList"), empty when absent.
    ai_summary_tags: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    #: 商品后台类目路径（最多两级）：[{"id": "288", "name": "厨具餐具", "depth": 0}, ...]
    product_category_path: list[dict] = field(default_factory=list)
    #: 规格可选值：[{name, values: [{value, image_url, sku_ids}]}]
    spec_options: list[dict] = field(default_factory=list)
    #: 图文详情区块（含子标题层级）：
    #: [{title, blocks: [{type: "heading"|"paragraph", text}], text, images}]
    content_sections: list[dict] = field(default_factory=list)
    #: 规格参数（平铺）：[{group, name, value}]
    specifications: list[dict] = field(default_factory=list)
    #: 规格参数表格：[{title, columns: ["属性", "值"], rows: [{name, value}]}]
    specification_tables: list[dict] = field(default_factory=list)
    #: 画廊视频：[{url, duration, cover, video_id}]
    videos: list[dict] = field(default_factory=list)
    #: 变体列表（WP-45 阶段 1）：每规格组合一条，见 ``extract_variants``。
    #: 没有规格轴的商品为空列表 —— 旧 payload 没有 variants 时导入行为不变。
    variants: list[dict] = field(default_factory=list)

    def to_payload(self) -> dict:
        """Joybuy-native block + legacy staging keys in one payload."""

        native = {
            "productId": self.source_id,
            "title": self.title,
            "brand": self.brand,
            "breadcrumbs": self.breadcrumbs,
            "priceInfo": {
                "currency": self.currency,
                "crossOffPrice": self.current_price,
                "mainPrice": self.main_price,
            },
            "skus": [
                {
                    "skuId": sku["source_id"],
                    "price": sku["price"],
                    "availability": sku["availability"],
                    "specs": sku["specs"],
                }
                for sku in self.skus
            ],
            "gallery": self.gallery,
            "description": self.description,
            "detailImages": self.detail_images,
            "specOptions": self.spec_options,
            "variants": self.variants,
            "specifications": self.specifications,
            "specificationTables": self.specification_tables,
            "contentSections": self.content_sections,
            "videos": self.videos,
            "seller": {"name": self.seller_name, "storeUrl": self.seller_url},
            "rating": {
                "average": self.rating_average,
                "count": self.rating_count,
                "distribution": self.rating_distribution,
            },
            "promotionLabel": self.promotion_label,
            "availability": self.availability,
            "sourceUrl": self.source_url,
            "productCategoryPath": self.product_category_path,
        }
        # The AI summary block only exists when the page rendered one.
        if self.ai_summary:
            native["aiReviewSummary"] = {
                "title": self.ai_summary_title,
                "text": self.ai_summary,
                "tags": self.ai_summary_tags,
            }
        return {
            "joybuy": native,
            "source_id": self.source_id,
            "title": self.title,
            "currency": self.currency,
            "current_price": self.current_price,
            "list_price": self.list_price,
            "promotion_label": self.promotion_label,
            "availability": self.availability,
            "brand": self.brand,
            "source_category_id": (self.breadcrumbs or [{}])[-1].get("cid", ""),
            "source_seller_id": self.seller_name,
            "source_seller_name": self.seller_name,
            "description": self.description,
            "rating_count": self.rating_count,
            "rating_average": self.rating_average,
            "rating_distribution": self.rating_distribution,
            "rating_source": self.rating_source,
            "ai_summary": self.ai_summary,
            "ai_summary_title": self.ai_summary_title,
            "ai_summary_tags": self.ai_summary_tags,
            "skus": self.skus,
            "spec_options": self.spec_options,
            "variants": self.variants,
            "specifications": self.specifications,
            "specification_tables": self.specification_tables,
            "content_sections": self.content_sections,
            "videos": self.videos,
            "video_urls": [video.get("url", "") for video in self.videos],
            "image_urls": self.gallery,
            "detail_image_urls": self.detail_images,
            "missing_fields": self.missing_fields,
            "product_category_path": self.product_category_path,
            "product_category_id": (
                str(self.product_category_path[-1].get("id") or "")
                if self.product_category_path
                else ""
            ),
        }


def _price(raw: str | None) -> str | None:
    if not raw:
        return None
    text = raw.replace(",", "")
    # The listing cards render a price as several text nodes ("£ 32 . 33"),
    # so a plain regex would stop at "32". Join decimals first.
    text = re.sub(r"(?<=\d)\s*\.\s*(?=\d)", ".", text)
    match = _PRICE_PATTERN.search(text)
    return match.group(0) if match else None


_FLIGHT_CHUNK = re.compile(r"self\.__next_f\.push\(\[1,\"(.*?)\"\]\)", re.DOTALL)
#: One JSON value as it appears after ``"key":`` — object, array, string or scalar.
_FLIGHT_VALUE = (
    r'(\{[^{}]*\}|\[[^\[\]]*\]|"(?:[^"\\]|\\.)*"|null|true|false|-?\d+(?:\.\d+)?)'
)


def _flight_text(html: str) -> str:
    """Decode every ``self.__next_f`` chunk into one searchable string.

    Next.js serialises the server payload into JS string literals, so the
    embedded JSON arrives escaped (``\\"``). Decoding through ``json``
    keeps multi-byte text intact, which a ``unicode_escape`` round-trip
    would mangle.
    """

    parts = []
    for match in _FLIGHT_CHUNK.finditer(html):
        raw = match.group(1)
        try:
            parts.append(json.loads(f'"{raw}"'))
        except json.JSONDecodeError:
            parts.append(
                raw.encode("utf-8", "ignore").decode("unicode_escape", errors="ignore")
            )
    return "\n".join(parts)


def _flight_ref(text: str, value):
    """Follow a Next.js dedupe reference (``"$19c"``) to its slot value.

    The flight stream replaces repeated objects with ``<id>:<value>``
    slots and points at them with ``"$<id>"``, so the rating block is
    usually one hop away from where it is referenced.
    """

    seen = set()
    while isinstance(value, str) and value.startswith("$") and len(value) > 1:
        reference = value[1:]
        if reference in seen:
            return None
        seen.add(reference)
        slot = re.search(rf'(?<![\w"])({re.escape(reference)}):{_FLIGHT_VALUE}', text)
        if not slot:
            return None
        try:
            value = json.loads(slot.group(2))
        except json.JSONDecodeError:
            return None
    return value


def _resolve_flight_slot(text: str, ref: str, depth: int = 0):
    """Follow a ``"$7c"`` slot reference with ``raw_decode``.

    ``_flight_ref`` matches the slot with a flat-value regex, which cannot
    follow a nested object (the inline ``aiSummary`` block is one). This
    variant decodes the slot value structurally instead.
    """

    if depth > 10:
        return None
    slot = str(ref).lstrip("$")
    match = re.search(rf"(?m)^{re.escape(slot)}:", text)
    if not match:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(text[match.end() :].lstrip())
    except json.JSONDecodeError:
        return None
    if isinstance(value, str) and value.startswith("$"):
        return _resolve_flight_slot(text, value, depth + 1)
    return value


def _json_after(text: str, key: str):
    """Read the JSON value printed after ``"key":``; follow ``"$ref"`` hops."""

    marker = f'"{key}":'
    idx = text.find(marker)
    if idx < 0:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(text[idx + len(marker) :].lstrip())
    except json.JSONDecodeError:
        return None
    if isinstance(value, str) and value.startswith("$"):
        return _resolve_flight_slot(text, value)
    return value


def _resolve_flight_refs(obj, text: str, depth: int = 0):
    """Recursively resolve every ``"$ref"`` inside one decoded flight value."""

    if depth > 10:
        return obj
    if isinstance(obj, str) and obj.startswith("$"):
        return _resolve_flight_refs(_resolve_flight_slot(text, obj), text, depth + 1)
    if isinstance(obj, list):
        return [_resolve_flight_refs(item, text, depth + 1) for item in obj]
    if isinstance(obj, dict):
        return {
            key: _resolve_flight_refs(value, text, depth + 1)
            for key, value in obj.items()
        }
    return obj


def _decode_server_product(html: str, *, text: str | None = None) -> dict:
    """Decode ``"serverProduct":`` out of the flight stream (``{}`` if absent)."""

    flight_text = _flight_text(html) if text is None else text
    idx = flight_text.find('"serverProduct":')
    if idx < 0:
        return {}
    start = flight_text.find("{", idx)
    if start < 0:
        return {}
    try:
        product, _ = json.JSONDecoder().raw_decode(flight_text[start:])
    except json.JSONDecodeError:
        return {}
    return product if isinstance(product, dict) else {}


def _floors_by_id(product_data: dict) -> dict[str, dict]:
    """``serverProduct.data.floors`` -> ``{floorId: data}`` (later wins)."""

    floors = {}
    for floor in (product_data.get("data") or {}).get("floors") or []:
        if not isinstance(floor, dict):
            continue
        floor_id = str(floor.get("floorId") or "")
        if floor_id:
            floors[floor_id] = floor.get("data") or {}
    return floors


def product_image_url(path: str, size: int = IMAGE_SIZE_GALLERY) -> str:
    """flight 图片路径 -> CDN 绝对地址（可指定 sNNNxNNN 尺寸）。

    Absolute URLs keep their own host (product galleries live on
    ``images1/3/4``); only the size token is rewritten.
    """

    raw = str(path or "").strip()
    if not raw:
        return ""
    if raw.startswith("//"):
        raw = f"https:{raw}"
    if raw.startswith("http"):
        return _SIZE_IN_PATH.sub(f"/s{size}x{size}_", raw, count=1)
    raw = raw.lstrip("/").removeprefix("product/")
    raw = re.sub(r"^s\d+x\d+_", "", raw)
    url = f"https://{IMAGE_CDN_HOST}/product/s{size}x{size}_{raw}"
    if url.endswith(".jpg"):
        url += "!q70.webp"
    return url


def normalize_gallery_url(url: str, *, size: int = IMAGE_SIZE_GALLERY) -> str:
    """把任意尺寸的商品图 URL 统一成 s1248 大图（保留原主机）。"""

    url = str(url or "").strip()
    if not url:
        return ""
    if url.startswith("//"):
        url = f"https:{url}"
    match = _SIZE_IN_PATH.search(url)
    if match:
        return _SIZE_IN_PATH.sub(f"/s{size}x{size}_", url, count=1)
    head, separator, tail = url.partition("/product/")
    if separator and tail and not tail.startswith(("s", "/")):
        return f"{head}/product/s{size}x{size}_{tail}"
    return url


def clean_gallery(urls: list[str]) -> list[str]:
    """只保留商品大图。

    Filters (2026-11-08/09 live measurements):

    * service/benefit icons live under ``.../jfsintlpro-000-com/`` at
      s32/s64/s96 and must be dropped — they used to be gallery entries 3~6;
    * spec thumbnails are s96 and are not gallery images either;
    * one product image is served at s598/s1248/s180, so dedupe on the path
      with the size token stripped and normalise every hit to s1248.
    """

    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in urls or []:
        original = f"https:{raw}" if str(raw).startswith("//") else str(raw or "")
        if "joy-sourcing.com" not in original or "/product/" not in original:
            continue
        if SERVICE_ICON_MARKER in original:
            continue
        size_match = _SIZE_IN_PATH.search(original)
        if size_match and int(size_match.group(1)) < IMAGE_SIZE_MIN_GALLERY:
            continue
        url = normalize_gallery_url(original)
        # Dedupe on the image path only: the same file is served from
        # images1/3/4, at several sizes (s598/s1248/s180) and with/without
        # the ``!q70.webp`` rendering suffix.
        path = url.partition("/product/")[2] or url
        key = _SIZE_IN_PATH.sub("/s_", path.split("!")[0])
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(url)
    return cleaned


def extract_flight_gallery(floors: dict) -> list[str]:
    """商品画廊：``productMainImageFloor.mediaData`` 自带全部大图。

    The DOM only exposes the currently selected ``bigImg`` plus s128
    thumbnails, which is why the crawl used to record one big image and
    four icons; the flight payload lists every media item at s1248.
    """

    data = floors.get("productMainImageFloor") or {}
    urls: list[str] = []
    for media in data.get("mediaData") or []:
        if not isinstance(media, dict):
            continue
        if media.get("image") is False:
            continue
        path = media.get("bigImageUrl") or media.get("imageUrl")
        if path:
            urls.append(product_image_url(path, IMAGE_SIZE_GALLERY))
    if not urls:
        for part in data.get("imagePartList") or []:
            if not isinstance(part, dict):
                continue
            core = part.get("C-P#image&image") or {}
            paths = [core.get("bigImageUrl") or core.get("imageUrl")]
            paths.extend(core.get("supplementaryImageList") or [])
            for path in paths:
                if path:
                    urls.append(product_image_url(path, IMAGE_SIZE_GALLERY))
    return clean_gallery(urls)


def extract_spec_options(floors: dict) -> list[dict]:
    """规格可选值：``productSeriesFloor.series`` + ``colorSizePartList``。

    Returns ``[{name, values: [{value, image_url, sku_ids}]}]``. Joybuy
    splits variants across two floors: the series/capacity dimension lives
    in ``productSeriesFloor`` (each value carries its ``skus``), colours and
    sizes in ``productSelectedFloor.colorSizePartList`` (spec image at s96).
    Series comes first, matching the order the page renders.
    """

    options: list[dict] = []

    series_floor = floors.get("productSeriesFloor") or {}
    series_title = str(series_floor.get("title") or "系列").strip()
    series_values = []
    for item in series_floor.get("series") or []:
        if not isinstance(item, dict):
            continue
        value = str(item.get("name") or "").strip()
        if not value:
            continue
        series_values.append(
            {
                "value": value,
                "image_url": "",
                "sku_ids": [str(sku) for sku in item.get("skus") or []],
            }
        )
    if series_title and series_values:
        options.append({"name": series_title, "values": series_values})

    selected = floors.get("productSelectedFloor") or {}
    for group in selected.get("colorSizePartList") or []:
        if not isinstance(group, dict):
            continue
        dimension = group.get("C-P#dimension&dimension") or {}
        name = str(dimension.get("dimTitle") or "").strip()
        values = []
        for part in group.get("buttonPartList") or []:
            button = (part or {}).get("C-P#dimensionButton&dimensionButton") or {}
            value = str(button.get("text") or "").strip()
            if not value:
                continue
            image_path = str(button.get("imgUrl") or "").strip()
            values.append(
                {
                    "value": value,
                    "image_url": (
                        product_image_url(image_path, IMAGE_SIZE_SPEC)
                        if image_path
                        else ""
                    ),
                    "sku_ids": [str(item) for item in button.get("skuList") or []],
                }
            )
        if name and values:
            options.append({"name": name, "values": values})
    return options


def sku_specs_from_options(options: list[dict]) -> dict[str, list[dict]]:
    """``sku_id -> [{name, value}]`` used to fill ``skus[].specs``."""

    mapping: dict[str, list[dict]] = {}
    for option in options:
        for value in option.get("values") or []:
            for sku_id in value.get("sku_ids") or []:
                mapping.setdefault(str(sku_id), []).append(
                    {"name": option["name"], "value": value["value"]}
                )
    return mapping


#: Every source sku has its own ``/dp/`` detail page (verified live on
#: 2026-11-15 with 10405110 / 10003147); the slug is ignored by the site, so
#: a constant placeholder keeps the URL valid without the product title.
VARIANT_DETAIL_URL_TEMPLATE = "https://www.joybuy.co.uk/dp/x/{source_sku_id}"


def variant_page_url(source_sku_id: str) -> str:
    """The ``/dp/`` detail page of one variant (used to fetch its price)."""

    return VARIANT_DETAIL_URL_TEMPLATE.format(source_sku_id=str(source_sku_id).strip())


def extract_variants(
    spec_options: list[dict],
    floors: dict,
    *,
    primary_source_id: str,
    currency: str = "",
    primary_price: str | None = None,
) -> list[dict]:
    """Variant list assembled from the spec axes (WP-45 phase 1).

    One detail request yields these variant-level facts (live-verified
    2026-11-15, iPhone 10404455 / wok 10003152):

    * ``productSeriesFloor.series[].skus`` and ``colorSizePartList[]
      .buttonPartList[].skuList`` map every spec value to its source sku ids;
    * colour/size buttons carry the s96x96 swatch (``imgUrl``) and a raw
      ``stockState`` code (33/34 both seen on purchasable items — passed
      through verbatim, never interpreted);
    * ``productSelectedFloor.skuStatus`` is a raw per-source-sku status map
      (also passed through verbatim).

    The price floor only describes the *currently browsed* sku, so non-
    primary variants get ``price=None`` here; callers enrich them one
    ``/dp/<sku>`` request at a time via :func:`extract_variant_price`
    (capped and switchable, see WP-45). The primary variant inherits the
    page price (``primary_price``) with ``price_source="detail_page"``.

    Returns ``[{source_sku_id, specification: {axis: value}, price, currency,
    image_url, stock_state, sku_status, is_primary, price_source}]`` in
    first-appearance order (series axes come before colour/size, matching
    ``spec_options``). Empty when the product has no spec axes — payloads
    without ``variants`` keep importing exactly as before (backward compat).
    """

    selected = floors.get("productSelectedFloor") or {}
    stock_state_by_sku: dict[str, object] = {}
    for group in selected.get("colorSizePartList") or []:
        if not isinstance(group, dict):
            continue
        for part in group.get("buttonPartList") or []:
            button = (part or {}).get("C-P#dimensionButton&dimensionButton") or {}
            stock_state = button.get("stockState")
            for sku_id in button.get("skuList") or []:
                stock_state_by_sku.setdefault(str(sku_id), stock_state)
    sku_status_map = selected.get("skuStatus") or {}

    specification_by_sku: dict[str, dict[str, str]] = {}
    image_by_sku: dict[str, str] = {}
    order: list[str] = []
    for option in spec_options or []:
        axis_name = str(option.get("name") or "").strip()
        if not axis_name:
            continue
        for value in option.get("values") or []:
            value_text = str(value.get("value") or "").strip()
            image_url = str(value.get("image_url") or "").strip()
            for raw_sku in value.get("sku_ids") or []:
                sku_id = str(raw_sku).strip()
                if not sku_id:
                    continue
                if sku_id not in specification_by_sku:
                    specification_by_sku[sku_id] = {}
                    order.append(sku_id)
                specification_by_sku[sku_id].setdefault(axis_name, value_text)
                if image_url:
                    image_by_sku.setdefault(sku_id, image_url)

    primary = str(primary_source_id or "").strip()
    variants = []
    for sku_id in order:
        is_primary = sku_id == primary
        price = None
        price_source = ""
        if is_primary and primary_price:
            price = primary_price
            price_source = "detail_page"
        variants.append(
            {
                "source_sku_id": sku_id,
                "specification": dict(specification_by_sku[sku_id]),
                "price": price,
                "currency": str(currency or ""),
                "image_url": image_by_sku.get(sku_id, ""),
                "stock_state": stock_state_by_sku.get(sku_id),
                "sku_status": sku_status_map.get(sku_id),
                "is_primary": is_primary,
                "price_source": price_source,
            }
        )
    return variants


def extract_variant_price(html: str) -> str | None:
    """The original price on one variant's own ``/dp/`` page.

    Same business rule as the main detail parse (2026-11-03): the crossed-off
    original wins over the discounted display price. Returns ``None`` when
    the page carries no usable price floor (risk-control page, layout change).
    """

    floors = _floors_by_id(_decode_server_product(html))
    price_floor = floors.get("productPriceFloor") or {}
    return _price(price_floor.get("crossOffPrice")) or _price(
        price_floor.get("mainPrice")
    )


def extract_videos(floors: dict) -> list[dict]:
    """画廊视频：``productMainImageFloor.mediaData`` 里 mediaType=2 的项。"""

    data = floors.get("productMainImageFloor") or {}
    videos = []
    for media in data.get("mediaData") or []:
        if not isinstance(media, dict):
            continue
        if not (media.get("video") or str(media.get("mediaType")) == "2"):
            continue
        url = str(media.get("videoUrl") or media.get("playUrl") or "").strip()
        if not url:
            continue
        videos.append(
            {
                "url": url,
                "duration": media.get("duration"),
                "cover": str(media.get("coverImageUrl") or media.get("coverUrl") or ""),
                "video_id": str(media.get("videoId") or ""),
            }
        )
    return videos


def extract_ai_summary(text: str) -> dict:
    """AI 评价摘要：内联 ``aiSummary{summaryContent, summaryText}`` + 标签。

    The block is either an object (measured 2026-11-09) or a ``$ref``
    slot. Tags live beside it in ``aiTagList[].tagName``. Nothing is
    invented when the page has no block.
    """

    empty = {"summary": "", "title": "", "tags": []}
    idx = text.find('"aiSummary":')
    if idx < 0:
        return empty
    value = _json_after(text, "aiSummary")
    value = _resolve_flight_refs(value, text) if value is not None else None
    if not isinstance(value, dict):
        return empty

    summary = str(value.get("summaryContent") or value.get("summary") or "").strip()
    if not summary:
        return empty
    title = str(value.get("summaryText") or "").strip() or AI_SUMMARY_LABELS[0]
    tags = []
    tag_list = _json_after(text, "aiTagList")
    if isinstance(tag_list, list):
        for item in tag_list:
            if isinstance(item, dict):
                tag_name = str(item.get("tagName") or "").strip()
                if tag_name:
                    tags.append(tag_name)
    deduped = []
    for tag in tags:
        if tag not in deduped:
            deduped.append(tag)
    return {"summary": summary, "title": title, "tags": deduped}


def _decode_nested_json_object(text: str, anchor: str) -> dict:
    """从 flight 文本里锚定 ``anchor``（如 ``'"ratingInfo":'``）后解出该对象。

    RSC 改版（2026-11-16）后这些块都嵌套在更大的对象里，靠「扁平花括号对」
    反查会失败；锚点之后的第一个 ``{`` 起做 ``raw_decode`` 才是稳的解。
    """

    if not text or not anchor:
        return {}
    idx = text.find(anchor)
    if idx < 0:
        return {}
    start = text.find("{", idx + len(anchor) - 1)
    if start < 0:
        return {}
    try:
        value, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _extract_flight_review(html: str, *, text: str | None = None) -> dict:
    """Aggregate rating + AI summary from the embedded flight JSON.

    The review block is a flat object that carries ``ratingInfo`` as a
    reference; anchoring on ``"ratingInfo"`` inside a brace pair avoids
    picking up the unrelated i18n strings that also mention ``aiSummary``.
    """

    text = _flight_text(html) if text is None else text
    if not text:
        return {}
    container = re.search(r'\{[^{}]*"ratingInfo"[^{}]*\}', text)
    block = {}
    if container:
        try:
            block = json.loads(container.group(0))
        except json.JSONDecodeError:
            block = {}
    rating_info = _flight_ref(text, block.get("ratingInfo")) or {}
    if not isinstance(rating_info, dict):
        rating_info = {}
    if not rating_info:
        # 2026-11-16: /dp/ 详情页改成 RSC 流后，``ratingInfo`` 不再是扁平花括号
        # 对象里的值（上面的 ``\{[^{}]*"ratingInfo"[^{}]*\}`` 锚点匹配不到），
        # 而是嵌套在更大的对象里。直接锚定键名再 raw_decode 才能解出——分桶
        # ``score1..5Count``、``commentCount``、``averageScore`` 都在其中
        # （实测 /dp/x/100020670022401：commentCount=49、bucket 合计 49）。
        rating_info = _decode_nested_json_object(text, '"ratingInfo":')

    distribution = {}
    for level in STAR_LEVELS:
        raw = rating_info.get(f"score{level}Count")
        try:
            distribution[str(level)] = int(raw) if raw is not None else 0
        except (TypeError, ValueError):
            distribution[str(level)] = 0

    count = block.get("totalCommentCount")
    if count is None:
        count = rating_info.get("commentCount")
    try:
        count = int(count) if count is not None else None
    except (TypeError, ValueError):
        count = None

    # ``star`` is the displayed product rating; ``averageScore`` defaults
    # to 5 on products with no reviews, so it is only trusted when there
    # is at least one review to average.
    average = None
    for candidate in (block.get("star"), block.get("starShow")):
        if candidate in (None, "", "0", "0.0"):
            continue
        if _price(str(candidate)):
            average = _price(str(candidate))
            break
    if average is None and count:
        average = _price(str(rating_info.get("averageScore") or ""))

    summary = block.get("aiSummary")
    summary = summary.strip() if isinstance(summary, str) else ""
    tags = _flight_ref(text, block.get("aiTagList"))
    tags = (
        [str(tag).strip() for tag in tags if str(tag).strip()]
        if isinstance(tags, list)
        else []
    )
    title = block.get("aiTagTitle")
    title = title.strip() if isinstance(title, str) else ""
    if not summary:
        # 2026-11-16 RSC 改版：aiSummary 块同样不在扁平容器里，用专用函数
        # 直接锚定 ``"aiSummary":`` 解出（同 /dp/ 页实测有摘要）。
        inline = extract_ai_summary(text)
        if inline.get("summary"):
            summary = inline["summary"]
            title = title or str(inline.get("title") or "").strip()
            tags = tags or list(inline.get("tags") or [])

    has_data = bool(rating_info) or count is not None or bool(summary)
    if not has_data:
        return {}
    return {
        "average": average,
        "count": count,
        "distribution": distribution if rating_info else {},
        "summary": summary,
        "summary_title": title,
        "summary_tags": tags,
        "source": "flight",
    }


def _extract_dom_review(selector) -> dict:
    """Fallback: read the AI summary block straight out of the DOM.

    Only the summary is attempted here. The star counts live in a
    canvas/bar widget whose text is not reliably present in the rendered
    HTML, so a DOM guess would invent numbers — better to report nothing
    than a wrong distribution.
    """

    for node in selector.css(
        '[class*="aiSummary"], [class*="ai-summary"], [class*="summaryContent"]'
    ):
        text = " ".join(" ".join(node.css("::text").getall()).split())
        for label in AI_SUMMARY_LABELS:
            if text.casefold().startswith(label.casefold()):
                text = text[len(label) :].strip(" :：")
        if len(text) >= 20:
            return {
                "average": None,
                "count": None,
                "distribution": {},
                "summary": text,
                "summary_title": "",
                "summary_tags": [],
                "source": "dom",
            }
    return {}


def _extract_flight_product(html: str, *, text: str | None = None) -> dict | None:
    """Search Next.js flight chunks for an embedded product JSON object."""

    text = _flight_text(html) if text is None else text
    if not text:
        return None
    for json_match in re.finditer(r"\{[^{}]*\"crossOffPrice\"[^{}]*\}", text):
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            continue
    return None


def _extract_flight_product_categories(
    html: str, *, text: str | None = None
) -> list[dict]:
    """Joybuy 商品后台类目（面包屑来源），最多保留两级。

    flight 结构::

        productBreadCrumbFloor.data["C-M#viewBreadCrumbItem&core"].categories
        = [{"name": "厨具餐具", "id": "288"}, {"name": "锅具", "id": "361"},
           {"name": "炒锅", "id": "372"}]

    第三级（炒锅）按 2026-11-09 口径丢弃；商品名称不是类目，不在 categories 里。
    """

    text = _flight_text(html) if text is None else text
    product = _decode_server_product(html, text=text)
    floors = (product.get("data") or {}).get("floors") or []
    for floor in floors:
        if not isinstance(floor, dict):
            continue
        if floor.get("floorId") != "productBreadCrumbFloor":
            continue
        core = (floor.get("data") or {}).get("C-M#viewBreadCrumbItem&core") or {}
        categories = core.get("categories") or []
        if not isinstance(categories, list):
            return []
        path = []
        for item in categories[:PRODUCT_CATEGORY_DEPTH]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            cid = str(item.get("id") or "").strip()
            if name:
                path.append({"id": cid, "name": name})
        return path
    return []


def _parse_json_ld(selector) -> dict:
    for block in selector.xpath(
        '//script[@type="application/ld+json"]/text()'
    ).getall():
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            json_type = item.get("@type")
            types = json_type if isinstance(json_type, list) else [json_type]
            if "Product" in types:
                return item
    return {}


def truncate_breadcrumbs(
    crumbs: list[dict], depth: int = BREADCRUMB_DEPTH
) -> list[dict]:
    """Keep only the first ``depth`` category levels after the home crumb.

    ``首页 / 母婴用品 / 健康护理 / 湿巾及配件 / 湿巾 / 商品`` becomes
    ``母婴用品 / 健康护理`` — the deeper levels are meaningful on the
    source site but only add noise to our own two-level catalog.
    """

    kept = [crumb for crumb in (crumbs or []) if (crumb.get("name") or "").strip()]
    if kept and kept[0]["name"].strip().casefold() in HOME_CRUMB_LABELS:
        kept = kept[1:]
    return kept[:depth]


def _rating_from_dom(selector, html: str = "") -> tuple[str | None, int | None]:
    """Last-resort rating read from the visible rating chip.

    Only used when the page JSON carried no ``ratingInfo``; the first
    number in the rating block is the average, the second the count.
    """

    average = None
    count = None
    for part in selector.css('[class*="rating"] ::text').getall():
        number = _price(part)
        if number is None:
            continue
        if average is None:
            average = number
        elif count is None:
            count = int(float(number))
    if average is None and html:
        # "rated 4.8 out of 5 based on 6 reviews"
        match = re.search(
            r"rated ([\d.]+) out of 5.*?([\d,]+)\s+reviews", html[:60000], re.IGNORECASE
        )
        if match:
            average = match.group(1)
            count = int(match.group(2).replace(",", ""))
    return average, count


def _absolute_url(href: str) -> str:
    if href.startswith("//"):
        return f"https:{href}"
    if href.startswith("/"):
        return f"https://www.joybuy.co.uk{href}"
    return href


def _image_url(src: str) -> str:
    if src.startswith("//"):
        return f"https:{src}"
    return src if src.startswith("http") else ""


def _text(node) -> str:
    return " ".join(" ".join(node.css("::text").getall()).split())


# ---------------------------------------------------------------------------
# 图文详情（子标题 + 正文 + 图片）与规格参数表格
# ---------------------------------------------------------------------------


def _image_from_src(src: str) -> str:
    """协议相对 / 绝对图片地址 -> 绝对地址；其它返回空串。"""

    src = (src or "").strip()
    if src.startswith("//"):
        return f"https:{src}"
    if src.startswith("http"):
        return src
    return ""


def _dedupe_images(values: list[str]) -> list[str]:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _blocks_text(blocks: list[dict]) -> str:
    return "\n".join(block["text"] for block in blocks if block.get("text"))


def _append_dom_block(node, blocks: list[dict]) -> None:
    """One DOM paragraph -> heading + paragraph blocks.

    Joybuy's rich text marks subheadings with ``<strong>``/``<b>`` (the page
    renders them larger and bolder, e.g. 「1.8L 小巧容量」「安全提醒：」);
    the rest of the same paragraph is body text.
    """

    full = _text(node)
    if not full:
        return
    strong = node.css("strong, b")
    if strong:
        heading = _text(strong[0])
        if heading:
            blocks.append({"type": "heading", "text": heading})
            remainder = full
            if remainder.startswith(heading):
                remainder = remainder[len(heading) :]
            else:
                remainder = remainder.replace(heading, "", 1)
            remainder = remainder.strip(" ：:.-")
            if remainder:
                blocks.append({"type": "paragraph", "text": remainder})
            return
    blocks.append({"type": "paragraph", "text": full})


def extract_dom_sections(selector) -> list[dict]:
    """PC 端所有折叠区块：标题 + 子标题/正文块 + 图片。

    The accordion titles differ per product (商品描述/重要信息/核心卖点与优势/
    产品详情/主要特点与优势/设置使用与兼容性…), so every accordion is kept
    under its own title. Spec sections (规格参数…) are client-rendered on PC
    and arrive empty here; the mobile page supplies them.
    """

    sections = []
    for accordion in selector.css('[class*="MuiAccordion-root"]'):
        title = " ".join(
            accordion.css('[class*="Accordion_title"] ::text').getall()
        ).strip()
        details = accordion.css('[class*="MuiAccordionDetails"]')
        if not title or not details:
            continue
        container = details.css('[aria-label="rich text container"]')
        root = container[0] if container else details[0]
        blocks: list[dict] = []
        nodes = root.xpath(
            ".//li | .//p[not(ancestor::li)] | "
            ".//h1[not(ancestor::li)] | .//h2[not(ancestor::li)] | "
            ".//h3[not(ancestor::li)] | .//h4[not(ancestor::li)] | "
            ".//h5[not(ancestor::li)] | .//h6[not(ancestor::li)]"
        )
        for node in nodes:
            _append_dom_block(node, blocks)
        if not blocks:
            text = _text(root)
            if text:
                blocks.append({"type": "paragraph", "text": text})
        images = _dedupe_images(
            [
                _image_from_src(src)
                for src in details.css("img::attr(src), img::attr(data-src)").getall()
            ]
        )
        sections.append(
            {
                "title": title,
                "blocks": blocks,
                "text": _blocks_text(blocks),
                "images": images,
            }
        )
    return sections


def _collect_blocks(node, blocks: list[dict], images: list[str]) -> None:
    """从 ``structuredFloors.modules`` 收集子标题/正文块和图片。

    Each ``moduleData`` item is one content group: a non-empty ``title`` is
    a subheading (bold/larger on the page), ``text`` is the paragraph. The
    order and the block type must survive — flattening them loses the
    hierarchy the storefront has to render (docs/14 §7.7).
    """

    if isinstance(node, dict):
        title = node.get("title")
        text = node.get("text")
        if isinstance(title, str):
            clean = title.strip()
            if clean and clean not in {"TEXT", "TEXT_AREA"}:
                blocks.append({"type": "heading", "text": clean})
        if isinstance(text, str):
            clean = text.strip()
            if clean and clean not in {"TEXT", "TEXT_AREA"}:
                blocks.append({"type": "paragraph", "text": clean})
        for key, value in node.items():
            if key in {"title", "text"}:
                continue
            if key in {"imageUrl", "coverImageUrl"} and isinstance(value, str):
                url = _image_from_src(value)
                if url:
                    images.append(url)
            elif isinstance(value, (dict, list)):
                _collect_blocks(value, blocks, images)
    elif isinstance(node, list):
        for item in node:
            _collect_blocks(item, blocks, images)


def _attribute_groups(node, group: str) -> list[dict]:
    """Collect every ``C-P#Attribute&attributeBasic`` under ``node``.

    Attribute order is preserved exactly as served: Joybuy renders the
    same order in its two-column tables, and ``attributeSort`` is only a
    hint (docs/14 §7.6).
    """

    params: list[dict] = []

    def walk(value):
        if isinstance(value, dict):
            basic = value.get("C-P#Attribute&attributeBasic")
            if isinstance(basic, dict):
                name = str(basic.get("attributeName") or "").strip()
                attribute_value = str(basic.get("attributes") or "").strip()
                if name and attribute_value:
                    params.append(
                        {"group": group, "name": name, "value": attribute_value}
                    )
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(node)
    return params


def build_specification_tables(specifications: list[dict]) -> list[dict]:
    """规格参数按 group 组成两列表格：``{title, columns, rows}``。

    Joybuy shows 【规格参数】/【材质与规格】/【技术规格】 as ``属性 | 值``
    tables; the storefront has to render the same structure, so the group
    and the row order are preserved here instead of being flattened.
    """

    groups: list[str] = []
    for item in specifications:
        group = str(item.get("group") or "规格参数").strip()
        if group not in groups:
            groups.append(group)
    tables = []
    for group in groups:
        rows = [
            {"name": item["name"], "value": item["value"]}
            for item in specifications
            if str(item.get("group") or "规格参数").strip() == group
        ]
        tables.append({"title": group, "columns": ["属性", "值"], "rows": rows})
    return tables


def parse_uk_mobile_detail(html: str) -> tuple[list[dict], list[dict]]:
    """移动端详情 SSR：``structuredFloors`` 图文区块 + 规格参数。

    Returns ``(sections, specifications)``:

    * sections: ``[{title, blocks, text, images}]`` — e.g. 核心卖点与优势/
      产品详情/使用说明, each keeping its heading/paragraph blocks;
    * specifications: ``[{group, name, value}]`` with group 规格参数/材质与规格/
      技术规格.

    Older mobile pages carry ``graphDetailsModule`` (+ ``graphDetailListN``)
    instead of ``structuredFloors``; both are supported.
    """

    text = _flight_text(html)
    sections: list[dict] = []
    specs: list[dict] = []

    idx = text.find('"structuredFloors":')
    if idx >= 0:
        start = text.find("[", idx)
        try:
            floors, _ = json.JSONDecoder().raw_decode(text[start:])
        except json.JSONDecodeError:
            floors = []
        for floor in _resolve_flight_refs(floors, text):
            if not isinstance(floor, dict):
                continue
            data = floor.get("data") or {}
            title = str(data.get("structuredName") or "").strip()
            modules = data.get("modules")
            if data.get("mode") == 8 or str(data.get("moduleType")) == "3":
                specs.extend(_attribute_groups(modules, title or "规格参数"))
                continue
            blocks: list[dict] = []
            images: list[str] = []
            _collect_blocks(modules, blocks, images)
            if title:
                sections.append(
                    {
                        "title": title,
                        "blocks": blocks,
                        "text": _blocks_text(blocks),
                        "images": _dedupe_images(images),
                    }
                )

    # 旧版移动端结构：graphDetailsModule + graphDetailListN。
    gidx = text.find('"graphDetailsModule":')
    if gidx >= 0:
        start = text.find("{", gidx)
        try:
            module, _ = json.JSONDecoder().raw_decode(text[start:])
        except json.JSONDecodeError:
            module = {}
        module = _resolve_flight_refs(module, text)
        if isinstance(module, dict):
            specs.extend(_attribute_groups(module.get("extendPartList"), "规格参数"))
            for group in module.get("specificationPartList") or []:
                if not isinstance(group, dict):
                    continue
                basic = group.get("C-P#Specification&specificationBasic") or {}
                group_name = str(
                    basic.get("specificationGroupName") or "规格参数"
                ).strip()
                specs.extend(
                    _attribute_groups(group.get("attributePartList"), group_name)
                )

    if not specs:
        for match in re.finditer(r'"graphDetailList\d+"\s*:', text):
            try:
                items, _ = json.JSONDecoder().raw_decode(text[match.end() :].lstrip())
            except json.JSONDecodeError:
                continue
            if isinstance(items, list):
                specs.extend(_attribute_groups(items, "规格参数"))

    seen = set()
    clean_specs = []
    for item in specs:
        key = (item["group"], item["name"], item["value"])
        if key in seen:
            continue
        seen.add(key)
        clean_specs.append(item)

    sections = [section for section in sections if section["text"] or section["images"]]
    return sections, clean_specs


def _description_from_sections(sections: list[dict]) -> str:
    """扁平文本兜底：区块标题 + ``## `` 标记的子标题 + 正文。"""

    parts = []
    for section in sections or []:
        if section.get("title") in SPEC_SECTION_TITLES:
            continue
        block_lines = []
        for block in section.get("blocks") or []:
            if block.get("type") == "heading":
                block_lines.append(f"## {block['text']}")
            else:
                block_lines.append(block["text"])
        if block_lines:
            parts.append(f"【{section['title']}】\n" + "\n".join(block_lines))
        elif section.get("images"):
            parts.append(f"【{section['title']}】")
    return "\n\n".join(parts)


def _section_images(sections: list[dict]) -> list[str]:
    images: list[str] = []
    for section in sections or []:
        for image in section.get("images") or []:
            if image not in images:
                images.append(image)
    return images


def mobile_detail_url(source_id: str) -> str:
    """Mobile/图文详情 URL（www 站点，robots.txt 允许）。"""

    return MOBILE_DETAIL_URL_TEMPLATE.format(source_id=source_id)


def merge_mobile_detail(product: UkProduct, mobile_html: str) -> UkProduct:
    """把移动端图文/规格合并进 PC 解析结果（纯函数，不联网）。

    Mobile ``structuredFloors`` wins; PC DOM only fills sections it does not
    already cover (e.g. 「重要信息」 10 张图). Spec tables are replaced only
    when the mobile page actually served attributes, so a failed/blocked
    mobile page cannot wipe PC data.
    """

    sections, specifications = parse_uk_mobile_detail(mobile_html)
    merged = list(sections)
    titles = {section["title"] for section in merged}
    for section in product.content_sections or []:
        if section.get("title") in titles:
            continue
        if section.get("text") or section.get("images"):
            merged.append(section)
    product.content_sections = merged
    product.description = _description_from_sections(merged) or product.description
    product.detail_images = _dedupe_images(
        list(product.detail_images or []) + _section_images(merged)
    )
    if specifications:
        product.specifications = specifications
        product.specification_tables = build_specification_tables(specifications)
    return product


def parse_uk_listing(html: str) -> list[UkListingEntry]:
    """Product cards from a listing / bestseller page.

    Two layouts exist in the wild (both live 2026-11-05):

    * **card layout** — ``div[class*="product_card"]`` wraps an image anchor
      plus ``title`` / ``brandName`` / ``crossOffPrice`` / ``mainPriceText``
      nodes. The image anchor itself carries no text, which is why a purely
      anchor-based parser produced titleless cards.
    * **anchor layout** — the older one where the card *is* an
      ``a[href*="/dp/"]`` with the title and price inside it (still used by
      bestseller pages and by the parser fixtures).

    Cards are scanned first; when the page has none the anchor path runs, so
    a layout change in either direction keeps working. Raises when nothing
    matches — a structure change must surface as a signal, never as an empty
    page.
    """

    selector = Selector(text=html)
    entries: list[UkListingEntry] = []
    seen_urls: set[str] = set()

    for card in selector.css('[class*="product_card"]'):
        anchor = card.css('a[href*="/dp/"]')
        if not anchor:
            continue
        href = _absolute_url((anchor[0].attrib.get("href") or "").strip())
        if "/dp/" not in href or href in seen_urls:
            continue
        seen_urls.add(href)
        title = (
            _text(card.css('[class*="style_title"]')[0])
            if card.css('[class*="style_title"]')
            else ""
        )
        if len(title) < 5:
            # Fall back to the image alt text, which carries the full title.
            title = " ".join(
                (anchor[0].css("img::attr(alt)").get() or "").split()
            ).strip()
        original = (
            _price(_text(card.css('[class*="crossOffPrice"]')[0]))
            if card.css('[class*="crossOffPrice"]')
            else None
        )
        if original is None and card.css('[class*="mainPriceText"]'):
            original = _price(_text(card.css('[class*="mainPriceText"]')[0]))
        if original is None and card.css('[class*="mainPrice"]'):
            original = _price(_text(card.css('[class*="mainPrice"]')[0]))
        image = anchor[0].css("img::attr(src)").get() or ""
        entries.append(
            UkListingEntry(
                source_url=href,
                rank=len(entries) + 1,
                title=title,
                original_price=original,
                image_url=_image_url(image),
            )
        )

    if not entries:
        # Older/anchor layout (bestseller pages, fixtures).
        for anchor in selector.css('a[href*="/dp/"]'):
            href = _absolute_url((anchor.attrib.get("href") or "").strip())
            if not href or "/dp/" not in href or href in seen_urls:
                continue
            seen_urls.add(href)
            # Prefer an explicit title node; then the anchor's own text; only
            # then everything inside it (which would also swallow the price).
            title = (
                _text(anchor.css('[class*="title"]')[0])
                if anchor.css('[class*="title"]')
                else ""
            )
            if not title:
                title = " ".join(
                    part.strip()
                    for part in anchor.xpath("./text()").getall()
                    if part.strip()
                )
            if not title:
                title = _text(anchor)
            original = (
                _price(_text(anchor.css('[class*="crossOffPrice"]')[0]))
                if anchor.css('[class*="crossOffPrice"]')
                else None
            )
            if original is None and anchor.css('[class*="mainPrice"]'):
                original = _price(_text(anchor.css('[class*="mainPrice"]')[0]))
            image = anchor.css("img::attr(src)").get() or ""
            entries.append(
                UkListingEntry(
                    source_url=href,
                    rank=len(entries) + 1,
                    title=title,
                    original_price=original,
                    image_url=_image_url(image),
                )
            )

    if not entries:
        raise RuntimeError("Joybuy UK listing page has no /dp/ product cards.")
    return entries


def parse_uk_product_detail(html: str, *, source_url: str = "") -> UkProduct:
    selector = Selector(text=html)

    flight_text = _flight_text(html)
    flight = _extract_flight_product(html, text=flight_text) or {}
    #: ``serverProduct.data.floors``: 画廊、规格、视频的权威来源（2026-11-09）。
    floors = _floors_by_id(_decode_server_product(html, text=flight_text))
    json_ld = _parse_json_ld(selector)

    title = (
        (selector.css("h1::text").get() or "").strip()
        or (json_ld.get("name") or "").strip()
        or str(flight.get("title") or "").strip()
    )
    source_id = ""
    for url in (source_url, json_ld.get("url") or ""):
        match = UK_PRODUCT_URL_PATTERN.search(url or "")
        if match:
            source_id = match.group(1)
            break
    if not source_id:
        source_id = str(flight.get("productId") or json_ld.get("sku") or "").strip()

    brand = (
        (selector.css('[class*="brand"] ::text').get() or "").strip()
        or (
            json_ld.get("brand", {}).get("name", "").strip()
            if isinstance(json_ld.get("brand"), dict)
            else str(json_ld.get("brand") or "").strip()
        )
        or str(flight.get("brand") or "").strip()
    )

    # Original-price rule: crossOffPrice (visible original) > JSON-LD (only
    # when it must be the original) > mainPrice last resort.
    cross_price = (
        _price(
            selector.css('[class*="crossOffPrice"] ::text').get()
            or selector.css('[class*="crossOffPrice"]::text').get()
        )
        or str(flight.get("crossOffPrice") or "").strip()
        or None
    )
    main_price = (
        _price(
            selector.css('[class*="mainPrice"] ::text').get()
            or selector.css('[class*="mainPrice"]::text').get()
        )
        or str(flight.get("mainPrice") or "").strip()
        or None
    )
    json_ld_price = None
    offers = json_ld.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    json_ld_price = _price(str(offers.get("price") or "")) if offers else None
    current_price = cross_price or json_ld_price or main_price
    list_price = None  # discounts are never kept (business rule)
    currency = str(offers.get("priceCurrency") or "").strip().upper() or (
        "GBP" if "£" in (html[:20000] or "") else ""
    )

    # Gallery (2026-11-09): the flight ``productMainImageFloor.mediaData``
    # lists every image at s1248. The DOM only shows the selected big image
    # plus s128 thumbnails, and it also carries service/benefit icons — so
    # it is only a fallback, and it is cleaned by the same rules.
    gallery = extract_flight_gallery(floors)
    if not gallery:
        dom_gallery = []
        for image in selector.css(
            'img[src*="joy-sourcing.com"]::attr(src), '
            'link[rel=preload][href*="joy-sourcing.com"]::attr(href)'
        ).getall():
            # Joybuy serves protocol-relative srcs; preload links point at
            # the hi-res variants (s1248x1248 seen live 2026-11-05).
            if image.startswith("//"):
                url = f"https:{image}"
            elif image.startswith("http"):
                url = image
            else:
                url = f"https://{image.lstrip('/')}"
            if "/product/" in url and url not in dom_gallery:
                dom_gallery.append(url)
        json_ld_images = json_ld.get("image") or []
        if isinstance(json_ld_images, str):
            json_ld_images = [json_ld_images]
        for image in json_ld_images:
            url = image if isinstance(image, str) else image.get("url", "")
            if url and "/product/" in url and url not in dom_gallery:
                dom_gallery.insert(0, url)
        gallery = clean_gallery(dom_gallery)

    # 2026-11-09: the flight payload carries the authoritative product-level
    # category path with numeric IDs (e.g. 厨具餐具(288)/锅具(361)/炒锅(372)).
    # We keep the first two levels for display/breadcrumb and drop the rest;
    # the DOM trail stays as a fallback when the flight block is absent.
    flight_categories = _extract_flight_product_categories(html, text=flight_text)
    if flight_categories:
        breadcrumbs = [{"name": item["name"], "cid": ""} for item in flight_categories]
    else:
        breadcrumbs = []
        for crumb in selector.css(
            'nav[class*="breadcrumb"] a, [class*="breadcrumb"] a'
        ):
            name = " ".join(crumb.css("::text").getall()).strip()
            href = crumb.attrib.get("href") or ""
            cid_match = re.search(r"(?:l1|cid[1-4]|firstcid)=(\d+)", href)
            breadcrumbs.append(
                {"name": name, "cid": f"l1:{cid_match.group(1)}" if cid_match else ""}
            )
        # Two-level catalog rule (2026-11-05): deeper levels are dropped here so
        # every downstream consumer sees the same trail length.
        breadcrumbs = truncate_breadcrumbs(breadcrumbs)

    product_category_path = [
        {"id": item["id"], "name": item["name"], "depth": index}
        for index, item in enumerate(flight_categories)
    ]

    skus = []
    for item in selector.css('[class*="sku"] [data-sku-id], [data-sku-id]'):
        sku_id = (item.attrib.get("data-sku-id") or "").strip()
        if not sku_id:
            continue
        sku_price = _price(item.attrib.get("data-price", "")) or current_price
        skus.append(
            {
                "source_id": sku_id,
                "price": sku_price,
                "availability": (
                    item.attrib.get("data-availability") or "UNKNOWN"
                ).upper(),
                "specs": [],
            }
        )
    if not skus and source_id:
        # Single-variant product: Joybuy detail pages without a SKU list
        # still expose one implicit SKU identified by the product id.
        flight_sku = str(flight.get("skuId") or "").strip()
        skus.append(
            {
                "source_id": flight_sku or source_id,
                "price": current_price,
                "availability": str(flight.get("availability") or "UNKNOWN").upper(),
                "specs": [],
            }
        )

    # Spec variants (2026-11-09): series/capacity in productSeriesFloor and
    # colour/size in colorSizePartList. Both feed ``spec_options`` and the
    # per-SKU ``specs``; a single-SKU product still gets its one value.
    spec_options = extract_spec_options(floors)
    sku_specs = sku_specs_from_options(spec_options)
    for sku in skus:
        specs = sku_specs.get(str(sku["source_id"]))
        if specs:
            sku["specs"] = specs
    if skus and not any(sku.get("specs") for sku in skus):
        single_values = [
            {"name": option["name"], "value": option["values"][0]["value"]}
            for option in spec_options
            if len(option.get("values") or []) == 1
        ]
        if single_values:
            skus[0]["specs"] = single_values

    # Variants (WP-45 phase 1): one entry per spec combination with its real
    # name/value pairs. The primary (currently browsed) sku inherits the page
    # price; the rest are enriched by the caller (spider / debug_crawl).
    variants = extract_variants(
        spec_options,
        floors,
        primary_source_id=source_id,
        currency=currency,
        primary_price=current_price,
    )

    # Description / 图文详情 (2026-11-09): the PC accordions carry their own
    # titles and <strong> subheadings; the mobile page adds the sections the
    # PC SSR never renders (see merge_mobile_detail).
    content_sections = extract_dom_sections(selector)
    if not content_sections:
        legacy_texts = [
            part.strip()
            for part in selector.css(
                '[class*="description"] ::text, [id*="description"] ::text'
            ).getall()
            if part.strip()
        ]
        legacy_images = [
            _image_from_src(src)
            for src in selector.css(
                '[class*="description"] img::attr(src), '
                '[id*="description"] img::attr(src)'
            ).getall()
        ]
        if legacy_texts or legacy_images:
            content_sections = [
                {
                    "title": "商品描述",
                    "blocks": [
                        {"type": "paragraph", "text": text} for text in legacy_texts
                    ],
                    "text": "\n".join(legacy_texts),
                    "images": _dedupe_images(legacy_images),
                }
            ]
    description = _description_from_sections(content_sections)
    detail_images = _section_images(content_sections)

    seller_anchor = selector.css('a[href*="/store/"]')
    seller_name = ""
    if seller_anchor:
        # The store card shows the seller name next to a "View store" /
        # 「查看店铺」link; the link text alone is not the seller. The UI
        # suffix changes with the site locale, so it must never leak into
        # the seller identity used by MerchantSourceMapping.
        raw = " ".join(seller_anchor[0].xpath("..").css("::text").getall())
        seller_name = normalize_seller_name(raw) or normalize_seller_name(
            str(flight.get("sellerName") or "")
        )
    seller_name = seller_name or normalize_seller_name(
        str(flight.get("sellerName") or "")
    )
    seller_url = seller_anchor[0].attrib.get("href", "") if seller_anchor else ""
    if seller_url.startswith("/"):
        seller_url = f"https://www.joybuy.co.uk{seller_url}"

    # Review data (2026-11-05): aggregates only, never review content.
    # The flight JSON is authoritative; the visible chip is a fallback.
    review = _extract_flight_review(html, text=flight_text) or _extract_dom_review(
        selector
    )
    rating_average = review.get("average")
    rating_count = review.get("count")
    rating_distribution = review.get("distribution") or {}
    rating_source = review.get("source", "")
    ai_summary = review.get("summary", "")
    ai_summary_title = review.get("summary_title", "")
    ai_summary_tags = review.get("summary_tags", [])

    # 2026-11-09: the page also carries the summary as an inline
    # ``aiSummary{summaryContent, summaryText}`` object; it wins because it
    # arrives with the tags the flat review block does not.
    inline_summary = extract_ai_summary(flight_text)
    if inline_summary["summary"]:
        ai_summary = inline_summary["summary"]
        ai_summary_title = inline_summary["title"]
        ai_summary_tags = inline_summary["tags"]

    if rating_average is None or rating_count is None:
        dom_average, dom_count = _rating_from_dom(selector, html)
        rating_average = rating_average or dom_average
        if rating_count is None:
            rating_count = dom_count

    # 2026-11-16: JSON-LD ``aggregateRating`` 是 RSC 改版后的可靠兜底——
    # /dp/ 页的 ld+json 仍带 ratingValue/ratingCount（实测 4.4 / 49），
    # flight 与 DOM 都取不到时才用，且不改写已解析出的分桶分布。
    if rating_average is None or rating_count is None:
        ld_rating = (
            json_ld.get("aggregateRating") if isinstance(json_ld, dict) else None
        )
        if isinstance(ld_rating, dict):
            ld_average = _price(str(ld_rating.get("ratingValue") or ""))
            ld_count = None
            try:
                raw_count = ld_rating.get("ratingCount")
                ld_count = int(raw_count) if raw_count is not None else None
            except (TypeError, ValueError):
                ld_count = None
            if ld_average is not None and rating_average is None:
                rating_average = ld_average
                rating_source = rating_source or "json_ld"
            if ld_count is not None and rating_count is None:
                rating_count = ld_count
                rating_source = rating_source or "json_ld"

    videos = extract_videos(floors)

    parsed = UkProduct(
        source_id=source_id,
        title=title,
        currency=currency,
        current_price=current_price,
        list_price=list_price,
        main_price=main_price,
        promotion_label="",
        availability=str(flight.get("availability") or "UNKNOWN").upper(),
        brand=brand,
        breadcrumbs=breadcrumbs,
        skus=skus,
        gallery=gallery,
        description=description,
        detail_images=detail_images,
        seller_name=seller_name,
        seller_url=seller_url,
        rating_average=rating_average,
        rating_count=rating_count,
        source_url=source_url,
        rating_distribution=rating_distribution,
        rating_source=rating_source,
        ai_summary=ai_summary,
        ai_summary_title=ai_summary_title,
        ai_summary_tags=ai_summary_tags,
        product_category_path=product_category_path,
        spec_options=spec_options,
        content_sections=content_sections,
        specifications=[],  # 移动端详情补齐（merge_mobile_detail）
        specification_tables=[],
        videos=videos,
        variants=variants,
    )
    parsed.missing_fields = [
        name
        for name in (
            "source_id",
            "title",
            "currency",
            "current_price",
            "skus",
        )
        if not getattr(parsed, name)
    ]
    return parsed
