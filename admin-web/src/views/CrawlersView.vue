<script setup>
import { onMounted, reactive, ref } from 'vue'

import AdminTable from '@/components/AdminTable.vue'
import { adminGet, adminWrite } from '@/composables/useAdminApi'
import { actionLabel, valueLabel } from '@/lib/locale'

// Crawler job control: create category tasks and drive the run state
// machine (start/pause/resume/cancel/requeue). Risk-control rules are
// enforced server-side; this UI only surfaces them.
const jobs = ref([])
const loading = ref(false)
const message = ref('')
const error = ref('')
const showCreate = ref(false)

const createForm = reactive({
  name: '',
  source_category_public_id: '',
  product_limit: 50,
  include_subcategories: 'auto',
  listing_sort: 'SOURCE_DEFAULT',
  sync_mode: 'INCREMENTAL',
  review_target: 50,
})

const columns = [
  { key: 'name', label: '任务名称' },
  { key: 'status', label: '状态' },
  { key: 'sync_mode', label: '同步模式' },
  { key: 'review_target', label: '评价目标数' },
  { key: 'created_at', label: '创建时间', width: '12rem' },
]

async function loadJobs() {
  loading.value = true
  const data = await adminGet('/crawlers/jobs')
  jobs.value = (data.items || []).map((job) => ({
    ...job,
    raw_status: job.status,
    status: valueLabel(job.status),
    sync_mode: valueLabel(job.sync_mode),
    created_at: job.created_at ? job.created_at.slice(0, 19).replace('T', ' ') : '—',
  }))
  loading.value = false
}

onMounted(loadJobs)

async function submitCreate() {
  error.value = ''
  message.value = ''
  const body = {
    name: createForm.name,
    source_category_public_id: createForm.source_category_public_id,
    product_limit: Number(createForm.product_limit),
    listing_sort: createForm.listing_sort,
    sync_mode: createForm.sync_mode,
    review_target: Number(createForm.review_target),
    include_subcategories:
      createForm.include_subcategories === 'auto'
        ? null
        : createForm.include_subcategories === 'true',
    reason: '从管理页面创建',
  }
  try {
    const data = await adminWrite('/crawlers/jobs', body)
    message.value = `任务「${data.public_id.slice(0, 8)}…」已创建，当前状态：${valueLabel(data.status)}。`
    showCreate.value = false
    await loadJobs()
  } catch (caught) {
    error.value = caught.message
  }
}

async function jobAction(job, action) {
  error.value = ''
  message.value = ''
  const reason = window.prompt(
    `请输入对任务「${job.name}」执行「${actionLabel(action)}」的原因（记入审计日志）：`,
  )
  if (!reason && action !== 'start') return
  try {
    const data = await adminWrite(`/crawlers/jobs/${job.public_id}/actions`, {
      action,
      reason: reason || '从管理页面启动',
    })
    message.value = `任务「${job.name}」已${actionLabel(action)}，当前状态：${valueLabel(data.status || '完成')}。`
    await loadJobs()
  } catch (caught) {
    error.value = caught.message
  }
}
</script>

<template>
  <section aria-labelledby="crawlers-title">
    <h1 id="crawlers-title">爬取任务</h1>

    <p v-if="message" class="notice" role="status">{{ message }}</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <div class="toolbar">
      <button type="button" @click="showCreate = !showCreate">
        {{ showCreate ? '取消创建' : '新建任务' }}
      </button>
      <button type="button" @click="loadJobs">刷新</button>
    </div>

    <form v-if="showCreate" class="create-form" @submit.prevent="submitCreate">
      <label>
        任务名称
        <input v-model="createForm.name" required />
      </label>
      <label>
        来源类目公开标识
        <input v-model="createForm.source_category_public_id" required />
      </label>
      <label>
        商品数量上限
        <input v-model.number="createForm.product_limit" type="number" min="1" required />
      </label>
      <label>
        子类目范围
        <select v-model="createForm.include_subcategories">
          <option value="auto">按层级自动判断</option>
          <option value="true">包含子类目</option>
          <option value="false">仅当前类目</option>
        </select>
      </label>
      <label>
        排序方式
        <select v-model="createForm.listing_sort">
          <option value="SOURCE_DEFAULT">来源默认排序</option>
          <option value="BEST_SELLING">销量优先</option>
          <option value="TOP_RATED">评分优先</option>
          <option value="NEWEST">最新优先</option>
          <option value="RANDOM">随机排序</option>
        </select>
      </label>
      <label>
        同步模式
        <select v-model="createForm.sync_mode">
          <option value="INCREMENTAL">增量同步</option>
          <option value="FULL_REFRESH">全量刷新</option>
        </select>
      </label>
      <label>
        评价目标数（1–300）
        <input v-model.number="createForm.review_target" type="number" min="1" max="300" />
      </label>
      <button type="submit">创建</button>
    </form>

    <AdminTable :columns="columns" :rows="jobs" :loading="loading" empty-text="暂无爬取任务。">
      <template #actions="{ row }">
        <button
          v-if="['READY', 'PAUSED', 'FAILED'].includes(row.raw_status)"
          type="button"
          @click="jobAction(row, 'start')"
        >
          启动
        </button>
        <button v-if="row.raw_status === 'RUNNING'" type="button" @click="jobAction(row, 'pause')">
          暂停
        </button>
        <button v-if="row.raw_status === 'PAUSED'" type="button" @click="jobAction(row, 'resume')">
          继续
        </button>
        <button
          v-if="['RUNNING', 'PAUSED'].includes(row.raw_status)"
          type="button"
          @click="jobAction(row, 'cancel')"
        >
          取消
        </button>
        <button v-if="row.raw_status === 'FAILED'" type="button" @click="jobAction(row, 'requeue')">
          重新入队
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

.toolbar button,
.create-form button {
  min-height: 44px;
  padding: 0 var(--space-4);
  border: 1px solid var(--colour-border-strong);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  cursor: pointer;
  font: inherit;
}

.create-form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
  gap: var(--space-3);
  margin-bottom: var(--space-5);
  padding: var(--space-4);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
}

.create-form label {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  font-size: var(--font-size-sm);
}

.create-form input,
.create-form select {
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
