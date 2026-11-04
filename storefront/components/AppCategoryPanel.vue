<script setup>
import { computed, ref, watch } from 'vue'

import { useLocale } from '../composables/useLocale'

// Categories dropdown (docs/12 §2): left column = 11 standard roots, right
// column = children of the selected root only (strict parent/child linkage).
// Rendered inside the header (no teleport) and anchored under the
// Categories trigger, left-aligned; hover keeps it open via the parent.
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
          <ul v-if="selectedRoot?.children?.length" class="category-panel__children">
            <li v-for="child in selectedRoot.children" :key="child.slug">
              <NuxtLink
                class="category-panel__child"
                :to="`/c/${child.slug}`"
                @click="emit('close')"
              >
                {{ categoryName(child) }}
              </NuxtLink>
            </li>
          </ul>
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
  width: min(800px, calc(100vw - 4rem));
  max-height: min(42rem, calc(100vh - 8rem));
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-lg);
  background: var(--colour-surface);
  box-shadow: var(--shadow-overlay);
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

.category-panel__children {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(10rem, 1fr));
  gap: var(--space-2);
}

.category-panel__child {
  display: inline-flex;
  align-items: center;
  min-height: 2.75rem;
  padding: 0 var(--space-3);
  border-radius: var(--radius-md);
  text-decoration: none;
  font-size: var(--font-size-sm);
  color: var(--colour-text-secondary);
}

.category-panel__child:hover {
  background: var(--colour-hover);
  color: var(--colour-accent);
}

@media (max-width: 48rem) {
  .category-panel__body {
    grid-template-columns: 11rem 1fr;
  }
}
</style>
