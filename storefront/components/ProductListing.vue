<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

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

import CategoryTileCarousel from './CategoryTileCarousel.vue'
import { resolveCategoryContext } from '../utils/categoryContext'
import { categoryHref } from '../utils/categoryLinks'

const route = useRoute()
const router = useRouter()

// Sidebar facets come from the shared category tree (11 standard roots).
const { categories } = useCategoryTree()
const { t, categoryName } = useLocale()

// Category mode resolves the current L2 to its parent so the page can show a
// trail (首页 / 一级 / 二级) plus the sibling tiles of that parent.
const categoryContext = computed(() =>
  props.mode === 'category'
    ? resolveCategoryContext(categories.value, props.slug)
    : { root: null, child: null },
)
const currentRoot = computed(() => categoryContext.value.root)
// Only set in the L2 view; the L1 view keeps the sidebar collapsed and the
// selection on the root itself.
const currentChild = computed(() => categoryContext.value.child)

// The filter list only ever contains the 11 roots: an L2 page highlights its
// parent root (never expands the children in the sidebar).
function isActiveRoot(category) {
  return category.slug === props.slug || category.slug === currentRoot.value?.slug
}

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
    // Localised category name (L2 when given, otherwise the L1); the slug is
    // only a fallback for unknown ids.
    const node = currentChild.value || currentRoot.value
    return node ? categoryName(node) : props.slug
  }
  return searchText.value ? `Search: ${searchText.value}` : 'Browse all products'
})

const sortOptions = computed(() => [
  { value: 'relevance', label: t('listing.relevance') },
  { value: 'price_desc', label: t('listing.priceHighLow') },
  { value: 'price_asc', label: t('listing.priceLowHigh') },
  { value: 'rating_desc', label: t('listing.topRated') },
  { value: 'newest', label: t('listing.newest') },
])

function updateQuery(patch) {
  router.push({ query: { ...route.query, page: undefined, ...patch } })
}

// Custom sort dropdown state (click-outside closes it).
const sortOpen = ref(false)
const sortRoot = ref(null)
const activeLabel = computed(
  () =>
    sortOptions.value.find((option) => option.value === activeSort.value)?.label ||
    t('listing.relevance'),
)

function pickSort(value) {
  sortOpen.value = false
  if (value !== activeSort.value) {
    updateQuery({ sort: value })
  }
}

function onDocClick(event) {
  if (sortOpen.value && sortRoot.value && !sortRoot.value.contains(event.target)) {
    sortOpen.value = false
  }
}

onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))

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
          <p class="listing-sidebar__title">{{ t('listing.filters') }}</p>
          <section class="filter-card">
            <h2 class="filter-card__title">{{ t('listing.category') }}</h2>
            <ul class="filter-card__list">
              <li v-for="category in categories" :key="category.slug">
                <NuxtLink
                  class="filter-card__item"
                  :class="{ 'filter-card__item--active': isActiveRoot(category) }"
                  :to="`/s?category=${category.slug}`"
                >
                  {{ categoryName(category) }}
                </NuxtLink>
              </li>
            </ul>
            <!-- The filter list stays flat: opening an L2 (from the header
                 dropdown or the tile row) keeps the L1 selected instead of
                 expanding the children here — the tile row is the L2 picker. -->
          </section>

          <section class="filter-card">
            <h2 class="filter-card__title">{{ t('listing.price') }}</h2>
            <form class="filter-card__price" @submit="applyPriceFilter">
              <input
                name="min_price"
                type="number"
                min="0"
                step="0.01"
                :value="minPrice"
                :aria-label="t('listing.price') + ' ↓'"
              />
              <span aria-hidden="true">–</span>
              <input
                name="max_price"
                type="number"
                min="0"
                step="0.01"
                :value="maxPrice"
                :aria-label="t('listing.price') + ' ↑'"
              />
              <button type="submit">{{ t('listing.apply') }}</button>
            </form>
          </section>
        </aside>

        <div class="listing-main">
          <!-- Category mode: trail (首页 / 一级 / 二级) + one carousel row of
               the sibling tiles of the same parent, current one highlighted. -->
          <template v-if="props.mode === 'category' && currentRoot">
            <nav class="listing-breadcrumb" :aria-label="t('categoryStrip.label')">
              <NuxtLink class="listing-breadcrumb__link" to="/">
                {{ t('breadcrumb.home') }}
              </NuxtLink>
              <span class="listing-breadcrumb__sep" aria-hidden="true">/</span>
              <!-- 一级回频道落地页（有频道 code 时），无 code 降级 /c/<slug>。 -->
              <NuxtLink class="listing-breadcrumb__link" :to="categoryHref(currentRoot)">
                {{ categoryName(currentRoot) }}
              </NuxtLink>
              <template v-if="currentChild">
                <span class="listing-breadcrumb__sep" aria-hidden="true">/</span>
                <span class="listing-breadcrumb__current">{{ categoryName(currentChild) }}</span>
              </template>
            </nav>
            <CategoryTileCarousel
              v-if="currentRoot.children?.length"
              class="listing-category-strip"
              :items="currentRoot.children"
              :active-slug="props.slug"
            />
          </template>
          <header class="listing-head">
            <h1>{{ heading }}</h1>
            <p class="listing-head__count" role="status">
              {{ total }} {{ t('listing.productsSuffix') }}
            </p>
          </header>

          <div class="listing-toolbar">
            <div ref="sortRoot" class="sort-control">
              <span class="sort-control__label">{{ t('listing.sortBy') }}</span>
              <!-- Custom dropdown (native select popups are OS-rendered blue):
                   white menu, grey hover, dark-border trigger. -->
              <button
                class="sort-control__trigger"
                type="button"
                :aria-expanded="sortOpen"
                @click="sortOpen = !sortOpen"
              >
                <span>{{ activeLabel }}</span>
                <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
                  <path d="m12 15-5-5h10l-5 5Z" fill="currentColor" />
                </svg>
              </button>
              <ul v-if="sortOpen" class="sort-control__menu" role="listbox">
                <li v-for="option in sortOptions" :key="option.value">
                  <button
                    class="sort-control__option"
                    :class="{ 'sort-control__option--active': option.value === activeSort }"
                    type="button"
                    role="option"
                    :aria-selected="option.value === activeSort"
                    @click="pickSort(option.value)"
                  >
                    {{ option.label }}
                  </button>
                </li>
              </ul>
            </div>
          </div>

          <div v-if="error" class="listing-state" role="alert">
            <p>{{ t('listing.loadError') }}</p>
          </div>

          <ul v-else-if="items.length > 0" class="listing-grid">
            <li v-for="item in items" :key="item.spu_public_id">
              <ProductCard :product="item" />
            </li>
          </ul>

          <div v-else-if="status !== 'pending'" class="listing-state" role="status">
            <p>
              {{ t('listing.emptyResults') }}
            </p>
          </div>

          <nav v-if="totalPages > 1" class="pagination" :aria-label="t('pagination.label')">
            <button type="button" :disabled="activePage <= 1" @click="goToPage(activePage - 1)">
              {{ t('pagination.previous') }}
            </button>
            <span aria-current="page">Page {{ activePage }} of {{ totalPages }}</span>
            <button
              type="button"
              :disabled="activePage >= totalPages"
              @click="goToPage(activePage + 1)"
            >
              {{ t('pagination.next') }}
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
.listing-page-bg.listing-page-bg {
  /* One flush white block: zero outer margin (doubled class beats the
   * .app-main > * margin rule), spacing comes from the inner padding. */
  margin-block: 0;
  margin-inline: calc(50% - 50vw);
  background: #ffffff;
  padding-block: 32px 24px;
}

/* Two-column layout per the joybuy /s?k= spec: 234px sidebar + results. */
.listing-layout {
  display: grid;
  grid-template-columns: 234px minmax(0, 1fr);
  gap: 24px;
  margin-block: 0;
}

/* Category trail: 首页 / 一级 / 二级 (current one is plain text). */
.listing-breadcrumb {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding-block: 0 var(--space-3);
  font-size: 0.875rem;
  color: var(--colour-text-secondary);
}

.listing-breadcrumb__link {
  color: var(--colour-text-secondary);
  text-decoration: none;
}

.listing-breadcrumb__link:hover {
  color: var(--colour-text);
  text-decoration: underline;
}

.listing-breadcrumb__sep {
  color: var(--colour-text-secondary);
}

.listing-breadcrumb__current {
  color: var(--colour-text);
  font-weight: 500;
}

/* Sibling category tiles of the current parent (same tile language as the
 * header dropdown); the open category keeps the white + outline state. */
.listing-category-strip {
  padding-block: 0 var(--space-5);
}

.listing-sidebar {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  align-self: start;
  position: sticky;
  top: calc(var(--header-height) + 40px + var(--space-4));
  /* The carousel row sits in the right column, so the filter column starts at
   * the top of the page like the source site. */
  padding-block: var(--space-5) 0;
}

.listing-sidebar__title {
  margin: 0;
  font-size: 1rem;
  font-weight: var(--font-weight-bold);
  color: var(--colour-text);
}

.filter-card {
  padding: var(--space-3);
  border-radius: 8px;
  background: var(--colour-surface);
}

/* Divider between the Category and Price sections (real sidebar). */
.filter-card + .filter-card {
  border-top: 1px solid var(--colour-border);
  border-radius: 0 0 8px 8px;
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
  background: #f7f7f7;
  color: #1a1a1a;
  font-weight: var(--font-weight-bold);
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
  margin-block: var(--space-4);
}

/* Sort sits on the left, right after the heading block (real site). */
.sort-control {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 16px;
  font-weight: var(--font-weight-medium);
  color: #1a1a1a;
}

.sort-control__trigger {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  min-width: 172px;
  white-space: nowrap;
  min-height: 40px;
  padding: 0 var(--space-3);
  border: 1px solid #1a1a1a;
  border-radius: var(--radius-sm);
  background: var(--colour-surface);
  color: #1a1a1a;
  font: inherit;
  font-size: 16px;
  cursor: pointer;
}

.sort-control__menu {
  position: absolute;
  top: calc(100% + 4px);
  left: auto;
  right: 0;
  z-index: var(--z-overlay);
  min-width: max-content;
  width: 100%;
  padding: var(--space-1) 0;
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-sm);
  background: var(--colour-surface);
  box-shadow: var(--shadow-overlay);
  list-style: none;
  margin: 0;
}

.sort-control__option {
  display: flex;
  align-items: center;
  width: 100%;
  min-height: 40px;
  padding: 0 var(--space-3);
  border: 0;
  background: transparent;
  text-align: left;
  font: inherit;
  font-size: 16px;
  color: #1a1a1a;
  cursor: pointer;
}

/* Hover/selected: light grey — never the OS blue. */
.sort-control__option:hover {
  background: var(--colour-hover);
}

.sort-control__option--active,
.sort-control__option--active:hover {
  background: var(--colour-surface-muted);
  font-weight: var(--font-weight-semibold);
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
