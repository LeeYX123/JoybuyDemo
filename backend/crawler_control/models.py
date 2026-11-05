import uuid

from django.db import models


class CrawlerAccountGroup(models.Model):
    """A named pool of crawler accounts (2026-11-05).

    The name was previously free text on ``CrawlerAccount``, so a group only
    existed while some account happened to carry that string and the admin UI
    had to type it. It is a real row now: groups can be created before any
    account uses them, and the UI can offer a dropdown.
    """

    name = models.CharField(max_length=100, unique=True)
    note = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "crawler_account_group"
        ordering = ["name"]

    def __str__(self):
        return self.name


class CrawlerAccount(models.Model):
    """Metadata for one authorized crawler account and its stored session.

    Only the encrypted Joybuy session blob is persisted. Facebook passwords
    are never collected, accepted or stored; see
    ``crawler_control.services.record_account_session``.
    """

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        PAUSED_RISK_CONTROL = "PAUSED_RISK_CONTROL", "Paused by risk control"
        DISABLED = "DISABLED", "Disabled"

    class SessionStatus(models.TextChoices):
        UNKNOWN = "UNKNOWN", "Unknown"
        VALID = "VALID", "Valid"
        EXPIRED = "EXPIRED", "Expired"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    label = models.CharField(max_length=120)
    account_group = models.CharField(max_length=100, default="default")
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.ACTIVE)
    session_status = models.CharField(
        max_length=16,
        choices=SessionStatus.choices,
        default=SessionStatus.UNKNOWN,
    )
    session_cipher = models.TextField(blank=True, default="", editable=False)
    session_updated_at = models.DateTimeField(null=True, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    risk_flagged_at = models.DateTimeField(null=True, blank=True)
    risk_reason = models.CharField(max_length=500, blank=True, default="")
    rate_limit_per_minute = models.PositiveIntegerField(null=True, blank=True)
    concurrency_limit = models.PositiveSmallIntegerField(null=True, blank=True)
    note = models.CharField(max_length=500, blank=True, default="")
    # Soft delete: the row disappears from management screens and its stored
    # session is destroyed, but historical runs keep the account label.
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "crawler_account"
        indexes = [
            models.Index(
                fields=["account_group", "status", "session_status"],
                name="crawler_account_group_idx",
            ),
        ]

    def __str__(self):
        return f"{self.label} ({self.account_group})"

    @property
    def is_selectable(self) -> bool:
        """An account may only pick up new runs while active with a valid session."""

        return self.status == self.Status.ACTIVE and self.session_status == self.SessionStatus.VALID


class CrawlJob(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        READY = "READY", "Ready"
        RUNNING = "RUNNING", "Running"
        PAUSED = "PAUSED", "Paused"
        COMPLETED = "COMPLETED", "Completed"
        CANCELED = "CANCELED", "Canceled"
        FAILED = "FAILED", "Failed"

    class CategoryMode(models.TextChoices):
        CURRENT_ONLY = "CURRENT_ONLY", "Current category only"
        INCLUDE_SUBCATEGORIES = "INCLUDE_SUBCATEGORIES", "Include subcategories"

    class ListingSort(models.TextChoices):
        SOURCE_DEFAULT = "SOURCE_DEFAULT", "Source default"
        BEST_SELLING = "BEST_SELLING", "Best selling"
        TOP_RATED = "TOP_RATED", "Top rated"
        NEWEST = "NEWEST", "Newest"
        RANDOM = "RANDOM", "Random"

    class SyncMode(models.TextChoices):
        INCREMENTAL = "INCREMENTAL", "Incremental sync"
        FULL_REFRESH = "FULL_REFRESH", "Full refresh"

    class FailureStrategy(models.TextChoices):
        PAUSE = "PAUSE", "Pause the job"
        CONTINUE = "CONTINUE", "Continue on failure"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=200)
    priority = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    market = models.ForeignKey("offers.Market", on_delete=models.PROTECT, related_name="crawl_jobs")
    currency = models.ForeignKey(
        "offers.Currency",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="crawl_jobs",
    )
    locale = models.CharField(max_length=16, default="en-GB")
    source_catalog = models.ForeignKey(
        "catalog.SourceCatalog",
        on_delete=models.PROTECT,
        related_name="crawl_jobs",
    )
    source_category = models.ForeignKey(
        "catalog.SourceCategory",
        on_delete=models.PROTECT,
        related_name="crawl_jobs",
    )
    # Optional snapshot binding; resolved and frozen onto each run.
    source_tree_version = models.ForeignKey(
        "catalog.SourceCategoryTreeVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crawl_jobs",
    )
    category_mode = models.CharField(
        max_length=24,
        choices=CategoryMode.choices,
        default=CategoryMode.INCLUDE_SUBCATEGORIES,
    )
    product_limit = models.PositiveIntegerField()
    listing_sort = models.CharField(
        max_length=24,
        choices=ListingSort.choices,
        default=ListingSort.SOURCE_DEFAULT,
    )
    # Persisted when listing_sort is RANDOM so repeat tasks are reproducible.
    random_seed = models.BigIntegerField(null=True, blank=True)
    sync_mode = models.CharField(
        max_length=16,
        choices=SyncMode.choices,
        default=SyncMode.INCREMENTAL,
    )
    review_target = models.PositiveSmallIntegerField(default=50)
    download_product_media = models.BooleanField(default=True)
    download_review_media = models.BooleanField(default=True)
    download_detail_media = models.BooleanField(default=False)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    concurrency = models.PositiveSmallIntegerField(default=1)
    rate_limit_per_minute = models.PositiveIntegerField(null=True, blank=True)
    account_group = models.CharField(max_length=100, default="default")
    # 指定账号（2026-11-05）：为空时按 account_group 自动挑「最近最少使用」的
    # 可用账号；有值时优先用这个账号。建任务时可选，避免所有任务都只会落到
    # default 组。
    account = models.ForeignKey(
        "CrawlerAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pinned_crawl_jobs",
    )
    failure_strategy = models.CharField(
        max_length=16,
        choices=FailureStrategy.choices,
        default=FailureStrategy.PAUSE,
    )
    allow_manual_resume = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "accounts_staff.StaffAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_crawl_jobs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "crawl_job"
        indexes = [
            models.Index(fields=["status", "priority", "scheduled_at"], name="job_queue_idx"),
            models.Index(fields=["source_catalog", "status"], name="job_catalog_status_idx"),
        ]

    def __str__(self):
        return f"{self.name} [{self.status}]"


class CrawlJobSourceSelection(models.Model):
    """One selected source category of a multi-category crawl job.

    Created when the job is saved: the tree version is frozen so later tree
    syncs never change what an existing job crawls. The legacy single
    ``CrawlJob.source_category`` field stays for jobs created before
    multi-category selection existed.
    """

    job = models.ForeignKey(CrawlJob, on_delete=models.CASCADE, related_name="source_selections")
    source_category = models.ForeignKey(
        "catalog.SourceCategory",
        on_delete=models.PROTECT,
        related_name="job_selections",
    )
    source_tree_version = models.ForeignKey(
        "catalog.SourceCategoryTreeVersion",
        on_delete=models.PROTECT,
        related_name="job_source_selections",
    )
    include_descendants = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "crawl_job_source_selection"
        constraints = [
            models.UniqueConstraint(
                fields=["job", "source_category"],
                name="crawl_job_source_selection_unique",
            )
        ]
        ordering = ["sort_order", "pk"]

    def __str__(self):
        return f"{self.job_id}:{self.source_category_id} descendants={self.include_descendants}"


class CrawlRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RUNNING = "RUNNING", "Running"
        PAUSED = "PAUSED", "Paused"
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        FAILED = "FAILED", "Failed"
        CANCELED = "CANCELED", "Canceled"

    class PauseReason(models.TextChoices):
        NONE = "NONE", "Not paused"
        MANUAL = "MANUAL", "Manual pause"
        RISK_CONTROL = "RISK_CONTROL", "Risk control"
        FAILURE_POLICY = "FAILURE_POLICY", "Failure policy"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    job = models.ForeignKey(CrawlJob, on_delete=models.PROTECT, related_name="runs")
    # The account pinned at start; a run is never taken over by another account.
    account = models.ForeignKey(
        CrawlerAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crawl_runs",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    pause_reason = models.CharField(
        max_length=24,
        choices=PauseReason.choices,
        default=PauseReason.NONE,
    )
    params_snapshot = models.JSONField(default=dict)
    discovered_count = models.PositiveIntegerField(default=0)
    downloaded_count = models.PositiveIntegerField(default=0)
    succeeded_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "crawl_run"
        indexes = [
            models.Index(fields=["job", "created_at"], name="run_job_created_idx"),
            models.Index(fields=["status", "updated_at"], name="run_status_updated_idx"),
            models.Index(fields=["account", "status"], name="run_account_status_idx"),
        ]

    def __str__(self):
        return f"Run {self.public_id} [{self.status}]"


class RawResponse(models.Model):
    """Index row for one archived raw HTTP response.

    Payload files are gzip-compressed under the raw storage root
    (``{yyyy}/{mm}/{dd}/{run public id}/{sha256}.gz``); this table keeps the
    relative path, hash and retention bookkeeping. After expiry the file is
    deleted but the row, hash and job link are kept for traceability.
    """

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    job = models.ForeignKey(CrawlJob, on_delete=models.CASCADE, related_name="raw_responses")
    run = models.ForeignKey(
        CrawlRun,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="raw_responses",
    )
    url = models.URLField(max_length=2000)
    status_code = models.PositiveIntegerField()
    content_type = models.CharField(max_length=100, blank=True, default="")
    response_hash = models.CharField(max_length=64)
    byte_size = models.PositiveBigIntegerField(default=0)
    relative_path = models.CharField(max_length=255, unique=True, editable=False)
    crawled_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    file_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "raw_response"
        indexes = [
            models.Index(fields=["job", "crawled_at"], name="raw_job_crawled_idx"),
            models.Index(fields=["run", "crawled_at"], name="raw_run_crawled_idx"),
            models.Index(fields=["expires_at", "file_deleted"], name="raw_expiry_idx"),
            models.Index(fields=["response_hash"], name="raw_hash_idx"),
        ]

    def __str__(self):
        return f"{self.url[:60]} -> {self.relative_path}"


class StagingProduct(models.Model):
    """Parsed product payload waiting for controlled import.

    Crawlers never write business tables directly: parse output lands here
    first, and ``crawler_control.import_services`` performs the idempotent
    import into catalog/offers through the domain services.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending import"
        IMPORTED = "IMPORTED", "Imported"
        REJECTED = "REJECTED", "Rejected"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    run = models.ForeignKey(
        CrawlRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staging_products",
    )
    source_system = models.CharField(max_length=50)
    source_id = models.CharField(max_length=160)
    source_url = models.URLField(max_length=1000, blank=True, default="")
    payload = models.JSONField(default=dict)
    parser_version = models.CharField(max_length=32, blank=True, default="")
    structure_version = models.PositiveIntegerField(default=1)
    missing_fields = models.JSONField(default=list)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    error_message = models.CharField(max_length=500, blank=True, default="")
    imported_refs = models.JSONField(default=dict, blank=True)
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    imported_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "staging_product"
        constraints = [
            models.UniqueConstraint(
                fields=["source_system", "source_id"],
                name="staging_product_identity_unique",
            )
        ]
        indexes = [
            models.Index(fields=["status", "last_seen_at"], name="staging_status_seen_idx"),
        ]

    def __str__(self):
        return f"Staging {self.source_system}:{self.source_id} [{self.status}]"


class QualityGateReport(models.Model):
    """Outcome of one quality-gate evaluation for a crawl run batch.

    A FAILED report freezes the batch: staging rows stay pending, the job
    pauses per its failure policy, and existing data is never overwritten.
    """

    class Status(models.TextChoices):
        PASSED = "PASSED", "Passed"
        FAILED = "FAILED", "Failed"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    run = models.ForeignKey(CrawlRun, on_delete=models.CASCADE, related_name="quality_reports")
    page_type = models.CharField(max_length=32)
    structure_version = models.PositiveIntegerField(default=1)
    checked_count = models.PositiveIntegerField(default=0)
    field_missing_rates = models.JSONField(default=dict)
    thresholds = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices)
    failure_detail = models.CharField(max_length=500, blank=True, default="")
    paused_job = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "quality_gate_report"
        indexes = [
            models.Index(fields=["run", "page_type"], name="quality_run_page_idx"),
            models.Index(fields=["status", "created_at"], name="quality_status_created_idx"),
        ]

    def __str__(self):
        return f"Quality {self.page_type} [{self.status}] run={self.run_id}"


class CrawlerCircuitBreaker(models.Model):
    """Global circuit breaker across all crawler accounts.

    Trips when several distinct accounts hit risk control within one
    window; while tripped, no job can start a run and only
    ``reset_circuit_breaker`` (after human review) clears it.
    """

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    is_tripped = models.BooleanField(default=False)
    tripped_at = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=500, blank=True, default="")
    window_minutes = models.PositiveIntegerField(default=30)
    account_threshold = models.PositiveSmallIntegerField(default=2)
    reset_at = models.DateTimeField(null=True, blank=True)
    reset_reason = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "crawler_circuit_breaker"

    def __str__(self):
        return f"CircuitBreaker tripped={self.is_tripped}"


class CrawlRunEvent(models.Model):
    """One progress/diagnostic event emitted by the live run executor.

    Per-item successes, parse failures, risk-control downgrades and the
    final outcome all land here so the admin UI can show what happened
    without reading logs.
    """

    class Level(models.TextChoices):
        INFO = "INFO", "Info"
        WARNING = "WARNING", "Warning"
        ERROR = "ERROR", "Error"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    run = models.ForeignKey(CrawlRun, on_delete=models.CASCADE, related_name="events")
    level = models.CharField(max_length=16, choices=Level.choices, default=Level.INFO)
    code = models.CharField(max_length=64, blank=True, default="")
    message = models.CharField(max_length=1000)
    source_url = models.URLField(max_length=2000, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "crawl_run_event"
        indexes = [
            models.Index(fields=["run", "created_at"], name="run_event_run_created_idx"),
            models.Index(fields=["level", "created_at"], name="run_event_level_idx"),
        ]

    def __str__(self):
        return f"[{self.level}] {self.code or 'EVENT'}: {self.message[:60]}"
