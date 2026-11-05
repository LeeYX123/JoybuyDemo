<script setup>
import { onMounted, reactive } from 'vue'

import AppDrawer from '@/components/AppDrawer.vue'
import AppModal from '@/components/AppModal.vue'
import AppPager from '@/components/AppPager.vue'
import { apiRequest, merchantWrite } from '@/lib/api'

const PAGE_SIZE = 10

const STATUS_TABS = [
  { key: 'ALL', label: '全部订单' },
  { key: 'PENDING', label: '待处理' },
  { key: 'SHIPPED', label: '已发货' },
  { key: 'COMPLETED', label: '已完成' },
]

const STATUS_LABELS = { PENDING: '待处理', SHIPPED: '已发货', COMPLETED: '已完成' }

const state = reactive({
  status: 'ALL',
  q: '',
  start: '',
  end: '',
  page: 1,
  loading: true,
  error: '',
  items: [],
  counts: {},
  total: 0,
  hasNext: false,
})

const detail = reactive({ value: null, open: false, loading: false })
const ship = reactive({ open: false, reference: '', busy: false, error: '' })

async function load() {
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page: String(state.page), page_size: String(PAGE_SIZE) })
    if (state.status !== 'ALL') params.set('status', state.status)
    if (state.q.trim()) params.set('q', state.q.trim())
    if (state.start) params.set('start', state.start)
    if (state.end) params.set('end', state.end)
    const payload = await apiRequest(`/merchant/orders?${params}`)
    state.items = payload.items || []
    state.counts = payload.counts || {}
    state.total = payload.total || 0
    state.hasNext = Boolean(payload.has_next)
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

function selectStatus(key) {
  state.status = key
  state.page = 1
  load()
}

function search() {
  state.page = 1
  load()
}

function resetFilters() {
  state.q = ''
  state.start = ''
  state.end = ''
  state.status = 'ALL'
  state.page = 1
  load()
}

function goPage(page) {
  state.page = page
  load()
}

async function openDetail(row) {
  detail.open = true
  detail.loading = true
  detail.value = null
  try {
    const payload = await apiRequest(`/merchant/orders/${row.id}`)
    detail.value = payload.order
  } catch (error) {
    state.error = error.message
    detail.open = false
  } finally {
    detail.loading = false
  }
}

function closeDetail() {
  detail.open = false
  detail.value = null
}

async function shipFromRow(row) {
  await openDetail(row)
  if (detail.value) openShip(detail.value)
}

function openShip(order) {
  detail.value = order
  ship.reference = ''
  ship.error = ''
  ship.open = true
}

function closeShip() {
  if (ship.busy) return
  ship.open = false
}

async function confirmShip() {
  if (!detail.value) return
  ship.busy = true
  ship.error = ''
  try {
    const payload = await merchantWrite(`/merchant/orders/${detail.value.id}/ship`, {
      reference: ship.reference,
    })
    ship.open = false
    if (detail.open) detail.value = payload.order
    await load()
  } catch (error) {
    ship.error = error.message
  } finally {
    ship.busy = false
  }
}

function fmtDate(value) {
  if (!value) return '—'
  return value.slice(0, 16).replace('T', ' ')
}

function nodeTime(order, index) {
  const times = order?.node_times || []
  return fmtDate(times[index])
}

function exportCsv() {
  const params = new URLSearchParams()
  if (state.status !== 'ALL') params.set('status', state.status)
  if (state.q.trim()) params.set('q', state.q.trim())
  if (state.start) params.set('start', state.start)
  if (state.end) params.set('end', state.end)
  window.open(`/api/v1/merchant/orders/export?${params}`, '_blank')
}

onMounted(load)
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>订单管理</h1>
        <p>订单状态只有待处理、已发货、已完成三种；物流节点是履约进度，不是第四种状态。</p>
      </div>
      <div class="page-intro__actions">
        <button type="button" class="btn btn--sm" @click="exportCsv">导出当前范围</button>
      </div>
    </div>

    <p v-if="state.error" class="notice notice--error">{{ state.error }}</p>

    <div class="tabs">
      <button
        v-for="tab in STATUS_TABS"
        :key="tab.key"
        type="button"
        :class="{ 'is-active': state.status === tab.key }"
        @click="selectStatus(tab.key)"
      >
        {{ tab.label }}
        <span class="tab-count">{{ state.counts[tab.key] ?? 0 }}</span>
      </button>
    </div>

    <div class="toolbar">
      <form class="filter-row" @submit.prevent="search">
        <input v-model="state.q" type="search" placeholder="订单号 / 商品名称 / 物流单号" />
        <label class="field-inline">
          下单起
          <input v-model="state.start" type="date" />
        </label>
        <label class="field-inline">
          止
          <input v-model="state.end" type="date" />
        </label>
        <button type="submit" class="btn btn--primary">查询</button>
        <button type="button" class="btn" @click="resetFilters">重置</button>
      </form>
    </div>

    <div class="card">
      <div class="card__body">
        <p v-if="state.loading" class="inline-loading">加载中…</p>
        <table v-else-if="state.items.length" class="data-table">
          <thead>
            <tr>
              <th>订单号</th>
              <th>商品</th>
              <th>订单金额</th>
              <th>发货成本</th>
              <th>状态</th>
              <th>下单时间</th>
              <th class="actions-col">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in state.items" :key="row.id">
              <td class="mono">{{ row.id.slice(0, 8) }}</td>
              <td>
                <div class="cell-strong">{{ row.title || '—' }}</div>
                <div class="cell-sub">× {{ row.quantity }}</div>
              </td>
              <td class="num">¥ {{ row.items_total }}</td>
              <td class="num">¥ {{ row.cost_total }}</td>
              <td>
                <span
                  class="tag"
                  :class="{
                    'tag--warn': row.status === 'PENDING',
                    'tag--ok': row.status === 'COMPLETED',
                  }"
                >
                  {{ STATUS_LABELS[row.status] || row.status }}
                </span>
              </td>
              <td>{{ fmtDate(row.created_at) }}</td>
              <td class="actions-col">
                <button type="button" class="btn btn--sm" @click="openDetail(row)">查看详情</button>
                <button
                  v-if="row.can_ship"
                  type="button"
                  class="btn btn--sm btn--primary"
                  @click="shipFromRow(row)"
                >
                  发货
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty-state">该范围内没有订单。</p>
      </div>
    </div>

    <AppPager
      :page="state.page"
      :page-size="PAGE_SIZE"
      :total="state.total"
      :has-next="state.hasNext"
      @change="goPage"
    />

    <AppDrawer :open="detail.open" title="订单详情" wide @close="closeDetail">
      <p v-if="detail.loading" class="inline-loading">加载中…</p>
      <template v-else-if="detail.value">
        <div class="ship-hero">
          <div>
            <span>发货成本合计</span>
            <strong class="num">¥ {{ detail.value.cost_total }}</strong>
          </div>
          <div>
            <span>订单金额</span>
            <b class="num">¥ {{ detail.value.items_total }}</b>
          </div>
          <div>
            <span>{{ detail.value.settled ? '盈利' : '回款后预估盈利' }}</span>
            <b class="num up">¥ {{ detail.value.profit }}</b>
          </div>
          <button
            v-if="detail.value.can_ship"
            type="button"
            class="btn btn--primary"
            @click="openShip(detail.value)"
          >
            确认发货
          </button>
        </div>

        <dl class="detail-grid">
          <div>
            <dt>订单号</dt>
            <dd class="mono">{{ detail.value.id }}</dd>
          </div>
          <div>
            <dt>父订单号</dt>
            <dd class="mono">{{ detail.value.order_id }}</dd>
          </div>
          <div>
            <dt>支付方式</dt>
            <dd>{{ detail.value.payment_method || '—' }}</dd>
          </div>
          <div>
            <dt>收件地区</dt>
            <dd>{{ detail.value.recipient_region || '—' }}</dd>
          </div>
          <div>
            <dt>物流凭证</dt>
            <dd>{{ detail.value.tracking_reference || '—' }}</dd>
          </div>
          <div>
            <dt>下单时间</dt>
            <dd>{{ fmtDate(detail.value.created_at) }}</dd>
          </div>
        </dl>

        <div v-if="detail.value.status !== 'COMPLETED'" class="order-detail-grid">
          <div class="card">
            <div class="card__head"><h2>物流进度</h2></div>
            <div class="card__body">
              <ol class="timeline">
                <li
                  v-for="(label, index) in detail.value.node_labels"
                  :key="label"
                  :class="{
                    'is-done': index <= detail.value.progress,
                    'is-current': index === detail.value.progress,
                  }"
                >
                  <span class="timeline__title">{{ label }}</span>
                  <span class="timeline__time">{{ nodeTime(detail.value, index) }}</span>
                </li>
              </ol>
              <p v-if="detail.value.progress < 0" class="hint-text">
                尚未发货，发货后从「待出库」开始记录时间。
              </p>
            </div>
          </div>

          <div class="card">
            <div class="card__head"><h2>商品与金额</h2></div>
            <div class="card__body">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>商品</th>
                    <th>数量</th>
                    <th>成交单价</th>
                    <th>单位成本</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in detail.value.items" :key="item.title">
                    <td>{{ item.title }}</td>
                    <td class="num">{{ item.quantity }}</td>
                    <td class="num">¥ {{ item.unit_price }}</td>
                    <td class="num">¥ {{ item.unit_cost ?? '—' }}</td>
                  </tr>
                </tbody>
              </table>
              <p class="hint-text">金额与成本都是下单时的快照，商品后续改价不影响历史订单。</p>
            </div>
          </div>
        </div>

        <div v-else class="card">
          <div class="card__head"><h2>已完成</h2></div>
          <div class="card__body">
            <dl class="detail-grid">
              <div>
                <dt>回款状态</dt>
                <dd>{{ detail.value.settled ? '已回款' : '未回款' }}</dd>
              </div>
              <div>
                <dt>回款时间</dt>
                <dd>{{ fmtDate(detail.value.settled_at) }}</dd>
              </div>
              <div>
                <dt>盈利</dt>
                <dd class="num up">¥ {{ detail.value.profit }}</dd>
              </div>
            </dl>
            <p class="hint-text">用户已确认收货，物流进度区不再展示。</p>
          </div>
        </div>
      </template>
    </AppDrawer>

    <AppModal
      :open="ship.open"
      title="确认发货"
      confirm-text="确认发货"
      :busy="ship.busy"
      @cancel="closeShip"
      @confirm="confirmShip"
    >
      <template v-if="detail.value">
        <p class="modal-lead">
          发货将按成本合计
          <b class="num">¥ {{ detail.value.cost_total }}</b>
          从钱包余额扣款，余额不足会拒绝发货。
        </p>
        <label class="field">
          <span class="field__label">物流单号 / 凭证（选填）</span>
          <input v-model="ship.reference" type="text" placeholder="例如 JB1000234" />
        </label>
        <p v-if="ship.error" class="notice notice--error">{{ ship.error }}</p>
      </template>
    </AppModal>
  </section>
</template>

<style scoped>
.tab-count {
  margin-left: 6px;
  font-size: 11px;
  color: var(--muted);
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.field-inline {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--muted);
}

.ship-hero {
  display: flex;
  align-items: center;
  gap: 24px;
  background: #fff7f8;
  border: 1px solid #f6d4d8;
  border-radius: 8px;
  padding: 14px 18px;
  margin-bottom: 16px;
}

.ship-hero span {
  display: block;
  font-size: 12px;
  color: var(--muted);
}

.ship-hero strong {
  font-size: 22px;
  color: var(--red);
}

.ship-hero .btn {
  margin-left: auto;
}

.order-detail-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: 1fr 1.2fr;
}

@media (max-width: 1000px) {
  .order-detail-grid {
    grid-template-columns: 1fr;
  }
}
</style>
