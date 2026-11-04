import hashlib
import json
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.utils import timezone

from catalog.domain import ProductSourceIdentityInvalid, SkuSpecificationInvalid
from catalog.models import (
    AttributeDefinition,
    Brand,
    LocalCategory,
    Sku,
    SkuSourceIdentity,
    SourceCategory,
    Spu,
    SpuSourceIdentity,
    SpuTranslation,
)


def _normalize_source_identity(source_system: str, source_id: str) -> tuple[str, str]:
    normalized_system = source_system.strip().casefold()
    normalized_id = source_id.strip()
    if not normalized_system or not normalized_id:
        raise ProductSourceIdentityInvalid("source_system and source_id are required.")
    return normalized_system, normalized_id


def get_or_create_spu_from_source(
    *,
    source_system: str,
    source_id: str,
    source_url: str = "",
    source_category: SourceCategory | None = None,
    brand: Brand | None = None,
    local_category: LocalCategory | None = None,
    title: str,
    locale: str = "en-GB",
) -> tuple[Spu, bool]:
    normalized_system, normalized_id = _normalize_source_identity(source_system, source_id)
    now = timezone.now()
    existing = (
        SpuSourceIdentity.objects.select_related("spu")
        .filter(source_system=normalized_system, source_id=normalized_id)
        .first()
    )
    if existing:
        existing.source_url = source_url.strip()
        existing.source_category = source_category
        existing.last_seen_at = now
        existing.save(update_fields=["source_url", "source_category", "last_seen_at", "updated_at"])
        return existing.spu, False

    try:
        with transaction.atomic():
            spu = Spu.objects.create(
                brand=brand,
                local_category=local_category,
                status=Spu.Status.DRAFT,
            )
            SpuTranslation.objects.create(
                spu=spu,
                locale=locale,
                title=title.strip(),
            )
            SpuSourceIdentity.objects.create(
                spu=spu,
                source_system=normalized_system,
                source_id=normalized_id,
                source_url=source_url.strip(),
                source_category=source_category,
                first_seen_at=now,
                last_seen_at=now,
            )
            return spu, True
    except IntegrityError:
        identity = SpuSourceIdentity.objects.select_related("spu").get(
            source_system=normalized_system,
            source_id=normalized_id,
        )
        return identity.spu, False


def normalize_sku_specification(specification: dict) -> tuple[dict, str]:
    if not isinstance(specification, dict):
        raise SkuSpecificationInvalid("SKU specification must be an object.")
    definitions = {
        item.code: item
        for item in AttributeDefinition.objects.prefetch_related("options").filter(
            code__in=specification
        )
    }
    if set(definitions) != set(specification):
        unknown = sorted(set(specification) - set(definitions))
        raise SkuSpecificationInvalid(f"Unknown SKU attributes: {', '.join(unknown)}.")

    normalized = {}
    for code in sorted(specification):
        definition = definitions[code]
        if not definition.is_active or definition.scope not in {
            AttributeDefinition.Scope.SKU,
            AttributeDefinition.Scope.BOTH,
        }:
            raise SkuSpecificationInvalid(f"Attribute {code} cannot be used by a SKU.")
        raw_value = specification[code]
        if definition.data_type == AttributeDefinition.DataType.BOOLEAN:
            if not isinstance(raw_value, bool):
                raise SkuSpecificationInvalid(f"Attribute {code} requires a boolean.")
            normalized[code] = raw_value
        elif definition.data_type == AttributeDefinition.DataType.INTEGER:
            if isinstance(raw_value, (bool, float)):
                raise SkuSpecificationInvalid(f"Attribute {code} requires an integer.")
            try:
                integer_value = Decimal(str(raw_value))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise SkuSpecificationInvalid(f"Attribute {code} requires an integer.") from exc
            if not integer_value.is_finite() or integer_value != integer_value.to_integral_value():
                raise SkuSpecificationInvalid(f"Attribute {code} requires an integer.")
            normalized[code] = int(integer_value)
        elif definition.data_type == AttributeDefinition.DataType.DECIMAL:
            if isinstance(raw_value, float):
                raise SkuSpecificationInvalid(f"Attribute {code} cannot use a float.")
            try:
                value = Decimal(str(raw_value))
            except (InvalidOperation, ValueError) as exc:
                raise SkuSpecificationInvalid(f"Attribute {code} requires a decimal.") from exc
            if not value.is_finite():
                raise SkuSpecificationInvalid(f"Attribute {code} requires a finite decimal.")
            normalized[code] = format(value.normalize(), "f")
        elif definition.data_type == AttributeDefinition.DataType.CHOICE:
            value = str(raw_value).strip()
            if not definition.options.filter(value=value, is_active=True).exists():
                raise SkuSpecificationInvalid(f"Invalid option for attribute {code}.")
            normalized[code] = value
        elif definition.data_type == AttributeDefinition.DataType.MULTI_CHOICE:
            if not isinstance(raw_value, (list, tuple)):
                raise SkuSpecificationInvalid(f"Attribute {code} requires a list of options.")
            values = sorted({str(item).strip() for item in raw_value})
            valid_count = definition.options.filter(value__in=values, is_active=True).count()
            if not values or valid_count != len(values):
                raise SkuSpecificationInvalid(f"Invalid options for attribute {code}.")
            normalized[code] = values
        else:
            value = str(raw_value).strip()
            if not value:
                raise SkuSpecificationInvalid(f"Attribute {code} cannot be empty.")
            normalized[code] = value

    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return normalized, hashlib.sha256(canonical.encode()).hexdigest()


def canonicalize_source_specification(specification) -> tuple[dict, str]:
    """Signature normalization for source-provided specs, without the local
    attribute registry. Crawler imports use this until an admin formalises
    the specs into ``AttributeDefinition`` entries (WP-31)."""

    if not isinstance(specification, dict):
        raise SkuSpecificationInvalid("SKU specification must be an object.")
    normalized = {}
    for raw_key, raw_value in specification.items():
        key = str(raw_key).strip()
        if not key:
            raise SkuSpecificationInvalid("Specification keys cannot be empty.")
        if isinstance(raw_value, bool) or raw_value is None:
            normalized[key] = raw_value
        elif isinstance(raw_value, (int, str)):
            normalized[key] = raw_value if not isinstance(raw_value, str) else raw_value.strip()
        elif isinstance(raw_value, float):
            # Source specs may contain measurements; keep them exact via str.
            normalized[key] = str(raw_value)
        elif isinstance(raw_value, (list, tuple)):
            normalized[key] = sorted({str(item).strip() for item in raw_value})
        else:
            raise SkuSpecificationInvalid(f"Unsupported specification value for {key}.")
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return normalized, hashlib.sha256(canonical.encode()).hexdigest()


def get_or_create_sku_from_source(
    *,
    spu: Spu,
    source_system: str,
    source_id: str,
    specification: dict,
    source_url: str = "",
    gtin: str = "",
    skip_attribute_validation: bool = False,
) -> tuple[Sku, bool]:
    normalized_system, normalized_id = _normalize_source_identity(source_system, source_id)
    if skip_attribute_validation:
        normalized_specification, signature = canonicalize_source_specification(specification)
    else:
        normalized_specification, signature = normalize_sku_specification(specification)
    now = timezone.now()
    existing = (
        SkuSourceIdentity.objects.select_related("sku")
        .filter(source_system=normalized_system, source_id=normalized_id)
        .first()
    )
    if existing:
        if existing.sku.spu_id != spu.pk or existing.sku.specification_signature != signature:
            raise ProductSourceIdentityInvalid(
                "The source SKU identity is already assigned to a different product or specification."
            )
        existing.source_url = source_url.strip()
        existing.last_seen_at = now
        existing.save(update_fields=["source_url", "last_seen_at", "updated_at"])
        return existing.sku, False

    try:
        with transaction.atomic():
            sku, sku_created = Sku.objects.get_or_create(
                spu=spu,
                specification_signature=signature,
                defaults={
                    "specification": normalized_specification,
                    "gtin": gtin.strip(),
                },
            )
            SkuSourceIdentity.objects.create(
                sku=sku,
                source_system=normalized_system,
                source_id=normalized_id,
                source_url=source_url.strip(),
                first_seen_at=now,
                last_seen_at=now,
            )
            return sku, sku_created
    except IntegrityError:
        identity = SkuSourceIdentity.objects.select_related("sku").get(
            source_system=normalized_system,
            source_id=normalized_id,
        )
        if identity.sku.spu_id != spu.pk or identity.sku.specification_signature != signature:
            raise ProductSourceIdentityInvalid(
                "The source SKU identity is already assigned to a different product or specification."
            )
        return identity.sku, False
