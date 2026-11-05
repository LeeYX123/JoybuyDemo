import base64
import gzip
import hashlib
import json
import os
import secrets
from datetime import timedelta
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from catalog.models import SourceCategorySnapshot, SourceCategoryTreeVersion
from crawler_control.domain import (
    CrawlAccountStateInvalid,
    CrawlJobParamsInvalid,
    CrawlJobStateInvalid,
    CrawlRunStateInvalid,
    CrawlSessionSecretInvalid,
    RawResponseInvalid,
    RiskControlPaused,
)
from crawler_control.models import (
    CrawlerAccount,
    CrawlerAccountGroup,
    CrawlJob,
    CrawlJobSourceSelection,
    CrawlRun,
    CrawlRunEvent,
    RawResponse,
)

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


def ensure_account_group(name: str) -> CrawlerAccountGroup:
    """Get or create a group row; the group list must never lose a name."""

    cleaned = (name or "").strip() or "default"
    group, _ = CrawlerAccountGroup.objects.get_or_create(name=cleaned)
    return group


def create_account_group(*, name: str, note: str = "") -> CrawlerAccountGroup:
    """Create an empty group so it can be chosen before accounts exist."""

    cleaned = (name or "").strip()
    if not cleaned:
        raise CrawlAccountStateInvalid("账号组名称必填。")
    if CrawlerAccountGroup.objects.filter(name=cleaned).exists():
        raise CrawlAccountStateInvalid(f"账号组「{cleaned}」已存在。")
    return CrawlerAccountGroup.objects.create(name=cleaned, note=(note or "").strip()[:200])


def list_account_groups() -> list[CrawlerAccountGroup]:
    return list(CrawlerAccountGroup.objects.all())


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
    group = ensure_account_group(account_group)
    return CrawlerAccount.objects.create(
        label=label.strip(),
        account_group=group.name,
        rate_limit_per_minute=rate_limit_per_minute,
        concurrency_limit=concurrency_limit,
        note=note.strip(),
    )


def update_crawler_account(
    account: CrawlerAccount,
    *,
    label=None,
    account_group=None,
    note=None,
) -> CrawlerAccount:
    """Edit the operator-facing fields; the stored session is left alone."""

    if account.deleted_at is not None:
        raise CrawlAccountStateInvalid("该账号已删除，不能编辑。")
    fields = []
    if label is not None:
        cleaned = str(label).strip()
        if not cleaned:
            raise CrawlAccountStateInvalid("账号名称不能为空。")
        account.label = cleaned[:120]
        fields.append("label")
    if account_group is not None:
        account.account_group = ensure_account_group(str(account_group)).name
        fields.append("account_group")
    if note is not None:
        account.note = str(note).strip()[:500]
        fields.append("note")
    if not fields:
        return account
    account.save(update_fields=[*fields, "updated_at"])
    return account


def delete_crawler_account(account: CrawlerAccount, *, reason: str = "") -> CrawlerAccount:
    """Soft delete: hide the account, destroy its session, keep run history.

    A hard delete would null out ``CrawlRun.account`` and erase which identity
    a past run used, so the row stays and only the credentials are dropped.
    """

    if account.deleted_at is not None:
        return account
    if CrawlRun.objects.filter(account=account, status=CrawlRun.Status.RUNNING).exists():
        raise CrawlAccountStateInvalid("该账号正在被运行中的任务使用，请先暂停或取消任务再删除。")
    account.deleted_at = timezone.now()
    account.status = CrawlerAccount.Status.DISABLED
    account.session_status = CrawlerAccount.SessionStatus.UNKNOWN
    account.session_cipher = ""
    account.risk_reason = ""
    account.note = (reason or account.note)[:500]
    account.save(
        update_fields=[
            "deleted_at",
            "status",
            "session_status",
            "session_cipher",
            "risk_reason",
            "note",
            "updated_at",
        ]
    )
    return account


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


def _session_has_cookies(account) -> bool:
    """True when the stored session actually contains replayable cookies.

    ``session_status=VALID`` on its own proves nothing: a session blob
    written by a fixture/placeholder (e.g. ``{"joybuy_session": "..."}``)
    is "valid" but carries zero cookies, so a run bound to it crawls
    anonymously while looking authenticated. That exact case produced
    login walls on 2026-11-05.
    """

    try:
        payload = load_account_session(account)
    except Exception:  # noqa: BLE001 - undecryptable = unusable
        return False
    cookies = payload.get("cookies") if isinstance(payload, dict) else None
    return any(
        str(cookie.get("name") or "").strip()
        for cookie in (cookies or [])
        if isinstance(cookie, dict)
    )


def _account_unusable_reason(account) -> str:
    """Chinese reason why an account cannot carry a crawl ('' when usable)."""

    if account is None:
        return "没有可用账号"
    if account.status != CrawlerAccount.Status.ACTIVE:
        return f"账号状态为 {account.status}"
    if account.session_status != CrawlerAccount.SessionStatus.VALID:
        return f"会话状态为 {account.session_status}"
    if not account.session_cipher:
        return "没有保存会话"
    if not _session_has_cookies(account):
        return "会话里没有可用 Cookie，需要重新登录"
    return ""


def _account_is_usable(account) -> bool:
    """An account can carry a crawl only when it is active and has cookies."""

    return not _account_unusable_reason(account)


def _resolve_account_for_run(job: CrawlJob):
    """Pinned account first, then the group's least-recently-used account.

    Returns ``(account, note)``: ``note`` is a Chinese explanation when the
    pinned account could not be used, so the run log says *why* a different
    account (or none at all) was picked instead of failing silently.
    """

    pinned = job.account
    if pinned is None:
        return _select_account_for_run(job.account_group), ""
    if _account_is_usable(pinned):
        return pinned, ""
    fallback = _select_account_for_run(job.account_group)
    tail = (
        f"已改按账号组「{job.account_group}」自动选择。"
        if fallback is not None
        else "组内也没有可用账号，本轮改为匿名抓取。"
    )
    return (
        fallback,
        f"任务指定的账号「{pinned.label}」当前不可用（{_account_unusable_reason(pinned)}），{tail}",
    )


def usable_accounts_for_run(job: CrawlJob) -> list[CrawlerAccount]:
    """Accounts a run may rotate through: pinned first, then the group.

    2026-11-05 (user decision): a crawl may spread its work across several
    accounts instead of holding one identity. Only accounts that really
    carry cookies are offered — a placeholder session would look
    authenticated while crawling anonymously.
    """

    pooled: list[CrawlerAccount] = []
    seen: set[int] = set()
    if job.account_id and _account_is_usable(job.account):
        pooled.append(job.account)
        seen.add(job.account_id)
    candidates = (
        CrawlerAccount.objects.filter(
            account_group=job.account_group,
            status=CrawlerAccount.Status.ACTIVE,
            session_status=CrawlerAccount.SessionStatus.VALID,
            deleted_at__isnull=True,
        )
        .exclude(pk=job.account_id)
        .order_by("last_used_at", "pk")[:50]
    )
    for account in candidates:
        if account.pk in seen or not _account_is_usable(account):
            continue
        pooled.append(account)
        seen.add(account.pk)
    return pooled


def _select_account_for_run(account_group: str) -> CrawlerAccount | None:
    """Pick the least-recently-used selectable account, or None.

    Since unauthenticated crawling is supported (2026-11-05), a group with
    no valid session no longer blocks a run: the run proceeds without a
    stored session and switches to account cookies only when the source
    demands a login (requirement: try logged-out first).
    """

    candidates = CrawlerAccount.objects.filter(
        account_group=account_group,
        status=CrawlerAccount.Status.ACTIVE,
        session_status=CrawlerAccount.SessionStatus.VALID,
        deleted_at__isnull=True,
    ).order_by("last_used_at", "pk")[:20]
    for account in candidates:
        # A "VALID" session with no cookies is not usable — picking it would
        # produce an anonymous crawl that looks authenticated.
        if _account_is_usable(account):
            return account
    return None


def set_account_status(account: CrawlerAccount, *, status: str) -> CrawlerAccount:
    """Admin enable/disable; risk-paused accounts must go through review."""

    if status not in {CrawlerAccount.Status.ACTIVE, CrawlerAccount.Status.DISABLED}:
        raise CrawlAccountStateInvalid("Only ACTIVE or DISABLED can be set directly.")
    if account.status == CrawlerAccount.Status.PAUSED_RISK_CONTROL:
        raise CrawlAccountStateInvalid(
            "A risk-paused account must be reactivated through human review."
        )
    account.status = status
    account.save(update_fields=["status", "updated_at"])
    return account


def verify_account_session(account: CrawlerAccount) -> dict:
    """Lightweight session check: render the homepage with stored cookies.

    Signed in = the real homepage's VISIBLE text no longer shows the
    Sign in button (scripts still mention it; same rule as the login
    command). Marks the account expired when the check fails.
    """

    observed_at = timezone.now()
    try:
        cookies = load_account_session(account).get("cookies") or []
    except CrawlSessionSecretInvalid:
        return {"verified": False, "reason": "NO_SESSION"}
    if not cookies:
        return {"verified": False, "reason": "NO_SESSION"}

    import sys
    from pathlib import Path

    crawler_dir = str(Path(__file__).resolve().parents[2] / "crawler")
    if crawler_dir not in sys.path:
        sys.path.insert(0, crawler_dir)
    from joybuy_crawler.render import _visible_text, render_page

    page = render_page(
        "https://www.joybuy.co.uk/",
        cookies=cookies,
        headless=True,
        wait_seconds=4,
    )
    evidence = {"cookie_count": len(cookies)}
    if page.error or not page.html:
        return {"verified": False, "reason": f"RENDER_FAILED: {page.error[:200]}", **evidence}
    if page.risk_control:
        # Never count a blocked page as a session failure.
        return {"verified": False, "reason": "RISK_CONTROL_BLOCKED", **evidence}
    logged_in = "sign in" not in _visible_text(page.html).lower()
    if logged_in:
        account.last_verified_at = observed_at
        account.session_status = CrawlerAccount.SessionStatus.VALID
        account.save(update_fields=["last_verified_at", "session_status", "updated_at"])
        return {
            "verified": True,
            "reason": "",
            **evidence,
            "detail": "在隔离无头浏览器中加载了该账号存储的加密 Cookie，页面已无 Sign in 按钮。",
        }
    mark_session_expired(account, observed_at=observed_at)
    return {"verified": False, "reason": "SESSION_EXPIRED", **evidence}


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
    source_category=None,
    product_limit: int,
    source_categories: list[dict] | None = None,
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
    account=None,
    failure_strategy: str = CrawlJob.FailureStrategy.PAUSE,
    allow_manual_resume: bool = True,
    download_product_media: bool = True,
    download_review_media: bool = True,
    download_detail_media: bool = False,
    created_by=None,
) -> CrawlJob:
    """Create a crawl job with one or more frozen source-category selections.

    ``source_categories`` is the multi-category form: a list of
    ``{"category": SourceCategory, "include_descendants": bool}`` dicts.
    The single ``source_category`` argument remains for legacy callers and
    is wrapped into one selection. Every selection pins
    ``source_tree_version`` (the latest published version when not given)
    so later tree syncs never change what the job crawls.
    """

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

    selections = []
    for entry in source_categories or []:
        category = (entry or {}).get("category")
        if category is None:
            raise CrawlJobParamsInvalid("Every source selection needs a category.")
        include = (entry or {}).get("include_descendants")
        if include is None:
            include = include_subcategories
        if include is None:
            include = _infer_include_subcategories(category)
        selections.append({"category": category, "include_descendants": bool(include)})
    if source_category is not None and not selections:
        include = include_subcategories
        if include is None:
            include = _infer_include_subcategories(source_category)
        selections = [{"category": source_category, "include_descendants": bool(include)}]
    if not selections:
        raise CrawlJobParamsInvalid("At least one source category selection is required.")
    seen_category_pks = set()
    for entry in selections:
        if entry["category"].catalog_id != source_catalog.pk:
            raise CrawlJobParamsInvalid("A selected category belongs to a different catalog.")
        if entry["category"].pk in seen_category_pks:
            raise CrawlJobParamsInvalid("Duplicate source category selection.")
        seen_category_pks.add(entry["category"].pk)

    if source_tree_version is None:
        source_tree_version = (
            SourceCategoryTreeVersion.objects.filter(
                catalog=source_catalog,
                status=SourceCategoryTreeVersion.Status.PUBLISHED,
            )
            .order_by("-captured_at", "-pk")
            .first()
        )
    if source_tree_version is None:
        raise CrawlJobParamsInvalid(
            f"Source catalog '{source_catalog.source_system}' has no published tree version."
        )
    from catalog.models import SourceCategorySnapshot

    covered_pks = set(
        SourceCategorySnapshot.objects.filter(tree_version=source_tree_version).values_list(
            "category_id", flat=True
        )
    )
    missing = [
        entry["category"].source_id
        for entry in selections
        if entry["category"].pk not in covered_pks
    ]
    if missing:
        raise CrawlJobParamsInvalid(
            "Categories missing from the frozen tree version: " + ", ".join(missing)
        )

    category_mode = (
        CrawlJob.CategoryMode.INCLUDE_SUBCATEGORIES
        if any(entry["include_descendants"] for entry in selections)
        else CrawlJob.CategoryMode.CURRENT_ONLY
    )

    random_seed = None
    if listing_sort == CrawlJob.ListingSort.RANDOM:
        random_seed = secrets.randbits(48)

    # Legacy single-category column keeps the first selection so old reads
    # keep working; the authoritative scope lives in CrawlJobSourceSelection.
    with transaction.atomic():
        job = CrawlJob.objects.create(
            name=name.strip(),
            priority=priority,
            market=market,
            currency=currency,
            locale=locale.strip() or "en-GB",
            source_catalog=source_catalog,
            source_category=selections[0]["category"],
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
            account=account,
            failure_strategy=failure_strategy,
            allow_manual_resume=allow_manual_resume,
            created_by=created_by,
        )
        CrawlJobSourceSelection.objects.bulk_create(
            [
                CrawlJobSourceSelection(
                    job=job,
                    source_category=entry["category"],
                    source_tree_version=source_tree_version,
                    include_descendants=entry["include_descendants"],
                    sort_order=index,
                )
                for index, entry in enumerate(selections)
            ]
        )
    return job


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
    selections = [
        {
            "source_category_id": selection.source_category.source_id,
            "include_descendants": selection.include_descendants,
        }
        for selection in job.source_selections.select_related("source_category").order_by(
            "sort_order", "pk"
        )
    ]
    return {
        "market": job.market.code,
        "currency": job.currency.code if job.currency else job.market.default_currency.code,
        "locale": job.locale,
        "source_catalog": job.source_catalog.source_system,
        "source_category_id": job.source_category.source_id,
        "source_categories": selections,
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
        account, account_note = _resolve_account_for_run(job)
        if account is not None:
            account.last_used_at = started_at
            account.save(update_fields=["last_used_at", "updated_at"])
        run = CrawlRun.objects.create(
            job=job,
            account=account,
            status=CrawlRun.Status.RUNNING,
            params_snapshot=_job_params_snapshot(job),
            started_at=started_at,
        )
        if account_note:
            record_run_event(
                run,
                level=CrawlRunEvent.Level.WARNING,
                code="ACCOUNT_FALLBACK",
                message=account_note,
            )
        if account is None:
            record_run_event(
                run,
                level=CrawlRunEvent.Level.INFO,
                code="RUN_UNAUTHENTICATED",
                message="本账号组内没有可用会话的爬虫账号，本轮以未登录状态启动"
                "（先按匿名流程抓取）。",
            )
        else:
            # Making the account visible in the run log is the point: ops must
            # be able to tell at a glance whether the crawl carried a session.
            record_run_event(
                run,
                level=CrawlRunEvent.Level.INFO,
                code="RUN_ACCOUNT_SELECTED",
                message=f"本轮使用爬虫账号「{account.label}」"
                f"（账号组 {account.account_group}），每次请求都会带上该账号的会话 Cookie。",
            )
        return run


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


def record_run_event(
    run: CrawlRun,
    *,
    level: str = CrawlRunEvent.Level.INFO,
    code: str = "",
    message: str,
    source_url: str = "",
) -> CrawlRunEvent:
    """Append one progress/diagnostic event for the run (admin UI reads these)."""

    if level not in CrawlRunEvent.Level.values:
        raise CrawlRunStateInvalid(f"Unknown run event level: {level}.")
    message = (message or "").strip()
    if not message:
        raise CrawlRunStateInvalid("A run event requires a message.")
    return CrawlRunEvent.objects.create(
        run=run,
        level=level,
        code=(code or "").strip()[:64],
        message=message[:1000],
        source_url=(source_url or "").strip()[:2000],
    )


def complete_run_failed(run: CrawlRun, *, reason: str, source_url: str = "") -> CrawlRun:
    """Fail a running run with a recorded reason; the job follows its policy."""

    record_run_event(
        run,
        level=CrawlRunEvent.Level.ERROR,
        code="RUN_FAILED",
        message=reason,
        source_url=source_url,
    )
    return complete_run(run, outcome=CrawlRun.Status.FAILED)


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
