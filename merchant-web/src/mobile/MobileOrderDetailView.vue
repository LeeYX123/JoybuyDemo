<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import SheetModal from '@/mobile/components/SheetModal.vue'
import { apiRequest, merchantWrite } from '@/lib/api'
import { showToast } from '@/shell'

// 手机壳订单详情（folio route 4）：
// - 履约进度 disclosure：默认只显示当前节点，「查看全部进度」展开；
// - 已完成订单整个进度区隐藏（README 验收①）；
// - 订单与商品信息卡 + 金额卡（盈利大字）+ 底部 sticky「发货」操作条（can_ship）。

const route = useRoute()
const router = useRouter()

const state = ref({ loading: true, error: '', order: null })

const shipOpen = ref(false)
const shipReference = ref('')
const shipBusy = ref(false)
const shipError = ref('')

async function load() {
  state.value.loading = true
  state.value.error = ''
  try {
    const payload = await apiRequest(`/merchant/orders/${route.params.id}`)
    state.value.order = payload.order
  } catch (error) {
    state.value.error = error.message
    state.value.order = null
  } finally {
    state.value.loading = false
  }
}

const order = computed(() => state.value.order)

const STATUS_LABELS = { PENDING: '待处理', SHIPPED: '已发货', COMPLETED: '已完成' }
const STATUS_TAG = { PENDING: 'm-tag--warn', SHIPPED: 'm-tag--gray', COMPLETED: 'm-tag--ok' }

// 进度节点：progress 是当前节点下标；progress<0 表示尚未发货（无当前节点可展示）。
const nodes = computed(() => {
  const value = order.value
  if (!value) return []
  return (value.node_labels || []).map((label, index) => ({
    label,
    time: (value.node_times || [])[index] || '',
    done: index <= value.progress,
    current: index === value.progress,
  }))
})

const currentNodeLabel = computed(() => {
  const value = order.value
  if (!value || value.progress < 0) return ''
  return (value.node_labels || [])[value.progress] || ''
})

function fmtDate(value) {
  if (!value) return '—'
  return value.slice(0, 16).replace('T', ' ')
}

function openShip() {
  shipReference.value = order.value?.tracking_reference || ''
  shipError.value = ''
  shipOpen.value = true
}

async function confirmShip() {
  if (!order.value) return
  shipBusy.value = true
  shipError.value = ''
  try {
    const payload = await merchantWrite(`/merchant/orders/${order.value.id}/ship`, {
      reference: shipReference.value,
    })
    state.value.order = payload.order
    shipOpen.value = false
    showToast('发货成功，成本已从钱包扣除')
  } catch (error) {
    shipError.value = error.message
  } finally {
    shipBusy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="m-page m-od">
    <p v-if="state.error" class="m-error">{{ state.error }}</p>
    <p v-else-if="state.loading" class="m-loading">加载中…</p>

    <template v-else-if="order">
      <!-- 摘要卡。 -->
      <section class="m-card m-card--pad">
        <div class="m-od__status-row">
          <span class="m-tag" :class="STATUS_TAG[order.status]">
            {{ STATUS_LABELS[order.status] || order.status }}
          </span>
          <span class="m-hint m-num">下单时间 {{ fmtDate(order.created_at) }}</span>
        </div>
        <p class="m-od__order-id m-num">{{ order.id }}</p>
      </section>

      <!-- 履约进度 disclosure：默认当前节点，展开看全部（已完成订单整块隐藏）。 -->
      <details v-if="order.status !== 'COMPLETED'" class="m-progress" :open="false">
        <summary>
          <span class="m-progress__main">
            <span class="m-progress__label">订单履约进度</span>
            <strong>{{ currentNodeLabel || '尚未发货' }}</strong>
            <small v-if="order.progress < 0">发货后从「待出库」开始记录时间</small>
          </span>
          <span class="m-progress__toggle">
            <span class="m-progress__show">查看全部进度</span>
            <span class="m-progress__hide">收起进度</span>
          </span>
        </summary>
        <ol class="m-progress__list">
          <li
            v-for="(node, index) in nodes"
            :key="node.label"
            :class="{ 'is-done': node.done, 'is-current': node.current }"
            :aria-current="node.current ? 'step' : undefined"
          >
            <span class="m-progress__dot m-num">{{ index + 1 }}</span>
            <span class="m-progress__body">
              <b>{{ node.label }}<i v-if="node.current" class="m-tag m-tag--danger">当前</i></b>
              <time>{{ fmtDate(node.time) }}</time>
            </span>
          </li>
        </ol>
      </details>

      <!-- 金额卡：盈利大字（folio od-summary-amount / od-profit）。 -->
      <section class="m-card m-card--pad m-od__money">
        <dl>
          <div><dt>订单金额</dt><dd class="m-num">¥ {{ order.items_total }}</dd></div>
          <div><dt>发货成本</dt><dd class="m-num">¥ {{ order.cost_total }}</dd></div>
          <div><dt>{{ order.settled ? '盈利' : '预估盈利' }}</dt><dd class="m-num is-profit">¥ {{ order.profit }}</dd></div>
        </dl>
        <p v-if="order.status === 'COMPLETED'" class="m-hint">
          用户已确认收货{{ order.settled ? '，货款已回款' : '，回款处理中' }}{{ order.settled_at ? `（${fmtDate(order.settled_at)}）` : '' }}，物流进度区不再展示。
        </p>
      </section>

      <!-- 商品与订单信息。 -->
      <section class="m-card m-card--pad">
        <h2 class="m-section-title">商品与订单信息</h2>
        <dl class="m-dl">
          <div><dt>商品</dt><dd>{{ order.title || '—' }}</dd></div>
          <div><dt>支付方式</dt><dd>{{ order.payment_method || '—' }}</dd></div>
          <div><dt>收件地区</dt><dd>{{ order.recipient_region || '—' }}</dd></div>
          <div><dt>物流凭证</dt><dd>{{ order.tracking_reference || '—' }}</dd></div>
          <div><dt>父订单号</dt><dd class="m-num">{{ order.order_id }}</dd></div>
        </dl>
        <div v-if="order.items?.length" class="m-od__items">
          <div v-for="item in order.items" :key="item.title" class="m-od__item">
            <span class="m-od__item-name">{{ item.title }}</span>
            <span class="m-hint m-num">
              数量 {{ item.quantity }} · 单价 ¥ {{ item.unit_price }} · 单位成本 ¥
              {{ item.unit_cost ?? '—' }}
            </span>
            <b class="m-num">¥ {{ item.amount }}</b>
          </div>
          <p class="m-hint">金额与成本都是下单时的快照，商品后续改价不影响历史订单。</p>
        </div>
      </section>

      <!-- 底部 sticky 发货操作条（can_ship 时）。 -->
      <div v-if="order.can_ship" class="m-od__actions">
        <button type="button" class="m-btn m-btn--primary m-btn--block" @click="openShip">
          确认发货（扣款 ¥ {{ order.cost_total }}）
        </button>
      </div>
    </template>

    <SheetModal :open="shipOpen" title="确认发货" @close="shipOpen = false">
      <p class="m-hint" style="margin: 0 0 12px">
        发货将按成本合计 <b class="m-num">¥ {{ order?.cost_total }}</b>
        从钱包余额扣款，余额不足会拒绝发货。
      </p>
      <label class="m-field">
        <span class="m-field__label">物流单号 / 凭证（选填）</span>
        <input v-model="shipReference" class="m-input" type="text" placeholder="例如 JB1000234" />
      </label>
      <p v-if="shipError" class="m-error">{{ shipError }}</p>
      <div class="m-sheet-actions">
        <button type="button" class="m-btn" :disabled="shipBusy" @click="shipOpen = false">取消</button>
        <button type="button" class="m-btn m-btn--primary" :disabled="shipBusy" @click="confirmShip">
          {{ shipBusy ? '发货中…' : '确认发货' }}
        </button>
      </div>
    </SheetModal>

    <button type="button" class="m-btn m-od__back" @click="router.push('/orders')">返回订单列表</button>
  </div>
</template>

<style scoped>
.m-od__status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--m-space-2);
}

.m-od__order-id {
  margin: 10px 0 0;
  font-size: 13px;
  color: var(--m-ink);
  overflow-wrap: anywhere;
}

/* 履约进度 disclosure（folio concept-order-progress）。 */
.m-progress {
  background: var(--m-paper);
  border: 1px solid var(--m-line);
  border-radius: var(--m-radius);
  border-inline-start: 3px solid var(--m-accent);
  color: var(--m-ink);
}

.m-progress summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  padding: 14px 12px;
  min-height: 78px;
  list-style: none;
  cursor: pointer;
  background: var(--m-tint);
  border-radius: 6px;
}

.m-progress summary::-webkit-details-marker {
  display: none;
}

.m-progress__main {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.m-progress__label {
  font-size: 13px;
  color: var(--m-muted);
}

.m-progress__main strong {
  font-size: clamp(22px, 6vw, 28px);
  line-height: 1.2;
  color: var(--m-accent);
  overflow-wrap: anywhere;
}

.m-progress__main small {
  font-size: 11px;
  color: var(--m-muted);
}

.m-progress__toggle {
  flex: none;
  font-size: 13px;
  font-weight: 650;
  color: var(--m-accent);
}

.m-progress__toggle::after {
  content: '';
  display: inline-block;
  width: 6px;
  height: 6px;
  border: solid currentColor;
  border-width: 0 1.5px 1.5px 0;
  transform: translateY(-2px) rotate(45deg);
  margin-inline-start: 6px;
}

.m-progress[open] .m-progress__toggle::after {
  transform: translateY(1px) rotate(225deg);
}

.m-progress:not([open]) .m-progress__hide,
.m-progress[open] .m-progress__show {
  display: none;
}

/* 8 节点时间线（od-node）。 */
.m-progress__list {
  margin: 0;
  padding: 4px 12px 12px 14px;
  list-style: none;
  border-top: 1px solid var(--m-line);
}

.m-progress__list li {
  position: relative;
  display: flex;
  gap: 12px;
  min-height: 52px;
  padding: 6px 0 10px;
  color: var(--m-muted);
}

.m-progress__list li:not(:last-child)::before {
  content: '';
  position: absolute;
  left: 8px;
  top: 24px;
  bottom: 0;
  width: 1px;
  background: #e9edf2;
}

.m-progress__list li.is-done:not(:last-child)::before {
  background: #f0c2c7;
}

.m-progress__dot {
  flex: 0 0 17px;
  width: 17px;
  height: 17px;
  margin-top: 3px;
  display: grid;
  place-items: center;
  border: 1px solid #dde2e9;
  border-radius: 50%;
  background: #fff;
  font-size: 10px;
  color: var(--m-muted);
  z-index: 1;
}

.m-progress__list li.is-done .m-progress__dot {
  color: #d73040;
  border-color: #f0bdc4;
  background: #fff8f8;
}

.m-progress__list li.is-current .m-progress__dot {
  background: var(--m-accent);
  color: #fff;
  border-color: var(--m-accent);
  box-shadow: 0 0 0 4px var(--m-tint);
}

.m-progress__body {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.m-progress__body b {
  font-size: 13px;
  font-weight: 500;
  color: inherit;
  display: flex;
  align-items: center;
  gap: 8px;
}

.m-progress__list li.is-current .m-progress__body b {
  font-weight: 600;
  color: var(--m-accent);
}

.m-progress__body time {
  font-size: 11px;
  color: var(--m-muted);
  font-variant-numeric: tabular-nums;
}

/* 金额卡。 */
.m-od__money dl {
  display: grid;
  gap: 10px;
  margin: 0;
}

.m-od__money dl > div {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.m-od__money dt {
  font-size: 12px;
  color: var(--m-muted);
}

.m-od__money dd {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--m-ink);
}

.m-od__money dd.is-profit {
  font-size: 24px;
  color: var(--m-accent);
}

.m-od__money .m-hint {
  margin: 10px 0 0;
  padding-top: 10px;
  border-top: 1px solid var(--m-line);
}

.m-dl {
  display: grid;
  gap: 10px;
  margin: 10px 0 0;
}

.m-dl > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
}

.m-dl dt {
  color: var(--m-muted);
  flex: none;
}

.m-dl dd {
  margin: 0;
  color: var(--m-ink);
  text-align: right;
  overflow-wrap: anywhere;
}

.m-od__items {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--m-line);
  display: grid;
  gap: 10px;
}

.m-od__item {
  display: grid;
  gap: 3px;
}

.m-od__item-name {
  font-size: 14px;
  color: var(--m-ink);
  overflow-wrap: anywhere;
}

.m-od__item b {
  font-size: 14px;
  color: var(--m-ink);
}

/* sticky 发货操作条（folio merchant-detail-actions）。 */
.m-od__actions {
  position: sticky;
  z-index: 4;
  bottom: max(8px, env(safe-area-inset-bottom));
  padding: 8px;
  background: var(--m-paper);
  border: 1px solid var(--m-line);
  border-radius: var(--m-radius);
}

.m-od__back {
  margin-top: 4px;
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
