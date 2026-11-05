<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import AppModal from '@/components/AppModal.vue'
import { adminWrite } from '@/composables/useAdminApi'
import { apiRequest } from '@/lib/api'

const state = reactive({
  q: '',
  items: [],
  loading: false,
  error: '',
  notice: '',
})

const catalog = ref({ modules: [], role_templates: [] })

const editorOpen = ref(false)
const editorBusy = ref(false)
const editorError = ref('')
const editorId = ref('')
const editorProtected = ref(false)
const editor = reactive({
  account: '',
  name: '',
  password: '',
  status: 'ACTIVE',
  modules: {},
})

const moduleGroups = computed(() => {
  const groups = new Map()
  for (const module of catalog.value.modules) {
    if (!groups.has(module.group)) groups.set(module.group, [])
    groups.get(module.group).push(module)
  }
  return [...groups.entries()].map(([label, modules]) => ({ label, modules }))
})

async function load() {
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams()
    if (state.q.trim()) params.set('q', state.q.trim())
    const payload = await apiRequest(`/staff/accounts?${params}`)
    state.items = payload.items
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

async function loadCatalog() {
  try {
    catalog.value = await apiRequest('/staff/permissions')
  } catch (error) {
    state.error = error.message
  }
}

function emptyModules() {
  return Object.fromEntries(
    catalog.value.modules.map((m) => [m.code, { read: false, write: false }]),
  )
}

function openEditor(row = null) {
  editorId.value = row?.id || ''
  editorProtected.value = Boolean(row?.is_protected)
  editor.account = row?.account || ''
  editor.name = row?.name || ''
  editor.password = ''
  editor.status = row?.status || 'ACTIVE'
  editor.modules = emptyModules()
  if (row?.modules) {
    for (const [code, entry] of Object.entries(row.modules)) {
      if (editor.modules[code]) editor.modules[code] = { ...entry }
    }
  }
  editorError.value = ''
  editorOpen.value = true
}

function toggleWrite(code, value) {
  editor.modules[code].write = value
  if (value) editor.modules[code].read = true
}

function toggleRead(code, value) {
  editor.modules[code].read = value
  if (!value) editor.modules[code].write = false
}

function applyTemplate(code) {
  const template = catalog.value.role_templates.find((item) => item.code === code)
  if (!template) return
  for (const moduleCode of Object.keys(editor.modules)) {
    const wanted = template.modules.includes(moduleCode)
    editor.modules[moduleCode] = { read: wanted, write: wanted }
  }
}

const readCount = computed(() => Object.values(editor.modules).filter((entry) => entry.read).length)

async function save() {
  if (readCount.value === 0) {
    editorError.value = '请至少授予一个可查看模块。'
    return
  }
  editorBusy.value = true
  editorError.value = ''
  const payload = {
    name: editor.name,
    status: editor.status,
    modules: editor.modules,
  }
  if (editor.password) payload.password = editor.password
  try {
    if (editorId.value) {
      await adminWrite(`/staff/accounts/${editorId.value}`, payload, 'PATCH')
    } else {
      await adminWrite('/staff/accounts', {
        ...payload,
        account: editor.account,
        password: editor.password,
      })
    }
    editorOpen.value = false
    state.notice = '账号已保存。'
    await load()
  } catch (error) {
    editorError.value = error.message
  } finally {
    editorBusy.value = false
  }
}

function formatTime(value) {
  return value ? value.replace('T', ' ').slice(0, 16) : '—'
}

function resetFilters() {
  state.q = ''
  load()
}

onMounted(async () => {
  await loadCatalog()
  await load()
})
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>账号与权限</h1>
        <p>逐模块勾选「查看 / 操作」：只勾查看即只读账号，勾操作会自动包含查看。</p>
      </div>
      <div class="page-intro__actions">
        <button
          type="button"
          class="btn btn--primary"
          :disabled="!catalog.modules.length"
          @click="openEditor()"
        >
          新增管理员
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
        <input v-model="state.q" type="search" placeholder="账号或姓名" @keyup.enter="load" />
        <button type="button" class="btn" @click="load">查询</button>
        <button type="button" class="btn" @click="resetFilters">重置</button>
      </div>

      <div class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>账号</th>
              <th>姓名</th>
              <th>角色</th>
              <th>可查看模块</th>
              <th>可操作模块</th>
              <th>状态</th>
              <th>最近登录</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in state.items" :key="row.id">
              <td>
                <b>{{ row.account }}</b>
                <span class="cell-sub">{{ row.id.slice(0, 8) }}</span>
              </td>
              <td>{{ row.name }}</td>
              <td class="mono">{{ row.roles.join(', ') || '—' }}</td>
              <td class="num">
                {{ Object.values(row.modules || {}).filter((m) => m.read).length }}
              </td>
              <td class="num">
                {{ Object.values(row.modules || {}).filter((m) => m.write).length }}
              </td>
              <td>
                <span class="tag" :class="row.status === 'ACTIVE' ? 'tag--ok' : 'tag--danger'">
                  {{ row.status === 'ACTIVE' ? '启用' : '停用' }}
                </span>
              </td>
              <td>{{ formatTime(row.last_login_at) }}</td>
              <td>
                <div class="row-actions">
                  <button type="button" class="btn btn--sm" @click="openEditor(row)">编辑</button>
                </div>
              </td>
            </tr>
            <tr v-if="!state.loading && state.items.length === 0">
              <td colspan="8" class="data-table__empty">没有匹配的账号。</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <AppModal
      v-if="editorOpen"
      :title="editorId ? '编辑管理员' : '新增管理员'"
      confirm-text="保存"
      :busy="editorBusy"
      @cancel="editorOpen = false"
      @confirm="save"
    >
      <p v-if="editorError" class="notice notice--error">{{ editorError }}</p>

      <div class="form-grid">
        <div class="field">
          <label for="staff-account">登录账号</label>
          <input
            id="staff-account"
            v-model="editor.account"
            type="text"
            :disabled="Boolean(editorId)"
            maxlength="64"
            placeholder="name@joybuy.test"
          />
          <span class="field__hint">3–64 位，仅字母、数字与 _ . @ - ；创建后不可改。</span>
        </div>
        <div class="field">
          <label for="staff-name">姓名</label>
          <input id="staff-name" v-model="editor.name" type="text" maxlength="120" />
        </div>
        <div class="field">
          <label for="staff-password">{{ editorId ? '新密码（留空不改）' : '初始密码' }}</label>
          <input
            id="staff-password"
            v-model="editor.password"
            type="password"
            autocomplete="new-password"
          />
          <span class="field__hint">8–64 位；密码不会写进日志或接口响应。</span>
        </div>
        <div class="field">
          <label for="staff-status">状态</label>
          <select id="staff-status" v-model="editor.status" :disabled="editorProtected">
            <option value="ACTIVE">启用</option>
            <option value="DISABLED">停用</option>
          </select>
          <span v-if="editorProtected" class="field__hint">超级管理员不能停用，避免自锁。</span>
        </div>
      </div>

      <div class="field" style="margin-top: 14px">
        <label for="staff-template">角色模板（预填权限，之后可逐项调整）</label>
        <select
          id="staff-template"
          :disabled="editorProtected"
          @change="applyTemplate($event.target.value)"
        >
          <option value="">不套用模板</option>
          <option
            v-for="template in catalog.role_templates"
            :key="template.code"
            :value="template.code"
          >
            {{ template.code }}
          </option>
        </select>
      </div>

      <h3 class="section-title">模块权限（已选 {{ readCount }} 个可查看）</h3>
      <div class="permission-groups">
        <div v-for="group in moduleGroups" :key="group.label" class="permission-group">
          <div class="permission-group__title">{{ group.label }}</div>
          <div v-for="module in group.modules" :key="module.code" class="permission-row">
            <span class="permission-row__label">{{ module.label }}</span>
            <label class="checkline">
              <input
                type="checkbox"
                :checked="editor.modules[module.code]?.read"
                :disabled="editorProtected || editor.modules[module.code]?.write"
                @change="toggleRead(module.code, $event.target.checked)"
              />
              查看
            </label>
            <label class="checkline">
              <input
                type="checkbox"
                :checked="editor.modules[module.code]?.write"
                :disabled="editorProtected"
                @change="toggleWrite(module.code, $event.target.checked)"
              />
              操作
            </label>
          </div>
        </div>
      </div>
    </AppModal>
  </section>
</template>

<style scoped>
.permission-groups {
  display: grid;
  gap: 12px;
  border: 1px solid #e0e7f0;
  border-radius: 4px;
  padding: 12px 14px;
  max-height: 320px;
  overflow-y: auto;
}

.permission-group__title {
  margin-bottom: 6px;
  font-size: 11px;
  letter-spacing: 0.5px;
  color: #7b8aa0;
}

.permission-row {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 6px 0;
  border-bottom: 1px solid #f0f3f8;
  font-size: 12px;
}

.permission-row:last-child {
  border-bottom: 0;
}

.permission-row__label {
  flex: 1;
  color: #52657f;
}
</style>
