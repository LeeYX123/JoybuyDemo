<script setup>
// Horizontal category carousel: one row of tiles, arrows appear when the row
// overflows, and the bottom nav bar shows a scroll-progress thumb between the
// two arrows (same language as the header dropdown's carousel on the source
// site). The channel landing page (13.1②) reuses it with `variant="channel"`
// and stacks tiles into `rows`-tall columns so multi-row modules still slide
// horizontally as one unit.
import { onBeforeUnmount, onMounted, ref } from 'vue'

import { useLocale } from '../composables/useLocale'

import CategoryTileGrid from './CategoryTileGrid.vue'

const { t } = useLocale()

const props = defineProps({
  items: {
    type: Array,
    default: () => [],
  },
  activeSlug: {
    type: String,
    default: '',
  },
  // 'default' (listing strip) or 'channel' (channel page tiles).
  variant: {
    type: String,
    default: 'default',
  },
  // Channel variant: name wrap width in CJK chars (6 → 140px, 9 → 194px).
  nameChars: {
    type: Number,
    default: 6,
  },
  // Channel variant: tiles per vertical stack (rows of the 13.1② table).
  rows: {
    type: Number,
    default: 1,
  },
  // Channel variant: tiles that must fit in one viewport row (8 / 6 / 5).
  perRow: {
    type: Number,
    default: 0,
  },
  // Channel variant: multi-row reading order ('row' | 'column').
  fill: {
    type: String,
    default: 'column',
  },
  // 批次 CA：分类页 carousel 第一张「全部」卡（见 CategoryTileGrid.allCard）。
  allCard: {
    type: Object,
    default: null,
  },
})

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
  <div class="category-carousel" :class="`category-carousel--${props.variant}`">
    <div ref="scroller" class="category-carousel__track" @scroll="sync">
      <CategoryTileGrid
        row
        :items="props.items"
        :active-slug="props.activeSlug"
        :variant="props.variant"
        :name-chars="props.nameChars"
        :columns="props.variant === 'channel' ? Math.max(props.rows, 1) : 0"
        :per-row="props.variant === 'channel' ? props.perRow : 0"
        :fill="props.fill"
        :all-card="props.allCard"
      />
    </div>
    <div v-if="overflowing" class="category-carousel__nav">
      <button
        class="category-carousel__arrow"
        type="button"
        :disabled="atStart"
        :aria-label="t('listing.prevCategories')"
        @click="scrollByPage(-1)"
      >
        <span aria-hidden="true">‹</span>
      </button>
      <span class="category-carousel__bar" role="presentation">
        <span
          class="category-carousel__thumb"
          :style="{ width: `${thumbWidth}%`, left: `${thumbLeft}%` }"
        />
      </span>
      <button
        class="category-carousel__arrow"
        type="button"
        :disabled="atEnd"
        :aria-label="t('listing.nextCategories')"
        @click="scrollByPage(1)"
      >
        <span aria-hidden="true">›</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.category-carousel {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.category-carousel__track {
  overflow-x: auto;
  overflow-y: hidden;
  scroll-behavior: smooth;
  /* The bar below is the scroll indicator; hide the native scrollbar. */
  scrollbar-width: none;
}

.category-carousel__track::-webkit-scrollbar {
  display: none;
}

/* Bottom nav: circular arrows either side of a thin progress track. */
.category-carousel__nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
}

.category-carousel__arrow {
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

.category-carousel__arrow:hover:not(:disabled) {
  border-color: var(--colour-border-strong);
}

.category-carousel__arrow:disabled {
  opacity: 0.35;
  cursor: default;
}

.category-carousel__bar {
  position: relative;
  width: 12rem;
  height: 3px;
  border-radius: var(--radius-pill);
  background: var(--colour-border);
}

.category-carousel__thumb {
  position: absolute;
  top: 0;
  height: 100%;
  border-radius: var(--radius-pill);
  background: var(--colour-text-secondary);
}

/* ---------------------------------------------------------------------- */
/* Channel variant (13.1②, measured 2026-11-23 §A.1): on the live channel */
/* page the arrows are an overlay ON the row (40×48, rgba(0,0,0,0.12)),    */
/* invisible until the module is hovered, and there is no progress bar.    */
/* ---------------------------------------------------------------------- */
.category-carousel--channel {
  position: relative;
  gap: 0;
}

.category-carousel--channel .category-carousel__nav {
  position: absolute;
  inset: 0;
  justify-content: space-between;
  gap: 0;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.category-carousel--channel:hover .category-carousel__nav,
.category-carousel--channel:focus-within .category-carousel__nav {
  opacity: 1;
}

.category-carousel--channel .category-carousel__arrow {
  width: 40px;
  height: 48px;
  border: 0;
  border-radius: 0;
  box-shadow: none;
  background: rgb(0 0 0 / 12%);
  color: #1a1a1a;
  font-size: 1.5rem;
  pointer-events: auto;
}

.category-carousel--channel .category-carousel__arrow:hover:not(:disabled) {
  border: 0;
  background: rgb(0 0 0 / 22%);
}

.category-carousel--channel .category-carousel__bar {
  display: none;
}
</style>
