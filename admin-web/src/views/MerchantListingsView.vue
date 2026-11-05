<script setup>
import { onMounted, reactive, ref } from 'vue'

import AppDrawer from '@/components/AppDrawer.vue'
import AppModal from '@/components/AppModal.vue'
import AppPager from '@/components/AppPager.vue'
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

const merchantOptions = ref([])
const detail = ref(null)
const removeTarget = ref(null)
const removing = ref(false)

async function searchMerchants() {
  if (!state.merchantQuery.trim()) {
    merchantOptions.value = []
    return
  }
  try {
    const payload = await apiRequest(
      `/merchant-options?q=${encodeURIComponent(state.merchantQuery.trim())}`,
    )
    merchantOptions.value = payload.items
  } catch {
    merchantOptions.value = []
  }
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
  merchantOptions.value = []
  load(true)
}

function pickMerchant(option) {
  state.merchantQuery = option.name
  merchantOptions.value = []
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
        <input
          v-model="state.merchantQuery"
          type="search"
          placeholder="商家名称 / 店铺 ID"
          @input="searchMerchants"
          @keyup.enter="load(true)"
        />
        <input
          v-model="state.productQuery"
          type="text"
          placeholder="商品 ID（精确匹配）"
          @keyup.enter="load(true)"
        />
        <button type="button" class="btn" @click="load(true)">查询</button>
        <button type="button" class="btn" @click="resetFilters">重置</button>
      </div>

      <div v-if="merchantOptions.length" class="toolbar" style="border-bottom: 0; padding-top: 0">
        <span class="cell-sub">匹配到的商家：</span>
        <button
          v-for="option in merchantOptions"
          :key="option.id"
          type="button"
          class="btn btn--sm"
          @click="pickMerchant(option)"
        >
          {{ option.name }}
        </button>
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
                <span class="cell-sub">{{ row.merchant.id.slice(0, 8) }}</span>
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
