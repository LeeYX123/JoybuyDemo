<script setup>
import { useHead } from '#imports'

import { useLocale } from '../../composables/useLocale'

import AccountEmpty from '../../components/account/AccountEmpty.vue'
import AccountShell from '../../components/account/AccountShell.vue'

// Reviews and Q&A: joybuy.co.uk/profile/my-reviews is a single panel with no
// tabs. The buyer-review API is not implemented in this repo (only product
// review reads), so the page is an honest empty state.
const { t } = useLocale()

useHead(() => ({ title: t('accountMenu.reviews') }))
</script>

<template>
  <AccountShell :title="t('accountMenu.reviews')">
    <AccountEmpty :message="t('reviews.empty')" />
  </AccountShell>
</template>
