<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from '#imports'

import { useSearch } from '../../composables/useSearchApi'
import { useCategoryTree } from '../../composables/useCategoryTree'
import { useLocale } from '../../composables/useLocale'
import { resolveCategoryContext } from '../../utils/categoryContext'
import { formatDisplayPrice } from '../../utils/display'

// Mobile listing (docs/20 §1): toolbar row (result count + native sort
// select), a 2-column product grid (white 12px-radius cards, 1:1 cover image,
// 14px two-line title, 16px/700 red price) and a prev/next pager with the
// current x/y position. Category mode shows the category name 20px/700 above
// the toolbar. Data comes from the same search API as the desktop listing
// (useSearch, SSR apiBaseInternal / client proxy) with identical query
// params; the desktop template stays untouched (ADR 0001).
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

const route = useRoute()
const router = useRouter()
const { t, categoryName, locale } = useLocale()

const { categories } = useCategoryTree()
const categoryContext = computed(() =>
  props.mode === 'category'
    ? resolveCategoryContext(categories.value, props.slug)
    : { root: null, child: null },
)

// /s?k= is the spec'd discovery entry (docs/12 §4); /search?q= stays compatible.
const searchText = computed(() => String(route.query.q || route.query.k || ''))
const activeSort = computed(() => String(route.query.sort || 'relevance'))
const activePage = computed(() => Math.max(1, Number(route.query.page || '1') || 1))
const minPrice = computed(() => String(route.query.min_price || ''))
const maxPrice = computed(() => String(route.query.max_price || ''))

const heading = computed(() => {
  if (props.mode === 'category') {
    const node = categoryContext.value.child || categoryContext.value.root
    return node ? categoryName(node) : props.slug
  }
  return searchText.value ? `Search: ${searchText.value}` : 'Browse all products'
})

// Same param shape as the desktop ProductListing (sort/page/price bounds).
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

const { data, error, status } = useSearch(params)

const items = computed(() => (Array.isArray(data.value?.items) ? data.value.items : []))
const resultTotal = computed(() => Number(data.value?.total ?? 0))
const totalPages = computed(() => data.value?.total_pages ?? 0)

// docs/20 §1 sort set: relevance / price ↑ / price ↓ / rating.
const sortOptions = computed(() => [
  { value: 'relevance', label: t('listing.relevance') },
  { value: 'price_asc', label: t('listing.priceLowHigh') },
  { value: 'price_desc', label: t('listing.priceHighLow') },
  { value: 'rating_desc', label: t('listing.topRated') },
])

function updateQuery(patch) {
  router.push({ query: { ...route.query, page: undefined, ...patch } })
}

function onSortChange(event) {
  const value = String(event.target.value || '')
  if (value && value !== activeSort.value) {
    updateQuery({ sort: value })
  }
}

function goToPage(page) {
  if (page >= 1 && (totalPages.value === 0 || page <= totalPages.value)) {
    updateQuery({ page })
  }
}

// Card value helpers: same data contract as ProductCard.
function priceOf(item) {
  const raw = item?.retail_price
  if (typeof raw === 'string' && raw.trim()) return raw.trim()
  const price = item?.price_min ?? item?.price
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

function productHref(item) {
  return item?.href || `/p/${item?.spu_public_id || item?.public_id || ''}`
}
</script>

<template>
  <div class="m-list">
    <h1 v-if="heading" class="m-list__heading">{{ heading }}</h1>

    <!-- Toolbar: result count + sort select (docs/20 §1). -->
    <div class="m-list__toolbar">
      <span class="m-list__count"> {{ resultTotal }} {{ t('listing.productsSuffix') }} </span>
      <label class="m-list__sort">
        <span class="m-list__sort-label">{{ t('listing.sortBy') }}</span>
        <select class="m-list__sort-select" :value="activeSort" @change="onSortChange">
          <option v-for="option in sortOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </label>
    </div>

    <p v-if="error" class="m-list__state" role="alert">{{ t('listing.loadError') }}</p>

    <ul v-else-if="items.length > 0" class="m-list__grid">
      <li v-for="item in items" :key="item.spu_public_id || item.public_id">
        <NuxtLink class="m-list__card" :to="productHref(item)">
          <img class="m-list__img" :src="imgOf(item)" alt="" loading="lazy" />
          <span class="m-list__name">{{ titleOf(item) }}</span>
          <span class="m-list__price">{{ priceOf(item) }}</span>
        </NuxtLink>
      </li>
    </ul>

    <p v-else-if="status !== 'pending'" class="m-list__state" role="status">
      {{ t('listing.emptyResults') }}
    </p>

    <!-- Pager: prev/next pills + current x/y (docs/20 §1). -->
    <nav v-if="totalPages > 1" class="m-list__pager" :aria-label="t('pagination.label')">
      <button
        class="m-list__pager-btn"
        type="button"
        :disabled="activePage <= 1"
        :aria-label="t('pagination.previous')"
        @click="goToPage(activePage - 1)"
      >
        {{ t('pagination.previous') }}
      </button>
      <span class="m-list__pager-page">
        {{ t('pagination.pageOf', { page: activePage, total: totalPages }) }}
      </span>
      <button
        class="m-list__pager-btn"
        type="button"
        :disabled="activePage >= totalPages"
        :aria-label="t('pagination.next')"
        @click="goToPage(activePage + 1)"
      >
        {{ t('pagination.next') }}
      </button>
    </nav>
  </div>
</template>

<style scoped>
.m-list {
  padding: 16px 16px 24px;
  background: #f5f6fa;
  min-height: 60vh;
}

/* Category name above the toolbar: 20px/700 (docs/20 §1). */
.m-list__heading {
  margin: 0 0 12px;
  color: #1a1a1a;
  font-size: 20px;
  font-weight: var(--font-weight-bold);
  line-height: 1.3;
}

.m-list__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.m-list__count {
  color: #1a1a1a;
  font-size: 16px;
}

.m-list__sort {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.m-list__sort-label {
  color: #55565b;
  font-size: 14px;
  white-space: nowrap;
}

.m-list__sort-select {
  max-width: 170px;
  height: 36px;
  padding: 0 8px;
  border: 1px solid #1a1a1a;
  border-radius: 8px;
  background: #ffffff;
  color: #1a1a1a;
  font: inherit;
  font-size: 14px;
}

/* 2-column product grid, gap 12 (docs/20 §1). */
.m-list__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.m-list__card {
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  background: #ffffff;
  overflow: hidden;
  text-decoration: none;
}

.m-list__img {
  width: 100%;
  aspect-ratio: 1 / 1;
  object-fit: cover;
  background: #eceef1;
}

.m-list__name {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  padding: 10px 12px 0;
  color: #1a1a1a;
  font-size: 14px;
  line-height: 20px;
  min-height: 50px;
}

.m-list__price {
  padding: 6px 12px 12px;
  color: #e1251b;
  font-size: 16px;
  font-weight: var(--font-weight-bold);
}

/* Empty / error states: same copy as the desktop listing. */
.m-list__state {
  margin: 32px 0;
  padding: 24px 16px;
  border: 1px dashed #c7c9cf;
  border-radius: 12px;
  background: #ffffff;
  color: #7a7d85;
  font-size: 15px;
  text-align: center;
}

/* Pager: prev/next capsules + x/y position. */
.m-list__pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding-top: 20px;
}

.m-list__pager-btn {
  min-height: 40px;
  padding: 0 20px;
  border: 1px solid #1a1a1a;
  border-radius: 999px;
  background: #ffffff;
  color: #1a1a1a;
  font: inherit;
  font-size: 15px;
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
}

.m-list__pager-btn:disabled {
  opacity: 0.35;
  cursor: default;
}

.m-list__pager-page {
  color: #1a1a1a;
  font-size: 16px;
}
</style>
