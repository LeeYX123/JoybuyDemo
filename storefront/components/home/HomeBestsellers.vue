<script setup>
import { computed, ref, watch } from 'vue'
import { useAsyncData } from '#imports'

import { useBestsellerFeed } from '../../composables/useBestsellerFeed'
import { useCategoryTree } from '../../composables/useCategoryTree'
import { useLocale } from '../../composables/useLocale'

// Home Bestsellers floor (docs/12 §1, real-site structure sampled from
// joybuy.co.uk 2026-11-04): floor title + "View all" on the right, a
// horizontal category tab row below the title (active = bold black with a
// black underline), and one row of ranked product cards for the active tab.
// Ranking data comes from the storefront search API (admin ranking config is
// the phase-2 backend work).
//
// 2026-11-27: two tabs are curated instead of "newest 5 of the whole subtree"
// (家居生活 = 家具 3 + 床上用品 2, 健康保健 = 维生素&补充剂 3 + 运动&体能 2).
// Rules live in `utils/bestsellerCurations.js`, the loader is shared with the
// mobile floor; every other tab keeps the original single request.
const { categories } = useCategoryTree()
const { t, categoryName, locale } = useLocale()
const { loadTabItems, localeKey } = useBestsellerFeed()

// Same nav scope as the header: categories hidden from the top nav must not
// reappear as bestseller tabs (需求文档03 12.4).
const navCategories = computed(() =>
  (categories.value || []).filter((category) => category.visible_in_nav !== false),
)

const activeSlug = ref(navCategories.value[0]?.slug || 'home-living')

// Initial tab, server-rendered. The key is reactive and carries the locale:
// a key frozen at setup keeps serving the cached English payload after the
// header switcher changes the locale (same bug class as `useSearchApi`).
const feedKey = computed(() => `home-bestsellers-${localeKey.value}`)
const { data: feed } = useAsyncData(feedKey, () => loadTabItems(activeSlug.value))

// Tab switches fetch on demand; the SSR row stays visible on a transient
// failure, matching the previous behaviour.
const switchedItems = ref(null)

// A tab row fetched before the switch is in the old language; drop it so the
// refetched (localised) feed row wins.
watch(localeKey, () => {
  switchedItems.value = null
})

const items = computed(() => {
  const source = switchedItems.value ?? feed.value
  return (Array.isArray(source) ? source : []).slice(0, 5)
})

async function selectTab(slug) {
  activeSlug.value = slug
  try {
    switchedItems.value = await loadTabItems(slug)
  } catch {
    // keep the previous list on a transient failure
  }
}

const viewAllTarget = computed(
  () => `/promo/best-seller?category=${encodeURIComponent(activeSlug.value)}`,
)

const floorTitle = computed(() => (locale.value === 'zh' ? '畅销榜单' : 'Bestsellers'))
</script>

<template>
  <section class="home-bestsellers" aria-labelledby="home-bestsellers-title">
    <header class="home-bestsellers__head">
      <h2 id="home-bestsellers-title" class="home-bestsellers__title">{{ floorTitle }}</h2>
      <NuxtLink class="home-bestsellers__view-all" :to="viewAllTarget">{{
        t('cms.viewAll')
      }}</NuxtLink>
    </header>

    <nav class="home-bestsellers__tabs" :aria-label="t('bestseller.categoriesAria')">
      <button
        v-for="category in navCategories"
        :key="category.slug"
        class="home-bestsellers__tab"
        :class="{ 'home-bestsellers__tab--active': category.slug === activeSlug }"
        type="button"
        @click="selectTab(category.slug)"
      >
        {{ categoryName(category) }}
      </button>
    </nav>

    <ul v-if="items.length > 0" class="home-bestsellers__row">
      <li v-for="(item, index) in items" :key="item.spu_public_id">
        <ProductCard :product="item" :rank="index + 1" />
      </li>
    </ul>
    <p v-else class="home-bestsellers__empty" role="status">
      {{ t('bestseller.noRanked') }}
    </p>
  </section>
</template>

<style scoped>
/* Floor spacing below the featured-brands row is larger, per the real page. */
.home-bestsellers {
  margin-top: 48px;
}

/* Real floor: 28px/600 title left, 18px/600 underlined View all right. */
.home-bestsellers__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
}

.home-bestsellers__title {
  margin: 0;
  font-size: 1.75rem;
  font-weight: var(--font-weight-semibold);
}

.home-bestsellers__view-all {
  color: #1a1a1a;
  font-size: 18px;
  font-weight: var(--font-weight-semibold);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.home-bestsellers__view-all:hover {
  color: var(--colour-accent);
}

/* Tab row: horizontal scroll, active tab = bold black + black underline. */
.home-bestsellers__tabs {
  display: flex;
  gap: 32px;
  margin-top: var(--space-3);
  overflow-x: auto;
  scrollbar-width: none;
}

.home-bestsellers__tabs::-webkit-scrollbar {
  display: none;
}

.home-bestsellers__tab {
  min-height: 42px;
  padding: 0;
  flex-shrink: 0;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  white-space: nowrap;
  font: inherit;
  font-size: 18px;
  font-weight: var(--font-weight-regular);
  color: #1a1a1a;
  cursor: pointer;
}

.home-bestsellers__tab--active {
  border-bottom: 2px solid #1a1a1a;
  font-weight: var(--font-weight-bold);
}

.home-bestsellers__row {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--space-3);
  margin-top: var(--space-4);
}

.home-bestsellers__empty {
  margin-block: var(--space-8);
  color: var(--colour-muted);
  text-align: center;
}

@media (max-width: 80rem) {
  .home-bestsellers__row {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 48rem) {
  .home-bestsellers__row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
