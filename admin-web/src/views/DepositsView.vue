<script setup>
import { onMounted, reactive, ref } from 'vue'

import AppDrawer from '@/components/AppDrawer.vue'
import AppModal from '@/components/AppModal.vue'
import AppPager from '@/components/AppPager.vue'
import StatusTag from '@/components/StatusTag.vue'
import { adminWrite } from '@/composables/useAdminApi'
import { apiRequest } from '@/lib/api'

const state = reactive({
  q: '',
  page: 1,
  items: [],
  meta: { total: 0, page_size: 20, has_next: false },
  loading: false,
  error: '',
})

const actionTarget = ref(null)
const actionKind = ref('')
const actionBusy = ref(false)
const actionError = ref('')
const actionForm = reactive({ amount: '', balance: '' })

const entries = ref([])
const entriesMerchant = ref(null)

async function load(resetPage = false) {
  if (resetPage) state.page = 1
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page: String(state.page) })
    if (state.q.trim()) params.set('q', state.q.trim())
    const payload = await apiRequest(`/deposits?${params}`)
    state.items = payload.items
    state.meta = payload
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

function openAction(row, kind) {
  actionTarget.value = row
  actionKind.value = kind
  actionError.value = ''
  actionForm.amount = ''
  actionForm.balance = row.balance
}

async function submitAction() {
  if (!actionTarget.value) return
  actionBusy.value = true
  actionError.value = ''
  try {
    await adminWrite(`/deposits/${actionTarget.value.id}/actions`, {
      action: actionKind.value,
      amount: actionKind.value === 'recharge' ? actionForm.amount : undefined,
      balance: actionKind.value === 'adjust' ? actionForm.balance : undefined,
    })
    actionTarget.value = null
    await load()
  } catch (error) {
    actionError.value = error.message
  } finally {
    actionBusy.value = false
  }
}

async function openEntries(row) {
  entriesMerchant.value = row
  entries.value = []
  try {
    const payload = await apiRequest(`/deposits/${row.id}/entries?page_size=50`)
    entries.value = payload.items
  } catch (error) {
    state.error = error.message
  }
}

function formatTime(value) {
  if (!value) return '—'
  return value.replace('T', ' ').slice(0, 16)
}

function goPage(page) {
  state.page = page
  load()
}

function resetFilters() {
  state.q = ''
  load(true)
}

onMounted(load)
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>保证金管理</h1>
        <p>
          仅对入驻审核选择需缴保证金的商家生效；首次缴足应缴额后自动转为接单中，余额调整为负也不会封店。
        </p>
      </div>
    </div>

    <div class="panel">
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

      <p v-if="state.error" class="notice notice--error" style="margin: 16px 20px">
        {{ state.error }}
      </p>

      <div class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>店铺</th>
              <th>应缴金额</th>
              <th>保证金余额</th>
              <th>待缴金额</th>
              <th>首次缴足</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in state.items" :key="row.id">
              <td>
                <span class="cell-strong">{{ row.name }}</span>
                <span class="cell-sub">{{ row.id.slice(0, 8) }}</span>
              </td>
              <td class="num">¥ {{ row.required_amount ?? '—' }}</td>
              <td class="num">¥ {{ row.balance }}</td>
              <td class="num">{{ row.pending_amount ? `¥ ${row.pending_amount}` : '已缴足' }}</td>
              <td>{{ row.initial_paid ? '是' : '否' }}</td>
              <td><StatusTag :value="row.status" /></td>
              <td>
                <div class="row-actions">
                  <button
                    type="button"
                    class="btn btn--sm btn--primary"
                    @click="openAction(row, 'recharge')"
                  >
                    充值保证金
                  </button>
                  <button type="button" class="btn btn--sm" @click="openAction(row, 'adjust')">
                    调整余额
                  </button>
                  <button type="button" class="btn btn--sm" @click="openEntries(row)">记录</button>
                </div>
              </td>
            </tr>
            <tr v-if="!state.loading && state.items.length === 0">
              <td colspan="7" class="data-table__empty">没有启用保证金的商家。</td>
            </tr>
            <tr v-if="state.loading">
              <td colspan="7" class="data-table__empty">加载中…</td>
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
      :title="actionKind === 'recharge' ? '充值保证金' : '调整保证金余额'"
      :busy="actionBusy"
      @cancel="actionTarget = null"
      @confirm="submitAction"
    >
      <p v-if="actionError" class="notice notice--error">{{ actionError }}</p>
      <p>
        {{ actionTarget.name }} · 当前保证金 ¥ {{ actionTarget.balance }}，应缴 ¥
        {{ actionTarget.required_amount }}
      </p>
      <div v-if="actionKind === 'recharge'" class="field">
        <label for="deposit-amount">本次充值金额</label>
        <input
          id="deposit-amount"
          v-model="actionForm.amount"
          type="number"
          min="0.01"
          step="0.01"
        />
      </div>
      <div v-else class="field">
        <label for="deposit-balance">调整后的保证金余额</label>
        <input id="deposit-balance" v-model="actionForm.balance" type="number" step="0.01" />
        <span class="field__hint">支持填 0 或负数；系统按差额记一条调整记录，不要求填写说明。</span>
      </div>
    </AppModal>

    <AppDrawer
      v-if="entriesMerchant"
      :title="`保证金记录 · ${entriesMerchant.name}`"
      @close="entriesMerchant = null"
    >
      <table v-if="entries.length" class="data-table">
        <thead>
          <tr>
            <th>时间</th>
            <th>类型</th>
            <th>金额</th>
            <th>余额</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="entry in entries" :key="entry.id">
            <td>{{ formatTime(entry.occurred_at) }}</td>
            <td><StatusTag :value="entry.kind" /></td>
            <td
              class="num"
              :style="{ color: Number(entry.amount) < 0 ? 'var(--red)' : 'var(--green)' }"
            >
              ¥ {{ entry.amount }}
            </td>
            <td class="num">¥ {{ entry.balance_after }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="empty-state">暂无保证金记录。</p>
    </AppDrawer>
  </section>
</template>
