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

import dataclasses
import urllib.request

from django.db import transaction
from django.utils import timezone

from catalog.models import Brand, CategoryMapping, SpuTranslation
from catalog.override_services import apply_source_field_values
from catalog.product_services import (
    get_or_create_sku_from_source,
    get_or_create_spu_from_source,
)
from crawler_control.models import StagingProduct
from merchants.services import resolve_import_merchant
from offers.models import Offer
from offers.services import import_offer_from_source

IMPORT_REQUIRED_FIELDS = ("source_id", "title", "currency", "current_price", "skus")


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


_IMPORT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def _fetch_image_bytes(url: str, *, timeout_seconds: float = 30.0) -> bytes | None:
    if not url or not url.startswith(("http://", "https://")):
        return None
    request = urllib.request.Request(url, headers={"User-Agent": _IMPORT_UA})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            if response.status != 200:
                return None
            return response.read(10 * 1024 * 1024)
    except Exception:  # noqa: BLE001 - gallery download is best-effort
        return None


def _import_gallery_images(spu, payload, *, observed_at) -> dict:
    """Download the payload gallery into the media library (role=gallery).

    Best-effort: a failed CDN object is reported per-URL and never blocks
    the product import. Highest-resolution variants are expected to have
    been resolved by the crawler already.
    """

    from media.pipeline import process_media_bytes
    from media.variants import link_asset_to_object

    summary = {"downloaded": 0, "failed": 0}
    urls = [url for url in (payload.get("image_urls") or []) if url]
    for sort_order, url in enumerate(urls):
        data = _fetch_image_bytes(url)
        if not data:
            summary["failed"] += 1
            continue
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


def import_staging_product(
    staging: StagingProduct,
    *,
    market,
    currency,
    locale: str = "en-GB",
    observed_at=None,
) -> ImportOutcome:
    """Import one staged payload; rejects rows missing required fields."""

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
    category_source_id = (payload.get("source_category_id") or "").strip()
    if category_source_id:
        from catalog.models import SourceCategory

        source_category = SourceCategory.objects.filter(
            catalog__source_system=staging.source_system, source_id=category_source_id
        ).first()

    with transaction.atomic():
        brand = _resolve_brand(payload)
        spu, created_spu = get_or_create_spu_from_source(
            source_system=staging.source_system,
            source_id=staging.source_id,
            source_url=staging.source_url,
            source_category=source_category,
            brand=brand,
            local_category=_resolve_local_category(source_category),
            title=payload["title"],
            locale=locale,
        )
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

        skus = []
        offers = []
        for index, sku_payload in enumerate(payload.get("skus") or []):
            specification = {
                spec["name"]: spec["value"]
                for spec in sku_payload.get("specs") or []
                if spec.get("name")
            }
            sku, _created_sku = get_or_create_sku_from_source(
                spu=spu,
                source_system=staging.source_system,
                source_id=sku_payload["source_id"],
                specification=specification,
                skip_attribute_validation=True,
            )
            skus.append(sku)
            offer, _created_offer = import_offer_from_source(
                sku=sku,
                merchant=merchant,
                market=market,
                currency=currency,
                source_system=staging.source_system,
                source_id=f"{staging.source_id}#{sku_payload['source_id']}",
                current_price=sku_payload.get("price") or payload["current_price"],
                list_price=payload.get("list_price"),
                source_availability=sku_payload.get("availability")
                or Offer.SourceAvailability.UNKNOWN,
                source_url=staging.source_url,
                promotion_label=payload.get("promotion_label") or "",
                observed_at=observed_at,
            )
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

        gallery_summary = _import_gallery_images(spu, payload, observed_at=observed_at)

        staging.missing_fields = sorted(set(payload.get("missing_fields") or []))
        staging.status = StagingProduct.Status.IMPORTED
        staging.imported_at = observed_at
        staging.error_message = ""
        staging.imported_refs = {
            "spu_public_id": str(spu.public_id),
            "sku_count": len(skus),
            "offer_count": len(offers),
            "gallery_images": gallery_summary,
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
