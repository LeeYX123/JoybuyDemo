<script setup>
import { computed, ref } from 'vue'
import { useHead } from '#imports'

import { useLocale } from '../../composables/useLocale'
import { useMobileView } from '../../composables/useMobileView'

import AccountEmpty from '../../components/account/AccountEmpty.vue'
import AccountShell from '../../components/account/AccountShell.vue'

// Reviews and Q&A: joybuy.co.uk/profile/my-reviews is a single panel with no
// tabs. The buyer-review API is not implemented in this repo (only product
// review reads), so the page is an honest empty state.
// Mobile (docs/20 §5.6, user decision): review semantics only — the header
// is 我的评价 with to-review/reviewed tabs and NO Q&A tab.
const { t } = useLocale()
const { isMobileHost } = useMobileView()

const activeTab = ref('to_review')
const tabs = computed(() => [
  { key: 'to_review', label: t('mobile.reviews.tabToReview') },
  { key: 'reviewed', label: t('mobile.reviews.tabReviewed') },
])

useHead(() => ({ title: t('accountMenu.reviews') }))
</script>

<template>
  <!-- ADR 0001: mobile host renders the docs/20 §5.6 mobile reviews
       (review-only semantics, no Q&A tab); the desktop AccountShell below is
       untouched. -->
  <MobileReviews
    v-if="isMobileHost"
    :tabs="tabs"
    :active-tab="activeTab"
    @tab="activeTab = $event"
  />
  <AccountShell v-else :title="t('accountMenu.reviews')">
    <AccountEmpty :message="t('reviews.empty')" />
  </AccountShell>
</template>
