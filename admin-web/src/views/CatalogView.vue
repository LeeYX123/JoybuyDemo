<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import AdminTable from '@/components/AdminTable.vue'
import { adminGet, adminWrite } from '@/composables/useAdminApi'
import { useStaffAuth } from '@/composables/useStaffAuth'
import { actionLabel, fieldLabel, valueLabel } from '@/lib/locale'

// Catalog administration: searchable product documents, the source-vs-
// override review workflow, and inventory adjustment with ledger reasons.
const { hasPermission } = useStaffAuth()

const searchQuery = ref('')
const items = ref([])
const loading = ref(false)
const message = ref('')
const error = ref('')

const selectedSpu = ref(null)
const diffs = ref([])

const inventoryForm = reactive({
  offer_public_id: '',
  quantity_delta: 0,
  ledger_reason: 'MANUAL_ADJUSTMENT',
  reason: '',
  idempotency_key: '',
})

const canManageOffers = computed(() => hasPermission('offers.manage'))

async function loadItems() {
  loading.value = true
  const query = searchQuery.value.trim() ? `?q=${encodeURIComponent(searchQuery.value.trim())}` : ''
  const data = await adminGet(`/search-documents${query}`)
  items.value = (data.items || []).map((row) => ({
    ...row,
    is_searchable: valueLabel(row.is_searchable),
  }))
  loading.value = false
}

onMounted(loadItems)

async function openOverrides(row) {
  error.value = ''
  message.value = ''
  selectedSpu.value = row
  const data = await adminGet(`/catalog/spus/${row.spu_public_id}/overrides`)
  diffs.value = (data.diffs || []).map(localizeDiff)
}

function localizeDiff(diff) {
  return {
    ...diff,
    field_code: diff.field,
    field: fieldLabel(diff.field),
    effective_origin: valueLabel(diff.effective_origin),
    override_status: valueLabel(diff.override?.status),
  }
}

async function overrideAction(action, diff) {
  error.value = ''
  message.value = ''
  const reason = window.prompt(
    `对字段「${diff.field}」执行「${actionLabel(action)}」的原因（记入审计日志）：`,
  )
  if (!reason) return
  const body = { action, field: diff.field_code, reason }
  if (action === 'propose') {
    body.value = window.prompt(`请输入「${diff.field}」的新值：`) ?? ''
  }
  if (action === 'approve') body.decision = 'APPROVED'
  try {
    const data = await adminWrite(
      `/catalog/spus/${selectedSpu.value.spu_public_id}/overrides`,
      body,
    )
    message.value = `字段「${diff.field}」已${actionLabel(action)}，当前状态：${valueLabel(data.status)}，版本：${data.version}。`
    const refreshed = await adminGet(`/catalog/spus/${selectedSpu.value.spu_public_id}/overrides`)
    diffs.value = (refreshed.diffs || []).map(localizeDiff)
  } catch (caught) {
    error.value = caught.message
  }
}

async function submitInventory() {
  error.value = ''
  message.value = ''
  if (!inventoryForm.idempotency_key.trim()) {
    inventoryForm.idempotency_key = `manual-${Date.now()}`
  }
  try {
    const data = await adminWrite(`/offers/${inventoryForm.offer_public_id}/inventory`, {
      ...inventoryForm,
    })
    message.value = `库存已调整，调整后余额：${data.balance_after}。`
  } catch (caught) {
    error.value = caught.message
  }
}

const columns = [
  { key: 'title', label: '标题' },
  { key: 'brand', label: '品牌' },
  { key: 'is_searchable', label: '可搜索' },
  { key: 'min_price', label: '最低价' },
  { key: 'rating_count', label: '评价数' },
]

const diffColumns = [
  { key: 'field', label: '字段' },
  { key: 'source', label: '来源值' },
  { key: 'effective', label: '生效值' },
  { key: 'effective_origin', label: '生效来源' },
  { key: 'override_status', label: '覆盖状态' },
]
</script>

<template>
  <section aria-labelledby="catalog-title">
    <h1 id="catalog-title">商品目录</h1>

    <p v-if="message" class="notice" role="status">{{ message }}</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <form class="toolbar" @submit.prevent="loadItems">
      <input v-model="searchQuery" type="search" placeholder="搜索标题或品牌" />
      <button type="submit">搜索</button>
    </form>

    <AdminTable :columns="columns" :rows="items" :loading="loading" empty-text="没有匹配的商品。">
      <template #actions="{ row }">
        <button type="button" @click="openOverrides(row)">覆盖管理</button>
      </template>
    </AdminTable>

    <section v-if="selectedSpu" class="panel" aria-labelledby="override-title">
      <h2 id="override-title">
        来源值与覆盖值 — {{ selectedSpu.title }}
        <button type="button" class="linkish" @click="selectedSpu = null">关闭</button>
      </h2>
      <AdminTable :columns="diffColumns" :rows="diffs" empty-text="该商品暂无覆盖记录。">
        <template #actions="{ row }">
          <button type="button" @click="overrideAction('propose', row)">提议修改</button>
          <button
            v-if="row.override && row.override.status === 'PENDING'"
            type="button"
            @click="overrideAction('approve', row)"
          >
            批准
          </button>
          <button
            v-if="row.override && ['APPROVED', 'PENDING'].includes(row.override.status)"
            type="button"
            @click="overrideAction('clear', row)"
          >
            清除
          </button>
        </template>
      </AdminTable>
    </section>

    <section v-if="canManageOffers" class="panel" aria-labelledby="inventory-title">
      <h2 id="inventory-title">库存调整</h2>
      <form class="panel-form" @submit.prevent="submitInventory">
        <label>
          销售报价公开标识
          <input v-model="inventoryForm.offer_public_id" placeholder="请输入报价标识" required />
        </label>
        <label>
          增减数量（正/负）
          <input v-model.number="inventoryForm.quantity_delta" type="number" required />
        </label>
        <label>
          台账原因
          <select v-model="inventoryForm.ledger_reason">
            <option value="MANUAL_ADJUSTMENT">人工调整</option>
            <option value="CORRECTION">更正</option>
          </select>
        </label>
        <label>
          原因（记入审计）
          <input v-model="inventoryForm.reason" required />
        </label>
        <button type="submit">执行调整</button>
      </form>
    </section>
  </section>
</template>

<style scoped>
h1 {
  font-size: var(--font-size-xl);
  margin-bottom: var(--space-4);
}

.toolbar {
  display: flex;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}

.toolbar input {
  min-height: 44px;
  flex: 0 1 20rem;
  padding: 0 var(--space-3);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  font: inherit;
}

.toolbar button,
.panel-form button,
.panel :deep(button),
.linkish {
  min-height: 44px;
  padding: 0 var(--space-4);
  border: 1px solid var(--colour-border-strong);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  cursor: pointer;
  font: inherit;
}

.panel :deep(button) {
  min-height: 36px;
  padding: 0 var(--space-3);
}

.linkish {
  border: 0;
  background: none;
  color: var(--colour-accent);
  padding: 0;
  min-height: auto;
  font-size: var(--font-size-sm);
}

.panel {
  margin-top: var(--space-6);
  padding: var(--space-5);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
}

.panel h2 {
  font-size: var(--font-size-lg);
  margin-bottom: var(--space-3);
}

.panel-form {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--space-3);
}

.panel-form label {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  font-size: var(--font-size-sm);
}

.panel-form input,
.panel-form select {
  min-height: 44px;
  padding: 0 var(--space-3);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
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
