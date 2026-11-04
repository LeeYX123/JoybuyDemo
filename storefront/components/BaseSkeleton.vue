<script setup>
// Loading placeholder; rendered as a neutral shimmer block.
const props = defineProps({
  variant: {
    type: String,
    default: 'text', // text | block | circle
    validator: (value) => ['text', 'block', 'circle'].includes(value),
  },
})
</script>

<template>
  <span class="base-skeleton" :class="`base-skeleton--${props.variant}`" aria-hidden="true" />
</template>

<style scoped>
.base-skeleton {
  display: block;
  border-radius: var(--radius-sm);
  background: linear-gradient(
    100deg,
    var(--colour-surface-muted) 40%,
    var(--colour-border) 50%,
    var(--colour-surface-muted) 60%
  );
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.4s ease infinite;
}

.base-skeleton--text {
  width: 100%;
  height: 0.875rem;
}

.base-skeleton--block {
  width: 100%;
  aspect-ratio: 1;
  border-radius: var(--radius-md);
}

.base-skeleton--circle {
  width: 2.5rem;
  height: 2.5rem;
  border-radius: var(--radius-pill);
}

@keyframes skeleton-shimmer {
  from {
    background-position: 120% 0;
  }

  to {
    background-position: -80% 0;
  }
}
</style>
