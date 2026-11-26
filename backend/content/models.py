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

    2026-11-24 起支持「每频道多组」：真站频道页往往有多个 ``uk-pc-image-ads``
    模块（品牌卡 + 品类活动卡），只有其中一部分是品类活动卡。``group_index``
    标识同一频道内的第几组（从 0 开始，按真站模块出现顺序编号），组内再按
    ``sort_order`` 排序。

    ``layout`` 是**组级**展示布局（同一 ``(channel_code, group_index)`` 内所有
    卡片共用一个值，写入时由服务层只同步该组），不是单卡属性，也不是频道属性：

    - ``row2``：一行 2 张的大卡（620×200），2 张即一行
    - ``row3``：一行 3 张（多数频道）
    - ``row3_scroll``：一屏 3 张、共 6 张，可左右滑动（健康保健 / 宠物首组）
    - ``grid2x2``：历史值，仅为兼容旧数据保留在 choices 里，新代码不再产生
    """

    class Layout(models.TextChoices):
        ROW2 = "row2", "两列两行"
        ROW3 = "row3", "一行三张"
        ROW3_SCROLL = "row3_scroll", "一屏三张可滑动"
        GRID2X2 = "grid2x2", "两列两行（历史）"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    channel_code = models.CharField(max_length=64)
    # 同一频道内的组序号（0 起）；组内再按 sort_order 排序。
    group_index = models.PositiveIntegerField(default=0)
    image_url = models.CharField(max_length=1000)
    link_url = models.CharField(max_length=1000, blank=True, default="")
    # 2026-11-26（ADR-0002）：绑定的本地落地页。绑定时购物端跳转用
    # ``/active/<external_id>`` 或 ``/store/<external_id>``，``link_url`` 保留
    # 原值仅作溯源/兜底；未绑定时沿用 ``link_url``。页面删除（物理）时置空。
    activity_page = models.ForeignKey(
        "ActivityPage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="channel_cards",
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    layout = models.CharField(max_length=20, default="row3", choices=Layout.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "channel_page_card"
        ordering = ["group_index", "sort_order", "public_id"]
        indexes = [
            models.Index(
                fields=["channel_code", "is_active", "sort_order"],
                name="channel_page_card_idx",
            )
        ]

    def __str__(self):
        return f"{self.channel_code}#{self.group_index}.{self.sort_order}"


class ChannelCardSetting(models.Model):
    """频道级卡片展示配置（2026-11-26，ADR-0002）。

    ``max_cards``：购物端该频道最多展示的卡片数（默认 3）；``null`` 表示
    不截断（母婴童玩频道的豁免）。没有配置行的频道按默认 3 处理。
    """

    channel_code = models.CharField(max_length=64, unique=True)
    max_cards = models.PositiveIntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "channel_card_setting"

    def __str__(self):
        return f"{self.channel_code} max={self.max_cards if self.max_cards is not None else '∞'}"


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
    """频道楼层内的商品顺序（唯一 ``(spu, sku)`` + 楼层内排序）。

    2026-11-24 起按 **SKU 唯一**：同一 SPU 的不同尺码/颜色各占一张卡（真站
    母婴「Buy more save more」17 张卡只有 5 个 SPU）。``sku`` 为空表示该位次
    只有 SPU 粒度（老数据 / 源站解析不到本地 SKU 时的兜底），渲染与旧行为一致。

    唯一约束选用 ``(module, spu, sku)``：MySQL 与 SQLite 都把 NULL 视为互不
    相等，``sku IS NULL`` 的重复行不会撞约束，因此 SPU 级去重由应用层保证
    （同步命令按 ``(spu_id, sku_id)`` 保序去重；``(module, sort_order)`` 保证
    同层位次不重）。没有做数据迁移：老行的 ``sku`` 保持 NULL，仍按 SPU 渲染。
    """

    module = models.ForeignKey(ChannelModule, on_delete=models.CASCADE, related_name="items")
    spu = models.ForeignKey("catalog.Spu", on_delete=models.CASCADE, related_name="channel_items")
    sku = models.ForeignKey(
        "catalog.Sku",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="channel_items",
    )
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "channel_module_product"
        ordering = ["module", "sort_order", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["module", "spu", "sku"],
                name="channel_module_product_sku_unique",
            ),
            models.UniqueConstraint(
                fields=["module", "sort_order"], name="channel_module_product_order_unique"
            ),
        ]

    def __str__(self):
        identity = self.sku_id if self.sku_id is not None else "spu"
        return f"{self.module_id}:{self.spu_id}/{identity}@{self.sort_order}"


class ActivityPage(models.Model):
    """真站 ``/campaign/active/<id>`` 与 ``/store/<id>`` 落地页的本地复刻
    （2026-11-25，首页「为你推荐」10 模块配套）。

    本地 URL 保留真站 ID：``/active/<external_id>``、``/store/<external_id>``。
    页面结构固定为「hero banner + 若干分区」：分区要么是整幅图片模块
    （``ActivitySection.Kind.BANNER``），要么是商品楼层（标题 + 商品清单，
    ``ActivitySection.Kind.PRODUCTS``）。倒计时、优惠码等运营交互元素按用户
    2026-11-25 口径**一律不复刻**。

    与 ``ChannelPageCard`` 同口径：单条开关 + 排序的高频运营对象，不进 CMS
    版本快照；店铺页（kind=STORE）是一次性快照，配置定死后不做常规运营入口。
    """

    class Kind(models.TextChoices):
        ACTIVITY = "ACTIVITY", "活动页"
        STORE = "STORE", "店铺页"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    kind = models.CharField(
        max_length=16, choices=Kind.choices, default=Kind.ACTIVITY, db_index=True
    )
    #: 真站 URL 段：active 页是 base62 id，store 页是数字店铺 id。
    external_id = models.CharField(max_length=64)
    title = models.CharField(max_length=200)
    title_zh = models.CharField(max_length=200, blank=True, default="")
    #: 店铺页顶栏店铺名（活动页留空）。
    store_name = models.CharField(max_length=160, blank=True, default="")
    #: 店铺页顶部黑色条里的商家头像（2026-11-26）。
    logo_image = models.CharField(max_length=1000, blank=True, default="")
    source_url = models.CharField(max_length=500, blank=True, default="")
    #: 首屏整幅 banner 图（本地 /media/ 或 public 路径）。
    hero_image = models.CharField(max_length=1000, blank=True, default="")
    #: 页面底色（真站部分活动页有底色，如 #ffffff）。
    background_color = models.CharField(max_length=16, blank=True, default="")
    enabled = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "activity_page"
        ordering = ["sort_order", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "external_id"], name="activity_page_kind_external_unique"
            )
        ]
        indexes = [
            models.Index(
                fields=["kind", "enabled", "sort_order"], name="activity_page_lookup_idx"
            )
        ]

    def __str__(self):
        return f"{self.kind}:{self.external_id} {self.title}"


class ActivitySection(models.Model):
    """活动页/店铺页内的一个分区：整幅图片模块或商品楼层。

    ``columns`` 是商品楼层的列数（真站实测活动页 5 列、店铺页 5 列）；
    ``show_more`` 只在楼层下显示【View more】按钮（本地点击加载已采集的下一批，
    见 ``ActivitySectionProduct`` 的分批口径）。
    """

    class Kind(models.TextChoices):
        BANNER = "BANNER", "整幅图片"
        PRODUCTS = "PRODUCTS", "商品楼层"
        #: 自动轮播 banner（真站店铺页顶部，hover 出左右箭头）。
        CAROUSEL = "CAROUSEL", "轮播图"
        #: 视频模块（真站店铺页 banner 下方，静音自动循环）。
        VIDEO = "VIDEO", "视频"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    page = models.ForeignKey(ActivityPage, on_delete=models.CASCADE, related_name="sections")
    kind = models.CharField(
        max_length=16, choices=Kind.choices, default=Kind.PRODUCTS, db_index=True
    )
    title = models.CharField(max_length=200, blank=True, default="")
    title_zh = models.CharField(max_length=200, blank=True, default="")
    #: 楼层标题条配色（2026-11-26 实测真站）：真站标题统一是 flex_cube floorTitle
    #: 模块，配色按页面配置——白底页是砖红字，深色页是白字配深红/炭黑条。
    #: 空字符串表示「无底色」（纯文字标题）。
    # 32 位：允许 rgba(255,255,255,1) 这类写法（真站有的模块就是 rgba）。
    title_color = models.CharField(max_length=32, blank=True, default="")
    title_background = models.CharField(max_length=32, blank=True, default="")
    image_url = models.CharField(max_length=1000, blank=True, default="")
    href = models.CharField(max_length=1000, blank=True, default="")
    columns = models.PositiveSmallIntegerField(default=5)
    show_more = models.BooleanField(default=False)
    #: 轮播/视频模块的附加配置：
    #: CAROUSEL: {"images": ["/a.webp", ...]}
    #: VIDEO: {"video": "/videos/x.mp4", "poster": "/images/x.webp"}
    extra = models.JSONField(default=dict, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "activity_section"
        ordering = ["page", "sort_order", "pk"]

    def __str__(self):
        return f"{self.page_id}:{self.kind}@{self.sort_order} {self.title}"


class ActivitySectionProduct(models.Model):
    """商品楼层里的商品位次（按真站顺序）。

    首批展示 ``FIRST_BATCH = 15`` 个（真站一屏 5×3），点一次【View more】
    追加剩余（我们只采一屏 + 一次更多，见 HANDOFF 0ct）。
    """

    FIRST_BATCH = 15

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    section = models.ForeignKey(
        ActivitySection, on_delete=models.CASCADE, related_name="items"
    )
    spu = models.ForeignKey("catalog.Spu", on_delete=models.PROTECT, related_name="activity_items")
    #: 多规格商品的具体规格（2026-11-25）：真站同一 SPU 的不同尺寸/规格各占一卡
    #: （如 Novilla 床垫 King 与 Double 各一个链接）。为空表示按 SPU 展示。
    sku = models.ForeignKey(
        "catalog.Sku",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="activity_items",
    )
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "activity_section_product"
        ordering = ["section", "sort_order", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["section", "spu", "sku"], name="activity_section_product_unique"
            )
        ]

    def __str__(self):
        return f"{self.section_id}:{self.spu_id}@{self.sort_order}"
