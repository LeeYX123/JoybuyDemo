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
// 向导为 C 版布局（用户选版）：左栏步骤导航（已完成可点击回跳）+ 右侧内容 + 底部已选摘要栏。
const TASK_STATUS_LABELS = {
  PENDING: '待执行',
  EXECUTED: '已下单',
  FAILED: '下单失败',
  CANCELED: '已取消',
}

const STEP_LABELS = ['选择买家', '选择商家', '选择商品', '规格数量时间', '确认创建']
// 商品分页：每页 4 张卡片（客户端分页，options 端点最多返回 30 件可售商品）。
const PRODUCT_PAGE_SIZE = 4

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
const productPage = ref(1)

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
  productPage.value = 1
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

// 已下架商品不展示（doc02 拍板）。
async function loadProducts() {
  if (!wizard.merchant) return
  try {
    const params = new URLSearchParams({ merchant_id: wizard.merchant.id })
    if (wizard.merchantQuery.trim()) params.set('q', wizard.merchantQuery.trim())
    const payload = await apiRequest(`/auto-orders/options?${params}`)
    wizard.products = payload.items
    productPage.value = 1
  } catch {
    wizard.products = []
  }
}

function pickBuyer(row) {
  wizard.buyer = row
}

function pickMerchant(row) {
  if (wizard.merchant && wizard.merchant.id !== row.id) {
    // 换商家后商品要重新拉取，清掉旧的商品/规格选择。
    wizard.product = null
    wizard.offerId = ''
  }
  wizard.merchant = row
  // 清空搜索词：进入第 3 步时它是商品搜索框，残留商家名会误过滤商品。
  wizard.merchantQuery = ''
  loadProducts()
}

function pickProduct(row) {
  wizard.product = row
  wizard.offerId = row.offers.length === 1 ? row.offers[0].offer_id : wizard.offerId
}

// 商品分页（客户端）。
const pagedProducts = computed(() => {
  const start = (productPage.value - 1) * PRODUCT_PAGE_SIZE
  return wizard.products.slice(start, start + PRODUCT_PAGE_SIZE)
})
const productTotalPages = computed(() =>
  Math.max(1, Math.ceil(wizard.products.length / PRODUCT_PAGE_SIZE)),
)
function goProductPage(n) {
  productPage.value = n
}

// 步骤导航：已完成步骤可点击回跳（只能往后，不能跳步往前——doc02 流程约束）。
function goBackStep(n) {
  if (n < wizard.step) wizard.step = n
}
function prevStep() {
  if (wizard.step > 1) wizard.step--
}
function nextStep() {
  createError.value = ''
  if (wizard.step === 1 && !wizard.buyer) {
    createError.value = '请先选择一个白名单用户。'
    return
  }
  if (wizard.step === 2 && !wizard.merchant) {
    createError.value = '请先选择一个商家。'
    return
  }
  if (wizard.step === 3 && !wizard.product) {
    createError.value = '请先选择一个商品。'
    return
  }
  if (wizard.step === 4) {
    if (!wizard.offerId) {
      createError.value = '请选择一个商品规格。'
      return
    }
    if (!wizard.triggerAt) {
      createError.value = '请设置任务触发时间。'
      return
    }
  }
  wizard.step++
}

const footSummary = computed(() => {
  const parts = []
  if (wizard.buyer) parts.push(wizard.buyer.account || wizard.buyer.name)
  if (wizard.merchant) parts.push(wizard.merchant.name)
  if (wizard.product) parts.push(`${wizard.product.title} × ${wizard.quantity}`)
  if (wizard.triggerAt) parts.push(`触发 ${wizard.triggerAt.replace('T', ' ')}`)
  return parts.length ? `已选：${parts.join(' · ')}` : '未选择买家'
})

const wizardSummary = computed(() => {
  const offer = wizard.product?.offers.find((item) => item.offer_id === wizard.offerId)
  return {
    buyer: wizard.buyer?.account || '—',
    balance: wizard.buyer?.balance || '—',
    merchant: wizard.merchant?.name || '—',
    product: wizard.product?.title || '—',
    spec: offer ? specText(offer) : '—',
    price: offer?.price || '—',
    quantity: wizard.quantity,
    triggerAt: wizard.triggerAt.replace('T', ' ') || '—',
  }
})

function specText(offer) {
  const spec = offer.specification || {}
  const entries = Object.entries(spec)
  return entries.length ? entries.map(([key, value]) => `${key}:${value}`).join(' / ') : '默认规格'
}

function merchantInitial(row) {
  return (row.name || '?').slice(0, 1)
}

async function submitCreate() {
  createBusy.value = true
  createError.value = ''
  try {
    const triggerIso = wizard.triggerAt ? new Date(wizard.triggerAt).toISOString() : undefined
    await adminWrite('/auto-orders', {
      account_id: wizard.buyer.id,
      merchant_id: wizard.merchant.id,
      offer_id: wizard.offerId,
      quantity: Number(wizard.quantity),
      trigger_at: triggerIso,
    })
    createOpen.value = false
    state.notice = '任务已创建，到触发时间将自动下单。'
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

    <!-- ===== C 版向导：左栏步骤导航 + 右侧内容 + 底部已选摘要栏 ===== -->
    <AppDrawer :open="createOpen" title="新建一键下单任务" wide @close="createOpen = false">
      <div class="wizard-rail">
        <nav class="rail-nav" aria-label="创建步骤">
          <button
            v-for="(label, index) in STEP_LABELS"
            :key="label"
            type="button"
            class="rail-item"
            :class="{
              'is-active': wizard.step === index + 1,
              'is-done': wizard.step > index + 1,
              'is-locked': wizard.step < index + 1,
            }"
            :disabled="wizard.step < index + 1"
            @click="goBackStep(index + 1)"
          >
            <span class="n">{{ wizard.step > index + 1 ? '✓' : index + 1 }}</span>
            <span>{{ label }}</span>
          </button>
        </nav>

        <div class="rail-body">
          <p v-if="createError" class="notice notice--error">{{ createError }}</p>

          <!-- 步骤 1：选择买家 -->
          <template v-if="wizard.step === 1">
            <div class="wizard-field">
              <label class="wizard-field__label" for="wizard-buyer">白名单用户</label>
              <input
                id="wizard-buyer"
                v-model="wizard.buyerQuery"
                type="search"
                placeholder="输入买家邮箱搜索（仅白名单）"
                @input="searchBuyers"
              />
              <p class="field__hint">只能选择白名单用户的账号；卡片上直接显示可用余额。</p>
            </div>
            <div class="pick-list">
              <button
                v-for="row in wizard.buyers"
                :key="row.id"
                type="button"
                class="pick-item"
                :class="{ 'is-sel': wizard.buyer && wizard.buyer.id === row.id }"
                @click="pickBuyer(row)"
              >
                <span class="ava ava--buyer">{{
                  (row.account || '?').slice(0, 1).toUpperCase()
                }}</span>
                <span class="meta">
                  <b>{{ row.account || row.name }}</b>
                  <span class="sub">可用余额 ¥ {{ row.balance }}</span>
                </span>
                <span class="pick-check" aria-hidden="true">✓</span>
              </button>
              <p v-if="!wizard.buyers.length" class="empty-state">输入关键字搜索白名单用户。</p>
            </div>
          </template>

          <!-- 步骤 2：选择商家 -->
          <template v-else-if="wizard.step === 2">
            <div class="wizard-field">
              <label class="wizard-field__label" for="wizard-merchant">商家</label>
              <input
                id="wizard-merchant"
                v-model="wizard.merchantQuery"
                type="search"
                placeholder="输入商家名称搜索"
                @input="searchMerchants"
              />
              <p class="field__hint">卡片展示头像、店铺 ID 与接单状态。</p>
            </div>
            <div class="pick-list">
              <button
                v-for="row in wizard.merchants"
                :key="row.id"
                type="button"
                class="pick-item"
                :class="{ 'is-sel': wizard.merchant && wizard.merchant.id === row.id }"
                @click="pickMerchant(row)"
              >
                <span class="ava">
                  <img v-if="row.avatar" :src="row.avatar" alt="" />
                  <template v-else>{{ merchantInitial(row) }}</template>
                </span>
                <span class="meta">
                  <b>{{ row.name }}</b>
                  <span class="sub">
                    <span class="mono">ID {{ row.id.slice(0, 8) }}</span>
                    <span>{{ row.status === 'ACTIVE' ? '接单中' : row.status }}</span>
                    <span>信誉分 {{ row.credit_score ?? '—' }}</span>
                  </span>
                </span>
                <span class="pick-check" aria-hidden="true">✓</span>
              </button>
              <p v-if="!wizard.merchants.length" class="empty-state">没有匹配的商家。</p>
            </div>
          </template>

          <!-- 步骤 3：选择商品（带缩略图与分页） -->
          <template v-else-if="wizard.step === 3">
            <div class="wizard-field">
              <label class="wizard-field__label" for="wizard-product"
                >商品（{{ wizard.merchant?.name }}）</label
              >
              <input
                id="wizard-product"
                v-model="wizard.merchantQuery"
                type="search"
                placeholder="输入商品名称搜索"
                @input="loadProducts"
              />
              <p class="field__hint">已下架商品不展示；卡片带缩略图、价格与规格数，支持分页。</p>
            </div>
            <div class="product-grid">
              <button
                v-for="row in pagedProducts"
                :key="row.id"
                type="button"
                class="product-card"
                :class="{ 'is-sel': wizard.product && wizard.product.id === row.id }"
                @click="pickProduct(row)"
              >
                <span class="thumb">
                  <img v-if="row.image" :src="row.image" alt="" />
                  <span class="thumb-empty">无图</span>
                </span>
                <span class="cardbody">
                  <b :title="row.title">{{ row.title }}</b>
                  <span class="price">¥ {{ row.price }}</span>
                  <span class="sub">{{ row.offers.length }} 个规格可选</span>
                </span>
                <span class="pick-check" aria-hidden="true">✓</span>
              </button>
              <p v-if="!pagedProducts.length" class="empty-state">该商家没有可售商品。</p>
            </div>
            <div class="product-pager">
              <button
                type="button"
                aria-label="上一页"
                :disabled="productPage <= 1"
                @click="goProductPage(productPage - 1)"
              >
                ‹
              </button>
              <button
                v-for="n in productTotalPages"
                :key="n"
                type="button"
                :class="{ 'is-on': productPage === n }"
                @click="goProductPage(n)"
              >
                {{ n }}
              </button>
              <button
                type="button"
                aria-label="下一页"
                :disabled="productPage >= productTotalPages"
                @click="goProductPage(productPage + 1)"
              >
                ›
              </button>
              <span class="pager-total"
                >共 {{ wizard.products.length }} 件商品 · 第 {{ productPage }}/{{
                  productTotalPages
                }}
                页</span
              >
            </div>
          </template>

          <!-- 步骤 4：规格数量时间 -->
          <template v-else-if="wizard.step === 4">
            <div class="wizard-field">
              <span class="wizard-field__label">商品规格</span>
              <label
                v-for="offer in wizard.product?.offers || []"
                :key="offer.offer_id"
                class="spec-row"
                :class="{ 'is-sel': wizard.offerId === offer.offer_id }"
              >
                <input
                  v-model="wizard.offerId"
                  type="radio"
                  :value="offer.offer_id"
                  name="wizard-offer"
                />
                <span class="spec-text">
                  {{ specText(offer) }}
                  <em>¥ {{ offer.price }}</em>
                  <em class="muted">库存 {{ offer.inventory }}</em>
                </span>
              </label>
              <p class="field__hint">规格失效会在创建时与触发下单时校验并提醒。</p>
            </div>
            <div class="wizard-field">
              <label class="wizard-field__label" for="wizard-qty">数量</label>
              <input id="wizard-qty" v-model="wizard.quantity" type="number" min="1" step="1" />
            </div>
            <div class="wizard-field">
              <label class="wizard-field__label" for="wizard-trigger"
                >触发时间（按电脑/服务器时间）</label
              >
              <input id="wizard-trigger" v-model="wizard.triggerAt" type="datetime-local" />
              <p class="field__hint">
                到触发时间自动下单；买家余额不足或规格已失效时任务标记失败并给出原因。
              </p>
            </div>
          </template>

          <!-- 步骤 5：确认创建 -->
          <template v-else>
            <dl class="detail-grid">
              <div>
                <dt>买家</dt>
                <dd>{{ wizardSummary.buyer }}（余额 ¥ {{ wizardSummary.balance }}）</dd>
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
          </template>
        </div>
      </div>

      <!-- 底部已选摘要栏 + 上一步/下一步 -->
      <div class="wizard-foot">
        <span class="foot-sum" :title="footSummary">{{ footSummary }}</span>
        <div class="foot-actions">
          <button type="button" class="btn" :disabled="wizard.step === 1" @click="prevStep">
            ← 上一步
          </button>
          <button v-if="wizard.step < 5" type="button" class="btn btn--primary" @click="nextStep">
            下一步 →
          </button>
          <button
            v-else
            type="button"
            class="btn btn--primary"
            :disabled="createBusy"
            @click="submitCreate"
          >
            {{ createBusy ? '创建中…' : '创建任务' }}
          </button>
        </div>
      </div>
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

/* ===== C 版向导：左栏步骤导航 ===== */
.wizard-rail {
  display: flex;
  min-height: 0;
}

.rail-nav {
  width: 190px;
  border-right: 1px solid var(--border, #e2e8f0);
  padding: 4px 10px 14px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: none;
}

.rail-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 10px;
  border-radius: 5px;
  color: var(--muted, #78869a);
  text-align: left;
}

.rail-item .n {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 11px;
  background: #eef1f6;
  flex: none;
}

.rail-item.is-active {
  background: var(--primary-soft, #eaf1fd);
  color: var(--primary, #2563eb);
  font-weight: 600;
}

.rail-item.is-active .n {
  background: var(--primary, #2563eb);
  color: #fff;
}

.rail-item.is-done {
  color: var(--ink, #18263b);
  cursor: pointer;
}

.rail-item.is-done:hover {
  background: var(--primary-soft, #eaf1fd);
}

.rail-item.is-done .n {
  background: var(--green, #16856a);
  color: #fff;
}

.rail-item.is-locked {
  opacity: 0.55;
  cursor: not-allowed;
}

.rail-body {
  flex: 1;
  min-width: 0;
  padding: 2px 4px 14px 16px;
}

/* ===== 向导字段：全宽 + 可见 label ===== */
.wizard-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 14px;
}

.wizard-field__label {
  font-size: 12px;
  font-weight: 600;
  color: var(--ink, #18263b);
}

.wizard-field input {
  width: 100%;
  min-height: 34px;
  padding: 7px 10px;
  border: 1px solid var(--border, #e2e8f0);
  border-radius: 3px;
  background: #fff;
  font: inherit;
  font-size: 13px;
  color: var(--ink, #18263b);
}

.wizard-field input:focus {
  outline: 0;
  border-color: var(--primary, #2563eb);
  box-shadow: 0 0 0 2px rgb(37 99 235 / 12%);
}

/* ===== 选项卡片 ===== */
.pick-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.pick-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border, #e2e8f0);
  border-radius: 6px;
  background: #fff;
  text-align: left;
}

.pick-item:hover {
  border-color: var(--primary, #2563eb);
}

.pick-item.is-sel {
  border-color: var(--primary, #2563eb);
  background: var(--primary-soft, #eaf1fd);
}

.ava {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  overflow: hidden;
  display: grid;
  place-items: center;
  color: #fff;
  font-weight: 600;
  font-size: 14px;
  background: var(--primary, #2563eb);
  flex: none;
}

.ava img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.meta {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.meta b {
  font-size: 13px;
}

.meta .sub {
  color: var(--muted, #78869a);
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.pick-check {
  margin-left: auto;
  color: var(--primary, #2563eb);
  opacity: 0;
}

.pick-item.is-sel .pick-check {
  opacity: 1;
}

/* ===== 商品卡片 + 分页 ===== */
.product-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.product-card {
  position: relative;
  display: flex;
  flex-direction: column;
  padding: 0;
  border: 1px solid var(--border, #e2e8f0);
  border-radius: 6px;
  background: #fff;
  overflow: hidden;
  text-align: left;
}

.product-card:hover {
  border-color: var(--primary, #2563eb);
}

.product-card.is-sel {
  border-color: var(--primary, #2563eb);
  background: var(--primary-soft, #eaf1fd);
}

.product-card .thumb {
  aspect-ratio: 1 / 1;
  height: auto;
  display: grid;
  place-items: center;
  background: #f2f5f9;
  color: var(--muted, #78869a);
}

.product-card .thumb-empty {
  font-size: 12px;
}

.product-card .thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.product-card .cardbody {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px 10px;
  min-width: 0;
}

.product-card .cardbody b {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.product-card .price {
  color: var(--red, #dc2638);
  font-weight: 600;
}

.product-card .sub {
  color: var(--muted, #78869a);
  font-size: 12px;
}

.product-pager {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
}

.product-pager button {
  min-width: 26px;
  height: 26px;
  border: 1px solid var(--border, #e2e8f0);
  border-radius: 4px;
  background: #fff;
  color: var(--ink, #18263b);
  font-size: 12px;
  display: grid;
  place-items: center;
}

.product-pager button.is-on {
  background: var(--primary, #2563eb);
  border-color: var(--primary, #2563eb);
  color: #fff;
}

.product-pager button[disabled] {
  opacity: 0.4;
  cursor: not-allowed;
}

.pager-total {
  color: var(--muted, #78869a);
  font-size: 12px;
  margin-left: 6px;
}

/* ===== 规格行 ===== */
.spec-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid var(--border, #e2e8f0);
  border-radius: 6px;
  margin-bottom: 6px;
  cursor: pointer;
}

.spec-row.is-sel {
  border-color: var(--primary, #2563eb);
  background: var(--primary-soft, #eaf1fd);
}

.spec-row .spec-text {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.spec-row em {
  font-style: normal;
  color: var(--red, #dc2638);
  font-weight: 600;
}

.spec-row em.muted {
  color: var(--muted, #78869a);
  font-weight: 400;
}

/* ===== 底部已选摘要栏 + 上一步/下一步 ===== */
.wizard-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 11px 18px;
  border-top: 1px solid var(--border, #e2e8f0);
  background: #fafbfd;
}

.foot-sum {
  flex: 1;
  min-width: 0;
  color: var(--muted, #78869a);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.foot-actions {
  display: flex;
  gap: 8px;
  flex: none;
}
</style>
