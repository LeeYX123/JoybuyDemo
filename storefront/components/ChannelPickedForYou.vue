<script setup>
// 频道页底部【精选好物 / Picked for you】（需求文档03 13.4，2026-11-19）。
//
// 交互（精确口径）：
//   1. 首屏一批（SSR 渲染，无布局闪动）；
//   2. 滚动到模块底部 → 第一次自动异步加载下一批；
//   3. 之后滚动到底出现【查看更多】按钮，点击加载下一批；
//   4. 数据池耗尽后循环重复（接口 cycle=1 取模，从头再来）。
// 卡片与楼层商品卡同款（无边框）；接口为扩展的
// GET /api/v1/recommendations?category=<slug>&page=N&cycle=1。
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useFetch, useRuntimeConfig } from '#imports'

import { useLocale } from '../composables/useLocale'
import { useMarketLocale } from '../composables/useMarketLocale'

import AppMoreButton from './AppMoreButton.vue'

const props = defineProps({
  // 需求 13.7-3：购物车页复用本组件时不传 categorySlug = 全库随机池
  // （接口不带 category 参数即全库，批次 I 后端口径）。
  categorySlug: {
    type: String,
    default: '',
  },
  // 需求 16.4：频道页底部按钮文案【更多 / More】（传 channel.more）；购物车页
  // 不传，沿用「查看更多」。
  moreLabel: {
    type: String,
    default: '',
  },
  // 2026-11-24 频道页【精选好物】卡片与楼层卡同款：楼层卡没有评分行、按后台
  // 零售价展示（不显示划线价/Promo 标签）。默认值与改前完全一致（有评分、
  // 普通价格口径），因此购物车页复用不受影响；只有频道页显式传 false/true。
  // 推荐接口不带 retail_price 时 ProductCard 自动回退 price_min（不报错、不显示 $0.00）。
  showRating: {
    type: Boolean,
    default: true,
  },
  useRetailPrice: {
    type: Boolean,
    default: false,
  },
  showBrand: {
    type: Boolean,
    default: true,
  },
  // 每批 = 接口一页（24 件，RECOMMENDATION_PAGE_SIZE）。真站 ForYou 接口被
  // 风控挡（403）无法实测每批数量，与首页【为您推荐】同口径（measurement.md §4）。
})

const { t } = useLocale()
const { apiQuery } = useMarketLocale()
const config = useRuntimeConfig()

function recoUrl(page) {
  const query = new URLSearchParams({
    ...apiQuery.value,
    page: String(page),
    cycle: '1', // 池子耗尽后取模循环；页号未超池时行为与普通请求一致
  })
  if (props.categorySlug) query.set('category', props.categorySlug)
  return import.meta.server
    ? `${config.apiBaseInternal}/recommendations?${query.toString()}`
    : `/api/v1/recommendations?${query.toString()}`
}

// 首屏一批走 SSR。
const { data: firstBatch } = await useFetch(() => recoUrl(1), {
  key: computed(
    () => `picked-for-you-${props.categorySlug || 'all'}-${apiQuery.value.locale || ''}`,
  ),
  default: () => ({}),
})

const items = ref([...(firstBatch.value?.items || [])])
const requestPage = ref(1)
const loading = ref(false)
// 第一次滚动自动加载完成后，改为【查看更多】按钮点击加载（13.4 第 3 步）。
const autoLoaded = ref(false)

const hasItems = computed(() => items.value.length > 0)

async function loadNextBatch() {
  if (loading.value || !hasItems.value) return
  loading.value = true
  try {
    requestPage.value += 1
    const batch = await $fetch(recoUrl(requestPage.value))
    const batchItems = Array.isArray(batch?.items) ? batch.items : []
    items.value.push(...batchItems)
  } catch {
    // 单次加载失败静默：按钮仍在，用户可重试。
  } finally {
    loading.value = false
  }
}

const sentinel = ref(null)
let observer = null

onMounted(() => {
  if (typeof IntersectionObserver === 'undefined' || !sentinel.value) return
  observer = new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting) && !autoLoaded.value) {
        autoLoaded.value = true
        observer?.disconnect()
        observer = null
        loadNextBatch()
      }
    },
    { rootMargin: '120px 0px' },
  )
  observer.observe(sentinel.value)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
})
</script>

<template>
  <section v-if="hasItems" class="picked-for-you" :aria-label="t('reco.pickedForYou')">
    <h2 class="picked-for-you__title">{{ t('reco.pickedForYou') }}</h2>
    <ul class="picked-for-you__grid">
      <li v-for="(product, index) in items" :key="`${product.spu_public_id}-${index}`">
        <ProductCard
          :product="product"
          :show-rating="props.showRating"
          :use-retail-price="props.useRetailPrice"
          :show-brand="props.showBrand"
        />
      </li>
    </ul>
    <!-- 模块底部哨兵：进入视口触发第一次自动加载（13.4 第 2 步）。 -->
    <div ref="sentinel" class="picked-for-you__sentinel" aria-hidden="true"></div>
    <div v-if="loading" class="picked-for-you__loading" role="status">
      <span class="picked-for-you__spinner" aria-hidden="true"></span>
      {{ t('reco.loading') }}
    </div>
    <div v-else-if="autoLoaded" class="picked-for-you__more">
      <!-- 需求 16.4：与首页【查看更多】同一份按钮实现（AppMoreButton）。 -->
      <AppMoreButton class="picked-for-you__more-btn" :disabled="loading" @click="loadNextBatch">
        {{ props.moreLabel || t('reco.viewMore') }}
      </AppMoreButton>
    </div>
  </section>
</template>

<style scoped>
.picked-for-you__title {
  margin: 0;
  font-size: 1.75rem;
  line-height: 1.3;
  font-weight: var(--font-weight-semibold);
  color: var(--colour-text);
}

/* 6 列网格（与商品楼层同规格，measurement.md §2），窄屏按既有断点降列。 */
.picked-for-you__grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 20px;
  margin-top: var(--space-4);
}

.picked-for-you__grid :deep(.product-card) {
  border: 0;
  padding: 0;
  background: transparent;
}

.picked-for-you__sentinel {
  height: 1px;
}

.picked-for-you__loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  min-height: 56px;
  margin-top: var(--space-4);
  color: var(--colour-text-secondary);
}

.picked-for-you__spinner {
  width: 1.25rem;
  height: 1.25rem;
  border: 2px solid var(--colour-border);
  border-top-color: var(--colour-accent);
  border-radius: 50%;
  animation: picked-for-you-spin 0.8s linear infinite;
}

@keyframes picked-for-you-spin {
  to {
    transform: rotate(360deg);
  }
}

.picked-for-you__more {
  display: flex;
  justify-content: center;
  margin-top: var(--space-4);
}

@media (max-width: 80rem) {
  .picked-for-you__grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

@media (max-width: 48rem) {
  .picked-for-you__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
