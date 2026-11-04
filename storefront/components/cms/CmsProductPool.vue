<script setup>
import { computed } from 'vue'

const props = defineProps({
  payload: {
    type: Object,
    required: true,
  },
})

const products = computed(() =>
  Array.isArray(props.payload.products) ? props.payload.products : [],
)
</script>

<template>
  <section class="cms-pool" :aria-label="props.payload.title">
    <div class="cms-pool__head">
      <h2 class="cms-pool__title">{{ props.payload.title }}</h2>
      <NuxtLink v-if="props.payload.href" class="cms-pool__more" :to="props.payload.href">
        View all
      </NuxtLink>
    </div>

    <ul class="cms-pool__grid">
      <li v-for="(product, index) in products" :key="product.public_id || index">
        <ProductCard :product="product" />
      </li>
    </ul>
  </section>
</template>

<style scoped>
.cms-pool__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-4);
}

.cms-pool__more {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  color: var(--colour-accent);
  font-weight: var(--font-weight-semibold);
  text-decoration: none;
}

.cms-pool__more:hover {
  text-decoration: underline;
}

.cms-pool__grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-4);
  margin-top: var(--space-4);
}

.product-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  height: 100%;
  padding: var(--space-3);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-lg);
  background: var(--colour-surface);
}

.product-card__title {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
}

.product-card__price {
  color: var(--colour-accent);
  font-weight: var(--font-weight-bold);
  font-size: var(--font-size-lg);
}

.product-card__meta {
  min-height: 1.25rem;
}

@media (max-width: 80rem) {
  .cms-pool__grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 48rem) {
  .cms-pool__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 30rem) {
  .cms-pool__grid {
    grid-template-columns: 1fr;
  }
}
</style>
