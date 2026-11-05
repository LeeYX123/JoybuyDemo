<script setup>
import { onMounted, reactive, ref } from 'vue'

import AppDrawer from '@/components/AppDrawer.vue'
import AppModal from '@/components/AppModal.vue'
import ImageUploader from '@/components/ImageUploader.vue'
import AppPager from '@/components/AppPager.vue'
import { adminWrite } from '@/composables/useAdminApi'
import { apiRequest } from '@/lib/api'

const TABS = [
  { key: '', label: '全部记录' },
  { key: 'NORMAL', label: '普通通知' },
  { key: 'REVIEW', label: '商品好评' },
]

const state = reactive({
  kind: '',
  read: '',
  q: '',
  page: 1,
  items: [],
  meta: { total: 0, page_size: 20, has_next: false },
  loading: false,
  error: '',
})

const detail = ref(null)
const detailLoading = ref(false)
const replyText = ref('')
const replyBusy = ref(false)

const composeOpen = ref(false)
const composeBusy = ref(false)
const composeError = ref('')
const compose = reactive({
  kind: 'NORMAL',
  target: 'ALL',
  merchantId: '',
  merchantQuery: '',
  productQuery: '',
  productId: '',
  title: '',
  content: '',
  rating: 5,
  images: [],
})

const merchantOptions = ref([])
const productOptions = ref([])

async function load(resetPage = false) {
  if (resetPage) state.page = 1
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page: String(state.page) })
    if (state.kind) params.set('kind', state.kind)
    if (state.read) params.set('read', state.read)
    if (state.q.trim()) params.set('q', state.q.trim())
    const payload = await apiRequest(`/notifications?${params}`)
    state.items = payload.items
    state.meta = payload
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

async function openDetail(row) {
  detail.value = null
  detailLoading.value = true
  replyText.value = ''
  try {
    const payload = await apiRequest(`/notifications/${row.id}`)
    detail.value = payload.notification
  } catch (error) {
    state.error = error.message
  } finally {
    detailLoading.value = false
  }
}

async function sendReply() {
  if (!detail.value || !replyText.value.trim()) return
  replyBusy.value = true
  try {
    await adminWrite(`/notifications/${detail.value.id}/replies`, {
      content: replyText.value.trim(),
    })
    replyText.value = ''
    await openDetail({ id: detail.value.id })
    await load()
  } catch (error) {
    state.error = error.message
  } finally {
    replyBusy.value = false
  }
}

async function searchMerchants() {
  if (!compose.merchantQuery.trim()) {
    merchantOptions.value = []
    return
  }
  try {
    const payload = await apiRequest(
      `/notifications/merchants?q=${encodeURIComponent(compose.merchantQuery.trim())}`,
    )
    merchantOptions.value = payload.items
  } catch {
    merchantOptions.value = []
  }
}

async function pickMerchant(option) {
  compose.merchantId = option.id
  compose.merchantQuery = option.name
  merchantOptions.value = []
  if (compose.kind === 'REVIEW') await searchProducts()
}

async function searchProducts() {
  if (!compose.merchantId) return
  try {
    const params = new URLSearchParams({ merchant_id: compose.merchantId })
    if (compose.productQuery.trim()) params.set('q', compose.productQuery.trim())
    const payload = await apiRequest(`/notifications/products?${params}`)
    productOptions.value = payload.items
  } catch {
    productOptions.value = []
  }
}

function pickProduct(option) {
  compose.productId = option.id
  compose.productQuery = option.name
  productOptions.value = []
  if (!compose.title) compose.title = '商品好评'
}

async function submitCompose() {
  composeBusy.value = true
  composeError.value = ''
  try {
    if (compose.kind === 'REVIEW') {
      await adminWrite('/notifications', {
        kind: 'REVIEW',
        merchant_id: compose.merchantId,
        product_id: compose.productId,
        title: compose.title,
        content: compose.content,
        rating: Number(compose.rating),
        images: compose.images
          .split('\n')
          .map((line) => line.trim())
          .filter(Boolean)
          .slice(0, 5),
      })
    } else {
      await adminWrite('/notifications', {
        kind: 'NORMAL',
        target: compose.target,
        merchant_id: compose.target === 'ONE' ? compose.merchantId : undefined,
        title: compose.title,
        content: compose.content,
      })
    }
    composeOpen.value = false
    Object.assign(compose, {
      kind: 'NORMAL',
      target: 'ALL',
      merchantId: '',
      merchantQuery: '',
      productQuery: '',
      productId: '',
      title: '',
      content: '',
      rating: 5,
      images: [],
    })
    await load(true)
  } catch (error) {
    composeError.value = error.message
  } finally {
    composeBusy.value = false
  }
}

function formatTime(value) {
  return value ? value.replace('T', ' ').slice(0, 16) : '—'
}

function selectTab(key) {
  state.kind = key
  load(true)
}

function resetFilters() {
  state.q = ''
  state.read = ''
  state.kind = ''
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

onMounted(load)
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>平台通知推送</h1>
        <p>推送普通通知或指定店铺的商品好评，并可与商家在同一记录里多轮回复。</p>
      </div>
      <div class="page-intro__actions">
        <button type="button" class="btn btn--primary" @click="composeOpen = true">新建推送</button>
      </div>
    </div>

    <div class="panel">
      <div class="tabs">
        <button
          v-for="tab in TABS"
          :key="tab.key"
          type="button"
          :class="{ 'is-active': state.kind === tab.key }"
          @click="selectTab(tab.key)"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="toolbar">
        <select v-model="state.read" @change="load(true)">
          <option value="">全部阅读状态</option>
          <option value="0">未读</option>
          <option value="1">已读</option>
        </select>
        <input
          v-model="state.q"
          type="search"
          placeholder="标题 / 正文 / 店铺"
          @keyup.enter="load(true)"
        />
        <button type="button" class="btn" @click="load(true)">查询</button>
        <button type="button" class="btn" @click="resetFilters">重置</button>
      </div>

      <p v-if="state.error" class="notice notice--error" style="margin: 0 20px 14px">
        {{ state.error }}
      </p>

      <div class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>类型</th>
              <th>标题</th>
              <th>接收店铺</th>
              <th>阅读</th>
              <th>回复</th>
              <th>发送时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in state.items" :key="row.id">
              <td>
                <span class="tag" :class="row.kind === 'REVIEW' ? 'tag--info' : 'tag--gray'">
                  {{ row.kind === 'REVIEW' ? '商品好评' : '普通通知' }}
                </span>
              </td>
              <td>
                <b>{{ row.title }}</b>
                <span class="cell-sub">{{ row.content.slice(0, 40) }}</span>
              </td>
              <td>{{ row.merchant.name }}</td>
              <td>
                <span class="tag" :class="row.read ? 'tag--ok' : 'tag--warn'">
                  {{ row.read ? '已读' : '未读' }}
                </span>
              </td>
              <td class="num">{{ row.reply_count }}</td>
              <td>{{ formatTime(row.created_at) }}</td>
              <td>
                <div class="row-actions">
                  <button type="button" class="btn btn--sm" @click="openDetail(row)">
                    详情 / 回复
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!state.loading && state.items.length === 0">
              <td colspan="7" class="data-table__empty">还没有推送过通知。</td>
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
      :title="detail ? detail.title : '通知详情'"
      wide
      @close="closeDetail"
    >
      <p v-if="detailLoading" class="inline-loading">加载中…</p>
      <template v-if="detail">
        <dl class="detail-grid">
          <div>
            <dt>类型</dt>
            <dd>{{ detail.kind === 'REVIEW' ? '商品好评' : '普通通知' }}</dd>
          </div>
          <div>
            <dt>接收店铺</dt>
            <dd>{{ detail.merchant.name }}</dd>
          </div>
          <div>
            <dt>阅读状态</dt>
            <dd>{{ detail.read ? '已读' : '未读' }}</dd>
          </div>
          <div>
            <dt>发送时间</dt>
            <dd>{{ formatTime(detail.created_at) }}</dd>
          </div>
        </dl>

        <div v-if="detail.product" class="panel" style="margin-bottom: 16px">
          <div class="panel__body" style="display: flex; gap: 12px; align-items: center">
            <img
              v-if="detail.product.image"
              :src="detail.product.image"
              alt=""
              class="thumb thumb--lg"
            />
            <div>
              <b>{{ detail.product.name }}</b>
              <div class="cell-sub">商品 ID：{{ detail.product.id }}</div>
              <div class="cell-sub">
                零售价 {{ detail.product.price ?? '—' }} · 成本 {{ detail.product.cost ?? '—' }}
              </div>
            </div>
          </div>
        </div>

        <h3 class="section-title">通知正文</h3>
        <p style="white-space: pre-wrap">{{ detail.content || '（无正文）' }}</p>

        <template v-if="detail.kind === 'REVIEW'">
          <h3 class="section-title">评价内容</h3>
          <p>
            <span class="tag tag--warn">{{ '★'.repeat(detail.rating || 5) }}</span>
          </p>
          <p style="white-space: pre-wrap">{{ detail.content }}</p>
          <div v-if="detail.images?.length" class="thumb-row">
            <img
              v-for="url in detail.images"
              :key="url"
              :src="url"
              alt=""
              class="thumb thumb--lg"
            />
          </div>
        </template>

        <h3 class="section-title">对话记录</h3>
        <ol v-if="detail.replies?.length" class="timeline">
          <li
            v-for="reply in detail.replies"
            :key="reply.id"
            :class="reply.role === 'PLATFORM' ? 'is-current' : 'is-done'"
          >
            <div class="timeline__title">
              {{ reply.role === 'PLATFORM' ? '平台' : '商家' }} · {{ reply.author || '—' }}
            </div>
            <div class="timeline__time">{{ formatTime(reply.created_at) }}</div>
            <p style="margin: 6px 0 0; font-size: 12px">{{ reply.content }}</p>
          </li>
        </ol>
        <p v-else class="empty-state">商家还没有回复。</p>
      </template>

      <template v-if="detail" #footer>
        <input
          v-model="replyText"
          type="text"
          maxlength="1000"
          placeholder="输入平台回复，最多 1000 字"
          style="
            flex: 1;
            min-height: 33px;
            padding: 7px 10px;
            border: 1px solid #d7e0ec;
            border-radius: 3px;
          "
        />
        <button
          type="button"
          class="btn btn--primary"
          :disabled="replyBusy || !replyText.trim()"
          @click="sendReply"
        >
          发送回复
        </button>
      </template>
    </AppDrawer>

    <AppModal
      v-if="composeOpen"
      title="新建推送"
      confirm-text="发送"
      :busy="composeBusy"
      @cancel="composeOpen = false"
      @confirm="submitCompose"
    >
      <p v-if="composeError" class="notice notice--error">{{ composeError }}</p>

      <div class="form-grid">
        <div class="field">
          <label for="compose-kind">类型</label>
          <select id="compose-kind" v-model="compose.kind">
            <option value="NORMAL">普通通知</option>
            <option value="REVIEW">商品好评</option>
          </select>
        </div>
        <div v-if="compose.kind === 'NORMAL'" class="field">
          <label for="compose-target">接收范围</label>
          <select id="compose-target" v-model="compose.target">
            <option value="ALL">全部接单商家</option>
            <option value="ONE">指定店铺</option>
          </select>
        </div>
      </div>

      <div
        v-if="compose.kind === 'REVIEW' || compose.target === 'ONE'"
        class="field"
        style="margin-top: 12px"
      >
        <label for="compose-merchant">店铺（输入名称搜索）</label>
        <input
          id="compose-merchant"
          v-model="compose.merchantQuery"
          type="search"
          placeholder="店铺名称"
          @input="searchMerchants"
        />
        <div v-if="merchantOptions.length" class="thumb-row">
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
      </div>

      <div v-if="compose.kind === 'REVIEW'" class="field" style="margin-top: 12px">
        <label for="compose-product">本店已上架商品（输入名称搜索）</label>
        <input
          id="compose-product"
          v-model="compose.productQuery"
          type="search"
          placeholder="先选店铺，再搜商品"
          @input="searchProducts"
        />
        <div v-if="productOptions.length" class="thumb-row">
          <button
            v-for="option in productOptions"
            :key="option.id"
            type="button"
            class="btn btn--sm"
            @click="pickProduct(option)"
          >
            {{ option.name }}
          </button>
        </div>
        <span class="field__hint">只能推送该店确实已上架的商品，服务端会再次校验。</span>
      </div>

      <div class="field" style="margin-top: 12px">
        <label for="compose-title">标题</label>
        <input id="compose-title" v-model="compose.title" type="text" maxlength="200" />
      </div>
      <div class="field" style="margin-top: 12px">
        <label for="compose-content">{{
          compose.kind === 'REVIEW' ? '评论内容' : '通知正文'
        }}</label>
        <textarea id="compose-content" v-model="compose.content" rows="3" />
      </div>

      <div v-if="compose.kind === 'REVIEW'" class="form-grid" style="margin-top: 12px">
        <div class="field">
          <label for="compose-rating">星级</label>
          <select id="compose-rating" v-model="compose.rating">
            <option v-for="value in [5, 4, 3, 2, 1]" :key="value" :value="value">
              {{ value }} 星
            </option>
          </select>
        </div>
      </div>
      <div v-if="compose.kind === 'REVIEW'" class="field" style="margin-top: 12px">
        <ImageUploader
          v-model="compose.images"
          purpose="review"
          multiple
          :max="5"
          :max-size-mb="1"
          label="评论图片"
        />
      </div>
    </AppModal>
  </section>
</template>
