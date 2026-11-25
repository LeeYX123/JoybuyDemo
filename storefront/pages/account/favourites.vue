<script setup>
import { computed } from 'vue'
import { useHead } from '#imports'
import { useLocale } from '../../composables/useLocale'
import { useMobileView } from '../../composables/useMobileView'

const { t } = useLocale()
const { isMobileHost } = useMobileView()

import { useActivityList } from '~/composables/useActivityList'
import { useWishlist } from '../../composables/useWishlist'
import { formatDisplayPrice } from '../../utils/display'
import AccountShell from '../../components/account/AccountShell.vue'

// Buyer favourites: list, remove, empty state and pagination.
// useActivityList is async (SSR fetch inside); awaiting it is required —
// without the await the destructured refs are undefined (latent desktop bug,
// fixed here because the mobile branch needs the same refs).
const { items, total, totalPages, page, goToPage, clientDelete } =
  await useActivityList('favourites')
const { removeLocal } = useWishlist()

function removeItem(publicId) {
  // Keep the heart state in sync with the list once the row is removed.
  removeLocal(publicId)
  clientDelete(publicId)
}

// Mobile wishlist cards (docs/20 §5.3): same 2-column card style as the
// mobile listing; removal reuses the shared removeItem above.
const mobileItems = computed(() =>
  items.value.map((item) => ({
    spuId: item.spu_public_id,
    title: item.title,
    price: formatDisplayPrice(item.price_min) ?? '',
    image: item.image_path || '',
  })),
)

useHead(() => ({ title: t('accountMenu.favourites') }))
</script>

<template>
  <!-- ADR 0001: mobile host renders the docs/20 §5.3 mobile wishlist;
       the desktop AccountShell below is untouched. -->
  <MobileWishlist v-if="isMobileHost" :items="mobileItems" @remove="removeItem" />
  <!-- Desktop: same shell frame as the other account modules (real
       /profile/wishlist page has the breadcrumb + rail layout). -->
  <AccountShell v-else :title="t('accountMenu.favourites')">
    <p v-if="total === 0" class="activity__empty" role="status">
      {{ t('account.emptyWishlist') }}
    </p>

    <template v-else>
      <!-- Desktop wishlist cards follow the real /profile/wishlist page
           (resurvey 2026-11-25): product image + title + price in a card
           grid. We only render fields we actually have (no brand/Plus Price/
           delivery badges — those need data this repo doesn't track). -->
      <ul class="fav-grid">
        <li v-for="item in items" :key="item.spu_public_id" class="fav-card">
          <div class="fav-card__media">
            <NuxtLink
              class="fav-card__media-link"
              :to="`/p/${item.spu_public_id}`"
              tabindex="-1"
              aria-hidden="true"
            >
              <img v-if="item.image_path" :src="item.image_path" alt="" loading="lazy" />
              <span v-else class="fav-card__placeholder" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="28" height="28">
                  <path
                    d="M12 2 3 7v10l9 5 9-5V7l-9-5Zm0 2.3L18.6 8 12 11.7 5.4 8 12 4.3ZM5 9.7l6 3.3v6.4l-6-3.3V9.7Zm8 9.7V13l6-3.3v6.4l-6 3.3Z"
                    fill="currentColor"
                  />
                </svg>
              </span>
            </NuxtLink>
            <button
              type="button"
              class="fav-card__remove"
              :aria-label="t('cart.remove')"
              @click="removeItem(item.spu_public_id)"
            >
              <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
                <path
                  d="M12 20.3C8.4 17.7 3 13.9 3 9.5A4.5 4.5 0 0 1 12 7a4.5 4.5 0 0 1 9 2.5c0 4.4-5.4 8.2-9 10.8Zm-1.2-12-.9.9 2.1 2.1-2.1 2.1.9.9 2.1-2.1 2.1 2.1.9-.9-2.1-2.1 2.1-2.1-.9-.9-2.1 2.1-2.1-2.1Z"
                  fill="currentColor"
                  fill-rule="evenodd"
                />
              </svg>
            </button>
          </div>
          <NuxtLink class="fav-card__title" :to="`/p/${item.spu_public_id}`">
            {{ item.title }}
          </NuxtLink>
          <span class="fav-card__price">
            {{ formatDisplayPrice(item.price_min) ?? 'Price unavailable' }}
          </span>
        </li>
      </ul>

      <nav v-if="totalPages > 1" class="activity__pagination" :aria-label="t('pagination.label')">
        <button type="button" :disabled="page <= 1" @click="goToPage(page - 1)">
          {{ t('pagination.previous') }}
        </button>
        <span>Page {{ page }} of {{ totalPages }}</span>
        <button type="button" :disabled="page >= totalPages" @click="goToPage(page + 1)">
          {{ t('pagination.next') }}
        </button>
      </nav>
    </template>
  </AccountShell>
</template>

<style scoped>
.activity__empty {
  margin: var(--space-4) 0 0;
  color: var(--colour-muted);
}

.fav-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
  gap: var(--space-6) var(--space-5);
  margin: var(--space-2) 0 0;
  padding: 0;
  list-style: none;
}

.fav-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.fav-card__media {
  position: relative;
  border-radius: var(--radius-md);
  background: var(--colour-surface-soft);
  overflow: hidden;
}

.fav-card__media-link {
  display: block;
  aspect-ratio: 1;
}

.fav-card__media img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  mix-blend-mode: multiply;
}

.fav-card__placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--colour-border-strong);
}

.fav-card__remove {
  position: absolute;
  top: var(--space-2);
  right: var(--space-2);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: var(--radius-pill);
  background: rgb(255 255 255 / 0.9);
  color: var(--colour-muted);
  cursor: pointer;
}

.fav-card__remove:hover {
  color: var(--colour-accent);
}

.fav-card__title {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 2.6em;
  color: var(--colour-text);
  font-size: var(--font-size-md);
  line-height: 1.3;
  text-decoration: none;
}

.fav-card__title:hover {
  color: var(--colour-accent);
}

.fav-card__price {
  color: var(--colour-accent);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
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
