<script setup>
import { computed, ref } from 'vue'
import { useFetch, useRuntimeConfig } from '#imports'

// Reviews section for the product detail page: facets, rating filter,
// pagination and local media viewer. Unknown/degraded media renders as a
// broken-image state, never as a page error.
const props = defineProps({
  productId: {
    type: String,
    required: true,
  },
})

const config = useRuntimeConfig()
const activeRating = ref('')
const page = ref(1)

const baseUrl = computed(() =>
  import.meta.server
    ? `${config.apiBaseInternal}/products/${props.productId}/reviews`
    : `/api/v1/products/${props.productId}/reviews`,
)
const url = computed(() => {
  const search = new URLSearchParams()
  if (activeRating.value) search.set('rating', activeRating.value)
  if (page.value > 1) search.set('page', String(page.value))
  const query = search.toString()
  return query ? `${baseUrl.value}?${query}` : baseUrl.value
})

const { data } = await useFetch(url, {
  key: `reviews-${props.productId}-${activeRating.value}-${page.value}`,
})

const items = computed(() => (Array.isArray(data.value?.items) ? data.value.items : []))
const count = computed(() => data.value?.count ?? 0)
const totalPages = computed(() => data.value?.total_pages ?? 0)
const filteredTotal = computed(() => data.value?.filtered_total ?? count.value)
const distribution = computed(() => data.value?.distribution ?? {})

function filterBy(rating) {
  activeRating.value = activeRating.value === rating ? '' : rating
  page.value = 1
}

function goToPage(next) {
  if (next >= 1 && (totalPages.value === 0 || next <= totalPages.value)) {
    page.value = next
  }
}
</script>

<template>
  <section id="reviews" class="reviews" aria-labelledby="reviews-heading">
    <h2 id="reviews-heading">Customer reviews</h2>

    <div v-if="count > 0" class="reviews__summary row">
      <span class="reviews__average">{{ data?.average }} / 5</span>
      <span class="reviews__count">{{ count }} reviews</span>
    </div>

    <div v-if="count > 0" class="reviews__facets" role="group" aria-label="Filter by rating">
      <button
        v-for="star in [5, 4, 3, 2, 1]"
        :key="star"
        type="button"
        class="reviews__facet"
        :class="{ 'reviews__facet--active': activeRating === String(star) }"
        @click="filterBy(String(star))"
      >
        {{ star }} stars ({{ distribution[String(star)] || 0 }})
      </button>
    </div>

    <p v-if="filteredTotal !== count" class="reviews__filtered" role="status">
      Showing {{ filteredTotal }} of {{ count }} reviews.
    </p>

    <ul v-if="items.length > 0" class="reviews__list">
      <li v-for="review in items" :key="review.public_id" class="review">
        <header class="review__head">
          <span class="review__stars" aria-hidden="true">
            <span v-for="star in 5" :key="star" :class="{ filled: star <= review.rating }">★</span>
          </span>
          <span class="visually-hidden">{{ review.rating }} out of 5 stars</span>
          <strong class="review__title">{{ review.title || 'Review' }}</strong>
        </header>
        <p class="review__meta">
          {{ review.display_name }}
          <template v-if="review.reviewed_at">
            · {{ new Date(review.reviewed_at).toLocaleDateString('en-GB') }}
          </template>
          <template v-if="review.variant_text"> · {{ review.variant_text }}</template>
        </p>
        <p class="review__body">{{ review.body }}</p>

        <div v-if="review.media.length > 0" class="review__media">
          <figure v-for="(item, index) in review.media" :key="index">
            <img
              v-if="item.kind === 'IMAGE'"
              :src="item.url"
              :alt="`Review image ${index + 1}`"
              loading="lazy"
              @error="item.failed = true"
            />
            <video v-else-if="item.kind === 'VIDEO'" :src="item.url" controls preload="none" />
            <span v-if="item.failed" class="review__media-failed">Media unavailable</span>
          </figure>
        </div>
      </li>
    </ul>

    <p v-else class="reviews__empty" role="status">
      No reviews yet{{ activeRating ? ' for this star rating' : '' }}.
    </p>

    <nav v-if="totalPages > 1" class="reviews__pagination" aria-label="Reviews pagination">
      <button type="button" :disabled="page <= 1" @click="goToPage(page - 1)">Previous</button>
      <span>Page {{ page }} of {{ totalPages }}</span>
      <button type="button" :disabled="page >= totalPages" @click="goToPage(page + 1)">Next</button>
    </nav>
  </section>
</template>

<style scoped>
.reviews {
  margin-block: var(--space-8);
  padding: var(--space-6);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-lg);
  background: var(--colour-surface);
}

.reviews__average {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
}

.reviews__count {
  color: var(--colour-muted);
}

.reviews__facets {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-4);
}

.reviews__facet {
  min-height: 44px;
  padding: 0 var(--space-4);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-pill);
  background: var(--colour-canvas);
  cursor: pointer;
  font-size: var(--font-size-sm);
}

.reviews__facet--active {
  border-color: var(--colour-accent);
  color: var(--colour-accent);
  background: var(--colour-accent-soft);
  font-weight: var(--font-weight-semibold);
}

.reviews__filtered {
  margin-top: var(--space-3);
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}

.reviews__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  margin-top: var(--space-6);
}

.review {
  border-top: 1px solid var(--colour-border);
  padding-top: var(--space-4);
}

.review__head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.review__stars .filled {
  color: var(--colour-star);
}

.review__meta {
  margin-top: var(--space-1);
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}

.review__body {
  margin-top: var(--space-2);
  color: var(--colour-text-secondary);
}

.review__media {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-3);
}

.review__media img,
.review__media video {
  width: 96px;
  height: 96px;
  object-fit: cover;
  border-radius: var(--radius-md);
  border: 1px solid var(--colour-border);
}

.review__media-failed {
  color: var(--colour-muted);
  font-size: var(--font-size-xs);
}

.reviews__empty {
  margin-top: var(--space-6);
  color: var(--colour-muted);
}

.reviews__pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  margin-top: var(--space-6);
}

.reviews__pagination button {
  min-height: 44px;
  padding: 0 var(--space-5);
  border: 1px solid var(--colour-border-strong);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  cursor: pointer;
  font-weight: var(--font-weight-semibold);
}

.reviews__pagination button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
