from audit.services import record_audit_entry
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone
from offers.services import parse_money

from catalog.domain import FieldValueInvalid, OverrideStateInvalid
from catalog.models import LocalFieldOverride, LocalFieldOverrideVersion, SourceFieldValue


def _validate_text(target, value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise FieldValueInvalid("Text field values must be strings.")
    text = str(value).strip()
    if not text:
        raise FieldValueInvalid("Text field values cannot be empty.")
    return text


def _validate_optional_text(target, value):
    if value is None:
        return ""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise FieldValueInvalid("Text field values must be strings.")
    return str(value).strip()


def _validate_offer_money(field_code):
    def validator(target, value):
        if value is None:
            raise FieldValueInvalid(f"{field_code} cannot be cleared to null.")
        return str(parse_money(value, target.currency))

    return validator


def _spu_translation_fields():
    from catalog.models import SpuTranslation

    return {
        SpuTranslation: {
            "title": _validate_text,
            "subtitle": _validate_optional_text,
            "description": _validate_optional_text,
        }
    }


def _offer_fields():
    from offers.models import Offer

    return {
        Offer: {
            "promotion_label": _validate_optional_text,
            "current_price": _validate_offer_money("current_price"),
            "list_price": _validate_offer_money("list_price"),
        }
    }


def _field_registry() -> dict:
    registry: dict = {}
    registry.update(_spu_translation_fields())
    registry.update(_offer_fields())
    return registry


def _target_key(target) -> tuple[ContentType, int]:
    if target is None or getattr(target, "pk", None) is None:
        raise FieldValueInvalid("The field target must be a saved model instance.")
    return ContentType.objects.get_for_model(type(target)), target.pk


def _resolve_validator(registry, target, field_code):
    model_registry = registry.get(type(target))
    if model_registry is None:
        raise FieldValueInvalid(f"Model {type(target).__name__} has no overridable fields.")
    validator = model_registry.get(field_code)
    if validator is None:
        raise FieldValueInvalid(f"Unknown overridable field: {field_code}.")
    return validator


def _normalize_values(registry, target, values: dict) -> dict:
    if not isinstance(values, dict) or not values:
        raise FieldValueInvalid("Field values must be a non-empty object.")
    normalized = {}
    for field_code, value in values.items():
        validator = _resolve_validator(registry, target, field_code)
        try:
            normalized[field_code] = validator(target, value)
        except FieldValueInvalid:
            raise
        except Exception as exc:
            raise FieldValueInvalid(f"Value for {field_code} is invalid.") from exc
    return normalized


def apply_source_field_values(
    target,
    values: dict,
    *,
    source_system: str,
    observed_at=None,
) -> dict:
    """Write crawler observations into the source layer only.

    Local overrides are separate rows, so this can never overwrite an
    approved local value. Returns the stored source values keyed by field.
    """

    normalized_system = source_system.strip().casefold()
    if not normalized_system:
        raise FieldValueInvalid("source_system is required.")
    observed_at = observed_at or timezone.now()
    normalized = _normalize_values(_field_registry(), target, values)
    content_type, object_id = _target_key(target)

    stored = {}
    with transaction.atomic():
        for field_code, value in normalized.items():
            row, _ = SourceFieldValue.objects.update_or_create(
                content_type=content_type,
                object_id=object_id,
                field_code=field_code,
                defaults={
                    "value": value,
                    "source_system": normalized_system,
                    "observed_at": observed_at,
                    "last_seen_at": observed_at,
                    "is_missing": False,
                },
                create_defaults={
                    "value": value,
                    "source_system": normalized_system,
                    "observed_at": observed_at,
                    "first_seen_at": observed_at,
                    "last_seen_at": observed_at,
                    "is_missing": False,
                },
            )
            stored[field_code] = row.value
    return stored


def mark_source_fields_missing(target, field_codes, *, observed_at=None) -> int:
    """Flag source fields that no longer appear at the source.

    Rows are kept so history and diffs remain traceable; effective values
    stop following a field once it is marked missing.
    """

    if not field_codes:
        raise FieldValueInvalid("At least one field code is required.")
    observed_at = observed_at or timezone.now()
    registry = _field_registry()
    content_type, object_id = _target_key(target)
    for field_code in field_codes:
        _resolve_validator(registry, target, field_code)
    with transaction.atomic():
        return SourceFieldValue.objects.filter(
            content_type=content_type,
            object_id=object_id,
            field_code__in=list(field_codes),
        ).update(is_missing=True, observed_at=observed_at, updated_at=timezone.now())


def resolve_effective_value(target, field_code: str) -> dict:
    """Resolve ``approved_local_override ?? latest_source_value`` for a field."""

    registry = _field_registry()
    _resolve_validator(registry, target, field_code)
    content_type, object_id = _target_key(target)

    source_row = SourceFieldValue.objects.filter(
        content_type=content_type,
        object_id=object_id,
        field_code=field_code,
    ).first()
    override_row = LocalFieldOverride.objects.filter(
        content_type=content_type,
        object_id=object_id,
        field_code=field_code,
    ).first()

    source_value = None if source_row is None or source_row.is_missing else source_row.value
    override_value = None
    if override_row is not None and override_row.status == LocalFieldOverride.Status.APPROVED:
        override_value = override_row.value

    if override_value is not None:
        effective, origin = override_value, "local_override"
    elif source_value is not None:
        effective, origin = source_value, "source"
    else:
        effective, origin = None, "none"

    return {
        "field": field_code,
        "source": source_value,
        "source_is_missing": bool(source_row and source_row.is_missing),
        "source_observed_at": source_row.observed_at if source_row else None,
        "override": None
        if override_row is None
        else {
            "value": override_row.value,
            "status": override_row.status,
            "version": override_row.version,
        },
        "effective": effective,
        "effective_origin": origin,
    }


def resolve_effective_values(target, field_codes=None) -> dict:
    registry = _field_registry()
    model_registry = registry.get(type(target))
    if model_registry is None:
        raise FieldValueInvalid(f"Model {type(target).__name__} has no overridable fields.")
    if field_codes is None:
        field_codes = list(model_registry)
    return {code: resolve_effective_value(target, code) for code in field_codes}


def _write_override_version(
    *,
    override: LocalFieldOverride,
    change_kind: str,
    actor,
    reason: str,
    request_id=None,
) -> None:
    LocalFieldOverrideVersion.objects.create(
        override=override,
        version=override.version,
        value=override.value,
        status=override.status,
        change_kind=change_kind,
        reason=reason,
        actor=actor,
        request_id=request_id,
    )


def _audit_override(
    *,
    action: str,
    override: LocalFieldOverride,
    actor,
    reason: str,
    before_state: dict,
    after_state: dict,
    request_id=None,
    ip_address=None,
) -> None:
    content_type = ContentType.objects.get_for_id(override.content_type_id)
    record_audit_entry(
        actor=actor,
        action=action,
        target_type=f"{content_type.app_label}.{content_type.model}.{override.field_code}",
        target_id=str(override.object_id),
        reason=reason,
        before_state=before_state,
        after_state=after_state,
        request_id=request_id,
        ip_address=ip_address,
        tenant_type="platform",
        tenant_id="catalog",
    )


def _override_before_state(override: LocalFieldOverride | None) -> dict:
    if override is None:
        return {}
    return {
        "value": override.value,
        "status": override.status,
        "version": override.version,
        "reason": override.reason,
    }


def propose_local_override(
    target,
    field_code: str,
    value,
    *,
    reason: str,
    proposed_by=None,
    request_id=None,
    ip_address=None,
) -> LocalFieldOverride:
    """Create or re-open a local override proposal without touching the source."""

    if not reason or not reason.strip():
        raise FieldValueInvalid("A reason is required for every local override.")
    normalized = _normalize_values(_field_registry(), target, {field_code: value})
    content_type, object_id = _target_key(target)
    normalized_value = normalized[field_code]
    resolved_request_id = request_id

    with transaction.atomic():
        override = (
            LocalFieldOverride.objects.select_for_update()
            .filter(content_type=content_type, object_id=object_id, field_code=field_code)
            .first()
        )
        before_state = _override_before_state(override)
        if override is None:
            override = LocalFieldOverride.objects.create(
                content_type=content_type,
                object_id=object_id,
                field_code=field_code,
                value=normalized_value,
                status=LocalFieldOverride.Status.PENDING,
                version=1,
                reason=reason.strip(),
                proposed_by=proposed_by,
            )
            change_kind = LocalFieldOverrideVersion.ChangeKind.CREATE
        else:
            override.value = normalized_value
            override.status = LocalFieldOverride.Status.PENDING
            override.version += 1
            override.reason = reason.strip()
            override.proposed_by = proposed_by
            override.reviewed_by = None
            override.reviewed_at = None
            override.save(
                update_fields=[
                    "value",
                    "status",
                    "version",
                    "reason",
                    "proposed_by",
                    "reviewed_by",
                    "reviewed_at",
                    "updated_at",
                ]
            )
            change_kind = LocalFieldOverrideVersion.ChangeKind.UPDATE
        _write_override_version(
            override=override,
            change_kind=change_kind,
            actor=proposed_by,
            reason=reason.strip(),
            request_id=resolved_request_id,
        )
        _audit_override(
            action="catalog.override.propose",
            override=override,
            actor=proposed_by,
            reason=reason.strip(),
            before_state=before_state,
            after_state=_override_before_state(override),
            request_id=resolved_request_id,
            ip_address=ip_address,
        )
        return override


def review_local_override(
    target,
    field_code: str,
    decision: str,
    *,
    reason: str,
    reviewed_by=None,
    request_id=None,
    ip_address=None,
) -> LocalFieldOverride:
    """Approve or reject a pending override; approval activates shadowing."""

    if decision not in {LocalFieldOverride.Status.APPROVED, LocalFieldOverride.Status.REJECTED}:
        raise OverrideStateInvalid("An override review decision must be APPROVED or REJECTED.")
    if not reason or not reason.strip():
        raise OverrideStateInvalid("A review reason is required.")
    registry = _field_registry()
    _resolve_validator(registry, target, field_code)
    content_type, object_id = _target_key(target)
    now = timezone.now()

    with transaction.atomic():
        override = (
            LocalFieldOverride.objects.select_for_update()
            .filter(content_type=content_type, object_id=object_id, field_code=field_code)
            .first()
        )
        if override is None:
            raise OverrideStateInvalid("No local override exists for this field.")
        if override.status != LocalFieldOverride.Status.PENDING:
            raise OverrideStateInvalid("Only pending overrides can be reviewed.")
        before_state = _override_before_state(override)
        override.status = decision
        override.version += 1
        override.reviewed_by = reviewed_by
        override.reviewed_at = now
        override.save(
            update_fields=["status", "version", "reviewed_by", "reviewed_at", "updated_at"]
        )
        _write_override_version(
            override=override,
            change_kind=LocalFieldOverrideVersion.ChangeKind.REVIEW,
            actor=reviewed_by,
            reason=reason.strip(),
            request_id=request_id,
        )
        _audit_override(
            action="catalog.override.approve"
            if decision == LocalFieldOverride.Status.APPROVED
            else "catalog.override.reject",
            override=override,
            actor=reviewed_by,
            reason=reason.strip(),
            before_state=before_state,
            after_state=_override_before_state(override),
            request_id=request_id,
            ip_address=ip_address,
        )
        return override


def clear_local_override(
    target,
    field_code: str,
    *,
    reason: str,
    cleared_by=None,
    request_id=None,
    ip_address=None,
) -> LocalFieldOverride:
    """Clear an override so the field follows the source value again."""

    if not reason or not reason.strip():
        raise OverrideStateInvalid("A reason is required to clear an override.")
    registry = _field_registry()
    _resolve_validator(registry, target, field_code)
    content_type, object_id = _target_key(target)

    with transaction.atomic():
        override = (
            LocalFieldOverride.objects.select_for_update()
            .filter(content_type=content_type, object_id=object_id, field_code=field_code)
            .first()
        )
        if override is None:
            raise OverrideStateInvalid("No local override exists for this field.")
        if override.status == LocalFieldOverride.Status.CLEARED:
            raise OverrideStateInvalid("The override is already cleared.")
        before_state = _override_before_state(override)
        override.status = LocalFieldOverride.Status.CLEARED
        override.version += 1
        override.reviewed_by = None
        override.reviewed_at = None
        override.save(
            update_fields=["status", "version", "reviewed_by", "reviewed_at", "updated_at"]
        )
        _write_override_version(
            override=override,
            change_kind=LocalFieldOverrideVersion.ChangeKind.CLEAR,
            actor=cleared_by,
            reason=reason.strip(),
            request_id=request_id,
        )
        _audit_override(
            action="catalog.override.clear",
            override=override,
            actor=cleared_by,
            reason=reason.strip(),
            before_state=before_state,
            after_state=_override_before_state(override),
            request_id=request_id,
            ip_address=ip_address,
        )
        return override


def list_override_diffs(target) -> list[dict]:
    """Show source vs override differences for every overridable field."""

    resolved = resolve_effective_values(target)
    return [
        {
            "field": item["field"],
            "source": item["source"],
            "override": item["override"],
            "differs": item["override"] is not None
            and item["override"]["status"] == LocalFieldOverride.Status.APPROVED
            and item["override"]["value"] != item["source"],
            "effective": item["effective"],
            "effective_origin": item["effective_origin"],
        }
        for item in resolved.values()
    ]
