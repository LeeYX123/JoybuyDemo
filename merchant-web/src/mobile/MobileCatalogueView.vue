<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import SheetModal from '@/mobile/components/SheetModal.vue'
import { apiRequest, merchantWrite } from '@/lib/api'
import { showToast } from '@/shell'

// 手机壳 商品页（folio route 1/2）：单页双段——「店铺商品」单列卡 /
// 「商品上架中心」两列小卡；搜索框 + 分类底部 sheet 筛选。
// 首页宫格「店铺商品」带 ?view=shop 落到店铺商品段，默认进上架中心。

const route = useRoute()

const PAGE_SIZE = 8

const tab = ref(route.query.view === 'shop' ? 'shop' : 'pool')

const state = reactive({
  loading: false,
  error: '',
  notice: '',
  categories: [],
  // 上架中心（平台商品池）
  poolCategory: 'ALL',
  poolQ: '',
  poolPage: 1,
  poolItems: [],
  poolTotal: 0,
  poolHasNext: false,
  // 店铺商品（本店已上架）
  shopCategory: 'ALL',
  shopQ: '',
  shopPage: 1,
  shopItems: [],
  shopTotal: 0,
  shopHasNext: false,
})

const sheetCategory = ref(false)
const detail = ref(null)
const confirmItem = ref(null)
const confirmBusy = ref(false)
const confirmError = ref('')

async function loadCategories() {
  try {
    const payload = await apiRequest('/merchant/catalog/categories')
    state.categories = payload.items || []
  } catch {
    state.categories = []
  }
}

async function loadPool() {
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page: String(state.poolPage), page_size: String(PAGE_SIZE) })
    if (state.poolCategory !== 'ALL') params.set('category', state.poolCategory)
    if (state.poolQ.trim()) params.set('q', state.poolQ.trim())
    const payload = await apiRequest(`/merchant/catalog/products?${params}`)
    state.poolItems = payload.items || []
    state.poolTotal = payload.total || 0
    state.poolHasNext = Boolean(payload.has_next)
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

async function loadShop() {
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({
      page: String(state.shopPage),
      page_size: String(PAGE_SIZE),
      status: 'ACTIVE',
    })
    if (state.shopCategory !== 'ALL') params.set('category', state.shopCategory)
    if (state.shopQ.trim()) params.set('q', state.shopQ.trim())
    const payload = await apiRequest(`/merchant/listings?${params}`)
    state.shopItems = payload.items || []
    state.shopTotal = payload.total || 0
    state.shopHasNext = Boolean(payload.has_next)
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

function load() {
  if (tab.value === 'shop') loadShop()
  else loadPool()
}

function selectTab(key) {
  if (tab.value === key) return
  tab.value = key
  // 两个段共用错误/提示位，切换时清掉旧文案。
  state.error = ''
  state.notice = ''
  if (key === 'shop' && !state.shopItems.length) loadShop()
  if (key === 'pool' && !state.poolItems.length) loadPool()
}

function submitSearch() {
  if (tab.value === 'shop') {
    state.shopPage = 1
    loadShop()
  } else {
    state.poolPage = 1
    loadPool()
  }
}

function chooseCategory(key) {
  sheetCategory.value = false
  if (tab.value === 'shop') {
    state.shopCategory = key
    state.shopPage = 1
    loadShop()
  } else {
    state.poolCategory = key
    state.poolPage = 1
    loadPool()
  }
}

const currentCategory = computed(() =>
  tab.value === 'shop' ? state.shopCategory : state.poolCategory,
)

const categoryLabel = computed(() => {
  if (currentCategory.value === 'ALL') return '分类'
  return state.categories.find((item) => item.id === currentCategory.value)?.name || '分类'
})

async function submitList() {
  if (!confirmItem.value) return
  confirmBusy.value = true
  confirmError.value = ''
  try {
    await merchantWrite('/merchant/listings', { product_id: confirmItem.value.id })
    confirmItem.value = null
    state.notice = '上架成功，已同步到店铺商品。'
    showToast('上架成功')
    await loadPool()
  } catch (error) {
    confirmError.value = error.message
  } finally {
    confirmBusy.value = false
  }
}

onMounted(async () => {
  await loadCategories()
  // 初始段可能因 ?view=shop 直接落在店铺商品：按当前段取数，不能写死商品池。
  load()
})
</script>

<template>
  <div class="m-page">
    <!-- 双段切换（店铺商品 / 商品上架中心）。 -->
    <div class="m-seg" role="tablist" aria-label="商品页切换">
      <button
        type="button"
        role="tab"
        :aria-selected="tab === 'shop'"
        :class="{ 'is-active': tab === 'shop' }"
        @click="selectTab('shop')"
      >
        店铺商品
      </button>
      <button
        type="button"
        role="tab"
        :aria-selected="tab === 'pool'"
        :class="{ 'is-active': tab === 'pool' }"
        @click="selectTab('pool')"
      >
        商品上架中心
      </button>
    </div>

    <p v-if="state.error" class="m-error">{{ state.error }}</p>
    <p v-if="state.notice" class="m-notice">{{ state.notice }}</p>

    <!-- 搜索框 + 分类（folio catalogue-controls：一行圆角搜索胶囊）。 -->
    <form class="m-controls" role="search" @submit.prevent="submitSearch">
      <input
        v-if="tab === 'shop'"
        v-model="state.shopQ"
        class="m-controls__input"
        type="search"
        enterkeyhint="search"
        placeholder="搜索店铺商品"
        aria-label="搜索商品"
      />
      <input
        v-else
        v-model="state.poolQ"
        class="m-controls__input"
        type="search"
        enterkeyhint="search"
        placeholder="搜索商品名称或 ID"
        aria-label="搜索商品"
      />
      <button type="submit" class="m-controls__action">搜索</button>
      <button
        type="button"
        class="m-controls__action m-controls__filter"
        aria-haspopup="dialog"
        @click="sheetCategory = true"
      >
        {{ categoryLabel }}
      </button>
    </form>

    <p v-if="state.loading" class="m-loading">加载中…</p>

    <!-- 店铺商品：单列卡（folio products 74px 图 + 文本）。 -->
    <template v-else-if="tab === 'shop'">
      <div v-if="state.shopItems.length" class="m-list">
        <article v-for="row in state.shopItems" :key="row.offer_id" class="m-card m-shop-item">
          <span class="m-shop-item__media">
            <img v-if="row.image" :src="row.image" alt="" />
            <span v-else class="m-shop-item__empty">无图</span>
          </span>
          <span class="m-shop-item__body">
            <strong>{{ row.name }}</strong>
            <small class="m-num">{{ row.product_id.slice(0, 8) }}…</small>
            <small>{{ row.merchant_category_label || row.category?.name_zh || '未分类' }}</small>
            <span class="m-shop-item__prices">
              <b class="m-num">成本 ¥ {{ row.cost || '—' }}</b>
              <b class="m-num">零售 ¥ {{ row.price }}</b>
            </span>
            <span class="m-shop-item__meta">
              <span class="m-tag m-tag--ok">已上架</span>
              <small>{{ row.listed_at ? row.listed_at.slice(0, 10) : '—' }}</small>
            </span>
          </span>
        </article>
        <p class="m-hint">如需下架商品，请联系平台客服，由管理端代为操作。</p>
      </div>
      <p v-else class="m-empty">还没有上架任何商品，去「商品上架中心」挑一件吧。</p>
      <div v-if="state.shopTotal" class="m-pager">
        <button type="button" class="m-btn" :disabled="state.shopPage <= 1" @click="state.shopPage -= 1; loadShop()">上一页</button>
        <span class="m-num">第 {{ state.shopPage }} 页 · 共 {{ state.shopTotal }} 件</span>
        <button type="button" class="m-btn" :disabled="!state.shopHasNext" @click="state.shopPage += 1; loadShop()">下一页</button>
      </div>
    </template>

    <!-- 商品上架中心：两列小卡（folio merchant-catalogue 两列）。 -->
    <template v-else>
      <div v-if="state.poolItems.length" class="m-grid2">
        <article v-for="item in state.poolItems" :key="item.id" class="m-card m-pool-item">
          <span class="m-pool-item__media">
            <img v-if="item.images && item.images.length" :src="item.images[0]" alt="" />
            <span v-else class="m-shop-item__empty">无图</span>
            <span v-if="item.activity" class="m-tag m-tag--warn m-pool-item__badge">活动</span>
            <span v-if="item.listed" class="m-tag m-tag--ok m-pool-item__badge">已上架</span>
          </span>
          <span class="m-pool-item__body">
            <strong>{{ item.name }}</strong>
            <small>{{ item.merchant_category_label || item.category?.name_zh || '未分类' }}</small>
            <span class="m-pool-item__prices">
              <span><small>成本价</small><b class="m-num">¥ {{ item.cost || '未定价' }}</b></span>
              <span><small>零售价</small><b class="m-num">¥ {{ item.price || '未定价' }}</b></span>
            </span>
            <button type="button" class="m-btn m-btn--block" @click="detail = item">查看详情</button>
            <button
              type="button"
              class="m-btn m-btn--primary m-btn--block"
              :disabled="item.listed || !item.can_list"
              @click="confirmItem = item; confirmError = ''"
            >
              {{ item.listed ? '已上架' : '上架商品' }}
            </button>
          </span>
        </article>
      </div>
      <p v-else class="m-empty">没有匹配的商品，换个关键词或品类试试。</p>
      <div v-if="state.poolTotal" class="m-pager">
        <button type="button" class="m-btn" :disabled="state.poolPage <= 1" @click="state.poolPage -= 1; loadPool()">上一页</button>
        <span class="m-num">第 {{ state.poolPage }} 页 · 共 {{ state.poolTotal }} 件</span>
        <button type="button" class="m-btn" :disabled="!state.poolHasNext" @click="state.poolPage += 1; loadPool()">下一页</button>
      </div>
    </template>

    <!-- 分类筛选底部 sheet。 -->
    <SheetModal :open="sheetCategory" title="商品分类" @close="sheetCategory = false">
      <div class="m-sheet-options">
        <button
          type="button"
          :aria-pressed="currentCategory === 'ALL'"
          :class="{ 'is-active': currentCategory === 'ALL' }"
          @click="chooseCategory('ALL')"
        >
          全部分类
        </button>
        <button
          v-for="category in state.categories"
          :key="category.id"
          type="button"
          :aria-pressed="currentCategory === category.id"
          :class="{ 'is-active': currentCategory === category.id }"
          @click="chooseCategory(category.id)"
        >
          {{ category.name }}
        </button>
      </div>
    </SheetModal>

    <!-- 商品详情 sheet。 -->
    <SheetModal :open="Boolean(detail)" :title="detail?.name || '商品详情'" @close="detail = null">
      <template v-if="detail">
        <div class="m-detail-img">
          <img v-if="detail.images && detail.images.length" :src="detail.images[0]" alt="" />
          <span v-else>无图</span>
        </div>
        <dl class="m-dl">
          <div><dt>商品 ID</dt><dd class="m-num">{{ detail.id }}</dd></div>
          <div><dt>品类</dt><dd>{{ detail.merchant_category_label || detail.category?.name_zh || '未分类' }}</dd></div>
          <div><dt>成本价</dt><dd class="m-num">¥ {{ detail.cost || '未定价' }}</dd></div>
          <div><dt>零售价</dt><dd class="m-num">¥ {{ detail.price || '未定价' }}</dd></div>
        </dl>
        <p class="m-hint">平台统一维护商品规格与销售范围。商品上架后，如需下架请联系客服处理。</p>
        <button
          type="button"
          class="m-btn m-btn--primary m-btn--block"
          :disabled="detail.listed || !detail.can_list"
          @click="confirmItem = detail; confirmError = ''"
        >
          {{ detail.listed ? '已上架' : '上架至店铺' }}
        </button>
      </template>
    </SheetModal>

    <!-- 上架确认 sheet。 -->
    <SheetModal :open="Boolean(confirmItem)" title="确认上架" @close="confirmItem = null">
      <p v-if="confirmItem" class="m-hint" style="margin: 0 0 12px">
        把「{{ confirmItem.name }}」上架到你的店铺？上架后立即出现在店铺商品列表。
      </p>
      <p v-if="confirmError" class="m-error">{{ confirmError }}</p>
      <div class="m-sheet-actions">
        <button type="button" class="m-btn" :disabled="confirmBusy" @click="confirmItem = null">取消</button>
        <button type="button" class="m-btn m-btn--primary" :disabled="confirmBusy" @click="submitList">
          {{ confirmBusy ? '上架中…' : '确认上架' }}
        </button>
      </div>
    </SheetModal>
  </div>
</template>

<style scoped>
.m-seg {
  display: flex;
  gap: 4px;
  padding: 4px;
  border: 1px solid var(--m-line);
  border-radius: var(--m-radius);
  background: var(--m-paper);
}

.m-seg button {
  flex: 1;
  min-height: 38px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--m-muted);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.m-seg button.is-active {
  background: var(--m-tint);
  color: var(--m-accent);
}

.m-controls {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 4px 3px 12px;
  border: 1px solid var(--m-line);
  border-radius: 10px;
  background: var(--m-paper);
}

.m-controls__input {
  flex: 1 1 0;
  width: 0;
  min-width: 0;
  min-height: 40px;
  border: 0;
  background: transparent;
  font-size: 16px;
  color: var(--m-ink);
}

.m-controls__input:focus-visible {
  outline: none;
}

.m-controls__action {
  flex: none;
  min-height: 40px;
  padding: 0 8px;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: var(--m-accent);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.m-controls__filter {
  border-left: 1px solid var(--m-line);
}

/* 店铺商品单列卡。 */
.m-list {
  display: grid;
  gap: var(--m-space-2);
}

.m-shop-item {
  display: grid;
  grid-template-columns: 74px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
  padding: 10px;
}

.m-shop-item__media {
  width: 74px;
  height: 82px;
  display: grid;
  place-items: center;
  border-radius: 5px;
  background: #f2f4f6;
  overflow: hidden;
}

.m-shop-item__media img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.m-shop-item__empty {
  font-size: 11px;
  color: var(--m-muted);
}

.m-shop-item__body {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.m-shop-item__body strong {
  min-height: 20px;
  font-size: 14px;
  line-height: 1.45;
  color: var(--m-ink);
  overflow-wrap: anywhere;
}

.m-shop-item__body small {
  color: var(--m-muted);
  font-size: 12px;
}

.m-shop-item__prices {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
  margin-top: 2px;
}

.m-shop-item__prices b {
  font-size: 13px;
  color: var(--m-ink);
}

.m-shop-item__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
}

.m-shop-item__meta small {
  color: var(--m-muted);
}

/* 上架中心两列卡。 */
.m-grid2 {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px 12px;
}

.m-pool-item {
  display: block;
  border-radius: 9px;
}

.m-pool-item__media {
  position: relative;
  display: grid;
  place-items: center;
  width: 100%;
  aspect-ratio: 1;
  background: #f3f5f7;
  overflow: hidden;
}

.m-pool-item__media img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.m-pool-item__badge {
  position: absolute;
  left: 6px;
  top: 6px;
}

.m-pool-item__body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px;
}

.m-pool-item__body strong {
  font-size: 14px;
  line-height: 1.45;
  color: var(--m-ink);
  overflow-wrap: anywhere;
}

.m-pool-item__body > small {
  color: var(--m-muted);
  font-size: 12px;
}

.m-pool-item__prices {
  display: flex;
  gap: 6px 10px;
  flex-wrap: wrap;
}

.m-pool-item__prices span {
  display: grid;
}

.m-pool-item__prices small {
  font-size: 10px;
  color: var(--m-muted);
}

.m-pool-item__prices b {
  font-size: 14px;
  color: var(--m-ink);
}

/* 分页行。 */
.m-pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--m-space-2);
}

.m-pager span {
  font-size: 12px;
  color: var(--m-muted);
}

.m-pager .m-btn {
  min-height: 40px;
  padding: 0 14px;
}

/* sheet 选项（folio sheet-options）。 */
.m-sheet-options {
  display: grid;
  gap: var(--m-space-2);
}

.m-sheet-options button {
  min-height: var(--m-target);
  padding: 8px 12px;
  border: 1px solid var(--m-line);
  border-radius: 5px;
  background: var(--m-paper);
  color: var(--m-ink);
  font-size: 14px;
  text-align: left;
  cursor: pointer;
}

.m-sheet-options button.is-active {
  border-color: var(--m-accent);
  background: var(--m-tint);
  color: var(--m-accent);
  font-weight: 650;
}

.m-sheet-options button.is-active::after {
  content: '✓';
  margin-left: 6px;
}

.m-detail-img {
  display: grid;
  place-items: center;
  height: 150px;
  border-radius: var(--m-radius);
  background: #f3f5f7;
  color: var(--m-muted);
  font-size: 12px;
  overflow: hidden;
  margin-bottom: var(--m-space-3);
}

.m-detail-img img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.m-dl {
  display: grid;
  gap: 10px;
  margin: 0 0 12px;
}

.m-dl > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
}

.m-dl dt {
  color: var(--m-muted);
  flex: none;
}

.m-dl dd {
  margin: 0;
  color: var(--m-ink);
  text-align: right;
  overflow-wrap: anywhere;
}

.m-sheet-actions {
  display: flex;
  gap: var(--m-space-2);
}

.m-sheet-actions .m-btn {
  flex: 1;
}
</style>
