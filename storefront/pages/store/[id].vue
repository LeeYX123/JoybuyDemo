<script setup>
// 店铺页 /store/<真站店铺 id>（2026-11-25，一次性快照复刻）。
// 与活动页共用配置模型（kind=store）：店铺头 + 商品网格，不含真站的
// 【店铺】【商品】tab（用户 2026-11-25 拍板）。
import { useHead } from '#imports'

import { useActivityPage } from '../../composables/useActivityPage'
import { useLocale } from '../../composables/useLocale'
import { useMobileView } from '../../composables/useMobileView'

import ActivityPageView from '../../components/activity/ActivityPageView.vue'
import MobileActivityPage from '../../components/mobile/MobileActivityPage.vue'

const { t } = useLocale()
const { isMobileHost } = useMobileView()
const { page } = useActivityPage('store')

useHead(() => ({ title: page.value?.store_name || page.value?.title || t('activity.notFound') }))
</script>

<template>
  <MobileActivityPage v-if="isMobileHost && page" :page="page" kind="store" />
  <ActivityPageView v-else-if="page" :page="page" kind="store" />
  <section v-else class="activity-missing" role="status">
    <p>{{ t('activity.notFound') }}</p>
    <NuxtLink class="activity-missing__home" to="/">{{ t('activity.backHome') }}</NuxtLink>
  </section>
</template>

<style scoped>
.activity-missing {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding-block: var(--space-8);
  color: var(--colour-text-secondary);
}

.activity-missing__home {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  color: var(--colour-accent);
  font-weight: var(--font-weight-semibold);
}
</style>
