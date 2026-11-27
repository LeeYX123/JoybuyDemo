<script setup>
import { computed, ref, watch } from 'vue'
import { useAsyncData } from '#imports'

import { useBestsellerFeed } from '../../composables/useBestsellerFeed'
import { useWishlist } from '../../composables/useWishlist'
import { useCategoryTree } from '../../composables/useCategoryTree'
import { useLocale } from '../../composables/useLocale'
import { formatDisplayPrice } from '../../utils/display'

// Mobile Bestsellers floor (docs/19 §2.4, m.joybuy archive measurements):
// 28px/700 title + 56px round chevron (view all), sub-category tab row
// (16px, active = 700 + black underline), horizontally scrolling ranked
// cards 146×250 with a grey rank badge top-left and a wishlist heart
// top-right. Data: same storefront search API as the desktop floor.
//
// 2026-11-27: the curated tabs (家居生活 3:2, 健康保健 3:2) share the desktop
// rules and loader (`utils/bestsellerCurations.js` +
// `composables/useBestsellerFeed.js`), so both floors show the same products
// in the same order; other tabs keep the original single request.
const { categories } = useCategoryTree()
const { t, categoryName, locale } = useLocale()
const { isFavourite, toggle } = useWishlist()
const { loadTabItems, localeKey } = useBestsellerFeed()

const navCategories = computed(() =>
  (categories.value || []).filter((category) => category.visible_in_nav !== false),
)

const activeSlug = ref(navCategories.value[0]?.slug || 'home-living')

// Reactive key carrying the locale, so a language switch refetches the row
// instead of reusing the cached English payload (same fix as the desktop floor
// and `useSearchApi`).
const feedKey = computed(() => `mobile-bestsellers-${localeKey.value}`)
const { data: feed } = useAsyncData(feedKey, () => loadTabItems(activeSlug.value))

// Curated tabs return their configured row (5 cards today); other tabs return
// the plain search page and keep showing up to 10 cards.
const switchedItems = ref(null)

// A row fetched before the switch is in the old language; drop it so the
// refetched (localised) feed row wins.
watch(localeKey, () => {
  switchedItems.value = null
})

const items = computed(() => {
  const source = switchedItems.value ?? feed.value
  return (Array.isArray(source) ? source : []).slice(0, 10)
})

async function selectTab(slug) {
  activeSlug.value = slug
  try {
    switchedItems.value = await loadTabItems(slug)
  } catch {
    // keep the previous list on a transient failure
  }
}

const floorTitle = computed(() => (locale.value === 'zh' ? '畅销榜单' : 'Bestsellers'))
const viewAllTarget = computed(
  () => `/promo/best-seller?category=${encodeURIComponent(activeSlug.value)}`,
)

function priceOf(item) {
  // Same price contract as ProductCard: retail_price string, fallback price_min.
  const raw = item?.retail_price
  if (typeof raw === 'string' && raw.trim()) return raw.trim()
  const price = item?.family_max_price ?? item?.price_min ?? item?.price
  return price == null ? '' : formatDisplayPrice(price)
}

function titleOf(item) {
  if (locale.value === 'zh' && item?.title_zh) return item.title_zh
  return item?.title || ''
}

const imgFallback = '/images/logo.png'

function imgOf(item) {
  const src = item?.image_path || item?.image
  return typeof src === 'string' && src ? src : imgFallback
}
</script>

<template>
  <section class="m-best" aria-labelledby="m-best-title">
    <header class="m-best__head">
      <h2 id="m-best-title" class="m-best__title">{{ floorTitle }}</h2>
      <NuxtLink class="m-best__more" :to="viewAllTarget" :aria-label="t('cms.viewAll')">
        <svg
          viewBox="0 0 24 24"
          width="18"
          height="18"
          aria-hidden="true"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <path d="m9 5 7 7-7 7" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </NuxtLink>
    </header>

    <nav class="m-best__tabs" :aria-label="t('bestseller.categoriesAria')">
      <button
        v-for="category in navCategories"
        :key="category.slug"
        class="m-best__tab"
        :class="{ 'm-best__tab--active': category.slug === activeSlug }"
        type="button"
        @click="selectTab(category.slug)"
      >
        {{ categoryName(category) }}
      </button>
    </nav>

    <ul v-if="items.length > 0" class="m-best__row">
      <li v-for="(item, index) in items" :key="item.spu_public_id">
        <NuxtLink class="m-best__card" :to="`/p/${item.spu_public_id}`">
          <span class="m-best__rank" aria-hidden="true">{{ index + 1 }}</span>
          <button
            class="m-best__heart"
            :class="{ 'm-best__heart--on': isFavourite(item.spu_public_id) }"
            type="button"
            :aria-label="t('product.addToWishlist')"
            @click.prevent="toggle(item.spu_public_id)"
          >
            <svg
              viewBox="0 0 24 24"
              width="18"
              height="18"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
            >
              <path
                d="M12 20s-7-4.6-9.3-9A5.3 5.3 0 0 1 12 6.7 5.3 5.3 0 0 1 21.3 11C19 15.4 12 20 12 20Z"
                stroke-linejoin="round"
              />
            </svg>
          </button>
          <img class="m-best__img" :src="imgOf(item)" alt="" loading="lazy" />
          <span class="m-best__name">{{ titleOf(item) }}</span>
          <span class="m-best__price">{{ priceOf(item) }}</span>
        </NuxtLink>
      </li>
    </ul>
    <p v-else class="m-best__empty" role="status">{{ t('bestseller.noRanked') }}</p>
  </section>
</template>

<style scoped>
.m-best {
  margin-top: 32px;
}

.m-best__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
}

.m-best__title {
  margin: 0;
  color: #1a1a1a;
  font-size: 28px;
  font-weight: var(--font-weight-bold);
  line-height: 1.2;
}

.m-best__more {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #f0f1f4;
  color: #1a1a1a;
}

.m-best__tabs {
  display: flex;
  gap: 24px;
  margin-top: 8px;
  padding: 0 16px;
  overflow-x: auto;
  scrollbar-width: none;
  border-bottom: 1px solid #f0f1f2;
}

.m-best__tabs::-webkit-scrollbar {
  display: none;
}

.m-best__tab {
  flex-shrink: 0;
  min-height: 40px;
  padding: 0;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: #1a1a1a;
  font: inherit;
  font-size: 16px;
  white-space: nowrap;
  cursor: pointer;
}

.m-best__tab--active {
  border-bottom-color: #1a1a1a;
  font-weight: var(--font-weight-bold);
}

/* Horizontal ranked cards: 146×250, gap 8 (measured). */
.m-best__row {
  display: flex;
  gap: 8px;
  margin: 12px 0 0;
  padding: 0 16px;
  list-style: none;
  overflow-x: auto;
  scrollbar-width: none;
}

.m-best__row::-webkit-scrollbar {
  display: none;
}

.m-best__row > li {
  flex-shrink: 0;
}

.m-best__card {
  position: relative;
  display: flex;
  flex-direction: column;
  width: 146px;
  height: 250px;
  border-radius: 12px;
  background: #f7f8fa;
  overflow: hidden;
}

.m-best__rank {
  position: absolute;
  top: 0;
  left: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 24px;
  padding: 0 6px;
  border-radius: 0 0 10px 0;
  background: rgba(199, 201, 207, 0.92);
  color: #ffffff;
  font-size: 13px;
  font-weight: var(--font-weight-bold);
}

.m-best__heart {
  position: absolute;
  top: 8px;
  right: 8px;
  display: inline-flex;
  padding: 4px;
  border: 0;
  background: transparent;
  color: #55565b;
  cursor: pointer;
}

.m-best__heart--on {
  color: var(--colour-accent, #e1251b);
}

.m-best__heart--on svg path {
  fill: currentColor;
}

.m-best__img {
  width: 100%;
  height: 146px;
  object-fit: cover;
  background: #eceef1;
}

.m-best__name {
  /* 标题最多 2 行，超出省略号（min-height 42 = 2×18 保持卡片等高）。 */
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  padding: 6px 8px 0;
  color: #1a1a1a;
  font-size: 13px;
  line-height: 18px;
  min-height: 42px;
  word-break: break-word;
}

.m-best__price {
  margin-top: auto;
  padding: 0 8px 10px;
  color: var(--colour-accent, #e1251b);
  font-size: 15px;
  font-weight: var(--font-weight-bold);
}

.m-best__empty {
  margin: 24px 16px;
  color: var(--colour-muted, #7a7d85);
  text-align: center;
}
</style>
