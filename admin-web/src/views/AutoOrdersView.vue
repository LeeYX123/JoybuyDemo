<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import AppDrawer from '@/components/AppDrawer.vue'
import AppModal from '@/components/AppModal.vue'
import AppPager from '@/components/AppPager.vue'
import StatusTag from '@/components/StatusTag.vue'
import { adminWrite } from '@/composables/useAdminApi'
import { apiRequest } from '@/lib/api'

// 一键下单（迭代02，整节新增）：向导式创建自动化下单任务。
// 白名单用户 → 商家 → 商品 → 规格 → 数量 → 触发时间（按电脑/服务器时间到点执行）。
const TASK_STATUS_LABELS = {
  PENDING: '待执行',
  EXECUTED: '已下单',
  FAILED: '下单失败',
  CANCELED: '已取消',
}

const state = reactive({
  status: 'ALL',
  q: '',
  page: 1,
  items: [],
  meta: {},
  loading: true,
  error: '',
  notice: '',
})

const createOpen = ref(false)
const createBusy = ref(false)
const createError = ref('')
const wizard = reactive({
  step: 1,
  buyerQuery: '',
  buyers: [],
  buyer: null,
  merchantQuery: '',
  merchants: [],
  merchant: null,
  products: [],
  product: null,
  offerId: '',
  quantity: 1,
  triggerAt: '',
  balanceWarning: '',
})

const detail = reactive({ open: false, value: null, loading: false })
const cancelTarget = ref(null)
const cancelBusy = ref(false)

async function load(resetPage = false) {
  if (resetPage) state.page = 1
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page: String(state.page) })
    if (state.status && state.status !== 'ALL') params.set('status', state.status)
    if (state.q.trim()) params.set('q', state.q.trim())
    const payload = await apiRequest(`/auto-orders?${params}`)
    state.items = payload.items
    state.meta = payload
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

function selectStatus(key) {
  state.status = key
  load(true)
}

function search() {
  load(true)
}

function goPage(page) {
  state.page = page
  load()
}

function openCreate() {
  Object.assign(wizard, {
    step: 1,
    buyerQuery: '',
    buyers: [],
    buyer: null,
    merchantQuery: '',
    merchants: [],
    merchant: null,
    products: [],
    product: null,
    offerId: '',
    quantity: 1,
    triggerAt: '',
    balanceWarning: '',
  })
  createError.value = ''
  createOpen.value = true
}

async function searchBuyers() {
  try {
    const payload = await apiRequest(
      `/buyers/accounts?whitelisted=1&q=${encodeURIComponent(wizard.buyerQuery.trim())}`,
    )
    wizard.buyers = payload.items
  } catch {
    wizard.buyers = []
  }
}

function pickBuyer(row) {
  wizard.buyer = row
  wizard.step = 2
  searchMerchants()
}

async function searchMerchants() {
  try {
    const payload = await apiRequest(
      `/merchants?status=ACTIVE&q=${encodeURIComponent(wizard.merchantQuery.trim())}`,
    )
    wizard.merchants = payload.items
  } catch {
    wizard.merchants = []
  }
}

async function pickMerchant(row) {
  wizard.merchant = row
  wizard.merchantQuery = '' // 清掉商家名，避免误当商品关键字过滤
  wizard.step = 3
  await loadProducts()
}

// 已下架商品不展示（doc02 拍板）。
async function loadProducts() {
  try {
    const params = new URLSearchParams({ merchant_id: wizard.merchant.id })
    if (wizard.merchantQuery.trim()) params.set('q', wizard.merchantQuery.trim())
    const payload = await apiRequest(`/auto-orders/options?${params}`)
    wizard.products = payload.items
  } catch {
    wizard.products = []
  }
}

function pickProduct(row) {
  wizard.product = row
  wizard.offerId = row.offers.length === 1 ? row.offers[0].offer_id : ''
  wizard.step = 4
}

function goStep(step) {
  wizard.step = step
  if (step === 3) loadProducts()
}

function specText(offer) {
  const spec = offer.specification || {}
  const text = Object.entries(spec)
    .map(([key, value]) => `${key}:${value}`)
    .join(' / ')
  return text || '默认规格'
}

function goReview() {
  if (!wizard.offerId) {
    createError.value = '请选择一个商品规格。'
    return
  }
  wizard.step = 5
}

async function submitCreate() {
  createBusy.value = true
  createError.value = ''
  try {
    const triggerIso = wizard.triggerAt ? new Date(wizard.triggerAt).toISOString() : undefined
    const payload = await adminWrite('/auto-orders', {
      account_id: wizard.buyer.id,
      merchant_id: wizard.merchant.id,
      offer_id: wizard.offerId,
      quantity: Number(wizard.quantity),
      trigger_at: triggerIso,
    })
    createOpen.value = false
    state.notice = payload.balance_warning
      ? `任务已创建。提醒：${payload.balance_warning}`
      : '任务已创建，到触发时间将自动下单。'
    await load(true)
  } catch (error) {
    createError.value = error.message
  } finally {
    createBusy.value = false
  }
}

async function openDetail(row) {
  detail.open = true
  detail.loading = true
  detail.value = null
  try {
    const payload = await apiRequest(`/auto-orders?status=ALL&q=${row.product_title}`)
    detail.value = payload.items.find((item) => item.id === row.id) || row
  } catch {
    detail.value = row
  } finally {
    detail.loading = false
  }
}

function askCancel(row) {
  cancelTarget.value = row
}

async function confirmCancel() {
  if (!cancelTarget.value) return
  cancelBusy.value = true
  try {
    await adminWrite(`/auto-orders/${cancelTarget.value.id}/actions`, { action: 'cancel' })
    cancelTarget.value = null
    await load()
  } catch (error) {
    state.error = error.message
  } finally {
    cancelBusy.value = false
  }
}

const wizardSummary = computed(() => {
  const offer = wizard.product?.offers.find((item) => item.offer_id === wizard.offerId)
  return {
    buyer: wizard.buyer?.account || '—',
    merchant: wizard.merchant?.name || '—',
    product: wizard.product?.title || '—',
    spec: offer ? specText(offer) : '—',
    price: offer?.price || '—',
    quantity: wizard.quantity,
    triggerAt: wizard.triggerAt.replace('T', ' ') || '—',
  }
})

function formatTime(value) {
  return value ? value.replace('T', ' ').slice(0, 16) : '—'
}

onMounted(load)
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>一键下单</h1>
        <p>
          创建自动化下单任务：选择白名单用户、商家、商品规格与数量，到触发时间（电脑时间）自动下单；状态流转与正常购买完全一致。
        </p>
      </div>
      <div class="page-intro__actions">
        <button type="button" class="btn btn--primary" @click="openCreate">新建任务</button>
      </div>
    </div>

    <p v-if="state.notice" class="notice notice--ok">{{ state.notice }}</p>
    <p v-if="state.error" class="notice notice--error">{{ state.error }}</p>

    <div class="panel">
      <div class="toolbar">
        <div class="tabs">
          <button
            v-for="tab in [
              { key: 'ALL', label: '全部' },
              { key: 'PENDING', label: '待执行' },
              { key: 'EXECUTED', label: '已下单' },
              { key: 'FAILED', label: '下单失败' },
              { key: 'CANCELED', label: '已取消' },
            ]"
            :key="tab.key"
            type="button"
            :class="{ 'is-active': state.status === tab.key }"
            @click="selectStatus(tab.key)"
          >
            {{ tab.label }}
          </button>
        </div>
        <input
          v-model="state.q"
          type="search"
          placeholder="商品 / 买家 / 商家"
          @keyup.enter="search"
        />
        <button type="button" class="btn" @click="search">查询</button>
      </div>

      <p v-if="state.loading" class="inline-loading">加载中…</p>
      <div v-else class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>买家</th>
              <th>商家 / 商品</th>
              <th>规格</th>
              <th>数量</th>
              <th>触发时间</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in state.items" :key="row.id">
              <td>
                <b>{{ row.buyer.name }}</b>
                <span v-if="row.status === 'FAILED'" class="cell-sub" style="color: var(--red)">
                  {{ row.failure_reason }}
                </span>
                <span v-else-if="row.executed_order_id" class="cell-sub mono">
                  订单 {{ row.executed_order_id.slice(0, 8) }}
                </span>
              </td>
              <td>
                <b>{{ row.merchant.name }}</b>
                <span class="cell-sub">{{ row.product_title }}</span>
              </td>
              <td>{{ specText({ specification: row.specification }) }}</td>
              <td class="num">{{ row.quantity }}</td>
              <td>{{ formatTime(row.trigger_at) }}</td>
              <td>
                <StatusTag :value="row.status" :labels="TASK_STATUS_LABELS" />
              </td>
              <td>
                <div class="row-actions">
                  <button type="button" class="btn btn--sm" @click="openDetail(row)">详情</button>
                  <button
                    v-if="row.status === 'PENDING'"
                    type="button"
                    class="btn btn--sm btn--danger"
                    @click="askCancel(row)"
                  >
                    取消任务
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!state.items.length">
              <td colspan="7" class="data-table__empty">还没有任务，点右上角「新建任务」创建。</td>
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

    <AppDrawer :open="createOpen" title="新建一键下单任务" @close="createOpen = false">
      <div class="wizard-steps">
        <span
          v-for="(label, index) in ['买家', '商家', '商品', '规格数量时间', '确认']"
          :key="label"
          class="wizard-step"
          :class="{ 'is-active': wizard.step === index + 1 }"
        >
          {{ index + 1 }}. {{ label }}
        </span>
      </div>

      <p v-if="createError" class="notice notice--error">{{ createError }}</p>

      <template v-if="wizard.step === 1">
        <p class="field__hint">只能选择白名单用户的账号。</p>
        <input
          v-model="wizard.buyerQuery"
          type="search"
          placeholder="输入买家邮箱搜索（仅白名单）"
          @input="searchBuyers"
        />
        <div class="pick-list">
          <button
            v-for="row in wizard.buyers"
            :key="row.id"
            type="button"
            class="pick-item"
            @click="pickBuyer(row)"
          >
            <b>{{ row.account }}</b>
            <span class="cell-sub">余额 ¥ {{ row.balance }}</span>
          </button>
          <p v-if="!wizard.buyers.length" class="empty-state">输入关键字搜索白名单用户。</p>
        </div>
      </template>

      <template v-else-if="wizard.step === 2">
        <input
          v-model="wizard.merchantQuery"
          type="search"
          placeholder="输入商家名称搜索"
          @input="searchMerchants"
        />
        <div class="pick-list">
          <button
            v-for="row in wizard.merchants"
            :key="row.id"
            type="button"
            class="pick-item"
            @click="pickMerchant(row)"
          >
            <b>{{ row.name }}</b>
          </button>
        </div>
      </template>

      <template v-else-if="wizard.step === 3">
        <p class="field__hint">已下架商品不会出现在这里。</p>
        <input
          v-model="wizard.merchantQuery"
          type="search"
          placeholder="输入商品名称搜索"
          @input="loadProducts"
        />
        <div class="pick-list">
          <button
            v-for="row in wizard.products"
            :key="row.id"
            type="button"
            class="pick-item"
            @click="pickProduct(row)"
          >
            <b>{{ row.title }}</b>
            <span class="cell-sub">¥ {{ row.price }} · {{ row.offers.length }} 个规格</span>
          </button>
          <p v-if="!wizard.products.length" class="empty-state">该商家没有可售商品。</p>
        </div>
      </template>

      <template v-else-if="wizard.step === 4">
        <div class="field">
          <span class="field__label">商品规格</span>
          <label
            v-for="offer in wizard.product?.offers || []"
            :key="offer.offer_id"
            class="checkline"
          >
            <input v-model="wizard.offerId" type="radio" :value="offer.offer_id" />
            {{ specText(offer) }}（¥ {{ offer.price }}，库存 {{ offer.inventory }}）
          </label>
          <span class="field__hint">规格失效会在创建时与触发下单时校验并提醒。</span>
        </div>
        <div class="field">
          <label for="wizard-qty">数量</label>
          <input id="wizard-qty" v-model="wizard.quantity" type="number" min="1" step="1" />
        </div>
        <div class="field">
          <label for="wizard-trigger">触发时间（按电脑/服务器时间）</label>
          <input id="wizard-trigger" v-model="wizard.triggerAt" type="datetime-local" />
        </div>
        <div class="form-actions">
          <button type="button" class="btn" @click="goStep(3)">上一步</button>
          <button type="button" class="btn btn--primary" @click="goReview">下一步</button>
        </div>
      </template>

      <template v-else>
        <dl class="detail-grid">
          <div>
            <dt>买家</dt>
            <dd>{{ wizardSummary.buyer }}</dd>
          </div>
          <div>
            <dt>商家</dt>
            <dd>{{ wizardSummary.merchant }}</dd>
          </div>
          <div>
            <dt>商品</dt>
            <dd>{{ wizardSummary.product }}</dd>
          </div>
          <div>
            <dt>规格</dt>
            <dd>{{ wizardSummary.spec }}</dd>
          </div>
          <div>
            <dt>单价 / 数量</dt>
            <dd>¥ {{ wizardSummary.price }} × {{ wizardSummary.quantity }}</dd>
          </div>
          <div>
            <dt>触发时间</dt>
            <dd>{{ wizardSummary.triggerAt }}</dd>
          </div>
        </dl>
        <p class="hint-text">
          触发时间按电脑（服务器）时间判定；到点自动下单，若买家余额不足或规格已失效，任务会标记失败并给出原因。
        </p>
        <div class="form-actions">
          <button type="button" class="btn" @click="goStep(4)">上一步</button>
          <button
            type="button"
            class="btn btn--primary"
            :disabled="createBusy"
            @click="submitCreate"
          >
            {{ createBusy ? '创建中…' : '创建任务' }}
          </button>
        </div>
      </template>
    </AppDrawer>

    <AppDrawer :open="detail.open" title="任务详情" @close="detail.open = false">
      <p v-if="detail.loading" class="inline-loading">加载中…</p>
      <template v-else-if="detail.value">
        <dl class="detail-grid">
          <div>
            <dt>买家</dt>
            <dd>{{ detail.value.buyer.name }}（余额 ¥ {{ detail.value.buyer.balance }}）</dd>
          </div>
          <div>
            <dt>商家 / 商品</dt>
            <dd>{{ detail.value.merchant.name }} · {{ detail.value.product_title }}</dd>
          </div>
          <div>
            <dt>规格</dt>
            <dd>{{ specText({ specification: detail.value.specification }) }}</dd>
          </div>
          <div>
            <dt>数量 / 单价</dt>
            <dd>{{ detail.value.quantity }} × ¥ {{ detail.value.unit_price || '—' }}</dd>
          </div>
          <div>
            <dt>触发时间</dt>
            <dd>{{ formatTime(detail.value.trigger_at) }}</dd>
          </div>
          <div>
            <dt>状态</dt>
            <dd>
              <StatusTag :value="detail.value.status" :labels="TASK_STATUS_LABELS" />
            </dd>
          </div>
          <div v-if="detail.value.failure_reason">
            <dt>失败原因</dt>
            <dd>{{ detail.value.failure_reason }}</dd>
          </div>
          <div v-if="detail.value.executed_order_id">
            <dt>生成订单</dt>
            <dd class="mono">{{ detail.value.executed_order_id }}</dd>
          </div>
        </dl>
      </template>
    </AppDrawer>

    <AppModal
      v-if="cancelTarget"
      title="取消任务"
      confirm-text="确认取消"
      :busy="cancelBusy"
      @cancel="cancelTarget = null"
      @confirm="confirmCancel"
    >
      <p>
        取消后该任务不会再自动下单（商品：{{ cancelTarget.product_title }}，触发时间
        {{ formatTime(cancelTarget.trigger_at) }}）。已执行/失败的任务无法取消。
      </p>
    </AppModal>
  </section>
</template>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.toolbar input[type='search'] {
  min-width: 220px;
}

.wizard-steps {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.wizard-step {
  font-size: 12px;
  color: var(--muted, #78869a);
  padding: 4px 10px;
  border: 1px solid var(--border, #e2e8f0);
  border-radius: 12px;
}

.wizard-step.is-active {
  color: #fff;
  background: var(--primary, #2563eb);
  border-color: var(--primary, #2563eb);
}

.pick-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
  max-height: 320px;
  overflow-y: auto;
}

.pick-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 10px 12px;
  border: 1px solid var(--border, #e2e8f0);
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  text-align: left;
}

.pick-item:hover {
  border-color: var(--primary, #2563eb);
}
</style>
