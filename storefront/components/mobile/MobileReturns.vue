<script setup>
import { useLocale } from '../../composables/useLocale'

// Mobile after-sales (docs/20 §5.5): the real-site tab row (all / in progress
// / completed / canceled — same keys as the desktop page) plus an honest
// empty card (no buyer after-sales backend yet, same as desktop). Presenta-
// tional; the tab state lives in pages/account/returns.vue.
defineProps({
  tabs: { type: Array, default: () => [] },
  activeTab: { type: String, default: 'all' },
})

const emit = defineEmits(['tab', 'back'])

const { t } = useLocale()
</script>

<template>
  <div class="m-returns">
    <MobilePageHeader :title="t('accountMenu.returns')" @back="emit('back')" />

    <!-- Tab row (docs/20 §0: 16px selected 700 + 2px black underline). -->
    <nav class="m-returns__tabs" :aria-label="t('account.tabs')">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="m-returns__tab"
        :class="{ 'm-returns__tab--active': tab.key === activeTab }"
        type="button"
        @click="emit('tab', tab.key)"
      >
        {{ tab.label }}
      </button>
    </nav>

    <!-- Empty state: same copy as the desktop returns.empty. -->
    <div class="m-returns__empty" role="status">
      <p class="m-returns__empty-text">{{ t('returns.empty') }}</p>
    </div>
  </div>
</template>

<style scoped>
.m-returns {
  min-height: 60vh;
  padding-bottom: 24px;
  background: #f5f6fa;
}

.m-returns__tabs {
  display: flex;
  overflow-x: auto;
  background: #ffffff;
  border-bottom: 1px solid #f0f1f2;
  scrollbar-width: none;
}

.m-returns__tabs::-webkit-scrollbar {
  display: none;
}

.m-returns__tab {
  min-height: 44px;
  flex-shrink: 0;
  padding: 0 14px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: #1a1a1a;
  font: inherit;
  font-size: 16px;
  white-space: nowrap;
  cursor: pointer;
}

.m-returns__tab--active {
  font-weight: var(--font-weight-bold);
  border-bottom-color: #1a1a1a;
}

.m-returns__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin: 24px 16px;
  padding: 40px 16px;
  border-radius: 12px;
  background: #ffffff;
}

.m-returns__empty-text {
  margin: 0;
  color: #1a1a1a;
  font-size: 16px;
  font-weight: var(--font-weight-semibold);
}
</style>
