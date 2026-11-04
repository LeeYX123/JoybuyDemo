<script setup>
import { onMounted, reactive, ref } from 'vue'

import AdminTable from '@/components/AdminTable.vue'
import { adminGet, adminWrite } from '@/composables/useAdminApi'
import { valueLabel } from '@/lib/locale'

// CMS publishing: list page versions and publish a new version (which
// archives the previous one — that is the rollback mechanism).
const pages = ref([])
const loading = ref(false)
const message = ref('')
const error = ref('')
const showForm = ref(false)

const form = reactive({
  page_key: 'home',
  title: 'Joybuy 首页',
  modules: '',
  reason: '',
})

const columns = [
  { key: 'page_key', label: '页面' },
  { key: 'version', label: '版本' },
  { key: 'status', label: '状态' },
  { key: 'module_count', label: '模块数' },
]

async function loadPages() {
  loading.value = true
  const data = await adminGet('/content/pages')
  pages.value = (data.items || []).map((page) => ({
    ...page,
    page_key: valueLabel(page.page_key),
    status: valueLabel(page.status),
  }))
  loading.value = false
}

onMounted(loadPages)

async function publish() {
  error.value = ''
  message.value = ''
  let modules
  try {
    modules = JSON.parse(form.modules)
  } catch {
    error.value = '模块数据必须是有效的数组格式，且每项都需包含模块类型与数据。'
    return
  }
  try {
    const data = await adminWrite('/content/pages', {
      page_key: form.page_key,
      title: form.title,
      modules,
      reason: form.reason,
    })
    message.value = `页面「${valueLabel(form.page_key)}」第 ${data.version} 版已发布，上一版已归档；如需回滚，请重新发布历史模块数据。`
    await loadPages()
  } catch (caught) {
    error.value = caught.message
  }
}
</script>

<template>
  <section aria-labelledby="cms-title">
    <h1 id="cms-title">内容页面</h1>

    <p v-if="message" class="notice" role="status">{{ message }}</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <div class="toolbar">
      <button type="button" @click="showForm = !showForm">
        {{ showForm ? '收起发布表单' : '发布新版本' }}
      </button>
      <button type="button" @click="loadPages">刷新</button>
    </div>

    <form v-if="showForm" class="publish-form" @submit.prevent="publish">
      <div class="publish-form__row">
        <label>
          页面标识
          <input v-model="form.page_key" required />
        </label>
        <label>
          标题
          <input v-model="form.title" required />
        </label>
        <label>
          审计原因
          <input v-model="form.reason" required />
        </label>
      </div>
      <label>
        模块数据
        <textarea
          v-model="form.modules"
          rows="8"
          placeholder="请输入模块数组数据"
          required
        ></textarea>
      </label>
      <button type="submit">发布</button>
    </form>

    <AdminTable :columns="columns" :rows="pages" :loading="loading" empty-text="暂无已发布页面。" />
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
.publish-form button {
  min-height: 44px;
  padding: 0 var(--space-4);
  border: 1px solid var(--colour-border-strong);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  cursor: pointer;
  font: inherit;
}

.publish-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin-bottom: var(--space-5);
  padding: var(--space-4);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
}

.publish-form__row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
  gap: var(--space-3);
}

.publish-form label {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  font-size: var(--font-size-sm);
}

.publish-form input,
.publish-form textarea {
  padding: var(--space-2) var(--space-3);
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
