<script setup>
import { computed, ref } from 'vue'
import { useFetch, useRuntimeConfig } from '#imports'

import { useCategoryTree } from '../../composables/useCategoryTree'
import { useLocale } from '../../composables/useLocale'

// Home Bestsellers floor (docs/12 §1, real-site structure sampled from
// joybuy.co.uk 2026-11-04): floor title + "View all" on the right, a
// horizontal category tab row below the title (active = bold black with a
// black underline), and one row of ranked product cards for the active tab.
// Ranking data comes from the storefront search API (admin ranking config is
// the phase-2 backend work).
const { categories } = useCategoryTree()
const { categoryName, locale } = useLocale()
const config = useRuntimeConfig()

const activeSlug = ref(categories.value[0]?.slug || 'home-living')

function searchUrl(slug) {
  const query = `category=${encodeURIComponent(slug)}&sort=rating_desc&page=1`
  return import.meta.server
    ? `${config.apiBaseInternal}/search?${query}`
    : `/api/v1/search?${query}`
}

const { data } = useFetch(() => searchUrl(activeSlug.value), {
  key: 'home-bestsellers',
})

const items = computed(() => (Array.isArray(data.value?.items) ? data.value.items : []).slice(0, 5))

async function selectTab(slug) {
  activeSlug.value = slug
  try {
    const response = await $fetch(searchUrl(slug))
    data.value = response
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
      <NuxtLink class="home-bestsellers__view-all" :to="viewAllTarget">View all</NuxtLink>
    </header>

    <nav class="home-bestsellers__tabs" aria-label="Bestseller categories">
      <button
        v-for="category in categories"
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
      No ranked products for this category yet.
    </p>
  </section>
</template>

<style scoped>
/* Real floor: 28px/700 title left, underlined View all right. */
.home-bestsellers__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
}

.home-bestsellers__title {
  margin: 0;
  font-size: 1.75rem;
  font-weight: var(--font-weight-bold);
}

.home-bestsellers__view-all {
  color: var(--colour-text);
  font-size: var(--font-size-md);
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
  gap: var(--space-6);
  margin-top: var(--space-3);
  overflow-x: auto;
  scrollbar-width: none;
}

.home-bestsellers__tabs::-webkit-scrollbar {
  display: none;
}

.home-bestsellers__tab {
  min-height: 40px;
  padding: 0 var(--space-1);
  flex-shrink: 0;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  white-space: nowrap;
  font: inherit;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-regular);
  color: var(--colour-text);
  cursor: pointer;
}

.home-bestsellers__tab--active {
  border-bottom: 2px solid var(--colour-text);
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
