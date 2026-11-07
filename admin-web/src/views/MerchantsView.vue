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
  // 折扣按百分数展示（70 = 70%），留空表示未设置。
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
            <dt>商家折扣</dt>
            <dd>{{ detail.discount_rate ? `${detail.discount_rate}%` : '未设置' }}</dd>
          </div>
          <div>
            <dt>活动商品折扣</dt>
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
          <label for="merchant-discount">折扣设置（%）</label>
          <input
            id="merchant-discount"
            v-model="form.discount_rate"
            type="number"
            step="0.01"
            min="0"
          />
          <span class="field__hint">成本价 = 向上取整(零售价 × 折扣)。留空表示未设置。</span>
        </div>
        <div class="field">
          <label for="merchant-activity-discount">活动商品折扣（%）</label>
          <input
            id="merchant-activity-discount"
            v-model="form.activity_discount_rate"
            type="number"
            step="0.01"
            min="0"
          />
          <span class="field__hint"
            >仅对活动商品生效，优先于普通折扣；不做区间校验，设多少按多少算。</span
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
  </section>
</template>
