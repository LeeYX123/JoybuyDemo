import uuid

from django.db import models


class CmsPage(models.Model):
    """A versioned CMS page (home first); modules render top to bottom."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"
        ARCHIVED = "ARCHIVED", "Archived"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    page_key = models.CharField(max_length=100)
    version = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cms_page"
        constraints = [
            models.UniqueConstraint(
                fields=["page_key", "version"],
                name="cms_page_version_unique",
            )
        ]
        indexes = [
            models.Index(fields=["page_key", "status", "version"], name="cms_page_status_idx"),
        ]

    def __str__(self):
        return f"{self.page_key} v{self.version} [{self.status}]"


class CmsModule(models.Model):
    """One floor/module of a page with a typed JSON payload.

    Payload schemas per ``module_type`` are documented in
    ``content/schemas.py``; renderers must treat unknown types and malformed
    payloads as degraded content, never as page-level errors.
    """

    class Type(models.TextChoices):
        HERO = "hero", "Hero banner"
        BANNER = "banner", "Promotional banner"
        PRODUCT_POOL = "product_pool", "Product pool"
        RICH_TEXT = "rich_text", "Rich text"
        LINK_GRID = "link_grid", "Link grid"
        CAMPAIGN_GRID = "campaign_grid", "Campaign grid"

    page = models.ForeignKey(CmsPage, on_delete=models.CASCADE, related_name="modules")
    module_type = models.CharField(max_length=32, choices=Type.choices)
    position = models.PositiveIntegerField()
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cms_module"
        constraints = [
            models.UniqueConstraint(
                fields=["page", "position"],
                name="cms_module_position_unique",
            )
        ]
        ordering = ["page", "position"]

    def __str__(self):
        return f"{self.module_type}@{self.position} of {self.page_id}"
