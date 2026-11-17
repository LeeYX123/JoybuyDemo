<script setup>
import { useLocale } from '../../composables/useLocale'

// Joybuy order/returns/addresses tabs (measured 2026-11-16): each tab is a
// 60x32 text button, 18px, inactive 500/#505259, active 700/#1A1A1A, with a
// 3px #19191B underline under the label only and 24px between tabs.
// Exposed as a proper tablist for keyboard and screen readers.
defineProps({
  tabs: {
    type: Array,
    required: true,
  },
  modelValue: {
    type: String,
    required: true,
  },
})

const emit = defineEmits(['update:modelValue'])
const { t } = useLocale()

function select(key) {
  emit('update:modelValue', key)
}
</script>

<template>
  <div class="account-tabs" role="tablist" :aria-label="t('account.tabs')">
    <button
      v-for="tab in tabs"
      :key="tab.key"
      class="account-tabs__tab"
      :class="{ 'account-tabs__tab--active': tab.key === modelValue }"
      type="button"
      role="tab"
      :aria-selected="tab.key === modelValue"
      @click="select(tab.key)"
    >
      <span class="account-tabs__label">
        {{ tab.label }}
        <span v-if="tab.count != null" class="account-tabs__count">{{ tab.count }}</span>
      </span>
    </button>
  </div>
</template>

<style scoped>
.account-tabs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-6);
}

.account-tabs__tab {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 60px;
  height: 32px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #505259;
  font-size: 18px;
  font-weight: var(--font-weight-medium);
  cursor: pointer;
}

.account-tabs__label {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  white-space: nowrap;
}

.account-tabs__label::after {
  position: absolute;
  bottom: -6px;
  left: 50%;
  width: 100%;
  height: 3px;
  border-radius: 1px;
  background: transparent;
  content: '';
  transform: translateX(-50%);
}

.account-tabs__tab:hover {
  color: #990915;
}

.account-tabs__tab--active {
  color: #1a1a1a;
  font-weight: var(--font-weight-bold);
}

.account-tabs__tab--active .account-tabs__label::after {
  background: #19191b;
}

.account-tabs__count {
  color: inherit;
  font-size: var(--font-size-sm);
}
</style>
