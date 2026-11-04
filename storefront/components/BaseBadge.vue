<script setup>
const props = defineProps({
  tone: {
    type: String,
    default: 'neutral', // neutral | promo | success | warning | error | info
    validator: (value) =>
      ['neutral', 'promo', 'success', 'warning', 'error', 'info'].includes(value),
  },
})
</script>

<template>
  <span class="base-badge" :class="`base-badge--${props.tone}`">
    <slot />
  </span>
</template>

<style scoped>
.base-badge {
  display: inline-flex;
  align-items: center;
  min-height: 1.375rem;
  padding: 0 var(--space-2);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  white-space: nowrap;
}

.base-badge--neutral {
  color: var(--colour-text-secondary);
  background: var(--colour-surface-muted);
}

.base-badge--promo {
  color: var(--colour-white);
  background: var(--colour-promo);
}

.base-badge--success {
  color: var(--colour-success);
  background: var(--colour-success-soft);
}

.base-badge--warning {
  color: var(--colour-warning);
  background: var(--colour-warning-soft);
}

.base-badge--error {
  color: var(--colour-error);
  background: var(--colour-error-soft);
}

.base-badge--info {
  color: var(--colour-info);
  background: var(--colour-info-soft);
}
</style>
