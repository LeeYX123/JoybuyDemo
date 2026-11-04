<script setup>
const props = defineProps({
  payload: {
    type: Object,
    required: true,
  },
})
</script>

<template>
  <section class="cms-rich-text">
    <h2 class="cms-rich-text__heading">{{ props.payload.heading }}</h2>
    <p class="cms-rich-text__body">{{ props.payload.body }}</p>
  </section>
</template>

<style scoped>
.cms-rich-text {
  padding: var(--space-6);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-lg);
  background: var(--colour-surface);
}

.cms-rich-text__heading {
  font-size: var(--font-size-lg);
}

.cms-rich-text__body {
  margin-top: var(--space-3);
  color: var(--colour-text-secondary);
}
</style>
