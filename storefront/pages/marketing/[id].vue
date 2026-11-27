<script setup>
// 营销落地页 /marketing/<真站 activityId>（2026-11-27，首页「每周甄选」落地页）。
// 复刻真站 marketing 页：深蓝装饰 banner（标题 + 副标题）+ 单一商品网格；
// 真站的类目切换 tab 与 Filter 侧栏不复刻（用户拍板）。商品为配额选品快照
// （首屏 20 件 = 4 行 × 5 列，点一次【查看更多】再展示 20 件，共 40）。
import { computed, ref } from 'vue'
import { useHead } from '#imports'

import { useActivityPage } from '../../composables/useActivityPage'
import { useLocale } from '../../composables/useLocale'
import { useMobileView } from '../../composables/useMobileView'

import ActivityPageSkeleton from '../../components/activity/ActivityPageSkeleton.vue'
import ProductCard from '../../components/ProductCard.vue'

const { t, locale } = useLocale()
const { isMobileHost } = useMobileView()
const { page, loading } = useActivityPage('marketing')

// 单一商品楼层：首屏 FIRST_BATCH 件，一次【查看更多】展开全部（共 40）。
const FIRST_BATCH = 20
const revealed = ref(false)
const products = computed(() => {
  const sections = page.value?.sections || []
  const floor = sections.find((s) => s.kind === 'PRODUCTS')
  return floor?.products || []
})
const visibleProducts = computed(() =>
  revealed.value ? products.value : products.value.slice(0, FIRST_BATCH),
)
const hasMore = computed(() => products.value.length > FIRST_BATCH)

const bannerStyle = computed(() => ({
  backgroundImage: page.value?.hero_image ? `url(${page.value.hero_image})` : undefined,
}))

useHead(() => ({
  title: page.value?.title || (loading.value ? t('activity.loading') : t('activity.notFound')),
}))

function onReveal() {
  revealed.value = true
}
</script>

<template>
  <ActivityPageSkeleton v-if="loading" kind="activity" />
  <section v-else-if="page" class="marketing-page">
    <!-- 装饰 banner：真站 1865×384 深蓝底图 + 白色标题/副标题（左对齐） -->
    <div class="marketing-banner" :style="bannerStyle">
      <div class="marketing-banner__inner">
        <h1 class="marketing-banner__title">
          {{ locale === 'zh' && page.title_zh ? page.title_zh : page.title }}
        </h1>
        <p v-if="page.subtitle" class="marketing-banner__subtitle">{{ page.subtitle }}</p>
      </div>
    </div>

    <!-- 商品网格：首屏 20（4×5），一次查看更多展示全部 40 -->
    <div class="marketing-body">
      <ul class="marketing-grid" :class="{ 'marketing-grid--mobile': isMobileHost }">
        <li v-for="item in visibleProducts" :key="item.item_key">
          <ProductCard :product="item" />
        </li>
      </ul>
      <div v-if="hasMore && !revealed" class="marketing-more">
        <button class="marketing-more__btn" type="button" @click="onReveal">
          {{ t('channel.more') }}
        </button>
      </div>
    </div>
  </section>
  <section v-else class="activity-missing" role="status">
    <p>{{ t('activity.notFound') }}</p>
    <NuxtLink class="activity-missing__home" to="/">{{ t('activity.backHome') }}</NuxtLink>
  </section>
</template>

<style scoped>
.marketing-page {
  margin-block-start: 0;
  background: var(--colour-canvas, #f6f7f9);
}

/* banner：真站深蓝装饰底图，标题白字左对齐（约 384/1865 比例高度）。 */
.marketing-banner {
  display: flex;
  align-items: center;
  min-height: 220px;
  background-color: #2e3577;
  background-size: cover;
  background-position: center;
}

.marketing-banner__inner {
  width: min(1296px, 92%);
  margin: 0 auto;
}

.marketing-banner__title {
  margin: 0;
  color: #fff;
  font-size: 32px;
  font-weight: var(--font-weight-bold, 700);
}

.marketing-banner__subtitle {
  margin: 8px 0 0;
  color: rgba(255, 255, 255, 0.92);
  font-size: 14px;
}

.marketing-body {
  width: min(1296px, 92%);
  margin: 0 auto;
  padding: 16px 0 40px;
}

.marketing-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 20px 16px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.marketing-grid--mobile {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 10px;
}

.marketing-more {
  display: flex;
  justify-content: center;
  padding: 24px 0 8px;
}

.marketing-more__btn {
  min-height: 44px;
  padding: 0 48px;
  border: 1px solid var(--colour-border, #e0e0e0);
  border-radius: 22px;
  background: #fff;
  color: var(--colour-text, #1a1a1a);
  font-size: 15px;
  font-weight: var(--font-weight-medium, 500);
  cursor: pointer;
}

.marketing-more__btn:hover {
  border-color: var(--colour-text, #1a1a1a);
}

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

@media (max-width: 1024px) {
  .marketing-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
