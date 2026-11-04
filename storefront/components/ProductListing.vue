<script setup>
import { computed } from 'vue'

// Category/search listing page shared by /c/[slug] and /search.
const props = defineProps({
  mode: {
    type: String,
    required: true,
    validator: (value) => ['category', 'search'].includes(value),
  },
  slug: {
    type: String,
    default: '',
  },
})

import { useCategoryTree } from '../composables/useCategoryTree'
import { useLocale } from '../composables/useLocale'

const route = useRoute()
const router = useRouter()

// Sidebar facets come from the shared category tree (11 standard roots).
const { categories } = useCategoryTree()
const { categoryName } = useLocale()

// /s?k= is the spec'd discovery entry (docs/12 §4); /search?q= stays compatible.
const searchText = computed(() => String(route.query.q || route.query.k || ''))
const activeSort = computed(() => String(route.query.sort || 'relevance'))
const activePage = computed(() => Number(route.query.page || '1'))
const minPrice = computed(() => String(route.query.min_price || ''))
const maxPrice = computed(() => String(route.query.max_price || ''))

const params = computed(() => {
  const base = { sort: activeSort.value, page: activePage.value }
  if (minPrice.value) base.min_price = minPrice.value
  if (maxPrice.value) base.max_price = maxPrice.value
  if (props.mode === 'category') {
    base.category = props.slug
  } else if (searchText.value) {
    base.q = searchText.value
  }
  return base
})

const { data, error, status } = await useSearch(params)

const items = computed(() => (Array.isArray(data.value?.items) ? data.value.items : []))
const total = computed(() => data.value?.total ?? 0)
const totalPages = computed(() => data.value?.total_pages ?? 0)

const heading = computed(() => {
  if (props.mode === 'category') {
    return data.value?.items?.length ? `Category: ${props.slug}` : `Category: ${props.slug}`
  }
  return searchText.value ? `Search: ${searchText.value}` : 'Browse all products'
})

const sortOptions = [
  { value: 'relevance', label: 'Relevance' },
  { value: 'price_asc', label: 'Price: low to high' },
  { value: 'price_desc', label: 'Price: high to low' },
  { value: 'rating_desc', label: 'Top rated' },
  { value: 'newest', label: 'Newest' },
]

function updateQuery(patch) {
  router.push({ query: { ...route.query, page: undefined, ...patch } })
}

function onSortChange(event) {
  updateQuery({ sort: event.target.value })
}

function applyPriceFilter(event) {
  event.preventDefault()
  const form = new FormData(event.target)
  updateQuery({ min_price: form.get('min_price'), max_price: form.get('max_price') })
}

function goToPage(page) {
  if (page >= 1 && (totalPages.value === 0 || page <= totalPages.value)) {
    updateQuery({ page })
  }
}

useHead(() => ({ title: heading.value }))
</script>

<template>
  <!-- Full-bleed white row (real listing pages are white edge to edge). -->
  <div class="listing-page-bg">
    <AppContainer>
      <div class="listing-layout">
        <!-- Left filter sidebar (joybuy /s?k= spec: 234px column). -->
        <aside class="listing-sidebar">
          <section class="filter-card">
            <h2 class="filter-card__title">Category</h2>
            <ul class="filter-card__list">
              <li v-for="category in categories" :key="category.slug">
                <NuxtLink
                  class="filter-card__item"
                  :class="{ 'filter-card__item--active': category.slug === props.slug }"
                  :to="`/s?category=${category.slug}`"
                >
                  {{ categoryName(category) }}
                </NuxtLink>
              </li>
            </ul>
          </section>

          <section class="filter-card">
            <h2 class="filter-card__title">Price</h2>
            <form class="filter-card__price" @submit="applyPriceFilter">
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
              <button type="submit">Go</button>
            </form>
          </section>
        </aside>

        <div class="listing-main">
          <header class="listing-head">
            <h1>{{ heading }}</h1>
            <p class="listing-head__count" role="status">
              {{ total }} product{{ total === 1 ? '' : 's' }}
            </p>
          </header>

          <div class="listing-toolbar">
            <span class="listing-toolbar__spacer" aria-hidden="true"></span>
            <label class="sort-control">
              <span>Sort by:</span>
              <select :value="activeSort" @change="onSortChange">
                <option v-for="option in sortOptions" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
            </label>
          </div>

          <div v-if="error" class="listing-state" role="alert">
            <p>Could not load products. Please try again shortly.</p>
          </div>

          <ul v-else-if="items.length > 0" class="listing-grid">
            <li v-for="item in items" :key="item.spu_public_id">
              <ProductCard :product="item" />
            </li>
          </ul>

          <div v-else-if="status !== 'pending'" class="listing-state" role="status">
            <p>
              No products match your filters yet. Try clearing the price range or another search.
            </p>
          </div>

          <nav v-if="totalPages > 1" class="pagination" aria-label="Pagination">
            <button type="button" :disabled="activePage <= 1" @click="goToPage(activePage - 1)">
              Previous
            </button>
            <span aria-current="page">Page {{ activePage }} of {{ totalPages }}</span>
            <button
              type="button"
              :disabled="activePage >= totalPages"
              @click="goToPage(activePage + 1)"
            >
              Next
            </button>
          </nav>
        </div>
      </div>
    </AppContainer>
  </div>
</template>

<style scoped>
/* Full-bleed white: escapes the centered container so ultra-wide strips are
 * white too (scoped attr beats the .app-main > * margin rule). */
.listing-page-bg {
  margin-top: 0;
  margin-inline: calc(50% - 50vw);
  background: #ffffff;
}

/* Two-column layout per the joybuy /s?k= spec: 234px sidebar + results. */
.listing-layout {
  display: grid;
  grid-template-columns: 234px minmax(0, 1fr);
  gap: 24px;
  margin-block: 24px;
}

.listing-sidebar {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  align-self: start;
  position: sticky;
  top: calc(var(--header-height) + 40px + var(--space-4));
}

.filter-card {
  padding: var(--space-3);
  border-radius: 8px;
  background: var(--colour-surface);
}

.filter-card__title {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-bold);
}

.filter-card__list {
  display: flex;
  flex-direction: column;
}

.filter-card__item {
  display: flex;
  align-items: center;
  min-height: 32px;
  padding: 0 var(--space-2);
  border-radius: var(--radius-sm);
  text-decoration: none;
  font-size: var(--font-size-sm);
  color: var(--colour-text-secondary);
}

.filter-card__item:hover {
  background: var(--colour-hover);
  color: var(--colour-text);
}

.filter-card__item--active {
  background: var(--colour-accent-soft);
  color: var(--colour-accent);
  font-weight: var(--font-weight-semibold);
}

.filter-card__price {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.filter-card__price input {
  min-height: 36px;
  width: 100%;
  min-width: 0;
  padding: 0 var(--space-2);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-sm);
  font: inherit;
  font-size: var(--font-size-sm);
}

.filter-card__price button {
  min-height: 36px;
  padding: 0 var(--space-3);
  flex-shrink: 0;
  border: 1px solid var(--colour-border-strong);
  border-radius: var(--radius-sm);
  background: var(--colour-surface);
  cursor: pointer;
  font: inherit;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
}

.listing-head h1 {
  margin: 0;
  font-size: 1.5rem;
  font-weight: var(--font-weight-bold);
}

.listing-head__count {
  margin: var(--space-1) 0 0;
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}

.listing-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  margin-block: var(--space-4);
}

.sort-control {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-sm);
  color: var(--colour-muted);
}

.sort-control select {
  min-height: 40px;
  padding: 0 var(--space-3);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-sm);
  font: inherit;
  background: var(--colour-surface);
}

.listing-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-2);
}

.listing-state {
  margin-block: var(--space-10);
  padding: var(--space-8);
  border: 1px dashed var(--colour-border-strong);
  border-radius: var(--radius-lg);
  color: var(--colour-muted);
  text-align: center;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  margin-block: var(--space-8);
}

.pagination button {
  min-height: 44px;
  padding: 0 var(--space-5);
  border: 1px solid var(--colour-border-strong);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  cursor: pointer;
  font-weight: var(--font-weight-semibold);
}

.pagination button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

@media (max-width: 80rem) {
  .listing-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 48rem) {
  .listing-layout {
    grid-template-columns: 1fr;
  }

  .listing-sidebar {
    position: static;
  }

  .listing-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 30rem) {
  .listing-grid {
    grid-template-columns: 1fr;
  }
}
</style>
