<script setup>
import { computed } from 'vue'
import { useRouter } from '#imports'

import { useLocale } from '../../composables/useLocale'

// 设置&隐私 page (user screenshot 2026-11-24): rows with chevrons for
// 账户安全 / 消息通知 / 个性化设置 / 管理Cookies / 法律信息, then 退出登录.
// Per the decision from the grill session: the toggle-type modules render a
// content + switch page with no logic behind it; 法律信息 lists the reused
// policy pages.
const { t } = useLocale()
const router = useRouter()

const rows = computed(() => [
  { key: 'account-security', label: t('mobile.drawer.settings.accountSecurity') },
  { key: 'notifications', label: t('mobile.drawer.settings.notifications') },
  { key: 'personalisation', label: t('mobile.drawer.settings.personalisation') },
  { key: 'cookies', label: t('mobile.drawer.settings.cookies') },
  { key: 'legal', label: t('mobile.drawer.settings.legal') },
])

function back() {
  router.back()
}
</script>

<template>
  <div class="m-settings">
    <MobilePageHeader :title="t('mobile.account.settingsPrivacy')" @back="back" />
    <div class="m-settings__body">
      <div class="m-settings__list">
        <NuxtLink
          v-for="row in rows"
          :key="row.key"
          class="m-settings__row"
          :to="`/account/settings/${row.key}`"
        >
          {{ row.label }}
          <svg
            class="m-settings__chevron"
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
      <MobileAccountSignOut />
    </div>
  </div>
</template>

<style scoped>
.m-settings__body {
  min-height: 100%;
  padding-bottom: 24px;
  background: #f5f6fa;
}

.m-settings__list {
  background: #ffffff;
}

.m-settings__row {
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
