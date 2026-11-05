<script setup>
import { onMounted, reactive, ref } from 'vue'

import AppDrawer from '@/components/AppDrawer.vue'
import AppPager from '@/components/AppPager.vue'
import { apiRequest } from '@/lib/api'

const state = reactive({
  q: '',
  module: '',
  action: '',
  start: '',
  end: '',
  page: 1,
  items: [],
  meta: { total: 0, page_size: 20, has_next: false },
  loading: false,
  error: '',
})

const modules = ref([])
const detail = ref(null)

async function loadModules() {
  try {
    const payload = await apiRequest('/audit-logs/modules')
    modules.value = payload.items
  } catch {
    modules.value = []
  }
}

async function load(resetPage = false) {
  if (resetPage) state.page = 1
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page: String(state.page) })
    if (state.q.trim()) params.set('q', state.q.trim())
    if (state.module) params.set('module', state.module)
    if (state.action.trim()) params.set('action', state.action.trim())
    if (state.start) params.set('start', state.start)
    if (state.end) params.set('end', state.end)
    const payload = await apiRequest(`/audit-logs?${params}`)
    state.items = payload.items
    state.meta = payload
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

function exportCsv() {
  const params = new URLSearchParams()
  if (state.q.trim()) params.set('q', state.q.trim())
  if (state.module) params.set('module', state.module)
  if (state.action.trim()) params.set('action', state.action.trim())
  if (state.start) params.set('start', state.start)
  if (state.end) params.set('end', state.end)
  window.open(`/api/v1/admin/audit-logs/export?${params}`, '_blank')
}

function formatTime(value) {
  return value ? value.replace('T', ' ').slice(0, 19) : '—'
}

function summarize(payload) {
  if (!payload || typeof payload !== 'object') return '—'
  const keys = Object.keys(payload)
  if (!keys.length) return '—'
  return keys
    .slice(0, 3)
    .map((key) => `${key}=${JSON.stringify(payload[key])}`)
    .join(' · ')
}

function resetFilters() {
  state.q = ''
  state.module = ''
  state.action = ''
  state.start = ''
  state.end = ''
  load(true)
}

function goPage(page) {
  state.page = page
  load()
}

onMounted(() => {
  loadModules()
  load()
})
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>操作日志</h1>
        <p>追溯后台关键变更、资金确认与登录行为；日志只追加，不可由业务用户修改或删除。</p>
      </div>
      <div class="page-intro__actions">
        <button type="button" class="btn" @click="exportCsv">导出日志</button>
      </div>
    </div>

    <div class="panel">
      <div class="toolbar">
        <input
          v-model="state.q"
          type="search"
          placeholder="操作人 / 对象编号"
          @keyup.enter="load(true)"
        />
        <select v-model="state.module" @change="load(true)">
          <option value="">全部模块</option>
          <option v-for="item in modules" :key="item.code" :value="item.code">
            {{ item.label }}
          </option>
        </select>
        <input
          v-model="state.action"
          type="text"
          placeholder="动作关键字，如 CREATED"
          @keyup.enter="load(true)"
        />
        <input v-model="state.start" type="date" aria-label="开始日期" />
        <span class="cell-sub">至</span>
        <input v-model="state.end" type="date" aria-label="结束日期" />
        <button type="button" class="btn" @click="load(true)">查询</button>
        <button type="button" class="btn" @click="resetFilters">重置</button>
      </div>

      <p v-if="state.error" class="notice notice--error" style="margin: 0 20px 14px">
        {{ state.error }}
      </p>

      <div class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>操作人</th>
              <th>模块</th>
              <th>动作</th>
              <th>业务对象</th>
              <th>变更摘要</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in state.items" :key="row.id">
              <td>{{ formatTime(row.occurred_at) }}</td>
              <td>{{ row.operator }}</td>
              <td>{{ row.module_label }}</td>
              <td class="mono">{{ row.action }}</td>
              <td class="mono">{{ row.target.slice(0, 8) }}</td>
              <td class="mono">{{ summarize(row.after) }}</td>
              <td>
                <div class="row-actions">
                  <button type="button" class="btn btn--sm" @click="detail = row">详情</button>
                </div>
              </td>
            </tr>
            <tr v-if="!state.loading && state.items.length === 0">
              <td colspan="7" class="data-table__empty">当前筛选条件下没有日志。</td>
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

    <AppDrawer v-if="detail" title="变更详情" wide @close="detail = null">
      <dl class="detail-grid">
        <div>
          <dt>时间</dt>
          <dd>{{ formatTime(detail.occurred_at) }}</dd>
        </div>
        <div>
          <dt>操作人</dt>
          <dd>{{ detail.operator }}（{{ detail.operator_email || '系统' }}）</dd>
        </div>
        <div>
          <dt>模块</dt>
          <dd>{{ detail.module_label }}</dd>
        </div>
        <div>
          <dt>动作</dt>
          <dd>{{ detail.action }}</dd>
        </div>
        <div>
          <dt>业务对象</dt>
          <dd class="mono">{{ detail.target }}</dd>
        </div>
        <div>
          <dt>请求 ID</dt>
          <dd class="mono">{{ detail.request_id || '—' }}</dd>
        </div>
        <div>
          <dt>IP</dt>
          <dd class="mono">{{ detail.ip_address || '—' }}</dd>
        </div>
        <div>
          <dt>备注</dt>
          <dd>{{ detail.reason || '—' }}</dd>
        </div>
      </dl>

      <h3 class="section-title">修改前</h3>
      <pre class="json-block">{{ JSON.stringify(detail.before, null, 2) }}</pre>
      <h3 class="section-title">修改后</h3>
      <pre class="json-block">{{ JSON.stringify(detail.after, null, 2) }}</pre>
    </AppDrawer>
  </section>
</template>

<style scoped>
.json-block {
  margin: 0;
  padding: 12px 14px;
  border: 1px solid var(--panel-subtle-border);
  border-radius: 3px;
  background: var(--panel-subtle);
  font-size: 11px;
  line-height: 1.6;
  color: #35465e;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
