import uuid

from django.db import models


class VirtualReviewer(models.Model):
    """Local display identity for a source reviewer.

    ``fingerprint = HMAC-SHA256(secret, source_system + stable_public_identifier)``;
    the reversible source identifier is never stored. Reviewers cannot log in
    and are never merged with real buyer accounts.
    """

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    source_system = models.CharField(max_length=50)
    fingerprint = models.CharField(max_length=64, unique=True, editable=False)
    display_name = models.CharField(max_length=120, blank=True, default="")
    avatar = models.ForeignKey(
        "media.MediaAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewer_avatars",
    )
    display_attributes = models.JSONField(default=dict, blank=True)
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "virtual_reviewer"
        constraints = [
            models.UniqueConstraint(
                fields=["source_system", "fingerprint"],
                name="virtual_reviewer_identity_unique",
            )
        ]
        indexes = [models.Index(fields=["source_system", "last_seen_at"], name="reviewer_seen_idx")]

    def __str__(self):
        return f"{self.source_system}:{self.fingerprint[:12]}"


class Review(models.Model):
    class Origin(models.TextChoices):
        SOURCE = "SOURCE", "Source review"
        LOCAL = "LOCAL", "Local review"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        DELETED = "DELETED", "Deleted at source"
        HIDDEN = "HIDDEN", "Hidden by platform"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    spu = models.ForeignKey("catalog.Spu", on_delete=models.PROTECT, related_name="reviews")
    origin = models.CharField(max_length=16, choices=Origin.choices, default=Origin.SOURCE)
    source_system = models.CharField(max_length=50)
    source_id = models.CharField(max_length=160)
    source_url = models.URLField(max_length=1000, blank=True, default="")
    reviewer = models.ForeignKey(
        VirtualReviewer,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reviews",
    )
    # Display snapshot for reviews without a stable source identity; such
    # reviews never get a reviewer row, so nicknames are never merged.
    guest_display_name = models.CharField(max_length=120, blank=True, default="")
    rating = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=300, blank=True, default="")
    body = models.TextField(blank=True, default="")
    locale = models.CharField(max_length=16, blank=True, default="")
    variant_text = models.CharField(max_length=300, blank=True, default="")
    likes_count = models.PositiveIntegerField(null=True, blank=True)
    source_reviewed_at = models.DateTimeField(null=True, blank=True)
    source_position = models.JSONField(default=dict, blank=True)
    content_hash = models.CharField(max_length=64, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "review"
        constraints = [
            models.UniqueConstraint(
                fields=["source_system", "source_id"],
                condition=models.Q(origin="SOURCE"),
                name="review_source_identity_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(rating__gte=1, rating__lte=5),
                name="review_rating_range",
            ),
        ]
        indexes = [
            models.Index(
                fields=["spu", "status", "source_reviewed_at"],
                name="review_spu_status_time_idx",
            ),
            models.Index(fields=["reviewer", "created_at"], name="review_reviewer_created_idx"),
        ]

    def __str__(self):
        return f"{self.origin}:{self.source_system}:{self.source_id}"


class ReviewVersion(models.Model):
    class ChangeKind(models.TextChoices):
        CREATED = "CREATED", "Created"
        UPDATED = "UPDATED", "Updated at source"
        DELETED = "DELETED", "Deleted at source"

    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="versions")
    content_hash = models.CharField(max_length=64)
    rating = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=300, blank=True, default="")
    body = models.TextField(blank=True, default="")
    variant_text = models.CharField(max_length=300, blank=True, default="")
    likes_count = models.PositiveIntegerField(null=True, blank=True)
    change_kind = models.CharField(max_length=16, choices=ChangeKind.choices)
    observed_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "review_version"
        ordering = ["review", "created_at", "pk"]
        indexes = [models.Index(fields=["review", "created_at"], name="review_version_time_idx")]


class ReviewMedia(models.Model):
    class MediaKind(models.TextChoices):
        IMAGE = "IMAGE", "Image"
        VIDEO = "VIDEO", "Video"

    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="media_items")
    asset = models.ForeignKey(
        "media.MediaAsset",
        on_delete=models.PROTECT,
        related_name="review_attachments",
    )
    media_kind = models.CharField(max_length=8, choices=MediaKind.choices)
    position = models.PositiveIntegerField(default=0)
    source_url = models.URLField(max_length=1000, blank=True, default="")
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "review_media"
        constraints = [
            models.UniqueConstraint(
                fields=["review", "asset"],
                name="review_media_unique",
            )
        ]
        ordering = ["review", "position", "pk"]
        indexes = [models.Index(fields=["review", "media_kind"], name="review_media_kind_idx")]
