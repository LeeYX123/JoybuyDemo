<script setup>
import { useLocale } from '../../composables/useLocale'

import AccountNav from './AccountNav.vue'

// Shared account page frame copied from joybuy.co.uk/profile/*: breadcrumb
// ("我的 / <page>"), 240px left module rail, white content panel with the
// page title and an optional top-right action. Only the four kept modules
// appear in the rail.
defineProps({
  title: {
    type: String,
    required: true,
  },
})

const { t } = useLocale()
</script>

<template>
  <div class="account-layout">
    <AppContainer>
      <div class="account-page">
        <nav class="account-page__crumbs" :aria-label="t('breadcrumb.label')">
          <NuxtLink class="account-page__crumb" to="/account">{{
            t('account.myAccount')
          }}</NuxtLink>
          <span class="account-page__sep" aria-hidden="true">/</span>
          <span class="account-page__crumb account-page__crumb--current">{{ title }}</span>
        </nav>

        <div class="account-page__grid">
          <AccountNav />
          <section class="account-panel" aria-labelledby="account-panel-title">
            <header class="account-panel__head">
              <h1 id="account-panel-title" class="account-panel__title">{{ title }}</h1>
              <div class="account-panel__actions"><slot name="actions" /></div>
            </header>
            <slot name="tabs" />
            <slot />
          </section>
        </div>
      </div>
    </AppContainer>
  </div>
</template>

<style scoped>
/* Joybuy 账号页实测（2026-11-16，1440/1920 均为 1264px 内容区）：
   面包屑 + 240px 左侧模块栏 + 24px 间距 + 1000px 白色面板 = 1264。
   只在账号页子树覆盖 --container-max，全局 token（详情页 1608）不动。 */
.account-layout {
  --container-max: calc(1264px + 2 * var(--container-pad));

  margin-block: 0;
  background: #f5f6fa;
}

.account-page {
  margin-block: 0 var(--space-12);
}

.account-page__crumbs {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: 2rem;
  padding-top: 2rem;
  color: #888b94;
  font-size: var(--font-size-md);
}

.account-page__crumb {
  color: #888b94;
  text-decoration: none;
}

.account-page__crumb:hover {
  color: var(--colour-text);
}

.account-page__crumb--current {
  color: var(--colour-text);
}

.account-page__sep {
  color: #888b94;
}

.account-page__grid {
  display: grid;
  grid-template-columns: 15rem minmax(0, 1fr);
  gap: var(--space-6);
  align-items: start;
}

.account-panel {
  padding: var(--space-6);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
}

.account-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  min-height: 48px;
  padding-bottom: var(--space-6);
}

.account-panel__title {
  margin: 0;
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  line-height: 1;
}

@media (max-width: 47.999rem) {
  .account-page__grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .account-panel {
    padding: var(--space-4);
  }
}
</style>
