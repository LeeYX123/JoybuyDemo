<script setup>
import { onMounted, reactive, ref } from 'vue'

import AppDrawer from '@/components/AppDrawer.vue'
import AppModal from '@/components/AppModal.vue'
import ImageUploader from '@/components/ImageUploader.vue'
import AppPager from '@/components/AppPager.vue'
import StatusTag from '@/components/StatusTag.vue'
import { adminWrite } from '@/composables/useAdminApi'
import { apiRequest } from '@/lib/api'

const STATUS_TABS = [
  { key: '', label: '全部商品' },
  { key: 'ACTIVE', label: '可售' },
  { key: 'INACTIVE', label: '已下架' },
  { key: 'DRAFT', label: '草稿' },
]

const state = reactive({
  status: '',
  q: '',
  category: '',
  page: 1,
  items: [],
  meta: { total: 0, page_size: 20, has_next: false },
  loading: false,
  error: '',
})

// 商品池的 ACTIVE 表示「可售」，与店铺的「接单中」不是同一个语义。
const PRODUCT_STATUS_LABELS = { ACTIVE: '可售', INACTIVE: '已下架', DRAFT: '草稿' }

const categories = ref([])
const detail = ref(null)
const detailLoading = ref(false)

const editorOpen = ref(false)
const editorBusy = ref(false)
const editorError = ref('')
const editorId = ref('')
const editor = reactive({
  name: '',
  category: '',
  cost: '',
  price: '',
  description: '',
  activity: false,
  status: 'ACTIVE',
  images: [],
  specs: [],
})

async function load(resetPage = false) {
  if (resetPage) state.page = 1
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page: String(state.page) })
    if (state.status) params.set('status', state.status)
    if (state.category) params.set('category', state.category)
    if (state.q.trim()) params.set('q', state.q.trim())
    const payload = await apiRequest(`/products?${params}`)
    state.items = payload.items
    state.meta = payload
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

async function loadCategories() {
  try {
    const payload = await apiRequest('/categories')
    categories.value = payload.items
  } catch {
    categories.value = []
  }
}

async function openDetail(row) {
  detail.value = null
  detailLoading.value = true
  try {
    const payload = await apiRequest(`/products/${row.id}`)
    detail.value = payload.product
  } catch (error) {
    state.error = error.message
  } finally {
    detailLoading.value = false
  }
}

function openEditor(row = null) {
  editorId.value = row?.id || ''
  editor.name = row?.name || ''
  editor.category = row?.category?.id || ''
  editor.cost = row?.cost || ''
  editor.price = row?.price || ''
  editor.description = row?.description || ''
  editor.activity = Boolean(row?.activity)
  editor.status = row?.status || 'ACTIVE'
  editor.images = [...(row?.images || [])]
  editor.specs = (row?.specs || []).map((item) => ({ ...item }))
  if (editor.specs.length === 0) editor.specs.push({ name: '', value: '' })
  editorError.value = ''
  editorOpen.value = true
}

function addSpec() {
  editor.specs.push({ name: '', value: '' })
}

function removeSpec(index) {
  editor.specs.splice(index, 1)
}

async function saveProduct() {
  editorBusy.value = true
  editorError.value = ''
  const payload = {
    name: editor.name,
    category: editor.category || null,
    cost: editor.cost,
    price: editor.price,
    description: editor.description,
    activity: editor.activity,
    status: editor.status,
    images: editor.images.filter(Boolean).slice(0, 5),
    specs: editor.specs.filter((item) => item.name.trim() && item.value.trim()),
  }
  try {
    if (editorId.value) {
      await adminWrite(`/products/${editorId.value}`, payload, 'PATCH')
    } else {
      await adminWrite('/products', payload)
    }
    editorOpen.value = false
    await load()
    if (editorId.value && detail.value?.id === editorId.value) {
      await openDetail({ id: editorId.value })
    }
  } catch (error) {
    editorError.value = error.message
  } finally {
    editorBusy.value = false
  }
}

async function toggleStatus(row) {
  const action = row.status === 'ACTIVE' ? 'unpublish' : 'publish'
  try {
    await adminWrite(`/products/${row.id}/actions`, { action })
    await load()
  } catch (error) {
    state.error = error.message
  }
}

function categoryLabel(category) {
  if (!category) return '未分类'
  return category.name_zh || category.name_en || category.name
}

function selectStatus(key) {
  state.status = key
  load(true)
}

function resetFilters() {
  state.q = ''
  state.category = ''
  state.status = ''
  load(true)
}

function goPage(page) {
  state.page = page
  load()
}

function closeDetail() {
  detail.value = null
  detailLoading.value = false
}

onMounted(() => {
  loadCategories()
  load()
})
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>商品池管理</h1>
        <p>
          维护平台商品的品类、图片、规格、价格与可售性。商品池复用主档
          SPU，商家上架时在此取成本价快照。
        </p>
      </div>
      <div class="page-intro__actions">
        <button type="button" class="btn btn--primary" @click="openEditor()">新增商品</button>
      </div>
    </div>

    <div class="panel">
      <div class="tabs">
        <button
          v-for="tab in STATUS_TABS"
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
          v-model="state.q"
          type="search"
          placeholder="商品名称或商品 ID"
          @keyup.enter="load(true)"
        />
        <select v-model="state.category" @change="load(true)">
          <option value="">全部品类</option>
          <option v-for="item in categories" :key="item.id" :value="item.id">
            {{ item.name_zh || item.name_en || item.name }}
          </option>
        </select>
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
              <th>商品</th>
              <th>品类</th>
              <th>成本价</th>
              <th>零售价</th>
              <th>商家数</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in state.items" :key="row.id">
              <td>
                <div style="display: flex; gap: 10px; align-items: center">
                  <img v-if="row.images?.length" :src="row.images[0]" alt="" class="thumb" />
                  <div>
                    <span class="cell-strong">{{ row.name }}</span>
                    <span class="cell-sub"
                      >{{ row.id.slice(0, 8)
                      }}<template v-if="row.activity"> · 活动商品</template></span
                    >
                  </div>
                </div>
              </td>
              <td>{{ categoryLabel(row.category) }}</td>
              <td class="num">{{ row.cost ? `¥ ${row.cost}` : '—' }}</td>
              <td class="num">{{ row.price ? `¥ ${row.price}` : '—' }}</td>
              <td class="num">{{ row.stores }}</td>
              <td><StatusTag :value="row.status" :labels="PRODUCT_STATUS_LABELS" /></td>
              <td>
                <div class="row-actions">
                  <button type="button" class="btn btn--sm" @click="openDetail(row)">详情</button>
                  <button type="button" class="btn btn--sm" @click="openEditor(row)">编辑</button>
                  <button type="button" class="btn btn--sm" @click="toggleStatus(row)">
                    {{ row.status === 'ACTIVE' ? '下架' : '恢复' }}
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!state.loading && state.items.length === 0">
              <td colspan="7" class="data-table__empty">没有匹配的商品。</td>
            </tr>
            <tr v-if="state.loading">
              <td colspan="7" class="data-table__empty">加载中…</td>
            </tr>
          </tbody>
        </table>
      </div>

      <AppPager
        :page="state.meta.page || 1"
        :page-size="state.meta.page_size || 20"
        :total="state.meta.total || 0"
        :has-next="state.meta.has_next"
        @change="goPage"
      />
    </div>

    <AppDrawer
      v-if="detail || detailLoading"
      :title="detail ? detail.name : '商品详情'"
      wide
      @close="closeDetail"
    >
      <p v-if="detailLoading" class="inline-loading">加载中…</p>
      <template v-if="detail">
        <div v-if="detail.images?.length" class="thumb-row">
          <img v-for="url in detail.images" :key="url" :src="url" alt="" class="thumb thumb--lg" />
        </div>
        <dl class="detail-grid" style="margin-top: 16px">
          <div>
            <dt>商品 ID</dt>
            <dd>{{ detail.id }}</dd>
          </div>
          <div>
            <dt>品类</dt>
            <dd>{{ categoryLabel(detail.category) }}</dd>
          </div>
          <div>
            <dt>成本价</dt>
            <dd>{{ detail.cost ? `¥ ${detail.cost}` : '—' }}</dd>
          </div>
          <div>
            <dt>零售价</dt>
            <dd>{{ detail.price ? `¥ ${detail.price}` : '—' }}</dd>
          </div>
          <div>
            <dt>商家数</dt>
            <dd>{{ detail.stores }}</dd>
          </div>
          <div>
            <dt>状态</dt>
            <dd><StatusTag :value="detail.status" :labels="PRODUCT_STATUS_LABELS" /></dd>
          </div>
          <div>
            <dt>活动商品</dt>
            <dd>{{ detail.activity ? '是' : '否' }}</dd>
          </div>
          <div>
            <dt>SKU 数</dt>
            <dd>{{ detail.sku_count ?? detail.skus?.length ?? 0 }}</dd>
          </div>
        </dl>
        <h3 class="section-title">商品描述</h3>
        <p style="white-space: pre-wrap">{{ detail.description || '暂无描述。' }}</p>
        <h3 class="section-title">规格</h3>
        <table v-if="detail.specs?.length" class="data-table">
          <thead>
            <tr>
              <th>规格名称</th>
              <th>规格值</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="spec in detail.specs" :key="spec.name">
              <td>{{ spec.name }}</td>
              <td>{{ spec.value }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty-state">暂无规格。</p>
      </template>
    </AppDrawer>

    <AppModal
      v-if="editorOpen"
      :title="editorId ? '编辑商品' : '新增商品'"
      :busy="editorBusy"
      confirm-text="保存"
      @cancel="editorOpen = false"
      @confirm="saveProduct"
    >
      <p v-if="editorError" class="notice notice--error">{{ editorError }}</p>
      <div class="form-grid">
        <div class="field">
          <label for="product-name">商品名称</label>
          <input id="product-name" v-model="editor.name" type="text" maxlength="80" />
        </div>
        <div class="field">
          <label for="product-category">品类</label>
          <select id="product-category" v-model="editor.category">
            <option value="">未分类</option>
            <option v-for="item in categories" :key="item.id" :value="item.id">
              {{ item.name_zh || item.name_en || item.name }}
            </option>
          </select>
        </div>
        <div class="field">
          <label for="product-cost">成本价（元）</label>
          <input id="product-cost" v-model="editor.cost" type="number" min="0.01" step="0.01" />
        </div>
        <div class="field">
          <label for="product-price">零售价（元）</label>
          <input id="product-price" v-model="editor.price" type="number" min="0.01" step="0.01" />
          <span class="field__hint">零售价不得低于成本价。</span>
        </div>
        <div class="field">
          <label for="product-status">状态</label>
          <select id="product-status" v-model="editor.status">
            <option value="ACTIVE">可售</option>
            <option value="INACTIVE">已下架</option>
            <option value="DRAFT">草稿</option>
          </select>
        </div>
        <div class="field">
          <label class="checkline">
            <input v-model="editor.activity" type="checkbox" /> 活动商品
          </label>
        </div>
      </div>

      <ImageUploader
        v-model="editor.images"
        purpose="product"
        multiple
        :max="5"
        :max-size-mb="1"
        label="商品图片"
        hint="最多 5 张，首张为主图。上传后存到服务器本地，URL 由后端返回。"
      />

      <div class="field" style="margin-top: 12px">
        <label for="product-desc">商品描述</label>
        <textarea id="product-desc" v-model="editor.description" rows="3" />
      </div>

      <h3 class="section-title">规格</h3>
      <div
        v-for="(spec, index) in editor.specs"
        :key="index"
        class="form-grid form-grid--tight"
        style="margin-bottom: 8px"
      >
        <div class="field">
          <input v-model="spec.name" type="text" placeholder="规格名称，如颜色" maxlength="30" />
        </div>
        <div class="field">
          <input v-model="spec.value" type="text" placeholder="规格值，如黑色" maxlength="200" />
        </div>
        <button type="button" class="btn btn--sm" @click="removeSpec(index)">移除</button>
      </div>
      <button type="button" class="btn btn--sm" @click="addSpec">新增规格</button>
    </AppModal>
  </section>
</template>
