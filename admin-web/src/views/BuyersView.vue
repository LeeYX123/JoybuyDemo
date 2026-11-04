<script setup>
import { computed, onMounted, ref } from 'vue'

import AdminTable from '@/components/AdminTable.vue'
import { adminGet, adminWrite } from '@/composables/useAdminApi'
import { actionLabel, valueLabel } from '@/lib/locale'

// Buyers (enable/disable only — no deletion by policy) and the phase-1
// order view (PENDING_PAYMENT / CANCELED listing, no fulfilment actions).
const tab = ref('buyers')
const buyerQuery = ref('')
const buyers = ref([])
const orders = ref([])
const orderFilter = ref('PENDING_PAYMENT')
const loading = ref(false)
const message = ref('')
const error = ref('')

const buyerColumns = [
  { key: 'email', label: '电子邮箱' },
  { key: 'phone', label: '手机号码' },
  { key: 'status', label: '状态' },
  { key: 'created_at', label: '创建时间', width: '12rem' },
]

const orderColumns = [
  { key: 'public_id', label: '订单号' },
  { key: 'status', label: '状态' },
  { key: 'total', label: '总额' },
  { key: 'currency', label: '币种' },
  { key: 'item_count', label: '商品件数' },
  { key: 'created_at', label: '创建时间', width: '12rem' },
]

async function loadTab() {
  loading.value = true
  if (tab.value === 'buyers') {
    const query = buyerQuery.value.trim() ? `?q=${encodeURIComponent(buyerQuery.value.trim())}` : ''
    const data = await adminGet(`/buyers${query}`)
    buyers.value = (data.items || []).map((row) => ({
      ...row,
      raw_status: row.status,
      status: valueLabel(row.status),
      created_at: row.created_at.slice(0, 19).replace('T', ' '),
    }))
  } else {
    const query = orderFilter.value ? `?status=${orderFilter.value}` : ''
    const data = await adminGet(`/orders${query}`)
    orders.value = (data.items || []).map((row) => ({
      ...row,
      status: valueLabel(row.status),
      currency: valueLabel(row.currency),
      public_id: `#${row.public_id.slice(0, 8)}`,
      created_at: row.created_at.slice(0, 19).replace('T', ' '),
    }))
  }
  loading.value = false
}

onMounted(loadTab)

function switchTab(next) {
  tab.value = next
  loadTab()
}

async function buyerAction(row, action) {
  error.value = ''
  message.value = ''
  const reason = window.prompt(
    `请输入对账号 ${row.email} 执行「${actionLabel(action)}」的原因（记入审计日志）：`,
  )
  if (!reason) return
  try {
    const data = await adminWrite('/buyers', {
      buyer_public_id: row.public_id,
      action,
      reason,
    })
    message.value = `账号 ${row.email} 已${actionLabel(action)}，当前状态：${valueLabel(data.status)}。`
    await loadTab()
  } catch (caught) {
    error.value = caught.message
  }
}

const buyerCount = computed(() => buyers.value.length)
</script>

<template>
  <section aria-labelledby="buyers-title">
    <h1 id="buyers-title">买家与订单</h1>

    <p v-if="message" class="notice" role="status">{{ message }}</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <div class="tabs" role="tablist">
      <button
        type="button"
        role="tab"
        :aria-selected="tab === 'buyers'"
        :class="{ active: tab === 'buyers' }"
        @click="switchTab('buyers')"
      >
        买家
      </button>
      <button
        type="button"
        role="tab"
        :aria-selected="tab === 'orders'"
        :class="{ active: tab === 'orders' }"
        @click="switchTab('orders')"
      >
        订单
      </button>
    </div>

    <template v-if="tab === 'buyers'">
      <form class="toolbar" @submit.prevent="loadTab">
        <input v-model="buyerQuery" type="search" placeholder="搜索电子邮箱或手机号码" />
        <button type="submit">搜索</button>
      </form>

      <AdminTable
        :columns="buyerColumns"
        :rows="buyers"
        :loading="loading"
        :empty-text="`当前有 ${buyerCount} 个买家账号，请通过搜索查找。`"
      >
        <template #actions="{ row }">
          <button
            v-if="row.raw_status === 'ACTIVE'"
            type="button"
            @click="buyerAction(row, 'disable')"
          >
            停用
          </button>
          <button v-else type="button" @click="buyerAction(row, 'enable')">启用</button>
        </template>
      </AdminTable>
    </template>

    <template v-else>
      <form class="toolbar" @submit.prevent="loadTab">
        <select v-model="orderFilter">
          <option value="">全部状态</option>
          <option value="PENDING_PAYMENT">待支付</option>
          <option value="CANCELED">已取消</option>
        </select>
        <button type="submit">筛选</button>
      </form>

      <AdminTable
        :columns="orderColumns"
        :rows="orders"
        :loading="loading"
        empty-text="该状态下暂无订单。"
      />
    </template>
  </section>
</template>

<style scoped>
h1 {
  font-size: var(--font-size-xl);
  margin-bottom: var(--space-4);
}

.tabs {
  display: flex;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}

.tabs button {
  min-height: 44px;
  padding: 0 var(--space-5);
  border: 1px solid var(--colour-border-strong);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  cursor: pointer;
  font: inherit;
  font-weight: var(--font-weight-semibold);
}

.tabs button.active {
  color: var(--colour-accent);
  border-color: var(--colour-accent);
  background: var(--colour-accent-soft);
}

.toolbar {
  display: flex;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}

.toolbar input,
.toolbar select {
  min-height: 44px;
  padding: 0 var(--space-3);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  font: inherit;
}

.toolbar input {
  flex: 0 1 20rem;
}

.toolbar button {
  min-height: 44px;
  padding: 0 var(--space-4);
  border: 1px solid var(--colour-border-strong);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  cursor: pointer;
  font: inherit;
}

.notice {
  color: var(--colour-success);
  margin-bottom: var(--space-3);
}

.error {
  color: var(--colour-error);
  margin-bottom: var(--space-3);
}
</style>
