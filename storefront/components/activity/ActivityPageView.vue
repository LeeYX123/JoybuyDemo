<script setup>
// 活动页 / 店铺页（桌面版，2026-11-25）。
//
// 结构按真站实测（var/home_modules_20261125/measure 系列）：
//   内容区 1224px 居中；hero banner 满宽；楼层标题 26/700 居中（真站深红
//   #A81810）；商品网格 5 列、卡 225px、列间 24 / 行间 32；【View more】
//   一行一个按钮，点一次追加载入已采集的下一批（我们只采一屏 + 一次更多）。
//
// 口径：倒计时、优惠码/优惠券一律不复刻（用户 2026-11-25 拍板）；商品价格
// 用库内正常售价（与 PDP 一致）；店铺页不含【店铺】【商品】tab。
import { computed, reactive } from 'vue'

import { useLocale } from '../../composables/useLocale'

import ActivityCarousel from './ActivityCarousel.vue'
import ActivityProductCard from './ActivityProductCard.vue'
import ActivityVideo from './ActivityVideo.vue'

const props = defineProps({
  page: {
    type: Object,
    required: true,
  },
  kind: {
    type: String,
    default: 'activity',
  },
})

const { t, locale } = useLocale()

// 真站默认只露一行（5 列 × 1 行），剩余折叠在【View more】后面；
// 点一次按钮展开全部剩余（2026-11-26 用户口径：哪怕只剩 1 个也要按钮）。
const FIRST_BATCH = 5
const revealAll = reactive({})

const sections = computed(() => props.page?.sections || [])

function sectionTitle(section) {
  return locale.value === 'zh' && section.title_zh ? section.title_zh : section.title
}

function visibleProducts(section) {
  const items = section.products || []
  // 店铺页是一次性快照，直接展示全部商品（用户 2026-11-26 口径）。
  if (props.kind === 'store') return items
  return revealAll[section.public_id] ? items : items.slice(0, FIRST_BATCH)
}

// 标题条配色（2026-11-26 实测）：真站标题统一是 floorTitle 模块，配色按页面配置。
// 有底色 → 整条通栏（1224 宽、上下 16px 内边距）；无底色 → 纯文字砖红。
// 真站：带可见色条的楼层标题紧贴上方模块（295t/4ZXg/3Yu5 实测 gap=0）；
// 纯文字标题（白底页）与上方 banner 之间留 40px（24EG 实测）。
function isFlush(section, index) {
  if (!section.title_background) return false
  if (index === 0) return true
  const prev = sections.value[index - 1]
  return !!prev && (prev.kind === 'BANNER' || prev.kind === 'CAROUSEL')
}

function titleStyle(section) {
  const style = {}
  if (section.title_background) {
    style.background = section.title_background
    style.padding = '16px 0'
  }
  style.color = section.title_color || '#a33838'
  return style
}

function hasMore(section) {
  if (props.kind === 'store') return false
  return (section.products || []).length > FIRST_BATCH && !revealAll[section.public_id]
}

function reveal(section) {
  revealAll[section.public_id] = true
}

// .app-main > * 默认给上下 24px 外边距；活动页/店铺页要求 header 与 banner 无缝，
// 用行内样式压掉上边距（scoped CSS 与全局规则特异性相同，不可靠）。
const pageStyle = computed(() => ({
  marginBlockStart: '0px',
  ...(props.page?.background_color ? { background: props.page.background_color } : {}),
}))

const hero = computed(() => props.page?.hero_image || '')
const storeName = computed(() => props.page?.store_name || '')
const pageTitle = computed(() =>
  locale.value === 'zh' && props.page?.title_zh ? props.page.title_zh : props.page?.title,
)
</script>

<template>
  <div class="activity-page" :style="pageStyle">
    <!-- 店铺页顶部黑色信息条：通栏铺满视口宽度（真站 storeHeader），无 Store/Products tab。 -->
    <div v-if="kind === 'store' && storeName" class="activity-store-bar">
      <div class="activity-store-bar__inner">
        <img
          v-if="page.logo_image"
          class="activity-store-bar__logo"
          :src="page.logo_image"
          alt=""
        />
        <span class="activity-store-bar__name">{{ storeName }}</span>
      </div>
    </div>

    <div class="activity-page__inner">
      <img v-if="hero" class="activity-hero" :src="hero" :alt="pageTitle" />

      <section
        v-for="(section, index) in sections"
        :key="section.public_id"
        class="activity-section"
        :class="[
          `activity-section--${section.kind.toLowerCase()}`,
          { 'activity-section--flush': isFlush(section, index) },
          { 'activity-section--store-banner': props.kind === 'store' && section.kind === 'BANNER' },
        ]"
      >
        <template v-if="section.kind === 'BANNER'">
          <NuxtLink v-if="section.href" :to="section.href" class="activity-banner-link">
            <img class="activity-banner" :src="section.image_url" alt="" loading="lazy" />
          </NuxtLink>
          <img v-else class="activity-banner" :src="section.image_url" alt="" loading="lazy" />
        </template>

        <template v-else-if="section.kind === 'CAROUSEL'">
          <ActivityCarousel :images="section.extra?.images || []" />
        </template>

        <template v-else-if="section.kind === 'VIDEO'">
          <ActivityVideo
            v-if="section.extra?.video"
            :src="section.extra.video"
            :poster="section.extra.poster || ''"
          />
        </template>

        <template v-else>
          <h2
            v-if="sectionTitle(section)"
            class="activity-floor-title"
            :class="{ 'activity-floor-title--bar': !!section.title_background }"
            :style="titleStyle(section)"
          >
            {{ sectionTitle(section) }}
            <span v-if="section.extra?.subtitle" class="activity-floor-subtitle">
              {{ section.extra.subtitle }}
            </span>
          </h2>
          <ul class="activity-grid" :style="{ '--columns': section.columns || 5 }">
            <li v-for="product in visibleProducts(section)" :key="product.item_key || product.spu_public_id">
              <ActivityProductCard :product="product" />
            </li>
          </ul>
          <div v-if="section.show_more && hasMore(section)" class="activity-more">
            <button type="button" class="activity-more__btn" @click="reveal(section)">
              {{ t('activity.viewMore') }}
            </button>
          </div>
        </template>
      </section>
    </div>
  </div>
</template>

<style scoped>
.activity-page {
  /* 真站活动页内容区 1224px（babel 模块实测 width:1224px）。 */
  --activity-width: 1224px;
  background: #fff;
  padding-block: 0 var(--space-8);
}

.activity-page__inner {
  width: 100%;
  max-width: calc(var(--activity-width) + 2 * var(--container-pad));
  margin-inline: auto;
  padding-inline: var(--container-pad);
}

.activity-hero {
  display: block;
  width: 100%;
  height: auto;
  border-radius: 0;
}

/* 店铺页顶部黑条（真站 storeHeader：通栏、高 64、纯黑、头像 40 圆角、白字店名），
   与下方 banner 之间留 36px（真站实测）。 */
.activity-store-bar {
  width: 100%;
  margin-bottom: 36px;
  background: #000;
  color: #fff;
}

.activity-store-bar__inner {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 64px;
  max-width: calc(1224px + 2 * var(--container-pad));
  margin-inline: auto;
  padding-inline: var(--container-pad);
}

.activity-store-bar__logo {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  object-fit: cover;
  background: #fff;
}

.activity-store-bar__name {
  font-size: 16px;
  font-weight: 500;
  line-height: 1.4;
}

.activity-section--carousel {
  margin-top: 0;
}

.activity-section--products {
  margin-top: 40px;
}

/* 真站：带色条的楼层标题紧贴上方模块；banner 与紧随其后的模块之间也紧贴
   （7Uw 的 banner → TOP DEAL 图 → banner）。纯文字标题保持 40px。 */
.activity-section--flush,
.activity-section--banner + .activity-section,
.activity-section--carousel + .activity-section {
  margin-top: 0;
}

/* 店铺页底部的整幅图之间留 24px（真站实测有间隙）。
   选择器要压过 `.activity-section--banner + .activity-section`（0,2,0）。 */
.activity-section--banner.activity-section--store-banner {
  margin-top: 24px;
}

.activity-section--banner {
  margin-top: 24px;
}

.activity-banner,
.activity-banner-link img {
  display: block;
  width: 100%;
  height: auto;
  border-radius: 0;
}

/* 真站楼层标题（2026-11-26 实测）：28px/700、行高 35px、砖红 #A33838、
   居中；标题底部到卡片顶 45px。 */
.activity-floor-title {
  margin: 0 0 45px;
  font-size: 28px;
  font-weight: 700;
  line-height: 35px;
  color: #a33838;
  text-align: center;
}

/* 通栏标题条（真站 floorTitle）：上下 16px 内边距、条宽撑满 1224；
   条后接商品网格的间距比纯文字标题小。 */
/* 副标题（真站 3Yu5「Ready to play?」下方还有一行 Explore our picks）。 */
.activity-floor-subtitle {
  display: block;
  margin-top: 2px;
  font-size: 16px;
  font-weight: 400;
  line-height: 24px;
}

.activity-floor-title--bar {
  margin-bottom: 24px;
  /* 真站标题条总高 72 = padding 16×2 + 行盒 40（文字本身 35）。 */
  line-height: 40px;
}

/* 真站网格：5 列、列间距 24、行间距 32。 */
.activity-grid {
  display: grid;
  grid-template-columns: repeat(var(--columns, 5), minmax(0, 1fr));
  gap: 32px 24px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.activity-more {
  display: flex;
  justify-content: center;
  margin-top: 32px;
}

/* 真站【View more】（2026-11-26 实测）：黑底白字实心胶囊，
   144×45、padding 12px 40px、radius 24、字号 14/400、行高 21、无边框。 */
.activity-more__btn {
  display: block;
  padding: 12px 40px;
  border: 0;
  border-radius: 24px;
  background: #000;
  color: #fff;
  font-size: 14px;
  font-weight: 400;
  line-height: 21px;
  cursor: pointer;
}

.activity-more__btn:hover {
  background: #333;
}

@media (max-width: 80rem) {
  .activity-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 48rem) {
  .activity-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px 12px;
  }
}
</style>
