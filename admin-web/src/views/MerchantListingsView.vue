<script setup>
import { onMounted, reactive, ref } from 'vue'

import AppDrawer from '@/components/AppDrawer.vue'
import AppModal from '@/components/AppModal.vue'
import AppPager from '@/components/AppPager.vue'
import AppPicker from '@/components/AppPicker.vue'
import StatusTag from '@/components/StatusTag.vue'
import { adminWrite } from '@/composables/useAdminApi'
import { apiRequest } from '@/lib/api'

const TABS = [
  { key: '', label: '全部关系' },
  { key: 'LISTED', label: '已上架' },
  { key: 'REMOVED', label: '已下架' },
]

const state = reactive({
  status: '',
  merchantQuery: '',
  productQuery: '',
  page: 1,
  items: [],
  meta: { total: 0, page_size: 12, has_next: false },
  loading: false,
  error: '',
})

const detail = ref(null)
const removeTarget = ref(null)
const removing = ref(false)

// 2026-11-28 可搜索下拉框：两个筛选改为 AppPicker——
// 商家候选走 /merchant-options（选中传商家编号，后端按编号精确匹配）；
// 商品候选走 /products（名称/UUID 搜索，选中传商品 UUID 精确匹配）。
function fetchListingMerchantOptions(q) {
  return apiRequest(`/merchant-options?q=${encodeURIComponent(q)}`)
}

function fetchListingProductOptions(q, page) {
  const params = new URLSearchParams({ page: String(page) })
  if (q.trim()) params.set('q', q.trim())
  return apiRequest(`/products?${params.toString()}`)
}

async function load(resetPage = false) {
  if (resetPage) state.page = 1
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page: String(state.page) })
    if (state.status) params.set('status', state.status)
    if (state.merchantQuery.trim()) params.set('merchant', state.merchantQuery.trim())
    if (state.productQuery.trim()) params.set('product', state.productQuery.trim())
    const payload = await apiRequest(`/merchant-listings?${params}`)
    state.items = payload.items
    state.meta = payload
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

async function confirmRemove() {
  if (!removeTarget.value) return
  removing.value = true
  try {
    await adminWrite(`/merchant-listings/${removeTarget.value.id}/actions`, { action: 'remove' })
    removeTarget.value = null
    await load()
  } catch (error) {
    state.error = error.message
  } finally {
    removing.value = false
  }
}

function formatTime(value) {
  if (!value) return '—'
  return value.replace('T', ' ').slice(0, 16)
}

function goPage(page) {
  state.page = page
  load()
}

function selectStatus(key) {
  state.status = key
  load(true)
}

function resetFilters() {
  state.merchantQuery = ''
  state.productQuery = ''
  state.status = ''
  load(true)
}

onMounted(load)
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>商家商品管理</h1>
        <p>定位指定商家的指定商品并从该店下架；状态只作用于店铺关系，不改商品池主档。</p>
      </div>
    </div>

    <div class="panel">
      <div class="tabs">
        <button
          v-for="tab in TABS"
          :key="tab.key"
          type="button"
          :class="{ 'is-active': state.status === tab.key }"
          @click="selectStatus(tab.key)"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="toolbar">
        <AppPicker
          v-model="state.merchantQuery"
          :fetcher="fetchListingMerchantOptions"
          placeholder="选择商家（名称 / 编号搜索）"
          @change="load(true)"
        />
        <AppPicker
          v-model="state.productQuery"
          :fetcher="fetchListingProductOptions"
          placeholder="选择商品（名称 / 商品编号搜索）"
          :option-meta="(option) => (option.price ? `¥ ${option.price}` : '')"
          @change="load(true)"
        />
        <button type="button" class="btn" @click="load(true)">查询</button>
        <button type="button" class="btn" @click="resetFilters">重置</button>
      </div>

      <p v-if="state.error" class="notice notice--error" style="margin: 16px 20px">
        {{ state.error }}
      </p>

      <div class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>商家</th>
              <th>商品</th>
              <th>成本价</th>
              <th>零售价</th>
              <th>状态</th>
              <th>上架时间</th>
              <th>下架时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in state.items" :key="row.id">
              <td>
                <span class="cell-strong">{{ row.merchant.name }}</span>
                <!-- 2026-11-27 全站编号改造：商家编号 JYM+10 位整号展示。 -->
                <span class="cell-sub">{{ row.merchant.id }}</span>
              </td>
              <td>{{ row.product.name }}</td>
              <td class="num">{{ row.cost ? `¥ ${row.cost}` : '—' }}</td>
              <td class="num">¥ {{ row.price }}</td>
              <td><StatusTag :value="row.status" /></td>
              <td>{{ formatTime(row.listed_at) }}</td>
              <td>{{ formatTime(row.removed_at) }}</td>
              <td>
                <div class="row-actions">
                  <button type="button" class="btn btn--sm" @click="detail = row">详情</button>
                  <button
                    v-if="row.status === 'LISTED'"
                    type="button"
                    class="btn btn--sm btn--danger"
                    @click="removeTarget = row"
                  >
                    下架
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!state.loading && state.items.length === 0">
              <td colspan="8" class="data-table__empty">没有匹配的店铺商品关系。</td>
            </tr>
            <tr v-if="state.loading">
              <td colspan="8" class="data-table__empty">加载中…</td>
            </tr>
          </tbody>
        </table>
      </div>

      <AppPager
        :page="state.meta.page || 1"
        :page-size="state.meta.page_size || 12"
        :total="state.meta.total || 0"
        :has-next="state.meta.has_next"
        @change="goPage"
      />
    </div>

    <AppDrawer v-if="detail" title="店铺商品详情" wide @close="detail = null">
      <div v-if="detail.product.images?.length" class="thumb-row">
        <img
          v-for="url in detail.product.images"
          :key="url"
          :src="url"
          alt=""
          class="thumb thumb--lg"
        />
      </div>
      <dl class="detail-grid" style="margin-top: 16px">
        <div>
          <dt>商家</dt>
          <dd>{{ detail.merchant.name }}</dd>
        </div>
        <div>
          <dt>商品 ID</dt>
          <dd>{{ detail.product.id }}</dd>
        </div>
        <div>
          <dt>商品名称</dt>
          <dd>{{ detail.product.name }}</dd>
        </div>
        <div>
          <dt>品类</dt>
          <dd>
            {{ detail.product.category?.name_zh || detail.product.category?.name || '未分类' }}
          </dd>
        </div>
        <div>
          <dt>成本价</dt>
          <dd>{{ detail.cost ? `¥ ${detail.cost}` : '—' }}</dd>
        </div>
        <div>
          <dt>零售价</dt>
          <dd>¥ {{ detail.price }}</dd>
        </div>
        <div>
          <dt>状态</dt>
          <dd><StatusTag :value="detail.status" /></dd>
        </div>
        <div>
          <dt>上架时间</dt>
          <dd>{{ formatTime(detail.listed_at) }}</dd>
        </div>
        <div>
          <dt>下架时间</dt>
          <dd>{{ formatTime(detail.removed_at) }}</dd>
        </div>
        <div>
          <dt>下架来源</dt>
          <dd>{{ detail.removed_by_platform ? '平台下架' : '—' }}</dd>
        </div>
      </dl>
      <h3 class="section-title">商品描述</h3>
      <p style="white-space: pre-wrap">{{ detail.product.description || '暂无描述。' }}</p>
      <h3 class="section-title">规格</h3>
      <table v-if="detail.product.specs?.length" class="data-table">
        <thead>
          <tr>
            <th>规格名称</th>
            <th>规格值</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="spec in detail.product.specs" :key="spec.name">
            <td>{{ spec.name }}</td>
            <td>{{ spec.value }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="empty-state">暂无规格。</p>
    </AppDrawer>

    <AppModal
      v-if="removeTarget"
      title="确认下架"
      confirm-text="确认下架"
      :busy="removing"
      @cancel="removeTarget = null"
      @confirm="confirmRemove"
    >
      <p>
        将从「{{ removeTarget.merchant.name }}」下架商品「{{ removeTarget.product.name }}」。
        该操作只影响这家店，不会改动商品池可售状态，也不会影响其他商家。
      </p>
    </AppModal>
  </section>
</template>
