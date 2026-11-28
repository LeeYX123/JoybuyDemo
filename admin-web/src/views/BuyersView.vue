<script setup>
import { onMounted, reactive, ref } from 'vue'

import AppDrawer from '@/components/AppDrawer.vue'
import AppModal from '@/components/AppModal.vue'
import AppPager from '@/components/AppPager.vue'
import AppPicker from '@/components/AppPicker.vue'
import { adminWrite } from '@/composables/useAdminApi'
import { apiRequest } from '@/lib/api'

const state = reactive({
  q: '',
  whitelisted: '',
  status: '',
  page: 1,
  items: [],
  meta: { total: 0, page_size: 20, has_next: false },
  loading: false,
  error: '',
  notice: '',
})

// 2026-11-28 可搜索下拉框：筛选改为选用户（用户名/邮箱/手机号/编号均可搜），
// 选中即按该用户编号（JYU）过滤。
function fetchBuyerFilterOptions(q) {
  return apiRequest(`/buyers/accounts?q=${encodeURIComponent(q)}`)
}

const detail = ref(null)
const detailLoading = ref(false)

// 2026-11-27 用户端管理【编辑】：两列弹窗 + 底部独立【重设密码】区域。
const editorOpen = ref(false)
const editorBusy = ref(false)
const editorError = ref('')
const editorId = ref('')
const editorOriginal = ref(null)
const editor = reactive({
  display_name: '',
  email: '',
  phone_e164: '',
  payment_enabled: true,
  balance: '0.00',
  purchase_whitelisted: true,
  status: 'ACTIVE',
  note: '',
})

const reset = reactive({ password: '', confirm: '' })
const resetBusy = ref(false)
const resetError = ref('')
const resetNotice = ref('')
const generatedPassword = ref('')

async function load(resetPage = false) {
  if (resetPage) state.page = 1
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page: String(state.page) })
    if (state.whitelisted) params.set('whitelisted', state.whitelisted)
    if (state.status) params.set('status', state.status)
    if (state.q.trim()) params.set('q', state.q.trim())
    const payload = await apiRequest(`/buyers/accounts?${params}`)
    state.items = payload.items
    state.meta = payload
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

async function openDetail(row) {
  detail.value = null
  detailLoading.value = true
  try {
    const payload = await apiRequest(`/buyers/accounts/${row.id}`)
    detail.value = payload.buyer
  } catch (error) {
    state.error = error.message
  } finally {
    detailLoading.value = false
  }
}

async function toggleStatus(row) {
  try {
    await adminWrite(`/buyers/accounts/${row.id}/profile`, {
      action: row.enabled ? 'disable' : 'enable',
    })
    await load()
  } catch (error) {
    state.error = error.message
  }
}

// 迭代02：白名单就地加入/移出（原独立白名单模块已删除）。
async function toggleWhitelist(row) {
  try {
    await adminWrite(`/buyers/accounts/${row.id}/whitelist`, {
      action: row.whitelisted ? 'remove' : 'add',
    })
    await load()
  } catch (error) {
    state.error = error.message
  }
}

function openEditor(source) {
  editorId.value = source.id
  editorOriginal.value = {
    display_name: source.display_name || '',
    email: source.email || '',
    phone_e164: source.phone || '',
    payment_enabled: Boolean(source.payment_enabled),
    balance: String(source.balance ?? '0.00'),
    purchase_whitelisted: Boolean(source.whitelisted),
    status: source.enabled ? 'ACTIVE' : 'DISABLED',
  }
  Object.assign(editor, { ...editorOriginal.value, note: '' })
  Object.assign(reset, { password: '', confirm: '' })
  editorError.value = ''
  resetError.value = ''
  resetNotice.value = ''
  generatedPassword.value = ''
  editorOpen.value = true
}

function closeEditor() {
  editorOpen.value = false
  editorBusy.value = false
  resetBusy.value = false
}

// 只提交真正改过的字段：既避免无意义写入，也让「只有 buyers.manage」的
// 账号不会因为带上未变的余额/白名单而被 whitelist.manage 拦下（403）。
function buildEditPayload() {
  const original = editorOriginal.value || {}
  const payload = {}
  if (editor.display_name !== original.display_name) payload.display_name = editor.display_name
  if (editor.email !== original.email) payload.email = editor.email
  if (editor.phone_e164 !== original.phone_e164) payload.phone_e164 = editor.phone_e164
  if (editor.payment_enabled !== original.payment_enabled) {
    payload.payment_enabled = editor.payment_enabled
  }
  if (editor.purchase_whitelisted !== original.purchase_whitelisted) {
    payload.purchase_whitelisted = editor.purchase_whitelisted
  }
  if (editor.status !== original.status) payload.status = editor.status
  if (Number(editor.balance) !== Number(original.balance)) payload.balance = editor.balance
  if (editor.note.trim()) payload.note = editor.note.trim()
  return payload
}

async function saveEditor() {
  if (editor.balance === '' || Number.isNaN(Number(editor.balance))) {
    editorError.value = '余额必须是数字。'
    return
  }
  const payload = buildEditPayload()
  if (Object.keys(payload).length === 0) {
    closeEditor()
    state.notice = '未检测到修改。'
    return
  }
  editorBusy.value = true
  editorError.value = ''
  try {
    await adminWrite(`/buyers/accounts/${editorId.value}/edit`, payload)
    closeEditor()
    state.notice = '用户资料已保存。'
    await load()
    if (detail.value) await refreshDetail()
  } catch (error) {
    editorError.value = error.message
  } finally {
    editorBusy.value = false
  }
}

async function refreshDetail() {
  const id = detail.value?.id
  if (!id) return
  await openDetail({ id })
}

async function resetPassword(generate) {
  resetError.value = ''
  resetNotice.value = ''
  if (!generate) {
    if (reset.password.length < 8) {
      resetError.value = '新密码至少 8 位。'
      return
    }
    if (reset.password !== reset.confirm) {
      resetError.value = '两次输入的新密码不一致。'
      return
    }
  }
  resetBusy.value = true
  try {
    const payload = generate ? { generate: true } : { password: reset.password }
    if (editor.note.trim()) payload.note = editor.note.trim()
    const response = await adminWrite(`/buyers/accounts/${editorId.value}/reset-password`, payload)
    generatedPassword.value = response.generated_password || ''
    const revoked = Number(response.revoked_sessions) || 0
    resetNotice.value = revoked > 0 ? `密码已重设，${revoked} 个登录会话已失效。` : '密码已重设。'
    if (generatedPassword.value) {
      resetNotice.value += ' 请立即保存下方临时密码（只显示一次）。'
    }
    Object.assign(reset, { password: '', confirm: '' })
  } catch (error) {
    resetError.value = error.message
  } finally {
    resetBusy.value = false
  }
}

const AUTH_PROVIDER_LABELS = { EMAIL: '邮箱', FACEBOOK: 'Facebook', GOOGLE: 'Google' }

function formatTime(value) {
  return value ? value.replace('T', ' ').slice(0, 16) : '—'
}

function resetFilters() {
  state.q = ''
  state.whitelisted = ''
  state.status = ''
  load(true)
}

function goPage(page) {
  state.page = page
  load()
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
        <h1>用户端管理</h1>
        <p>查询商城注册用户、查看白名单标识与充值消费历史。买家余额与商家钱包是两套独立账户。</p>
      </div>
    </div>

    <div class="panel">
      <div class="toolbar">
        <AppPicker
          v-model="state.q"
          :fetcher="fetchBuyerFilterOptions"
          placeholder="选择用户（用户名 / 邮箱 / 手机号 / 编号）"
          @change="load(true)"
        />
        <select v-model="state.whitelisted" @change="load(true)">
          <option value="">全部账号</option>
          <option value="1">仅白名单</option>
          <option value="0">非白名单</option>
        </select>
        <select v-model="state.status" @change="load(true)">
          <option value="">全部状态</option>
          <option value="ACTIVE">启用</option>
          <option value="DISABLED">停用</option>
        </select>
        <button type="button" class="btn" @click="load(true)">查询</button>
        <button type="button" class="btn" @click="resetFilters">重置</button>
      </div>

      <p v-if="state.error" class="notice notice--error" style="margin: 0 20px 14px">
        {{ state.error }}
      </p>
      <p v-if="state.notice" class="notice notice--ok" style="margin: 0 20px 14px">
        {{ state.notice }}
      </p>

      <div class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>账号</th>
              <th>登录渠道</th>
              <th>启用</th>
              <th>白名单</th>
              <th>余额</th>
              <th>支付权限</th>
              <th>注册时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in state.items" :key="row.id">
              <td>
                <b>{{ row.account || '—' }}</b>
                <span class="cell-sub">
                  <!-- 2026-11-27 全站编号改造：用户编号 JYU+10 位整号展示。 -->
                  {{ row.display_name ? `${row.display_name} · ` : '' }}{{ row.id }}
                </span>
              </td>
              <td>
                <span
                  class="tag"
                  :class="row.auth_provider === 'EMAIL' ? 'tag--gray' : 'tag--info'"
                >
                  {{ AUTH_PROVIDER_LABELS[row.auth_provider] || row.auth_provider }}
                </span>
              </td>
              <td>
                <span class="tag" :class="row.enabled ? 'tag--ok' : 'tag--danger'">
                  {{ row.enabled ? '启用' : '停用' }}
                </span>
              </td>
              <td>
                <span class="tag" :class="row.whitelisted ? 'tag--info' : 'tag--gray'">
                  {{ row.whitelisted ? '白名单' : '普通' }}
                </span>
              </td>
              <td class="num">¥ {{ row.balance }}</td>
              <td>
                <span class="tag" :class="row.payment_enabled ? 'tag--ok' : 'tag--gray'">
                  {{ row.payment_permission || '—' }}
                </span>
              </td>
              <td>{{ formatTime(row.joined_at) }}</td>
              <td>
                <div class="row-actions">
                  <button type="button" class="btn btn--sm" @click="openDetail(row)">详情</button>
                  <!-- 2026-11-27：编辑资料 / 支付权限 / 余额 / 白名单 / 状态 + 重设密码。 -->
                  <button type="button" class="btn btn--sm" @click="openEditor(row)">编辑</button>
                  <!-- 迭代02：白名单就地操作（原独立白名单模块已并入本页）。 -->
                  <button
                    type="button"
                    class="btn btn--sm"
                    :class="row.whitelisted ? 'btn--danger' : 'btn--primary'"
                    @click="toggleWhitelist(row)"
                  >
                    {{ row.whitelisted ? '移出白名单' : '加入白名单' }}
                  </button>
                  <button type="button" class="btn btn--sm" @click="toggleStatus(row)">
                    {{ row.enabled ? '停用' : '启用' }}
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!state.loading && state.items.length === 0">
              <td colspan="8" class="data-table__empty">没有匹配的用户。</td>
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
      :title="detail ? `用户详情 · ${detail.account}` : '用户详情'"
      wide
      @close="closeDetail"
    >
      <p v-if="detailLoading" class="inline-loading">加载中…</p>
      <template v-if="detail">
        <div class="form-actions" style="justify-content: flex-start; margin-top: 0">
          <button type="button" class="btn btn--primary" @click="openEditor(detail)">
            编辑用户
          </button>
        </div>
        <dl class="detail-grid">
          <div>
            <dt>用户 ID</dt>
            <dd>{{ detail.id }}</dd>
          </div>
          <div>
            <dt>账号</dt>
            <dd>{{ detail.account }}</dd>
          </div>
          <div>
            <dt>用户名</dt>
            <dd>{{ detail.display_name || '—' }}</dd>
          </div>
          <div>
            <dt>邮箱</dt>
            <dd>{{ detail.email || '—' }}</dd>
          </div>
          <div>
            <dt>手机号</dt>
            <dd>{{ detail.phone || '—' }}</dd>
          </div>
          <div>
            <dt>登录渠道</dt>
            <dd>{{ AUTH_PROVIDER_LABELS[detail.auth_provider] || detail.auth_provider }}</dd>
          </div>
          <div>
            <dt>支付权限</dt>
            <dd>{{ detail.payment_permission }}</dd>
          </div>
          <div>
            <dt>余额</dt>
            <dd>¥ {{ detail.balance }}</dd>
          </div>
          <div>
            <dt>白名单</dt>
            <dd>{{ detail.whitelisted ? '是' : '否' }}</dd>
          </div>
          <div>
            <dt>状态</dt>
            <dd>{{ detail.enabled ? '启用' : '停用' }}</dd>
          </div>
          <div>
            <dt>注册时间</dt>
            <dd>{{ formatTime(detail.joined_at) }}</dd>
          </div>
        </dl>

        <h3 class="section-title">充值 / 消费明细</h3>
        <table v-if="detail.ledger?.length" class="data-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>类型</th>
              <th>金额</th>
              <th>变动后</th>
              <th>关联订单</th>
              <th>备注</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="entry in detail.ledger" :key="entry.id">
              <td>{{ formatTime(entry.occurred_at) }}</td>
              <td>
                {{
                  entry.kind === 'RECHARGE'
                    ? '余额充值'
                    : entry.kind === 'PURCHASE'
                      ? '商城消费'
                      : '余额调整'
                }}
              </td>
              <td
                class="num"
                :style="{ color: Number(entry.amount) < 0 ? 'var(--red)' : 'var(--green)' }"
              >
                ¥ {{ entry.amount }}
              </td>
              <td class="num">¥ {{ entry.balance_after }}</td>
              <td class="mono">{{ entry.order_id || '—' }}</td>
              <td>{{ entry.note || '—' }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty-state">暂无资金明细。</p>
      </template>
    </AppDrawer>

    <AppModal
      v-if="editorOpen"
      title="编辑用户"
      confirm-text="保存"
      :busy="editorBusy"
      @cancel="closeEditor"
      @confirm="saveEditor"
    >
      <p v-if="editorError" class="notice notice--error">{{ editorError }}</p>

      <div class="form-grid">
        <div class="field">
          <label for="buyer-name">用户名</label>
          <input id="buyer-name" v-model="editor.display_name" type="text" maxlength="32" />
          <span class="field__hint">最多 32 个字符；购物端展示昵称。</span>
        </div>
        <div class="field">
          <label for="buyer-email">邮箱</label>
          <input id="buyer-email" v-model="editor.email" type="email" autocomplete="off" />
        </div>
        <div class="field">
          <label for="buyer-phone">手机号</label>
          <input
            id="buyer-phone"
            v-model="editor.phone_e164"
            type="tel"
            placeholder="+447700900123"
          />
          <span class="field__hint">E.164 国际格式（含国家码）。</span>
        </div>
        <div class="field">
          <label for="buyer-payment">支付权限</label>
          <select id="buyer-payment" v-model="editor.payment_enabled">
            <option :value="true">允许</option>
            <option :value="false">已关闭</option>
          </select>
          <span class="field__hint">关闭后该账号无法下单支付。</span>
        </div>
        <div class="field">
          <label for="buyer-balance">余额</label>
          <input id="buyer-balance" v-model="editor.balance" type="number" step="0.01" min="0" />
          <span class="field__hint">保存后写入余额台账（按差额调整）。</span>
        </div>
        <div class="field">
          <label for="buyer-whitelist">白名单</label>
          <select id="buyer-whitelist" v-model="editor.purchase_whitelisted">
            <option :value="true">在白名单</option>
            <option :value="false">不在白名单</option>
          </select>
        </div>
        <div class="field">
          <label for="buyer-status">状态</label>
          <select id="buyer-status" v-model="editor.status">
            <option value="ACTIVE">启用</option>
            <option value="DISABLED">停用</option>
          </select>
        </div>
        <div class="field">
          <label for="buyer-note">备注</label>
          <input
            id="buyer-note"
            v-model="editor.note"
            type="text"
            maxlength="255"
            placeholder="写入审计日志"
          />
        </div>
      </div>

      <h3 class="section-title">重设密码</h3>
      <p v-if="resetError" class="notice notice--error">{{ resetError }}</p>
      <p v-if="resetNotice" class="notice notice--ok">{{ resetNotice }}</p>
      <div v-if="generatedPassword" class="field">
        <label for="buyer-generated">临时密码（只显示一次）</label>
        <input id="buyer-generated" :value="generatedPassword" type="text" readonly />
      </div>
      <div class="form-grid form-grid--tight">
        <div class="field">
          <label for="buyer-password">新密码</label>
          <input
            id="buyer-password"
            v-model="reset.password"
            type="password"
            autocomplete="new-password"
          />
          <span class="field__hint">至少 8 位；重设后该用户所有登录立即失效。</span>
        </div>
        <div class="field">
          <label for="buyer-password-confirm">确认新密码</label>
          <input
            id="buyer-password-confirm"
            v-model="reset.confirm"
            type="password"
            autocomplete="new-password"
          />
        </div>
      </div>
      <div class="form-actions">
        <button type="button" class="btn" :disabled="resetBusy" @click="resetPassword(false)">
          重设密码
        </button>
        <button
          type="button"
          class="btn btn--primary"
          :disabled="resetBusy"
          @click="resetPassword(true)"
        >
          自动生成并重设
        </button>
      </div>
    </AppModal>
  </section>
</template>
