<script setup>
import { computed, ref } from 'vue'
import { useHead } from '#imports'

import { useLocale } from '../../composables/useLocale'
import { useMobileView } from '../../composables/useMobileView'

import AccountEmpty from '../../components/account/AccountEmpty.vue'
import AccountShell from '../../components/account/AccountShell.vue'
import AccountTabs from '../../components/account/AccountTabs.vue'

// After-sales list: the Joybuy page has four tabs and a "申请售后" entry.
// This repo has no buyer after-sales backend yet, so the page shows the real
// tab structure with an honest empty state instead of fabricated records.
const { t } = useLocale()
// ADR 0001: on the m. host the same tab data renders the mobile after-sales
// page (docs/20 §5.5); the desktop AccountShell below is untouched.
const { isMobileHost } = useMobileView()

const tab = ref('all')
const tabs = computed(() => [
  { key: 'all', label: t('returns.tabAll') },
  { key: 'in_progress', label: t('returns.tabInProgress') },
  { key: 'completed', label: t('returns.tabCompleted') },
  { key: 'canceled', label: t('returns.tabCanceled') },
])

useHead(() => ({ title: t('accountMenu.returns') }))
</script>

<template>
  <!-- ADR 0001: mobile host renders the docs/20 §5.5 mobile after-sales;
       the desktop AccountShell below is untouched. -->
  <MobileReturns v-if="isMobileHost" :tabs="tabs" :active-tab="tab" @tab="tab = $event" />
  <AccountShell v-else :title="t('accountMenu.returns')">
    <template #actions>
      <button class="returns-apply" type="button" disabled>
        {{ t('returns.apply') }}
      </button>
    </template>

    <template #tabs>
      <AccountTabs v-model="tab" :tabs="tabs" />
    </template>

    <AccountEmpty :message="t('returns.empty')" />
  </AccountShell>
</template>

<style scoped>
.returns-apply {
  min-height: 40px;
  padding: 0 var(--space-3);
  border: 0;
  background: transparent;
  color: var(--colour-muted);
  font-size: var(--font-size-md);
  cursor: not-allowed;
}
</style>
