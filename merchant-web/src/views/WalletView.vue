<script setup>
import { computed, onMounted, reactive } from 'vue'

import AppDrawer from '@/components/AppDrawer.vue'
import AppModal from '@/components/AppModal.vue'
import AppPager from '@/components/AppPager.vue'
import { apiRequest, merchantWrite } from '@/lib/api'

const PAGE_SIZE = 10

const KIND_TABS = [
  { key: 'ALL', label: '全部类型' },
  { key: 'RECHARGE', label: '充值入账' },
  { key: 'WITHDRAWAL', label: '提现申请' },
  { key: 'ORDER_SHIPPING', label: '订单发货' },
  { key: 'ORDER_SETTLEMENT', label: '订单回款' },
  { key: 'REFERRAL_COMMISSION', label: '推荐返佣' },
  { key: 'ADJUSTMENT', label: '余额调整' },
]

const WITHDRAW_STATES = {
  PENDING: '待审核',
  REJECTED: '已打回',
  APPROVED: '审核通过',
  TRANSFERRING: '转账中',
  FAILED: '转账失败',
  PAID: '已到账',
}

const state = reactive({
  tab: 'entries',
  kind: 'ALL',
  page: 1,
  loading: true,
  error: '',
  notice: '',
  summary: null,
  entries: [],
  total: 0,
  hasNext: false,
  withdrawals: [],
  withdrawalTotal: 0,
  withdrawalPage: 1,
  withdrawalHasNext: false,
})

const detail = reactive({ value: null, open: false })

const passwordModal = reactive({
  open: false,
  oldPassword: '',
  newPassword: '',
  confirmPassword: '',
  busy: false,
  error: '',
})

const withdrawModal = reactive({
  open: false,
  method: 'BANK',
  amount: '',
  bank: { name: '', account: '', holder: '', branch: '', code: '' },
  chain: { coin: 'USDT', network: 'TRC-20', address: '' },
  walletPassword: '',
  busy: false,
  error: '',
})

const passwordConfigured = computed(() => Boolean(state.summary?.wallet_password_configured))
const balanceNumber = computed(() => Number(state.summary?.balance || 0))
const amountTooLarge = computed(
  () => Number(withdrawModal.amount || 0) > balanceNumber.value && Number(withdrawModal.amount) > 0,
)

async function loadSummary() {
  try {
    state.summary = await apiRequest('/merchant/wallet')
  } catch (error) {
    state.error = error.message
  }
}

async function loadEntries() {
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page: String(state.page), page_size: String(PAGE_SIZE) })
    if (state.kind !== 'ALL') params.set('kind', state.kind)
    const payload = await apiRequest(`/merchant/wallet/entries?${params}`)
    state.entries = payload.items || []
    state.total = payload.total || 0
    state.hasNext = Boolean(payload.has_next)
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

async function loadWithdrawals() {
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({
      page: String(state.withdrawalPage),
      page_size: String(PAGE_SIZE),
    })
    const payload = await apiRequest(`/merchant/wallet/withdrawals?${params}`)
    state.withdrawals = payload.items || []
    state.withdrawalTotal = payload.total || 0
    state.withdrawalHasNext = Boolean(payload.has_next)
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

function selectTab(key) {
  state.tab = key
  if (key === 'entries') loadEntries()
  else loadWithdrawals()
}

function selectKind(key) {
  state.kind = key
  state.page = 1
  loadEntries()
}

function goPage(page) {
  state.page = page
  loadEntries()
}

function goWithdrawalPage(page) {
  state.withdrawalPage = page
  loadWithdrawals()
}

function openEntry(row) {
  detail.value = row
  detail.open = true
}

function closeDetail() {
  detail.open = false
  detail.value = null
}

function exportCsv() {
  const params = new URLSearchParams()
  if (state.kind !== 'ALL') params.set('kind', state.kind)
  window.open(`/api/v1/merchant/wallet/entries/export?${params}`, '_blank')
}

function openPassword() {
  passwordModal.oldPassword = ''
  passwordModal.newPassword = ''
  passwordModal.confirmPassword = ''
  passwordModal.error = ''
  passwordModal.open = true
}

function closePassword() {
  if (passwordModal.busy) return
  passwordModal.open = false
}

async function submitPassword() {
  passwordModal.busy = true
  passwordModal.error = ''
  try {
    await merchantWrite('/merchant/wallet/password', {
      old_password: passwordModal.oldPassword || undefined,
      new_password: passwordModal.newPassword,
      confirm_password: passwordModal.confirmPassword,
    })
    passwordModal.open = false
    state.notice = passwordConfigured.value ? '钱包密码已更新。' : '钱包密码已设置。'
    await loadSummary()
  } catch (error) {
    passwordModal.error = error.message
  } finally {
    passwordModal.busy = false
  }
}

function openWithdraw() {
  if (!passwordConfigured.value) {
    state.notice = '请先设置 6 位数字钱包密码，再申请提现。'
    openPassword()
    return
  }
  withdrawModal.amount = ''
  withdrawModal.walletPassword = ''
  withdrawModal.error = ''
  withdrawModal.open = true
}

function closeWithdraw() {
  if (withdrawModal.busy) return
  withdrawModal.open = false
}

async function submitWithdraw() {
  withdrawModal.busy = true
  withdrawModal.error = ''
  try {
    const payload = {
      method: withdrawModal.method,
      amount: withdrawModal.amount,
      wallet_password: withdrawModal.walletPassword,
    }
    if (withdrawModal.method === 'BANK') payload.bank = { ...withdrawModal.bank }
    else payload.chain = { ...withdrawModal.chain }
    await merchantWrite('/merchant/wallet/withdrawals', payload)
    withdrawModal.open = false
    state.notice = '提现申请已提交，等待平台审核。'
    await Promise.all([loadSummary(), loadEntries(), loadWithdrawals().catch(() => {})])
  } catch (error) {
    withdrawModal.error = error.message
  } finally {
    withdrawModal.busy = false
  }
}

function fmtDate(value) {
  if (!value) return '—'
  return value.slice(0, 16).replace('T', ' ')
}

function amountClass(amount) {
  return Number(amount) >= 0 ? 'up' : 'down'
}

function goMessages() {
  window.location.href = '/messages'
}

onMounted(async () => {
  await Promise.all([loadSummary(), loadEntries(), loadWithdrawals().catch(() => {})])
})
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>钱包管理</h1>
        <p>充值需联系平台客服；提现占用可用余额，审核通过后由平台出款。</p>
      </div>
    </div>

    <p v-if="state.error" class="notice notice--error">{{ state.error }}</p>
    <p v-if="state.notice" class="notice notice--ok">{{ state.notice }}</p>

    <div class="wallet-hero">
      <div class="wallet-hero__balance">
        <span>可用余额（{{ state.summary?.currency || 'CNY' }}）</span>
        <strong class="num">¥ {{ state.summary?.balance || '0.00' }}</strong>
        <small>
          累计收入 ¥ {{ state.summary?.totals?.income || '0.00' }} ｜ 累计支出 ¥
          {{ state.summary?.totals?.expense || '0.00' }}
        </small>
      </div>
      <div class="wallet-hero__actions">
        <button type="button" class="btn" @click="goMessages">联系客服充值</button>
        <button type="button" class="btn btn--primary" @click="openWithdraw">申请提现</button>
        <button type="button" class="btn" @click="openPassword">
          {{ passwordConfigured ? '修改钱包密码' : '设置钱包密码' }}
        </button>
      </div>
    </div>

    <p v-if="!passwordConfigured" class="notice notice--info">
      你还没有设置钱包密码（6 位数字）。提现前必须先设置，用于二次验证。
    </p>

    <div class="tabs">
      <button
        type="button"
        :class="{ 'is-active': state.tab === 'entries' }"
        @click="selectTab('entries')"
      >
        统一资金明细
      </button>
      <button
        type="button"
        :class="{ 'is-active': state.tab === 'withdrawals' }"
        @click="selectTab('withdrawals')"
      >
        提现申请
      </button>
    </div>

    <template v-if="state.tab === 'entries'">
      <div class="toolbar">
        <div class="chip-row">
          <button
            v-for="tab in KIND_TABS"
            :key="tab.key"
            type="button"
            class="chip"
            :class="{ 'is-active': state.kind === tab.key }"
            @click="selectKind(tab.key)"
          >
            {{ tab.label }}
          </button>
        </div>
        <button type="button" class="btn btn--sm" @click="exportCsv">导出明细</button>
      </div>

      <div class="card">
        <div class="card__body">
          <p v-if="state.loading" class="inline-loading">加载中…</p>
          <table v-else-if="state.entries.length" class="data-table">
            <thead>
              <tr>
                <th>发生时间</th>
                <th>业务类型</th>
                <th>金额</th>
                <th>变动后余额</th>
                <th>关联订单</th>
                <th>说明</th>
                <th class="actions-col">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in state.entries" :key="row.id">
                <td>{{ fmtDate(row.occurred_at) }}</td>
                <td>{{ KIND_TABS.find((tab) => tab.key === row.kind)?.label || row.kind }}</td>
                <td class="num" :class="amountClass(row.amount)">
                  {{ Number(row.amount) >= 0 ? '+' : '' }}{{ row.amount }}
                </td>
                <td class="num">¥ {{ row.balance_after }}</td>
                <td class="mono">{{ row.order_id ? row.order_id.slice(0, 8) : '—' }}</td>
                <td class="cell-sub">{{ row.note || '—' }}</td>
                <td class="actions-col">
                  <button type="button" class="btn btn--sm" @click="openEntry(row)">查看</button>
                </td>
              </tr>
            </tbody>
          </table>
          <p v-else class="empty-state">该类型下还没有资金流水。</p>
        </div>
      </div>

      <AppPager
        :page="state.page"
        :page-size="PAGE_SIZE"
        :total="state.total"
        :has-next="state.hasNext"
        @change="goPage"
      />
    </template>

    <template v-else>
      <div class="card">
        <div class="card__body">
          <p v-if="state.loading" class="inline-loading">加载中…</p>
          <table v-else-if="state.withdrawals.length" class="data-table">
            <thead>
              <tr>
                <th>申请时间</th>
                <th>方式</th>
                <th>申请金额</th>
                <th>手续费</th>
                <th>实际到账</th>
                <th>状态</th>
                <th class="actions-col">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in state.withdrawals" :key="row.id">
                <td>{{ fmtDate(row.created_at) }}</td>
                <td>{{ row.method === 'BANK' ? '银行卡' : '链上转账' }}</td>
                <td class="num">¥ {{ row.amount }}</td>
                <td class="num">¥ {{ row.fee }}</td>
                <td class="num">¥ {{ row.net_amount }}</td>
                <td>
                  <span
                    class="tag"
                    :class="{
                      'tag--warn': ['PENDING', 'APPROVED', 'TRANSFERRING'].includes(row.state),
                      'tag--ok': row.state === 'PAID',
                      'tag--danger': ['REJECTED', 'FAILED'].includes(row.state),
                    }"
                  >
                    {{ WITHDRAW_STATES[row.state] || row.state }}
                  </span>
                </td>
                <td class="actions-col">
                  <button type="button" class="btn btn--sm" @click="openEntry(row)">
                    处理详情
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <p v-else class="empty-state">还没有提现申请。</p>
        </div>
      </div>
      <AppPager
        :page="state.withdrawalPage"
        :page-size="PAGE_SIZE"
        :total="state.withdrawalTotal"
        :has-next="state.withdrawalHasNext"
        @change="goWithdrawalPage"
      />
    </template>

    <AppDrawer :open="detail.open" title="明细详情" @close="closeDetail">
      <template v-if="detail.value">
        <template v-if="detail.value.method">
          <dl class="detail-grid">
            <div>
              <dt>申请单号</dt>
              <dd class="mono">{{ detail.value.id }}</dd>
            </div>
            <div>
              <dt>状态</dt>
              <dd>{{ WITHDRAW_STATES[detail.value.state] || detail.value.state }}</dd>
            </div>
            <div>
              <dt>申请金额</dt>
              <dd class="num">¥ {{ detail.value.amount }}</dd>
            </div>
            <div>
              <dt>实际到账</dt>
              <dd class="num">¥ {{ detail.value.net_amount }}</dd>
            </div>
          </dl>
          <h3 class="section-title">收款信息</h3>
          <dl v-if="detail.value.bank" class="detail-grid">
            <div>
              <dt>银行名称</dt>
              <dd>{{ detail.value.bank.name }}</dd>
            </div>
            <div>
              <dt>银行卡号</dt>
              <dd class="mono">{{ detail.value.bank.account }}</dd>
            </div>
            <div>
              <dt>姓名</dt>
              <dd>{{ detail.value.bank.holder }}</dd>
            </div>
            <div>
              <dt>支行</dt>
              <dd>{{ detail.value.bank.branch }}（{{ detail.value.bank.code }}）</dd>
            </div>
          </dl>
          <dl v-else-if="detail.value.chain" class="detail-grid">
            <div>
              <dt>币种</dt>
              <dd>{{ detail.value.chain.coin }}</dd>
            </div>
            <div>
              <dt>链类型</dt>
              <dd>{{ detail.value.chain.network }}</dd>
            </div>
            <div>
              <dt>钱包地址</dt>
              <dd class="mono">{{ detail.value.chain.address }}</dd>
            </div>
          </dl>
          <p v-if="detail.value.reason" class="notice notice--error">
            {{ detail.value.reason }}
          </p>
          <h3 class="section-title">处理过程</h3>
          <ol class="timeline">
            <li v-for="event in detail.value.history" :key="event.action + event.at">
              <span class="timeline__title">{{ event.action }}</span>
              <span class="timeline__time">
                {{ fmtDate(event.at) }} {{ event.note ? `· ${event.note}` : '' }}
              </span>
            </li>
          </ol>
        </template>

        <template v-else>
          <dl class="detail-grid">
            <div>
              <dt>业务单号</dt>
              <dd class="mono">{{ detail.value.id }}</dd>
            </div>
            <div>
              <dt>业务类型</dt>
              <dd>{{ KIND_TABS.find((tab) => tab.key === detail.value.kind)?.label }}</dd>
            </div>
            <div>
              <dt>金额</dt>
              <dd class="num" :class="amountClass(detail.value.amount)">
                {{ detail.value.amount }}
              </dd>
            </div>
            <div>
              <dt>变动前 / 后余额</dt>
              <dd class="num">
                ¥ {{ detail.value.balance_before }} → ¥ {{ detail.value.balance_after }}
              </dd>
            </div>
            <div>
              <dt>发生时间</dt>
              <dd>{{ fmtDate(detail.value.occurred_at) }}</dd>
            </div>
            <div>
              <dt>关联订单</dt>
              <dd class="mono">{{ detail.value.order_id || '—' }}</dd>
            </div>
          </dl>

          <template v-if="detail.value.order_snapshot">
            <h3 class="section-title">订单资金明细</h3>
            <dl class="detail-grid">
              <div>
                <dt>商品</dt>
                <dd>{{ detail.value.order_snapshot.title }}</dd>
              </div>
              <div>
                <dt>数量</dt>
                <dd class="num">{{ detail.value.order_snapshot.quantity }}</dd>
              </div>
              <div>
                <dt>成交单价</dt>
                <dd class="num">¥ {{ detail.value.order_snapshot.unit_price }}</dd>
              </div>
              <div>
                <dt>单位成本</dt>
                <dd class="num">¥ {{ detail.value.order_snapshot.unit_cost ?? '—' }}</dd>
              </div>
              <div>
                <dt>成本合计</dt>
                <dd class="num">¥ {{ detail.value.order_snapshot.cost_total }}</dd>
              </div>
              <div>
                <dt>{{ detail.value.order_snapshot.profit_label }}</dt>
                <dd class="num up">¥ {{ detail.value.order_snapshot.profit }}</dd>
              </div>
            </dl>
          </template>
        </template>
      </template>
    </AppDrawer>

    <AppModal
      :open="passwordModal.open"
      :title="passwordConfigured ? '修改钱包密码' : '设置钱包密码'"
      confirm-text="保存"
      :busy="passwordModal.busy"
      @cancel="closePassword"
      @confirm="submitPassword"
    >
      <p class="modal-lead">钱包密码为 6 位数字，仅用于提现二次验证，与登录密码不同。</p>
      <label v-if="passwordConfigured" class="field">
        <span class="field__label">当前密码</span>
        <input
          v-model="passwordModal.oldPassword"
          type="password"
          maxlength="6"
          inputmode="numeric"
        />
      </label>
      <label class="field">
        <span class="field__label">新密码</span>
        <input
          v-model="passwordModal.newPassword"
          type="password"
          maxlength="6"
          inputmode="numeric"
        />
      </label>
      <label class="field">
        <span class="field__label">确认新密码</span>
        <input
          v-model="passwordModal.confirmPassword"
          type="password"
          maxlength="6"
          inputmode="numeric"
        />
      </label>
      <p v-if="passwordModal.error" class="notice notice--error">{{ passwordModal.error }}</p>
    </AppModal>

    <AppModal
      :open="withdrawModal.open"
      title="申请提现"
      confirm-text="提交提现申请"
      :busy="withdrawModal.busy"
      @cancel="closeWithdraw"
      @confirm="submitWithdraw"
    >
      <div class="tabs">
        <button
          type="button"
          :class="{ 'is-active': withdrawModal.method === 'BANK' }"
          @click="withdrawModal.method = 'BANK'"
        >
          银行卡
        </button>
        <button
          type="button"
          :class="{ 'is-active': withdrawModal.method === 'CHAIN' }"
          @click="withdrawModal.method = 'CHAIN'"
        >
          数字货币链上转账
        </button>
      </div>

      <template v-if="withdrawModal.method === 'BANK'">
        <div class="form-grid">
          <label class="field">
            <span class="field__label">银行名称</span>
            <input v-model="withdrawModal.bank.name" type="text" />
          </label>
          <label class="field">
            <span class="field__label">银行卡号</span>
            <input v-model="withdrawModal.bank.account" type="text" />
          </label>
          <label class="field">
            <span class="field__label">姓名</span>
            <input v-model="withdrawModal.bank.holder" type="text" />
          </label>
          <label class="field">
            <span class="field__label">银行支行名称</span>
            <input v-model="withdrawModal.bank.branch" type="text" />
          </label>
          <label class="field">
            <span class="field__label">支行编号</span>
            <input v-model="withdrawModal.bank.code" type="text" />
          </label>
        </div>
      </template>

      <template v-else>
        <div class="form-grid">
          <label class="field">
            <span class="field__label">币种</span>
            <select v-model="withdrawModal.chain.coin">
              <option value="USDT">USDT</option>
              <option value="ETH">ETH</option>
            </select>
          </label>
          <label class="field">
            <span class="field__label">链类型</span>
            <select v-model="withdrawModal.chain.network">
              <option value="ERC-20">ERC-20</option>
              <option value="TRC-20">TRC-20</option>
            </select>
          </label>
        </div>
        <label class="field">
          <span class="field__label">钱包地址</span>
          <input v-model="withdrawModal.chain.address" type="text" />
        </label>
        <p v-if="withdrawModal.chain.coin === 'ETH'" class="hint-text">ETH 只支持 ERC-20。</p>
      </template>

      <label class="field">
        <span class="field__label">提现金额</span>
        <input v-model="withdrawModal.amount" type="number" step="0.01" min="0" />
        <span class="field__hint">可用余额 ¥ {{ state.summary?.balance || '0.00' }}</span>
      </label>
      <p v-if="amountTooLarge" class="notice notice--error">提现金额超过可用余额。</p>

      <label class="field">
        <span class="field__label">钱包密码</span>
        <input
          v-model="withdrawModal.walletPassword"
          type="password"
          maxlength="6"
          inputmode="numeric"
        />
      </label>
      <p v-if="withdrawModal.error" class="notice notice--error">{{ withdrawModal.error }}</p>
    </AppModal>
  </section>
</template>

<style scoped>
.wallet-hero {
  display: flex;
  align-items: center;
  gap: 24px;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 20px 24px;
  margin-bottom: 16px;
}

.wallet-hero__balance span {
  display: block;
  font-size: 12px;
  color: var(--muted);
}

.wallet-hero__balance strong {
  display: block;
  font-size: 32px;
  color: var(--ink);
  margin: 4px 0;
}

.wallet-hero__balance small {
  color: var(--muted);
  font-size: 12px;
}

.wallet-hero__actions {
  margin-left: auto;
  display: flex;
  gap: 10px;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.chip {
  border: 1px solid var(--line);
  background: #fff;
  border-radius: 16px;
  padding: 5px 14px;
  font-size: 13px;
  color: var(--muted);
  cursor: pointer;
}

.chip.is-active {
  border-color: var(--red);
  color: var(--red);
  background: var(--red-soft);
  font-weight: 600;
}
</style>
