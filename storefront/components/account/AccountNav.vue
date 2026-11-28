<script setup>
import { computed } from 'vue'
import { NuxtLink } from '#components'
import { useRoute } from '#imports'

import { useLocale } from '../../composables/useLocale'

// Joybuy account sidebar rebuilt from the 2026-11-25 resurvey
// (var/profile_resurvey_20261125/): the real rail is 我的 / 我的订单 / 售后单 /
// 评价与问答 / 心愿单 / Joybuy 余额 / 积分 / 优惠券 / 地址. We keep our own
// naming for the wishlist entry (我的收藏, see CONTEXT.md).
// 2026-11-28（用户要求）：账号区不再有商家入口（含「进入商家中心」）；
// 进入商家端只保留页头右上角的【切换商家端】pill。
const route = useRoute()
const { t } = useLocale()

const items = computed(() => [
  { key: 'home', to: '/account', label: t('accountMenu.home') },
  { key: 'orders', to: '/account/orders', label: t('accountMenu.orders') },
  { key: 'returns', to: '/account/returns', label: t('accountMenu.returns') },
  { key: 'reviews', to: '/account/reviews', label: t('accountMenu.reviews') },
  { key: 'favourites', to: '/account/favourites', label: t('accountMenu.favourites') },
  { key: 'balance', to: '/account/balance', label: t('accountMenu.balance') },
  { key: 'points', to: '/account/points', label: t('accountMenu.points') },
  { key: 'coupons', to: '/account/coupons', label: t('accountMenu.coupons') },
  { key: 'addresses', to: '/account/addresses', label: t('accountMenu.addresses') },
])

function isActive(item) {
  return Boolean(item.to) && (route.path === item.to || route.path.startsWith(`${item.to}/`))
}

const ICONS = {
  home: 'M10 3.6 3 9.4V20a1 1 0 0 0 1 1h5v-6h6v6h5a1 1 0 0 0 1-1V9.4l-7-5.8a1 1 0 0 0-1.28 0Z',
  orders:
    'M6 3h12a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Zm2 4v2h8V7H8Zm0 4v2h8v-2H8Zm0 4v2h5v-2H8Z',
  returns:
    'M4 6h16v4H4V6Zm0 6h16v7a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-7Zm3 3v2h6v-2H7Zm9-9h4v14h-2V8h-2V6Z',
  reviews:
    'M4 4h16a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H9l-5 4V5a1 1 0 0 1 1-1Zm3 5v2h10V9H7Zm0 4v2h7v-2H7Z',
  favourites: 'M12 21s-8-5.2-8-11a4.6 4.6 0 0 1 8-3.1A4.6 4.6 0 0 1 20 10c0 5.8-8 11-8 11Z',
  balance:
    'M3 6h18a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1Zm1 4v5h16v-5H4Zm0-2h16V8H4v2Z',
  points:
    'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm1 5v3.2l3 1.7-1 1.7-3-1.7-3 1.7-1-1.7 3-1.7V7h2Z',
  coupons:
    'M3 5h18a1 1 0 0 1 1 1v4a2 2 0 0 0 0 4v4a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-4a2 2 0 0 0 0-4V6a1 1 0 0 1 1-1Zm3 4v2h6V9H6Zm0 4v2h10v-2H6Z',
  addresses:
    'M12 2a7 7 0 0 1 7 7c0 5-7 13-7 13S5 14 5 9a7 7 0 0 1 7-7Zm0 4a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z',
}
</script>

<template>
  <nav class="account-nav" :aria-label="t('account.navigation')">
    <ul class="account-nav__list">
      <li v-for="item in items" :key="item.key">
        <NuxtLink
          class="account-nav__item"
          :class="{ 'account-nav__item--active': isActive(item) }"
          :to="item.to"
          :aria-current="isActive(item) ? 'page' : undefined"
        >
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
            <path :d="ICONS[item.key]" fill="currentColor" />
          </svg>
          <span>{{ item.label }}</span>
        </NuxtLink>
      </li>
    </ul>
  </nav>
</template>

<style scoped>
.account-nav {
  align-self: start;
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
}

.account-nav__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}

.account-nav__item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  width: 100%;
  min-height: 56px;
  padding: 0 var(--space-4);
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--colour-text);
  text-align: left;
  font: inherit;
  font-size: var(--font-size-lg);
  text-decoration: none;
  cursor: pointer;
}

.account-nav__item:hover {
  background: var(--colour-hover);
}

.account-nav__item--active {
  background: var(--colour-hover);
  font-weight: var(--font-weight-semibold);
}

@media (max-width: 47.999rem) {
  .account-nav {
    width: 100%;
    padding: var(--space-2);
  }

  .account-nav__list {
    flex-direction: row;
    flex-wrap: wrap;
  }

  .account-nav__item {
    width: auto;
    min-height: 44px;
    padding: 0 var(--space-3);
    font-size: var(--font-size-md);
  }
}
</style>
