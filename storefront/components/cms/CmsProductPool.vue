<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useLocale } from '../../composables/useLocale'

const { t } = useLocale()

const props = defineProps({
  payload: {
    type: Object,
    required: true,
  },
})

const products = computed(() =>
  Array.isArray(props.payload.products) ? props.payload.products : [],
)

// Channel floors on the real site show 20 cards in 5 columns; the CMS home
// floors keep 4. Default stays 4 so existing pages are unchanged.
const columns = computed(() => Number(props.payload.columns) || 4)

// 13.1④ (2026-11-19): channel module floors render a single row with the
// overflow sliding horizontally (real site: 194px cards, 20px gap, 6 visible,
// no card border). `single_row` opts the pool into that scroller; `flat`
// drops the card outline. Home CMS floors keep the grid + outline.
const singleRow = computed(() => Boolean(props.payload.single_row))
const flat = computed(() => singleRow.value || Boolean(props.payload.flat))

// Real site: 6 cards per row in the 1264px container (measurement.md §2).
const rowColumns = computed(() => Number(props.payload.row_columns) || 6)

const scroller = ref(null)
const overflowing = ref(false)
const atStart = ref(true)
const atEnd = ref(false)
const thumbWidth = ref(100)
const thumbLeft = ref(0)

let resizeObserver = null

function sync() {
  const el = scroller.value
  if (!el) return
  const max = el.scrollWidth - el.clientWidth
  overflowing.value = max > 1
  atStart.value = el.scrollLeft <= 1
  atEnd.value = el.scrollLeft >= max - 1
  if (el.scrollWidth > 0) {
    const ratio = el.clientWidth / el.scrollWidth
    thumbWidth.value = Math.max(12, Math.round(ratio * 100))
    const travel = el.scrollWidth - el.clientWidth
    thumbLeft.value =
      travel > 0 ? Math.round((el.scrollLeft / travel) * (100 - thumbWidth.value)) : 0
  }
}

function scrollByPage(direction) {
  const el = scroller.value
  if (!el) return
  el.scrollBy({ left: direction * Math.round(el.clientWidth * 0.9), behavior: 'smooth' })
}

onMounted(() => {
  if (!singleRow.value) return
  sync()
  if (typeof ResizeObserver !== 'undefined' && scroller.value) {
    resizeObserver = new ResizeObserver(sync)
    resizeObserver.observe(scroller.value)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
})
</script>

<template>
  <section class="cms-pool" :class="{ 'cms-pool--flat': flat }" :aria-label="props.payload.title">
    <div class="cms-pool__head">
      <h2 class="cms-pool__title">{{ props.payload.title }}</h2>
      <NuxtLink v-if="props.payload.href" class="cms-pool__more" :to="props.payload.href">
        {{ props.payload.more_label || t('cms.viewAll') }}
      </NuxtLink>
    </div>

    <div
      v-if="singleRow"
      ref="scroller"
      class="cms-pool__scroller"
      :style="{ '--cms-pool-row-columns': rowColumns }"
      @scroll="sync"
    >
      <ul class="cms-pool__row">
        <li v-for="(product, index) in products" :key="product.public_id || index">
          <ProductCard :product="product" />
        </li>
      </ul>
    </div>
    <ul v-else class="cms-pool__grid" :style="{ '--cms-pool-columns': columns }">
      <li v-for="(product, index) in products" :key="product.public_id || index">
        <ProductCard :product="product" />
      </li>
    </ul>

    <div v-if="singleRow && overflowing" class="cms-pool__nav">
      <button
        class="cms-pool__arrow"
        type="button"
        :disabled="atStart"
        :aria-label="t('listing.prevCategories')"
        @click="scrollByPage(-1)"
      >
        <span aria-hidden="true">‹</span>
      </button>
      <span class="cms-pool__bar" role="presentation">
        <span class="cms-pool__thumb" :style="{ width: `${thumbWidth}%`, left: `${thumbLeft}%` }" />
      </span>
      <button
        class="cms-pool__arrow"
        type="button"
        :disabled="atEnd"
        :aria-label="t('listing.nextCategories')"
        @click="scrollByPage(1)"
      >
        <span aria-hidden="true">›</span>
      </button>
    </div>
  </section>
</template>

<style scoped>
.cms-pool__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-4);
}

.cms-pool__more {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  color: var(--colour-accent);
  font-weight: var(--font-weight-semibold);
  text-decoration: none;
}

.cms-pool__more:hover {
  text-decoration: underline;
}

.cms-pool__grid {
  display: grid;
  grid-template-columns: repeat(var(--cms-pool-columns, 4), minmax(0, 1fr));
  gap: var(--space-4);
  margin-top: var(--space-4);
}

/* Flat mode (13.1④): no card outline anywhere in this pool. */
.cms-pool--flat .product-card,
.cms-pool--flat :deep(.product-card) {
  border: 0;
  padding: 0;
  background: transparent;
}

/* Single-row scroller (13.1④): 6 cards visible, 20px gaps, no native
   scrollbar — the progress bar below is the indicator. */
.cms-pool__scroller {
  overflow-x: auto;
  overflow-y: hidden;
  scroll-behavior: smooth;
  scrollbar-width: none;
  margin-top: var(--space-4);
}

.cms-pool__scroller::-webkit-scrollbar {
  display: none;
}

.cms-pool__row {
  display: flex;
  flex-wrap: nowrap;
  gap: 20px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.cms-pool__row > li {
  flex: 0 0
    calc((100% - (var(--cms-pool-row-columns, 6) - 1) * 20px) / var(--cms-pool-row-columns, 6));
}

.cms-pool__row :deep(.product-card) {
  border: 0;
  padding: 0;
  background: transparent;
}

/* Bottom nav: circular arrows either side of a thin progress track (same
   language as CategoryTileCarousel). */
.cms-pool__nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  margin-top: var(--space-3);
}

.cms-pool__arrow {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  padding: 0;
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-pill);
  background: var(--colour-surface);
  box-shadow: var(--shadow-card);
  color: var(--colour-text);
  font-size: 1.125rem;
  line-height: 1;
  cursor: pointer;
}

.cms-pool__arrow:hover:not(:disabled) {
  border-color: var(--colour-border-strong);
}

.cms-pool__arrow:disabled {
  opacity: 0.35;
  cursor: default;
}

.cms-pool__bar {
  position: relative;
  width: 12rem;
  height: 3px;
  border-radius: var(--radius-pill);
  background: var(--colour-border);
}

.cms-pool__thumb {
  position: absolute;
  top: 0;
  height: 100%;
  border-radius: var(--radius-pill);
  background: var(--colour-text-secondary);
}

@media (max-width: 80rem) {
  .cms-pool__grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 48rem) {
  .cms-pool__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 30rem) {
  .cms-pool__grid {
    grid-template-columns: 1fr;
  }
}
</style>
