<script setup>
import { computed } from 'vue'
const props = defineProps({
  payload: {
    type: Object,
    required: true,
  },
})

const theme = computed(() =>
  ['primary', 'dark'].includes(props.payload.theme) ? props.payload.theme : 'primary',
)
</script>

<template>
  <section class="cms-hero" :class="`cms-hero--${theme}`">
    <div class="cms-hero__content">
      <h2 class="cms-hero__heading">{{ props.payload.heading }}</h2>
      <p v-if="props.payload.subheading" class="cms-hero__subheading">
        {{ props.payload.subheading }}
      </p>
      <NuxtLink
        v-if="props.payload.cta_label && props.payload.cta_href"
        class="cms-hero__cta"
        :to="props.payload.cta_href"
      >
        {{ props.payload.cta_label }}
      </NuxtLink>
    </div>
  </section>
</template>

<style scoped>
.cms-hero {
  border-radius: var(--radius-lg);
  padding: var(--space-10) var(--space-8);
  color: var(--colour-white);
  background: var(--colour-accent);
}

.cms-hero--dark {
  background: var(--colour-text);
}

.cms-hero__heading {
  font-size: var(--font-size-3xl);
}

.cms-hero__subheading {
  max-width: 40rem;
  margin-top: var(--space-3);
  opacity: 0.9;
}

.cms-hero__cta {
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  margin-top: var(--space-6);
  padding: 0 var(--space-6);
  border-radius: var(--radius-pill);
  background: var(--colour-white);
  color: var(--colour-text);
  font-weight: var(--font-weight-semibold);
  text-decoration: none;
}

.cms-hero__cta:hover {
  background: var(--colour-surface-muted);
}

@media (max-width: 30rem) {
  .cms-hero {
    padding: var(--space-8) var(--space-5);
  }

  .cms-hero__heading {
    font-size: var(--font-size-2xl);
  }
}
</style>
