<script setup>
import { onMounted, reactive, ref } from 'vue'

import AppModal from '@/components/AppModal.vue'
import AppPager from '@/components/AppPager.vue'
import StatusTag from '@/components/StatusTag.vue'
import { adminWrite } from '@/composables/useAdminApi'
import { apiRequest } from '@/lib/api'

const TABS = [
  { key: 'withdrawals', label: '提现审核' },
  { key: 'ledger', label: '资金流水' },
]

const WITHDRAWAL_STATES = [
  { key: 'PENDING', label: '待审核' },
  { key: 'APPROVED', label: '审核通过' },
  { key: 'TRANSFERRING', label: '转账中' },
  { key: 'PAID', label: '已到账' },
  { key: 'REJECTED', label: '已打回' },
  { key: 'FAILED', label: '转账失败' },
]

const LEDGER_KINDS = [
  { key: 'RECHARGE', label: '充值入账' },
  { key: 'WITHDRAWAL', label: '提现申请' },
  { key: 'ORDER_SHIPPING', label: '订单发货' },
  { key: 'ORDER_SETTLEMENT', label: '订单回款' },
  { key: 'REFERRAL_COMMISSION', label: '推荐返佣' },
  { key: 'ADJUSTMENT', label: '余额调整' },
]

const state = reactive({
  tab: 'withdrawals',
  wdState: 'PENDING',
  ledgerKind: '',
  q: '',
  page: 1,
  items: [],
  meta: { total: 0, page_size: 20, has_next: false },
  loading: false,
  error: '',
})

const summary = ref(null)

const actionTarget = ref(null)
const actionKind = ref('')
const actionBusy = ref(false)
const actionError = ref('')
const actionForm = reactive({ fee: '0.00', reference: '', reason: '' })

const rechargeOpen = ref(false)
const rechargeBusy = ref(false)
const rechargeError = ref('')
const rechargeForm = reactive({ merchantQuery: '', merchantId: '', amount: '', note: '' })
const merchantOptions = ref([])

async function loadSummary() {
  try {
    const payload = await apiRequest('/finance/summary')
    summary.value = payload.summary
  } catch (error) {
    state.error = error.message
  }
}

async function load(resetPage = false) {
  if (resetPage) state.page = 1
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page: String(state.page) })
    let path = '/finance/withdrawals'
    if (state.tab === 'ledger') {
      path = '/finance/ledger'
      if (state.ledgerKind) params.set('kind', state.ledgerKind)
    } else if (state.wdState) {
      params.set('state', state.wdState)
    }
    if (state.q.trim()) params.set('q', state.q.trim())
    const payload = await apiRequest(`${path}?${params}`)
    state.items = payload.items
    state.meta = payload
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

function switchTab(key) {
  state.tab = key
  state.q = ''
  state.page = 1
  load()
}

function openAction(row, kind) {
  actionTarget.value = row
  actionKind.value = kind
  actionError.value = ''
  actionForm.fee = kind === 'approve' ? '0.00' : ''
  actionForm.reference = ''
  actionForm.reason = ''
}

const ACTION_TITLES = {
  approve: '审核通过',
  reject: '打回提现',
  start_transfer: '开始转账',
  mark_paid: '确认到账',
  mark_failed: '标记转账失败',
}

async function submitAction() {
  if (!actionTarget.value) return
  actionBusy.value = true
  actionError.value = ''
  try {
    await adminWrite(`/finance/withdrawals/${actionTarget.value.id}/actions`, {
      action: actionKind.value,
      fee: actionKind.value === 'approve' ? actionForm.fee : undefined,
      reference:
        actionKind.value === 'start_transfer' || actionKind.value === 'mark_paid'
          ? actionForm.reference || undefined
          : undefined,
      reason:
        actionKind.value === 'reject' || actionKind.value === 'mark_failed'
          ? actionForm.reason
          : undefined,
    })
    actionTarget.value = null
    await Promise.all([load(), loadSummary()])
  } catch (error) {
    actionError.value = error.message
  } finally {
    actionBusy.value = false
  }
}

async function searchMerchants() {
  if (!rechargeForm.merchantQuery.trim()) {
    merchantOptions.value = []
    return
  }
  try {
    const payload = await apiRequest(
      `/finance/merchants?q=${encodeURIComponent(rechargeForm.merchantQuery.trim())}`,
    )
    merchantOptions.value = payload.items
  } catch {
    merchantOptions.value = []
  }
}

function pickMerchant(option) {
  rechargeForm.merchantId = option.id
  rechargeForm.merchantQuery = option.name
  merchantOptions.value = []
}

async function submitRecharge() {
  rechargeBusy.value = true
  rechargeError.value = ''
  try {
    await adminWrite('/finance/recharges', {
      merchant_id: rechargeForm.merchantId,
      amount: rechargeForm.amount,
      note: rechargeForm.note,
    })
    rechargeOpen.value = false
    rechargeForm.merchantId = ''
    rechargeForm.merchantQuery = ''
    rechargeForm.amount = ''
    rechargeForm.note = ''
    await Promise.all([load(), loadSummary()])
  } catch (error) {
    rechargeError.value = error.message
  } finally {
    rechargeBusy.value = false
  }
}

function formatTime(value) {
  if (!value) return '—'
  return value.replace('T', ' ').slice(0, 16)
}

function exportLedger() {
  window.open('/api/v1/admin/finance/ledger/export', '_blank')
}

function goPage(page) {
  state.page = page
  load()
}

function resetFilters() {
  state.q = ''
  state.wdState = ''
  state.ledgerKind = ''
  load(true)
}

onMounted(() => {
  loadSummary()
  load()
})
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>资金审核</h1>
        <p>手动建立商家钱包充值，处理提现审核与出款。金额与流水同事务落库。</p>
      </div>
      <div class="page-intro__actions">
        <button type="button" class="btn" @click="exportLedger">导出资金流水</button>
        <button type="button" class="btn btn--primary" @click="rechargeOpen = true">
          新建钱包充值
        </button>
      </div>
    </div>

    <div class="stat-row">
      <div class="stat-card">
        <div class="stat-card__label">待审提现</div>
        <div class="stat-card__value">{{ summary?.pending_withdrawal_count ?? '—' }}</div>
        <div class="stat-card__hint">
          申请金额合计 ¥ {{ summary?.pending_withdrawal_amount ?? '0.00' }}
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-card__label">累计充值成功</div>
        <div class="stat-card__value">¥ {{ summary?.recharge_total ?? '0.00' }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-card__label">累计提现到账</div>
        <div class="stat-card__value">¥ {{ summary?.withdrawal_paid_total ?? '0.00' }}</div>
      </div>
    </div>

    <div class="panel">
      <div class="tabs">
        <button
          v-for="tab in TABS"
          :key="tab.key"
          type="button"
          :class="{ 'is-active': state.tab === tab.key }"
          @click="switchTab(tab.key)"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="toolbar">
        <template v-if="state.tab === 'withdrawals'">
          <select v-model="state.wdState" @change="load(true)">
            <option value="">全部状态</option>
            <option v-for="item in WITHDRAWAL_STATES" :key="item.key" :value="item.key">
              {{ item.label }}
            </option>
          </select>
          <input
            v-model="state.q"
            type="search"
            placeholder="商家 / 收款人 / 卡号"
            @keyup.enter="load(true)"
          />
        </template>
        <template v-else>
          <select v-model="state.ledgerKind" @change="load(true)">
            <option value="">全部类型</option>
            <option v-for="item in LEDGER_KINDS" :key="item.key" :value="item.key">
              {{ item.label }}
            </option>
          </select>
        </template>
        <button type="button" class="btn" @click="load(true)">查询</button>
        <button type="button" class="btn" @click="resetFilters">重置</button>
      </div>

      <p v-if="state.error" class="notice notice--error" style="margin: 16px 20px">
        {{ state.error }}
      </p>

      <div v-if="state.tab === 'withdrawals'" class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>申请号</th>
              <th>商家</th>
              <th>收款方式</th>
              <th>申请金额</th>
              <th>手续费 / 到账</th>
              <th>状态</th>
              <th>提交时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in state.items" :key="row.id">
              <td>{{ row.id.slice(0, 8) }}</td>
              <td>{{ row.merchant.name }}</td>
              <td>
                <span v-if="row.method === 'BANK'">
                  {{ row.bank.name }}
                  <span class="cell-sub">{{ row.bank.account }} · {{ row.bank.holder }}</span>
                </span>
                <span v-else>
                  {{ row.chain.coin }} · {{ row.chain.network }}
                  <span class="cell-sub">{{ row.chain.address }}</span>
                </span>
              </td>
              <td class="num">¥ {{ row.amount }}</td>
              <td class="num">
                ¥ {{ row.fee }}
                <span class="cell-sub">到账 ¥ {{ row.net_amount }}</span>
              </td>
              <td>
                <StatusTag :value="row.state" />
                <span v-if="row.reason" class="cell-sub">{{ row.reason }}</span>
              </td>
              <td>{{ formatTime(row.created_at) }}</td>
              <td>
                <div class="row-actions">
                  <button
                    v-if="row.state === 'PENDING'"
                    type="button"
                    class="btn btn--sm btn--primary"
                    @click="openAction(row, 'approve')"
                  >
                    审核
                  </button>
                  <button
                    v-if="row.state === 'PENDING'"
                    type="button"
                    class="btn btn--sm btn--danger"
                    @click="openAction(row, 'reject')"
                  >
                    打回
                  </button>
                  <button
                    v-if="row.state === 'APPROVED'"
                    type="button"
                    class="btn btn--sm btn--primary"
                    @click="openAction(row, 'start_transfer')"
                  >
                    开始转账
                  </button>
                  <button
                    v-if="row.state === 'TRANSFERRING'"
                    type="button"
                    class="btn btn--sm"
                    @click="openAction(row, 'mark_paid')"
                  >
                    确认到账
                  </button>
                  <button
                    v-if="row.state === 'TRANSFERRING'"
                    type="button"
                    class="btn btn--sm btn--danger"
                    @click="openAction(row, 'mark_failed')"
                  >
                    转账失败
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!state.loading && state.items.length === 0">
              <td colspan="8" class="data-table__empty">当前筛选条件下没有提现申请。</td>
            </tr>
            <tr v-if="state.loading">
              <td colspan="8" class="data-table__empty">加载中…</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-else class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>业务单号</th>
              <th>商家</th>
              <th>类型</th>
              <th>金额</th>
              <th>变动前</th>
              <th>变动后</th>
              <th>备注</th>
              <th>发生时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in state.items" :key="row.id">
              <td>{{ row.id.slice(0, 8) }}</td>
              <td>{{ row.merchant.name }}</td>
              <td><StatusTag :value="row.kind" /></td>
              <td
                class="num"
                :style="{ color: Number(row.amount) < 0 ? 'var(--red)' : 'var(--green)' }"
              >
                ¥ {{ row.amount }}
              </td>
              <td class="num">¥ {{ row.balance_before }}</td>
              <td class="num">¥ {{ row.balance_after }}</td>
              <td>{{ row.note || '—' }}</td>
              <td>{{ formatTime(row.occurred_at) }}</td>
            </tr>
            <tr v-if="!state.loading && state.items.length === 0">
              <td colspan="8" class="data-table__empty">暂无资金流水。</td>
            </tr>
            <tr v-if="state.loading">
              <td colspan="8" class="data-table__empty">加载中…</td>
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

    <AppModal
      v-if="actionTarget"
      :title="ACTION_TITLES[actionKind]"
      :busy="actionBusy"
      @cancel="actionTarget = null"
      @confirm="submitAction"
    >
      <p v-if="actionError" class="notice notice--error">{{ actionError }}</p>
      <p>
        {{ actionTarget.merchant.name }} · 申请金额 ¥ {{ actionTarget.amount }}
        <template v-if="actionTarget.method === 'BANK'"
          >（{{ actionTarget.bank.account }}）</template
        >
      </p>
      <div class="form-grid">
        <div v-if="actionKind === 'approve'" class="field">
          <label for="fee">手续费</label>
          <input id="fee" v-model="actionForm.fee" type="number" min="0" step="0.01" />
          <span class="field__hint">实际到账 = 申请金额 - 手续费，出款时不再重复扣可用余额。</span>
        </div>
        <div v-if="actionKind === 'start_transfer'" class="field">
          <label for="reference">出款凭证 / 交易编号</label>
          <input id="reference" v-model="actionForm.reference" type="text" maxlength="160" />
        </div>
        <div v-if="actionKind === 'mark_paid'" class="field">
          <label for="paid-reference">凭证（选填）</label>
          <input id="paid-reference" v-model="actionForm.reference" type="text" maxlength="160" />
        </div>
        <div v-if="actionKind === 'reject' || actionKind === 'mark_failed'" class="field">
          <label for="wd-reason">原因（选填）</label>
          <input id="wd-reason" v-model="actionForm.reason" type="text" maxlength="255" />
          <span class="field__hint">打回或失败会退回一次可用余额。</span>
        </div>
      </div>
    </AppModal>

    <AppModal
      v-if="rechargeOpen"
      title="新建钱包充值"
      confirm-text="确认充值"
      :busy="rechargeBusy"
      @cancel="rechargeOpen = false"
      @confirm="submitRecharge"
    >
      <p v-if="rechargeError" class="notice notice--error">{{ rechargeError }}</p>
      <div class="form-grid">
        <div class="field">
          <label for="recharge-merchant">商家</label>
          <input
            id="recharge-merchant"
            v-model="rechargeForm.merchantQuery"
            type="search"
            placeholder="输入店铺名称搜索"
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
              {{ option.name }}（余额 ¥ {{ option.wallet_balance }}）
            </button>
          </div>
        </div>
        <div class="field">
          <label for="recharge-amount">充值金额</label>
          <input
            id="recharge-amount"
            v-model="rechargeForm.amount"
            type="number"
            min="0.01"
            step="0.01"
          />
        </div>
        <div class="field">
          <label for="recharge-note">备注（选填）</label>
          <input id="recharge-note" v-model="rechargeForm.note" type="text" maxlength="255" />
        </div>
      </div>
    </AppModal>
  </section>
</template>
