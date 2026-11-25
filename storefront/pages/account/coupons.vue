<script setup>
import { computed, ref } from 'vue'
import { useHead } from '#imports'

import { useLocale } from '../../composables/useLocale'
import { useMobileView } from '../../composables/useMobileView'

import AccountEmpty from '../../components/account/AccountEmpty.vue'
import AccountShell from '../../components/account/AccountShell.vue'
import AccountTabs from '../../components/account/AccountTabs.vue'

// "优惠券" account module (real site /profile/coupons-discounts, resurveyed
// 2026-11-25): "可使用 / 历史记录" tabs over a coupon-card list. There is no
// buyer coupon backend in this repo, so both tabs show an honest empty state
// instead of fabricated coupons.
const { t } = useLocale()
const { isMobileHost } = useMobileView()

const tab = ref('available')
const tabs = computed(() => [
  { key: 'available', label: t('account.couponsTabAvailable') },
  { key: 'history', label: t('account.couponsTabHistory') },
])

useHead(() => ({ title: t('accountMenu.coupons') }))
</script>

<template>
  <div v-if="isMobileHost" class="m-generic">
    <MobilePageHeader :title="t('accountMenu.coupons')" @back="$router.back()" />
    <div class="m-generic__body">
      <AccountTabs v-model="tab" :tabs="tabs" />
      <AccountEmpty :message="t('account.couponsEmpty')" />
    </div>
  </div>

  <AccountShell v-else :title="t('accountMenu.coupons')">
    <template #tabs>
      <AccountTabs v-model="tab" :tabs="tabs" />
    </template>

    <AccountEmpty :message="t('account.couponsEmpty')" />
  </AccountShell>
</template>

<style scoped>
.m-generic {
  padding: var(--space-4);
}

.m-generic__body {
  margin-top: var(--space-4);
}
</style>
