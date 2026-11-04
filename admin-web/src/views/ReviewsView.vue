<script setup>
import { onMounted, ref } from 'vue'

import AdminTable from '@/components/AdminTable.vue'
import { adminGet, adminWrite } from '@/composables/useAdminApi'
import { valueLabel } from '@/lib/locale'

// Review moderation: search, filter by status, soft-delete with a reason
// (history preserved — the storefront simply stops showing the review).
const searchQuery = ref('')
const statusFilter = ref('ACTIVE')
const items = ref([])
const loading = ref(false)
const message = ref('')
const error = ref('')

const columns = [
  { key: 'product', label: '商品' },
  { key: 'rating', label: '星级' },
  { key: 'title', label: '标题' },
  { key: 'display_name', label: '评价人' },
  { key: 'status', label: '状态' },
]

async function loadItems() {
  loading.value = true
  const params = new URLSearchParams()
  if (searchQuery.value.trim()) params.set('q', searchQuery.value.trim())
  if (statusFilter.value) params.set('status', statusFilter.value)
  const data = await adminGet(`/reviews${params.toString() ? `?${params}` : ''}`)
  items.value = (data.items || []).map((row) => ({
    ...row,
    raw_status: row.status,
    status: valueLabel(row.status),
  }))
  loading.value = false
}

onMounted(loadItems)

async function removeReview(row) {
  error.value = ''
  message.value = ''
  const reason = window.prompt(`删除「${row.display_name}」评价的原因（记入审计日志）：`)
  if (!reason) return
  try {
    const data = await adminWrite('/reviews', {
      review_public_id: row.public_id,
      reason,
    })
    message.value = `评价已处理，当前状态：${valueLabel(data.status)}。历史记录已保留。`
    await loadItems()
  } catch (caught) {
    error.value = caught.message
  }
}
</script>

<template>
  <section aria-labelledby="reviews-title">
    <h1 id="reviews-title">评价管理</h1>

    <p v-if="message" class="notice" role="status">{{ message }}</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <form class="toolbar" @submit.prevent="loadItems">
      <input v-model="searchQuery" type="search" placeholder="搜索标题或正文" />
      <select v-model="statusFilter">
        <option value="">全部状态</option>
        <option value="ACTIVE">有效</option>
        <option value="DELETED">已删除</option>
        <option value="HIDDEN">已隐藏</option>
      </select>
      <button type="submit">筛选</button>
    </form>

    <AdminTable :columns="columns" :rows="items" :loading="loading" empty-text="没有匹配的评价。">
      <template #actions="{ row }">
        <button v-if="row.raw_status === 'ACTIVE'" type="button" @click="removeReview(row)">
          删除
        </button>
      </template>
    </AdminTable>
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
