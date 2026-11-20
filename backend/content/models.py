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
        WEEKLY_PICKS = "weekly_picks", "Weekly picks"

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


class HomeBanner(models.Model):
    """商城首页顶部轮播图（平台管理后台 A10）。

    没有并进 ``CmsModule``：CMS 是**整页版本快照**（发布/回滚，模块位置固定），
    而轮播图是单条独立开关 + 排序 + 随时上下线的高频运营对象，两者生命周期
    不同；塞进版本化页面会让「改一张图」变成「发一个新版本」。
    """

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    title = models.CharField(max_length=40)
    description = models.CharField(max_length=100, blank=True, default="")
    image_url = models.CharField(max_length=1000, blank=True, default="")
    href = models.CharField(max_length=1000, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "home_banner"
        ordering = ["sort_order", "public_id"]
        indexes = [models.Index(fields=["enabled", "sort_order"], name="banner_enabled_sort_idx")]

    def __str__(self):
        return f"{self.title}@{self.sort_order}"


class HomeCampaignCard(models.Model):
    """商城首页「Offers for you」活动卡片（搜索框下方 10 宫格）。

    与 ``HomeBanner`` 同理：卡片是单条开关 + 排序的高频运营对象，不进
    CMS 版本快照。``storefront_home`` 输出时用本表（enabled）覆盖快照里
    写死的 ``campaign_grid`` 模块，快照保持只读历史。
    """

    class Section(models.TextChoices):
        CAMPAIGN = "campaign", "活动卡片"
        DISCOVERY = "discovery", "品类发现"
        WEEKLY = "weekly", "每周甄选"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    section = models.CharField(max_length=16, choices=Section.choices, default=Section.CAMPAIGN)
    title = models.CharField(max_length=60)
    title_zh = models.CharField(max_length=60, blank=True, default="")
    subtitle = models.CharField(max_length=120, blank=True, default="")
    subtitle_zh = models.CharField(max_length=120, blank=True, default="")
    image_url = models.CharField(max_length=1000, blank=True, default="")
    href = models.CharField(max_length=1000, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "home_campaign_card"
        ordering = ["section", "sort_order", "public_id"]
        indexes = [
            models.Index(fields=["section", "enabled", "sort_order"], name="card_section_sort_idx")
        ]

    def __str__(self):
        return f"{self.title}@{self.sort_order}"


class ChannelBanner(models.Model):
    """频道落地页（``/minihome/<code>``）顶部轮播图，按频道维度配置。

    与 ``HomeBanner`` 的区别：首页轮播图是「全站一张清单」，本表按
    ``channel_code`` 分组——每个 Joybuy minihome 频道（如
    ``UK-Mini-HP-Home-Living``）各有一组轮播图，购物端频道页只取本频道
    enabled 的条目。与 ``HomeBanner`` / ``HomeCampaignCard`` 同理，这是
    单条开关 + 排序 + 随时上下线的高频运营对象，**不进 CMS 版本快照**。
    """

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    # Joybuy minihome 代码（CategoryMapping 里 ``minihome:`` 前缀的来源类目）。
    channel_code = models.CharField(max_length=64)
    image_url = models.CharField(max_length=1000)
    href = models.CharField(max_length=1000, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "channel_banner"
        ordering = ["sort_order", "public_id"]
        indexes = [
            models.Index(
                fields=["channel_code", "enabled", "sort_order"],
                name="channel_banner_lookup_idx",
            )
        ]

    def __str__(self):
        return f"{self.channel_code}#{self.sort_order}"


class ChannelPageCard(models.Model):
    """频道页（``/minihome/<code>``）品类卡下方的活动卡片（13.2，2026-11-19）。

    与 ``ChannelBanner`` 同口径：按 ``channel_code`` 分组的高频运营对象，
    单条开关 + 排序，不进 CMS 版本快照。跳转链接 ``link_url`` 按 13.8
    链接规则**存原值不限制不改写**：以 ``http(s)://``、``//``、``www.``
    开头视为外链原样跳转，否则视为站内路径（判定在消费端 helper）。
    """

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    channel_code = models.CharField(max_length=64)
    image_url = models.CharField(max_length=1000)
    link_url = models.CharField(max_length=1000, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "channel_page_card"
        ordering = ["sort_order", "public_id"]
        indexes = [
            models.Index(
                fields=["channel_code", "is_active", "sort_order"],
                name="channel_page_card_idx",
            )
        ]

    def __str__(self):
        return f"{self.channel_code}#{self.sort_order}"


class ChannelModule(models.Model):
    """频道落地页（``/minihome/<code>``）的商品楼层（批次 H，2026-11-19）。

    真站频道页的运营楼层（如美妆【爆品热销】【新品上线】）按频道配置：
    每个楼层有中英文标题、排序、开关和有序商品清单（``ChannelModuleProduct``
    → ``catalog.Spu``）。商品来自真实抓取入库的 SPU；楼层只引用，不改商品。
    与 ``ChannelBanner`` 同口径：独立表、单条开关 + 排序，不进 CMS 版本快照。
    """

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    channel_code = models.CharField(max_length=64)
    title_en = models.CharField(max_length=120)
    title_zh = models.CharField(max_length=120, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "channel_module"
        ordering = ["channel_code", "sort_order", "public_id"]
        indexes = [
            models.Index(
                fields=["channel_code", "enabled", "sort_order"],
                name="channel_module_lookup_idx",
            )
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["channel_code", "sort_order"],
                name="channel_module_order_unique",
            )
        ]

    def __str__(self):
        return f"{self.channel_code}#{self.sort_order} {self.title_en}"


class ChannelModuleProduct(models.Model):
    """频道楼层内的商品顺序（唯一 SPU + 楼层内排序）。"""

    module = models.ForeignKey(ChannelModule, on_delete=models.CASCADE, related_name="items")
    spu = models.ForeignKey("catalog.Spu", on_delete=models.CASCADE, related_name="channel_items")
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "channel_module_product"
        ordering = ["module", "sort_order", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["module", "spu"], name="channel_module_product_unique"),
            models.UniqueConstraint(
                fields=["module", "sort_order"], name="channel_module_product_order_unique"
            ),
        ]

    def __str__(self):
        return f"{self.module_id}:{self.spu_id}@{self.sort_order}"
