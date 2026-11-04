<script setup>
import { useHead } from '#imports'

import { useActivityList } from '~/composables/useActivityList'
import { formatDisplayPrice } from '../../utils/display'

// Buyer favourites: list, remove, empty state and pagination.
const { items, total, totalPages, page, goToPage, clientDelete } =
  useActivityList('recently-viewed')

function removeItem(publicId) {
  clientDelete(publicId)
}

useHead({ title: 'Recently viewed' })
</script>

<template>
  <AppContainer narrow>
    <section class="activity" aria-labelledby="activity-title">
      <h1 id="activity-title">Recently viewed</h1>

      <p v-if="total === 0" class="activity__empty" role="status">
        Nothing here yet. Products you open while signed in will appear automatically.
      </p>

      <template v-else>
        <ul class="activity__list">
          <li v-for="item in items" :key="item.spu_public_id" class="activity__row">
            <div class="activity__info">
              <NuxtLink :to="`/p/${item.spu_public_id}`" class="activity__title">
                {{ item.title }}
              </NuxtLink>
              <span class="activity__meta">
                {{ formatDisplayPrice(item.price_min) ?? 'Price unavailable' }}
              </span>
            </div>
            <button type="button" class="activity__remove" @click="removeItem(item.spu_public_id)">
              Remove
            </button>
          </li>
        </ul>

        <nav v-if="totalPages > 1" class="activity__pagination" aria-label="Pagination">
          <button type="button" :disabled="page <= 1" @click="goToPage(page - 1)">Previous</button>
          <span>Page {{ page }} of {{ totalPages }}</span>
          <button type="button" :disabled="page >= totalPages" @click="goToPage(page + 1)">
            Next
          </button>
        </nav>
      </template>
    </section>
  </AppContainer>
</template>

<style scoped>
.activity {
  margin-block: var(--space-10);
}

.activity__empty {
  margin-top: var(--space-5);
  color: var(--colour-muted);
}

.activity__list {
  display: flex;
  flex-direction: column;
  margin-top: var(--space-5);
}

.activity__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  border-top: 1px solid var(--colour-border);
  padding-block: var(--space-3);
}

.activity__title {
  color: var(--colour-text);
  font-weight: var(--font-weight-semibold);
  text-decoration: none;
}

.activity__title:hover {
  color: var(--colour-accent);
}

.activity__meta {
  display: block;
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}

.activity__remove {
  min-height: 44px;
  padding: 0 var(--space-4);
  border: 1px solid var(--colour-border-strong);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  cursor: pointer;
}

.activity__pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  margin-top: var(--space-6);
}

.activity__pagination button {
  min-height: 44px;
  padding: 0 var(--space-4);
  border: 1px solid var(--colour-border-strong);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  cursor: pointer;
}

.activity__pagination button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
