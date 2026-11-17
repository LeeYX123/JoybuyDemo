<script setup>
// Horizontal category carousel for the category results page: one row of
// tiles, arrows appear when the row overflows, and the bottom nav bar shows a
// scroll-progress thumb between the two arrows (same language as the header
// dropdown's carousel on the source site).
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
  <div class="category-carousel">
    <div ref="scroller" class="category-carousel__track" @scroll="sync">
      <CategoryTileGrid row :items="props.items" :active-slug="props.activeSlug" />
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
</style>
