<script setup>
import { computed, ref, watch } from 'vue'

import { useLocale } from '../composables/useLocale'

import CategoryTileGrid from './CategoryTileGrid.vue'
import { allCardImage } from '../utils/categoryAllCards'

// Categories dropdown (docs/12 §2): left column = 11 standard roots, right
// column = children of the selected root only (strict parent/child linkage).
// Rendered inside the header (no teleport) and anchored under the
// Categories trigger, left-aligned; hover keeps it open via the parent.
// Children render as Joybuy-style tile cards: one grey square per category
// with both the image and the name inside the box (local manifest asset,
// downloaded from the source site).
const props = defineProps({
  open: {
    type: Boolean,
    default: false,
  },
  categories: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['close'])

const { t, categoryName } = useLocale()

const selectedIndex = ref(0)
const selectedRoot = computed(() => props.categories[selectedIndex.value] || null)

// 批次 CA：右侧二级区域第一张固定为「查看全部 <一级品类名>」，图片取常量
// （不随接口数据变化），点击进入该一级品类的全部商品页。
const allCard = computed(() => {
  const root = selectedRoot.value
  if (!root) return null
  return {
    label: `${t('categoryPanel.viewAll')} ${categoryName(root)}`,
    image: allCardImage(root.slug),
    to: `/c/${root.slug}`,
    active: false,
  }
})

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen && selectedIndex.value >= props.categories.length) {
      selectedIndex.value = 0
    }
  },
)

function select(index) {
  selectedIndex.value = index
}
</script>

<template>
  <div v-if="open" class="category-panel" role="dialog" aria-modal="false">
    <div class="category-panel__card">
      <button class="category-panel__close" type="button" @click="emit('close')">
        <span aria-hidden="true">×</span>
        <span class="visually-hidden">{{ t('categoryPanel.close') }}</span>
      </button>
      <div class="category-panel__body">
        <ul class="category-panel__roots">
          <li v-for="(root, index) in categories" :key="root.slug">
            <button
              class="category-panel__root"
              :class="{ 'category-panel__root--active': index === selectedIndex }"
              type="button"
              @mouseenter="select(index)"
              @focus="select(index)"
              @click="select(index)"
            >
              {{ categoryName(root) }}
            </button>
          </li>
        </ul>
        <div class="category-panel__detail">
          <p v-if="selectedRoot" class="category-panel__heading">
            {{ categoryName(selectedRoot) }}
          </p>
          <CategoryTileGrid
            v-if="selectedRoot?.children?.length"
            class="category-panel__children"
            :items="selectedRoot.children"
            :all-card="allCard"
            @select="emit('close')"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Anchored dropdown: flush under the trigger, left-aligned with it. */
.category-panel {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: var(--z-overlay);
}

.category-panel__card {
  position: relative;
  display: flex;
  flex-direction: column;
  /* 896px keeps four tile columns visible (the source site fits 4 × 136px +
   * 3 × 8px gaps in 568px of tile area). */
  width: min(56rem, calc(100vw - 4rem));
  max-height: min(42rem, calc(100vh - 8rem));
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-lg);
  background: var(--colour-surface);
  /* 需求 13.5-1：下拉阴影按真站加大。真站打开态 CSS 被风控挡（见
     var/header_footer_cart_20261119/measurement.md §1.5），按真站自家 sticky
     阴影 token（0 2px 12px rgba(0,0,0,.039), 0 4px 6px rgba(0,0,0,.059)）同族放大。 */
  box-shadow:
    rgb(0 0 0 / 8%) 0 4px 24px 0,
    rgb(0 0 0 / 6%) 0 12px 48px 0;
  overflow: hidden;
}

.category-panel__close {
  position: absolute;
  top: 0.5rem;
  right: 0.75rem;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  height: 2.25rem;
  border: 0;
  border-radius: var(--radius-pill);
  cursor: pointer;
  background: transparent;
  color: var(--colour-text-secondary);
  font-size: 1.5rem;
  line-height: 1;
}

.category-panel__close:hover {
  background: var(--colour-hover);
}

.category-panel__body {
  display: grid;
  grid-template-columns: 15rem 1fr;
  min-height: 0;
  flex: 1;
}

/* Left rail: 184px column, 36px rows with 16px gaps; label 14px. Hover and
 * the selected row both use the #F7F7F7 pill with bold black text (real-site
 * behaviour — no accent red). */
.category-panel__roots {
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: var(--space-4) 0 var(--space-4) var(--space-4);
  background: var(--colour-surface);
}

.category-panel__root {
  display: flex;
  align-items: center;
  width: 184px;
  min-height: 36px;
  padding: 8px 12px;
  border: 0;
  border-radius: 8px;
  cursor: pointer;
  background: transparent;
  text-align: left;
  font: inherit;
  font-size: 14px;
  font-weight: var(--font-weight-regular);
  color: var(--colour-text);
  line-height: var(--line-height-tight);
}

.category-panel__root:hover,
.category-panel__root--active {
  background: #f7f7f7;
  font-weight: var(--font-weight-semibold);
  color: var(--colour-text);
}

.category-panel__detail {
  overflow-y: auto;
  padding: var(--space-4) var(--space-5);
}

.category-panel__heading {
  margin: 0 0 var(--space-4);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}

@media (max-width: 48rem) {
  .category-panel__body {
    grid-template-columns: 11rem 1fr;
  }
}
</style>
