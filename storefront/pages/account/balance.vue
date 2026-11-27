<script setup>
import { computed, ref, watch } from 'vue'
import { useFetch, useHead, useRequestHeaders, useRuntimeConfig } from '#imports'

import { useBuyerAuth } from '../../composables/useBuyerAuth'
import { useLocale } from '../../composables/useLocale'
import { useMobileView } from '../../composables/useMobileView'

import AccountEmpty from '../../components/account/AccountEmpty.vue'
import AccountPager from '../../components/account/AccountPager.vue'
import AccountShell from '../../components/account/AccountShell.vue'

// "Joybuy 余额" account module (real site /profile/wallet, resurveyed
// 2026-11-25): read-only balance + transaction history. Top-ups stay admin-side
// (requirement 8-6 whitelist); the buyer API has no write path, so the page is
// honest about the empty state. Entry amounts keep the wallet sign convention:
// income positive, spending negative.
const { t } = useLocale()
const { isAuthenticated } = useBuyerAuth()
const config = useRuntimeConfig()
const { isMobileHost } = useMobileView()

const walletUrl = computed(() =>
  import.meta.server ? `${config.apiBaseInternal}/wallet` : '/api/v1/buyer/wallet',
)

const { data } = await useFetch(walletUrl, {
  key: 'buyer-wallet',
  headers: { cookie: useRequestHeaders(['cookie']).cookie || '' },
})

const balance = computed(() => data.value?.balance ?? null)
const entries = computed(() => (Array.isArray(data.value?.entries) ? data.value.entries : []))

const page = ref(1)
const totalPages = computed(() => Math.max(1, Number(data.value?.total_pages) || 1))

watch(totalPages, (value) => {
  if (page.value > value) page.value = value
})

const KIND_KEYS = {
  RECHARGE: 'account.walletKindRecharge',
  PURCHASE: 'account.walletKindPurchase',
  ADJUSTMENT: 'account.walletKindAdjustment',
}

function kindLabel(entry) {
  return t(KIND_KEYS[entry.kind] || 'account.walletKindAdjustment')
}

// Balance is a Decimal string with up to 4dp; display uses the site-wide "$" symbol.
function formatMoney(value) {
  const number = Number(value)
  return `$${Number.isFinite(number) ? number.toFixed(2) : value}`
}

function formatDate(value) {
  if (!value) return ''
  return String(value).slice(0, 16).replace('T', ' ')
}

function goToPage(next) {
  if (next >= 1 && next <= totalPages.value) page.value = next
}

useHead(() => ({ title: t('accountMenu.balance') }))
</script>

<template>
  <!-- Mobile host: these modules have no m. counterpart (m. hub drops
       余额/积分/优惠券 tiles per docs/19), so a light page-header variant keeps
       direct URL visits presentable without touching the desktop shell. -->
  <div v-if="isMobileHost" class="m-generic">
    <MobilePageHeader :title="t('accountMenu.balance')" @back="$router.back()" />
    <div class="m-generic__body">
      <div class="balance-current">
        <span class="balance-current__label">{{ t('account.balanceCurrent') }}</span>
        <strong class="balance-current__value">{{
          balance === null ? '—' : formatMoney(balance)
        }}</strong>
      </div>
      <h2 class="balance-history">{{ t('account.transactionHistory') }}</h2>
      <AccountEmpty v-if="entries.length === 0" :message="t('account.walletEmpty')" />
      <ul v-else class="balance-list">
        <li v-for="entry in entries" :key="entry.public_id" class="balance-row">
          <div class="balance-row__info">
            <span class="balance-row__kind">{{ kindLabel(entry) }}</span>
            <span class="balance-row__date">{{ formatDate(entry.occurred_at) }}</span>
          </div>
          <span
            class="balance-row__amount"
            :class="{ 'balance-row__amount--neg': Number(entry.amount) < 0 }"
          >
            {{ Number(entry.amount) > 0 ? '+' : '' }}{{ formatMoney(entry.amount) }}
          </span>
        </li>
      </ul>
    </div>
  </div>

  <AccountShell v-else :title="t('accountMenu.balance')">
    <div v-if="!isAuthenticated" class="balance-signed-out">
      <AccountEmpty :message="t('orders.signInRequired')" :note="t('orders.signInNote')" compact />
      <div class="balance-signed-out__actions">
        <NuxtLink to="/auth/login"
          ><BaseButton variant="primary">{{ t('header.signIn') }}</BaseButton></NuxtLink
        >
      </div>
    </div>

    <template v-else>
      <div class="balance-current">
        <span class="balance-current__label">{{ t('account.balanceCurrent') }}</span>
        <strong class="balance-current__value">{{
          balance === null ? '—' : formatMoney(balance)
        }}</strong>
      </div>

      <h2 class="balance-history">{{ t('account.transactionHistory') }}</h2>

      <AccountEmpty v-if="entries.length === 0" :message="t('account.walletEmpty')" />

      <template v-else>
        <ul class="balance-list">
          <li v-for="entry in entries" :key="entry.public_id" class="balance-row">
            <div class="balance-row__info">
              <span class="balance-row__kind">{{ kindLabel(entry) }}</span>
              <span class="balance-row__date">{{ formatDate(entry.occurred_at) }}</span>
            </div>
            <span
              class="balance-row__amount"
              :class="{ 'balance-row__amount--neg': Number(entry.amount) < 0 }"
            >
              {{ Number(entry.amount) > 0 ? '+' : '' }}{{ formatMoney(entry.amount) }}
            </span>
          </li>
        </ul>

        <AccountPager :page="page" :total-pages="totalPages" @change="goToPage" />
      </template>
    </template>
  </AccountShell>
</template>

<style scoped>
.balance-current {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-5);
  border-radius: var(--radius-md);
  background: var(--colour-surface-soft);
}

.balance-current__label {
  color: var(--colour-muted);
  font-size: var(--font-size-md);
}

.balance-current__value {
  font-size: 2rem;
  font-weight: var(--font-weight-bold);
  line-height: 1.2;
}

.balance-history {
  margin: var(--space-6) 0 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
}

.balance-list {
  display: flex;
  flex-direction: column;
  margin: var(--space-3) 0 0;
  padding: 0;
  list-style: none;
}

.balance-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  border-top: 1px solid var(--colour-border);
  padding-block: var(--space-3);
}

.balance-row:first-child {
  border-top: 0;
}

.balance-row__info {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.balance-row__kind {
  font-weight: var(--font-weight-semibold);
}

.balance-row__date {
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}

.balance-row__amount {
  font-weight: var(--font-weight-semibold);
  color: var(--colour-success);
}

.balance-row__amount--neg {
  color: var(--colour-text);
}

.balance-signed-out {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.balance-signed-out__actions {
  padding-bottom: var(--space-8);
}

.balance-signed-out__actions :deep(a) {
  text-decoration: none;
}

.m-generic {
  padding: var(--space-4);
}

.m-generic__body {
  margin-top: var(--space-4);
}
</style>
