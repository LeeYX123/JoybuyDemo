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
import { computed } from 'vue'
import { useHead, useRoute } from '#imports'

import { useCategoryTree } from '../../composables/useCategoryTree'
import { useChannelBanners } from '../../composables/useChannelBanners'
import { useChannelModules } from '../../composables/useChannelModules'
import { useLocale } from '../../composables/useLocale'
import { useSearch } from '../../composables/useSearchApi'
import { channelTileConfig } from '../../utils/channelTiles'

import AppContainer from '../../components/AppContainer.vue'
import CategoryTileCarousel from '../../components/CategoryTileCarousel.vue'
import ChannelHeroCarousel from '../../components/ChannelHeroCarousel.vue'
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

// 管理端配置的本频道 banner（公开接口只返回 enabled）；空数组回退渐变占位。
const { banners } = useChannelBanners(code)
const heroBanners = computed(() => (banners.value || []).filter((item) => item?.image_url))

// 13.1②：隐藏该频道页指定二级卡（宠物页「其他动物用品」；分类下拉是后端
// 树不受影响），再截到 maxVisible，余量交给横滑与「查看全部品类」。
const tiles = computed(() => {
  const children = channelRoot.value?.children || []
  const hidden = tileConfig.value.hiddenTiles || []
  const filtered = hidden.length
    ? children.filter((child) => !hidden.includes(child.slug))
    : children
  return filtered.slice(0, tileConfig.value.maxVisible)
})
const hiddenTileCount = computed(() => {
  const children = channelRoot.value?.children || []
  const hidden = tileConfig.value.hiddenTiles || []
  const visibleTotal = hidden.length
    ? children.filter((child) => !hidden.includes(child.slug)).length
    : children.length
  return visibleTotal - tiles.value.length
})

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
      more_label: t('channel.more'),
      // 13.1④：楼层卡去外框 + 单行横滑（真站 6 张/行，measurement.md §2）。
      single_row: true,
      flat: true,
      row_columns: 6,
    })),
)

const hotPool = computed(() => ({
  title: t('channel.hotPicks'),
  href: resultsHref.value,
  products: hotProducts.value,
  single_row: true,
  flat: true,
  row_columns: 6,
}))
const newestPool = computed(() => ({
  title: t('channel.newArrivals'),
  products: newestProducts.value,
  single_row: true,
  flat: true,
  row_columns: 6,
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
            :name-chars="tileConfig.nameChars"
          />
          <div v-if="hiddenTileCount > 0" class="channel-tiles__more">
            <NuxtLink class="channel-tiles__more-link" :to="resultsHref">
              {{ t('channel.viewAllCategories') }}
            </NuxtLink>
          </div>
        </section>

        <!-- 商品楼层（product floor 同位）：真站该频道特有楼层 + 【更多】，
             楼层卡去外框、单行横滑。没有配置时回退两个通用楼层，保证页面不
             空白。 -->
        <template v-if="modulePools.length > 0">
          <CmsProductPool
            v-for="(pool, index) in modulePools"
            :key="`${index}-${pool.title}`"
            class="channel-pool"
            :payload="pool"
          />
        </template>
        <template v-else>
          <CmsProductPool v-if="hotProducts.length > 0" class="channel-pool" :payload="hotPool" />
          <CmsProductPool
            v-if="newestProducts.length > 0"
            class="channel-pool"
            :payload="newestPool"
          />
        </template>

        <!-- 13.4【精选好物】：该品类商品随机混排，滚动自动一批 → 查看更多
             点击 → 池耗尽循环。16.4：底部按钮与首页【查看更多】同规格，
             文案为【更多 / More】。 -->
        <ChannelPickedForYou
          :key="channelRoot.slug"
          class="channel-pool"
          :category-slug="channelRoot.slug"
          :more-label="t('channel.more')"
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

/* 频道标题：源站 h1 通栏居中、36px/700/54px，与 banner 之间无间距。 */
.channel-title {
  margin: 0;
  font-size: 2.25rem;
  line-height: 1.5;
  font-weight: var(--font-weight-bold);
  color: var(--colour-text);
  text-align: center;
}

/* Banner 位（1264×280、r=8、下方 32px）的样式在 ChannelHeroCarousel 里：
   组件同时负责「无图渐变占位 / 单图静态 / 多图轮播」三种形态。 */

.channel-tiles {
  /* 源站模块之间的纵向间距为 32px。 */
  margin-bottom: var(--space-8);
}

/* 13.1②：健康保健卡片区上方的【分类导航】标题（真站 28px/700，标题块与
   卡区间隔 24px，measurement.md §1）。 */
.channel-tiles__title {
  margin: 0 0 var(--space-5);
  font-size: 1.75rem;
  line-height: 1;
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

/* 真站频道楼层标题 28px/600，与首页 Bestsellers 楼层同口径；【更多】在标题行
   右端（CmsProductPool 的 head 已是 space-between，无需改布局）。 */
.channel-pool :deep(.cms-pool__title) {
  font-size: 1.75rem;
  line-height: 1.3;
  font-weight: var(--font-weight-semibold);
  color: var(--colour-text);
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
