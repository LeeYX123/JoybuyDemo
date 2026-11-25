<script setup>
import { useHead } from '#imports'

import { useLocale } from '../../composables/useLocale'
import { useMobileView } from '../../composables/useMobileView'

import AccountEmpty from '../../components/account/AccountEmpty.vue'
import AccountShell from '../../components/account/AccountShell.vue'

// "积分" account module (real site /profile/points-activity, resurveyed
// 2026-11-25): "积分与记录" heading, current-points line and a records list.
// There is no buyer points backend in this repo, so the page shows the real
// structure with an honest zero/empty state instead of fabricated records
// (same pattern as the after-sales page).
const { t } = useLocale()
const { isMobileHost } = useMobileView()

useHead(() => ({ title: t('accountMenu.points') }))
</script>

<template>
  <div v-if="isMobileHost" class="m-generic">
    <MobilePageHeader :title="t('account.pointsHeading')" @back="$router.back()" />
    <div class="m-generic__body">
      <p class="points-have">
        {{ t('account.pointsYouHave') }} <strong>0</strong> {{ t('account.pointsUnit') }}
      </p>
      <h2 class="points-records">{{ t('account.pointsRecords') }}</h2>
      <AccountEmpty :message="t('account.pointsEmpty')" />
    </div>
  </div>

  <AccountShell v-else :title="t('account.pointsHeading')">
    <p class="points-have">
      {{ t('account.pointsYouHave') }} <strong>0</strong> {{ t('account.pointsUnit') }}
    </p>
    <h2 class="points-records">{{ t('account.pointsRecords') }}</h2>
    <AccountEmpty :message="t('account.pointsEmpty')" />
  </AccountShell>
</template>

<style scoped>
.points-have {
  margin: 0;
  color: var(--colour-text-secondary);
  font-size: var(--font-size-md);
}

.points-have strong {
  color: var(--colour-text);
  font-size: var(--font-size-xl);
}

.points-records {
  margin: var(--space-6) 0 0;
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
}

.m-generic {
  padding: var(--space-4);
}

.m-generic__body {
  margin-top: var(--space-4);
}
</style>
