<script setup>
import { useLocale } from '../../composables/useLocale'

// Mobile wishlist (docs/20 §5.3): 2-column product grid using the same card
// style as MobileListing (white 12px-radius cards, 1:1 cover, 14px two-line
// title, 16px/700 red price) plus a remove action per card. Data comes from
// the same useActivityList('favourites') loader as the desktop page; removal
// is emitted so the page keeps the useWishlist toggle in sync (ADR 0001).
defineProps({
  items: { type: Array, default: () => [] },
})

const emit = defineEmits(['remove', 'back'])

const { t } = useLocale()

const imgFallback = '/images/logo.png'

function imgOf(item) {
  const src = item?.image
  return typeof src === 'string' && src ? src : imgFallback
}
</script>

<template>
  <div class="m-wish">
    <MobilePageHeader :title="t('account.favourites')" @back="emit('back')" />

    <!-- Empty state: same copy as the desktop account.emptyWishlist. -->
    <div v-if="items.length === 0" class="m-wish__empty" role="status">
      <p class="m-wish__empty-title">{{ t('account.emptyWishlist') }}</p>
      <NuxtLink class="m-wish__shopping" to="/">{{ t('cart.goShopping') }}</NuxtLink>
    </div>

    <ul v-else class="m-wish__grid">
      <li v-for="item in items" :key="item.spuId" class="m-wish__cell">
        <NuxtLink class="m-wish__card" :to="`/p/${item.spuId}`">
          <img class="m-wish__img" :src="imgOf(item)" alt="" loading="lazy" />
          <span class="m-wish__name">{{ item.title }}</span>
          <span class="m-wish__price">{{ item.price }}</span>
        </NuxtLink>
        <button
          type="button"
          class="m-wish__remove"
          :aria-label="t('cart.remove')"
          @click="emit('remove', item.spuId)"
        >
          {{ t('cart.remove') }}
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.m-wish {
  min-height: 60vh;
  padding: 0 0 24px;
  background: #f5f6fa;
}

/* Empty state */
.m-wish__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin: 24px 16px;
  padding: 40px 16px;
  border-radius: 12px;
  background: #ffffff;
}

.m-wish__empty-title {
  margin: 0;
  color: #1a1a1a;
  font-size: 16px;
  font-weight: var(--font-weight-semibold);
}

.m-wish__shopping {
  display: inline-flex;
  align-items: center;
  min-height: 40px;
  margin-top: 16px;
  padding: 0 20px;
  border: 1px solid #1a1a1a;
  border-radius: 999px;
  color: #1a1a1a;
  font-size: 14px;
  font-weight: var(--font-weight-semibold);
  text-decoration: none;
}

/* 2-column product grid, gap 12 (same card style as docs/20 §1). */
.m-wish__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin: 16px 16px 0;
  padding: 0;
  list-style: none;
}

.m-wish__cell {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.m-wish__card {
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  background: #ffffff;
  overflow: hidden;
  text-decoration: none;
}

.m-wish__img {
  width: 100%;
  aspect-ratio: 1 / 1;
  object-fit: cover;
  background: #eceef1;
}

.m-wish__name {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  padding: 10px 12px 0;
  color: #1a1a1a;
  font-size: 14px;
  line-height: 20px;
  min-height: 50px;
}

.m-wish__price {
  padding: 6px 12px 12px;
  color: #e1251b;
  font-size: 16px;
  font-weight: var(--font-weight-bold);
}

.m-wish__remove {
  min-height: 36px;
  border: 1px solid #e0e1e5;
  border-radius: 18px;
  background: #ffffff;
  color: #55565b;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}

.m-wish__remove:hover {
  border-color: #1a1a1a;
  color: #1a1a1a;
}
</style>
