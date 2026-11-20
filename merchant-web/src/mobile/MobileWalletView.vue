<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import SheetModal from '@/mobile/components/SheetModal.vue'
import { apiRequest, merchantWrite } from '@/lib/api'
import { showToast } from '@/shell'

// 手机壳钱包（folio route 5）：余额大字 + 充值/提现双按钮 → 钱包安全行
// （接既有 /merchant/wallet/password 流程）→ 资金类型 sheet 筛选（后端
// MerchantWalletEntry.Kind 枚举）→ 流水列表（方向箭头/类型/时间/金额/状态/
// chevron 点开明细）→ 分页。充值走平台客服会话（与桌面同口径）。

const router = useRouter()
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
  loading: true,
  error: '',
  notice: '',
  summary: null,
  kind: 'ALL',
  page: 1,
  entries: [],
  total: 0,
  hasNext: false,
})

const kindSheet = ref(false)
const entryDetail = ref(null)
const passwordSheet = ref(false)
const withdrawSheet = ref(false)

const passwordForm = reactive({ oldPassword: '', newPassword: '', confirmPassword: '', busy: false, error: '' })
const withdrawForm = reactive({
  method: 'BANK',
  amount: '',
  bank: { name: '', account: '', holder: '', branch: '', code: '' },
  chain: { coin: 'USDT', network: 'TRC-20', address: '' },
  walletPassword: '',
  busy: false,
  error: '',
})

const passwordConfigured = computed(() => Boolean(state.summary?.wallet_password_configured))
const balance = computed(() => state.summary?.balance || '0.00')

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

function chooseKind(key) {
  kindSheet.value = false
  if (key === state.kind) return
  state.kind = key
  state.page = 1
  loadEntries()
}

const kindLabel = computed(() => KIND_TABS.find((tab) => tab.key === state.kind)?.label || '全部类型')

function isOutgoing(row) {
  return Number(row.amount) < 0
}

function amountText(row) {
  return `${Number(row.amount) >= 0 ? '+' : '−'}${Math.abs(Number(row.amount)).toFixed(2)}`
}

function stateLabel(row) {
  return WITHDRAW_STATES[row.state] || row.state || '已完成'
}

function fmtDate(value) {
  if (!value) return '—'
  return value.slice(0, 16).replace('T', ' ')
}

function openPassword() {
  passwordForm.oldPassword = ''
  passwordForm.newPassword = ''
  passwordForm.confirmPassword = ''
  passwordForm.error = ''
  passwordSheet.value = true
}

async function submitPassword() {
  passwordForm.busy = true
  passwordForm.error = ''
  try {
    await merchantWrite('/merchant/wallet/password', {
      old_password: passwordForm.oldPassword || undefined,
      new_password: passwordForm.newPassword,
      confirm_password: passwordForm.confirmPassword,
    })
    passwordSheet.value = false
    state.notice = passwordConfigured.value ? '钱包密码已更新。' : '钱包密码已设置。'
    showToast(state.notice)
    await loadSummary()
  } catch (error) {
    passwordForm.error = error.message
  } finally {
    passwordForm.busy = false
  }
}

function openWithdraw() {
  if (!passwordConfigured.value) {
    state.notice = '请先设置 6 位数字钱包密码，再申请提现。'
    openPassword()
    return
  }
  withdrawForm.amount = ''
  withdrawForm.walletPassword = ''
  withdrawForm.error = ''
  withdrawSheet.value = true
}

async function submitWithdraw() {
  withdrawForm.busy = true
  withdrawForm.error = ''
  try {
    const payload = {
      method: withdrawForm.method,
      amount: withdrawForm.amount,
      wallet_password: withdrawForm.walletPassword,
    }
    if (withdrawForm.method === 'BANK') payload.bank = { ...withdrawForm.bank }
    else payload.chain = { ...withdrawForm.chain }
    await merchantWrite('/merchant/wallet/withdrawals', payload)
    withdrawSheet.value = false
    state.notice = '提现申请已提交，等待平台审核。'
    showToast(state.notice)
    await Promise.all([loadSummary(), loadEntries()])
  } catch (error) {
    withdrawForm.error = error.message
  } finally {
    withdrawForm.busy = false
  }
}

const pageCount = computed(() => Math.max(1, Math.ceil(state.total / PAGE_SIZE)))

onMounted(async () => {
  await Promise.all([loadSummary(), loadEntries()])
})
</script>

<template>
  <div class="m-page">
    <p v-if="state.error" class="m-error">{{ state.error }}</p>
    <p v-if="state.notice" class="m-notice">{{ state.notice }}</p>

    <!-- 余额卡：大字 + 双按钮（folio wallet-overview：底部红边）。 -->
    <section class="m-card m-card--pad m-wallet-hero">
      <span class="m-wallet-hero__label">可用余额（{{ state.summary?.currency || 'CNY' }}）</span>
      <strong class="m-wallet-hero__balance m-num">¥ {{ balance }}</strong>
      <small class="m-hint m-num">
        累计收入 ¥ {{ state.summary?.totals?.income || '0.00' }} ｜ 累计支出 ¥
        {{ state.summary?.totals?.expense || '0.00' }}
      </small>
      <div class="m-wallet-hero__actions">
        <button type="button" class="m-btn m-btn--tint" @click="router.push('/messages?open=support')">
          充值
        </button>
        <button type="button" class="m-btn m-btn--primary" @click="openWithdraw">提现</button>
      </div>
    </section>

    <!-- 钱包安全行。 -->
    <section class="m-card m-wallet-security">
      <h2>钱包安全</h2>
      <div>
        <span class="m-hint">{{ passwordConfigured ? '已设置钱包密码' : '未设置钱包密码' }}</span>
        <button type="button" class="m-wallet-security__action" @click="openPassword">
          {{ passwordConfigured ? '修改密码' : '设置密码' }}
        </button>
      </div>
    </section>

    <p v-if="!passwordConfigured" class="m-notice">
      你还没有设置钱包密码（6 位数字）。提现前必须先设置，用于二次验证。
    </p>

    <!-- 流水列表：标题行含资金类型筛选（folio wallet-filter chevron）。 -->
    <section class="m-card">
      <div class="m-wallet-head">
        <h2>资金明细</h2>
        <button
          type="button"
          class="m-wallet-filter"
          aria-haspopup="dialog"
          :aria-label="`资金类型，当前为${kindLabel}`"
          @click="kindSheet = true"
        >
          {{ kindLabel }}
        </button>
      </div>

      <p v-if="state.loading" class="m-loading">加载中…</p>
      <ul v-else-if="state.entries.length" class="m-records">
        <li v-for="row in state.entries" :key="row.id">
          <button type="button" class="m-record" @click="entryDetail = row">
            <span class="m-record__direction" :class="{ 'is-out': isOutgoing(row) }" aria-hidden="true">
              {{ isOutgoing(row) ? '↑' : '↓' }}
            </span>
            <span class="m-record__main">
              <strong>{{ KIND_TABS.find((tab) => tab.key === row.kind)?.label || row.kind }}</strong>
              <small>{{ fmtDate(row.occurred_at) }}</small>
            </span>
            <span class="m-record__value">
              <strong :class="{ 'is-out': isOutgoing(row) }" class="m-num">{{ amountText(row) }}</strong>
              <small>{{ stateLabel(row) }}</small>
            </span>
            <span class="m-record__chevron" aria-hidden="true">›</span>
          </button>
        </li>
      </ul>
      <p v-else class="m-empty">该类型下还没有资金流水。</p>

      <div v-if="state.total" class="m-wallet-pager">
        <button type="button" class="m-btn" :disabled="state.page <= 1" @click="state.page -= 1; loadEntries()">上一页</button>
        <span class="m-num">第 {{ state.page }} / {{ pageCount }} 页</span>
        <button type="button" class="m-btn" :disabled="!state.hasNext" @click="state.page += 1; loadEntries()">下一页</button>
      </div>
    </section>

    <!-- 资金类型 sheet。 -->
    <SheetModal :open="kindSheet" title="资金类型" @close="kindSheet = false">
      <div class="m-sheet-options">
        <button
          v-for="tab in KIND_TABS"
          :key="tab.key"
          type="button"
          :aria-pressed="state.kind === tab.key"
          :class="{ 'is-active': state.kind === tab.key }"
          @click="chooseKind(tab.key)"
        >
          {{ tab.label }}
        </button>
      </div>
    </SheetModal>

    <!-- 流水明细 sheet。 -->
    <SheetModal :open="Boolean(entryDetail)" title="资金明细" @close="entryDetail = null">
      <template v-if="entryDetail">
        <dl class="m-dl">
          <div><dt>业务类型</dt><dd>{{ KIND_TABS.find((tab) => tab.key === entryDetail.kind)?.label || entryDetail.kind }}</dd></div>
          <div><dt>发生时间</dt><dd class="m-num">{{ fmtDate(entryDetail.occurred_at) }}</dd></div>
          <div><dt>金额</dt><dd class="m-num">{{ amountText(entryDetail) }}</dd></div>
          <div><dt>变动后余额</dt><dd class="m-num">¥ {{ entryDetail.balance_after }}</dd></div>
          <div><dt>关联订单</dt><dd class="m-num">{{ entryDetail.order_id ? entryDetail.order_id.slice(0, 8) + '…' : '—' }}</dd></div>
          <div><dt>说明</dt><dd>{{ entryDetail.note || '—' }}</dd></div>
        </dl>
      </template>
    </SheetModal>

    <!-- 钱包密码 sheet（既有 /merchant/wallet/password 流程）。 -->
    <SheetModal :open="passwordSheet" :title="passwordConfigured ? '修改钱包密码' : '设置钱包密码'" @close="passwordSheet = false">
      <form class="m-sheet-form" @submit.prevent="submitPassword">
        <label v-if="passwordConfigured" class="m-field">
          <span class="m-field__label">原密码</span>
          <input v-model="passwordForm.oldPassword" class="m-input" type="password" inputmode="numeric" autocomplete="off" />
        </label>
        <label class="m-field">
          <span class="m-field__label">新密码（6 位数字）</span>
          <input v-model="passwordForm.newPassword" class="m-input" type="password" inputmode="numeric" maxlength="6" autocomplete="new-password" />
        </label>
        <label class="m-field">
          <span class="m-field__label">确认新密码</span>
          <input v-model="passwordForm.confirmPassword" class="m-input" type="password" inputmode="numeric" maxlength="6" autocomplete="new-password" />
        </label>
        <p v-if="passwordForm.error" class="m-error">{{ passwordForm.error }}</p>
        <button type="submit" class="m-btn m-btn--primary m-btn--block" :disabled="passwordForm.busy">
          {{ passwordForm.busy ? '保存中…' : '保存' }}
        </button>
      </form>
    </SheetModal>

    <!-- 提现 sheet（method + 金额 + 密码，字段与桌面 withdrawModal 一致）。 -->
    <SheetModal :open="withdrawSheet" title="申请提现" @close="withdrawSheet = false">
      <form class="m-sheet-form" @submit.prevent="submitWithdraw">
        <div class="m-seg">
          <button type="button" :class="{ 'is-active': withdrawForm.method === 'BANK' }" @click="withdrawForm.method = 'BANK'">银行卡</button>
          <button type="button" :class="{ 'is-active': withdrawForm.method === 'CHAIN' }" @click="withdrawForm.method = 'CHAIN'">链上转账</button>
        </div>
        <label class="m-field">
          <span class="m-field__label">提现金额（可用 ¥ {{ balance }}）</span>
          <input v-model="withdrawForm.amount" class="m-input m-num" type="number" min="0" step="0.01" />
        </label>
        <template v-if="withdrawForm.method === 'BANK'">
          <label class="m-field"><span class="m-field__label">开户行</span><input v-model="withdrawForm.bank.name" class="m-input" type="text" /></label>
          <label class="m-field"><span class="m-field__label">银行账号</span><input v-model="withdrawForm.bank.account" class="m-input m-num" type="text" /></label>
          <label class="m-field"><span class="m-field__label">开户人</span><input v-model="withdrawForm.bank.holder" class="m-input" type="text" /></label>
          <label class="m-field"><span class="m-field__label">支行</span><input v-model="withdrawForm.bank.branch" class="m-input" type="text" /></label>
          <label class="m-field"><span class="m-field__label">联行号</span><input v-model="withdrawForm.bank.code" class="m-input m-num" type="text" /></label>
        </template>
        <template v-else>
          <label class="m-field"><span class="m-field__label">币种</span><input v-model="withdrawForm.chain.coin" class="m-input" type="text" /></label>
          <label class="m-field"><span class="m-field__label">网络</span><input v-model="withdrawForm.chain.network" class="m-input" type="text" /></label>
          <label class="m-field"><span class="m-field__label">收款地址</span><input v-model="withdrawForm.chain.address" class="m-input" type="text" /></label>
        </template>
        <label class="m-field">
          <span class="m-field__label">钱包密码（二次验证）</span>
          <input v-model="withdrawForm.walletPassword" class="m-input" type="password" inputmode="numeric" maxlength="6" autocomplete="off" />
        </label>
        <p v-if="withdrawForm.error" class="m-error">{{ withdrawForm.error }}</p>
        <button type="submit" class="m-btn m-btn--primary m-btn--block" :disabled="withdrawForm.busy">
          {{ withdrawForm.busy ? '提交中…' : '提交申请' }}
        </button>
      </form>
    </SheetModal>
  </div>
</template>

<style scoped>
/* 余额卡（folio wallet-overview：border-block-end 2px accent）。 */
.m-wallet-hero {
  display: grid;
  gap: var(--m-space-2);
  border-block-end: 2px solid var(--m-accent);
}

.m-wallet-hero__label {
  font-size: 13px;
  color: var(--m-muted);
}

.m-wallet-hero__balance {
  font-size: clamp(27px, 9vw, 38px);
  font-weight: 700;
  letter-spacing: -0.035em;
  line-height: 1.15;
  color: var(--m-ink);
}

.m-wallet-hero__actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--m-space-2);
  margin-top: 4px;
}

/* 钱包安全行（folio wallet-security-row）。 */
.m-wallet-security {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 4px 10px;
  padding: 8px 14px;
}

.m-wallet-security h2 {
  margin: 0;
  font-size: 15px;
  color: var(--m-ink);
}

.m-wallet-security > div {
  display: flex;
  align-items: center;
  gap: 8px;
}

.m-wallet-security__action {
  min-height: 40px;
  padding: 0 6px;
  border: 0;
  background: transparent;
  color: var(--m-accent);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

/* 流水列表（folio wallet-records）。 */
.m-wallet-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--m-space-2);
  min-height: 52px;
  padding: 0 12px;
  border-bottom: 1px solid var(--m-line);
}

.m-wallet-head h2 {
  margin: 0;
  font-size: 15px;
  color: var(--m-ink);
}

.m-wallet-filter {
  min-height: 40px;
  padding: 0 6px;
  border: 0;
  background: transparent;
  color: var(--m-accent);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.m-wallet-filter::after {
  content: '⌄';
  margin-left: 6px;
}

.m-records {
  margin: 0;
  padding: 0;
  list-style: none;
}

.m-records li {
  border-top: 1px solid var(--m-line);
}

.m-records li:first-child {
  border-top: 0;
}

.m-record {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr) auto 10px;
  align-items: center;
  gap: var(--m-space-2);
  width: 100%;
  min-height: 64px;
  padding: 7px 10px;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.m-record:active {
  background: var(--m-canvas);
}

.m-record__direction {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #f2f7f4;
  color: var(--m-success);
  font-weight: 700;
}

.m-record__direction.is-out {
  background: var(--m-tint);
  color: var(--m-accent);
}

.m-record__main,
.m-record__value {
  display: grid;
  gap: 2px;
}

.m-record__main strong {
  font-size: 14px;
  color: var(--m-ink);
}

.m-record__value {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.m-record__value strong {
  font-size: 14px;
  color: var(--m-success);
}

.m-record__value strong.is-out {
  color: var(--m-accent);
}

.m-record small {
  color: var(--m-muted);
  font-size: 11px;
  font-weight: 400;
}

.m-record__chevron {
  color: var(--m-muted);
  font-size: 18px;
}

.m-wallet-pager {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--m-space-2);
  padding: 6px 10px;
  border-top: 1px solid var(--m-line);
}

.m-wallet-pager span {
  color: var(--m-muted);
  font-size: 12px;
}

.m-wallet-pager .m-btn {
  min-height: 40px;
  padding: 0 12px;
}

/* sheet 内容公共。 */
.m-sheet-options {
  display: grid;
  gap: var(--m-space-2);
}

.m-sheet-options button {
  min-height: var(--m-target);
  padding: 8px 12px;
  border: 1px solid var(--m-line);
  border-radius: 5px;
  background: var(--m-paper);
  color: var(--m-ink);
  font-size: 14px;
  text-align: left;
  cursor: pointer;
}

.m-sheet-options button.is-active {
  border-color: var(--m-accent);
  background: var(--m-tint);
  color: var(--m-accent);
  font-weight: 650;
}

.m-sheet-options button.is-active::after {
  content: '✓';
  margin-left: 6px;
}

.m-sheet-form {
  display: grid;
  gap: var(--m-space-3);
}

.m-dl {
  display: grid;
  gap: 10px;
  margin: 0;
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

.m-seg {
  display: flex;
  gap: 6px;
}

.m-seg button {
  flex: 1;
  min-height: 40px;
  border: 1px solid var(--m-line);
  border-radius: var(--m-radius);
  background: var(--m-paper);
  color: var(--m-muted);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.m-seg button.is-active {
  border-color: var(--m-accent);
  background: var(--m-tint);
  color: var(--m-accent);
}
</style>
