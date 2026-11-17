<script setup>
import { computed, onMounted } from 'vue'
import { NuxtLink } from '#components'
import { useFetch, useHead, useRequestHeaders, useRuntimeConfig } from '#imports'

import { useBuyerAuth } from '../../composables/useBuyerAuth'
import { useLocale } from '../../composables/useLocale'
import { useMerchantEntry } from '../../composables/useMerchantEntry'

// Account hub rebuilt from joybuy.co.uk/profile (screenshots in
// var/account_pages_20261116): avatar + username header, one order summary
// strip, then the kept modules (orders, after-sales, reviews and Q&A,
// addresses) plus the seller entry: apply for a shop, track the review, or
// switch to the merchant portal once approved.
const { isAuthenticated, account, logout } = useBuyerAuth()
const { t } = useLocale()
const config = useRuntimeConfig()
const {
  label: merchantLabel,
  description: merchantDesc,
  linkTarget,
  switching,
  loadStatus,
  openMerchantConsole,
} = useMerchantEntry()

const ordersUrl = computed(() =>
  import.meta.server ? `${config.apiBaseInternal}/orders` : '/api/v1/orders',
)

const { data: ordersData } = await useFetch(ordersUrl, {
  key: 'buyer-orders',
  headers: { cookie: useRequestHeaders(['cookie']).cookie || '' },
})

const orders = computed(() =>
  Array.isArray(ordersData.value?.orders) ? ordersData.value.orders : [],
)

const counts = computed(() => ({
  pendingPayment: orders.value.filter((order) => order.state === 'PENDING_PAYMENT').length,
  shipped: orders.value.filter((order) => order.state === 'SHIPPED').length,
  completed: orders.value.filter((order) => order.state === 'COMPLETED').length,
}))

const orderStats = computed(() => [
  {
    key: 'pending_payment',
    label: t('orders.tabPendingPayment'),
    count: counts.value.pendingPayment,
  },
  { key: 'shipped', label: t('orders.tabToReceive'), count: counts.value.shipped },
  { key: 'completed', label: t('orders.tabCompleted'), count: counts.value.completed },
])

const modules = computed(() => [
  {
    key: 'orders',
    to: '/account/orders',
    title: t('accountMenu.orders'),
    description: t('account.moduleOrdersDesc'),
    icon: 'orders',
  },
  {
    key: 'returns',
    to: '/account/returns',
    title: t('accountMenu.returns'),
    description: t('account.moduleReturnsDesc'),
    icon: 'returns',
  },
  {
    key: 'reviews',
    to: '/account/reviews',
    title: t('accountMenu.reviews'),
    description: t('account.moduleReviewsDesc'),
    icon: 'reviews',
  },
  {
    key: 'addresses',
    to: '/account/addresses',
    title: t('accountMenu.addresses'),
    description: t('account.moduleAddressesDesc'),
    icon: 'addresses',
  },
  {
    key: 'merchant',
    to: linkTarget.value,
    title: merchantLabel.value,
    description: merchantDesc.value,
    icon: 'shop',
  },
])

onMounted(() => {
  if (isAuthenticated.value) loadStatus({ force: true })
})

const displayName = computed(
  () => account.value?.display_identifier || account.value?.email || account.value?.phone_number,
)

async function signOut() {
  await logout()
  await navigateTo('/')
}

useHead(() => ({ title: t('account.myAccount') }))
</script>

<template>
  <AppContainer>
    <section v-if="isAuthenticated" class="profile" aria-labelledby="profile-title">
      <header class="profile-head">
        <div class="profile-head__avatar" aria-hidden="true">
          <svg viewBox="0 0 40 40" width="40" height="40">
            <circle cx="20" cy="20" r="20" fill="#dfe3e8" />
            <circle cx="14" cy="17" r="2" fill="#fff" />
            <circle cx="26" cy="17" r="2" fill="#fff" />
            <path
              d="M12 26c2.2 2.6 4.8 3.9 8 3.9s5.8-1.3 8-3.9"
              fill="none"
              stroke="#fff"
              stroke-width="2"
              stroke-linecap="round"
            />
          </svg>
        </div>
        <div class="profile-head__identity">
          <h1 id="profile-title" class="profile-head__name">{{ displayName }}</h1>
          <p class="profile-head__meta">
            {{ t('account.signedInAs') }} <span>{{ displayName }}</span>
          </p>
        </div>
        <button class="profile-head__signout" type="button" @click="signOut">
          {{ t('accountMenu.signOut') }}
        </button>
      </header>

      <section class="order-summary" :aria-label="t('accountMenu.orders')">
        <NuxtLink class="order-summary__all" to="/account/orders">
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
            <path
              d="M6 3h12a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Zm2 4v2h8V7H8Zm0 4v2h8v-2H8Zm0 4v2h5v-2H8Z"
              fill="currentColor"
            />
          </svg>
          <span>{{ t('accountMenu.orders') }}</span>
          <span class="order-summary__arrow" aria-hidden="true">›</span>
        </NuxtLink>
        <NuxtLink
          v-for="stat in orderStats"
          :key="stat.key"
          class="order-summary__stat"
          :to="`/account/orders?tab=${stat.key}`"
        >
          <strong>{{ stat.count }}</strong>
          <span>{{ stat.label }}</span>
        </NuxtLink>
      </section>

      <nav class="profile-modules" :aria-label="t('account.modules')">
        <component
          :is="module.to ? NuxtLink : 'button'"
          v-for="module in modules"
          :key="module.key"
          class="profile-module"
          :class="{ 'profile-module--action': !module.to }"
          :to="module.to || undefined"
          :type="module.to ? undefined : 'button'"
          :disabled="!module.to && switching"
          @click="!module.to && openMerchantConsole()"
        >
          <span class="profile-module__icon" aria-hidden="true">
            <svg v-if="module.icon === 'orders'" viewBox="0 0 24 24" width="22" height="22">
              <path
                d="M6 3h12a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Zm2 4v2h8V7H8Zm0 4v2h8v-2H8Zm0 4v2h5v-2H8Z"
                fill="currentColor"
              />
            </svg>
            <svg v-else-if="module.icon === 'returns'" viewBox="0 0 24 24" width="22" height="22">
              <path
                d="M4 6h16v4H4V6Zm0 6h16v7a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-7Zm3 3v2h6v-2H7Zm9-9h4v14h-2V8h-2V6Z"
                fill="currentColor"
              />
            </svg>
            <svg v-else-if="module.icon === 'reviews'" viewBox="0 0 24 24" width="22" height="22">
              <path
                d="M4 4h16a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H9l-5 4V5a1 1 0 0 1 1-1Zm3 5v2h10V9H7Zm0 4v2h7v-2H7Z"
                fill="currentColor"
              />
            </svg>
            <svg v-else-if="module.icon === 'addresses'" viewBox="0 0 24 24" width="22" height="22">
              <path
                d="M12 2a7 7 0 0 1 7 7c0 5-7 13-7 13S5 14 5 9a7 7 0 0 1 7-7Zm0 4a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z"
                fill="currentColor"
              />
            </svg>
            <svg v-else viewBox="0 0 24 24" width="22" height="22">
              <path
                d="M4 4h16v3H4V4Zm0 5h16v10a1 1 0 0 1-1 1h-5v-5H10v5H5a1 1 0 0 1-1-1V9Zm2 2v2h2v-2H6Zm4 0v2h2v-2h-2Zm4 0v2h2v-2h-2Z"
                fill="currentColor"
              />
            </svg>
          </span>
          <span class="profile-module__body">
            <span class="profile-module__title">
              {{ switching && !module.to ? t('merchantEntry.opening') : module.title }}
            </span>
            <span class="profile-module__desc">{{ module.description }}</span>
          </span>
          <span class="profile-module__arrow" aria-hidden="true">›</span>
        </component>
      </nav>
    </section>

    <section v-else class="profile-signed-out" aria-labelledby="profile-title">
      <h1 id="profile-title">{{ t('account.myAccount') }}</h1>
      <p>{{ t('account.signInPrompt') }}</p>
      <div class="profile-signed-out__actions">
        <NuxtLink to="/auth/login"
          ><BaseButton variant="primary">{{ t('header.signIn') }}</BaseButton></NuxtLink
        >
        <NuxtLink to="/auth/register">
          <BaseButton variant="secondary">{{ t('auth.createAccount') }}</BaseButton>
        </NuxtLink>
      </div>
    </section>
  </AppContainer>
</template>

<style scoped>
.profile {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  margin-block: var(--space-6) var(--space-12);
}

.profile-head {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-5) var(--space-6);
}

.profile-head__avatar {
  display: flex;
  flex: 0 0 auto;
}

.profile-head__identity {
  flex: 1;
  min-width: 0;
}

.profile-head__name {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 1.5rem;
  font-weight: var(--font-weight-bold);
}

.profile-head__meta {
  margin: var(--space-1) 0 0;
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}

.profile-head__signout {
  min-height: 40px;
  padding: 0 var(--space-4);
  border: 1px solid var(--colour-border-strong);
  border-radius: var(--radius-pill);
  background: var(--colour-surface);
  color: var(--colour-text);
  cursor: pointer;
}

.profile-head__signout:hover {
  background: var(--colour-surface-muted);
}

.order-summary {
  display: grid;
  grid-template-columns: 1.35fr repeat(3, 1fr);
  gap: var(--space-3);
  padding: var(--space-3);
  border-radius: 4px;
  background: var(--colour-surface);
}

.order-summary__all {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-height: 80px;
  padding: 0 var(--space-4);
  border-radius: 2px;
  color: var(--colour-text);
  text-decoration: none;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
}

.order-summary__arrow {
  margin-left: auto;
  color: var(--colour-muted);
  font-size: 1.25rem;
}

.order-summary__stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-1);
  min-height: 80px;
  border-radius: 2px;
  background: var(--colour-surface-soft);
  color: var(--colour-text);
  text-decoration: none;
  font-size: var(--font-size-md);
}

.order-summary__stat:hover,
.order-summary__all:hover,
.profile-module:hover {
  background: var(--colour-hover);
}

.order-summary__stat strong {
  font-size: 1.5rem;
  font-weight: var(--font-weight-bold);
}

.profile-modules {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--space-4);
}

.profile-module {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-height: 104px;
  padding: var(--space-4);
  border: 0;
  border-radius: 4px;
  background: var(--colour-surface);
  color: var(--colour-text);
  text-align: left;
  text-decoration: none;
  font: inherit;
  cursor: pointer;
}

.profile-module--action:disabled {
  cursor: progress;
  opacity: 0.75;
}

.profile-module__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: var(--colour-surface-muted);
  color: var(--colour-text-secondary);
}

.profile-module__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.profile-module__title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
}

.profile-module__desc {
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
  line-height: var(--line-height-normal);
}

.profile-module__arrow {
  color: var(--colour-muted);
  font-size: 1.25rem;
}

.profile-signed-out {
  max-width: 30rem;
  margin: var(--space-10) auto;
  padding: var(--space-8);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-lg);
  background: var(--colour-surface);
}

.profile-signed-out p {
  margin-block: var(--space-3) var(--space-5);
  color: var(--colour-text-secondary);
}

.profile-signed-out__actions {
  display: flex;
  gap: var(--space-3);
}

.profile-signed-out__actions :deep(a) {
  text-decoration: none;
}

@media (max-width: 63.999rem) {
  .profile-modules {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 47.999rem) {
  .profile-head {
    flex-wrap: wrap;
    padding: var(--space-4);
  }

  .order-summary {
    grid-template-columns: repeat(3, 1fr);
  }

  .order-summary__all {
    grid-column: 1 / -1;
    min-height: 56px;
  }

  .profile-modules {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
