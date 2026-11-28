"""A03 商品池管理 / A04 商家商品管理。

商品池复用 ``catalog.Spu``（爬虫导入、商城详情、搜索都基于它），
店铺商品关系复用 ``offers.Offer``（merchant × sku × market），
两边都不新建并行表，避免同一件商品有两套主档。
"""

import uuid

from django.conf import settings
from django.db import transaction
from django.db.models import Count, F, Func, IntegerField, Prefetch, Q, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.response import Response

from accounts_staff.api_exceptions import StaffApiError
from accounts_staff.permissions import StaffRbacPermission
from audit.services import record_audit
from catalog.detail_views import _spec_options_payload, _video_payload
from catalog.models import (
    LOCAL_PARENT_MERCHANT_CATEGORY,
    LocalCategory,
    Sku,
    Spu,
    SpuDetail,
    SpuTranslation,
    SpuVideo,
)
from media.models import MediaUsage
from media.storage import media_url
from merchant_ops.api_utils import (
    OpsAPIView,
    iso,
    money_str,
    paginate,
    parse_amount,
    require,
)
from merchant_ops.localization import pick_title
from offers.models import Offer

MAX_IMAGES = 5


def _category_payload(category: LocalCategory | None) -> dict | None:
    if category is None:
        return None
    return {
        "id": str(category.public_id),
        "name": category.name,
        "name_zh": category.name_zh,
        "name_en": category.name_en,
        "path": category.path,
    }


def _primary_images(spu_ids) -> dict:
    """批量取商品主图：优先主图角色，其次任意排序最小的图片。"""

    if not spu_ids:
        return {}
    from django.contrib.contenttypes.models import ContentType

    content_type = ContentType.objects.get_for_model(Spu)
    usages = (
        MediaUsage.objects.select_related("asset")
        .filter(content_type=content_type, object_id__in=spu_ids)
        .order_by("object_id", "sort_order", "pk")
    )
    result = {}
    for usage in usages:
        result.setdefault(usage.object_id, media_url(usage.asset.relative_path))
    return result


def _title_for(spu: Spu, locale: str | None = None) -> str:
    # 列表视图用 Prefetch(to_attr="list_translations") 只取标题列，避免把
    # spu_translation.description 长文本也拉回来；详情视图仍用 translations.all()。
    translations = getattr(spu, "list_translations", None)
    if translations is None:
        translations = list(spu.translations.all())
    # 商家端按请求语言取标题（缺失回退原文语言）；管理端不传 locale，走原口径。
    if locale:
        title = pick_title(translations, locale)
        if title:
            return title
    for code in ("zh-CN", "zh", "en-GB", "en"):
        for translation in translations:
            if translation.locale == code and translation.title:
                return translation.title
    return translations[0].title if translations else f"SPU {str(spu.public_id)[:8]}"


AI_SUMMARY_PREVIEW_LEN = 80


def _preview_ai_summary(ai_summary) -> str:
    text = (ai_summary or "").strip()
    if len(text) > AI_SUMMARY_PREVIEW_LEN:
        text = text[:AI_SUMMARY_PREVIEW_LEN] + "…"
    return text


def _detail_summary(detail, *, video_count=0) -> dict:
    """商品池列表用的爬虫详情摘要（不携带完整 JSON 块，保持列表轻量）。"""

    if detail is None:
        return {
            "has_detail": False,
            "video_count": video_count,
            "section_count": 0,
            "spec_table_count": 0,
            "ai_summary": "",
            "source_updated_at": None,
        }
    return {
        "has_detail": True,
        "video_count": video_count,
        "section_count": len(detail.content_sections or []),
        "spec_table_count": len(detail.specification_tables or []),
        "ai_summary": _preview_ai_summary(detail.ai_summary),
        "source_updated_at": iso(detail.source_observed_at or detail.updated_at),
    }


def _detail_summaries(spu_ids) -> dict:
    """批量取列表页的详情摘要（2026-11-28 性能优化）。

    列表只需要「区块数 / 规格表数 / AI 摘要预览 / 来源时间」，不需要
    ``content_sections`` / ``specification_tables`` 的整块 JSON。之前列表
    用 ``select_related("detail")`` 会把这两个大字段连同规格选项一起
    SELECT 出来，这里改成只算 ``JSON_LENGTH``，单页只传 ai_summary 文本。
    """

    if not spu_ids:
        return {}
    rows = (
        SpuDetail.objects.filter(spu_id__in=spu_ids)
        .annotate(
            section_count=Coalesce(
                Func(F("content_sections"), function="JSON_LENGTH"),
                Value(0),
                output_field=IntegerField(),
            ),
            spec_table_count=Coalesce(
                Func(F("specification_tables"), function="JSON_LENGTH"),
                Value(0),
                output_field=IntegerField(),
            ),
        )
        .values(
            "spu_id",
            "ai_summary",
            "source_observed_at",
            "updated_at",
            "section_count",
            "spec_table_count",
        )
    )
    return {row["spu_id"]: row for row in rows}


def _detail_summary_from_row(row, *, video_count=0) -> dict:
    if row is None:
        return _detail_summary(None, video_count=video_count)
    return {
        "has_detail": True,
        "video_count": video_count,
        "section_count": row["section_count"] or 0,
        "spec_table_count": row["spec_table_count"] or 0,
        "ai_summary": _preview_ai_summary(row["ai_summary"]),
        "source_updated_at": iso(row["source_observed_at"] or row["updated_at"]),
    }


def _spu_payload(spu: Spu, *, images=None, stores=0, detail_summary=None, locale=None) -> dict:
    images = images or []
    summary = detail_summary or _detail_summary(None)
    return {
        "id": str(spu.public_id),
        "name": _title_for(spu, locale),
        "category": _category_payload(spu.local_category),
        "cost": money_str(spu.cost_price) if spu.cost_price is not None else None,
        "price": money_str(spu.retail_price) if spu.retail_price is not None else None,
        "images": list(spu.image_urls or []) or images,
        "specs": list(spu.specs or []),
        "description": spu.description,
        "status": spu.status,
        "stores": stores,
        "activity": spu.is_activity,
        "merchant_category": spu.merchant_category,
        "merchant_category_label": Spu.merchant_category_label(spu.merchant_category),
        "sku_count": getattr(spu, "sku_total", None),
        "created_at": iso(spu.created_at),
        # 爬虫详情摘要（增量字段，旧消费方可忽略）。
        "has_detail": summary["has_detail"],
        "video_count": summary["video_count"],
        "section_count": summary["section_count"],
        "spec_table_count": summary["spec_table_count"],
        "ai_summary": summary["ai_summary"],
        "source_updated_at": summary["source_updated_at"],
    }


def _product_category_breadcrumb(spu: Spu) -> list[dict]:
    """爬到的商品类目（最多两级），与购物端 category_breadcrumb 同构。"""

    breadcrumb = []
    node = spu.product_category
    while node is not None and len(breadcrumb) < 2:
        breadcrumb.append({"id": node.source_id, "name": node.name, "depth": node.depth})
        node = node.parent
    breadcrumb.reverse()
    return breadcrumb


def _gallery_urls(spu: Spu) -> list[str]:
    """商品全部图片：媒体库画廊（爬虫导入）在前，手工 image_urls 去重补后。"""

    from django.contrib.contenttypes.models import ContentType

    content_type = ContentType.objects.get_for_model(Spu)
    urls = [
        media_url(usage.asset.relative_path)
        for usage in MediaUsage.objects.select_related("asset")
        .filter(content_type=content_type, object_id=spu.pk, role="gallery")
        .order_by("sort_order", "pk")
    ]
    for url in spu.image_urls or []:
        if url and url not in urls:
            urls.append(url)
    return urls


class AdminProductPoolView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["catalog.pool.manage"]
    view_permissions = ["catalog.pool.view"]

    # 列表只取页面真正用到的列（编辑弹窗也从行数据回填 description/images/specs）。
    # 不包含 SpuDetail 的 JSON 大字段——详情摘要由 ``_detail_summaries`` 用
    # JSON_LENGTH 单独算，见 2026-11-28 性能优化。
    list_fields = (
        "id",
        "public_id",
        "local_category_id",
        "status",
        "cost_price",
        "retail_price",
        "is_activity",
        "merchant_category",
        "description",
        "image_urls",
        "specs",
        "created_at",
        "local_category__public_id",
        "local_category__name",
        "local_category__name_zh",
        "local_category__name_en",
        "local_category__path",
    )

    def _queryset(self, request):
        # 2026-11-28：不再 select_related("detail")（OneToOne 的整行大 JSON
        # 会被一起 SELECT），只按需取摘要；translations 只 preload 标题列。
        queryset = (
            Spu.objects.select_related("local_category")
            .prefetch_related(
                Prefetch(
                    "translations",
                    queryset=SpuTranslation.objects.only("spu_id", "locale", "title"),
                    to_attr="list_translations",
                )
            )
            .only(*self.list_fields)
        )
        query = (request.query_params.get("q") or "").strip()
        if query:
            # 用子查询代替 translations JOIN：原写法为了去重必须 DISTINCT，
            # 而 DISTINCT + ORDER BY + LIMIT 会让 MySQL 把 2.3 万行整行放进
            # 临时表做 filesort（实测单条 SQL 588ms）。子查询不会产生重复行。
            condition = Q(
                pk__in=SpuTranslation.objects.filter(title__icontains=query).values("spu_id")
            )
            try:
                condition |= Q(public_id=uuid.UUID(query))
            except ValueError:
                pass
            # 2026-11-28 可搜索下拉框：支持按部分 UUID 前缀搜商品（完整 UUID 走上面的精确分支）。
            condition |= Q(public_id__icontains=query)
            queryset = queryset.filter(condition)
        category = (request.query_params.get("category") or "").strip()
        if category:
            # 按整棵子树匹配：管理端筛选只展示父类目，而商品大量挂在二级类目上，
            # 只按父类目精确匹配会漏掉子类目商品。
            node = (
                LocalCategory.objects.filter(public_id=category).only("path").first()
                if _is_uuid(category)
                else LocalCategory.objects.filter(slug=category).only("path").first()
            )
            queryset = (
                queryset.filter(local_category__path__startswith=node.path)
                if node is not None
                else queryset.none()
            )
        status = (request.query_params.get("status") or "").strip().upper()
        if status and status != "ALL":
            queryset = queryset.filter(status=status)
        if request.query_params.get("activity") in {"1", "true"}:
            queryset = queryset.filter(is_activity=True)
        # 原 ``.distinct()`` 是无条件加的（为了 translations JOIN 去重），但没有
        # q 时并不需要；q 改成子查询后任何时候都不会有重复行，这里不再 distinct。
        return queryset.order_by("-created_at", "-pk")

    def get(self, request):
        rows, meta = paginate(self._queryset(request), request)
        ids = [spu.pk for spu in rows]
        images = _primary_images(ids)
        store_counts = dict(
            Offer.objects.filter(sku__spu_id__in=ids, status=Offer.Status.ACTIVE)
            .values("sku__spu_id")
            .annotate(total=Count("merchant_id", distinct=True))
            .values_list("sku__spu_id", "total")
        )
        sku_counts = dict(
            Sku.objects.filter(spu_id__in=ids)
            .values("spu_id")
            .annotate(total=Count("pk"))
            .values_list("spu_id", "total")
        )
        video_counts = dict(
            SpuVideo.objects.filter(spu_id__in=ids)
            .values("spu_id")
            .annotate(total=Count("pk"))
            .values_list("spu_id", "total")
        )
        detail_summaries = _detail_summaries(ids)
        for spu in rows:
            spu.sku_total = sku_counts.get(spu.pk, 0)
        return Response(
            {
                "items": [
                    _spu_payload(
                        spu,
                        images=[images[spu.pk]] if spu.pk in images else [],
                        stores=store_counts.get(spu.pk, 0),
                        detail_summary=_detail_summary_from_row(
                            detail_summaries.get(spu.pk),
                            video_count=video_counts.get(spu.pk, 0),
                        ),
                    )
                    for spu in rows
                ],
                **meta,
            }
        )

    def post(self, request):
        payload = request.data or {}
        name = require(payload, "name", label="商品名称").strip()
        if len(name) > 80:
            raise StaffApiError(
                business_code="NAME_TOO_LONG", message="商品名称不能超过 80 个字。", status_code=400
            )
        # 成本价可选（2026-11-10）：爬虫商品没有成本价，留空 = NULL；
        # 填了则必须大于 0。零售价仍必填。
        cost = (
            parse_amount(payload["cost"], field="成本价")
            if payload.get("cost") not in (None, "")
            else None
        )
        if cost is not None and cost <= 0:
            raise StaffApiError(
                business_code="PRICE_INVALID", message="成本价必须大于 0。", status_code=400
            )
        price = parse_amount(payload.get("price"), field="零售价")
        if price <= 0:
            raise StaffApiError(
                business_code="PRICE_INVALID", message="零售价必须大于 0。", status_code=400
            )
        if cost is not None and price < cost:
            raise StaffApiError(
                business_code="PRICE_BELOW_COST",
                message="零售价不得低于成本价。",
                status_code=400,
            )
        images, specs = _validated_media_payload(payload)
        category = _resolve_category(payload.get("category"))
        merchant_category = _validated_merchant_category(payload.get("merchant_category"))

        spu = Spu.objects.create(
            local_category=category,
            merchant_category=merchant_category,
            status=payload.get("status")
            if payload.get("status") in dict(Spu.Status.choices)
            else Spu.Status.ACTIVE,
            cost_price=cost,
            retail_price=price,
            is_activity=bool(payload.get("activity")),
            description=(payload.get("description") or "").strip(),
            image_urls=images,
            specs=specs,
        )
        SpuTranslation.objects.create(
            spu=spu,
            locale="zh-CN",
            title=name,
            description=spu.description,
        )
        record_audit(
            request=request,
            actor=request.staff_account,
            action="PRODUCT_CREATED",
            target_type="spu",
            target_id=str(spu.public_id),
            reason="",
            before_state={},
            after_state={
                "name": name,
                "cost": str(cost) if cost is not None else "",
                "price": str(price),
            },
        )
        _refresh_search_documents(spu)
        return Response({"product": _spu_payload(spu, images=images)}, status=201)


class AdminProductPoolDetailView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["catalog.pool.manage"]
    view_permissions = ["catalog.pool.view"]

    def _get(self, public_id):
        spu = (
            Spu.objects.select_related("local_category", "detail", "product_category__parent")
            .prefetch_related("translations", "videos__video", "videos__poster")
            .filter(public_id=public_id)
            .first()
        )
        if spu is None:
            raise StaffApiError(
                business_code="PRODUCT_NOT_FOUND", message="商品不存在。", status_code=404
            )
        return spu

    def get(self, request, public_id):
        spu = self._get(public_id)
        spu.sku_total = spu.skus.count()
        images = _primary_images([spu.pk])
        stores = (
            Offer.objects.filter(sku__spu=spu, status=Offer.Status.ACTIVE)
            .values("merchant_id")
            .distinct()
            .count()
        )
        detail = getattr(spu, "detail", None)
        videos = list(spu.videos.all())
        payload = _spu_payload(
            spu,
            images=[images[spu.pk]] if spu.pk in images else [],
            stores=stores,
            detail_summary=_detail_summary(detail, video_count=len(videos)),
        )
        payload["skus"] = [
            {
                "id": str(sku.public_id),
                "specification": sku.specification,
                "merchant_sku": sku.merchant_sku,
                "status": sku.status,
            }
            for sku in spu.skus.all()[:50]
        ]
        # --- 爬虫详情增量字段（只读展示，旧字段全部保留）---
        payload["gallery"] = _gallery_urls(spu)
        payload["content_sections"] = detail.content_sections if detail else []
        # content_sections 的来源（crawler/manual）：manual 表示管理端人工编辑过，
        # 爬虫重导入不会覆盖图文区块。
        payload["content_source"] = detail.content_source if detail else None
        payload["specification_tables"] = detail.specification_tables if detail else []
        payload["specifications"] = detail.specifications if detail else []
        # spec_options 的 sku_ids 与购物端一样映射为 Sku.public_id。
        payload["spec_options"] = _spec_options_payload(spu, detail.spec_options if detail else [])
        payload["ai_summary"] = detail.ai_summary if detail else ""
        payload["ai_summary_title"] = detail.ai_summary_title if detail else ""
        payload["ai_summary_tags"] = detail.ai_summary_tags if detail else []
        payload["videos"] = _video_payload(spu)
        # 爬到的商品类目（最多两级），只读参考。
        payload["product_category"] = _product_category_breadcrumb(spu)
        return Response({"product": payload})

    def patch(self, request, public_id):
        spu = self._get(public_id)
        payload = request.data or {}
        before = {
            "name": _title_for(spu),
            "cost": str(spu.cost_price),
            "price": str(spu.retail_price),
            "status": spu.status,
            "activity": spu.is_activity,
        }

        if "name" in payload:
            name = (payload.get("name") or "").strip()
            if not name:
                raise StaffApiError(
                    business_code="NAME_REQUIRED", message="商品名称不能为空。", status_code=400
                )
            translation = (
                spu.translations.filter(locale="zh-CN").first() or spu.translations.first()
            )
            if translation is None:
                SpuTranslation.objects.create(spu=spu, locale="zh-CN", title=name)
            else:
                translation.title = name
                translation.save(update_fields=["title", "updated_at"])

        # 成本价可选（2026-11-10）：不带 cost 键 = 保持不变；带键且为空 = 清空
        # （爬虫商品本来就没有成本价）；带键且有值 = 必须是大于 0 的数字。
        if "cost" in payload:
            if payload.get("cost") in (None, ""):
                cost = None
            else:
                cost = parse_amount(payload["cost"], field="成本价")
                if cost <= 0:
                    raise StaffApiError(
                        business_code="PRICE_INVALID", message="成本价必须大于 0。", status_code=400
                    )
        else:
            cost = spu.cost_price
        price = (
            parse_amount(payload["price"], field="零售价")
            if payload.get("price") not in (None, "")
            else spu.retail_price
        )
        if cost is not None and price is not None and price < cost:
            raise StaffApiError(
                business_code="PRICE_BELOW_COST",
                message="零售价不得低于成本价。",
                status_code=400,
            )
        if "cost" in payload:
            spu.cost_price = cost
        if "price" in payload:
            spu.retail_price = price
        if "category" in payload:
            spu.local_category = _resolve_category(payload.get("category"))
        if "merchant_category" in payload:
            spu.merchant_category = _validated_merchant_category(payload.get("merchant_category"))
        if "description" in payload:
            spu.description = (payload.get("description") or "").strip()
        if "activity" in payload:
            spu.is_activity = bool(payload.get("activity"))
        if "status" in payload and payload.get("status") in dict(Spu.Status.choices):
            spu.status = payload["status"]
        if "images" in payload or "specs" in payload:
            images, specs = _validated_media_payload(payload)
            spu.image_urls = images
            spu.specs = specs
        spu.save()
        # 品类/名称/价格/状态变化都要同步搜索文档，否则购物端类目页与搜索还是旧数据。
        _refresh_search_documents(spu)
        if "cost" in payload or "price" in payload:
            # 已上架商品的成本价按零售价×折扣实时折算（2026-11-10 口径），
            # 零售价变化会改变成本价；商品池 cost_price 虽不参与公式，
            # 带着也重算一次无副作用（幂等）。
            from merchant_ops.services import reprice_listed_offers

            reprice_listed_offers(spu=spu)

        # 图文详情（content_sections）人工编辑：保存进 SpuDetail 并标记
        # content_source=manual，此后爬虫重导入不再覆盖图文区块（docs/14 §9.9）。
        saved_sections = None
        if "content_sections" in payload:
            sections = _validated_content_sections(payload.get("content_sections"))
            existing_detail = SpuDetail.objects.filter(spu=spu).first()
            sections_before = len(existing_detail.content_sections or []) if existing_detail else 0
            detail, _created = SpuDetail.objects.get_or_create(spu=spu)
            detail.content_sections = sections
            detail.content_source = SpuDetail.ContentSource.MANUAL
            detail.save(update_fields=["content_sections", "content_source", "updated_at"])
            saved_sections = sections
            record_audit(
                request=request,
                actor=request.staff_account,
                action="PRODUCT_DETAIL_UPDATED",
                target_type="spu",
                target_id=str(spu.public_id),
                reason="",
                before_state={"section_count": sections_before},
                after_state={
                    "section_count": len(sections),
                    "content_source": SpuDetail.ContentSource.MANUAL,
                },
            )

        record_audit(
            request=request,
            actor=request.staff_account,
            action="PRODUCT_UPDATED",
            target_type="spu",
            target_id=str(spu.public_id),
            reason="",
            before_state=before,
            after_state={
                "name": _title_for(spu),
                "cost": str(spu.cost_price),
                "price": str(spu.retail_price),
                "status": spu.status,
                "activity": spu.is_activity,
            },
        )
        response_payload = _spu_payload(spu, images=list(spu.image_urls or []))
        if saved_sections is not None:
            # 本次请求改过图文详情：回包带上保存后的区块，前端据此刷新抽屉。
            response_payload["content_sections"] = saved_sections
            response_payload["content_source"] = SpuDetail.ContentSource.MANUAL
        return Response({"product": response_payload})


def _activate_offers_on_publish(spu) -> int:
    """管理端上架即可售：把该商品的商家报价一并开售（2026-11-10 口径）。

    - `DRAFT`：导入/建池后从未上架的报价，平台上架时一并开售；
    - `INACTIVE` 且 `removed_by_platform=True`：恢复平台下架前的报价；
    - `INACTIVE` 且 `removed_by_platform=False`（商家自己下架）：不动，尊重商家意愿；
    - 只处理接单中（`onboarding_status=ACTIVE`）的商家，封店/关店商家的报价不复活；
      爬虫导入的商家可能还没走完入驻审核（`admission_approved=False`），平台主动
      上架不受此限制（否则这批商品永远无法出现在购物端）。

    成本价按当前零售价 × (1 − 商家折扣%) 重算，成交价同步为零售价。
    商品既没有可激活的报价、也没有已上架报价时抛 400（否则「上架」后
    购物端永远搜不到）；需要激活且有零售价缺失时同样抛 400。
    返回激活的 Offer 行数。
    """

    from merchant_ops.services import compute_listing_cost
    from merchants.models import Merchant

    has_active = Offer.objects.filter(sku__spu=spu, status=Offer.Status.ACTIVE).exists()
    candidates = [
        offer
        for offer in Offer.objects.filter(sku__spu=spu)
        .exclude(status=Offer.Status.ACTIVE)
        .select_related("merchant")
        if offer.status == Offer.Status.DRAFT or offer.removed_by_platform
    ]
    candidates = [
        offer
        for offer in candidates
        if offer.merchant.onboarding_status == Merchant.OnboardingStatus.ACTIVE
    ]
    if not candidates:
        if has_active:
            return 0
        raise StaffApiError(
            business_code="PRODUCT_OFFER_MISSING",
            message="该商品没有可上架的商家报价（报价未激活或商家已停止接单），无法在购物端上架。",
            status_code=400,
        )
    if spu.retail_price is None:
        raise StaffApiError(
            business_code="PRODUCT_PRICE_MISSING",
            message="商品缺少零售价，不能上架到购物端。",
            status_code=400,
        )

    now = timezone.now()
    for offer in candidates:
        Offer.objects.filter(pk=offer.pk).update(
            status=Offer.Status.ACTIVE,
            current_price=spu.retail_price,
            cost_price=compute_listing_cost(offer.merchant, spu),
            listed_at=now,
            removed_at=None,
            removed_by_platform=False,
            updated_at=now,
        )
    return len(candidates)


class AdminProductPoolActionsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["catalog.pool.manage"]
    view_permissions = ["catalog.pool.view"]

    def post(self, request, public_id):
        spu = Spu.objects.filter(public_id=public_id).first()
        if spu is None:
            raise StaffApiError(
                business_code="PRODUCT_NOT_FOUND", message="商品不存在。", status_code=404
            )
        action = ((request.data or {}).get("action") or "").strip().lower()
        before = {"status": spu.status, "activity": spu.is_activity}
        activated_offers = 0
        with transaction.atomic():
            if action == "publish":
                # 上架即可售：先激活报价（失败则整笔回滚，状态不变），再改状态。
                activated_offers = _activate_offers_on_publish(spu)
                spu.status = Spu.Status.ACTIVE
            elif action == "unpublish":
                spu.status = Spu.Status.INACTIVE
            elif action in {"mark_activity", "unmark_activity"}:
                # 活动商品管理（WP-42）：只打/去标记，不改变原品类。
                spu.is_activity = action == "mark_activity"
            else:
                raise StaffApiError(
                    business_code="ACTION_UNSUPPORTED", message="不支持的操作。", status_code=400
                )
            spu.save(
                update_fields=(
                    ["status", "updated_at"]
                    if action in {"publish", "unpublish"}
                    else ["is_activity", "updated_at"]
                )
            )
        # 迭代02：平台下架 → 商家端和购物端统一下掉——把该商品所有商家 ACTIVE
        # Offer 一并下架（removed_by_platform 留痕，历史行保留），并即时刷新搜索文档。
        cascade_offers = 0
        if action == "unpublish":
            cascade_offers = Offer.objects.filter(sku__spu=spu, status=Offer.Status.ACTIVE).update(
                status=Offer.Status.INACTIVE,
                removed_by_platform=True,
                removed_at=timezone.now(),
                updated_at=timezone.now(),
            )
        if action in {"publish", "unpublish"}:
            from catalog.search_services import refresh_spu_search_documents

            removed_docs = refresh_spu_search_documents(spu)
        else:
            removed_docs = 0
        if action in {"mark_activity", "unmark_activity"}:
            # 活动商品用活动折扣，标记变化后已上架商品的成本价要按新折扣重算。
            from merchant_ops.services import reprice_listed_offers

            reprice_listed_offers(spu=spu)
        record_audit(
            request=request,
            actor=request.staff_account,
            action="PRODUCT_STATUS_CHANGED"
            if action in {"publish", "unpublish"}
            else "PRODUCT_ACTIVITY_MARKED",
            target_type="spu",
            target_id=str(spu.public_id),
            reason="",
            before_state=before,
            after_state={
                "status": spu.status,
                "activity": spu.is_activity,
                "activated_offers": activated_offers,
                "cascade_removed_offers": cascade_offers,
                "removed_search_documents": removed_docs,
            },
        )
        payload = _spu_payload(spu, images=list(spu.image_urls or []))
        if action == "publish":
            payload["activated_offers"] = activated_offers
        if action == "unpublish":
            payload["cascade_removed_offers"] = cascade_offers
        return Response({"product": payload})


# --------------------------------------------------------------------------
# A04 商家商品管理
# --------------------------------------------------------------------------


class AdminMerchantListingsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["catalog.listings.manage"]
    view_permissions = ["catalog.listings.view"]

    def _queryset(self, request):
        queryset = Offer.objects.select_related(
            "merchant", "sku__spu__local_category", "currency"
        ).prefetch_related("sku__spu__translations")
        merchant_query = (request.query_params.get("merchant") or "").strip()
        if merchant_query:
            # 商家 ID 已改为 MER+6 位数字，不再是 UUID：ID 精确匹配或店名模糊匹配。
            queryset = queryset.filter(
                Q(merchant__public_id__iexact=merchant_query)
                | Q(merchant__display_name__icontains=merchant_query)
            )
        product_query = (request.query_params.get("product") or "").strip()
        if product_query:
            try:
                queryset = queryset.filter(sku__spu__public_id=uuid.UUID(product_query))
            except ValueError:
                raise StaffApiError(
                    business_code="PRODUCT_ID_INVALID",
                    message="商品 ID 格式不正确。",
                    status_code=400,
                ) from None
        status = (request.query_params.get("status") or "").strip().upper()
        if status == "LISTED":
            queryset = queryset.filter(status=Offer.Status.ACTIVE)
        elif status == "REMOVED":
            queryset = queryset.filter(status=Offer.Status.INACTIVE)
        return queryset.order_by("-updated_at", "-pk")

    def get(self, request):
        rows, meta = paginate(self._queryset(request), request, default_size=12)
        return Response(
            {
                "items": [
                    {
                        "id": str(offer.public_id),
                        "merchant": {
                            "id": str(offer.merchant.public_id),
                            "name": offer.merchant.display_name,
                        },
                        "product": {
                            "id": str(offer.sku.spu.public_id),
                            "name": _title_for(offer.sku.spu),
                            "category": _category_payload(offer.sku.spu.local_category),
                            "images": list(offer.sku.spu.image_urls or []),
                            "description": offer.sku.spu.description,
                            "specs": list(offer.sku.spu.specs or []),
                        },
                        "status": "LISTED" if offer.status == Offer.Status.ACTIVE else "REMOVED",
                        "cost": money_str(offer.cost_price)
                        if offer.cost_price is not None
                        else None,
                        "price": money_str(offer.current_price),
                        "currency": offer.currency.code,
                        "listed_at": iso(offer.listed_at),
                        "removed_at": iso(offer.removed_at),
                        "removed_by_platform": offer.removed_by_platform,
                    }
                    for offer in rows
                ],
                **meta,
            }
        )


class AdminMerchantListingActionsView(OpsAPIView):
    permission_classes = [StaffRbacPermission]
    required_permissions = ["catalog.listings.manage"]
    view_permissions = ["catalog.listings.view"]

    def post(self, request, public_id):
        from django.utils import timezone

        offer = (
            Offer.objects.select_related("merchant", "sku__spu").filter(public_id=public_id).first()
        )
        if offer is None:
            raise StaffApiError(
                business_code="LISTING_NOT_FOUND", message="店铺商品关系不存在。", status_code=404
            )
        action = ((request.data or {}).get("action") or "").strip().lower()
        if action != "remove":
            raise StaffApiError(
                business_code="ACTION_UNSUPPORTED", message="不支持的操作。", status_code=400
            )
        if offer.status != Offer.Status.ACTIVE:
            # 幂等：重复下架不重复写时间与日志。
            return Response({"listing": {"id": str(offer.public_id), "status": "REMOVED"}})

        before = {"status": "LISTED"}
        offer.status = Offer.Status.INACTIVE
        offer.removed_at = timezone.now()
        offer.removed_by_platform = True
        offer.save(update_fields=["status", "removed_at", "removed_by_platform", "updated_at"])
        # 迭代02：单商家下架后购物端该商家此商品不再展示——即时刷新搜索文档。
        from catalog.search_services import refresh_spu_search_documents

        removed_docs = refresh_spu_search_documents(offer.sku.spu)
        record_audit(
            request=request,
            actor=request.staff_account,
            action="LISTING_REMOVED",
            target_type="offer",
            target_id=str(offer.public_id),
            reason=(request.data or {}).get("reason") or "",
            before_state=before,
            after_state={"status": "REMOVED", "removed_search_documents": removed_docs},
            tenant_type="merchant",
            tenant_id=str(offer.merchant.public_id),
        )
        return Response({"listing": {"id": str(offer.public_id), "status": "REMOVED"}})


# --------------------------------------------------------------------------
# 共用校验
# --------------------------------------------------------------------------


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def _resolve_category(value) -> LocalCategory | None:
    if not value:
        return None
    queryset = LocalCategory.objects.all()
    if _is_uuid(str(value)):
        return queryset.filter(public_id=value).first()
    return queryset.filter(slug=str(value)).first()


def _validated_merchant_category(value) -> str:
    raw = (value or "").strip().upper()
    if raw and raw not in Spu.MerchantCategory.values:
        raise StaffApiError(
            business_code="MERCHANT_CATEGORY_INVALID",
            message="无效的商家端品类。",
            status_code=400,
        )
    return raw


def _refresh_search_documents(spu) -> None:
    """商品池改动后同步购物端搜索/类目文档（失败不影响商品本身保存）。"""

    from catalog.search_services import refresh_spu_search_documents

    try:
        refresh_spu_search_documents(spu)
    except ValueError:
        # 市场默认语言缺失等历史数据问题不应阻断后台保存。
        return


# --- 图文详情（content_sections）人工编辑的校验上限（2026-11-10）---
# 2026-11-27 上限放宽：子标题 200→1000，段落 5000→50000（管理端编辑商品实测反馈原上限太紧）。
MAX_CONTENT_SECTIONS = 50
MAX_CONTENT_BLOCKS = 100
MAX_SECTION_IMAGES = 20
MAX_SECTION_TITLE_LEN = 120
MAX_HEADING_LEN = 1000
MAX_PARAGRAPH_LEN = 50000
CONTENT_BLOCK_TYPES = ("heading", "paragraph")


def _validated_content_sections(value) -> list:
    """校验管理端提交的图文详情，结构与爬虫 payload 一致（docs/14 §7.7）。

    ``[{title, blocks: [{type: "heading"|"paragraph", text}], images: [...]}]``；
    图片必须是本地上传返回的 ``/media/...`` URL（不允许第三方 CDN），
    空文本块被静默丢弃，其余不合结构/超长/非法 URL 一律 400。
    """

    if not isinstance(value, list):
        raise StaffApiError(
            business_code="CONTENT_SECTIONS_INVALID",
            message="图文详情必须是数组。",
            status_code=400,
        )
    if len(value) > MAX_CONTENT_SECTIONS:
        raise StaffApiError(
            business_code="CONTENT_SECTIONS_TOO_MANY",
            message=f"图文详情最多 {MAX_CONTENT_SECTIONS} 个区块。",
            status_code=400,
        )
    media_prefix = settings.MEDIA_URL
    sections = []
    for raw_section in value:
        if not isinstance(raw_section, dict):
            raise StaffApiError(
                business_code="CONTENT_SECTIONS_INVALID",
                message="图文详情区块格式不正确。",
                status_code=400,
            )
        title = str(raw_section.get("title") or "").strip()
        if len(title) > MAX_SECTION_TITLE_LEN:
            raise StaffApiError(
                business_code="CONTENT_TEXT_TOO_LONG",
                message=f"区块标题最多 {MAX_SECTION_TITLE_LEN} 字。",
                status_code=400,
            )
        raw_blocks = raw_section.get("blocks")
        if not isinstance(raw_blocks, list):
            raise StaffApiError(
                business_code="CONTENT_SECTIONS_INVALID",
                message="图文详情缺少内容块列表。",
                status_code=400,
            )
        if len(raw_blocks) > MAX_CONTENT_BLOCKS:
            raise StaffApiError(
                business_code="CONTENT_SECTIONS_TOO_MANY",
                message=f"单个区块最多 {MAX_CONTENT_BLOCKS} 个内容块。",
                status_code=400,
            )
        blocks = []
        for raw_block in raw_blocks:
            if not isinstance(raw_block, dict):
                raise StaffApiError(
                    business_code="CONTENT_SECTIONS_INVALID",
                    message="内容块格式不正确。",
                    status_code=400,
                )
            block_type = str(raw_block.get("type") or "").strip()
            if block_type not in CONTENT_BLOCK_TYPES:
                raise StaffApiError(
                    business_code="CONTENT_BLOCK_TYPE_INVALID",
                    message="内容块类型只支持子标题（heading）与段落（paragraph）。",
                    status_code=400,
                )
            text = str(raw_block.get("text") or "").strip()
            cap = MAX_HEADING_LEN if block_type == "heading" else MAX_PARAGRAPH_LEN
            if len(text) > cap:
                raise StaffApiError(
                    business_code="CONTENT_TEXT_TOO_LONG",
                    message=f"子标题最多 {MAX_HEADING_LEN} 字，段落最多 {MAX_PARAGRAPH_LEN} 字。",
                    status_code=400,
                )
            if text:
                blocks.append({"type": block_type, "text": text})
        raw_images = raw_section.get("images")
        if raw_images is None:
            raw_images = []
        if not isinstance(raw_images, list):
            raise StaffApiError(
                business_code="CONTENT_SECTIONS_INVALID",
                message="区块图片必须是数组。",
                status_code=400,
            )
        if len(raw_images) > MAX_SECTION_IMAGES:
            raise StaffApiError(
                business_code="CONTENT_SECTIONS_TOO_MANY",
                message=f"单个区块最多 {MAX_SECTION_IMAGES} 张图片。",
                status_code=400,
            )
        images = []
        for image in raw_images:
            url = str(image or "").strip()
            if not url:
                continue
            # 只接受本地上传接口返回的 /media/ URL，运行时不允许请求第三方 CDN。
            if not url.startswith(media_prefix) or ".." in url:
                raise StaffApiError(
                    business_code="CONTENT_IMAGE_INVALID",
                    message="区块图片必须是本地上传的图片（/media/…），不接受外部链接。",
                    status_code=400,
                )
            images.append(url)
        sections.append({"title": title, "blocks": blocks, "images": images})
    return sections


def _validated_media_payload(payload) -> tuple[list, list]:
    images = payload.get("images")
    if images is not None:
        if not isinstance(images, list):
            raise StaffApiError(
                business_code="IMAGES_INVALID", message="商品图片必须是数组。", status_code=400
            )
        if len(images) > MAX_IMAGES:
            raise StaffApiError(
                business_code="TOO_MANY_IMAGES",
                message=f"商品图片最多 {MAX_IMAGES} 张。",
                status_code=400,
            )
        images = [str(url).strip() for url in images if str(url).strip()]
    else:
        images = []

    specs = payload.get("specs")
    if specs is not None:
        if not isinstance(specs, list):
            raise StaffApiError(
                business_code="SPECS_INVALID", message="规格必须是数组。", status_code=400
            )
        seen = set()
        cleaned = []
        for entry in specs:
            if not isinstance(entry, dict):
                raise StaffApiError(
                    business_code="SPECS_INVALID", message="规格格式不正确。", status_code=400
                )
            name = str(entry.get("name") or "").strip()
            value = str(entry.get("value") or "").strip()
            if not name or not value:
                raise StaffApiError(
                    business_code="SPECS_INCOMPLETE",
                    message="规格名称和规格值都不能为空。",
                    status_code=400,
                )
            if len(name) > 30 or len(value) > 200:
                raise StaffApiError(
                    business_code="SPECS_TOO_LONG",
                    message="规格名称最多 30 字，规格值最多 200 字。",
                    status_code=400,
                )
            if name in seen:
                raise StaffApiError(
                    business_code="SPECS_DUPLICATED",
                    message="同一商品的规格名称不能重复。",
                    status_code=400,
                )
            seen.add(name)
            cleaned.append({"name": name, "value": value})
        specs = cleaned
    else:
        specs = []
    return images, specs


class AdminCategoriesView(OpsAPIView):
    """商品池表单与筛选用的本地类目选项（扁平列表，带中英名）。

    编辑表单先选「商家端品类（父品类）」，再选它下面的二级类目（子品类），
    所以这里额外返回 ``parent_id`` 与一级类目的 ``merchant_category`` 映射，
    前端据此做联动；筛选下拉只用 ``depth=0`` 的父类目。
    """

    permission_classes = [StaffRbacPermission]
    required_permissions = ["catalog.pool.manage"]
    view_permissions = ["catalog.pool.view"]

    def get(self, request):
        rows = (
            LocalCategory.objects.filter(status=LocalCategory.Status.ACTIVE)
            .select_related("parent")
            .order_by("path", "sort_order")[:500]
        )
        return Response(
            {
                "items": [
                    {
                        "id": str(category.public_id),
                        "name": category.name,
                        "name_zh": category.name_zh,
                        "name_en": category.name_en,
                        "path": category.path,
                        "depth": category.depth,
                        "sort_order": category.sort_order,
                        "parent_id": str(category.parent.public_id) if category.parent_id else None,
                        "merchant_category": (
                            LOCAL_PARENT_MERCHANT_CATEGORY.get(category.slug, "")
                            if category.depth == 0
                            else ""
                        ),
                    }
                    for category in rows
                ]
            }
        )


class AdminMerchantOptionsView(OpsAPIView):
    """商家商品模块的商家搜索框数据源（不依赖商家管理权限）。"""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["catalog.listings.manage"]
    view_permissions = ["catalog.listings.view"]

    def get(self, request):
        from merchants.models import Merchant

        query = (request.query_params.get("q") or "").strip()
        queryset = Merchant.objects.exclude(onboarding_status=Merchant.OnboardingStatus.DRAFT)
        if query:
            # 2026-11-28 可搜索下拉框：店铺编号 JYM 整号/部分号都能搜。
            queryset = queryset.filter(
                Q(display_name__icontains=query)
                | Q(slug__icontains=query)
                | Q(public_id__icontains=query)
            )
        return Response(
            {
                "items": [
                    {
                        "id": str(merchant.public_id),
                        "name": merchant.display_name,
                        "status": merchant.onboarding_status,
                    }
                    for merchant in queryset.order_by("-created_at")[:20]
                ]
            }
        )
