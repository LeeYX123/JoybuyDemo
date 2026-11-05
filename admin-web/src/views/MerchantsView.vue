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
})

const createOpen = ref(false)
const createForm = reactive({
  name: '',
  legal_name: '',
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
      await adminWrite(
        `/merchants/${id}`,
        {
          name: form.name,
          avatar: form.avatar,
          wallet_balance: form.wallet_balance,
          ban_after_days: Number(form.ban_after_days),
        },
        'PATCH',
      )
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

async function submitCreate() {
  createForm.busy = true
  try {
    await adminWrite('/merchants', {
      name: createForm.name,
      legal_name: createForm.legal_name,
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

onMounted(load)
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
              <th>待发货</th>
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
            <dt>未发货封店天数</dt>
            <dd>{{ detail.ban_after_days }} 天</dd>
          </div>
          <div>
            <dt>总关注</dt>
            <dd>{{ detail.followers }}（当日 +{{ detail.follow_delta }}）</dd>
          </div>
          <div>
            <dt>曝光量</dt>
            <dd>{{ detail.exposure }}</dd>
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

      <template v-if="detail" #footer>
        <button type="button" class="btn" @click="openModal('edit', detail)">编辑商家</button>
        <button type="button" class="btn" @click="openModal('credit', detail)">扣信誉分</button>
        <button
          v-if="detail.status === 'ACTIVE'"
          type="button"
          class="btn btn--danger"
          @click="openModal('suspend', detail)"
        >
          封店
        </button>
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
          <label for="merchant-ban">未发货封店天数</label>
          <input id="merchant-ban" v-model="form.ban_after_days" type="number" min="1" step="1" />
        </div>
      </div>

      <div v-else-if="modal.kind === 'credit'" class="form-grid">
        <div class="field">
          <label for="credit-points">扣分数</label>
          <input id="credit-points" v-model="form.points" type="number" min="0.01" step="0.01" />
          <span class="field__hint"
            >当前信誉分 {{ modal.merchant?.credit_score }}，扣分数不得超过当前分数。</span
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
          <label for="new-ban">未发货封店天数</label>
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
  </section>
</template>
