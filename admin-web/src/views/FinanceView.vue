<script setup>
import { onMounted, reactive, ref } from 'vue'

import AppDrawer from '@/components/AppDrawer.vue'
import AppModal from '@/components/AppModal.vue'
import AppPager from '@/components/AppPager.vue'
import AppPicker from '@/components/AppPicker.vue'
import StatusTag from '@/components/StatusTag.vue'
import { adminWrite } from '@/composables/useAdminApi'
import { refreshWithdrawalBadge } from '@/composables/useWithdrawalBadge'
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
const rechargeForm = reactive({ merchantId: '', amount: '', note: '' })

// 2026-11-28 可搜索下拉框：充值选商家改为 AppPicker 远程搜索（名称/编号均可查）。
function fetchRechargeMerchants(q) {
  return apiRequest(`/finance/merchants?q=${encodeURIComponent(q)}`)
}

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

// 两步流转（2026-11-28）：审核通过 → 转账中；转账中 → 转账成功 / 转账失败（必填原因）。
const ACTION_TITLES = {
  approve: '审核通过（进入转账中）',
  reject: '打回提现',
  start_transfer: '开始转账',
  mark_paid: '确认转账成功',
  mark_failed: '确认转账失败',
}

// 详情抽屉（列表/详情都能看到失败或打回原因）。
const detail = ref(null)

function openDetail(row) {
  detail.value = row
}

async function refreshAfterAction() {
  // 列表 + 顶部统计 + 侧边导航徽标一起刷新（审核后徽标应立刻 -1）。
  await Promise.all([load(), loadSummary(), refreshWithdrawalBadge()])
}

async function submitAction() {
  if (!actionTarget.value) return
  const needsReason = ['reject', 'mark_failed'].includes(actionKind.value)
  if (needsReason && !actionForm.reason.trim()) {
    actionError.value =
      actionKind.value === 'mark_failed' ? '请填写转账失败原因。' : '请填写打回原因。'
    return
  }
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
      reason: needsReason ? actionForm.reason.trim() : undefined,
    })
    actionTarget.value = null
    await refreshAfterAction()
  } catch (error) {
    actionError.value = error.message
  } finally {
    actionBusy.value = false
  }
}

async function submitRecharge() {
  rechargeBusy.value = true
  rechargeError.value = ''
  if (!rechargeForm.merchantId) {
    rechargeError.value = '请先选择一个商家。'
    rechargeBusy.value = false
    return
  }
  try {
    await adminWrite('/finance/recharges', {
      merchant_id: rechargeForm.merchantId,
      amount: rechargeForm.amount,
      note: rechargeForm.note,
    })
    rechargeOpen.value = false
    rechargeForm.merchantId = ''
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
  // 进入本页即对齐一次导航徽标（商家新申请时点进来就能看到最新数字）。
  refreshWithdrawalBadge()
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
              <td>{{ row.id }}</td>
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
                <!-- 两步流转：待审核 →【审核】【打回】；转账中 →【转账成功】【转账失败】；
                     已完成态只读，仅保留【详情】。 -->
                <div class="row-actions">
                  <button type="button" class="btn btn--sm" @click="openDetail(row)">详情</button>
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
                    class="btn btn--sm btn--primary"
                    @click="openAction(row, 'mark_paid')"
                  >
                    转账成功
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
              <td>{{ row.id }}</td>
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
          <label for="fee">手续费（审核通过后展示）</label>
          <input id="fee" v-model="actionForm.fee" type="number" min="0" step="0.01" />
          <span class="field__hint"
            >通过后状态直接变为【转账中】；商家端不展示手续费，实际到账 = 申请金额 - 手续费。</span
          >
        </div>
        <div v-if="actionKind === 'mark_paid'" class="field">
          <label for="paid-reference">转账凭证 / 流水号（选填）</label>
          <input id="paid-reference" v-model="actionForm.reference" type="text" maxlength="160" />
          <span class="field__hint">确认后状态变为【转账成功】，商家端同步显示该状态。</span>
        </div>
        <div v-if="actionKind === 'reject' || actionKind === 'mark_failed'" class="field">
          <label for="wd-reason">
            {{ actionKind === 'reject' ? '打回原因' : '转账失败原因' }}（必填）
          </label>
          <input
            id="wd-reason"
            v-model="actionForm.reason"
            type="text"
            maxlength="255"
            required
            placeholder="例如：收款账户状态异常，请核对后重新提交"
          />
          <span class="field__hint">
            {{ actionKind === 'reject' ? '打回' : '转账失败' }}会立即把 ¥
            {{ actionTarget.amount }} 退回商家钱包余额，原因会同时记入审计日志与商家端资金明细。
          </span>
        </div>
      </div>
    </AppModal>

    <!-- 提现申请详情（列表与详情都能看到失败/打回原因） -->
    <AppDrawer v-if="detail" title="提现申请详情" wide @close="detail = null">
      <dl class="detail-grid">
        <div>
          <dt>申请号</dt>
          <dd class="mono">{{ detail.id }}</dd>
        </div>
        <div>
          <dt>商家</dt>
          <dd>
            {{ detail.merchant.name }}
            <span class="cell-sub mono">{{ detail.merchant.id }}</span>
          </dd>
        </div>
        <div>
          <dt>状态</dt>
          <dd><StatusTag :value="detail.state" /></dd>
        </div>
        <div>
          <dt>申请金额</dt>
          <dd>¥ {{ detail.amount }}</dd>
        </div>
        <div>
          <dt>手续费 / 到账</dt>
          <dd>¥ {{ detail.fee }} / ¥ {{ detail.net_amount }}</dd>
        </div>
        <div>
          <dt>收款方式</dt>
          <dd>
            <template v-if="detail.method === 'BANK'">
              {{ detail.bank.name }} · {{ detail.bank.account }} · {{ detail.bank.holder }}
            </template>
            <template v-else>
              {{ detail.chain.coin }} · {{ detail.chain.network }} · {{ detail.chain.address }}
            </template>
          </dd>
        </div>
        <div v-if="detail.reference">
          <dt>转账凭证 / 流水号</dt>
          <dd class="mono">{{ detail.reference }}</dd>
        </div>
        <div>
          <dt>申请时间</dt>
          <dd>{{ formatTime(detail.created_at) }}</dd>
        </div>
      </dl>
      <template v-if="detail.reason">
        <h3 class="section-title">
          {{ detail.state === 'FAILED' ? '转账失败原因' : '打回原因' }}
        </h3>
        <p class="notice notice--error" style="white-space: pre-wrap">{{ detail.reason }}</p>
      </template>
    </AppDrawer>

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
          <label for="recharge-merchant">商家（输入名称或编号搜索）</label>
          <AppPicker
            v-model="rechargeForm.merchantId"
            input-id="recharge-merchant"
            :fetcher="fetchRechargeMerchants"
            placeholder="输入店铺名称或编号"
            :option-meta="(option) => `余额 ¥ ${option.wallet_balance}`"
          />
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
