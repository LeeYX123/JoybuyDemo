<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useFetch, useRuntimeConfig } from '#imports'

import { useLocale } from '../../composables/useLocale'

import AppMoreButton from '../AppMoreButton.vue'

// Home "Recommended for you" floor (需求文档03 11.6), mounted right below the
// Bestsellers floor. Real-site note (2026-11-19, var/reco_pdp_20261119/):
// the current joybuy.co.uk homepage has no live reco module, so the floor
// follows the measured site floor conventions instead — 28px/600 title,
// 5-column grid with 16px gutters, no personalisation tab row.
// Data comes from /api/v1/recommendations: a deterministic (md5 of spu id)
// cross-category pool capped at 240 items, 24 per page, appended on click.
const { t } = useLocale()
const config = useRuntimeConfig()

const PAGE_SIZE = 24
const MAX_ITEMS = 240
// 16.2（含 2026-11-20 修正）：任何时刻最后一行都要满格。展示列表在渲染时用
// 池头（已加载列表开头）循环补齐到当前列数的整数倍——首屏 24 件同样补齐
// （桌面 5 列 → 25 件）。补齐只发生在 computed 里，appended 仍只存接口数据。
// 列数与 .home-reco__grid 的断点保持一致：>80rem 5 列、≤80rem 3 列、≤48rem 2 列。
const DESKTOP_COLUMNS = 5
const COLUMN_BREAKPOINTS = [
  { query: '(max-width: 48rem)', columns: 2 },
  { query: '(max-width: 80rem)', columns: 3 },
]
// SSR/首屏按桌面 5 列渲染，客户端 hydrate 后再按实际视口列数补齐（避免
// 服务端与客户端列数不同导致的 hydration mismatch）。
const columns = ref(DESKTOP_COLUMNS)
let columnListeners = []

const page = ref(1)
const appended = ref([])
const loading = ref(false)
const loadError = ref(false)
const loadEnded = ref(false)

const firstUrl = import.meta.server
  ? `${config.apiBaseInternal}/recommendations?page=1`
  : '/api/v1/recommendations?page=1'

// 首屏 24 件必须 await：SSR 等数据就绪再渲染真实列表（O1 修复——非 await 时
// 服务端 setup 阶段 data 还是 null，SSR 渲染「Loading…」而客户端 payload 已有
// 24 件，hydration 必 mismatch）。key 用静态字符串（模板字符串 key 冻结旧坑）。
const { data } = await useFetch(() => firstUrl, {
  key: 'home-recommended-page1',
})

// 首屏列表始终从 data 派生（SSR/客户端/hydration 三态一致），点击追加的页放进
// appended；不能在 setup 里把 data.value.items 拷进本地 ref——那正是 O1 的根因。
const loadedItems = computed(() => {
  const first = Array.isArray(data.value?.items) ? data.value.items : []
  return [...first, ...appended.value]
})

// 渲染列表 = 已加载商品 + 池头循环补齐（允许重复商品；模板 key 带下标，重复项
// 不会触发重复 key / hydration 告警）。不用占位骨架/灰块。
const items = computed(() => {
  const list = loadedItems.value
  const cols = columns.value
  if (list.length === 0 || !cols) return list
  const remainder = list.length % cols
  if (remainder === 0) return list
  const needed = cols - remainder
  return [...list, ...list.slice(0, needed)]
})

// 240 上限由后端池保证；前端按"已加载页数"与"池上限"判断是否到底（用接口
// 数据条数，不受补齐影响）。
const reachedEnd = computed(
  () =>
    loadedItems.value.length >= MAX_ITEMS ||
    (data.value && loadedItems.value.length >= data.value.total),
)

function syncColumns() {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
  const matched = COLUMN_BREAKPOINTS.find((bp) => window.matchMedia(bp.query).matches)
  columns.value = matched ? matched.columns : DESKTOP_COLUMNS
}

onMounted(() => {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
  columnListeners = COLUMN_BREAKPOINTS.map((bp) => window.matchMedia(bp.query))
  columnListeners.forEach((mq) => mq.addEventListener?.('change', syncColumns))
  syncColumns()
})

onBeforeUnmount(() => {
  columnListeners.forEach((mq) => mq.removeEventListener?.('change', syncColumns))
  columnListeners = []
})

async function loadMore() {
  if (loading.value || loadEnded.value) return
  loading.value = true
  loadError.value = false
  try {
    const next = page.value + 1
    const response = await $fetch(`/api/v1/recommendations?page=${next}`)
    const batch = Array.isArray(response?.items) ? response.items : []
    appended.value = [...appended.value, ...batch]
    page.value = next
    if (batch.length < PAGE_SIZE || loadedItems.value.length >= MAX_ITEMS) {
      loadEnded.value = true
    }
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="home-reco" aria-labelledby="home-reco-title">
    <header class="home-reco__head">
      <h2 id="home-reco-title" class="home-reco__title">{{ t('home.reco.title') }}</h2>
    </header>

    <ul v-if="items.length > 0" class="home-reco__grid">
      <li v-for="(item, index) in items" :key="`${item.spu_public_id}-${index}`">
        <ProductCard :product="item" />
      </li>
    </ul>
    <p v-else class="home-reco__empty" role="status">{{ t('home.reco.loading') }}</p>

    <div v-if="items.length > 0 && !reachedEnd" class="home-reco__more">
      <AppMoreButton class="home-reco__more-btn" :disabled="loading" @click="loadMore">
        {{
          loadError
            ? t('home.reco.viewMore')
            : loading
              ? t('home.reco.loading')
              : t('home.reco.viewMore')
        }}
      </AppMoreButton>
    </div>
    <p v-else-if="items.length > 0" class="home-reco__end" role="status">
      {{ t('home.reco.allLoaded') }}
    </p>
  </section>
</template>

<style scoped>
/* Floor spacing below Bestsellers matches the real floor rhythm (48px). */
.home-reco {
  margin-top: 48px;
}

/* Measured real-site floor title: 28px/600 #1A1A1A, 4px to the grid. */
.home-reco__head {
  margin-bottom: 4px;
}

.home-reco__title {
  margin: 0;
  font-size: 1.75rem;
  font-weight: var(--font-weight-semibold);
  color: #1a1a1a;
}

/* Measured real-site bestsellers grid: 5 columns, 16px gutters. */
.home-reco__grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 16px;
  margin-top: var(--space-4);
  list-style: none;
  padding: 0;
}

.home-reco__empty {
  margin-block: var(--space-8);
  color: var(--colour-muted);
  text-align: center;
}

/* 16.2：底部按钮区增加 60px 下留白。 */
.home-reco__more {
  margin-top: 32px;
  padding-bottom: 60px;
  text-align: center;
}

.home-reco__end {
  margin-top: 32px;
  color: var(--colour-muted);
  text-align: center;
}

@media (max-width: 80rem) {
  .home-reco__grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 48rem) {
  .home-reco__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
