<script setup>
// 活动页 /active/<真站 id>（2026-11-25，首页「为你推荐」落地页）。
// 数据来自 /api/v1/activity-pages/active/<id>；停用或不存在时渲染降级态。
import { useHead } from '#imports'

import { useActivityPage } from '../../composables/useActivityPage'
import { useLocale } from '../../composables/useLocale'
import { useMobileView } from '../../composables/useMobileView'

import ActivityPageView from '../../components/activity/ActivityPageView.vue'
import MobileActivityPage from '../../components/mobile/MobileActivityPage.vue'

const { t } = useLocale()
const { isMobileHost } = useMobileView()
const { page } = useActivityPage('active')

useHead(() => ({ title: page.value?.title || t('activity.notFound') }))
</script>

<template>
  <MobileActivityPage v-if="isMobileHost && page" :page="page" kind="activity" />
  <ActivityPageView v-else-if="page" :page="page" kind="activity" />
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
