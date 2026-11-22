<script setup>
import { computed, onMounted, reactive } from 'vue'

import AppDrawer from '@/components/AppDrawer.vue'
import AppModal from '@/components/AppModal.vue'
import AppPager from '@/components/AppPager.vue'
import { apiRequest, merchantWrite } from '@/lib/api'

const PAGE_SIZE = 8

const state = reactive({
  tab: 'pool',
  category: 'ALL',
  q: '',
  page: 1,
  loading: true,
  error: '',
  notice: '',
  items: [],
  total: 0,
  hasNext: false,
  categories: [],
  listings: [],
  listingTotal: 0,
  listingPage: 1,
  listingHasNext: false,
  // 本店已上架 Tab 的搜索与品类筛选（文档 M02：商品名称/ID 搜索 + 已上架品类导航）。
  listingCategory: 'ALL',
  listingQ: '',
})

const detail = reactive({ value: null, open: false, loading: false, error: '', requestId: 0 })
const confirm = reactive({ value: null, open: false, busy: false, error: '' })

const listedCount = computed(() => state.listings.length && state.listingTotal)
const poolEmpty = computed(() => !state.loading && !state.items.length)

// --- 查看详情：图文区块 / 规格（数据来自商家端单品详情接口）---
const detailSections = computed(() =>
  (detail.value?.content_sections || []).filter(
    (section) =>
      (section.blocks || []).some((block) => block.text) ||
      section.text ||
      (section.images || []).length,
  ),
)
// 历史兜底：没有结构化图文区块时，用纯文本描述。
const detailText = computed(() => (detail.value?.description || '').trim())
const specTables = computed(() =>
  (detail.value?.specification_tables || []).filter((table) => (table.rows || []).length),
)
// 没有规格表时用平铺规格参数（SpuDetail.specifications / Spu.specs）。
const flatSpecs = computed(() => {
  if (specTables.value.length) return []
  const detailed = detail.value?.specifications || []
  if (detailed.length) return detailed
  return detail.value?.specs || []
})
// 再兜底：从 SKU 的规格字典汇总「属性 → 可选值」。
const skuSpecs = computed(() => {
  if (specTables.value.length || flatSpecs.value.length) return []
  const buckets = new Map()
  for (const sku of detail.value?.skus || []) {
    for (const [name, value] of Object.entries(sku.specification || {})) {
      if (value === null || value === undefined || value === '') continue
      const values = buckets.get(name) || []
      if (!values.includes(String(value))) values.push(String(value))
      buckets.set(name, values)
    }
  }
  return [...buckets.entries()].map(([name, values]) => ({
    name,
    value: values.join(' / '),
  }))
})
// 最后兜底：爬虫规格选项（只有可选值、没有表格时）。
const specOptionChips = computed(() => {
  if (specTables.value.length || flatSpecs.value.length || skuSpecs.value.length) return []
  return (detail.value?.spec_options || []).filter((option) => (option.values || []).length)
})

async function loadCategories() {
  const payload = await apiRequest('/merchant/catalog/categories')
  state.categories = payload.items || []
}

async function loadPool() {
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({
      page: String(state.page),
      page_size: String(PAGE_SIZE),
    })
    if (state.category && state.category !== 'ALL') params.set('category', state.category)
    if (state.q.trim()) params.set('q', state.q.trim())
    const payload = await apiRequest(`/merchant/catalog/products?${params}`)
    state.items = payload.items || []
    state.total = payload.total || 0
    state.hasNext = Boolean(payload.has_next)
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

async function loadListingCount() {
  try {
    const payload = await apiRequest('/merchant/listings?page=1&page_size=1&status=ACTIVE')
    state.listingTotal = payload.total || 0
  } catch {
    // 计数失败不影响商品池浏览，忽略即可。
  }
}

async function loadListings() {
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({
      page: String(state.listingPage),
      page_size: String(PAGE_SIZE),
      status: 'ACTIVE',
    })
    if (state.listingCategory && state.listingCategory !== 'ALL') {
      params.set('category', state.listingCategory)
    }
    if (state.listingQ.trim()) params.set('q', state.listingQ.trim())
    const payload = await apiRequest(`/merchant/listings?${params}`)
    state.listings = payload.items || []
    state.listingTotal = payload.total || 0
    state.listingHasNext = Boolean(payload.has_next)
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

function selectListingCategory(key) {
  state.listingCategory = key
  state.listingPage = 1
  loadListings()
}

function searchListings() {
  state.listingPage = 1
  loadListings()
}

function selectCategory(key) {
  state.category = key
  state.page = 1
  loadPool()
}

function search() {
  state.page = 1
  loadPool()
}

function goPage(page) {
  state.page = page
  loadPool()
}

function goListingPage(page) {
  state.listingPage = page
  loadListings()
}

function selectTab(key) {
  state.tab = key
  if (key === 'pool') loadPool()
  else loadListings()
}

async function openDetail(item) {
  // 先用列表行数据占位，避免抽屉空白；再拉单品详情补图文区块与规格。
  const requestId = detail.requestId + 1
  detail.requestId = requestId
  detail.value = item
  detail.open = true
  detail.loading = true
  detail.error = ''
  try {
    const payload = await apiRequest(`/merchant/catalog/products/${item.id}`)
    if (detail.requestId !== requestId || !detail.open) return
    detail.value = { ...item, ...(payload.product || {}) }
  } catch (error) {
    if (detail.requestId !== requestId) return
    detail.error = error.message
  } finally {
    if (detail.requestId === requestId) detail.loading = false
  }
}

function closeDetail() {
  detail.requestId += 1
  detail.open = false
  detail.value = null
  detail.loading = false
  detail.error = ''
}

function askList(item) {
  confirm.value = item
  confirm.open = true
  confirm.error = ''
}

function closeConfirm() {
  if (confirm.busy) return
  confirm.open = false
  confirm.value = null
}

async function submitList() {
  if (!confirm.value) return
  confirm.busy = true
  confirm.error = ''
  try {
    await merchantWrite('/merchant/listings', { product_id: confirm.value.id })
    confirm.open = false
    confirm.value = null
    state.notice = '上架成功，已同步到店铺商品。'
    await loadPool()
  } catch (error) {
    confirm.error = error.message
  } finally {
    confirm.busy = false
  }
}

onMounted(async () => {
  await loadCategories().catch(() => {})
  await Promise.all([loadPool(), loadListingCount()])
})
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>商品上架中心</h1>
        <p>从平台商品池挑选商品上架到你自己的店铺，成本与零售价分开显示。</p>
      </div>
    </div>

    <p v-if="state.error" class="notice notice--error">{{ state.error }}</p>
    <p v-if="state.notice" class="notice notice--ok">{{ state.notice }}</p>

    <div class="tabs">
      <button
        type="button"
        :class="{ 'is-active': state.tab === 'pool' }"
        @click="selectTab('pool')"
      >
        平台商品池
      </button>
      <button
        type="button"
        :class="{ 'is-active': state.tab === 'listing' }"
        @click="selectTab('listing')"
      >
        本店已上架
      </button>
      <span class="tabs__count tag">已上架 {{ state.listingTotal || listedCount || 0 }} 件</span>
    </div>

    <template v-if="state.tab === 'pool'">
      <div class="toolbar">
        <div class="chip-row">
          <button
            type="button"
            class="chip"
            :class="{ 'is-active': state.category === 'ALL' }"
            @click="selectCategory('ALL')"
          >
            全部
          </button>
          <button
            v-for="category in state.categories"
            :key="category.id"
            type="button"
            class="chip"
            :class="{ 'is-active': state.category === category.id }"
            @click="selectCategory(category.id)"
          >
            {{ category.name }}
          </button>
        </div>
      </div>
      <!-- 搜索框独立成行（不跟品类挤在一行）。 -->
      <form class="search-row" @submit.prevent="search">
        <input v-model="state.q" type="search" placeholder="输入商品名称或 ID 搜索" />
        <button type="submit" class="btn btn--primary">搜索</button>
      </form>

      <p v-if="state.loading" class="inline-loading">加载中…</p>
      <p v-else-if="poolEmpty" class="empty-state">没有匹配的商品，换个关键词或品类试试。</p>

      <div v-else class="product-grid">
        <article v-for="item in state.items" :key="item.id" class="product-card">
          <div class="product-card__media">
            <img v-if="item.images && item.images.length" :src="item.images[0]" :alt="item.name" />
            <span v-else>无图</span>
            <span v-if="item.activity" class="tag tag--red product-card__badge">活动</span>
            <span v-if="item.listed" class="tag tag--ok product-card__badge">已上架</span>
          </div>
          <div class="product-card__body">
            <h3 :title="item.name">{{ item.name }}</h3>
            <p class="product-card__meta">
              {{ item.merchant_category_label || item.category?.name_zh || '未分类' }}
            </p>
            <div class="product-card__prices">
              <div>
                <span class="product-card__label">成本价</span>
                <b class="num">¥ {{ item.cost || '未定价' }}</b>
              </div>
              <div>
                <span class="product-card__label">零售价</span>
                <b class="num">¥ {{ item.price || '未定价' }}</b>
              </div>
            </div>
            <div class="product-card__actions">
              <button type="button" class="btn btn--sm" @click="openDetail(item)">查看详情</button>
              <button
                type="button"
                class="btn btn--sm btn--primary"
                :disabled="item.listed || !item.can_list"
                @click="askList(item)"
              >
                {{ item.listed ? '已上架' : '上架商品' }}
              </button>
            </div>
          </div>
        </article>
      </div>

      <AppPager
        :page="state.page"
        :page-size="PAGE_SIZE"
        :total="state.total"
        :has-next="state.hasNext"
        @change="goPage"
      />
    </template>

    <template v-else>
      <div class="toolbar">
        <div class="chip-row">
          <button
            type="button"
            class="chip"
            :class="{ 'is-active': state.listingCategory === 'ALL' }"
            @click="selectListingCategory('ALL')"
          >
            全部
          </button>
          <button
            v-for="category in state.categories"
            :key="category.id"
            type="button"
            class="chip"
            :class="{ 'is-active': state.listingCategory === category.id }"
            @click="selectListingCategory(category.id)"
          >
            {{ category.name }}
          </button>
        </div>
      </div>
      <form class="search-row" @submit.prevent="searchListings">
        <input v-model="state.listingQ" type="search" placeholder="输入商品名称或 ID 搜索" />
        <button type="submit" class="btn btn--primary">搜索</button>
      </form>

      <div class="card">
        <div class="card__body">
          <div v-if="state.listings.length" class="data-table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>商品</th>
                  <th>品类</th>
                  <th>成本价</th>
                  <th>零售价</th>
                  <th>上架时间</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in state.listings" :key="row.offer_id">
                  <td>
                    <div class="listing-cell">
                      <img
                        v-if="row.image"
                        :src="row.image"
                        :alt="row.name"
                        class="listing-cell__img"
                      />
                      <span v-else class="listing-cell__img listing-cell__img--empty">无图</span>
                      <div>
                        <div class="cell-strong">{{ row.name }}</div>
                        <div class="cell-sub mono">{{ row.product_id.slice(0, 8) }}…</div>
                      </div>
                    </div>
                  </td>
                  <td>
                    {{ row.merchant_category_label || row.category?.name_zh || '未分类' }}
                    <span v-if="row.activity" class="tag tag--red">活动</span>
                  </td>
                  <td class="num">¥ {{ row.cost || '—' }}</td>
                  <td class="num">¥ {{ row.price }}</td>
                  <td>{{ row.listed_at ? row.listed_at.slice(0, 10) : '—' }}</td>
                  <td><span class="tag tag--ok">已上架</span></td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="empty-state">还没有上架任何商品，去「平台商品池」挑一件吧。</p>
          <p class="hint-text" style="margin-top: 8px">
            如需下架商品，请联系平台客服，由管理端代为操作。
          </p>
        </div>
      </div>
      <AppPager
        :page="state.listingPage"
        :page-size="PAGE_SIZE"
        :total="state.listingTotal"
        :has-next="state.listingHasNext"
        @change="goListingPage"
      />
    </template>

    <AppDrawer :open="detail.open" title="商品详情" wide @close="closeDetail">
      <template v-if="detail.value">
        <dl class="detail-grid">
          <div>
            <dt>商品 ID</dt>
            <dd class="mono">{{ detail.value.id }}</dd>
          </div>
          <div>
            <dt>品类</dt>
            <dd>
              {{ detail.value.merchant_category_label || '未分类' }}
            </dd>
          </div>
          <div>
            <dt>成本价</dt>
            <dd class="num">¥ {{ detail.value.cost || '未定价' }}</dd>
          </div>
          <div>
            <dt>零售价</dt>
            <dd class="num">¥ {{ detail.value.price || '未定价' }}</dd>
          </div>
          <div>
            <dt>可售状态</dt>
            <dd>{{ detail.value.status === 'ACTIVE' ? '可售' : '已下架' }}</dd>
          </div>
        </dl>

        <p v-if="detail.error" class="notice notice--error">{{ detail.error }}</p>

        <h3 class="section-title">商品描述</h3>
        <p v-if="detail.loading" class="inline-loading">详情加载中…</p>
        <div v-else-if="detailSections.length" class="detail-content">
          <section
            v-for="(section, si) in detailSections"
            :key="si"
            class="detail-content__section"
          >
            <h4 v-if="section.title">{{ section.title }}</h4>
            <template v-for="(block, bi) in section.blocks || []" :key="bi">
              <h5 v-if="block.type === 'heading' && block.text" class="detail-content__heading">
                {{ block.text }}
              </h5>
              <p v-else-if="block.text" class="detail-content__paragraph">{{ block.text }}</p>
            </template>
            <p v-if="section.text && !(section.blocks || []).length" class="detail-content__paragraph">
              {{ section.text }}
            </p>
            <div v-if="(section.images || []).length" class="detail-content__images">
              <img
                v-for="url in section.images"
                :key="url"
                :src="url"
                alt=""
                class="detail-content__image"
              />
            </div>
          </section>
        </div>
        <p v-else-if="detailText" class="detail-content__paragraph">{{ detailText }}</p>
        <p v-else class="muted-text">该商品暂无图文详情。</p>

        <h3 class="section-title">规格</h3>
        <p v-if="detail.loading" class="inline-loading">规格加载中…</p>
        <template v-else-if="specTables.length">
          <div v-for="(table, ti) in specTables" :key="ti" class="detail-spec-table">
            <h4 v-if="table.title">{{ table.title }}</h4>
            <div class="data-table-wrap">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>属性</th>
                    <th>值</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in table.rows" :key="row.name">
                    <th scope="row">{{ row.name }}</th>
                    <td>{{ row.value }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </template>
        <div v-else-if="flatSpecs.length" class="data-table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>属性</th>
                <th>值</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="spec in flatSpecs" :key="spec.name">
                <th scope="row">{{ spec.name }}</th>
                <td>{{ spec.value }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <ul v-else-if="skuSpecs.length" class="spec-list">
          <li v-for="spec in skuSpecs" :key="spec.name">{{ spec.name }}：{{ spec.value }}</li>
        </ul>
        <div v-else-if="specOptionChips.length" class="detail-spec-options">
          <div v-for="option in specOptionChips" :key="option.name" class="detail-spec-options__row">
            <span class="detail-spec-options__name">{{ option.name }}</span>
            <span v-for="value in option.values" :key="value.value" class="detail-spec-options__chip">
              {{ value.value }}
            </span>
          </div>
        </div>
        <p v-else class="muted-text">该商品暂无规格信息。</p>
      </template>
    </AppDrawer>

    <AppModal
      :open="confirm.open"
      title="确认上架商品"
      confirm-text="确认上架"
      :busy="confirm.busy"
      @cancel="closeConfirm"
      @confirm="submitList"
    >
      <template v-if="confirm.value">
        <p class="modal-lead">上架后该商品会立即出现在本店商品列表，可按成本价采购并发货。</p>
        <dl class="detail-grid">
          <div>
            <dt>商品名称</dt>
            <dd>{{ confirm.value.name }}</dd>
          </div>
          <div>
            <dt>品类</dt>
            <dd>
              {{ confirm.value.category?.name_zh || confirm.value.category?.name || '未分类' }}
            </dd>
          </div>
          <div>
            <dt>成本价</dt>
            <dd class="num">¥ {{ confirm.value.cost }}</dd>
          </div>
          <div>
            <dt>零售价</dt>
            <dd class="num">¥ {{ confirm.value.price }}</dd>
          </div>
        </dl>
        <p v-if="confirm.error" class="notice notice--error">{{ confirm.error }}</p>
      </template>
    </AppModal>
  </section>
</template>

<style scoped>
/* 统计标签：放在 tab 行最右侧（两端一致）。 */
.tabs__count {
  margin-left: auto;
  align-self: center;
  white-space: nowrap;
}

/* 品类筛选：只占一行，超出的横向滚动（桌面本就一行，行为无感知差异）。 */
.chip-row {
  display: flex;
  flex-wrap: nowrap;
  gap: 8px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
}

.chip-row::-webkit-scrollbar {
  display: none;
}

.chip {
  flex: none;
  border: 1px solid var(--line);
  background: #fff;
  border-radius: 16px;
  padding: 5px 14px;
  font-size: 13px;
  color: var(--muted);
  cursor: pointer;
  white-space: nowrap;
}

.chip.is-active {
  border-color: var(--red);
  color: var(--red);
  background: var(--red-soft);
  font-weight: 600;
}

.search-row {
  display: flex;
  gap: 8px;
  /* 与品类条、下方商品卡片都留出空隙；水平对齐工具条的 20px 内边距。 */
  margin: 12px 20px 16px;
  max-width: 460px;
}

@media (max-width: 768px) {
  .search-row {
    max-width: 100%;
    margin: 12px 16px 16px;
  }
}

.search-row input {
  flex: 1;
  min-height: 32px;
  padding: 6px 10px;
  border: 1px solid #e3e6eb;
  border-radius: 5px;
  background: #ffffff;
  font-size: 12px;
}

.search-row input:focus {
  outline: 0;
  border-color: #c9ced6;
}

.product-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
}

.product-card {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.product-card__media {
  position: relative;
  height: 150px;
  background: #f2f4f7;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--muted);
  font-size: 12px;
}

.product-card__media img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #fff;
}

.product-card__badge {
  position: absolute;
  top: 8px;
  left: 8px;
}

.product-card__badge + .product-card__badge {
  left: auto;
  right: 8px;
}

.product-card__body {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
}

.product-card__body h3 {
  font-size: 14px;
  margin: 0;
  line-height: 1.4;
  height: 40px;
  overflow: hidden;
}

.product-card__meta {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
}

.product-card__prices {
  display: flex;
  gap: 16px;
}

.product-card__label {
  display: block;
  font-size: 11px;
  color: var(--muted);
}

.product-card__actions {
  display: flex;
  gap: 8px;
  margin-top: auto;
}

.product-card__actions .btn {
  flex: 1;
}

.listing-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.listing-cell__img {
  width: 40px;
  height: 40px;
  object-fit: contain;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 4px;
  flex: none;
}

.listing-cell__img--empty {
  display: grid;
  place-items: center;
  font-size: 10px;
  color: var(--muted);
  background: #f2f4f7;
}

.spec-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: var(--ink);
}

/* 查看详情：图文区块（标题 / 子标题 / 段落 / 图片）。 */
.detail-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 8px;
}

.detail-content__section h4 {
  margin: 0 0 8px;
  font-size: 14px;
  color: var(--ink);
}

.detail-content__heading {
  margin: 10px 0 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
}

.detail-content__paragraph {
  margin: 0 0 8px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--ink);
  white-space: pre-wrap;
  word-break: break-word;
}

.detail-content__images {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}

.detail-content__image {
  width: 100%;
  height: auto;
  border-radius: 6px;
  background: #f5f5f5;
}

/* 查看详情：规格表之间留空隙，表格复用全局 data-table 样式。 */
.detail-spec-table + .detail-spec-table {
  margin-top: 16px;
}

.detail-spec-table h4 {
  margin: 0 0 8px;
  font-size: 14px;
  color: var(--ink);
}

/* 查看详情：只有规格可选值时的 chip 展示。 */
.detail-spec-options {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.detail-spec-options__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.detail-spec-options__name {
  font-size: 13px;
  color: var(--muted);
}

.detail-spec-options__chip {
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 3px 12px;
  font-size: 13px;
  color: var(--ink);
  background: #fff;
}

/* 手机档商品卡：一行两个，图片、字号、内边距同步收紧；桌面布局不变。 */
@media (max-width: 768px) {
  .product-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
  }

  .product-card__media {
    height: 110px;
  }

  .product-card__body {
    padding: 10px;
    gap: 6px;
  }

  .product-card__body h3 {
    font-size: 13px;
    height: 37px;
  }

  .product-card__meta {
    font-size: 11px;
  }

  .product-card__prices {
    gap: 10px;
  }

  .product-card__label {
    font-size: 10px;
  }

  .product-card__prices b {
    font-size: 13px;
  }
}
</style>
