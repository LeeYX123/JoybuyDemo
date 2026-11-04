<script setup>
const props = defineProps({
  payload: {
    type: Object,
    required: true,
  },
})
</script>

<template>
  <NuxtLink class="cms-banner" :to="props.payload.href" :aria-label="props.payload.alt">
    <BaseBadge :tone="props.payload.theme === 'info' ? 'info' : 'promo'">
      {{ props.payload.label || 'Offer' }}
    </BaseBadge>
    <span class="cms-banner__text">{{ props.payload.alt || props.payload.label }}</span>
  </NuxtLink>
</template>

<style scoped>
.cms-banner {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-height: 56px;
  padding: var(--space-3) var(--space-5);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-lg);
  background: var(--colour-surface);
  text-decoration: none;
  font-weight: var(--font-weight-semibold);
}

.cms-banner:hover {
  border-color: var(--colour-border-strong);
  box-shadow: var(--shadow-card);
}

.cms-banner__text {
  color: var(--colour-text-secondary);
  font-size: var(--font-size-sm);
}
</style>
