<script setup>
import { onMounted, reactive, ref } from 'vue'

import AppModal from '@/components/AppModal.vue'
import AppPager from '@/components/AppPager.vue'
import { adminWrite } from '@/composables/useAdminApi'
import { apiRequest } from '@/lib/api'

const state = reactive({
  q: '',
  page: 1,
  items: [],
  meta: { total: 0, page_size: 20, has_next: false },
  loading: false,
  error: '',
  notice: '',
})

const target = ref(null)
const actionKind = ref('')
const actionBusy = ref(false)
const actionError = ref('')
const actionForm = reactive({ amount: '', balance: '', note: '' })

const finderOpen = ref(false)
const finderQuery = ref('')
const finderItems = ref([])

async function load(resetPage = false) {
  if (resetPage) state.page = 1
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page: String(state.page), whitelisted: '1' })
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

function openAction(row, kind) {
  target.value = row
  actionKind.value = kind
  actionError.value = ''
  actionForm.amount = ''
  actionForm.balance = row.balance
  actionForm.note = ''
}

async function submitAction() {
  if (!target.value) return
  actionBusy.value = true
  actionError.value = ''
  try {
    await adminWrite(`/buyers/accounts/${target.value.id}/whitelist`, {
      action: actionKind.value,
      amount: actionKind.value === 'recharge' ? actionForm.amount : undefined,
      balance: actionKind.value === 'adjust' ? actionForm.balance : undefined,
      note: actionForm.note,
    })
    target.value = null
    state.notice = '操作已完成。'
    await load()
  } catch (error) {
    actionError.value = error.message
  } finally {
    actionBusy.value = false
  }
}

async function searchUsers() {
  if (!finderQuery.value.trim()) {
    finderItems.value = []
    return
  }
  try {
    const payload = await apiRequest(
      `/buyers/lookup?q=${encodeURIComponent(finderQuery.value.trim())}`,
    )
    finderItems.value = payload.items
  } catch (error) {
    state.error = error.message
  }
}

async function addToWhitelist(user) {
  try {
    await adminWrite(`/buyers/accounts/${user.id}/whitelist`, { action: 'add' })
    finderOpen.value = false
    finderQuery.value = ''
    finderItems.value = []
    state.notice = `已把 ${user.account} 加入白名单。`
    await load(true)
  } catch (error) {
    state.error = error.message
  }
}

function formatTime(value) {
  return value ? value.replace('T', ' ').slice(0, 16) : '—'
}

function resetFilters() {
  state.q = ''
  load(true)
}

function goPage(page) {
  state.page = page
  load()
}

onMounted(load)
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>白名单账号</h1>
        <p>白名单可在未开放地区进入支付并用余额扣款；移出只取消权限，余额与历史保留。</p>
      </div>
      <div class="page-intro__actions">
        <button type="button" class="btn btn--primary" @click="finderOpen = true">
          添加白名单
        </button>
      </div>
    </div>

    <p v-if="state.notice" class="notice notice--ok" style="margin-bottom: 14px">
      {{ state.notice }}
    </p>
    <p v-if="state.error" class="notice notice--error" style="margin-bottom: 14px">
      {{ state.error }}
    </p>

    <div class="panel">
      <div class="toolbar">
        <input
          v-model="state.q"
          type="search"
          placeholder="账号 / 邮箱 / 手机号"
          @keyup.enter="load(true)"
        />
        <button type="button" class="btn" @click="load(true)">查询</button>
        <button type="button" class="btn" @click="resetFilters">重置</button>
      </div>

      <div class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>账号</th>
              <th>地区</th>
              <th>状态</th>
              <th>余额</th>
              <th>余额支付</th>
              <th>注册时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in state.items" :key="row.id">
              <td>
                <b>{{ row.account || '—' }}</b>
                <span class="cell-sub">{{ row.id.slice(0, 8) }}</span>
              </td>
              <td>{{ row.region || '未设置' }}</td>
              <td>
                <span class="tag" :class="row.enabled ? 'tag--ok' : 'tag--danger'">
                  {{ row.enabled ? '启用' : '停用' }}
                </span>
              </td>
              <td class="num">¥ {{ row.balance }}</td>
              <td>
                <span class="tag" :class="row.balance_pay_allowed ? 'tag--ok' : 'tag--gray'">
                  {{ row.balance_pay_allowed ? '允许' : '禁止' }}
                </span>
              </td>
              <td>{{ formatTime(row.joined_at) }}</td>
              <td>
                <div class="row-actions">
                  <button
                    type="button"
                    class="btn btn--sm btn--primary"
                    :disabled="!row.enabled"
                    @click="openAction(row, 'recharge')"
                  >
                    充值
                  </button>
                  <button type="button" class="btn btn--sm" @click="openAction(row, 'adjust')">
                    调整余额
                  </button>
                  <button
                    type="button"
                    class="btn btn--sm btn--danger"
                    @click="openAction(row, 'remove')"
                  >
                    移出白名单
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!state.loading && state.items.length === 0">
              <td colspan="7" class="data-table__empty">白名单里还没有账号。</td>
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
      v-if="target"
      :title="
        actionKind === 'recharge'
          ? '白名单充值'
          : actionKind === 'adjust'
            ? '调整账号余额'
            : '移出白名单'
      "
      :confirm-text="actionKind === 'remove' ? '确认移出' : '确认提交'"
      :busy="actionBusy"
      @cancel="target = null"
      @confirm="submitAction"
    >
      <p v-if="actionError" class="notice notice--error">{{ actionError }}</p>
      <p>{{ target.account }} · 当前余额 ¥ {{ target.balance }}</p>

      <div v-if="actionKind === 'recharge'" class="field">
        <label for="whitelist-amount">充值金额</label>
        <input
          id="whitelist-amount"
          v-model="actionForm.amount"
          type="number"
          min="0.01"
          step="0.01"
        />
        <span class="field__hint">确认后立即增加余额并写一条「余额充值」流水，同一请求幂等。</span>
      </div>
      <div v-else-if="actionKind === 'adjust'" class="field">
        <label for="whitelist-balance">调整后的余额</label>
        <input
          id="whitelist-balance"
          v-model="actionForm.balance"
          type="number"
          min="0"
          step="0.01"
        />
        <span class="field__hint">系统按差额记流水，余额不能为负。</span>
      </div>
      <div v-else class="field">
        <span class="field__hint">
          移出后将取消余额支付与地区豁免，余额和历史记录保留。若有余额，请先与用户确认处理方式。
        </span>
      </div>
    </AppModal>

    <AppModal
      v-if="finderOpen"
      title="添加白名单"
      confirm-text="关闭"
      @cancel="finderOpen = false"
      @confirm="finderOpen = false"
    >
      <div class="field">
        <label for="finder-query">搜索已注册用户</label>
        <input
          id="finder-query"
          v-model="finderQuery"
          type="search"
          placeholder="账号 / 邮箱 / 手机号"
          @input="searchUsers"
        />
        <span class="field__hint">只匹配已注册用户；已停用账号不能加入白名单。</span>
      </div>
      <table v-if="finderItems.length" class="data-table" style="margin-top: 12px">
        <thead>
          <tr>
            <th>账号</th>
            <th>状态</th>
            <th>白名单</th>
            <th>余额</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="user in finderItems" :key="user.id">
            <td>{{ user.account }}</td>
            <td>{{ user.enabled ? '启用' : '停用' }}</td>
            <td>{{ user.whitelisted ? '已加入' : '未加入' }}</td>
            <td class="num">¥ {{ user.balance }}</td>
            <td>
              <button
                type="button"
                class="btn btn--sm btn--primary"
                :disabled="user.whitelisted || !user.enabled"
                @click="addToWhitelist(user)"
              >
                加入白名单
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </AppModal>
  </section>
</template>
