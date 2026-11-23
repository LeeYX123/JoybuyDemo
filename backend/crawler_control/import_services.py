"""Controlled import of staged products into catalog/offers (WP-16).

Everything goes through the existing domain services:

- ``catalog.product_services`` for SPU/SKU and source identities;
- ``offers.services.import_offer_from_source`` for offers, prices, snapshots
  and the initial 9999 inventory ledger;
- ``catalog.override_services.apply_source_field_values`` so crawler values
  only ever touch the SOURCE layer — approved local overrides keep winning;
- ``merchants.services.resolve_import_merchant`` for seller mapping with the
  "Joybuy 自营导入" fallback.

Repeated imports never duplicate entities; they refresh observations and
append price snapshots.
"""

import copy
import dataclasses
import logging
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from catalog.domain import ProductSourceIdentityInvalid
from catalog.models import (
    Brand,
    CategoryMapping,
    ProductCategory,
    SkuSourceIdentity,
    SourceCatalog,
    SpuTranslation,
)
from catalog.override_services import apply_source_field_values
from catalog.product_services import (
    get_or_create_sku_from_source,
    get_or_create_spu_from_source,
)
from crawler_control.domain import ImportSourceConflict
from crawler_control.models import StagingProduct
from merchants.services import resolve_import_merchant
from offers.domain import OfferSourceIdentityInvalid
from offers.models import Offer, OfferSourceIdentity
from offers.services import import_offer_from_source

logger = logging.getLogger(__name__)

IMPORT_REQUIRED_FIELDS = ("source_id", "title", "currency", "current_price", "skus")

#: 变体价格可信来源（WP-45 阶段 2）：``variant_page`` = 变体页补抓所得，
#: ``detail_page`` = 主变体继承详情页原价。留空（开关关闭/补抓失败/超上限）
#: 的变体只建 SKU 不建 Offer —— 宁缺毋假，不得用 SPU 价格冒充变体价。
VARIANT_TRUSTED_PRICE_SOURCES = {"variant_page", "detail_page"}

#: 「活动商品」是 Spu.is_activity 标记，不是类目（见 catalog.models.Spu）。
#: 任务选中这些 Joybuy 菜单节点时，商品直接按活动商品入库，且不分配本地类目。
ACTIVITY_SOURCE_CATEGORY_IDS = {"l2:1580"}  # 节庆装饰品
ACTIVITY_SOURCE_CATEGORY_NAMES = {"节庆装饰品"}
#: 兜底信号：节庆装饰品在商品后台类目里落在「节日派对/节日与活动(4945)」；
#: 即使任务选的是父频道，也能把这些商品标成活动商品。
ACTIVITY_PRODUCT_CATEGORY_IDS = {"4945"}  # 节日与活动
ACTIVITY_PRODUCT_CATEGORY_NAMES = {"节日与活动"}


class StagingImportRejected(RuntimeError):
    """The staged payload is missing required fields; nothing was imported."""

    def __init__(self, staging: StagingProduct, missing_fields: list[str]):
        self.staging = staging
        self.missing_fields = missing_fields
        super().__init__(
            f"暂存记录 {staging.source_system}:{staging.source_id} 缺少必填字段："
            f"{', '.join(missing_fields)}。"
        )


@dataclasses.dataclass
class ImportOutcome:
    staging: StagingProduct
    spu: object
    created_spu: bool
    skus: list
    offers: list


def _resolve_brand(payload) -> Brand | None:
    brand_name = (payload.get("brand") or "").strip()
    if not brand_name:
        return None
    brand, _ = Brand.objects.get_or_create(
        name=brand_name,
        defaults={"slug": _brand_slug(brand_name)},
    )
    return brand


def _brand_slug(name: str) -> str:
    slug = "".join(char if char.isalnum() else "-" for char in name.lower())
    return "-".join(part for part in slug.split("-") if part)[:120] or "brand"


def _resolve_local_category(source_category):
    mapping = (
        (
            CategoryMapping.objects.select_related("local_category")
            .filter(source_category=source_category, is_primary=True)
            .first()
        )
        if source_category
        else None
    )
    return mapping.local_category if mapping else None


#: Spu.retail_price 是 DecimalField(max_digits=18, decimal_places=4)：
#: 4 位小数、最多 14 位整数。
_SPU_PRICE_QUANTUM = Decimal("0.0001")
_SPU_PRICE_MAX_INTEGER = Decimal(10) ** 14


def _parse_spu_retail_price(value) -> Decimal | None:
    """抓取价=入库价=零售价（2026-11-10 口径）：payload ``current_price`` 即
    ``Spu.retail_price``（爬虫只采原价，crossOffPrice 规则见 docs/05）。

    解析失败（缺失/非数字/负数/溢出位数）返回 ``None``，调用方保留原值——
    必填字段缺失时导入在入口就被拒绝，这里只兜住「脏价格不让导入翻车」。"""

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount < 0 or abs(amount) >= _SPU_PRICE_MAX_INTEGER:
        return None
    return amount.quantize(_SPU_PRICE_QUANTUM)


def _parse_rating_summary(payload: dict) -> dict:
    """源站评价汇总 → ``SpuDetail`` 评分字段（2026-11-10）。

    爬虫商品没有本地评价行，评分/评价数/星级分布按源站快照保存；
    值为空/非法时返回空字典，调用方不覆盖旧值。
    """

    count = payload.get("rating_count")
    try:
        count = int(count or 0)
    except (TypeError, ValueError):
        count = 0
    if count <= 0:
        return {}
    fields: dict = {"rating_count": count}

    average = payload.get("rating_average")
    if average is not None:
        try:
            parsed = Decimal(str(average))
        except InvalidOperation:
            parsed = None
        if parsed is not None and parsed.is_finite() and 0 <= parsed <= 5:
            fields["rating_average"] = parsed.quantize(Decimal("0.01"))

    distribution = payload.get("rating_distribution")
    if isinstance(distribution, dict):
        clean = {}
        for star, value in distribution.items():
            try:
                key = int(str(star))
                amount = int(value or 0)
            except (TypeError, ValueError):
                continue
            if 1 <= key <= 5 and amount >= 0:
                clean[str(key)] = amount
        if clean:
            fields["rating_distribution"] = clean
    return fields


def _apply_spu_retail_price(spu, payload: dict):
    """按 payload 原价刷新 ``Spu.retail_price``（新建与重导都更新：爬虫是价格
    的唯一事实源）。价格缺失/非法时保留旧值；DB 约束要求 retail >= cost，
    撞约束时同样保留旧值、绝不为改价弄挂整次导入；不动 ``cost_price``。"""

    new_price = _parse_spu_retail_price(payload.get("current_price"))
    if new_price is None:
        return
    if spu.cost_price is not None and new_price < spu.cost_price:
        return
    if spu.retail_price == new_price:
        return
    spu.retail_price = new_price
    spu.save(update_fields=["retail_price", "updated_at"])


def _is_accessory_category_name(name: str) -> bool:
    """类目名是否含「配件 / Accessories」语义（2026-11-23 批次 A）。"""

    normalized = str(name or "").strip().casefold()
    return any(token in normalized for token in ("配件", "accessory", "accessories"))


def _accessory_parent_conflict(existing, intended_parent) -> bool:
    """配件类目在库内的父级与源面包屑父级是否不一致。

    「配件」在多个一级类目下同名（电子产品 > 配件 vs 服装与配饰 > 配件），
    只看名字会把商品静默归到另一个父级。库内节点已有父级、而本次 payload
    的父级与它不同（或缺失）时，视为不一致。
    """

    if existing.parent_id is None:
        return False
    if intended_parent is None:
        return True
    return existing.parent_id != intended_parent.pk


def _record_accessory_parent_mismatch(*, staging, node, existing, intended_parent):
    """记录 ``PRODUCT_CATEGORY_PARENT_MISMATCH`` 告警（日志 + 抓取运行事件）。"""

    intended_name = intended_parent.name if intended_parent is not None else "（源面包屑缺父级）"
    intended_id = intended_parent.source_id if intended_parent is not None else ""
    intended_label = f"{intended_name}（source_id {intended_id}）" if intended_id else intended_name
    message = (
        f"商品 {getattr(staging, 'source_id', '')} 的配件类目「{node['name']}」"
        f"（source_id {node['source_id']}）源面包屑父级为「{intended_label}」，"
        f"与库内父级「{existing.parent.name}」（source_id {existing.parent.source_id}）"
        "不一致；本次不自动归类，保留库内父级。"
    )
    logger.warning(
        "product_category_parent_mismatch",
        extra={
            "event": "PRODUCT_CATEGORY_PARENT_MISMATCH",
            "staging_source_id": getattr(staging, "source_id", ""),
            "product_category_source_id": node["source_id"],
            "existing_parent_source_id": existing.parent.source_id,
            "intended_parent_source_id": intended_id,
        },
    )
    run_id = getattr(staging, "run_id", None)
    if not run_id:
        return
    from crawler_control.models import CrawlRunEvent

    CrawlRunEvent.objects.create(
        run_id=run_id,
        level=CrawlRunEvent.Level.WARNING,
        code="PRODUCT_CATEGORY_PARENT_MISMATCH",
        message=message[:1000],
        source_url=(getattr(staging, "source_url", "") or "")[:2000],
    )


def _sync_product_categories(payload: dict, *, source_system: str, staging=None):
    """把一个商品的两级商品类目路径写进 ``ProductCategory`` 并返回最深节点。

    2026-11-09 口径：Joybuy 商品面包屑可能是 3~4 级（厨具餐具/锅具/炒锅），
    这里只保留前两级；第三级及更深永远不落库。

    2026-11-23（批次 A）：名字含「配件 / Accessories」的类目额外校验父级。
    库内节点已有父级、且与本次源面包屑父级不一致（或 payload 缺父级）时，
    **不重新归类/不重挂父级**，只记录 ``PRODUCT_CATEGORY_PARENT_MISMATCH``
    告警事件；商品照常导入，类目保持库内现值。
    """

    raw_path = payload.get("product_category_path") or []
    if not isinstance(raw_path, list):
        return None
    nodes = []
    for item in raw_path[:2]:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        if source_id and name:
            nodes.append({"source_id": source_id, "name": name})
    if not nodes:
        return None

    catalog = SourceCatalog.objects.filter(source_system__iexact=source_system.strip()).first()
    if catalog is None:
        return None

    parent = None
    path_parts = []
    for depth, node in enumerate(nodes):
        path_parts.append(node["source_id"])
        existing = (
            ProductCategory.objects.select_related("parent")
            .filter(catalog=catalog, source_id=node["source_id"])
            .first()
        )
        if (
            existing is not None
            and _is_accessory_category_name(node["name"])
            and _accessory_parent_conflict(existing, parent)
        ):
            _record_accessory_parent_mismatch(
                staging=staging, node=node, existing=existing, intended_parent=parent
            )
            # 保留库内节点与父级，作为下一级的父级继续解析。
            parent = existing
            continue
        parent, _ = ProductCategory.objects.update_or_create(
            catalog=catalog,
            source_id=node["source_id"],
            defaults={
                "parent": parent,
                "name": node["name"],
                "depth": depth,
                "path": "/" + "/".join(path_parts) + "/",
            },
        )
    return parent


_IMPORT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

#: 单张图片下载上限（画廊图）。
_IMAGE_MAX_BYTES = 10 * 1024 * 1024
#: 单条视频下载上限。实测蒸锅 23s 视频 7.1MB；放宽到 100MB 防大文件打爆内存。
_VIDEO_MAX_BYTES = 100 * 1024 * 1024
_IMAGE_TIMEOUT_SECONDS = 30.0
_VIDEO_TIMEOUT_SECONDS = 120.0


def _adopt_enriched_specification(
    *,
    spu,
    source_system: str,
    source_id: str,
    specification: dict,
    source_url: str = "",
):
    """历史 SKU 补上规格时的兼容处理（2026-11-09）。

    2026-11-05 那批 SKU 导入时解析器拿不到规格（``skus[].specs`` 为空，
    签名是 ``{}``）；现在从「系列 / 颜色」维度解析出了规格，同一来源 SKU
    的签名会变，``get_or_create_sku_from_source`` 会抛身份冲突。

    身份键是 ``source_id``，规格只是观测值，所以这里只允许「旧规格为空 →
    新规格非空」的补全；旧规格非空且不一致、身份属于别的 SPU、或新签名已被
    同 SPU 其它 SKU 占用时返回 ``None``，调用方仍然抛原错误。
    """

    from catalog.models import Sku, SkuSourceIdentity
    from catalog.product_services import canonicalize_source_specification

    identity = (
        SkuSourceIdentity.objects.select_related("sku")
        .filter(
            source_system=source_system.strip().casefold(),
            source_id=source_id.strip(),
        )
        .first()
    )
    if identity is None or identity.sku.spu_id != spu.pk:
        return None
    sku = identity.sku
    if sku.specification:
        return None
    try:
        normalized, signature = canonicalize_source_specification(specification)
    except Exception:  # noqa: BLE001 - 非法规格仍按原错误上抛
        return None
    if not normalized:
        return None
    if Sku.objects.filter(spu=spu, specification_signature=signature).exclude(pk=sku.pk).exists():
        return None
    sku.specification = normalized
    sku.specification_signature = signature
    sku.save(update_fields=["specification", "specification_signature", "updated_at"])
    if source_url:
        identity.source_url = source_url.strip()
    identity.last_seen_at = timezone.now()
    identity.save(update_fields=["source_url", "last_seen_at", "updated_at"])
    return sku


def _split_variants_by_same_source(payload: dict) -> tuple[list[dict], list[dict]]:
    """Split payload ``variants`` into same-source-product vs sibling-product rows.

    口径（WP-45 阶段 2，2026-11-15 实抓实锤）：源站详情页的
    ``productSelectedFloor.skuStatus`` 只覆盖当前源商品自己的 SKU；系列轴的
    值可能指向「兄弟商品」（如 iPhone 1TB 是另一个源商品页，其 sku id 不在
    skuStatus 里）。阶段 1 解析器把 skuStatus 逐 sku 透传进
    ``variants[].sku_status``，因此判定规则是：

    - ``is_primary`` 为真（当前浏览的源 sku）；
    - 或 ``source_sku_id`` 与 payload 顶层 ``skus[].source_id``（主 SKU）相同；
    - 或 ``sku_status`` 非 null（被当前商品页的 skuStatus 声明过）。

    三者任一即视为「与主 SKU 同属一个源商品」，其余一律视为跨商品轴值，
    跳过并记日志。skuStatus 万一漏掉本商品某个 SKU 也按「宁缺毋假」跳过。
    """

    variants = payload.get("variants")
    if not isinstance(variants, list):
        return [], []
    main_source_ids = {
        str(item.get("source_id") or "").strip()
        for item in payload.get("skus") or []
        if isinstance(item, dict) and item.get("source_id")
    }
    same_source: list[dict] = []
    siblings: list[dict] = []
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        source_sku_id = str(variant.get("source_sku_id") or "").strip()
        if (
            variant.get("is_primary")
            or (source_sku_id and source_sku_id in main_source_ids)
            or variant.get("sku_status") is not None
        ):
            same_source.append(variant)
        else:
            siblings.append(variant)
            logger.info(
                "WP45 variant %s of product %s points at a sibling source product "
                "(no skuStatus entry, not primary); skipped.",
                source_sku_id or "?",
                payload.get("source_id") or "?",
            )
    return same_source, siblings


def _import_variant_image(sku, url: str, *, observed_at) -> bool:
    """Localize one variant spec image and link it to the SKU (role=variant).

    Best-effort: any download/processing failure returns False and never
    blocks the import — the SKU simply keeps no image (fallback 无图).
    """

    from media.pipeline import process_media_bytes

    data = _fetch_image_bytes(url)
    if not data:
        return False
    try:
        process_media_bytes(
            data,
            kind="PRODUCT",
            mime_type=_image_mime_type(url),
            source_url=url,
            target=sku,
            role="variant",
            observed_at=observed_at,
        )
    except Exception:  # noqa: BLE001 - 变体图失败不阻断导入
        logger.debug("Variant image localization failed for %s", url, exc_info=True)
        return False
    return True


def _fetch_bytes(url: str, *, max_bytes: int, timeout_seconds: float) -> bytes | None:
    """Best-effort remote fetch with a hard byte cap (never raises)."""

    if not url or not url.startswith(("http://", "https://")):
        return None
    request = urllib.request.Request(url, headers={"User-Agent": _IMPORT_UA})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            if response.status != 200:
                return None
            data = response.read(max_bytes + 1)
            if len(data) > max_bytes:
                return None
            return data
    except Exception:  # noqa: BLE001 - media download is best-effort
        return None


def _fetch_image_bytes(url: str) -> bytes | None:
    return _fetch_bytes(url, max_bytes=_IMAGE_MAX_BYTES, timeout_seconds=_IMAGE_TIMEOUT_SECONDS)


def _fetch_video_bytes(url: str) -> bytes | None:
    return _fetch_bytes(url, max_bytes=_VIDEO_MAX_BYTES, timeout_seconds=_VIDEO_TIMEOUT_SECONDS)


#: 导入阶段媒体并发数（与爬虫 dataset 的 CRAWL_MEDIA_DOWNLOAD_WORKERS 共用）。
IMPORT_MEDIA_WORKERS = int(os.getenv("CRAWL_MEDIA_DOWNLOAD_WORKERS", "6"))


def _read_local_media(path: str | None) -> bytes | None:
    """读取 dataset 已落盘的媒体文件；路径丢失/不可读时返回 None。"""

    if not path:
        return None
    try:
        return Path(path).read_bytes()
    except OSError:
        return None


def _fetch_media_many(
    urls: list[str],
    *,
    local_files: dict | None,
    fetcher,
) -> list[tuple[bytes | None, bool]]:
    """并发取一组媒体字节，保持输入顺序，返回 ``(bytes, 是否来自本地文件)``。

    优先复用爬虫 dataset 已经下载的文件（``local_files`` 是 URL→绝对路径），
    只有缺失或不可读时才重新下载——同一张图不再下载两遍。
    """

    if not urls:
        return []
    local_files = local_files or {}

    def _one(url: str) -> tuple[bytes | None, bool]:
        data = _read_local_media(local_files.get(url))
        if data is not None:
            return data, True
        return fetcher(url), False

    workers = max(1, min(IMPORT_MEDIA_WORKERS, len(urls)))
    if workers == 1:
        return [_one(url) for url in urls]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_one, urls))


def _image_mime_type(url: str) -> str:
    lower = url.lower()
    if ".webp" in lower:
        return "image/webp"
    if ".png" in lower:
        return "image/png"
    if ".gif" in lower:
        return "image/gif"
    return "image/jpeg"


def _video_mime_type(url: str) -> str:
    return "video/webm" if ".webm" in url.lower() else "video/mp4"


def _store_local_image(url: str, *, observed_at=None):
    """Download one image into the media library; ``None`` on failure."""

    from media.pipeline import process_media_bytes

    data = _fetch_image_bytes(url)
    if not data:
        return None
    try:
        asset, _created = process_media_bytes(
            data,
            kind="PRODUCT",
            mime_type=_image_mime_type(url),
            source_url=url,
            observed_at=observed_at,
        )
        return asset
    except Exception:  # noqa: BLE001 - a bad CDN object must not fail the import
        return None


def _localized_image_url(url: str, *, cache: dict, observed_at=None) -> str:
    """Local ``/media/...`` URL for a remote image; empty when it failed."""

    from media.storage import media_url

    if not url:
        return ""
    if url.startswith(settings.MEDIA_URL):
        # Payload already points at the local library (re-import of a
        # normalised payload): keep it as-is.
        return url
    if url in cache:
        asset = cache[url]
    else:
        asset = _store_local_image(url, observed_at=observed_at)
        cache[url] = asset
    return media_url(asset.relative_path) if asset is not None else ""


def _localize_content_sections(sections: list, *, cache: dict, observed_at=None) -> list[dict]:
    """Persist section images locally and drop unresolvable CDN URLs.

    Text/blocks are kept verbatim; only ``images`` is rewritten so the
    storefront never requests a third-party CDN at runtime.
    """

    result = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        item = copy.deepcopy(section)
        images = []
        for url in item.get("images") or []:
            local = _localized_image_url(
                str(url or "").strip(), cache=cache, observed_at=observed_at
            )
            if local:
                images.append(local)
        item["images"] = images
        result.append(item)
    return result


def _localize_spec_options(options: list, *, cache: dict, observed_at=None) -> list[dict]:
    result = []
    for option in options:
        if not isinstance(option, dict):
            continue
        item = copy.deepcopy(option)
        values = []
        for value in item.get("values") or []:
            if not isinstance(value, dict):
                continue
            entry = dict(value)
            entry["image_url"] = _localized_image_url(
                str(entry.get("image_url") or "").strip(),
                cache=cache,
                observed_at=observed_at,
            )
            entry["sku_ids"] = [str(sku_id) for sku_id in entry.get("sku_ids") or []]
            values.append(entry)
        item["values"] = values
        if values:
            result.append(item)
    return result


def _tables_from_specifications(specifications: list[dict]) -> list[dict]:
    """Backend fallback: group flat specs into two-column tables.

    Older payloads carry ``specifications`` without ``specification_tables``;
    the group and row order are preserved exactly like the crawler does.
    """

    groups: list[str] = []
    for item in specifications:
        if not isinstance(item, dict):
            continue
        group = str(item.get("group") or "规格参数").strip()
        if group not in groups:
            groups.append(group)
    tables = []
    for group in groups:
        rows = [
            {"name": item["name"], "value": item["value"]}
            for item in specifications
            if isinstance(item, dict)
            and str(item.get("group") or "规格参数").strip() == group
            and item.get("name")
        ]
        if rows:
            tables.append({"title": group, "columns": ["属性", "值"], "rows": rows})
    return tables


def _sync_spu_detail(spu, payload: dict, *, observed_at) -> dict:
    """Write crawled detail structure; never clears fields on an empty payload.

    A failed/older parse must not wipe previously imported detail data, so
    only non-empty values overwrite. ``Spu.description`` and the admin-edited
    ``image_urls`` / ``specs`` fields are left untouched.

    2026-11-10：管理端人工编辑过的图文详情（``content_source == "manual"``）
    不被爬虫覆盖 —— 只跳过 ``content_sections``，规格表格 / spec_options /
    AI 摘要等其它字段照常刷新。空的 payload sections 仍然不写入（既有规则）。
    """

    from catalog.models import SpuDetail

    fields: dict = {}
    image_cache: dict = {}

    sections = payload.get("content_sections")
    if isinstance(sections, list) and sections:
        existing_detail = SpuDetail.objects.filter(spu=spu).only("content_source").first()
        if existing_detail is not None and existing_detail.content_source == (
            SpuDetail.ContentSource.MANUAL
        ):
            # 人工编辑的图文区块是权威数据，爬虫 payload 不覆盖；
            # 其它字段（规格表格 / spec_options / AI）继续走下面的刷新逻辑。
            sections = []
        else:
            localized = _localize_content_sections(
                sections, cache=image_cache, observed_at=observed_at
            )
            if localized:
                fields["content_sections"] = localized

    specifications = payload.get("specifications")
    if isinstance(specifications, list) and specifications:
        fields["specifications"] = [item for item in specifications if isinstance(item, dict)]
        tables = payload.get("specification_tables")
        if isinstance(tables, list) and tables:
            fields["specification_tables"] = [table for table in tables if isinstance(table, dict)]
        else:
            fields["specification_tables"] = _tables_from_specifications(fields["specifications"])

    options = payload.get("spec_options")
    if isinstance(options, list) and options:
        localized_options = _localize_spec_options(
            options, cache=image_cache, observed_at=observed_at
        )
        if localized_options:
            fields["spec_options"] = localized_options

    ai_summary = str(payload.get("ai_summary") or "").strip()
    if ai_summary:
        fields["ai_summary"] = ai_summary
        ai_title = str(payload.get("ai_summary_title") or "").strip()
        if ai_title:
            fields["ai_summary_title"] = ai_title
        tags = payload.get("ai_summary_tags")
        if isinstance(tags, list):
            clean_tags = [str(tag).strip() for tag in tags if str(tag).strip()]
            if clean_tags:
                fields["ai_summary_tags"] = clean_tags

    # 评价汇总（2026-11-10）：本地没有评价行时购物端用这份源站快照显示
    # 「评分 / 评价数 / 1~5 星分布」；空 payload 不覆盖已有值。
    rating_fields = _parse_rating_summary(payload)
    if rating_fields:
        fields.update(rating_fields)

    # 销量/评价展示值（2026-11-19，productCommentSaleFloor.saleAmount）：
    # 展示字符串原样入库（如 "10k+"），空值不覆盖已有值。
    sale_amount = str(payload.get("sale_amount") or "").strip()
    if sale_amount:
        fields["sale_amount"] = sale_amount
    comment_display = str(payload.get("comment_count_display") or "").strip()
    if comment_display:
        fields["comment_count_display"] = comment_display

    if not fields:
        return {}
    fields["source_observed_at"] = observed_at
    SpuDetail.objects.update_or_create(spu=spu, defaults=fields)
    return {
        "content_sections": len(fields.get("content_sections") or []),
        "specification_tables": len(fields.get("specification_tables") or []),
        "spec_options": len(fields.get("spec_options") or []),
        "ai_summary": bool(fields.get("ai_summary")),
        "rating_count": fields.get("rating_count", 0),
        "sale_amount": fields.get("sale_amount", ""),
    }


def _duration_ms(value) -> int | None:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return int(round(seconds * 1000))


def _import_spu_videos(spu, payload: dict, *, observed_at, local_files: dict | None = None) -> dict:
    """Persist gallery videos from ``payload["videos"]`` (idempotent).

    Files land in the local media library (kind=VIDEO, content-addressed),
    posters in the image library. Rows match by source video id / URL so a
    re-import updates in place; videos no longer present on the source are
    removed, but an empty/missing ``videos`` key never wipes existing rows
    (that would lose data when a download or an older parser failed).

    2026-11-10 提速：``local_files``（URL→dataset 已下载视频）命中的视频直接
    读本地文件，不再重复下载。
    """

    from catalog.models import SpuVideo
    from media.models import MediaAsset
    from media.storage import store_bytes, stored_file_exists

    raw_videos = payload.get("videos")
    if not isinstance(raw_videos, list) or not raw_videos:
        return {"downloaded": 0, "reused": 0, "failed": 0}

    existing = list(SpuVideo.objects.filter(spu=spu).select_related("video", "poster"))
    matched_ids: set[int] = set()
    summary = {"downloaded": 0, "reused": 0, "failed": 0}
    image_cache: dict = {}
    local_files = local_files or {}
    media_prefix = settings.MEDIA_URL.rstrip("/") + "/"

    for index, item in enumerate(raw_videos):
        if not isinstance(item, dict):
            continue
        source_url = str(item.get("url") or "").strip()
        source_video_id = str(item.get("video_id") or "").strip()
        identity = source_video_id or source_url
        if not identity:
            continue

        matched = None
        for row in existing:
            if row.pk in matched_ids:
                continue
            if (source_video_id and row.source_video_id == source_video_id) or (
                source_url and row.source_url == source_url
            ):
                matched = row
                break

        video_asset = None
        if matched is not None:
            # Reuse the stored object when it still exists (local file or S3
            # object); a missing object falls through to re-download.
            try:
                if stored_file_exists(matched.video.relative_path):
                    video_asset = matched.video
            except Exception:  # noqa: BLE001 - fall through to re-download
                video_asset = None

        if video_asset is None:
            if source_url.startswith(media_prefix):
                video_asset = MediaAsset.objects.filter(
                    relative_path=source_url[len(media_prefix) :]
                ).first()
            if video_asset is None and source_url.startswith(("http://", "https://")):
                # 优先用 dataset 已下载的视频文件，避免同一个视频下载两遍。
                data = _read_local_media(local_files.get(source_url)) or _fetch_video_bytes(
                    source_url
                )
                if not data:
                    summary["failed"] += 1
                    continue
                try:
                    video_asset, _created = store_bytes(
                        data,
                        kind="VIDEO",
                        mime_type=_video_mime_type(source_url),
                        source_url=source_url,
                        observed_at=observed_at,
                    )
                    summary["downloaded"] += 1
                except Exception:  # noqa: BLE001
                    summary["failed"] += 1
                    continue
        if video_asset is None:
            summary["failed"] += 1
            continue
        if matched is not None and matched.video_id == video_asset.pk:
            summary["reused"] += 1

        poster_asset = None
        cover_url = str(item.get("cover") or "").strip()
        if cover_url:
            local_poster = _localized_image_url(
                cover_url, cache=image_cache, observed_at=observed_at
            )
            if local_poster.startswith(media_prefix):
                poster_asset = MediaAsset.objects.filter(
                    relative_path=local_poster[len(media_prefix) :]
                ).first()

        values = {
            "video": video_asset,
            "poster": poster_asset,
            "duration_ms": _duration_ms(item.get("duration")),
            "source_video_id": source_video_id,
            "source_url": source_url,
            "sort_order": index,
        }
        if matched is None:
            matched = SpuVideo.objects.create(spu=spu, **values)
        else:
            for field, value in values.items():
                setattr(matched, field, value)
            matched.save(update_fields=[*values.keys(), "updated_at"])
        matched_ids.add(matched.pk)

    if matched_ids:
        SpuVideo.objects.filter(spu=spu).exclude(pk__in=matched_ids).delete()
    return summary


def _import_gallery_images(spu, payload, *, observed_at, local_files: dict | None = None) -> dict:
    """Download the payload gallery into the media library (role=gallery).

    Best-effort: a failed CDN object is reported per-URL and never blocks
    the product import. Highest-resolution variants are expected to have
    been resolved by the crawler already.

    2026-11-10 提速：``local_files``（URL→dataset 已下载文件）命中的图片直接
    读本地文件，不再重复下载；其余图片并发下载，媒体写入/变体生成仍按顺序。
    """

    from media.pipeline import process_media_bytes
    from media.variants import link_asset_to_object

    summary = {"downloaded": 0, "failed": 0, "reused": 0}
    urls = [url for url in (payload.get("image_urls") or []) if url]
    local_files = local_files or {}
    payloads = _fetch_media_many(urls, local_files=local_files, fetcher=_fetch_image_bytes)
    for sort_order, (url, (data, from_local)) in enumerate(zip(urls, payloads)):
        if not data:
            summary["failed"] += 1
            continue
        if from_local:
            summary["reused"] += 1
        mime_type = "image/webp" if ".webp" in url else "image/jpeg"
        try:
            asset, _created = process_media_bytes(
                data,
                kind="PRODUCT",
                mime_type=mime_type,
                source_url=url,
                target=spu,
                role="gallery",
                observed_at=observed_at,
            )
            usage, _usage_created = link_asset_to_object(
                asset, spu, role="gallery", sort_order=sort_order
            )
            usage.sort_order = sort_order
            usage.save(update_fields=["sort_order"])
            summary["downloaded"] += 1
        except Exception:  # noqa: BLE001
            summary["failed"] += 1
    return summary


def _specification_label(specification) -> str:
    """Human-readable spec label used only in Chinese conflict messages."""

    if not isinstance(specification, dict) or not specification:
        return "规格为空"
    return "、".join(f"{name}={value}" for name, value in specification.items())


def _offer_identity_conflict_message(
    *,
    staging: StagingProduct,
    source_system: str,
    source_id: str,
    sku,
    merchant,
    market,
    currency,
    specification,
) -> str:
    """Build the Chinese, actionable message for an offer identity conflict.

    The English exception from ``offers.services`` is kept for the DEBUG log
    only. Users get the source identity, both sides of the mismatch and the
    likely cause (seller-name / locale drift), plus the manual next step.
    """

    identity = (
        OfferSourceIdentity.objects.select_related(
            "offer__sku", "offer__merchant", "offer__market", "offer__currency"
        )
        .filter(
            source_system=source_system.strip().casefold(),
            source_id=source_id.strip(),
        )
        .first()
    )
    if identity is None:
        return (
            f"商品 {staging.source_id} 的来源 Offer「{source_system}:{source_id}」校验失败，"
            "本次未导入。请检查来源标识与商家映射后重试；系统不会自动新建或改绑来源身份。"
        )

    existing = identity.offer
    differences = []
    if existing.sku_id != sku.pk:
        differences.append("SKU")
    if existing.merchant_id != merchant.pk:
        differences.append("商家")
    if existing.market_id != market.pk:
        differences.append("市场")
    if existing.currency_id != currency.pk:
        differences.append("币种")
    if not differences:
        # 身份归属其实一致：另一类 OfferSourceIdentityInvalid（例如同一观测
        # 时间已存在不同价格）不能误报成商家冲突。
        return (
            f"商品 {staging.source_id} 的来源 Offer「{source_system}:{source_id}」"
            "在本次观测时间已有不同的价格数据，导入未完成。"
            "这通常说明同一商品被并发重复导入，请稍后重试；系统不会覆盖已有价格快照。"
        )
    return (
        f"商品 {staging.source_id} 的来源 Offer「{source_system}:{source_id}」"
        f"已绑定到另一个 Offer：现有商家 {existing.merchant.display_name}/"
        f"{existing.merchant_id}、SKU（{_specification_label(existing.sku.specification)}）、"
        f"市场 {existing.market.code}、币种 {existing.currency.code}；"
        f"本次商家 {merchant.display_name}/{merchant.pk}、"
        f"SKU（{_specification_label(specification)}）、市场 {market.code}、"
        f"币种 {currency.code}；不一致：{'、'.join(differences)}。"
        "这通常不是重复导入，而是卖家名称/本地化变化（例如同一店铺在中英文站显示不同名称）"
        "导致同一来源身份解析到了不同商家。系统不会自动改绑已有 Offer，"
        "请检查商家映射（MerchantSourceMapping）后再导入。"
    )


def _sku_identity_conflict_message(
    *,
    staging: StagingProduct,
    source_system: str,
    source_id: str,
    spu,
    specification,
) -> str:
    """SKU-side counterpart of :func:`_offer_identity_conflict_message`."""

    from catalog.models import SkuSourceIdentity

    identity = (
        SkuSourceIdentity.objects.select_related("sku", "sku__spu")
        .filter(
            source_system=source_system.strip().casefold(),
            source_id=source_id.strip(),
        )
        .first()
    )
    if identity is None:
        return (
            f"商品 {staging.source_id} 的来源 SKU「{source_system}:{source_id}」校验失败，"
            "本次未导入。请检查来源标识后再重试；系统不会自动改绑来源身份。"
        )

    existing = identity.sku
    if existing.spu_id != spu.pk:
        return (
            f"商品 {staging.source_id} 的来源 SKU「{source_system}:{source_id}」"
            f"已绑定到另一个商品（现有 SPU {existing.spu.public_id}、"
            f"规格（{_specification_label(existing.specification)}）；"
            f"本次 SPU {spu.public_id}）。系统不会自动改绑，"
            "请确认来源商品 ID 没有被复用后再导入。"
        )
    return (
        f"商品 {staging.source_id} 的来源 SKU「{source_system}:{source_id}」"
        f"已绑定到同一商品下的另一个规格（现有规格"
        f"（{_specification_label(existing.specification)}）；"
        f"本次规格（{_specification_label(specification)}））。"
        "系统不会自动改绑；如果这是商品规格改版，请先核对历史 SKU 与来源身份的"
        "对应关系后再导入。"
    )


def import_staging_product(
    staging: StagingProduct,
    *,
    market,
    currency,
    locale: str = "en-GB",
    observed_at=None,
    local_media: dict | None = None,
) -> ImportOutcome:
    """Import one staged payload; rejects rows missing required fields.

    ``local_media`` 由爬虫 dataset 提供：``{"gallery": {url: 本地路径},
    "videos": {url: 本地路径}}``。命中的媒体直接读本地文件，不再重复下载
    （2026-11-10）；缺省时行为与以前完全一致。
    """

    payload = staging.payload or {}
    missing = [name for name in IMPORT_REQUIRED_FIELDS if not payload.get(name)]
    if missing:
        staging.missing_fields = sorted(set(missing))
        staging.status = StagingProduct.Status.REJECTED
        staging.error_message = f"缺少必填字段：{', '.join(missing)}。"
        staging.save(update_fields=["missing_fields", "status", "error_message", "updated_at"])
        raise StagingImportRejected(staging, missing)

    observed_at = observed_at or timezone.now()
    source_category = None
    # 菜单来源类目（docs/05 §9.2）：优先 payload["source_category_id"]（蜘蛛
    # 从任务所选类目写入）；旧 payload 只有 crawl_source_category_id，兜底回退。
    category_source_id = (payload.get("source_category_id") or "").strip() or (
        payload.get("crawl_source_category_id") or ""
    ).strip()
    if category_source_id:
        from catalog.models import SourceCategory

        source_category = SourceCategory.objects.filter(
            catalog__source_system=staging.source_system, source_id=category_source_id
        ).first()

    with transaction.atomic():
        brand = _resolve_brand(payload)
        product_category = _sync_product_categories(
            payload, source_system=staging.source_system, staging=staging
        )
        activity_source_id = str(payload.get("crawl_source_category_id") or "").strip()
        activity_source_name = str(payload.get("crawl_source_category_name") or "").strip()
        product_path = [
            item
            for item in (payload.get("product_category_path") or [])[:2]
            if isinstance(item, dict)
        ]
        product_category_ids = {str(item.get("id") or "").strip() for item in product_path}
        product_category_names = {str(item.get("name") or "").strip() for item in product_path}
        is_activity = (
            activity_source_id in ACTIVITY_SOURCE_CATEGORY_IDS
            or activity_source_name in ACTIVITY_SOURCE_CATEGORY_NAMES
            or bool(product_category_ids & ACTIVITY_PRODUCT_CATEGORY_IDS)
            or bool(product_category_names & ACTIVITY_PRODUCT_CATEGORY_NAMES)
        )
        spu, created_spu = get_or_create_spu_from_source(
            source_system=staging.source_system,
            source_id=staging.source_id,
            source_url=staging.source_url,
            source_category=source_category,
            brand=brand,
            local_category=(None if is_activity else _resolve_local_category(source_category)),
            product_category=product_category,
            is_activity=is_activity,
            title=payload["title"],
            locale=locale,
        )
        # 抓取价=入库价=零售价：payload 原价 → Spu.retail_price（新建必填、
        # 重导覆盖；价格缺失/非法/低于成本价约束时保留旧值）。
        _apply_spu_retail_price(spu, payload)
        translation, _ = SpuTranslation.objects.get_or_create(
            spu=spu,
            locale=locale,
            defaults={"title": payload["title"]},
        )
        content_values = {"title": payload["title"]}
        if (payload.get("description") or "").strip():
            content_values["description"] = payload["description"].strip()
        apply_source_field_values(
            translation,
            content_values,
            source_system=staging.source_system,
            observed_at=observed_at,
        )

        merchant = resolve_import_merchant(
            source_system=staging.source_system,
            source_seller_id=payload.get("source_seller_id") or None,
            source_name=payload.get("source_seller_name") or "",
            source_url=staging.source_url,
        )

        # WP-45 阶段 2：payload 带 variants 时按变体建多 SKU。系列轴的值可能
        # 指向源站「兄弟商品」（另一个源商品页），先按同源口径拆分：只有与主
        # SKU 同属一个源商品的变体才建本地 SKU，跨商品轴值跳过并记日志。
        same_source_variants, sibling_variants = _split_variants_by_same_source(payload)
        # 「上架即可售」惯例（仅 WP-45 多变体路径）：本次导入新建的 Offer 直接
        # ACTIVE 并写 listed_at；重导入命中已有 Offer 一律不动归属/状态/价格层。
        activate_new_offers = bool(same_source_variants)
        main_sku_source_ids = {
            str(item.get("source_id") or "").strip()
            for item in payload.get("skus") or []
            if isinstance(item, dict) and item.get("source_id")
        }

        skus = []
        offers = []
        new_offer_ids = set()
        for index, sku_payload in enumerate(payload.get("skus") or []):
            specification = {
                spec["name"]: spec["value"]
                for spec in sku_payload.get("specs") or []
                if spec.get("name")
            }
            try:
                sku, _created_sku = get_or_create_sku_from_source(
                    spu=spu,
                    source_system=staging.source_system,
                    source_id=sku_payload["source_id"],
                    specification=specification,
                    skip_attribute_validation=True,
                )
            except ProductSourceIdentityInvalid as exc:
                # 旧 SKU 规格为空、现在解析出了规格：同一来源身份沿用，只补
                # 源层规格；无法安全补全时上抛中文冲突提示（事件码固定）。
                adopted = _adopt_enriched_specification(
                    spu=spu,
                    source_system=staging.source_system,
                    source_id=sku_payload["source_id"],
                    specification=specification,
                    source_url=staging.source_url,
                )
                if adopted is None:
                    logger.debug(
                        "SKU source identity conflict for %s#%s: %s",
                        staging.source_id,
                        sku_payload["source_id"],
                        exc,
                        exc_info=True,
                    )
                    raise ImportSourceConflict(
                        _sku_identity_conflict_message(
                            staging=staging,
                            source_system=staging.source_system,
                            source_id=sku_payload["source_id"],
                            spu=spu,
                            specification=specification,
                        )
                    ) from exc
                sku = adopted
            skus.append(sku)
            offer_source_id = f"{staging.source_id}#{sku_payload['source_id']}"
            try:
                offer, offer_created = import_offer_from_source(
                    sku=sku,
                    merchant=merchant,
                    market=market,
                    currency=currency,
                    source_system=staging.source_system,
                    source_id=offer_source_id,
                    current_price=sku_payload.get("price") or payload["current_price"],
                    list_price=payload.get("list_price"),
                    source_availability=sku_payload.get("availability")
                    or Offer.SourceAvailability.UNKNOWN,
                    source_url=staging.source_url,
                    promotion_label=payload.get("promotion_label") or "",
                    observed_at=observed_at,
                )
            except OfferSourceIdentityInvalid as exc:
                logger.debug(
                    "Offer source identity conflict for %s: %s",
                    offer_source_id,
                    exc,
                    exc_info=True,
                )
                raise ImportSourceConflict(
                    _offer_identity_conflict_message(
                        staging=staging,
                        source_system=staging.source_system,
                        source_id=offer_source_id,
                        sku=sku,
                        merchant=merchant,
                        market=market,
                        currency=currency,
                        specification=specification,
                    )
                ) from exc
            offers.append(offer)
            offer_source_values = {
                "promotion_label": payload.get("promotion_label") or "",
                "current_price": offer.current_price,
            }
            if offer.list_price is not None:
                offer_source_values["list_price"] = offer.list_price
            apply_source_field_values(
                offer,
                offer_source_values,
                source_system=staging.source_system,
                observed_at=observed_at,
            )
            if offer_created:
                new_offer_ids.add(offer.pk)
                if activate_new_offers:
                    offer.status = Offer.Status.ACTIVE
                    offer.listed_at = observed_at
                    offer.save(update_fields=["status", "listed_at", "updated_at"])

        # —— WP-45 阶段 2：同源变体逐个建 SKU / Offer / 变体图 ——
        variant_summary = {
            "kept": len(same_source_variants),
            "skipped_cross_product": len(sibling_variants),
            "skipped_no_spec": 0,
            "skipped_identity_conflict": 0,
            "skus_created": 0,
            "offers_created": 0,
            "offers_skipped_no_price": 0,
            "images_localized": 0,
            "images_failed": 0,
        }
        for variant in same_source_variants:
            variant_sku_id = str(variant.get("source_sku_id") or "").strip()
            # 主变体（与顶层 skus[].source_id 相同）已由上面的 skus 循环处理：
            # 旧单 SKU 身份在那里原地升级（补 specification + 重算签名），
            # 不在这里重建。
            if not variant_sku_id or variant_sku_id in main_sku_source_ids:
                continue
            specification = {
                str(name).strip(): value
                for name, value in (variant.get("specification") or {}).items()
                if str(name).strip()
            }
            if not specification:
                # 无规格名值对的变体无法在 PDP 被选中，按「宁缺毋假」跳过。
                variant_summary["skipped_no_spec"] += 1
                logger.info(
                    "WP45 variant %s of product %s has no specification; skipped.",
                    variant_sku_id,
                    staging.source_id,
                )
                continue
            try:
                sku, variant_sku_created = get_or_create_sku_from_source(
                    spu=spu,
                    source_system=staging.source_system,
                    source_id=variant_sku_id,
                    specification=specification,
                    source_url=staging.source_url,
                    skip_attribute_validation=True,
                )
            except ProductSourceIdentityInvalid as exc:
                # 身份冲突不是重复，绝不自动重绑（WP-45 阶段 2 设计注意 #1）。
                # 实抓场景：同一源 sku 早已作为「兄弟商品」独立导入过（它自己
                # 的源商品页有自己的 SPU + 身份）。此时跳过该变体并记日志，
                # 不阻断整单导入，也不动已有身份；仅当身份已绑定到同一 SPU
                # 下另一个规格（商品规格改版）时才作为硬冲突上抛。
                variant_identity = (
                    SkuSourceIdentity.objects.select_related("sku", "sku__spu")
                    .filter(
                        source_system=staging.source_system.strip().casefold(),
                        source_id=variant_sku_id,
                    )
                    .first()
                )
                if variant_identity is not None and variant_identity.sku.spu_id != spu.pk:
                    variant_summary["skipped_identity_conflict"] += 1
                    logger.info(
                        "WP45 variant %s of product %s already imported as its own "
                        "product (SPU %s); variant skipped, existing identity untouched.",
                        variant_sku_id,
                        staging.source_id,
                        variant_identity.sku.spu.public_id,
                    )
                    continue
                logger.debug(
                    "Variant SKU source identity conflict for %s#%s: %s",
                    staging.source_id,
                    variant_sku_id,
                    exc,
                    exc_info=True,
                )
                raise ImportSourceConflict(
                    _sku_identity_conflict_message(
                        staging=staging,
                        source_system=staging.source_system,
                        source_id=variant_sku_id,
                        spu=spu,
                        specification=specification,
                    )
                ) from exc
            skus.append(sku)
            if variant_sku_created:
                variant_summary["skus_created"] += 1

            image_url = str(variant.get("image_url") or "").strip()
            if image_url:
                if _import_variant_image(sku, image_url, observed_at=observed_at):
                    variant_summary["images_localized"] += 1
                else:
                    variant_summary["images_failed"] += 1

            variant_price = str(variant.get("price") or "").strip()
            variant_price_source = str(variant.get("price_source") or "").strip()
            if not variant_price or variant_price_source not in VARIANT_TRUSTED_PRICE_SOURCES:
                # 价格留空/来源不可信（开关关闭、补抓失败、超上限）：只建 SKU
                # 不建 Offer，SKU 保留但不可购；不得用 SPU 价格冒充变体价。
                variant_summary["offers_skipped_no_price"] += 1
                continue
            variant_offer_source_id = f"{staging.source_id}#{variant_sku_id}"
            try:
                variant_offer, variant_offer_created = import_offer_from_source(
                    sku=sku,
                    merchant=merchant,
                    market=market,
                    currency=currency,
                    source_system=staging.source_system,
                    source_id=variant_offer_source_id,
                    current_price=variant_price,
                    list_price=None,
                    source_availability=Offer.SourceAvailability.UNKNOWN,
                    source_url=staging.source_url,
                    promotion_label="",
                    observed_at=observed_at,
                )
            except OfferSourceIdentityInvalid as exc:
                logger.debug(
                    "Variant offer source identity conflict for %s: %s",
                    variant_offer_source_id,
                    exc,
                    exc_info=True,
                )
                raise ImportSourceConflict(
                    _offer_identity_conflict_message(
                        staging=staging,
                        source_system=staging.source_system,
                        source_id=variant_offer_source_id,
                        sku=sku,
                        merchant=merchant,
                        market=market,
                        currency=currency,
                        specification=specification,
                    )
                ) from exc
            offers.append(variant_offer)
            apply_source_field_values(
                variant_offer,
                {"promotion_label": "", "current_price": variant_offer.current_price},
                source_system=staging.source_system,
                observed_at=observed_at,
            )
            if variant_offer_created:
                variant_summary["offers_created"] += 1
                if activate_new_offers:
                    variant_offer.status = Offer.Status.ACTIVE
                    variant_offer.listed_at = observed_at
                    variant_offer.save(update_fields=["status", "listed_at", "updated_at"])

        gallery_summary = _import_gallery_images(
            spu,
            payload,
            observed_at=observed_at,
            local_files=(local_media or {}).get("gallery"),
        )
        detail_summary = _sync_spu_detail(spu, payload, observed_at=observed_at)
        video_summary = _import_spu_videos(
            spu,
            payload,
            observed_at=observed_at,
            local_files=(local_media or {}).get("videos"),
        )

        staging.missing_fields = sorted(set(payload.get("missing_fields") or []))
        staging.status = StagingProduct.Status.IMPORTED
        staging.imported_at = observed_at
        staging.error_message = ""
        # 导入完成后刷新该 SPU 的搜索文档（WP-45 阶段 2）：多变体多 Offer 会
        # 自然形成 min/max 价格区间；SPU 非 ACTIVE 或无可购 Offer 时文档被清空
        # （与既有口径一致），运营上架后再刷新即可露出。
        from catalog.search_services import refresh_spu_search_documents

        search_docs_removed = refresh_spu_search_documents(spu)
        staging.imported_refs = {
            "spu_public_id": str(spu.public_id),
            "sku_count": len(skus),
            "offer_count": len(offers),
            "new_active_offers": (
                len(new_offer_ids) + variant_summary["offers_created"] if activate_new_offers else 0
            ),
            "variants": variant_summary,
            "gallery_images": gallery_summary,
            "detail": detail_summary,
            "videos": video_summary,
            "search_docs_removed": search_docs_removed,
        }
        staging.save(
            update_fields=[
                "missing_fields",
                "status",
                "imported_at",
                "error_message",
                "imported_refs",
                "updated_at",
            ]
        )
        return ImportOutcome(
            staging=staging,
            spu=spu,
            created_spu=created_spu,
            skus=skus,
            offers=offers,
        )
