<script setup>
import { computed } from 'vue'
import { useRouter } from '#imports'

import { useLocale } from '../../composables/useLocale'

// 法律信息 page (user screenshot, decision 2026-11-24): the five policy
// entries reuse the existing web policy pages.
const { t } = useLocale()
const router = useRouter()

const links = computed(() => [
  { label: t('mobile.drawer.settings.legal.terms'), to: '/pages/terms-conditions' },
  { label: t('mobile.drawer.settings.legal.cookies'), to: '/pages/cookie-policy' },
  { label: t('mobile.drawer.settings.legal.privacy'), to: '/pages/privacy-policy' },
  { label: t('mobile.drawer.settings.legal.sales'), to: '/pages/terms-of-use' },
  { label: t('mobile.drawer.settings.legal.accessibility'), to: '/pages/accessibility-statement' },
])

function back() {
  router.back()
}
</script>

<template>
  <div class="m-legal">
    <MobilePageHeader :title="t('mobile.drawer.settings.legal')" @back="back" />
    <div class="m-legal__list">
      <NuxtLink v-for="link in links" :key="link.to" class="m-legal__row" :to="link.to">
        {{ link.label }}
        <svg
          class="m-legal__chevron"
          viewBox="0 0 24 24"
          width="18"
          height="18"
          aria-hidden="true"
          fill="none"
          stroke="currentColor"
          stroke-width="1.8"
        >
          <path d="m9 5 7 7-7 7" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </NuxtLink>
    </div>
  </div>
</template>

<style scoped>
.m-legal__list {
  background: #ffffff;
}

.m-legal__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 56px;
  padding: 0 16px;
  border-bottom: 1px solid #f0f1f2;
  color: #1a1a1a;
  font-size: 16px;
  text-decoration: none;
}
</style>
