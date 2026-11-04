import base64
import gzip
import hashlib
import json
import os
import secrets
from datetime import timedelta
from pathlib import Path

from catalog.models import SourceCategorySnapshot, SourceCategoryTreeVersion
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from crawler_control.domain import (
    CrawlAccountStateInvalid,
    CrawlJobParamsInvalid,
    CrawlJobStateInvalid,
    CrawlRunStateInvalid,
    CrawlSessionSecretInvalid,
    RawResponseInvalid,
    RiskControlPaused,
)
from crawler_control.models import CrawlerAccount, CrawlJob, CrawlRun, RawResponse

PASSWORD_LIKE_KEY_PARTS = ("password", "passwd")

REVIEW_TARGET_MIN = 1
REVIEW_TARGET_MAX = 300
REVIEW_TARGET_DEFAULT = 50


# ---------------------------------------------------------------------------
# Account sessions
# ---------------------------------------------------------------------------


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.CRAWL_SESSION_ENCRYPTION_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _reject_password_like_fields(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise CrawlSessionSecretInvalid("The session payload must be an object.")
    for key in payload:
        lowered = str(key).casefold()
        if any(part in lowered for part in PASSWORD_LIKE_KEY_PARTS):
            raise CrawlSessionSecretInvalid(
                f"Refusing to store credential-like field: {key}. "
                "Passwords are never collected or persisted."
            )


def record_account_session(account: CrawlerAccount, session_payload: dict, *, observed_at=None):
    """Encrypt and store the Joybuy session blob for an account.

    The payload holds session cookies/tokens only; password-like fields are
    rejected before anything touches the database.
    """

    _reject_password_like_fields(session_payload)
    observed_at = observed_at or timezone.now()
    account.session_cipher = (
        _fernet().encrypt(json.dumps(session_payload, separators=(",", ":")).encode()).decode()
    )
    account.session_status = CrawlerAccount.SessionStatus.VALID
    account.session_updated_at = observed_at
    account.last_login_at = observed_at
    account.save(
        update_fields=[
            "session_cipher",
            "session_status",
            "session_updated_at",
            "last_login_at",
            "updated_at",
        ]
    )
    return account


def load_account_session(account: CrawlerAccount) -> dict:
    if not account.session_cipher:
        raise CrawlSessionSecretInvalid("The account has no stored session.")
    try:
        plain = _fernet().decrypt(account.session_cipher.encode())
    except InvalidToken as exc:
        raise CrawlSessionSecretInvalid(
            "The stored session cannot be decrypted with the configured key."
        ) from exc
    return json.loads(plain.decode())


def mark_session_expired(account: CrawlerAccount, *, observed_at=None):
    """Mark a session invalid; only a fresh manual login restores selection."""

    account.session_status = CrawlerAccount.SessionStatus.EXPIRED
    account.session_cipher = ""
    account.session_updated_at = observed_at or timezone.now()
    account.save(
        update_fields=["session_status", "session_cipher", "session_updated_at", "updated_at"]
    )
    return account


def create_crawler_account(
    *,
    label: str,
    account_group: str = "default",
    rate_limit_per_minute=None,
    concurrency_limit=None,
    note: str = "",
) -> CrawlerAccount:
    if not label.strip():
        raise CrawlAccountStateInvalid("A crawler account label is required.")
    return CrawlerAccount.objects.create(
        label=label.strip(),
        account_group=account_group.strip() or "default",
        rate_limit_per_minute=rate_limit_per_minute,
        concurrency_limit=concurrency_limit,
        note=note.strip(),
    )


def flag_account_risk_control(account: CrawlerAccount, *, reason: str, observed_at=None):
    """Immediately remove an account from the queue and pause its active run."""

    if not reason.strip():
        raise CrawlAccountStateInvalid("A risk-control reason is required.")
    observed_at = observed_at or timezone.now()
    with transaction.atomic():
        account = CrawlerAccount.objects.select_for_update().get(pk=account.pk)
        account.status = CrawlerAccount.Status.PAUSED_RISK_CONTROL
        account.risk_flagged_at = observed_at
        account.risk_reason = reason.strip()
        account.save(
            update_fields=[
                "status",
                "risk_flagged_at",
                "risk_reason",
                "updated_at",
            ]
        )
        running = (
            CrawlRun.objects.select_for_update()
            .filter(account=account, status=CrawlRun.Status.RUNNING)
            .first()
        )
        if running:
            _transition_run(
                running,
                CrawlRun.Status.PAUSED,
                pause_reason=CrawlRun.PauseReason.RISK_CONTROL,
                at=observed_at,
            )
            if running.job.status == CrawlJob.Status.RUNNING:
                _transition_job(running.job, CrawlJob.Status.PAUSED)
        # Cross-account circuit-breaker accounting (WP-19); the account is
        # already out of the queue, this counts it toward the global trip.
        from crawler_control.quality_services import report_account_risk

        report_account_risk(account, reason=reason.strip(), observed_at=observed_at)
    return account


def reactivate_account(account: CrawlerAccount, *, note: str = "", observed_at=None):
    """Manual reactivation after human review of a risk-control pause."""

    observed_at = observed_at or timezone.now()
    with transaction.atomic():
        account = CrawlerAccount.objects.select_for_update().get(pk=account.pk)
        if account.status != CrawlerAccount.Status.PAUSED_RISK_CONTROL:
            raise CrawlAccountStateInvalid("Only risk-control paused accounts can be reactivated.")
        account.status = CrawlerAccount.Status.ACTIVE
        account.risk_flagged_at = None
        account.risk_reason = ""
        if note.strip():
            account.note = note.strip()[:500]
        account.save(
            update_fields=["status", "risk_flagged_at", "risk_reason", "note", "updated_at"]
        )
    return account


def _select_account_for_run(account_group: str) -> CrawlerAccount:
    account = (
        CrawlerAccount.objects.filter(
            account_group=account_group,
            status=CrawlerAccount.Status.ACTIVE,
            session_status=CrawlerAccount.SessionStatus.VALID,
        )
        .order_by("last_used_at", "pk")
        .first()
    )
    if account is None:
        raise CrawlAccountStateInvalid(
            f"No selectable crawler account with a valid session in group '{account_group}'."
        )
    return account


# ---------------------------------------------------------------------------
# Job parameters and creation
# ---------------------------------------------------------------------------


def _infer_include_subcategories(source_category) -> bool:
    """Second-level categories default to including children, deeper do not."""

    snapshot = SourceCategorySnapshot.objects.filter(
        category=source_category,
        tree_version__status=SourceCategoryTreeVersion.Status.PUBLISHED,
    ).order_by("-tree_version__captured_at", "-pk")
    latest = snapshot.first()
    if latest is None:
        return True
    return latest.depth <= 1


def create_crawl_job(
    *,
    name: str,
    market,
    source_catalog,
    source_category,
    product_limit: int,
    include_subcategories=None,
    listing_sort: str = CrawlJob.ListingSort.SOURCE_DEFAULT,
    sync_mode: str = CrawlJob.SyncMode.INCREMENTAL,
    review_target: int = REVIEW_TARGET_DEFAULT,
    locale: str = "en-GB",
    currency=None,
    source_tree_version=None,
    priority: int = 0,
    scheduled_at=None,
    concurrency: int = 1,
    rate_limit_per_minute=None,
    account_group: str = "default",
    failure_strategy: str = CrawlJob.FailureStrategy.PAUSE,
    allow_manual_resume: bool = True,
    download_product_media: bool = True,
    download_review_media: bool = True,
    download_detail_media: bool = False,
    created_by=None,
) -> CrawlJob:
    if not name.strip():
        raise CrawlJobParamsInvalid("A job name is required.")
    if isinstance(product_limit, bool) or not isinstance(product_limit, int) or product_limit < 1:
        raise CrawlJobParamsInvalid("product_limit must be a positive integer.")
    if isinstance(review_target, bool) or not isinstance(review_target, int):
        raise CrawlJobParamsInvalid("review_target must be an integer.")
    if not REVIEW_TARGET_MIN <= review_target <= REVIEW_TARGET_MAX:
        raise CrawlJobParamsInvalid(
            f"review_target must be between {REVIEW_TARGET_MIN} and {REVIEW_TARGET_MAX}."
        )
    if listing_sort not in CrawlJob.ListingSort.values:
        raise CrawlJobParamsInvalid("Unknown listing sort.")
    if sync_mode not in CrawlJob.SyncMode.values:
        raise CrawlJobParamsInvalid("Unknown sync mode.")
    if failure_strategy not in CrawlJob.FailureStrategy.values:
        raise CrawlJobParamsInvalid("Unknown failure strategy.")
    if isinstance(concurrency, bool) or not isinstance(concurrency, int) or concurrency < 1:
        raise CrawlJobParamsInvalid("concurrency must be a positive integer.")

    if include_subcategories is None:
        category_mode = (
            CrawlJob.CategoryMode.INCLUDE_SUBCATEGORIES
            if _infer_include_subcategories(source_category)
            else CrawlJob.CategoryMode.CURRENT_ONLY
        )
    elif include_subcategories is True:
        category_mode = CrawlJob.CategoryMode.INCLUDE_SUBCATEGORIES
    elif include_subcategories is False:
        category_mode = CrawlJob.CategoryMode.CURRENT_ONLY
    else:
        raise CrawlJobParamsInvalid("include_subcategories must be a boolean or None.")

    random_seed = None
    if listing_sort == CrawlJob.ListingSort.RANDOM:
        random_seed = secrets.randbits(48)

    return CrawlJob.objects.create(
        name=name.strip(),
        priority=priority,
        market=market,
        currency=currency,
        locale=locale.strip() or "en-GB",
        source_catalog=source_catalog,
        source_category=source_category,
        source_tree_version=source_tree_version,
        category_mode=category_mode,
        product_limit=product_limit,
        listing_sort=listing_sort,
        random_seed=random_seed,
        sync_mode=sync_mode,
        review_target=review_target,
        download_product_media=download_product_media,
        download_review_media=download_review_media,
        download_detail_media=download_detail_media,
        scheduled_at=scheduled_at,
        concurrency=concurrency,
        rate_limit_per_minute=rate_limit_per_minute,
        account_group=account_group.strip() or "default",
        failure_strategy=failure_strategy,
        allow_manual_resume=allow_manual_resume,
        created_by=created_by,
    )


def mark_job_ready(job: CrawlJob) -> CrawlJob:
    if job.status != CrawlJob.Status.DRAFT:
        raise CrawlJobStateInvalid("Only draft jobs can be marked ready.")
    job.status = CrawlJob.Status.READY
    job.save(update_fields=["status", "updated_at"])
    return job


# ---------------------------------------------------------------------------
# Job and run state machine
# ---------------------------------------------------------------------------

JOB_TRANSITIONS = {
    CrawlJob.Status.DRAFT: {CrawlJob.Status.READY, CrawlJob.Status.CANCELED},
    CrawlJob.Status.READY: {CrawlJob.Status.RUNNING, CrawlJob.Status.CANCELED},
    CrawlJob.Status.RUNNING: {
        CrawlJob.Status.PAUSED,
        CrawlJob.Status.COMPLETED,
        CrawlJob.Status.FAILED,
        CrawlJob.Status.READY,
        CrawlJob.Status.CANCELED,
    },
    CrawlJob.Status.PAUSED: {CrawlJob.Status.RUNNING, CrawlJob.Status.CANCELED},
    CrawlJob.Status.COMPLETED: set(),
    CrawlJob.Status.CANCELED: set(),
    CrawlJob.Status.FAILED: {CrawlJob.Status.RUNNING, CrawlJob.Status.CANCELED},
}


def _transition_job(job: CrawlJob, target: str) -> CrawlJob:
    if target not in JOB_TRANSITIONS.get(job.status, set()):
        raise CrawlJobStateInvalid(f"Cannot transition job from {job.status} to {target}.")
    job.status = target
    job.save(update_fields=["status", "updated_at"])
    return job


def _job_params_snapshot(job: CrawlJob) -> dict:
    return {
        "market": job.market.code,
        "currency": job.currency.code if job.currency else job.market.default_currency.code,
        "locale": job.locale,
        "source_catalog": job.source_catalog.source_system,
        "source_category_id": job.source_category.source_id,
        "source_tree_version": job.source_tree_version.version_key
        if job.source_tree_version
        else None,
        "category_mode": job.category_mode,
        "product_limit": job.product_limit,
        "listing_sort": job.listing_sort,
        "random_seed": job.random_seed,
        "sync_mode": job.sync_mode,
        "review_target": job.review_target,
        "download_product_media": job.download_product_media,
        "download_review_media": job.download_review_media,
        "download_detail_media": job.download_detail_media,
        "concurrency": job.concurrency,
        "rate_limit_per_minute": job.rate_limit_per_minute,
        "account_group": job.account_group,
        "failure_strategy": job.failure_strategy,
    }


def start_run(job: CrawlJob, *, started_at=None) -> CrawlRun:
    """Transition READY -> RUNNING and create the first pinned run.

    Refused while the global circuit breaker is tripped (WP-19).
    """

    started_at = started_at or timezone.now()
    with transaction.atomic():
        from crawler_control.quality_services import ensure_breaker_allows_run

        ensure_breaker_allows_run()
        job = CrawlJob.objects.select_for_update().get(pk=job.pk)
        if job.status not in {
            CrawlJob.Status.READY,
            CrawlJob.Status.PAUSED,
            CrawlJob.Status.FAILED,
        }:
            raise CrawlJobStateInvalid(f"Job in status {job.status} cannot start a run.")
        _transition_job(job, CrawlJob.Status.RUNNING)
        account = _select_account_for_run(job.account_group)
        account.last_used_at = started_at
        account.save(update_fields=["last_used_at", "updated_at"])
        return CrawlRun.objects.create(
            job=job,
            account=account,
            status=CrawlRun.Status.RUNNING,
            params_snapshot=_job_params_snapshot(job),
            started_at=started_at,
        )


def pause_run(run: CrawlRun, *, reason: str, observed_at=None) -> CrawlRun:
    observed_at = observed_at or timezone.now()
    with transaction.atomic():
        run = CrawlRun.objects.select_for_update().get(pk=run.pk)
        if run.status != CrawlRun.Status.RUNNING:
            raise CrawlRunStateInvalid("Only running crawls can be paused.")
        pause_reason = reason
        if pause_reason not in CrawlRun.PauseReason.values or pause_reason in {
            CrawlRun.PauseReason.NONE,
        }:
            raise CrawlRunStateInvalid("A pause requires MANUAL, RISK_CONTROL or FAILURE_POLICY.")
        _transition_run(run, CrawlRun.Status.PAUSED, pause_reason=pause_reason, at=observed_at)
        if run.job.status == CrawlJob.Status.RUNNING:
            _transition_job(run.job, CrawlJob.Status.PAUSED)
        return run


def resume_run(run: CrawlRun, *, observed_at=None) -> CrawlRun:
    """Manually resume a paused run with the same pinned account.

    A risk-control pause can only be lifted after the pinned account has
    been reviewed and reactivated by a human; runs are never taken over by
    another account.
    """

    observed_at = observed_at or timezone.now()
    with transaction.atomic():
        run = CrawlRun.objects.select_for_update().select_related("job", "account").get(pk=run.pk)
        if run.status != CrawlRun.Status.PAUSED:
            raise CrawlRunStateInvalid("Only paused runs can be resumed.")
        if not run.job.allow_manual_resume:
            raise CrawlRunStateInvalid("The job does not allow manual resume.")
        account = run.account
        if run.pause_reason == CrawlRun.PauseReason.RISK_CONTROL:
            if account is None or not account.is_selectable:
                raise RiskControlPaused(
                    "A risk-control paused run requires its account to be reviewed "
                    "and reactivated by a human first."
                )
        elif account is None or not account.is_selectable:
            raise CrawlAccountStateInvalid(
                "The pinned account is not selectable; restore its session or status first."
            )
        _transition_run(run, CrawlRun.Status.RUNNING, pause_reason=None, at=observed_at)
        if run.job.status == CrawlJob.Status.PAUSED:
            _transition_job(run.job, CrawlJob.Status.RUNNING)
        return run


def cancel_run(run: CrawlRun, *, observed_at=None) -> CrawlRun:
    observed_at = observed_at or timezone.now()
    with transaction.atomic():
        run = CrawlRun.objects.select_for_update().select_related("job").get(pk=run.pk)
        if run.status not in {
            CrawlRun.Status.PENDING,
            CrawlRun.Status.RUNNING,
            CrawlRun.Status.PAUSED,
        }:
            raise CrawlRunStateInvalid("Only open runs can be canceled.")
        _transition_run(run, CrawlRun.Status.CANCELED, at=observed_at, finish=True)
        job = run.job
        if job.status in {CrawlJob.Status.RUNNING, CrawlJob.Status.PAUSED}:
            has_open_runs = (
                CrawlRun.objects.filter(
                    job=job,
                    status__in={
                        CrawlRun.Status.PENDING,
                        CrawlRun.Status.RUNNING,
                        CrawlRun.Status.PAUSED,
                    },
                )
                .exclude(pk=run.pk)
                .exists()
            )
            if not has_open_runs:
                _transition_job(job, CrawlJob.Status.CANCELED)
        return run


def complete_run(run: CrawlRun, *, outcome: str, observed_at=None) -> CrawlRun:
    observed_at = observed_at or timezone.now()
    with transaction.atomic():
        run = CrawlRun.objects.select_for_update().select_related("job").get(pk=run.pk)
        if run.status != CrawlRun.Status.RUNNING:
            raise CrawlRunStateInvalid("Only running runs can be completed.")
        if outcome not in {CrawlRun.Status.SUCCEEDED, CrawlRun.Status.FAILED}:
            raise CrawlRunStateInvalid("A run completes as SUCCEEDED or FAILED.")
        _transition_run(run, outcome, at=observed_at, finish=True)
        job = run.job
        if job.status != CrawlJob.Status.RUNNING:
            return run
        has_open_runs = (
            CrawlRun.objects.filter(
                job=job,
                status__in={
                    CrawlRun.Status.PENDING,
                    CrawlRun.Status.RUNNING,
                    CrawlRun.Status.PAUSED,
                },
            )
            .exclude(pk=run.pk)
            .exists()
        )
        if has_open_runs:
            return run
        if outcome == CrawlRun.Status.SUCCEEDED:
            _transition_job(job, CrawlJob.Status.COMPLETED)
        elif job.failure_strategy == CrawlJob.FailureStrategy.PAUSE:
            _transition_job(job, CrawlJob.Status.FAILED)
        else:
            _transition_job(job, CrawlJob.Status.READY)
        return run


def _transition_run(run: CrawlRun, target: str, *, at, pause_reason=None, finish=False):
    if target != CrawlRun.Status.PAUSED and run.status == CrawlRun.Status.PAUSED:
        allowed = {CrawlRun.Status.RUNNING, CrawlRun.Status.CANCELED, CrawlRun.Status.FAILED}
        if target not in allowed:
            raise CrawlRunStateInvalid(f"Cannot transition a paused run to {target}.")
    elif target == CrawlRun.Status.PAUSED and run.status != CrawlRun.Status.RUNNING:
        raise CrawlRunStateInvalid("Only running runs can be paused.")
    run.status = target
    if pause_reason is not None:
        run.pause_reason = pause_reason
    if target != CrawlRun.Status.PAUSED:
        run.pause_reason = CrawlRun.PauseReason.NONE
    if finish:
        run.finished_at = at
    run.save(update_fields=["status", "pause_reason", "finished_at", "updated_at"])
    return run


def update_run_progress(
    run: CrawlRun,
    *,
    discovered: int | None = None,
    downloaded: int | None = None,
    succeeded: int | None = None,
    failed: int | None = None,
) -> CrawlRun:
    """Accumulate progress counters; values are deltas, not absolutes."""

    fields = ["updated_at"]
    for field, delta in (
        ("discovered_count", discovered),
        ("downloaded_count", downloaded),
        ("succeeded_count", succeeded),
        ("failed_count", failed),
    ):
        if delta is not None:
            if isinstance(delta, bool) or not isinstance(delta, int) or delta < 0:
                raise CrawlRunStateInvalid(f"{field} delta must be a non-negative integer.")
            setattr(run, field, getattr(run, field) + delta)
            fields.append(field)
    run.save(update_fields=fields)
    return run


# ---------------------------------------------------------------------------
# Raw response archive
# ---------------------------------------------------------------------------

SENSITIVE_KEY_PARTS = ("password", "passwd", "cookie", "authorization", "set-cookie", "secret")


def redact_sensitive_keys(payload: dict) -> dict:
    """Strip credential-like keys from structured raw payloads before writing."""

    if not isinstance(payload, dict):
        raise RawResponseInvalid("Redaction expects a JSON object payload.")
    redacted = {}
    for key, value in payload.items():
        lowered = str(key).casefold()
        if any(part in lowered for part in SENSITIVE_KEY_PARTS):
            redacted[str(key)] = "[REDACTED]"
        else:
            redacted[str(key)] = value
    return redacted


def _raw_root() -> Path:
    root = Path(settings.CRAWL_RAW_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_raw_path(relative_path: str) -> Path:
    clean = str(relative_path).replace("\\", "/")
    if not clean or clean.startswith("/") or ".." in clean.split("/"):
        raise RawResponseInvalid("relative_path must stay inside the raw storage root.")
    full = (_raw_root() / clean).resolve()
    if _raw_root().resolve() not in full.parents and full != _raw_root().resolve():
        raise RawResponseInvalid("relative_path escapes the raw storage root.")
    return full


def record_raw_response(
    run: CrawlRun,
    *,
    url: str,
    status_code: int,
    payload: bytes,
    content_type: str = "",
    crawled_at=None,
) -> RawResponse:
    """Compress and archive one raw response, keeping the index row only here."""

    if not url.strip():
        raise RawResponseInvalid("A URL is required.")
    if not payload:
        raise RawResponseInvalid("An empty response payload cannot be archived.")
    crawled_at = crawled_at or timezone.now()
    digest = hashlib.sha256(payload).hexdigest()
    compressed = gzip.compress(payload)
    relative_path = f"{crawled_at.strftime('%Y/%m/%d')}/{run.public_id}/{digest}.gz"
    full_path = resolve_raw_path(relative_path)
    full_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = full_path.with_name(f"{full_path.name}.tmp-{os.getpid()}")
    tmp_path.write_bytes(compressed)
    os.replace(tmp_path, full_path)
    return RawResponse.objects.create(
        job=run.job,
        run=run,
        url=url.strip(),
        status_code=status_code,
        content_type=(content_type or "").strip(),
        response_hash=digest,
        byte_size=len(payload),
        relative_path=relative_path,
        crawled_at=crawled_at,
        expires_at=crawled_at + timedelta(days=settings.CRAWL_RAW_RETENTION_DAYS),
    )


def purge_expired_raw_responses(*, now=None) -> int:
    """Delete expired payload files; index rows and hashes are kept forever."""

    now = now or timezone.now()
    expired = RawResponse.objects.filter(expires_at__lt=now, file_deleted=False)
    purged = 0
    for row in expired.iterator(chunk_size=200):
        full_path = resolve_raw_path(row.relative_path)
        if full_path.exists():
            full_path.unlink()
        row.file_deleted = True
        row.deleted_at = now
        row.save(update_fields=["file_deleted", "deleted_at"])
        purged += 1
    return purged
