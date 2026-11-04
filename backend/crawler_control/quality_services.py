"""Quality gates, staleness tracking and the global circuit breaker (WP-19).

Guarantees (docs/05 §11 and §7.2):
- an anomalous batch can never overwrite good data — FAILED reports freeze
  the batch and pause the job per its failure policy;
- risk-control-flagged accounts leave the queue immediately (WP-13) and are
  counted here;
- when several distinct accounts hit risk control inside one window, the
  global circuit breaker trips and no new run can start until a human
  resets it;
- full refresh marks unseen offers as suspected-stale; only consecutive
  confirmations turn them UNAVAILABLE, and nothing is ever deleted.
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from crawler_control.domain import CrawlerControlError, CrawlJobStateInvalid
from crawler_control.models import (
    CrawlerAccount,
    CrawlerCircuitBreaker,
    CrawlJob,
    CrawlRun,
    QualityGateReport,
    StagingProduct,
)

DEFAULT_MISSING_RATE_THRESHOLD = 0.20

PAGE_TYPES = ("listing", "product_detail", "review")


def _breakers() -> CrawlerCircuitBreaker:
    obj = CrawlerCircuitBreaker.objects.first()
    if obj is None:
        obj = CrawlerCircuitBreaker.objects.create()
    return obj


def evaluate_batch_quality(
    run: CrawlRun,
    *,
    page_type: str,
    structure_version: int,
    payloads: list[dict],
    required_fields: dict[str, list[str]] | None = None,
    thresholds: dict[str, float] | None = None,
) -> QualityGateReport:
    """Compute missing rates per required field for one batch.

    ``required_fields`` defaults to the WP-16 contract; callers can extend
    it per page type. A FAILED report pauses the job per its failure policy
    and leaves staging untouched — existing data is never overwritten.
    """

    if page_type not in PAGE_TYPES:
        raise CrawlerControlError(f"Unknown page type: {page_type}.")
    for rate in (thresholds or {}).values():
        if not 0 < rate <= 1:
            raise CrawlerControlError("Missing-rate thresholds must be within (0, 1].")
    required = (
        required_fields
        if required_fields is not None
        else {
            "product_detail": ["source_id", "title", "currency", "current_price", "skus"],
            "listing": ["source_url", "rank", "title"],
            "review": ["source_id", "rating"],
        }.get(page_type, [])
    )
    limits = {field: threshold for field, threshold in (thresholds or {}).items()}
    if not limits:
        limits = {field: DEFAULT_MISSING_RATE_THRESHOLD for field in required}

    checked = len(payloads)
    missing_counts = {field: 0 for field in required}
    for payload in payloads or []:
        for field in required:
            value = (payload or {}).get(field)
            if value is None or value == "" or value == []:
                missing_counts[field] += 1

    rates = {field: (missing_counts[field] / checked if checked else 0.0) for field in required}
    breached = {field: rate for field, rate in rates.items() if rate > limits.get(field, 1.0)}
    failed = bool(breached) or checked == 0

    with transaction.atomic():
        report = QualityGateReport.objects.create(
            run=run,
            page_type=page_type,
            structure_version=structure_version,
            checked_count=checked,
            field_missing_rates=rates,
            thresholds=limits,
            status=QualityGateReport.Status.FAILED if failed else QualityGateReport.Status.PASSED,
            failure_detail=(
                f"Missing-rate threshold breached: "
                f"{ {field: round(rate, 4) for field, rate in breached.items()} }"
                if breached
                else ("No payloads to evaluate." if checked == 0 else "")
            ),
        )
        if failed:
            paused_job = apply_quality_failure_policy(run, report)
            report.paused_job = paused_job
            report.save(update_fields=["paused_job"])
        return report


def apply_quality_failure_policy(run: CrawlRun, report: QualityGateReport) -> bool:
    """Pause the run/job after a failed gate, honouring the failure strategy.

    The job is re-read from the database: admins may change the strategy
    while a run is in flight.
    """

    from crawler_control.services import pause_run

    job = CrawlJob.objects.get(pk=run.job_id)
    if job.failure_strategy == CrawlJob.FailureStrategy.CONTINUE:
        return False
    if run.status == CrawlRun.Status.RUNNING:
        pause_run(run, reason=CrawlRun.PauseReason.FAILURE_POLICY)
        return True
    return False


# ---------------------------------------------------------------------------
# Incremental sync vs full refresh staleness
# ---------------------------------------------------------------------------

STALE_UNAVAILABLE_CONFIRMATIONS = 2


def mark_missing_offers_suspect(run: CrawlRun, *, seen_source_ids: set[str]) -> dict:
    """Full-refresh staleness pass for the offers of one run's source system.

    Offers not in ``seen_source_ids`` are marked suspected-stale on the
    first miss and become ``UNAVAILABLE`` after the configured number of
    consecutive confirmations. Incremental sync never calls this.
    """

    if run.job.sync_mode != CrawlJob.SyncMode.FULL_REFRESH:
        raise CrawlJobStateInvalid("Only full-refresh runs may mark offers suspected-stale.")
    now = timezone.now()
    from offers.models import Offer

    suspects = Offer.objects.filter(
        sku__spu__source_identities__source_system=run.job.source_catalog.source_system
    ).exclude(source_identities__source_id__in=seen_source_ids)

    marked = 0
    confirmed = 0
    for offer in suspects.select_for_update():
        if offer.suspected_stale_since is None:
            offer.suspected_stale_since = now
            offer.stale_confirmations = 1
            marked += 1
        else:
            offer.stale_confirmations += 1
            confirmed += 1
        if offer.stale_confirmations >= STALE_UNAVAILABLE_CONFIRMATIONS:
            offer.source_availability = Offer.SourceAvailability.UNAVAILABLE
        offer.save(
            update_fields=[
                "suspected_stale_since",
                "stale_confirmations",
                "source_availability",
                "updated_at",
            ]
        )
    return {"marked_suspect": marked, "confirmed_stale": confirmed}


def clear_stale_suspicions(run: CrawlRun, *, seen_source_ids: set[str]) -> int:
    """Offers seen again in a full refresh lose their suspicion immediately."""

    if run.job.sync_mode != CrawlJob.SyncMode.FULL_REFRESH:
        raise CrawlJobStateInvalid("Only full-refresh runs may clear staleness.")
    from offers.models import Offer

    return (
        Offer.objects.filter(
            sku__spu__source_identities__source_system=run.job.source_catalog.source_system,
            source_identities__source_id__in=seen_source_ids,
        )
        .exclude(suspected_stale_since=None)
        .update(suspected_stale_since=None, stale_confirmations=0, updated_at=timezone.now())
    )


# ---------------------------------------------------------------------------
# Global circuit breaker
# ---------------------------------------------------------------------------


def report_account_risk(account: CrawlerAccount, *, reason: str, observed_at=None) -> dict:
    """Register one risk-control hit and trip the breaker if needed.

    The account itself is removed from the queue by WP-13's
    ``flag_account_risk_control``; this adds the cross-account count.
    """

    observed_at = observed_at or timezone.now()
    with transaction.atomic():
        breaker = _breakers()
        if not breaker.is_tripped:
            window_start = observed_at - timedelta(minutes=breaker.window_minutes)
            recent_hits = CrawlerAccount.objects.filter(
                risk_flagged_at__gte=window_start
            ).values_list("pk", flat=True)
            distinct_accounts = set(recent_hits)
            # The flagged account is already persisted by the caller.
            if len(distinct_accounts) >= breaker.account_threshold:
                breaker.is_tripped = True
                breaker.tripped_at = observed_at
                breaker.reason = (
                    f"{len(distinct_accounts)} accounts hit risk control within "
                    f"{breaker.window_minutes} minutes; last reason: {reason.strip()}"
                )
                breaker.save(update_fields=["is_tripped", "tripped_at", "reason", "updated_at"])
                pause_all_ready_jobs(f"Global circuit breaker tripped: {breaker.reason}")
        return {
            "tripped": breaker.is_tripped,
            "reason": breaker.reason if breaker.is_tripped else "",
        }


def pause_all_ready_jobs(reason: str) -> int:
    """Move every READY/RUNNING job to PAUSED while the breaker is tripped."""

    from crawler_control.services import _transition_job

    paused = 0
    for job in CrawlJob.objects.filter(status__in={CrawlJob.Status.READY, CrawlJob.Status.RUNNING}):
        try:
            _transition_job(job, CrawlJob.Status.PAUSED)
            paused += 1
        except CrawlJobStateInvalid:
            continue
    del reason
    return paused


def ensure_breaker_allows_run() -> None:
    """Guard called by ``start_run``; refuses while the breaker is tripped."""

    breaker = _breakers()
    if breaker.is_tripped:
        raise CrawlerControlError(f"CRAWL_GLOBAL_CIRCUIT_BREAKER_TRIPPED: {breaker.reason}")


def reset_circuit_breaker(*, reason: str, observed_at=None) -> CrawlerCircuitBreaker:
    """Human-reviewed reset; jobs stay paused and must be resumed manually."""

    if not reason.strip():
        raise CrawlerControlError("A reset reason is required after human review.")
    observed_at = observed_at or timezone.now()
    with transaction.atomic():
        breaker = _breakers()
        breaker.is_tripped = False
        breaker.reset_at = observed_at
        breaker.reset_reason = reason.strip()
        breaker.save(update_fields=["is_tripped", "reset_at", "reset_reason", "updated_at"])
        return breaker


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------


def requeue_staging_for_replay(staging: StagingProduct, *, note: str = "") -> StagingProduct:
    """Requeue a rejected staging row after a parser fix (raw response replay)."""

    if staging.status != StagingProduct.Status.REJECTED:
        raise CrawlerControlError("Only rejected staging rows can be requeued for replay.")
    staging.status = StagingProduct.Status.PENDING
    staging.error_message = f"Requeued for replay: {note.strip()}"[:500]
    staging.save(update_fields=["status", "error_message", "updated_at"])
    return staging
