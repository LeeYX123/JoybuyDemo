import uuid

from django.contrib.contenttypes.fields import GenericForeignKey
from django.db import models


class MediaAsset(models.Model):
    class Kind(models.TextChoices):
        PRODUCT = "PRODUCT", "Product"
        REVIEW = "REVIEW", "Review"
        CMS = "CMS", "CMS"
        MERCHANT = "MERCHANT", "Merchant"
        ICON = "ICON", "Icon"
        FONT = "FONT", "Font"
        # 爬虫画廊视频（2026-11-09）：与图片同库、同样内容寻址。
        VIDEO = "VIDEO", "Video"

    class DownloadStatus(models.TextChoices):
        PENDING = "PENDING", "Pending download"
        DOWNLOADED = "DOWNLOADED", "Downloaded"
        FAILED = "FAILED", "Failed"

    class ProcessStatus(models.TextChoices):
        PENDING = "PENDING", "Pending processing"
        PROCESSED = "PROCESSED", "Processed"
        FAILED = "FAILED", "Failed"
        SKIPPED = "SKIPPED", "Skipped"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    sha256 = models.CharField(max_length=64, unique=True, editable=False)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    relative_path = models.CharField(max_length=255, unique=True, editable=False)
    mime_type = models.CharField(max_length=100, blank=True, default="")
    extension = models.CharField(max_length=16, blank=True, default="")
    byte_size = models.PositiveBigIntegerField(default=0)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    source_url = models.URLField(max_length=1000, blank=True, default="")
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    download_status = models.CharField(
        max_length=16,
        choices=DownloadStatus.choices,
        default=DownloadStatus.PENDING,
    )
    process_status = models.CharField(
        max_length=16,
        choices=ProcessStatus.choices,
        default=ProcessStatus.PENDING,
    )
    error_message = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "media_asset"
        indexes = [
            models.Index(fields=["kind", "download_status"], name="media_kind_download_idx"),
            models.Index(fields=["kind", "process_status"], name="media_kind_process_idx"),
        ]

    def __str__(self):
        return f"{self.kind}:{self.sha256[:12]}"


class MediaVariant(models.Model):
    class Format(models.TextChoices):
        JPEG = "JPEG", "JPEG"
        WEBP = "WEBP", "WebP"
        AVIF = "AVIF", "AVIF"
        MP4 = "MP4", "MP4"
        HLS = "HLS", "HLS"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        READY = "READY", "Ready"
        FAILED = "FAILED", "Failed"

    asset = models.ForeignKey(MediaAsset, on_delete=models.CASCADE, related_name="variants")
    preset = models.CharField(max_length=32)
    format = models.CharField(max_length=8, choices=Format.choices)
    width = models.PositiveIntegerField(default=0)
    relative_path = models.CharField(max_length=255, unique=True, editable=False)
    byte_size = models.PositiveBigIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    error_message = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "media_variant"
        constraints = [
            models.UniqueConstraint(
                fields=["asset", "preset", "format"],
                name="media_variant_unique",
            )
        ]
        indexes = [models.Index(fields=["asset", "status"], name="variant_asset_status_idx")]

    def __str__(self):
        return f"{self.asset_id}:{self.preset}:{self.format}"


class MediaUsage(models.Model):
    """Links an asset to a business object with a display role.

    Example roles: ``gallery``, ``review_image``, ``cms_banner``. The actual
    media pipeline (WP-18) writes usages; admin and storefront read them.
    """

    asset = models.ForeignKey(MediaAsset, on_delete=models.PROTECT, related_name="usages")
    content_type = models.ForeignKey(
        "contenttypes.ContentType",
        on_delete=models.CASCADE,
    )
    object_id = models.PositiveBigIntegerField()
    target = GenericForeignKey("content_type", "object_id")
    role = models.CharField(max_length=50)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "media_usage"
        constraints = [
            models.UniqueConstraint(
                fields=["asset", "content_type", "object_id", "role"],
                name="media_usage_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=["content_type", "object_id", "role"],
                name="usage_target_role_idx",
            )
        ]
