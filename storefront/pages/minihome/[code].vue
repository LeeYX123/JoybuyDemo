<script setup>
// 频道落地页 /minihome/<code>（joybuy.co.uk/minihome/<pagecode> 同构）。
// Joybuy 频道页的模块顺序（2026-11-11 存档 SSR，14 频道一致）：
//   h1 频道名 → banner 轮播 → 二级品类卡片区（popular-category，链到二级
//   列表）→ 广告 banner → 1~2 个带标题的商品楼层 → 推荐楼层（CSR 拉取）。
// 本地 hero 优先用管理端按频道配置的 banner（本地 /media/ 图，不引外部
// CDN）；没有配置时回退渐变色块占位、不留空白。
// 推荐楼层是客户端拉取，SSR 里是空的，按「数据取不到的模块省略」省略。
// 2026-11-20 批次 I（需求文档03 13.1①②④ + 13.4）：二级品类卡按真站实测
// 规格（背景只包图、名称在背景外、行数/每行个数/名称宽度数据驱动）、楼层
// 商品卡去外框单行横滑、底部新增【精选好物】循环加载模块。
// 2026-11-23：活动卡片（ChannelPageCards）接入，按真站实测放在品类卡之后、
// 第一个商品楼层之前（宠物页例外，见 PETS_CHANNEL）；品类卡顺序可由
// utils/channelTileLists.js 的有序清单覆盖。
// 2026-11-23 第二批（截图对比 6 处硬差异）：活动卡片升级为「多组」契约
// （groups + items[].group_index，见 utils/channelCards.js）；楼层卡按后台
// 零售价 retail_price 展示（无折扣/划线价/Promo、无评分行）；【更多】改
// View More ›；品类卡 fill='row' 行距 32px；banner 圆角 0；h1 #1A1A1A；
// 楼层标题到卡顶 24.5px。
import { computed } from 'vue'
import { useHead, useRoute } from '#imports'

import { useCategoryTree } from '../../composables/useCategoryTree'
import { useChannelBanners } from '../../composables/useChannelBanners'
import { useChannelModules } from '../../composables/useChannelModules'
import { useChannelPageCards } from '../../composables/useChannelPageCards'
import { useLocale } from '../../composables/useLocale'
import { useSearch } from '../../composables/useSearchApi'
import { channelTileConfig, orderChannelTiles } from '../../utils/channelTiles'
import { channelTileList } from '../../utils/channelTileLists'

import AppContainer from '../../components/AppContainer.vue'
import CategoryTileCarousel from '../../components/CategoryTileCarousel.vue'
import ChannelHeroCarousel from '../../components/ChannelHeroCarousel.vue'
import ChannelPageCards from '../../components/ChannelPageCards.vue'
import ChannelPickedForYou from '../../components/ChannelPickedForYou.vue'
import CmsProductPool from '../../components/cms/CmsProductPool.vue'

const route = useRoute()
const { t, categoryName } = useLocale()

const code = computed(() => String(route.params.code || ''))

// The tile/product floors need the tree before they can build their search
// params (category=<L1 slug>), so the page awaits the tree once.
const { categories, treeData } = useCategoryTree()
await treeData

// 频道 code → 一级类目；对不上（无此频道/该一级没有频道 code）渲染降级态。
const channelRoot = computed(
  () => categories.value.find((category) => category.channel_code === code.value) || null,
)

// 13.1②：行数/每行个数/名称宽度按频道配置数据驱动（utils/channelTiles.js）。
const tileConfig = computed(() => channelTileConfig(channelRoot.value?.slug || ''))

// 宠物页是唯一把活动卡片放在「第一个商品楼层」之后的频道（真站实测
// var/channel_styles_20261123/measurement.md §B.3）。
const PETS_CHANNEL = 'UK-Mini-HP-Pets'
const cardsAfterFirstFloor = computed(() => code.value === PETS_CHANNEL)

// 管理端配置的本频道 banner（公开接口只返回 enabled）；空数组回退渐变占位。
const { banners } = useChannelBanners(code)
const heroBanners = computed(() => (banners.value || []).filter((item) => item?.image_url))

// 13.2 活动卡片（品类卡下方）：管理端按频道配置；空数组时整块不渲染。
// 2026-11-23 多组契约：groups 给组顺序与布局，items 给组内卡片。
const { items: pageCardItems, groups: pageCardGroups } = await useChannelPageCards(code)

// 真站精选清单里有跨一级的 L2（家居页挂了 diy-tools / fitness-training /
// outdoor-gear，电子页挂了 peripherals 等），所以不能只从本频道 children 里
// 取。用同一棵树的全部一级 children 建「slug → 节点」全局索引（不发新请求）。
const globalTileIndex = computed(() => {
  const index = new Map()
  for (const root of categories.value || []) {
    for (const child of root.children || []) {
      if (!index.has(child.slug)) index.set(child.slug, child)
    }
  }
  return index
})

// 本地树没有的清单项跳过（本轮不新建类目节点）；dev 下每个 slug 只 warn 一次。
const warnedMissingTiles = new Set()
function warnMissingTile(slug) {
  if (!import.meta.dev || warnedMissingTiles.has(slug)) return
  warnedMissingTiles.add(slug)
  console.warn(`[channel-tiles] no local category node for "${slug}"`)
}

// 品类卡顺序以 utils/channelTileLists.js 的精选清单为准（真站顺序，含跨一级
// 的 L2）；清单为 null 的频道保持后端树顺序。之后隐藏该频道页指定二级卡
// （13.1② 宠物页「其他动物用品」；分类下拉是后端树不受影响）。
const curatedTiles = computed(() =>
  channelTileList
    ? orderChannelTiles(
        channelTileList(channelRoot.value?.slug || ''),
        globalTileIndex.value,
        warnMissingTile,
      )
    : null,
)
const channelTiles = computed(() => {
  const hidden = tileConfig.value.hiddenTiles || []
  const base = curatedTiles.value || channelRoot.value?.children || []
  return hidden.length ? base.filter((child) => !hidden.includes(child.slug)) : base
})
// 截断口径（2026-11-24 缺陷修复）：有精选清单时清单长度就是展示数——清单是
// 真站该页的完整精选子集，maxVisible 只用于没有清单的降级路径（后端树可能很
// 长）。此前统一按 maxVisible=22 截断，把母婴页清单的第 23/24 张卡切掉了。
// 余量（降级路径）仍交给横滑与「查看全部品类」。
const tiles = computed(() =>
  curatedTiles.value
    ? channelTiles.value
    : channelTiles.value.slice(0, tileConfig.value.maxVisible),
)
const hiddenTileCount = computed(() => channelTiles.value.length - tiles.value.length)

// 商品楼层：useSearch 的 category= 支持「子树匹配」，传一级 slug 即该一级
// 全部子类商品。两个楼层 = 同类目两种排序（对齐 Joybuy 两个 product 楼层）。
// 未知名 code 用占位 slug 让搜索 404 成空集，避免拉全站商品。
const FALLBACK_CATEGORY = 'unknown-channel'
const hotParams = computed(() => ({
  category: channelRoot.value?.slug || FALLBACK_CATEGORY,
  page: 1,
}))
const newestParams = computed(() => ({
  category: channelRoot.value?.slug || FALLBACK_CATEGORY,
  page: 1,
  sort: 'newest',
}))

const { data: hotData } = await useSearch(hotParams)
const { data: newestData } = await useSearch(newestParams)

const hotProducts = computed(() => (hotData.value?.items || []).slice(0, 10))
const newestProducts = computed(() => (newestData.value?.items || []).slice(0, 10))

const resultsHref = computed(() =>
  channelRoot.value ? `/s?category=${channelRoot.value.slug}` : '/s',
)
// 真站该频道特有的运营楼层（如美妆【爆品热销】【新品上线】），由批次 H 的
// 楼层配置提供；【更多】落该一级的品类列表页 /c/<slug>。没有配置时回退下面
// 两个通用楼层（按热度/上新），保证任何频道都不空白。
const { modules } = useChannelModules(code)
const modulePools = computed(() =>
  (modules.value || [])
    .filter((module) => (module.products || []).length > 0)
    .map((module) => ({
      title: module.title,
      href: module.href,
      products: module.products,
      // 真站楼层【更多】文案「View More ›」（频道页专用 i18n key，
      // 不动 cms.viewAll 以免影响首页楼层）。
      more_label: t('channel.viewMore'),
      more_arrow: true,
      // 13.1④：楼层卡去外框 + 单行横滑（真站 6 张/行，measurement.md §2）。
      single_row: true,
      flat: true,
      row_columns: 6,
      // 2026-11-23 用户拍板：楼层卡按后台零售价展示、不显示折扣/划线价/Promo；
      // 真站楼层卡没有评分行（首页/搜索页卡片不受影响）。
      use_retail_price: true,
      hide_rating: true,
    })),
)

const hotPool = computed(() => ({
  title: t('channel.hotPicks'),
  href: resultsHref.value,
  products: hotProducts.value,
  more_label: t('channel.viewMore'),
  more_arrow: true,
  single_row: true,
  flat: true,
  row_columns: 6,
  use_retail_price: true,
  hide_rating: true,
}))
const newestPool = computed(() => ({
  title: t('channel.newArrivals'),
  products: newestProducts.value,
  more_label: t('channel.viewMore'),
  more_arrow: true,
  single_row: true,
  flat: true,
  row_columns: 6,
  use_retail_price: true,
  hide_rating: true,
}))

useHead(() => ({
  title: channelRoot.value ? categoryName(channelRoot.value) : t('channel.notFound'),
}))
</script>

<template>
  <div class="channel-page-bg">
    <AppContainer>
      <!-- 降级：code 对不上任何一级频道（含无频道 code 的一级被直链进来）。 -->
      <section v-if="!channelRoot" class="channel-unavailable" role="status">
        <p>{{ t('channel.notFound') }}</p>
        <NuxtLink class="channel-unavailable__home" to="/">{{ t('channel.backHome') }}</NuxtLink>
      </section>

      <template v-else>
        <!-- 频道头：一级类目名（Joybuy 频道页 h1 同位）。 -->
        <h1 class="channel-title">{{ categoryName(channelRoot) }}</h1>

        <!-- Banner 位：管理端配置的轮播；未配置时回退渐变占位。 -->
        <ChannelHeroCarousel :items="heroBanners" :fallback-title="categoryName(channelRoot)" />

        <!-- 二级品类卡片区（popular-category 同位）：13.1①② 真站规格，
             行数/名称宽度按频道配置；健康保健卡区上方有【分类导航】标题。 -->
        <section class="channel-tiles">
          <h2 v-if="tileConfig.showTitle" class="channel-tiles__title">
            {{ t('channel.categoriesNav') }}
          </h2>
          <CategoryTileCarousel
            class="channel-tiles__carousel"
            variant="channel"
            :items="tiles"
            :rows="tileConfig.rows"
            :per-row="tileConfig.perRow"
            :name-chars="tileConfig.nameChars"
            :fill="tileConfig.fill || 'column'"
          />
          <div v-if="hiddenTileCount > 0" class="channel-tiles__more">
            <NuxtLink class="channel-tiles__more-link" :to="resultsHref">
              {{ t('channel.viewAllCategories') }}
            </NuxtLink>
          </div>
        </section>

        <!-- 活动卡片（13.2）：除宠物页外，紧跟二级品类卡、在第一个商品楼层
             之前。接口按组返回，组件按 group_index 逐组渲染（组间 32px）；
             空数据时组件自己返回空，不留空缺。 -->
        <ChannelPageCards
          v-if="!cardsAfterFirstFloor"
          :items="pageCardItems"
          :groups="pageCardGroups"
        />

        <!-- 商品楼层（product floor 同位）：真站该频道特有楼层 + 【更多】，
             楼层卡去外框、单行横滑。没有配置时回退两个通用楼层，保证页面不
             空白。宠物页的活动卡片在第一个楼层之后、第二个楼层之前。 -->
        <template v-if="modulePools.length > 0">
          <template v-for="(pool, index) in modulePools" :key="`${index}-${pool.title}`">
            <CmsProductPool class="channel-pool channel-floor" :payload="pool" />
            <ChannelPageCards
              v-if="cardsAfterFirstFloor && index === 0"
              :items="pageCardItems"
              :groups="pageCardGroups"
            />
          </template>
        </template>
        <template v-else>
          <CmsProductPool
            v-if="hotProducts.length > 0"
            class="channel-pool channel-floor"
            :payload="hotPool"
          />
          <ChannelPageCards
            v-if="cardsAfterFirstFloor"
            :items="pageCardItems"
            :groups="pageCardGroups"
          />
          <CmsProductPool
            v-if="newestProducts.length > 0"
            class="channel-pool channel-floor"
            :payload="newestPool"
          />
        </template>

        <!-- 13.4【精选好物】：该品类商品随机混排，滚动自动一批 → 查看更多
             点击 → 池耗尽循环。16.4：底部按钮与首页【查看更多】同规格，
             文案为【更多 / More】。 -->
        <ChannelPickedForYou
          :key="channelRoot.slug"
          class="channel-pool channel-picked"
          :category-slug="channelRoot.slug"
          :more-label="t('channel.more')"
          :show-rating="false"
          :use-retail-price="true"
          :show-brand="false"
        />
      </template>
    </AppContainer>
  </div>
</template>

<style scoped>
/* 与结果页一致的全幅白底画布。 */
.channel-page-bg.channel-page-bg {
  /* 频道页内容区宽度按 joybuy.co.uk 频道页实测（2026-11-16，登录态渲染，
     1920/1680/1440/1280 视口均为 1264px 且居中）：这里只在频道页子树内
     覆盖 --container-max（AppContainer 读的就是它），全局 token 保持
     1608px（详情页实测值）不动，首页/详情页/结果页宽度不受影响。
     用 calc 是因为 --container-max 是含左右 padding 的盒宽。 */
  --container-max: calc(1264px + 2 * var(--container-pad));

  margin-block: 0;
  margin-inline: calc(50% - 50vw);
  background: #ffffff;
  /* 源站频道标题上间距 32px、末个楼层下留白 32px。 */
  padding-block: 2rem var(--space-8);
}

/* 频道标题：源站 h1 通栏居中、36px/700/54px，颜色 #1A1A1A（截图对比
   2026-11-23：真站 rgb(26,26,26)，我们此前用 --colour-text = #17202A）。 */
.channel-title {
  margin: 0;
  font-size: 2.25rem;
  line-height: 1.5;
  font-weight: var(--font-weight-bold);
  color: #1a1a1a;
  text-align: center;
}

/* Banner 位（1264×280、r=0、下方 32px）的样式在 ChannelHeroCarousel 里：
   组件同时负责「无图渐变占位 / 单图静态 / 多图轮播」三种形态。 */

.channel-tiles {
  /* 源站模块之间的纵向间距为 32px。 */
  margin-bottom: var(--space-8);
}

/* 13.1②：健康保健卡片区上方的【分类导航】标题（真站 28px/700，标题块与
   卡区间隔 24px，measurement.md §1）。 */
.channel-tiles__title {
  margin: 0 0 var(--space-6);
  font-size: 1.75rem;
  line-height: 1.75rem;
  font-weight: var(--font-weight-bold);
  color: var(--colour-text);
}

.channel-tiles__more {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--space-3);
}

.channel-tiles__more-link {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  color: var(--colour-accent);
  font-weight: var(--font-weight-semibold);
  text-decoration: none;
}

.channel-tiles__more-link:hover {
  text-decoration: underline;
}

.channel-pool {
  margin-bottom: var(--space-8);
}

/* 商品楼层 / 精选好物对齐真站实测（measurement.md §C，2026-11-23）：
   标题 28/700/36/#1A1A1A，标题底到卡顶 24.5px；【更多】16/400/37/#000；
   卡片 194 白底无边框（row_columns: 6 + gap 20 由 CmsProductPool 提供）；
   图片块白底 contain；价格 18/700/24，颜色一律 #1A1A1A（后台零售价口径，
   不按折扣判红）。

   2026-11-24 作用域收紧：楼层容器单独挂 .channel-floor，楼层专属结构
   （.cms-pool__*）只作用于它；卡片皮肤规则用显式选择器列表同时命中
   .channel-floor 与 .channel-picked。这样精选好物不再因为共用 .channel-pool
   类而「被动继承半套样式」，而是要写进列表才生效。精选好物的评分/品牌/
   价格口径由 ChannelPickedForYou 传 ProductCard props 控制。 */
.channel-floor :deep(.cms-pool__head) {
  /* 标题条高 37px（标题 36 + 1）→ 标题底到卡顶 = head 内多出的 1px + 23.5px
     = 24.5px。head 必须与标题同高：默认的 44px【更多】触控高度会多撑 9px，
     真站该链接高 37px，这里显式压到 37。 */
  align-items: flex-start;
  margin-bottom: 23.5px;
}

.channel-floor :deep(.cms-pool__more) {
  font-size: 16px;
  font-weight: 400;
  line-height: 37px;
  min-height: 37px;
  color: #000;
}

.channel-floor :deep(.cms-pool__title) {
  margin: 0;
  font-size: 1.75rem;
  line-height: 36px;
  font-weight: 700;
  color: #1a1a1a;
}

.channel-floor :deep(.cms-pool__scroller) {
  margin-top: 0;
}

.channel-floor :deep(.product-card__media),
.channel-picked :deep(.product-card__media) {
  background: #fff;
}

.channel-floor :deep(.product-card__media img),
.channel-picked :deep(.product-card__media img) {
  object-fit: contain;
}

.channel-floor :deep(.product-card__title),
.channel-picked :deep(.product-card__title) {
  font-size: 16px;
  font-weight: 500;
  line-height: 22px;
  color: #1a1a1a;
}

/* 2026-11-24 卡片高度对齐真站结构：真站楼层卡只有「图 194 → 文本区
   padding 12/6/0/6 → 标题 44 → 价格+加购行 40」，没有品牌行、没有行间
   gap、没有底部 padding。我们多出的留白正是这几段，频道页内统一收敛：
   - 品牌行（HomeLiving 首张卡实测 21px + gap 4px = 25px）真站没有 → 隐藏；
   - 文本区 padding 由 8/6/6 改为真站 12/6/0（上 +4、下 −6）；
   - flex gap 4 → 0、footer padding-top 8 → 0（标题到价格行 −12）。
   合计 328.98 − 25 + 4 − 6 − 4 − 8 = 289.98，与真站 310 − 20（真站该卡
   有 20px 划线原价行、我们按用户要求不显示）同结构。首页/搜索卡不受影响。
   楼层品牌行走下面的 CSS 隐藏（楼层 payload 来自后端，没有品牌 prop）；精选
   好物按用户口径「与楼层卡同款」，品牌/评分/价格口径改由 props 控制，因此
   品牌规则只留 .channel-floor。 */
.channel-floor :deep(.product-card__brand) {
  display: none;
}

.channel-floor :deep(.product-card__body),
.channel-picked :deep(.product-card__body) {
  gap: 0;
  padding: 12px 6px 0;
}

.channel-floor :deep(.product-card__footer),
.channel-picked :deep(.product-card__footer) {
  padding-top: 0;
}

/* 频道楼层价格一律 #1A1A1A（2026-11-23 用户拍板：直接用后台零售价展示，
   不乘折扣、不判红）。因此这里不再覆盖 .product-card__price--discount。 */
.channel-floor :deep(.product-card__price),
.channel-picked :deep(.product-card__price) {
  font-size: 18px;
  font-weight: 700;
  line-height: 24px;
  color: #1a1a1a;
}

.channel-floor :deep(.product-card__price-original) {
  font-size: 14px;
  font-weight: 500;
  line-height: 20px;
  color: #1a1a1a;
  text-decoration: line-through;
}

/* 精选好物标题与楼层标题同规格（真站复用同一 section 标题）。 */
.channel-picked :deep(.picked-for-you__title) {
  font-size: 1.75rem;
  line-height: 36px;
  font-weight: 700;
  color: #1a1a1a;
}

.channel-unavailable {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding-block: var(--space-8);
  text-align: center;
  color: var(--colour-text-secondary);
}

.channel-unavailable__home {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  color: var(--colour-accent);
  font-weight: var(--font-weight-semibold);
  text-decoration: none;
}

.channel-unavailable__home:hover {
  text-decoration: underline;
}
</style>
