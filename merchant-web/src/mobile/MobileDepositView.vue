<script setup>
import { computed, onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'

import { apiRequest } from '@/lib/api'

// 手机壳保证金（folio route 6）：摘要格 + 联系客服 + 明细列表 + 折叠规则说明。

const router = useRouter()
const PAGE_SIZE = 10

const state = reactive({
  loading: true,
  error: '',
  deposit: null,
  items: [],
  total: 0,
  page: 1,
  hasNext: false,
})

async function load() {
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page: String(state.page), page_size: String(PAGE_SIZE) })
    const payload = await apiRequest(`/merchant/deposit?${params}`)
    state.deposit = payload.deposit
    state.items = payload.items || []
    state.total = payload.total || 0
    state.hasNext = Boolean(payload.has_next)
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

function fmtDate(value) {
  if (!value) return '—'
  return value.slice(0, 16).replace('T', ' ')
}

function amountText(row) {
  return `${Number(row.amount) >= 0 ? '+' : '−'}${Math.abs(Number(row.amount)).toFixed(2)}`
}

const summaryCards = computed(() => {
  const deposit = state.deposit
  if (!deposit) return []
  return [
    {
      label: '保证金余额',
      value: `¥ ${deposit.balance}`,
      wide: true,
    },
    { label: '应缴金额', value: `¥ ${deposit.required}` },
    { label: '待缴金额', value: `¥ ${deposit.pending}` },
    {
      label: '缴纳状态',
      value: deposit.status === 'PAID' ? '已缴纳' : '待缴保证金',
      ok: deposit.status === 'PAID',
    },
  ]
})

onMounted(load)
</script>

<template>
  <div class="m-page">
    <p v-if="state.error" class="m-error">{{ state.error }}</p>
    <p v-if="state.loading" class="m-loading">加载中…</p>

    <template v-else-if="state.deposit">
      <!-- 未启用保证金：与桌面同口径的说明。 -->
      <div v-if="!state.deposit.enabled" class="m-card m-card--pad">
        <h1 class="m-section-title">该店铺未启用保证金</h1>
        <p class="m-hint" style="margin: 10px 0 0">
          当前店铺在入驻审核时选择了免缴保证金，因此没有保证金记录。该规则在首次审核通过后已锁定，无需也无法补缴。
        </p>
      </div>

      <template v-else>
        <!-- 摘要格（folio deposit-summary：余额格加宽）。 -->
        <section class="m-deposit-summary">
          <div
            v-for="card in summaryCards"
            :key="card.label"
            class="m-deposit-stat"
            :class="{ 'is-wide': card.wide }"
          >
            <span>{{ card.label }}</span>
            <strong :class="{ 'is-ok': card.ok }" class="m-num">{{ card.value }}</strong>
          </div>
          <button
            type="button"
            class="m-btn m-btn--primary m-btn--block m-deposit-contact"
            @click="router.push('/messages?open=support')"
          >
            联系客服缴纳
          </button>
        </section>

        <p class="m-notice">保证金余额与钱包余额是两个账户：保证金不参与发货扣款，充值请联系平台客服。</p>

        <!-- 明细列表（folio deposit-ledger）。 -->
        <section class="m-card">
          <div class="m-deposit-head"><h2>保证金记录</h2></div>
          <p v-if="state.loading" class="m-loading">加载中…</p>
          <ul v-else-if="state.items.length" class="m-ledger">
            <li v-for="row in state.items" :key="row.id">
              <div>
                <strong>{{ row.kind_label }}</strong>
                <small>{{ fmtDate(row.occurred_at) }}</small>
              </div>
              <b :class="Number(row.amount) >= 0 ? 'is-in' : 'is-out'" class="m-num">{{ amountText(row) }}</b>
              <p class="m-num">
                {{ row.related_id || '—' }} · 余额 ¥ {{ row.balance_after }}{{ row.note ? ` · ${row.note}` : '' }}
              </p>
            </li>
          </ul>
          <p v-else class="m-empty">还没有保证金记录。</p>
          <div v-if="state.total" class="m-ledger-pager">
            <button type="button" class="m-btn" :disabled="state.page <= 1" @click="state.page -= 1; load()">上一页</button>
            <span class="m-num">第 {{ state.page }} 页 · 共 {{ state.total }} 条</span>
            <button type="button" class="m-btn" :disabled="!state.hasNext" @click="state.page += 1; load()">下一页</button>
          </div>
        </section>

        <!-- 折叠规则说明。 -->
        <details class="m-disclosure">
          <summary>保证金规则说明</summary>
          <div class="m-disclosure__body m-hint">
            保证金由平台审核时确定，应缴金额不可修改；缴足后才能上架商品。余额不足时平台会通知补缴；
            保证金不参与发货扣款，商家不能自行修改余额，充值请联系平台客服。
          </div>
        </details>
      </template>
    </template>
  </div>
</template>

<style scoped>
/* 摘要格（folio deposit-summary：首格跨两列强调）。 */
.m-deposit-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--m-space-2);
  padding: var(--m-space-3);
  border: 1px solid var(--m-line);
  border-radius: 9px;
  background: var(--m-paper);
}

.m-deposit-stat {
  padding: 10px;
  border-radius: var(--m-radius);
  background: var(--m-canvas);
  display: grid;
  gap: 4px;
}

.m-deposit-stat.is-wide {
  grid-column: 1 / -1;
  background: var(--m-tint);
}

.m-deposit-stat span {
  font-size: 12px;
  color: var(--m-muted);
}

.m-deposit-stat strong {
  font-size: clamp(16px, 5vw, 22px);
  color: var(--m-ink);
  overflow-wrap: normal;
  word-break: normal;
}

.m-deposit-stat.is-wide strong {
  font-size: clamp(23px, 8vw, 32px);
}

.m-deposit-stat strong.is-ok {
  color: var(--m-success);
}

.m-deposit-contact {
  grid-column: 1 / -1;
}

.m-deposit-head {
  min-height: 52px;
  display: flex;
  align-items: center;
  padding: 0 12px;
  border-bottom: 1px solid var(--m-line);
}

.m-deposit-head h2 {
  margin: 0;
  font-size: 15px;
  color: var(--m-ink);
}

/* 明细列表（folio deposit-ledger）。 */
.m-ledger {
  margin: 0;
  padding: 0;
  list-style: none;
}

.m-ledger li {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 4px var(--m-space-2);
  align-items: center;
  padding: 10px 12px;
  border-top: 1px solid var(--m-line);
}

.m-ledger li:first-child {
  border-top: 0;
}

.m-ledger strong {
  font-size: 14px;
  color: var(--m-ink);
}

.m-ledger small {
  display: block;
  color: var(--m-muted);
  font-size: 12px;
}

.m-ledger b {
  font-size: 14px;
}

.m-ledger b.is-in {
  color: var(--m-success);
}

.m-ledger b.is-out {
  color: var(--m-accent);
}

.m-ledger p {
  grid-column: 1 / -1;
  margin: 0;
  color: var(--m-muted);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.m-ledger-pager {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--m-space-2);
  padding: 6px 10px;
  border-top: 1px solid var(--m-line);
}

.m-ledger-pager span {
  color: var(--m-muted);
  font-size: 12px;
}

.m-ledger-pager .m-btn {
  min-height: 40px;
  padding: 0 12px;
}

/* 折叠规则。 */
.m-disclosure {
  border: 1px solid var(--m-line);
  border-radius: var(--m-radius);
  background: var(--m-paper);
}

.m-disclosure summary {
  min-height: var(--m-target);
  padding: 12px;
  font-size: 14px;
  font-weight: 650;
  color: var(--m-ink);
  cursor: pointer;
  list-style: none;
}

.m-disclosure summary::-webkit-details-marker {
  display: none;
}

.m-disclosure__body {
  padding: 0 12px 12px;
}
</style>
