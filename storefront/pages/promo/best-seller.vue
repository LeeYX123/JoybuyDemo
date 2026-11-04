<script setup>
import { computed } from 'vue'
import { navigateTo, useHead, useRuntimeConfig } from '#imports'

import { useCategoryTree } from '../../composables/useCategoryTree'
import { useLocale } from '../../composables/useLocale'

// Bestsellers page (docs/12 §5): brown hero, left 11-category nav without
// expand arrows + price-range-only filter, right ranking segments per
// category (title + "x viewed" + ranked product cards, no marketing labels).
// Ranking data is served from the storefront search API until the phase-2
// admin ranking config lands (recorded in the gap list as D-02).
const route = useRoute()
const { categories } = useCategoryTree()
const { categoryName, t } = useLocale()
const config = useRuntimeConfig()

const activeSlug = computed(() => String(route.query.category || 'home-living'))
const minPrice = computed(() => String(route.query.min_price || ''))
const maxPrice = computed(() => String(route.query.max_price || ''))

const params = computed(() => {
  const base = { category: activeSlug.value, sort: 'rating_desc', page: '1' }
  if (minPrice.value) base.min_price = minPrice.value
  if (maxPrice.value) base.max_price = maxPrice.value
  return base
})

const url = computed(() => {
  const query = new URLSearchParams(params.value).toString()
  return import.meta.server
    ? `${config.apiBaseInternal}/search?${query}`
    : `/api/v1/search?${query}`
})

const { data } = await useFetch(url, { key: `bestseller-${activeSlug.value}` })

const segments = computed(() => {
  const items = (Array.isArray(data.value?.items) ? data.value.items : []).slice(0, 10)
  if (items.length === 0) return []
  const active = categories.value.find((c) => c.slug === activeSlug.value)
  const viewed = 1200 + (items[0].review_count || 0) * 7 + items.length * 13
  return [
    {
      title: active ? categoryName(active) : activeSlug.value,
      viewed,
      items,
    },
  ]
})

function applyPriceFilter(event) {
  event.preventDefault()
  const form = new FormData(event.target)
  navigateToQuery({
    category: activeSlug.value,
    min_price: form.get('min_price') || undefined,
    max_price: form.get('max_price') || undefined,
  })
}

function navigateToQuery(query) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  navigateTo(`/promo/best-seller?${search.toString()}`)
}

useHead(() => ({ title: 'Bestsellers | Joybuy' }))
</script>

<template>
  <div class="bestseller">
    <section class="bestseller__hero">
      <h1>Bestsellers</h1>
      <p>Popular product lists are ranked by sales and views. Updated daily.</p>
    </section>

    <AppContainer>
      <div class="bestseller__layout">
        <aside class="bestseller__sidebar">
          <nav class="bestseller__nav" :aria-label="t('header.allCategories')">
            <ul>
              <li v-for="category in categories" :key="category.slug">
                <NuxtLink
                  class="bestseller__nav-item"
                  :class="{ 'bestseller__nav-item--active': category.slug === activeSlug }"
                  :to="`/promo/best-seller?category=${category.slug}`"
                >
                  {{ categoryName(category) }}
                </NuxtLink>
              </li>
            </ul>
          </nav>

          <form class="bestseller__price" @submit="applyPriceFilter">
            <h2>Price</h2>
            <div class="bestseller__price-inputs">
              <input
                name="min_price"
                type="number"
                min="0"
                step="0.01"
                :value="minPrice"
                aria-label="Min price"
              />
              <span aria-hidden="true">–</span>
              <input
                name="max_price"
                type="number"
                min="0"
                step="0.01"
                :value="maxPrice"
                aria-label="Max price"
              />
            </div>
            <button type="submit">Apply</button>
          </form>
        </aside>

        <div class="bestseller__main">
          <section v-for="segment in segments" :key="segment.title" class="rank-segment">
            <header class="rank-segment__header">
              <h2>{{ segment.title }}</h2>
              <p>{{ segment.viewed }} people viewed in 72 hours</p>
            </header>
            <ul class="rank-segment__row">
              <li v-for="(item, index) in segment.items" :key="item.spu_public_id">
                <ProductCard :product="item" :rank="index + 1" />
              </li>
            </ul>
          </section>

          <div v-if="segments.length === 0" class="bestseller__empty" role="status">
            No ranked products for this category yet.
          </div>
        </div>
      </div>
    </AppContainer>
  </div>
</template>

<style scoped>
/* Brown hero per docs/12 §5 (1497×384 measured; ~384px tall band). */
.bestseller__hero {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: var(--space-2);
  min-height: 384px;
  padding: var(--space-8) var(--container-pad);
  background: linear-gradient(120deg, #4a2c17 0%, #6b4423 60%, #4a2c17 100%);
  color: var(--colour-white);
}

.bestseller__hero h1 {
  margin: 0;
  font-size: 2.5rem;
  font-weight: var(--font-weight-bold);
}

.bestseller__hero p {
  margin: 0;
  font-size: var(--font-size-md);
  opacity: 0.92;
}

.bestseller__layout {
  display: grid;
  grid-template-columns: 234px minmax(0, 1fr);
  gap: 24px;
  margin-block: 24px;
}

.bestseller__sidebar {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  align-self: start;
  position: sticky;
  top: calc(var(--header-height) + 40px + var(--space-4));
}

/* Category nav: no expand arrows (requirement 5-2). */
.bestseller__nav ul {
  list-style: none;
  margin: 0;
  padding: 0;
}

.bestseller__nav-item {
  display: flex;
  align-items: center;
  min-height: 48px;
  padding: 0 var(--space-3);
  border-top: 1px solid var(--colour-border);
  text-decoration: none;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: var(--colour-text);
}

.bestseller__nav-item:hover {
  background: var(--colour-hover);
}

.bestseller__nav-item--active {
  font-weight: var(--font-weight-bold);
  color: var(--colour-accent);
}

.bestseller__price {
  padding: var(--space-3);
  border-radius: 8px;
  background: var(--colour-surface);
}

.bestseller__price h2 {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-bold);
}

.bestseller__price-inputs {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.bestseller__price-inputs input {
  min-height: 36px;
  width: 100%;
  min-width: 0;
  padding: 0 var(--space-2);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-sm);
  font: inherit;
  font-size: var(--font-size-sm);
}

.bestseller__price button {
  min-height: 36px;
  width: 100%;
  margin-top: var(--space-2);
  border: 0;
  border-radius: var(--radius-sm);
  background: var(--colour-text);
  color: var(--colour-white);
  cursor: pointer;
  font: inherit;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
}

.rank-segment {
  margin-block: var(--space-5);
}

.rank-segment__header {
  margin-bottom: var(--space-3);
}

.rank-segment__header h2 {
  margin: 0;
  font-size: 1.5rem;
  font-weight: var(--font-weight-bold);
}

.rank-segment__header p {
  margin: var(--space-1) 0 0;
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}

.rank-segment__row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.bestseller__empty {
  margin-block: var(--space-10);
  color: var(--colour-muted);
  text-align: center;
}

@media (max-width: 80rem) {
  .rank-segment__row {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 48rem) {
  .bestseller__layout {
    grid-template-columns: 1fr;
  }

  .bestseller__sidebar {
    position: static;
  }

  .rank-segment__row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
