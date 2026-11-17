<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import AppDrawer from '@/components/AppDrawer.vue'
import AppModal from '@/components/AppModal.vue'
import AppPager from '@/components/AppPager.vue'
import StatusTag from '@/components/StatusTag.vue'
import { adminWrite } from '@/composables/useAdminApi'
import { apiRequest } from '@/lib/api'

const TABS = [
  { key: '', label: '全部商家' },
  { key: 'PENDING_REVIEW', label: '待审核' },
  { key: 'PENDING_DEPOSIT', label: '待缴保证金' },
  { key: 'ACTIVE', label: '接单中' },
  { key: 'SUSPENDED', label: '已封店' },
  { key: 'REJECTED', label: '已驳回' },
]

const state = reactive({
  tab: '',
  q: '',
  page: 1,
  items: [],
  meta: { total: 0, page_size: 20, has_next: false },
  loading: false,
  error: '',
})

const detail = ref(null)
const detailLoading = ref(false)

const modal = reactive({ kind: '', merchant: null, busy: false, error: '' })
const form = reactive({
  approved: true,
  require_deposit: false,
  deposit_required: '500.00',
  ban_after_days: 4,
  name: '',
  avatar: '',
  wallet_balance: '',
  points: '',
  reason: '',
  discount_rate: '',
  activity_discount_rate: '',
})

const createOpen = ref(false)
const createForm = reactive({
  name: '',
  legal_name: '',
  referrer_code: '',
  ban_after_days: 4,
  admission_approved: false,
  busy: false,
})

const statusLabel = computed(() =>
  Object.fromEntries(TABS.filter((tab) => tab.key).map((tab) => [tab.key, tab.label])),
)

async function load(resetPage = false) {
  if (resetPage) state.page = 1
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page: String(state.page) })
    if (state.tab) params.set('status', state.tab)
    if (state.q.trim()) params.set('q', state.q.trim())
    const payload = await apiRequest(`/merchants?${params}`)
    state.items = payload.items
    state.meta = payload
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

async function openDetail(merchant) {
  detail.value = null
  detailLoading.value = true
  try {
    const payload = await apiRequest(`/merchants/${merchant.id}`)
    detail.value = payload.merchant
  } catch (error) {
    state.error = error.message
  } finally {
    detailLoading.value = false
  }
}

function openModal(kind, merchant) {
  modal.kind = kind
  modal.merchant = merchant
  modal.busy = false
  modal.error = ''
  form.approved = true
  form.require_deposit = Boolean(merchant?.deposit_enabled)
  form.deposit_required = merchant?.deposit_required || '500.00'
  form.ban_after_days = merchant?.ban_after_days || 4
  form.name = merchant?.name || ''
  form.avatar = merchant?.avatar || ''
  form.wallet_balance = merchant?.wallet_balance || '0.00'
  form.points = ''
  form.reason = ''
  // 折扣按百分数展示，数值是「减免百分比」（20 = 成本价减免 20%，即按 80% 计），留空表示未设置。
  form.discount_rate = merchant?.discount_rate ?? ''
  form.activity_discount_rate = merchant?.activity_discount_rate ?? ''
}

const MODAL_TITLES = {
  review: '入驻审核',
  edit: '编辑商家',
  credit: '扣除信誉分',
  suspend: '确认封店',
  unsuspend: '确认解封',
}

async function submitModal() {
  if (!modal.merchant) return
  modal.busy = true
  modal.error = ''
  const id = modal.merchant.id
  try {
    if (modal.kind === 'review') {
      await adminWrite(`/merchants/${id}/actions`, {
        action: 'review',
        approved: form.approved,
        require_deposit: form.require_deposit,
        deposit_required: form.require_deposit ? form.deposit_required : undefined,
        ban_after_days: Number(form.ban_after_days),
      })
    } else if (modal.kind === 'edit') {
      // 余额只在真的改动时才提交：后端对"余额未变化"返回 NO_CHANGE 400，
      // 总是带上余额会让普通的资料/折扣编辑一直失败。
      const payload = {
        name: form.name,
        avatar: form.avatar,
        ban_after_days: Number(form.ban_after_days),
        discount_rate: form.discount_rate === '' ? '' : form.discount_rate,
        activity_discount_rate:
          form.activity_discount_rate === '' ? '' : form.activity_discount_rate,
      }
      if (form.wallet_balance !== (modal.merchant?.wallet_balance || '0.00')) {
        payload.wallet_balance = form.wallet_balance
      }
      // 迭代02：把自动封店天数改小时先预检——存在超时未处理订单要二次确认，
      // 确认后带 confirm_suspend=true 保存并立即封店。
      const currentDays = modal.merchant?.ban_after_days
      const newDays = Number(form.ban_after_days)
      const shrinking = currentDays == null || newDays < currentDays
      if (shrinking) {
        if (banConfirm.pending.value) {
          // 用户已在确认弹框点了确认：带 confirm_suspend 直接保存。
          payload.confirm_suspend = true
          banConfirm.pending.value = false
        } else {
          const check = await apiRequest(`/merchants/${id}/ban-check?days=${newDays}`)
          if (check.ban_check?.overdue) {
            banConfirm.days.value = check.ban_check.overdue_days ?? newDays
            banConfirm.payload.value = payload
            banConfirm.pending.value = true
            modal.busy = false
            return
          }
        }
      }
      await adminWrite(`/merchants/${id}`, payload, 'PATCH')
    } else if (modal.kind === 'credit') {
      await adminWrite(`/merchants/${id}/actions`, {
        action: 'deduct_credit',
        points: form.points,
      })
    } else if (modal.kind === 'suspend' || modal.kind === 'unsuspend') {
      await adminWrite(`/merchants/${id}/actions`, {
        action: modal.kind,
        reason: form.reason,
      })
    }
    modal.kind = ''
    await load()
    if (detail.value?.id === id) await openDetail({ id })
  } catch (error) {
    modal.error = error.message
  } finally {
    modal.busy = false
  }
}

// 自动封店天数缩小 → 二次确认弹框状态（pending 保持 true 直到提交成功）。
const banConfirm = {
  pending: ref(false),
  days: ref(0),
  payload: ref(null),
}

function confirmBanShrink() {
  // 不清 pending：submitModal 检测到 pending=true 会带 confirm_suspend 提交。
  submitModal()
}

async function submitCreate() {
  createForm.busy = true
  try {
    await adminWrite('/merchants', {
      name: createForm.name,
      legal_name: createForm.legal_name,
      referrer_code: createForm.referrer_code || undefined,
      ban_after_days: Number(createForm.ban_after_days),
      admission_approved: createForm.admission_approved,
    })
    createOpen.value = false
    createForm.name = ''
    createForm.legal_name = ''
    await load(true)
  } catch (error) {
    state.error = error.message
  } finally {
    createForm.busy = false
  }
}

function exportCsv() {
  const params = new URLSearchParams()
  if (state.tab) params.set('status', state.tab)
  if (state.q.trim()) params.set('q', state.q.trim())
  window.open(`/api/v1/admin/merchants/export?${params}`, '_blank')
}

function shortId(value) {
  return value ? value.slice(0, 8) : '—'
}

function formatTime(value) {
  if (!value) return '—'
  return value.replace('T', ' ').slice(0, 16)
}

function goPage(page) {
  state.page = page
  load()
}

function selectTab(key) {
  state.tab = key
  load(true)
}

function resetFilters() {
  state.q = ''
  state.tab = ''
  load(true)
}

function closeDetail() {
  detail.value = null
  detailLoading.value = false
}

// ---------- 入驻申请（购物端「申请店铺」提交的开店申请） ----------
const APP_TABS = [
  { key: '', label: '全部申请' },
  { key: 'PENDING', label: '待审核' },
  { key: 'APPROVED', label: '已通过' },
  { key: 'REJECTED', label: '已驳回' },
]

const appStatusLabels = {
  PENDING: '待审核',
  APPROVED: '已通过',
  REJECTED: '已驳回',
}

// 2026-11-17 申请表单 7 项：证件类型三选一的展示文案。
const appDocTypeLabels = {
  ID_CARD: '身份证',
  PASSPORT: '护照',
  DRIVER_LICENSE: '驾照',
}

// 审核弹窗里点击 logo / 证件照后的放大预览（空串 = 关闭）。
const appPreview = ref('')

const applications = reactive({
  tab: 'PENDING',
  page: 1,
  items: [],
  meta: { total: 0, page_size: 20, has_next: false },
  pendingCount: 0,
  notice: '',
  loading: false,
  error: '',
})

async function loadApplications(resetPage = false) {
  if (resetPage) applications.page = 1
  applications.loading = true
  applications.error = ''
  try {
    const params = new URLSearchParams({ page: String(applications.page) })
    if (applications.tab) params.set('status', applications.tab)
    const payload = await apiRequest(`/merchant-applications?${params}`)
    applications.items = payload.items
    applications.meta = payload
    applications.pendingCount = payload.pending_count || 0
  } catch (error) {
    applications.error = error.message
  } finally {
    applications.loading = false
  }
}

const appModal = reactive({ open: false, application: null, busy: false, error: '' })
const appForm = reactive({
  approved: true,
  require_deposit: true,
  deposit_amount: '500.00',
  ban_after_days: 4,
  reason: '',
})

function openAppModal(application) {
  appModal.open = true
  appModal.application = application
  appModal.busy = false
  appModal.error = ''
  appPreview.value = ''
  appForm.approved = true
  appForm.require_deposit = true
  appForm.deposit_amount = '500.00'
  appForm.ban_after_days = 4
  appForm.reason = ''
}

async function submitAppModal() {
  if (!appModal.application) return
  if (!appForm.approved && !appForm.reason.trim()) {
    appModal.error = '请填写驳回原因。'
    return
  }
  appModal.busy = true
  appModal.error = ''
  try {
    const payload = appForm.approved
      ? {
          application_id: appModal.application.id,
          action: 'approve',
          require_deposit: appForm.require_deposit,
          deposit_amount: appForm.require_deposit ? appForm.deposit_amount : undefined,
          ban_after_days: Number(appForm.ban_after_days),
        }
      : {
          application_id: appModal.application.id,
          action: 'reject',
          reason: appForm.reason.trim(),
        }
    const response = await adminWrite('/merchant-applications/actions', payload)
    appModal.open = false
    if (appForm.approved && response.staff_account_created === false) {
      applications.notice = '该邮箱已存在员工账号，已直接关联（密码保持不变）。'
    } else {
      applications.notice = ''
    }
    await loadApplications()
  } catch (error) {
    appModal.error = error.message
  } finally {
    appModal.busy = false
  }
}

function selectAppTab(key) {
  applications.tab = key
  loadApplications(true)
}

function goAppPage(page) {
  applications.page = page
  loadApplications()
}

onMounted(() => {
  load()
  loadApplications()
})
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>商家管理</h1>
        <p>审核开店、查看店铺资金与履约情况，管理封店与信誉。</p>
      </div>
      <div class="page-intro__actions">
        <button type="button" class="btn" @click="exportCsv">导出商家</button>
        <button type="button" class="btn btn--primary" @click="createOpen = true">补录商家</button>
      </div>
    </div>

    <div class="panel">
      <div class="tabs">
        <button
          v-for="tab in TABS"
          :key="tab.key"
          type="button"
          :class="{ 'is-active': state.tab === tab.key }"
          @click="selectTab(tab.key)"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="toolbar">
        <input
          v-model="state.q"
          type="search"
          placeholder="店铺名称或店铺 ID"
          @keyup.enter="load(true)"
        />
        <button type="button" class="btn" @click="load(true)">查询</button>
        <button type="button" class="btn" @click="resetFilters">重置</button>
      </div>

      <div v-if="state.error" class="panel__body">
        <p class="notice notice--error">{{ state.error }}</p>
      </div>

      <div class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>店铺</th>
              <th>待发货（金额=成本合计）</th>
              <th>钱包余额</th>
              <th>保证金</th>
              <th>信誉分</th>
              <th>状态</th>
              <th>上次在线</th>
              <th>入驻日期</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in state.items" :key="row.id">
              <td>
                <span class="cell-strong">{{ row.name }}</span>
                <span class="cell-sub">{{ shortId(row.id) }}</span>
              </td>
              <td class="num">
                {{ row.pending_order_count }} 笔
                <span class="cell-sub">¥ {{ row.pending_order_amount }}</span>
              </td>
              <td class="num">¥ {{ row.wallet_balance }}</td>
              <td class="num">
                ¥ {{ row.deposit_balance }}
                <span v-if="row.deposit_enabled" class="cell-sub">
                  应缴 {{ row.deposit_required }}
                </span>
                <span v-else class="cell-sub">无需缴纳</span>
              </td>
              <td class="num">{{ row.credit_score }}</td>
              <td><StatusTag :value="row.status" :labels="statusLabel" /></td>
              <td>{{ formatTime(row.last_online_at) }}</td>
              <td>{{ formatTime(row.joined) }}</td>
              <td>
                <div class="row-actions">
                  <button type="button" class="btn btn--sm" @click="openDetail(row)">详情</button>
                  <button
                    v-if="row.status === 'PENDING_REVIEW'"
                    type="button"
                    class="btn btn--sm btn--primary"
                    @click="openModal('review', row)"
                  >
                    审核
                  </button>
                  <button type="button" class="btn btn--sm" @click="openModal('edit', row)">
                    编辑
                  </button>
                  <button type="button" class="btn btn--sm" @click="openModal('credit', row)">
                    扣信誉分
                  </button>
                  <button
                    v-if="row.status === 'ACTIVE'"
                    type="button"
                    class="btn btn--sm btn--danger"
                    @click="openModal('suspend', row)"
                  >
                    封店
                  </button>
                  <button
                    v-if="row.status === 'SUSPENDED'"
                    type="button"
                    class="btn btn--sm"
                    @click="openModal('unsuspend', row)"
                  >
                    解封
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!state.loading && state.items.length === 0">
              <td colspan="9" class="data-table__empty">当前筛选条件下没有商家。</td>
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

    <!-- 入驻申请（购物端「申请店铺」提交的开店申请） -->
    <h2 class="section-title app-section-title">
      入驻申请
      <span class="app-pending-count">待审核 {{ applications.pendingCount }} 条</span>
    </h2>
    <div class="panel">
      <div class="tabs">
        <button
          v-for="tab in APP_TABS"
          :key="tab.key"
          type="button"
          :class="{ 'is-active': applications.tab === tab.key }"
          @click="selectAppTab(tab.key)"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="panel__body">
        <p v-if="applications.notice" class="notice notice--warn">{{ applications.notice }}</p>
        <p v-if="applications.error" class="notice notice--error">{{ applications.error }}</p>
      </div>

      <div class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>买家账号</th>
              <th>用户名字</th>
              <th>店铺名称</th>
              <th>手机号码</th>
              <th>邀请码</th>
              <th>状态</th>
              <th>申请时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in applications.items" :key="row.id">
              <td>{{ row.buyer_email || '—' }}</td>
              <td>{{ row.user_name || '—' }}</td>
              <td>
                <span class="cell-strong">{{ row.shop_name }}</span>
              </td>
              <td>{{ row.phone || '—' }}</td>
              <td>{{ row.referrer_code || '—' }}</td>
              <td><StatusTag :value="row.status" :labels="appStatusLabels" /></td>
              <td>{{ formatTime(row.submitted_at) }}</td>
              <td>
                <button
                  v-if="row.status === 'PENDING'"
                  type="button"
                  class="btn btn--sm btn--primary"
                  @click="openAppModal(row)"
                >
                  审核
                </button>
                <span v-else>—</span>
              </td>
            </tr>
            <tr v-if="!applications.loading && applications.items.length === 0">
              <td colspan="8" class="data-table__empty">当前筛选条件下没有入驻申请。</td>
            </tr>
            <tr v-if="applications.loading">
              <td colspan="8" class="data-table__empty">加载中…</td>
            </tr>
          </tbody>
        </table>
      </div>

      <AppPager
        :page="applications.meta.page || 1"
        :page-size="applications.meta.page_size || 20"
        :total="applications.meta.total || 0"
        :has-next="applications.meta.has_next"
        @change="goAppPage"
      />
    </div>

    <AppDrawer
      v-if="detail || detailLoading"
      :title="detail ? `商家详情 · ${detail.name}` : '商家详情'"
      wide
      @close="closeDetail"
    >
      <p v-if="detailLoading" class="inline-loading">加载中…</p>
      <template v-if="detail">
        <dl class="detail-grid">
          <div>
            <dt>店铺 ID</dt>
            <dd>{{ detail.id }}</dd>
          </div>
          <div>
            <dt>店铺状态</dt>
            <dd><StatusTag :value="detail.status" :labels="statusLabel" /></dd>
          </div>
          <div>
            <dt>钱包余额</dt>
            <dd>¥ {{ detail.wallet_balance }}</dd>
          </div>
          <div>
            <dt>保证金余额</dt>
            <dd>¥ {{ detail.deposit_balance }}</dd>
          </div>
          <div>
            <dt>应缴保证金</dt>
            <dd>{{ detail.deposit_required ?? '—' }}</dd>
          </div>
          <div>
            <dt>信誉分</dt>
            <dd>{{ detail.credit_score }}</dd>
          </div>
          <div>
            <dt>订单未处理自动封店天数（天）</dt>
            <dd>{{ detail.ban_after_days ?? '不自动封店' }}</dd>
          </div>
          <div>
            <dt>商家折扣（成本价减免）</dt>
            <dd>{{ detail.discount_rate ? `${detail.discount_rate}%` : '未设置' }}</dd>
          </div>
          <div>
            <dt>活动商品折扣（成本价减免）</dt>
            <dd>
              {{ detail.activity_discount_rate ? `${detail.activity_discount_rate}%` : '未设置' }}
            </dd>
          </div>
          <div>
            <dt>总关注</dt>
            <dd>{{ detail.followers }}（当日 +{{ detail.follow_delta }}）</dd>
          </div>
          <div>
            <dt>总曝光度</dt>
            <dd>{{ detail.exposure }}（今日 +{{ detail.exposure_delta }}）</dd>
          </div>
          <div>
            <dt>推荐码</dt>
            <dd>{{ detail.referral_code || '—' }}</dd>
          </div>
          <div>
            <dt>入驻时间</dt>
            <dd>{{ formatTime(detail.joined) }}</dd>
          </div>
          <div>
            <dt>上次在线</dt>
            <dd>{{ formatTime(detail.last_online_at) }}</dd>
          </div>
          <div>
            <dt>待发货订单</dt>
            <dd>{{ detail.pending_order_count }} 笔 / ¥ {{ detail.pending_order_amount }}</dd>
          </div>
          <div v-if="detail.suspend_reason">
            <dt>封店原因</dt>
            <dd>{{ detail.suspend_reason }}</dd>
          </div>
        </dl>

        <h3 class="section-title">最近扣分记录</h3>
        <table v-if="detail.credit_records?.length" class="data-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>操作人</th>
              <th>扣前</th>
              <th>扣后</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="record in detail.credit_records" :key="record.id">
              <td>{{ formatTime(record.occurred_at) }}</td>
              <td>{{ record.operator }}</td>
              <td class="num">{{ record.before }}</td>
              <td class="num">{{ record.after }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty-state">暂无扣分记录。</p>
      </template>
    </AppDrawer>

    <AppModal
      v-if="modal.kind"
      :title="MODAL_TITLES[modal.kind]"
      :busy="modal.busy"
      @cancel="modal.kind = ''"
      @confirm="submitModal"
    >
      <p v-if="modal.error" class="notice notice--error">{{ modal.error }}</p>

      <div v-if="modal.kind === 'review'" class="form-grid">
        <div class="field">
          <span class="field__label">审核结果</span>
          <label class="checkline">
            <input v-model="form.approved" type="radio" :value="true" /> 通过
          </label>
          <label class="checkline">
            <input v-model="form.approved" type="radio" :value="false" /> 驳回
          </label>
        </div>
        <div class="field">
          <label class="checkline">
            <input v-model="form.require_deposit" type="checkbox" :disabled="!form.approved" />
            需要保证金
          </label>
          <span class="field__hint">审核通过后该选择永久锁定，不可再改。</span>
        </div>
        <div v-if="form.approved && form.require_deposit" class="field">
          <label for="deposit-required">应缴保证金</label>
          <input
            id="deposit-required"
            v-model="form.deposit_required"
            type="number"
            min="0.01"
            step="0.01"
          />
        </div>
        <div class="field">
          <label for="ban-days">未发货封店天数</label>
          <input id="ban-days" v-model="form.ban_after_days" type="number" min="1" step="1" />
        </div>
      </div>

      <div v-else-if="modal.kind === 'edit'" class="form-grid">
        <div class="field">
          <label for="merchant-name">店铺名称</label>
          <input id="merchant-name" v-model="form.name" type="text" maxlength="160" />
        </div>
        <div class="field">
          <label for="merchant-avatar">店铺头像 URL</label>
          <input id="merchant-avatar" v-model="form.avatar" type="text" />
        </div>
        <div class="field">
          <label for="merchant-wallet">钱包余额</label>
          <input
            id="merchant-wallet"
            v-model="form.wallet_balance"
            type="number"
            step="0.01"
            min="0"
          />
          <span class="field__hint">按调整后的余额填写，系统自动记差额流水。</span>
        </div>
        <div class="field">
          <label for="merchant-ban">订单未处理自动封店天数（天）</label>
          <input id="merchant-ban" v-model="form.ban_after_days" type="number" min="1" step="1" />
          <span class="field__hint"
            >存在待处理订单且下单时间超过该天数时自动封店；这是唯一的自动封店规则。</span
          >
        </div>
        <div class="field">
          <label for="merchant-discount">折扣设置（%，成本价减免）</label>
          <input
            id="merchant-discount"
            v-model="form.discount_rate"
            type="number"
            step="0.01"
            min="0"
          />
          <span class="field__hint"
            >平台给商家的进货折扣：成本价 = 零售价 × (1 − 折扣%)，顾客价（零售价）不变。<br />
            例：零售 3599、折扣 20% → 3599 × 80% = 2879.20；留空 = 减免 0% → 成本价 = 零售价。</span
          >
        </div>
        <div class="field">
          <label for="merchant-activity-discount">活动商品折扣（%，成本价减免）</label>
          <input
            id="merchant-activity-discount"
            v-model="form.activity_discount_rate"
            type="number"
            step="0.01"
            min="0"
          />
          <span class="field__hint"
            >仅对活动商品生效，优先于普通折扣，同样以零售价为基数减免；不做区间校验，设多少按多少算。</span
          >
        </div>
      </div>

      <div v-else-if="modal.kind === 'credit'" class="form-grid">
        <div class="field">
          <label for="credit-points">扣分数</label>
          <input id="credit-points" v-model="form.points" type="number" min="0.01" step="0.01" />
          <span class="field__hint"
            >当前信誉分 {{ modal.merchant?.credit_score }}；100 分制，最低扣到
            0，扣完不做自动处理。</span
          >
        </div>
      </div>

      <div v-else class="form-grid">
        <p>
          将对「{{ modal.merchant?.name }}」执行{{ modal.kind === 'suspend' ? '封店' : '解封' }}。
          解封会重置未处理订单的履约计时。
        </p>
        <div v-if="modal.kind === 'suspend'" class="field">
          <label for="suspend-reason">封店原因（选填）</label>
          <input id="suspend-reason" v-model="form.reason" type="text" maxlength="255" />
        </div>
      </div>
    </AppModal>

    <AppModal
      v-if="createOpen"
      title="补录商家"
      :busy="createForm.busy"
      @cancel="createOpen = false"
      @confirm="submitCreate"
    >
      <div class="form-grid">
        <div class="field">
          <label for="new-name">店铺名称</label>
          <input id="new-name" v-model="createForm.name" type="text" maxlength="160" />
        </div>
        <div class="field">
          <label for="new-legal">主体名称（选填）</label>
          <input id="new-legal" v-model="createForm.legal_name" type="text" maxlength="200" />
        </div>
        <div class="field">
          <label for="new-referral">邀请码（选填，填了即为邀请入驻）</label>
          <input id="new-referral" v-model="createForm.referrer_code" type="text" maxlength="32" />
          <span class="field__hint">填邀请商家的推荐码，审核通过后建立返佣绑定。</span>
        </div>
        <div class="field">
          <label for="new-ban">订单未处理自动封店天数（天）</label>
          <input id="new-ban" v-model="createForm.ban_after_days" type="number" min="1" step="1" />
        </div>
        <div class="field">
          <label class="checkline">
            <input v-model="createForm.admission_approved" type="checkbox" />
            直接标记为审核通过（接单中）
          </label>
        </div>
      </div>
    </AppModal>

    <AppModal
      v-if="appModal.open"
      title="入驻申请审核"
      :busy="appModal.busy"
      @cancel="appModal.open = false"
      @confirm="submitAppModal"
    >
      <div class="form-grid">
        <!-- 2026-11-17 申请 7 项字段全量展示：字段表格 + logo 缩略图 + 证件照（点击放大） -->
        <table class="app-detail-table">
          <tbody>
            <tr>
              <th>买家账号</th>
              <td>{{ appModal.application?.buyer_email || '—' }}</td>
            </tr>
            <tr>
              <th>用户名字</th>
              <td>{{ appModal.application?.user_name || '—' }}</td>
            </tr>
            <tr>
              <th>店铺名称</th>
              <td>{{ appModal.application?.shop_name || '—' }}</td>
            </tr>
            <tr>
              <th>手机号码</th>
              <td>{{ appModal.application?.phone || '—' }}</td>
            </tr>
            <tr>
              <th>邀请码</th>
              <td>{{ appModal.application?.referrer_code || '—（选填，未填）' }}</td>
            </tr>
            <tr>
              <th>证件类型</th>
              <td>
                {{ appDocTypeLabels[appModal.application?.id_document_type] || '—' }}
              </td>
            </tr>
            <tr>
              <th>居住地址</th>
              <td>{{ appModal.application?.residential_address || '—' }}</td>
            </tr>
            <tr>
              <th>店铺logo</th>
              <td>
                <img
                  v-if="appModal.application?.logo_image_url"
                  :src="appModal.application.logo_image_url"
                  alt="店铺logo"
                  class="app-image-thumb"
                  @click="appPreview = appModal.application.logo_image_url"
                />
                <span v-else>—</span>
              </td>
            </tr>
            <tr>
              <th>证件照片</th>
              <td>
                <img
                  v-if="appModal.application?.id_document_image_url"
                  :src="appModal.application.id_document_image_url"
                  alt="证件照片（点击放大）"
                  class="app-image-thumb app-image-thumb--doc"
                  @click="appPreview = appModal.application.id_document_image_url"
                />
                <span v-else>—</span>
                <span class="app-image-hint">（敏感信息，仅供入驻审核使用）</span>
              </td>
            </tr>
            <tr>
              <th>申请时间</th>
              <td>{{ formatTime(appModal.application?.submitted_at) }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="appModal.error" class="notice notice--error">{{ appModal.error }}</p>

        <div class="field">
          <span class="field__label">审核结果</span>
          <label class="checkline">
            <input v-model="appForm.approved" type="radio" :value="true" /> 通过
          </label>
          <label class="checkline">
            <input v-model="appForm.approved" type="radio" :value="false" /> 驳回
          </label>
        </div>
        <div v-if="appForm.approved" class="field">
          <label class="checkline">
            <input v-model="appForm.require_deposit" type="checkbox" /> 需要保证金
          </label>
          <span class="field__hint">审核通过后该选择永久锁定，不可再改。</span>
        </div>
        <div v-if="appForm.approved && appForm.require_deposit" class="field">
          <label for="app-deposit-required">应缴保证金</label>
          <input
            id="app-deposit-required"
            v-model="appForm.deposit_amount"
            type="number"
            min="0.01"
            step="0.01"
          />
        </div>
        <div v-if="appForm.approved" class="field">
          <label for="app-ban-days">未发货封店天数</label>
          <input
            id="app-ban-days"
            v-model="appForm.ban_after_days"
            type="number"
            min="1"
            step="1"
          />
        </div>
        <div v-if="!appForm.approved" class="field">
          <label for="app-reject-reason">驳回原因（必填）</label>
          <input id="app-reject-reason" v-model="appForm.reason" type="text" maxlength="255" />
        </div>
        <p v-if="appForm.approved" class="field__hint">
          通过后将自动开店：买家邮箱即为商家端账号（密码同买家账号）；需保证金时店铺进入「待缴保证金」。
        </p>
      </div>
    </AppModal>

    <AppModal
      v-if="banConfirm.pending.value"
      title="确认修改自动封店天数"
      confirm-text="确认修改并封店"
      :busy="modal.busy"
      @cancel="banConfirm.pending.value = false"
      @confirm="confirmBanShrink"
    >
      <p class="notice notice--warn">
        该店铺有超过 {{ banConfirm.days.value }} 天未处理的订单，是否要修改？
      </p>
      <p>确认修改后店铺将立即置为【已封店】；超时订单发完后由客服在管理端手动解封。</p>
    </AppModal>

    <!-- 入驻审核：点击 logo / 证件照后的放大预览（点击遮罩关闭） -->
    <div v-if="appPreview" class="app-image-lightbox" @click="appPreview = ''">
      <img :src="appPreview" alt="申请图片放大预览" />
    </div>
  </section>
</template>

<style scoped>
.app-section-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.app-pending-count {
  padding: 2px 8px;
  border-radius: 10px;
  background: #fff4e5;
  color: #a05a00;
  font-size: 12px;
  font-weight: 600;
}

/* 入驻申请审核：字段表格 + 图片 */
.app-detail-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.app-detail-table th {
  width: 88px;
  padding: 6px 10px 6px 0;
  text-align: left;
  vertical-align: top;
  color: #5a6673;
  font-weight: 600;
  white-space: nowrap;
}

.app-detail-table td {
  padding: 6px 0;
  vertical-align: top;
  word-break: break-word;
}

.app-image-thumb {
  display: block;
  width: 56px;
  height: 56px;
  object-fit: cover;
  border: 1px solid #d7dee6;
  border-radius: 6px;
  cursor: zoom-in;
}

.app-image-thumb--doc {
  width: 84px;
}

.app-image-hint {
  display: block;
  margin-top: 4px;
  color: #98a2ad;
  font-size: 12px;
}

.app-image-lightbox {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px;
  background: rgba(15, 23, 32, 0.72);
  cursor: zoom-out;
}

.app-image-lightbox img {
  max-width: 100%;
  max-height: 100%;
  border-radius: 8px;
  background: #fff;
}
</style>
