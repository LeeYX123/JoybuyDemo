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


# 本地类目树一级类目（depth=0）↔ 商家端固定品类（Spu.MerchantCategory）的对应关系。
# 商品池编辑表单用它把「商家端品类（父）」和「子品类」关联起来：先选父品类，
# 再只展示该父类目下的二级类目；二级类目本身不需要单独维护映射。
LOCAL_PARENT_MERCHANT_CATEGORY = {
    "home-living": "HOME",
    "electronics": "ELECTRONICS",
    "beauty-personal-care": "BEAUTY",
    "small-home-appliances": "SMALL_APPLIANCE",
    "health-wellness": "HEALTH",
    "computers-accessories": "COMPUTER",
    "clothing-accessories": "APPAREL",
    "outdoor-sports": "OUTDOOR",
    "pet-supplies": "PET",
    "baby-toddler": "BABY",
    "games-accessories": "GAMES",
}


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


class LocalCategoryTranslation(models.Model):
    category = models.ForeignKey(
        LocalCategory,
        on_delete=models.CASCADE,
        related_name="translations",
    )
    locale = models.ForeignKey(
        "offers.Locale",
        on_delete=models.PROTECT,
        related_name="category_translations",
    )
    name = models.CharField(max_length=160)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "local_category_translation"
        constraints = [
            models.UniqueConstraint(
                fields=["category", "locale"],
                name="local_category_translation_unique",
            )
        ]


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


class ProductCategory(models.Model):
    """Joybuy 商品后台类目（最多两级，如 厨具餐具/锅具）。

    与 ``SourceCategory``（首页频道菜单树）是两套 ID 空间：这里的
    ``source_id`` 是商品面包屑里的数字类目 ID（如 288/361/372）。
    按 2026-11-09 口径只保留前两级，第三级及更深在解析阶段丢弃。
    """

    catalog = models.ForeignKey(
        SourceCatalog,
        on_delete=models.CASCADE,
        related_name="product_categories",
    )
    source_id = models.CharField(max_length=64)
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
    )
    # 先存中文（页面 Cookie 为 zh_CN）；英文名后续再补翻译。
    name = models.CharField(max_length=200)
    depth = models.PositiveSmallIntegerField(default=0)
    path = models.CharField(max_length=700, db_index=True)
    # 商品类目 ↔ 本地类目的映射留空位，本轮不自动填。
    local_category = models.ForeignKey(
        LocalCategory,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="product_categories",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "product_category"
        ordering = ["path"]
        constraints = [
            models.UniqueConstraint(
                fields=["catalog", "source_id"],
                name="product_category_identity_unique",
            ),
            models.CheckConstraint(
                check=Q(depth__lte=1),
                name="product_category_depth_max_1",
            ),
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


class AttributeDefinitionTranslation(models.Model):
    attribute = models.ForeignKey(
        AttributeDefinition,
        on_delete=models.CASCADE,
        related_name="translations",
    )
    locale = models.ForeignKey(
        "offers.Locale",
        on_delete=models.PROTECT,
        related_name="attribute_translations",
    )
    name = models.CharField(max_length=160)
    unit = models.CharField(max_length=32, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "attribute_definition_translation"
        constraints = [
            models.UniqueConstraint(
                fields=["attribute", "locale"],
                name="attribute_definition_translation_unique",
            )
        ]


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


class AttributeOptionTranslation(models.Model):
    option = models.ForeignKey(
        AttributeOption,
        on_delete=models.CASCADE,
        related_name="translations",
    )
    locale = models.ForeignKey(
        "offers.Locale",
        on_delete=models.PROTECT,
        related_name="attribute_option_translations",
    )
    label = models.CharField(max_length=160)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "attribute_option_translation"
        constraints = [
            models.UniqueConstraint(
                fields=["option", "locale"],
                name="attribute_option_translation_unique",
            )
        ]


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

    class MerchantCategory(models.TextChoices):
        """商家端 12 个固定品类（WP-42，文档 M03 §3）。

        「活动商品」不是品类：它是 is_activity 标记，不改变原品类，
        在商家端以独立的【活动商品】筛选呈现。
        """

        HOME = "HOME", "家居生活"
        ELECTRONICS = "ELECTRONICS", "电子产品"
        BEAUTY = "BEAUTY", "美妆个人护理"
        SMALL_APPLIANCE = "SMALL_APPLIANCE", "小家电"
        HEALTH = "HEALTH", "健康与保健"
        COMPUTER = "COMPUTER", "计算机与配件"
        APPAREL = "APPAREL", "服装与配饰"
        OUTDOOR = "OUTDOOR", "户外运动"
        PET = "PET", "宠物用品"
        BABY = "BABY", "婴幼儿用品"
        GAMES = "GAMES", "游戏及配件"

    @classmethod
    def merchant_category_label(cls, value: str) -> str:
        return cls.MerchantCategory(value).label if value else "未分类"

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
    # 商品自身的 Joybuy 类目（最多两级，如 厨具餐具/锅具），与 local_category 并存。
    product_category = models.ForeignKey(
        ProductCategory,
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
    # 商家端 12 固定品类（空 = 未分类）；与商城 local_category 是两套维度。
    merchant_category = models.CharField(
        max_length=24,
        choices=MerchantCategory.choices,
        blank=True,
        default="",
        db_index=True,
    )
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


class SpuDetail(models.Model):
    """爬虫解析的结构化详情（2026-11-09）。

    与 ``Spu.description``（本地化纯文本、历史兜底）并存：这里按 Joybuy
    页面原结构保存图文区块、规格表格、规格可选值与 AI 摘要，购物端据此
    渲染子标题 / 两列表格 / 视频等。历史商品没有该行，API 返回空结构，
    页面回退到 ``description``，不会报错。
    """

    class ContentSource(models.TextChoices):
        """``content_sections`` 的来源（2026-11-10）。

        crawler = 爬虫抓取（默认）；manual = 平台管理端人工编辑。人工编辑
        后爬虫重导入只刷新其它字段（规格表格 / spec_options / AI / 视频），
        不再覆盖 ``content_sections``，见 docs/14 §9.9。
        """

        CRAWLER = "crawler", "爬虫抓取"
        MANUAL = "manual", "人工编辑"

    spu = models.OneToOneField(Spu, on_delete=models.CASCADE, related_name="detail")
    #: [{title, blocks: [{type: "heading"|"paragraph", text}], text, images}]
    #: ``images`` 已替换为本地 ``/media/...`` URL。
    content_sections = models.JSONField(default=list, blank=True)
    #: ``content_sections`` 的来源：crawler=爬虫抓取（默认），manual=管理端
    #: 人工编辑；manual 时导入器不再覆盖 ``content_sections``。
    content_source = models.CharField(
        max_length=16,
        choices=ContentSource.choices,
        default=ContentSource.CRAWLER,
        blank=True,
    )
    #: [{title, columns: ["属性", "值"], rows: [{name, value}]}]
    specification_tables = models.JSONField(default=list, blank=True)
    #: 平铺规格参数 [{group, name, value}]，保留兼容。
    specifications = models.JSONField(default=list, blank=True)
    #: [{name, values: [{value, image_url, sku_ids}]}]
    spec_options = models.JSONField(default=list, blank=True)
    ai_summary = models.TextField(blank=True, default="")
    ai_summary_title = models.CharField(max_length=200, blank=True, default="")
    ai_summary_tags = models.JSONField(default=list, blank=True)
    #: 源站评价汇总（2026-11-10）：爬虫商品没有本地评价行，购物端评分/评价数
    #: 用这里的快照；本地有 ACTIVE 评价时以本地统计为准。
    rating_average = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    rating_count = models.PositiveIntegerField(default=0)
    #: 星级分布 {"5": n, ...}，原样保存源站口径。
    rating_distribution = models.JSONField(default=dict, blank=True)
    #: 销量展示值（2026-11-19）：源站 productCommentSaleFloor.saleAmount，如
    #: "10k+"。展示字符串原样保存，非精确数字。
    sale_amount = models.CharField(max_length=32, blank=True, default="")
    #: 评价数展示值：同 floor 的 commentCount（如 "80+"），与精确的
    #: rating_count 并存（源站展示口径）。
    comment_count_display = models.CharField(max_length=32, blank=True, default="")
    #: 最近一次从源站刷新这些字段的时间。
    source_observed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "spu_detail"


class SpuDetailTranslation(models.Model):
    """``spu_detail_translation`` 只读镜像（2026-11-17）。

    表由 translation_agent（SQLAlchemy，``translation_agent/agent/db.py``）
    创建并写入，每个 SPU 每个 ``language_code``（de/fr/nl）一行；购物端详情
    接口在请求语言命中时用它替换 ``SpuDetail`` 的图文详情 / 规格参数表 /
    spec_options / AI 摘要。Django 侧只读：

    - ``managed=False`` 且**不建 Django 迁移**（表已存在于 dev MySQL）；
    - 测试库 / 未初始化环境没有该表时，查询方（``catalog/detail_views.py``）
      必须防御 ``OperationalError`` 回退源数据；
    - ``specification_*`` 三列可空：NULL 与 [] 等价，都表示「还没构建」。
    """

    id = models.BigAutoField(primary_key=True)
    spu_id = models.BigIntegerField()
    language_code = models.CharField(max_length=8)
    content_sections = models.JSONField(default=list)
    ai_summary = models.TextField(default="")
    ai_summary_title = models.CharField(max_length=200, default="")
    source_locale = models.CharField(max_length=16)
    source_hash = models.CharField(max_length=64)
    origin = models.CharField(max_length=16)
    specification_tables = models.JSONField(null=True, blank=True)
    specifications = models.JSONField(null=True, blank=True)
    spec_options = models.JSONField(null=True, blank=True)
    quality_flags = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        db_table = "spu_detail_translation"
        managed = False


class SpuVideo(models.Model):
    """商品画廊视频（2026-11-09）。

    视频字节走媒体库（``MediaAsset`` kind=VIDEO，内容寻址、本地
    ``/media/...``），数据库只存关联与元数据；海报沿用图片资产。
    """

    spu = models.ForeignKey(Spu, on_delete=models.CASCADE, related_name="videos")
    video = models.ForeignKey(
        "media.MediaAsset",
        on_delete=models.PROTECT,
        related_name="spu_video_links",
    )
    poster = models.ForeignKey(
        "media.MediaAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="spu_video_posters",
    )
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    source_video_id = models.CharField(max_length=160, blank=True, default="")
    source_url = models.URLField(max_length=1000, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "spu_video"
        ordering = ["spu", "sort_order", "pk"]
        indexes = [models.Index(fields=["spu", "sort_order"], name="spu_video_order_idx")]


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


class SpuMarketContent(models.Model):
    class Origin(models.TextChoices):
        SOURCE = "SOURCE", "Source"
        HUMAN = "HUMAN", "Human translation"
        MACHINE = "MACHINE", "Machine translation"

    class Status(models.TextChoices):
        CURRENT = "CURRENT", "Current"
        STALE = "STALE", "Stale"
        FAILED = "FAILED", "Failed"

    spu = models.ForeignKey(Spu, on_delete=models.CASCADE, related_name="market_contents")
    market = models.ForeignKey(
        "offers.Market",
        on_delete=models.PROTECT,
        related_name="product_contents",
    )
    locale = models.ForeignKey(
        "offers.Locale",
        on_delete=models.PROTECT,
        related_name="product_contents",
    )
    title = models.CharField(max_length=500)
    subtitle = models.CharField(max_length=500, blank=True, default="")
    description = models.TextField(blank=True, default="")
    actual_locales = models.JSONField(default=dict, blank=True)
    origin = models.CharField(max_length=16, choices=Origin.choices, default=Origin.SOURCE)
    source_content_hash = models.CharField(max_length=64, blank=True, default="")
    observed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.CURRENT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "spu_market_content"
        constraints = [
            models.UniqueConstraint(
                fields=["spu", "market", "locale"],
                name="spu_market_content_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=["market", "locale", "status"],
                name="spu_market_locale_status_idx",
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
    #: 同款多规格合并标记（2026-11-27 批次 CB2）。
    #: True 表示该 SKU 的 ``specification`` 是「同款合并」工具按标题差异派生
    #: 写入的（Size/Colour/Pack/Style），源站页面本身没有规格解析结果。
    #: 爬虫重导该变体页时会保留本地规格，而不是按「旧非空 → 新空」判为身份
    #: 冲突（见 ``crawler_control.import_services._adopt_enriched_specification``）。
    #: 只有合并工具会置位，普通导入/人工编辑保持 False。
    specification_merge_managed = models.BooleanField(default=False)
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


class SkuSpecificationTranslation(models.Model):
    class Method(models.TextChoices):
        DIRECT = "DIRECT", "Direct translation"
        HUMAN = "HUMAN", "Human reviewed"
        SOURCE = "SOURCE", "Source supplied"

    sku = models.ForeignKey(
        Sku,
        on_delete=models.CASCADE,
        related_name="specification_translations",
    )
    locale = models.ForeignKey(
        "offers.Locale",
        on_delete=models.PROTECT,
        related_name="sku_specification_translations",
    )
    specification = models.JSONField(default=dict)
    source_locale = models.CharField(max_length=16, blank=True, default="en-GB")
    method = models.CharField(max_length=16, choices=Method.choices, default=Method.DIRECT)
    untranslated_terms = models.JSONField(default=list, blank=True)
    needs_review = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sku_specification_translation"
        constraints = [
            models.UniqueConstraint(
                fields=["sku", "locale"],
                name="sku_specification_translation_unique",
            )
        ]
        indexes = [
            models.Index(fields=["locale", "needs_review"], name="sku_spec_locale_review_idx")
        ]


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
    """Flattened searchable row per (SPU, market, locale).

    Rebuilt from SPU/SKU/Offer data by ``catalog.search_services``; the
    storefront search and category APIs read only this table so list queries
    stay simple and fully indexed. MySQL FULLTEXT powers text search.
    """

    spu = models.ForeignKey(Spu, on_delete=models.CASCADE, related_name="search_documents")
    market = models.ForeignKey(
        "offers.Market", on_delete=models.PROTECT, related_name="search_documents"
    )
    locale_code = models.CharField(max_length=16, default="en-GB")
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
    #: 批次 DB（2026-11-27）：同款族键。空串 = 该 SPU 不属于任何族（独立商品）。
    family_key = models.CharField(max_length=160, blank=True, default="")
    #: 是否族代表（列表/搜索只出代表卡）。回填前默认 True，保证行为与旧版一致。
    is_family_representative = models.BooleanField(default=True)
    #: 族内最高价（各成员当前价取最大），卡片价格显示用；空则回退 ``min_price``。
    family_max_price = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "product_search_document"
        constraints = [
            models.UniqueConstraint(
                fields=["spu", "market", "locale_code"],
                name="product_search_document_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=["market", "locale_code", "is_searchable", "local_category", "min_price"],
                name="psd_market_locale_cat_idx",
            ),
            models.Index(
                fields=["market", "locale_code", "is_searchable", "published_at"],
                name="psd_market_locale_new_idx",
            ),
            models.Index(
                fields=["market", "locale_code", "is_searchable", "rating_average"],
                name="psd_market_locale_rate_idx",
            ),
            models.Index(fields=["family_key"], name="psd_family_key_idx"),
        ]


class SpuAlias(models.Model):
    """旧商品 URL 别名（2026-11-27 批次 CB2 同款多规格合并）。

    合并不物理删除 SPU：被合并的 SPU 归档（``status=INACTIVE``）并把它的
    ``public_id`` 写进本表，指向保留 SPU。购物端 ``/p/<old_public_id>`` 命中
    别名时 301 到 ``/p/<keep_public_id>``，后端详情接口也回退到保留 SPU，
    保证历史订单「查看商品」、外部分享链接、搜索引擎收录都不 404。
    """

    #: 被合并（归档）SPU 的 public_id；全局唯一 —— 一个旧链接只能指向一个保留商品。
    old_public_id = models.UUIDField(unique=True)
    spu = models.ForeignKey(Spu, on_delete=models.CASCADE, related_name="aliases")
    #: 审计用：哪个批次/组产生了这条别名（如 ``CB2/A/A-0002``）。
    reason = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "spu_alias"
        indexes = [models.Index(fields=["spu"], name="spu_alias_spu_idx")]


class SpuVariantArchive(models.Model):
    """同款合并后的「变体档案」（2026-11-27 批次 DA）。

    批次 CB2 把同款多规格合并成 1 个保留 SPU + 多 SKU，但成员 SPU 的画廊
    ``MediaUsage`` 已改挂保留 SPU 并按 asset 去重、SKU/身份也改挂保留 SPU，
    库里没有「SKU → 合并前来源 SPU」的持久映射。本表从
    ``var/variant_merge_20261126/backup_merge.json`` 一次性回填：

    - ``spu``/``sku``：合并后保留 SPU 与它名下的 SKU（唯一键）；
    - ``source_spu_public_id``：该 SKU 合并前所属的 SPU（保留 SPU 自己的 SKU
      等于 ``spu`` 本身）；归档 SPU 的 ``SpuDetail``/译文仍可读，供详情块切换；
    - ``gallery_manifest``：来源 SPU 合并前的画廊 asset 相对路径（按原
      ``sort_order``），因为归属只在备份里；缺图时前端回退保留 SPU 的画廊；
    - ``rating_snapshot``/``sold_snapshot``：来源 SPU 的评分/已售快照，避免
      依赖运行期 join；``detail_spu`` 指向归档 SPU，图文详情从它实时读；
    - ``share_metadata``：是否「只共享元数据」（纯尺码/数量变体）。True =
      切规格只换价格/库存/规格；False = 整套切换（画廊/评分/已售/详情/标题）。
      判定不确定时一律 True（保守，不换数据），原因写在 ``share_metadata_reason``。

    注意：``detail_spu`` 用 ``SET_NULL``，归档 SPU 若被物理清理，详情块回退
    保留 SPU 的内容（快照仍在，不会 500）。
    """

    #: 合并后的保留 SPU。
    spu = models.ForeignKey(Spu, on_delete=models.CASCADE, related_name="variant_archives")
    #: 该档案对应的 SKU（必属于 ``spu``；DB 层由唯一键保证一对一）。
    sku = models.ForeignKey(Sku, on_delete=models.CASCADE, related_name="variant_archives")
    #: 合并前该 SKU 所属 SPU 的 public_id（保留 SPU 自己的 SKU 等于 ``spu``）。
    source_spu_public_id = models.UUIDField()
    #: 派生轴值，如 "300g"/"X Max S"；来自合并后的 ``sku.specification``。
    axis_label = models.CharField(max_length=120, blank=True, default="")
    #: 来源 SPU 合并前的画廊图片相对路径列表（按原 sort_order）。
    gallery_manifest = models.JSONField(default=list, blank=True)
    #: 归档 SPU（图文详情来源）；保留 SPU 自己的 SKU 为 NULL（回退保留 SPU 详情）。
    detail_spu = models.ForeignKey(
        Spu,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="variant_archive_sources",
    )
    #: {average, count, distribution, source}
    rating_snapshot = models.JSONField(default=dict, blank=True)
    #: {sale_amount, comment_count_display}
    sold_snapshot = models.JSONField(default=dict, blank=True)
    #: 来源 SPU 的标题快照 {locale: title}（切规格时用于替换标题）。
    title_snapshots = models.JSONField(default=dict, blank=True)
    #: True = 纯尺码/数量变体，仅价格/库存/规格切换；False = 整套数据切换。
    share_metadata = models.BooleanField(default=True)
    #: 判定依据（审计用）：size_like / colour_word / axis_text / uncertain_default。
    share_metadata_reason = models.CharField(max_length=40, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "spu_variant_archive"
        constraints = [
            models.UniqueConstraint(
                fields=["spu", "sku"],
                name="spu_variant_archive_unique",
            )
        ]
        indexes = [
            models.Index(fields=["spu", "share_metadata"], name="variant_archive_spu_share_idx"),
            models.Index(fields=["detail_spu"], name="variant_archive_detail_idx"),
        ]


class VariantFamily(models.Model):
    """同款族（批次 DB，2026-11-27）：列表/搜索/商家页「一个商品只出一张卡」。

    全站商品都是自营，商家「上架」只是同一商品的不同 SKU Offer，所以同一件商品
    可能既有「源站同 slug 的多个 SPU」（批次 CB2 没合并掉的），也有「源站不同
    slug 但名称极像、只是型号不同」的多个 SPU（如 Hypershell X Max S / X Ultra S）。
    本表把这类 SPU 归到一个族，族内只保留一个「代表 SPU」出卡。

    ``family_key`` 形如 ``slug:<源站 slug>`` / ``title:<hash>`` /
    ``merged:<保留 SPU public_id>``；族计算规则在
    ``catalog/variant_family_services.py``（与 ``var/`` 下的预览脚本同源）。
    """

    class Kind(models.TextChoices):
        SLUG = "slug", "同源站 slug"
        TITLE = "title", "标题相似（型号差异）"
        MERGED = "merged", "已合并（1 SPU 多 SKU）"

    class Confidence(models.TextChoices):
        HIGH = "high", "High"
        MEDIUM = "medium", "Medium"
        LOW = "low", "Low"

    family_key = models.CharField(max_length=160, unique=True)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    #: 出卡的 SPU（列表/搜索只出这一张卡）。
    representative_spu = models.ForeignKey(
        Spu, on_delete=models.CASCADE, related_name="variant_families_represented"
    )
    confidence = models.CharField(
        max_length=8, choices=Confidence.choices, default=Confidence.HIGH
    )
    #: 派生轴名提示（Size/Colour/Style/Model/Style…），只做运营提示，不参与判定。
    axis_hint = models.CharField(max_length=64, blank=True, default="")
    #: 建族依据（审计用，如 ``same_slug`` / ``sim>=0.85&(img|brand|head)&price``）。
    evidence = models.CharField(max_length=240, blank=True, default="")
    #: 族内 SPU 数（去重后，冗余存一份便于后台列族）。
    member_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "variant_family"
        indexes = [
            models.Index(fields=["kind", "confidence"], name="variant_family_kind_conf_idx"),
            models.Index(fields=["representative_spu"], name="variant_family_rep_idx"),
        ]


class VariantFamilyMember(models.Model):
    """族成员：一条 = (族, SPU, SKU, 商家 offer)。

    跨商家族按 offer 维度展开（同一 SKU 不同商家各一条），``merchant_label``
    存商家展示名；``axis_label`` 是该 SKU 的规格展示串（如 ``Size: 140g``）。
    PDP 的「规格 × 商家」两级选择读这里 + 实时 ``Offer`` 表（价格/库存必须实时）。
    """

    family = models.ForeignKey(VariantFamily, on_delete=models.CASCADE, related_name="members")
    spu = models.ForeignKey(Spu, on_delete=models.CASCADE, related_name="variant_family_memberships")
    #: 规格维度；SPU 级成员（没有 SKU，理论上不会出现）为 NULL。
    sku = models.ForeignKey(
        Sku,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="variant_family_memberships",
    )
    #: 商家维度；Offer 被删/下架后置 NULL（成员结构仍在，PDP 回退到 SKU 级）。
    offer = models.ForeignKey(
        "offers.Offer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="variant_family_memberships",
    )
    axis_label = models.CharField(max_length=160, blank=True, default="")
    merchant_label = models.CharField(max_length=160, blank=True, default="")
    #: True = 该行属于代表 SPU（列表/搜索文档的 is_family_representative 与它一致）。
    is_representative = models.BooleanField(default=False)
    #: 展示顺序：代表 SPU 优先，其次按创建时间/pk。
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "variant_family_member"
        constraints = [
            models.UniqueConstraint(
                fields=["family", "spu", "sku", "offer"],
                name="variant_family_member_unique",
            )
        ]
        indexes = [
            models.Index(fields=["spu"], name="variant_member_spu_idx"),
            models.Index(fields=["family", "is_representative"], name="variant_member_family_rep_idx"),
            models.Index(fields=["sku"], name="variant_member_sku_idx"),
        ]
