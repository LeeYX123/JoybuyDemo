<script setup>
import { computed } from 'vue'

// Rating stars for product cards and reviews (display-only in WP-20).
const props = defineProps({
  rating: {
    type: Number,
    default: 0,
  },
  count: {
    type: Number,
    default: 0,
  },
  showCount: {
    type: Boolean,
    default: false,
  },
})

const filledStars = computed(() => Math.round(Math.min(5, Math.max(0, props.rating))))
const formattedCount = computed(() => props.count.toLocaleString('en-GB'))
</script>

<template>
  <span class="rating-stars" role="img" :aria-label="`Rated ${props.rating} out of 5`">
    <span class="rating-stars__icons" aria-hidden="true">
      <span
        v-for="star in 5"
        :key="star"
        class="star"
        :class="{ 'star--filled': star <= filledStars }"
        >★</span
      >
    </span>
    <span v-if="props.showCount" class="rating-stars__count">({{ formattedCount }})</span>
  </span>
</template>

<style scoped>
.rating-stars {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
}

.rating-stars__icons {
  display: inline-flex;
  gap: 1px;
}

.star {
  color: var(--colour-border-strong);
  font-size: var(--font-size-md);
}

.star--filled {
  color: var(--colour-star);
}

.rating-stars__count {
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}
</style>
