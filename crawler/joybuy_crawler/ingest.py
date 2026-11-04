"""Staging ingestion: parsed product payloads land in crawler_control.

Crawlers stop here; the import into business tables only happens through
``crawler_control.import_services`` with the domain services.
"""

from datetime import timedelta

from crawler_control.models import StagingProduct
from django.utils import timezone


def ingest_product_payload(
    run,
    payload: dict,
    *,
    source_system: str,
    source_url: str = "",
    parser_version: str,
    structure_version: int,
    observed_at=None,
) -> StagingProduct:
    """Create or refresh the staging row for one product (idempotent)."""

    source_id = str((payload or {}).get("source_id") or "").strip()
    if not source_id:
        raise ValueError("Parsed payload is missing source_id; nothing to stage.")
    observed_at = observed_at or timezone.now()
    missing_fields = sorted(set((payload or {}).get("missing_fields") or []))

    staging, created = StagingProduct.objects.update_or_create(
        source_system=source_system.strip().casefold(),
        source_id=source_id,
        defaults={
            "run": run,
            "source_url": source_url.strip(),
            "payload": payload or {},
            "parser_version": parser_version,
            "structure_version": structure_version,
            "missing_fields": missing_fields,
            # Fresh observations reset the row for re-import review.
            "status": StagingProduct.Status.PENDING,
            "error_message": "",
            "last_seen_at": observed_at,
        },
        create_defaults={
            "run": run,
            "source_url": source_url.strip(),
            "payload": payload or {},
            "parser_version": parser_version,
            "structure_version": structure_version,
            "missing_fields": missing_fields,
            "status": StagingProduct.Status.PENDING,
            "first_seen_at": observed_at,
            "last_seen_at": observed_at,
        },
    )
    return staging


def pending_staging_products(*, older_than_minutes: int = 0):
    """Staging rows awaiting import, oldest first (used by the importer)."""

    cutoff = timezone.now() - timedelta(minutes=older_than_minutes)
    return StagingProduct.objects.filter(
        status=StagingProduct.Status.PENDING, last_seen_at__lte=cutoff
    ).order_by("last_seen_at", "pk")
