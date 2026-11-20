<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import SheetModal from '@/mobile/components/SheetModal.vue'
import { apiRequest, merchantWrite } from '@/lib/api'
import { showToast } from '@/shell'

// 手机壳订单管理（folio route 3）：状态 chips + 日期筛选 → 订单卡片流
// （单号+状态 / 商品行 / 金额·成本·盈利三列 / 底部操作）。
// 后端状态枚举 PENDING / SHIPPED / COMPLETED，payload 见 views_merchant_orders.py。

const router = useRouter()
const PAGE_SIZE = 10

const STATUS_TABS = [
  { key: 'ALL', label: '全部' },
  { key: 'PENDING', label: '待处理' },
  { key: 'SHIPPED', label: '已发货' },
  { key: 'COMPLETED', label: '已完成' },
]

const STATUS_LABELS = { PENDING: '待处理', SHIPPED: '已发货', COMPLETED: '已完成' }
const STATUS_TAG = {
  PENDING: 'm-tag--warn',
  SHIPPED: 'm-tag--gray',
  COMPLETED: 'm-tag--ok',
}

const state = reactive({
  status: 'ALL',
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

const shipTarget = ref(null)
const shipReference = ref('')
const shipBusy = ref(false)
const shipError = ref('')

async function load() {
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page: String(state.page), page_size: String(PAGE_SIZE) })
    if (state.status !== 'ALL') params.set('status', state.status)
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

function applyDateFilter() {
  state.page = 1
  load()
}

function resetDateFilter() {
  state.start = ''
  state.end = ''
  state.page = 1
  load()
}

function openShip(row) {
  shipTarget.value = row
  shipReference.value = ''
  shipError.value = ''
}

async function confirmShip() {
  if (!shipTarget.value) return
  shipBusy.value = true
  shipError.value = ''
  try {
    await merchantWrite(`/merchant/orders/${shipTarget.value.id}/ship`, {
      reference: shipReference.value,
    })
    shipTarget.value = null
    showToast('发货成功，成本已从钱包扣除')
    await load()
  } catch (error) {
    shipError.value = error.message
  } finally {
    shipBusy.value = false
  }
}

function fmtDate(value) {
  if (!value) return '—'
  return value.slice(0, 16).replace('T', ' ')
}

const shipLabel = computed(() =>
  shipTarget.value ? `确认发货并扣除成本 ¥ ${shipTarget.value.cost_total}` : '',
)

onMounted(load)
</script>

<template>
  <div class="m-page">
    <!-- 状态 chips（folio tabs）。 -->
    <div class="m-chips" role="tablist" aria-label="订单状态">
      <button
        v-for="tab in STATUS_TABS"
        :key="tab.key"
        type="button"
        class="m-chip"
        role="tab"
        :aria-selected="state.status === tab.key"
        :class="{ 'is-active': state.status === tab.key }"
        @click="selectStatus(tab.key)"
      >
        {{ tab.label }}
        <span class="m-chip__count m-num">{{ state.counts[tab.key] ?? 0 }}</span>
      </button>
    </div>

    <!-- 日期筛选行。 -->
    <form class="m-datebar" @submit.prevent="applyDateFilter">
      <input v-model="state.start" type="date" aria-label="下单起始日期" />
      <input v-model="state.end" type="date" aria-label="下单截止日期" />
      <button type="submit" class="m-btn m-btn--primary">查询</button>
      <button v-if="state.start || state.end" type="button" class="m-btn" @click="resetDateFilter">重置</button>
    </form>

    <p v-if="state.error" class="m-error">{{ state.error }}</p>
    <p v-if="state.loading" class="m-loading">加载中…</p>

    <!-- 订单卡片流（folio merchant-order-list）。 -->
    <div v-else-if="state.items.length" class="m-order-list" role="list">
      <article v-for="row in state.items" :key="row.id" class="m-order" role="listitem">
        <div class="m-order__top">
          <span class="m-num">{{ row.id.slice(0, 8) }}…</span>
          <span class="m-tag" :class="STATUS_TAG[row.status]">
            {{ STATUS_LABELS[row.status] || row.status }}
          </span>
        </div>
        <button type="button" class="m-order__item" @click="router.push(`/orders/${row.id}`)">
          <span class="m-order__art" aria-hidden="true">{{ (row.title || '商').slice(0, 1) }}</span>
          <span class="m-order__info">
            <strong>{{ row.title || '—' }}</strong>
            <small>数量 × {{ row.quantity }}</small>
            <small>{{ fmtDate(row.created_at) }}</small>
          </span>
        </button>
        <dl class="m-order__costs">
          <div><dt>订单金额</dt><dd class="m-num">¥ {{ row.items_total }}</dd></div>
          <div><dt>发货成本</dt><dd class="m-num">¥ {{ row.cost_total }}</dd></div>
          <div><dt>{{ row.settled ? '盈利' : '预估盈利' }}</dt><dd class="m-num is-profit">¥ {{ row.profit }}</dd></div>
        </dl>
        <div class="m-order__footer">
          <button type="button" class="m-btn" @click="router.push(`/orders/${row.id}`)">查看详情</button>
          <button
            v-if="row.can_ship"
            type="button"
            class="m-btn m-btn--primary"
            @click="openShip(row)"
          >
            发货
          </button>
        </div>
      </article>
    </div>
    <p v-else class="m-empty">暂无符合条件的订单，请尝试调整筛选条件。</p>

    <div v-if="state.total" class="m-pager">
      <button type="button" class="m-btn" :disabled="state.page <= 1" @click="state.page -= 1; load()">上一页</button>
      <span class="m-num">第 {{ state.page }} 页 · 共 {{ state.total }} 单</span>
      <button type="button" class="m-btn" :disabled="!state.hasNext" @click="state.page += 1; load()">下一页</button>
    </div>

    <!-- 发货确认 sheet：reference 选填，语义与桌面 AppModal 一致。 -->
    <SheetModal :open="Boolean(shipTarget)" title="确认发货" @close="shipTarget = null">
      <template v-if="shipTarget">
        <p class="m-hint" style="margin: 0 0 12px">
          订单 {{ shipTarget.id.slice(0, 8) }}… 发货将按成本合计
          <b class="m-num">¥ {{ shipTarget.cost_total }}</b>
          从钱包余额扣款，余额不足会拒绝发货。
        </p>
        <label class="m-field">
          <span class="m-field__label">物流单号 / 凭证（选填）</span>
          <input v-model="shipReference" class="m-input" type="text" placeholder="例如 JB1000234" />
        </label>
        <p v-if="shipError" class="m-error">{{ shipError }}</p>
        <p class="m-hint" style="margin: 10px 0 0">{{ shipLabel }}</p>
        <div class="m-sheet-actions">
          <button type="button" class="m-btn" :disabled="shipBusy" @click="shipTarget = null">取消</button>
          <button type="button" class="m-btn m-btn--primary" :disabled="shipBusy" @click="confirmShip">
            {{ shipBusy ? '发货中…' : '确认发货' }}
          </button>
        </div>
      </template>
    </SheetModal>
  </div>
</template>

<style scoped>
.m-datebar {
  display: flex;
  align-items: center;
  gap: var(--m-space-2);
  flex-wrap: wrap;
}

.m-datebar input[type='date'] {
  flex: 1 1 110px;
  min-width: 0;
  min-height: 40px;
  padding: 4px 8px;
  border: 1px solid var(--m-line);
  border-radius: var(--m-radius);
  background: var(--m-paper);
  font-size: 14px;
  color: var(--m-ink);
}

.m-datebar .m-btn {
  min-height: 40px;
  padding: 0 14px;
}

/* 订单卡（folio merchant-order：顶部红边上卡）。 */
.m-order-list {
  display: grid;
  gap: 14px;
}

.m-order {
  display: grid;
  background: var(--m-paper);
  border: 0;
  border-top: 2px solid var(--m-accent);
  border-bottom: 1px solid var(--m-line);
  overflow: hidden;
}

.m-order__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--m-space-2);
  padding: 9px 12px;
  border-block: 1px solid var(--m-line);
  font-size: 12px;
  color: var(--m-muted);
}

.m-order__item {
  display: grid;
  grid-template-columns: 62px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  padding: 11px 12px;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
  width: 100%;
}

.m-order__art {
  display: grid;
  place-items: center;
  width: 62px;
  height: 62px;
  border-radius: 7px;
  background: var(--m-canvas);
  color: var(--m-muted);
  font-size: 20px;
  font-weight: 650;
}

.m-order__info {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.m-order__info strong {
  font-size: 15px;
  color: var(--m-ink);
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.m-order__info small {
  color: var(--m-muted);
  font-size: 12px;
}

.m-order__costs {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 5px;
  margin: 0 12px;
  padding: 9px 8px;
  border-bottom: 1px solid var(--m-line);
}

.m-order__costs dt {
  color: var(--m-muted);
  font-size: 12px;
}

.m-order__costs dd {
  margin: 2px 0 0;
  font-weight: 700;
  font-size: 14px;
  color: var(--m-ink);
}

.m-order__costs dd.is-profit {
  color: var(--m-accent);
}

.m-order__footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--m-space-2);
  padding: 8px 12px;
}

.m-order__footer .m-btn {
  min-height: 38px;
  padding: 0 14px;
}

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

.m-sheet-actions {
  display: flex;
  gap: var(--m-space-2);
  margin-top: var(--m-space-4);
}

.m-sheet-actions .m-btn {
  flex: 1;
}
</style>
