<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import AppDrawer from '@/components/AppDrawer.vue'
import AppModal from '@/components/AppModal.vue'
import AppPager from '@/components/AppPager.vue'
import StatusTag from '@/components/StatusTag.vue'
import { adminWrite } from '@/composables/useAdminApi'
import { apiRequest } from '@/lib/api'

const TABS = [
  { key: '', label: '全部订单' },
  { key: 'PENDING', label: '待处理' },
  { key: 'SHIPPED', label: '已发货' },
  { key: 'COMPLETED', label: '已完成' },
]

const NODE_LABELS = [
  '待出库',
  '已出库',
  '已揽收',
  '运输中',
  '到达目的地网点',
  '派送中',
  '已签收',
  '用户确认收货',
]

const state = reactive({
  status: '',
  q: '',
  start: '',
  end: '',
  page: 1,
  items: [],
  meta: { total: 0, page_size: 20, has_next: false },
  loading: false,
  error: '',
})

const detail = ref(null)
const detailLoading = ref(false)
const actionError = ref('')
const busy = ref(false)

const nodeForm = reactive({ node_index: '', reference: '' })
const timeForm = reactive({ created_at: '', nodes: Array(8).fill('') })
const confirmComplete = ref(false)

const nextNodes = computed(() => {
  if (!detail.value) return []
  return NODE_LABELS.map((label, index) => ({ label, index })).filter(
    (item) => item.index > detail.value.progress,
  )
})

async function load(resetPage = false) {
  if (resetPage) state.page = 1
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page: String(state.page) })
    if (state.status) params.set('status', state.status)
    if (state.q.trim()) params.set('q', state.q.trim())
    if (state.start) params.set('start', state.start)
    if (state.end) params.set('end', state.end)
    const payload = await apiRequest(`/merchant-orders?${params}`)
    state.items = payload.items
    state.meta = payload
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

function toLocalInput(value) {
  if (!value) return ''
  return value.replace('T', ' ').slice(0, 16).replace(' ', 'T')
}

async function openDetail(row) {
  detail.value = null
  detailLoading.value = true
  actionError.value = ''
  try {
    const payload = await apiRequest(`/merchant-orders/${row.id}`)
    detail.value = payload.order
    nodeForm.node_index = String(payload.order.progress + 1 > 7 ? 7 : payload.order.progress + 1)
    nodeForm.reference = payload.order.tracking_reference || ''
    timeForm.created_at = toLocalInput(payload.order.created_at)
    timeForm.nodes = NODE_LABELS.map((_, index) =>
      toLocalInput((payload.order.node_times || [])[index]),
    )
  } catch (error) {
    state.error = error.message
  } finally {
    detailLoading.value = false
  }
}

async function advance() {
  if (!detail.value) return
  busy.value = true
  actionError.value = ''
  try {
    const payload = await adminWrite(
      `/merchant-orders/${detail.value.id}/actions`,
      {
        action: 'advance',
        node_index: Number(nodeForm.node_index),
        reference: nodeForm.reference,
      },
      'POST',
    )
    detail.value = payload.order
    await load()
  } catch (error) {
    actionError.value = error.message
  } finally {
    busy.value = false
  }
}

async function completeAll() {
  if (!detail.value) return
  busy.value = true
  actionError.value = ''
  try {
    const payload = await adminWrite(`/merchant-orders/${detail.value.id}/actions`, {
      action: 'complete_all',
    })
    detail.value = payload.order
    confirmComplete.value = false
    await load()
  } catch (error) {
    actionError.value = error.message
  } finally {
    busy.value = false
  }
}

async function saveTimes() {
  if (!detail.value) return
  busy.value = true
  actionError.value = ''
  try {
    const payload = await adminWrite(
      `/merchant-orders/${detail.value.id}`,
      {
        created_at: timeForm.created_at || undefined,
        node_times: timeForm.nodes.map((value) => value || null),
      },
      'PATCH',
    )
    detail.value = payload.order
    await load()
  } catch (error) {
    actionError.value = error.message
  } finally {
    busy.value = false
  }
}

async function openDetailById(id) {
  await openDetail({ id })
}

function formatTime(value) {
  if (!value) return '—'
  return value.replace('T', ' ').slice(0, 16)
}

function exportCsv() {
  const params = new URLSearchParams()
  if (state.status) params.set('status', state.status)
  if (state.q.trim()) params.set('q', state.q.trim())
  if (state.start) params.set('start', state.start)
  if (state.end) params.set('end', state.end)
  window.open(`/api/v1/admin/merchant-orders/export?${params}`, '_blank')
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
  state.q = ''
  state.start = ''
  state.end = ''
  state.status = ''
  load(true)
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
        <h1>订单管理</h1>
        <p>按商家子单维护物流节点；推进到「用户确认收货」时一次性回款，重复提交不会重复入账。</p>
      </div>
      <div class="page-intro__actions">
        <button type="button" class="btn" @click="exportCsv">导出订单</button>
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
          v-model="state.q"
          type="search"
          placeholder="子单号 / 订单号 / 商家 / 商品"
          @keyup.enter="load(true)"
        />
        <input v-model="state.start" type="date" aria-label="下单开始日期" />
        <span class="cell-sub">至</span>
        <input v-model="state.end" type="date" aria-label="下单结束日期" />
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
              <th>子单 / 订单</th>
              <th>商家</th>
              <th>成交金额</th>
              <th>发货成本</th>
              <th>盈利</th>
              <th>状态</th>
              <th>当前节点</th>
              <th>下单时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in state.items" :key="row.id">
              <td>
                <span class="cell-strong">{{ row.id.slice(0, 8) }}</span>
                <span class="cell-sub">{{ row.order_id.slice(0, 8) }}</span>
              </td>
              <td>{{ row.merchant.name }}</td>
              <td class="num">¥ {{ row.items_total }}</td>
              <td class="num">¥ {{ row.cost_total }}</td>
              <td
                class="num"
                :style="{ color: Number(row.profit) < 0 ? 'var(--colour-error)' : 'var(--green)' }"
              >
                ¥ {{ row.profit }}
              </td>
              <td><StatusTag :value="row.status" /></td>
              <td>
                {{ row.progress >= 0 ? NODE_LABELS[row.progress] : '未发货' }}
                <span v-if="row.settled" class="cell-sub">已回款</span>
              </td>
              <td>{{ formatTime(row.created_at) }}</td>
              <td>
                <div class="row-actions">
                  <button type="button" class="btn btn--sm" @click="openDetail(row)">详情</button>
                </div>
              </td>
            </tr>
            <tr v-if="!state.loading && state.items.length === 0">
              <td colspan="9" class="data-table__empty">没有匹配的订单。</td>
            </tr>
            <tr v-if="state.loading">
              <td colspan="9" class="data-table__empty">加载中…</td>
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
      :title="detail ? `订单 ${detail.id.slice(0, 8)}` : '订单详情'"
      wide
      @close="closeDetail"
    >
      <p v-if="detailLoading" class="inline-loading">加载中…</p>
      <template v-if="detail">
        <p v-if="actionError" class="notice notice--error">{{ actionError }}</p>

        <div class="stat-row">
          <div class="stat-card">
            <div class="stat-card__label">订单金额</div>
            <div class="stat-card__value">¥ {{ detail.items_total }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-card__label">发货成本合计</div>
            <div class="stat-card__value" style="color: var(--red)">¥ {{ detail.cost_total }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-card__label">{{ detail.settled ? '盈利' : '回款后预估盈利' }}</div>
            <div class="stat-card__value">¥ {{ detail.profit }}</div>
          </div>
        </div>

        <dl class="detail-grid">
          <div>
            <dt>商家</dt>
            <dd>{{ detail.merchant.name }}</dd>
          </div>
          <div>
            <dt>父订单</dt>
            <dd>{{ detail.order_id }}</dd>
          </div>
          <div>
            <dt>买家</dt>
            <dd>{{ detail.buyer?.name || '—' }}</dd>
          </div>
          <div>
            <dt>支付方式</dt>
            <dd>{{ detail.payment_method || '—' }}</dd>
          </div>
          <div>
            <dt>收件地区</dt>
            <dd>{{ detail.recipient_region || '—' }}</dd>
          </div>
          <div>
            <dt>物流凭证</dt>
            <dd>{{ detail.tracking_reference || '—' }}</dd>
          </div>
          <div>
            <dt>状态</dt>
            <dd><StatusTag :value="detail.status" /></dd>
          </div>
          <div>
            <dt>下单时间</dt>
            <dd>{{ formatTime(detail.created_at) }}</dd>
          </div>
          <div>
            <dt>发货时间</dt>
            <dd>{{ formatTime(detail.shipped_at) }}</dd>
          </div>
          <div>
            <dt>回款时间</dt>
            <dd>{{ formatTime(detail.settled_at) }}</dd>
          </div>
        </dl>

        <h3 class="section-title">订单商品</h3>
        <table class="data-table">
          <thead>
            <tr>
              <th>商品</th>
              <th>数量</th>
              <th>成交单价</th>
              <th>单位成本</th>
              <th>金额</th>
              <th>成本合计</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in detail.items" :key="item.title">
              <td>{{ item.title }}</td>
              <td class="num">{{ item.quantity }}</td>
              <td class="num">¥ {{ item.unit_price }}</td>
              <td class="num">{{ item.unit_cost ? `¥ ${item.unit_cost}` : '—' }}</td>
              <td class="num">¥ {{ item.amount }}</td>
              <td class="num">¥ {{ item.cost_amount }}</td>
            </tr>
          </tbody>
        </table>

        <h3 class="section-title">物流进度</h3>
        <ol class="timeline">
          <li
            v-for="(label, index) in NODE_LABELS"
            :key="label"
            :class="{
              'is-done': index < detail.progress,
              'is-current': index === detail.progress,
            }"
          >
            <div class="timeline__title">{{ label }}</div>
            <div class="timeline__time">{{ formatTime((detail.node_times || [])[index]) }}</div>
          </li>
        </ol>

        <h3 class="section-title">更新订单进度</h3>
        <div class="form-grid form-grid--tight">
          <div class="field">
            <label for="node-select">目标节点</label>
            <select id="node-select" v-model="nodeForm.node_index">
              <option v-for="node in nextNodes" :key="node.index" :value="String(node.index)">
                {{ node.label }}
              </option>
            </select>
          </div>
          <div class="field">
            <label for="node-reference">物流凭证</label>
            <input id="node-reference" v-model="nodeForm.reference" type="text" maxlength="120" />
          </div>
          <div class="field">
            <span class="field__label">&nbsp;</span>
            <button
              type="button"
              class="btn btn--primary"
              :disabled="busy || detail.status === 'PENDING' || nextNodes.length === 0"
              @click="advance"
            >
              推进节点
            </button>
          </div>
        </div>
        <p v-if="detail.status === 'PENDING'" class="field__hint">
          订单尚未发货，需由商家端「确认发货」后才会进入物流节点。
        </p>

        <h3 class="section-title">修改时间（后台留痕）</h3>
        <div class="form-grid form-grid--tight">
          <div class="field">
            <label for="created-at">下单时间</label>
            <input id="created-at" v-model="timeForm.created_at" type="datetime-local" />
          </div>
          <div v-for="(label, index) in NODE_LABELS" :key="label" class="field">
            <label :for="`node-time-${index}`">{{ label }}</label>
            <input
              :id="`node-time-${index}`"
              v-model="timeForm.nodes[index]"
              type="datetime-local"
            />
          </div>
        </div>
        <div class="form-actions">
          <button type="button" class="btn" :disabled="busy" @click="saveTimes">保存时间</button>
        </div>
      </template>

      <template v-if="detail" #footer>
        <button
          type="button"
          class="btn"
          :disabled="detail.status === 'PENDING' || detail.progress >= 7"
          @click="confirmComplete = true"
        >
          一键完成全部节点
        </button>
        <button
          type="button"
          class="btn btn--primary"
          :disabled="busy"
          @click="openDetailById(detail.id)"
        >
          刷新
        </button>
      </template>
    </AppDrawer>

    <AppModal
      v-if="confirmComplete"
      title="确认完成全部节点"
      confirm-text="确认完成并回款"
      :busy="busy"
      @cancel="confirmComplete = false"
      @confirm="completeAll"
    >
      <p>
        将把当前订单推进到「用户确认收货」，订单状态改为已完成，并按订单金额一次性回款到商家钱包。
        该操作只影响当前这一笔，且不会重复入账。
      </p>
    </AppModal>
  </section>
</template>
