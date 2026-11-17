<script setup>
import { computed, onMounted } from 'vue'
import { NuxtLink } from '#components'
import { useRoute } from '#imports'

import { useBuyerAuth } from '../../composables/useBuyerAuth'
import { useLocale } from '../../composables/useLocale'
import { useMerchantEntry } from '../../composables/useMerchantEntry'

// Joybuy account sidebar: the four kept modules (orders, returns, reviews,
// addresses) plus the seller entry. The seller label follows
// GET /api/v1/account/merchant-application: apply / under review / enter the
// merchant portal; only the approved state is an action (switch session), the
// other two are links to /account/apply-shop.
const route = useRoute()
const { t } = useLocale()
const { isAuthenticated } = useBuyerAuth()
const {
  label: merchantLabel,
  linkTarget,
  switching,
  loadStatus,
  openMerchantConsole,
} = useMerchantEntry()

const items = computed(() => [
  { key: 'orders', to: '/account/orders', label: t('accountMenu.orders') },
  { key: 'returns', to: '/account/returns', label: t('accountMenu.returns') },
  { key: 'reviews', to: '/account/reviews', label: t('accountMenu.reviews') },
  { key: 'addresses', to: '/account/addresses', label: t('accountMenu.addresses') },
  {
    key: 'merchant',
    to: linkTarget.value,
    label: switching.value ? t('merchantEntry.opening') : merchantLabel.value,
    icon: 'shop',
  },
])

function isActive(item) {
  return Boolean(item.to) && (route.path === item.to || route.path.startsWith(`${item.to}/`))
}

onMounted(() => {
  if (isAuthenticated.value) loadStatus({ force: true })
})
</script>

<template>
  <nav class="account-nav" :aria-label="t('account.navigation')">
    <ul class="account-nav__list">
      <li v-for="item in items" :key="item.key">
        <component
          :is="item.to ? NuxtLink : 'button'"
          class="account-nav__item"
          :class="{ 'account-nav__item--active': isActive(item) }"
          :to="item.to || undefined"
          :type="item.to ? undefined : 'button'"
          :aria-current="isActive(item) ? 'page' : undefined"
          :disabled="!item.to && switching"
          @click="!item.to && openMerchantConsole()"
        >
          <svg
            v-if="item.key === 'orders'"
            viewBox="0 0 24 24"
            width="18"
            height="18"
            aria-hidden="true"
          >
            <path
              d="M6 3h12a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Zm2 4v2h8V7H8Zm0 4v2h8v-2H8Zm0 4v2h5v-2H8Z"
              fill="currentColor"
            />
          </svg>
          <svg
            v-else-if="item.key === 'returns'"
            viewBox="0 0 24 24"
            width="18"
            height="18"
            aria-hidden="true"
          >
            <path
              d="M4 6h16v4H4V6Zm0 6h16v7a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-7Zm3 3v2h6v-2H7Zm9-9h4v14h-2V8h-2V6Z"
              fill="currentColor"
            />
          </svg>
          <svg
            v-else-if="item.key === 'reviews'"
            viewBox="0 0 24 24"
            width="18"
            height="18"
            aria-hidden="true"
          >
            <path
              d="M4 4h16a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H9l-5 4V5a1 1 0 0 1 1-1Zm3 5v2h10V9H7Zm0 4v2h7v-2H7Z"
              fill="currentColor"
            />
          </svg>
          <svg
            v-else-if="item.key === 'addresses'"
            viewBox="0 0 24 24"
            width="18"
            height="18"
            aria-hidden="true"
          >
            <path
              d="M12 2a7 7 0 0 1 7 7c0 5-7 13-7 13S5 14 5 9a7 7 0 0 1 7-7Zm0 4a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z"
              fill="currentColor"
            />
          </svg>
          <svg v-else viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
            <path
              d="M4 4h16v3H4V4Zm0 5h16v10a1 1 0 0 1-1 1h-5v-5H10v5H5a1 1 0 0 1-1-1V9Zm2 2v2h2v-2H6Zm4 0v2h2v-2h-2Zm4 0v2h2v-2h-2Z"
              fill="currentColor"
            />
          </svg>
          <span>{{ item.label }}</span>
        </component>
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

.account-nav__item:disabled {
  cursor: progress;
  opacity: 0.75;
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
