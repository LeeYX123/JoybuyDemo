import re
import uuid

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import F, Q


def normalize_brand_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


class SourceCatalog(models.Model):
    source_system = models.CharField(max_length=50, unique=True)
    display_name = models.CharField(max_length=120)
    current_version = models.ForeignKey(
        "SourceCategoryTreeVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_for_catalogs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "source_catalog"
        ordering = ["source_system"]


class SourceCategory(models.Model):
    catalog = models.ForeignKey(
        SourceCatalog,
        on_delete=models.CASCADE,
        related_name="categories",
    )
    source_id = models.CharField(max_length=160)
    # 中文名按 source_id 持久保存：重新同步英文树版本时直接继承，
    # 不必为拿到中文名再跑一遍中文抓取（管理端选择器同时展示中英文）。
    name_zh = models.CharField(max_length=200, blank=True, default="")
    is_active = models.BooleanField(default=True)
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "source_category"
        constraints = [
            models.UniqueConstraint(
                fields=["catalog", "source_id"],
                name="source_category_identity_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=["catalog", "is_active", "source_id"],
                name="source_category_active_idx",
            )
        ]


class SourceCategoryTreeVersion(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"
        FAILED = "FAILED", "Failed"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    catalog = models.ForeignKey(
        SourceCatalog,
        on_delete=models.CASCADE,
        related_name="tree_versions",
    )
    version_key = models.CharField(max_length=100)
    structure_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    captured_at = models.DateTimeField()
    published_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "source_category_tree_version"
        constraints = [
            models.UniqueConstraint(
                fields=["catalog", "version_key"],
                name="source_category_version_unique",
            )
        ]
        ordering = ["-captured_at", "-pk"]


class SourceCategorySnapshot(models.Model):
    tree_version = models.ForeignKey(
        SourceCategoryTreeVersion,
        on_delete=models.CASCADE,
        related_name="snapshots",
    )
    category = models.ForeignKey(
        SourceCategory,
        on_delete=models.PROTECT,
        related_name="snapshots",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
    )
    name = models.CharField(max_length=200)
    # 中文名来自 joybuy.co.uk 站点切到 中文(简体) 后的类目菜单，按 source_id 对齐英文名。
    name_zh = models.CharField(max_length=200, blank=True, default="")
    source_url = models.URLField(max_length=1000, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    depth = models.PositiveSmallIntegerField(default=0)
    path = models.CharField(max_length=700, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "source_category_snapshot"
        constraints = [
            models.UniqueConstraint(
                fields=["tree_version", "category"],
                name="source_category_snapshot_unique",
            )
        ]
        ordering = ["path", "sort_order", "pk"]


class LocalCategory(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        HIDDEN = "HIDDEN", "Hidden"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
    )
    name = models.CharField(max_length=160)
    # Bilingual display names for the storefront locale switcher (docs/12
    # global convention); ``name`` stays the fallback when a locale is missing.
    name_en = models.CharField(max_length=160, blank=True, default="")
    name_zh = models.CharField(max_length=160, blank=True, default="")
    slug = models.SlugField(max_length=120, unique=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    sort_order = models.PositiveIntegerField(default=0)
    depth = models.PositiveSmallIntegerField(default=0)
    path = models.CharField(max_length=700, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "local_category"
        ordering = ["path", "sort_order", "pk"]

    def display_name(self, locale: str) -> str:
        if locale == "zh" and self.name_zh:
            return self.name_zh
        if self.name_en:
            return self.name_en
        return self.name


class CategoryMapping(models.Model):
    local_category = models.ForeignKey(
        LocalCategory,
        on_delete=models.CASCADE,
        related_name="source_mappings",
    )
    source_category = models.ForeignKey(
        SourceCategory,
        on_delete=models.PROTECT,
        related_name="local_mappings",
    )
    is_primary = models.BooleanField(default=False)
    confidence = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "category_mapping"
        constraints = [
            models.UniqueConstraint(
                fields=["local_category", "source_category"],
                name="category_mapping_unique",
            )
        ]


class Brand(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=160)
    normalized_name = models.CharField(max_length=160, unique=True, editable=False)
    slug = models.SlugField(max_length=120, unique=True)
    website_url = models.URLField(max_length=1000, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "brand"
        ordering = ["normalized_name"]

    def save(self, *args, **kwargs):
        self.normalized_name = normalize_brand_name(self.name)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "name" in update_fields:
            kwargs["update_fields"] = set(update_fields) | {"normalized_name"}
        super().save(*args, **kwargs)


class AttributeDefinition(models.Model):
    class DataType(models.TextChoices):
        TEXT = "TEXT", "Text"
        INTEGER = "INTEGER", "Integer"
        DECIMAL = "DECIMAL", "Decimal"
        BOOLEAN = "BOOLEAN", "Boolean"
        CHOICE = "CHOICE", "Choice"
        MULTI_CHOICE = "MULTI_CHOICE", "Multiple choice"

    class Scope(models.TextChoices):
        SPU = "SPU", "SPU"
        SKU = "SKU", "SKU"
        BOTH = "BOTH", "SPU and SKU"

    code = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=160)
    data_type = models.CharField(max_length=24, choices=DataType.choices)
    scope = models.CharField(max_length=16, choices=Scope.choices, default=Scope.BOTH)
    unit = models.CharField(max_length=32, blank=True, default="")
    is_filterable = models.BooleanField(default=False)
    is_variant_axis = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "attribute_definition"
        ordering = ["code"]


class AttributeOption(models.Model):
    attribute = models.ForeignKey(
        AttributeDefinition,
        on_delete=models.CASCADE,
        related_name="options",
    )
    value = models.CharField(max_length=120)
    label = models.CharField(max_length=160)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "attribute_option"
        constraints = [
            models.UniqueConstraint(
                fields=["attribute", "value"],
                name="attribute_option_unique",
            )
        ]
        ordering = ["sort_order", "pk"]


class CategoryAttributeDefinition(models.Model):
    category = models.ForeignKey(
        LocalCategory,
        on_delete=models.CASCADE,
        related_name="attribute_assignments",
    )
    attribute = models.ForeignKey(
        AttributeDefinition,
        on_delete=models.PROTECT,
        related_name="category_assignments",
    )
    is_required = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "category_attribute_definition"
        constraints = [
            models.UniqueConstraint(
                fields=["category", "attribute"],
                name="category_attribute_unique",
            )
        ]
        ordering = ["sort_order", "pk"]


class Spu(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    brand = models.ForeignKey(
        Brand,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="spus",
    )
    local_category = models.ForeignKey(
        LocalCategory,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="spus",
    )
    model_number = models.CharField(max_length=120, blank=True, default="")
    gtin = models.CharField(max_length=14, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)

    # --- 商品池（平台管理后台 A03）字段 ---
    # 商品池是「平台可售商品主档」：成本价与零售价是平台建议值，
    # 商家上架时把成本价快照进 Offer，之后调价不影响已生成的订单。
    cost_price = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    retail_price = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    is_activity = models.BooleanField(default=False)
    description = models.TextField(blank=True, default="")
    # 商品池表单里的图片与规格是「平台手工录入值」，与爬虫导入的
    # media_asset / sku.specification 并存：前者用于后台编辑展示，
    # 后者是商城详情页的真实数据源。
    image_urls = models.JSONField(default=list, blank=True)
    specs = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "spu"
        constraints = [
            models.CheckConstraint(
                condition=Q(cost_price__isnull=True) | Q(cost_price__gte=0),
                name="spu_cost_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(retail_price__isnull=True)
                | Q(cost_price__isnull=True)
                | Q(retail_price__gte=F("cost_price")),
                name="spu_retail_not_below_cost",
            ),
        ]
        indexes = [
            models.Index(
                fields=["local_category", "status", "created_at"],
                name="spu_category_status_idx",
            ),
            models.Index(fields=["brand", "status"], name="spu_brand_status_idx"),
        ]


class SpuTranslation(models.Model):
    spu = models.ForeignKey(Spu, on_delete=models.CASCADE, related_name="translations")
    locale = models.CharField(max_length=16)
    title = models.CharField(max_length=500)
    subtitle = models.CharField(max_length=500, blank=True, default="")
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "spu_translation"
        constraints = [
            models.UniqueConstraint(
                fields=["spu", "locale"],
                name="spu_translation_locale_unique",
            )
        ]


class SpuSourceIdentity(models.Model):
    spu = models.ForeignKey(Spu, on_delete=models.PROTECT, related_name="source_identities")
    source_system = models.CharField(max_length=50)
    source_id = models.CharField(max_length=160)
    source_url = models.URLField(max_length=1000, blank=True, default="")
    source_category = models.ForeignKey(
        SourceCategory,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="spu_source_identities",
    )
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "spu_source_identity"
        constraints = [
            models.UniqueConstraint(
                fields=["source_system", "source_id"],
                name="spu_source_identity_unique",
            )
        ]
        indexes = [models.Index(fields=["spu", "source_system"], name="spu_source_lookup_idx")]


class Sku(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    spu = models.ForeignKey(Spu, on_delete=models.CASCADE, related_name="skus")
    specification = models.JSONField(default=dict)
    specification_signature = models.CharField(max_length=64)
    gtin = models.CharField(max_length=14, blank=True, default="")
    merchant_sku = models.CharField(max_length=120, blank=True, default="")
    weight_grams = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    length_mm = models.PositiveIntegerField(null=True, blank=True)
    width_mm = models.PositiveIntegerField(null=True, blank=True)
    height_mm = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sku"
        constraints = [
            models.UniqueConstraint(
                fields=["spu", "specification_signature"],
                name="sku_specification_unique",
            )
        ]
        indexes = [models.Index(fields=["spu", "status"], name="sku_spu_status_idx")]


class SkuSourceIdentity(models.Model):
    sku = models.ForeignKey(Sku, on_delete=models.PROTECT, related_name="source_identities")
    source_system = models.CharField(max_length=50)
    source_id = models.CharField(max_length=160)
    source_url = models.URLField(max_length=1000, blank=True, default="")
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sku_source_identity"
        constraints = [
            models.UniqueConstraint(
                fields=["source_system", "source_id"],
                name="sku_source_identity_unique",
            )
        ]
        indexes = [models.Index(fields=["sku", "source_system"], name="sku_source_lookup_idx")]


class SourceFieldValue(models.Model):
    """Latest known value of one overridable field as observed at the source.

    Crawlers only ever write here; approved local overrides live in
    ``LocalFieldOverride`` and always win when resolving effective values.
    """

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    target = GenericForeignKey("content_type", "object_id")
    field_code = models.CharField(max_length=100)
    value = models.JSONField(null=True)
    source_system = models.CharField(max_length=50)
    observed_at = models.DateTimeField()
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    is_missing = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "source_field_value"
        constraints = [
            models.UniqueConstraint(
                fields=["content_type", "object_id", "field_code"],
                name="source_field_value_unique",
            )
        ]
        indexes = [
            models.Index(fields=["source_system", "observed_at"], name="source_field_seen_idx")
        ]


class LocalFieldOverride(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CLEARED = "CLEARED", "Cleared"

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    target = GenericForeignKey("content_type", "object_id")
    field_code = models.CharField(max_length=100)
    value = models.JSONField(null=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    version = models.PositiveIntegerField(default=1)
    reason = models.CharField(max_length=500)
    proposed_by = models.ForeignKey(
        "accounts_staff.StaffAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="field_override_proposals",
    )
    reviewed_by = models.ForeignKey(
        "accounts_staff.StaffAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="field_override_reviews",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "local_field_override"
        constraints = [
            models.UniqueConstraint(
                fields=["content_type", "object_id", "field_code"],
                name="local_field_override_unique",
            )
        ]
        indexes = [
            models.Index(fields=["status", "updated_at"], name="override_status_updated_idx")
        ]


class LocalFieldOverrideVersion(models.Model):
    class ChangeKind(models.TextChoices):
        CREATE = "CREATE", "Created"
        UPDATE = "UPDATE", "Updated"
        REVIEW = "REVIEW", "Reviewed"
        CLEAR = "CLEAR", "Cleared"

    override = models.ForeignKey(
        LocalFieldOverride,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    version = models.PositiveIntegerField()
    value = models.JSONField(null=True)
    status = models.CharField(max_length=16, choices=LocalFieldOverride.Status.choices)
    change_kind = models.CharField(max_length=16, choices=ChangeKind.choices)
    reason = models.CharField(max_length=500)
    actor = models.ForeignKey(
        "accounts_staff.StaffAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="field_override_versions",
    )
    request_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "local_field_override_version"
        constraints = [
            models.UniqueConstraint(
                fields=["override", "version"],
                name="local_field_override_version_unique",
            )
        ]
        ordering = ["override", "version"]


class ProductSearchDocument(models.Model):
    """Flattened searchable row per (SPU, market).

    Rebuilt from SPU/SKU/Offer data by ``catalog.search_services``; the
    storefront search and category APIs read only this table so list queries
    stay simple and fully indexed. MySQL FULLTEXT powers text search.
    """

    spu = models.OneToOneField(Spu, on_delete=models.CASCADE, related_name="search_document")
    market = models.ForeignKey(
        "offers.Market", on_delete=models.PROTECT, related_name="search_documents"
    )
    title = models.CharField(max_length=500)
    brand_name = models.CharField(max_length=160, blank=True, default="")
    local_category = models.ForeignKey(
        LocalCategory,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="search_documents",
    )
    min_price = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    max_price = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    currency_code = models.CharField(max_length=3, blank=True, default="")
    rating_average = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    rating_count = models.PositiveIntegerField(default=0)
    is_searchable = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "product_search_document"
        indexes = [
            models.Index(
                fields=["market", "is_searchable", "local_category", "min_price"],
                name="psd_market_cat_price_idx",
            ),
            models.Index(fields=["market", "is_searchable", "published_at"], name="psd_newest_idx"),
            models.Index(
                fields=["market", "is_searchable", "rating_average"], name="psd_rating_idx"
            ),
        ]
