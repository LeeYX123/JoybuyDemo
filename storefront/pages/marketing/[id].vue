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
import AppMoreButton from '../../components/AppMoreButton.vue'
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
  // 真站营销页没有 body 背景规则（浏览器默认纯白）；我们全局主题给 body 上了
  // --colour-canvas(#F6F7F9)，用户报「背景不是纯白」。只在本页把 body 底色改成
  // 白色（unhead 随组件卸载回收，不动全局 token）。
  bodyAttrs: { style: 'background-color: #ffffff' },
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
        <AppMoreButton @click="onReveal">
          {{ t('activity.viewMore') }}
        </AppMoreButton>
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
  /* 真站营销页无 body 背景规则（默认纯白）；用户报「背景不是纯白」，本页作用域内改白，
     不动全局 --colour-canvas。 */
  background: #ffffff;
}

/* banner：真站 .BackGroundImage_backgroundImage 实测——高 384、图按高度铺满
   （background-size: auto 100%，1440 宽下 1865×384 原图左右裁切）、容器 1264、
   标题 44/700/44 + 下边距 12、副标题 18/500/24。真站无窄屏高度断点，390 宽同为 384。 */
.marketing-banner {
  display: flex;
  align-items: center;
  height: 384px;
  background-color: #2e3577;
  background-repeat: no-repeat;
  background-size: auto 100%;
  background-position: center;
}

.marketing-banner__inner {
  width: min(1264px, calc(100% - 48px));
  margin: 0 auto;
}

.marketing-banner__title {
  display: block;
  width: 632px;
  max-width: 100%;
  margin: 0 0 12px;
  overflow: visible;
  color: #fff;
  font-size: 44px;
  font-weight: 700;
  line-height: 44px;
  word-break: break-word;
}

.marketing-banner__subtitle {
  display: block;
  width: 632px;
  max-width: 100%;
  margin: 0;
  overflow: visible;
  color: #fff;
  font-size: 18px;
  font-weight: 500;
  line-height: 24px;
  word-break: break-word;
}

.marketing-body {
  /* 与真站容器一致（1264），让 banner 标题与网格左缘对齐。 */
  width: min(1264px, calc(100% - 48px));
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

/* 真站 .style_footer__2m0ZT：宽 100%、上下 24、居中；按钮样式由共用
   AppMoreButton 提供（131×48 / #1A1A1A / 白字 / radius 4 / 16px 500），
   与真站 .style_btn__T8rQQ 实测值一致。文案用 activity.viewMore（查看更多）。 */
.marketing-more {
  display: flex;
  justify-content: center;
  margin: 24px 0;
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
