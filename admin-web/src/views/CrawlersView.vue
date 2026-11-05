<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

import AdminTable from '@/components/AdminTable.vue'
import CategoryTreePicker from '@/components/CategoryTreePicker.vue'
import { adminGet, adminWrite } from '@/composables/useAdminApi'
import { actionLabel, eventCodeLabel, valueLabel } from '@/lib/locale'

// 爬虫任务模块（2026-11-05 重建）：类目树选择建任务 + 运行进度/事件流 +
// Facebook 爬虫账号管理（人工弹窗登录，密码永不落库）。
const activeTab = ref('jobs')

// ---- 任务 Tab ----
const jobs = ref([])
const loadingJobs = ref(false)
const message = ref('')
const error = ref('')
const showCreate = ref(false)
const tree = ref({ version: null, categories: [] })
const selectedCategories = ref([])

const createForm = reactive({
  name: '',
  product_limit: 50,
  listing_sort: 'SOURCE_DEFAULT',
  sync_mode: 'INCREMENTAL',
  review_target: 50,
  // 爬虫账号：空字符串 = 按账号组自动选号（2026-11-05 起可指定）。
  account_public_id: '',
  // 账号组：不指定具体账号时，从这一组里挑可用账号并轮换。
  account_group: 'default',
})

const jobColumns = [
  { key: 'name', label: '任务名称' },
  { key: 'status', label: '状态' },
  { key: 'categories', label: '类目' },
  { key: 'sync_mode', label: '同步模式' },
  { key: 'review_target', label: '评价目标数' },
  { key: 'created_at', label: '创建时间', width: '12rem' },
]

// 任务详情抽屉（进度计数 + 事件流，运行中每 5s 轮询）
const detail = ref(null)
let detailTimer = null

const accountColumns = [
  { key: 'label', label: '账号名称' },
  { key: 'account_group', label: '账号组' },
  { key: 'status', label: '状态' },
  { key: 'session_status', label: '会话' },
  { key: 'note', label: '最近动作' },
]

const accounts = ref([])
const loadingAccounts = ref(false)
// 只有 ACTIVE 账号可以被指定；停用/风控暂停的账号即使指定了后端也会拒绝。
const selectableAccounts = computed(() =>
  accounts.value.filter((account) => account.raw_status === 'ACTIVE'),
)
const showAccountCreate = ref(false)
const accountForm = reactive({ label: '', account_group: '', note: '' })
// 账号组是独立实体（2026-11-05）：下拉选择，可先建空组再放账号。
const accountGroups = ref([])
const showGroupCreate = ref(false)
const groupForm = reactive({ name: '', note: '' })
// 编辑中的一个账号（空 = 未编辑）
const editingAccountId = ref('')
const editingAccountLabel = ref('')
const editForm = reactive({ label: '', account_group: '', note: '' })
const loginPendingIds = ref(new Set())
let accountTimer = null

async function loadTree() {
  try {
    tree.value = await adminGet('/crawlers/source-tree')
  } catch (caught) {
    tree.value = { version: null, categories: [] }
    error.value = `类目树加载失败：${caught.message}`
  }
}

async function loadJobs() {
  loadingJobs.value = true
  try {
    const data = await adminGet('/crawlers/jobs')
    jobs.value = (data.items || []).map((job) => ({
      ...job,
      raw_status: job.status,
      status: valueLabel(job.status),
      sync_mode: valueLabel(job.sync_mode),
      created_at: job.created_at ? job.created_at.slice(0, 19).replace('T', ' ') : '—',
    }))
  } finally {
    loadingJobs.value = false
  }
}

async function loadAccounts() {
  loadingAccounts.value = true
  try {
    const data = await adminGet('/crawlers/accounts')
    accounts.value = (data.items || []).map((account) => ({
      ...account,
      raw_status: account.status,
      raw_session: account.session_status,
      status: valueLabel(account.status),
      session_status: valueLabel(account.session_status),
      session_updated_at: account.session_updated_at
        ? account.session_updated_at.slice(0, 19).replace('T', ' ')
        : '—',
      note: account.note || '—',
      login_pending: loginPendingIds.value.has(account.public_id),
    }))
  } finally {
    loadingAccounts.value = false
  }
}

onMounted(() => {
  loadJobs()
  loadTree()
  loadAccounts()
  loadAccountGroups()
})

onBeforeUnmount(() => {
  if (detailTimer) clearTimeout(detailTimer)
  if (accountTimer) clearTimeout(accountTimer)
})

async function submitCreate() {
  error.value = ''
  message.value = ''
  if (selectedCategories.value.length === 0) {
    error.value = '请至少勾选一个 Joybuy 类目。'
    return
  }
  const body = {
    name: createForm.name,
    product_limit: Number(createForm.product_limit),
    listing_sort: createForm.listing_sort,
    sync_mode: createForm.sync_mode,
    review_target: Number(createForm.review_target),
    account_public_id: createForm.account_public_id || null,
    account_group: createForm.account_group || 'default',
    // 类目身份是 joybuy 的 source_id（如 l2:1405），非 UUID。
    source_ids: selectedCategories.value.map((item) => item.source_id),
    include_subcategories: selectedCategories.value.every((item) => item.include_descendants),
    reason: '从管理页面创建',
  }
  try {
    const data = await adminWrite('/crawlers/jobs', body)
    message.value = `任务「${data.public_id.slice(0, 8)}…」已创建，当前状态：${valueLabel(data.status)}。`
    showCreate.value = false
    selectedCategories.value = []
    createForm.name = ''
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
    message.value = `任务「${job.name}」已${actionLabel(action)}，当前状态：${valueLabel(data.status || 'RUNNING')}。`
    await loadJobs()
    if (detail.value && detail.value.public_id === job.public_id) {
      await openDetail({ public_id: job.public_id, name: job.name }, { keepOpen: true })
    }
  } catch (caught) {
    error.value = caught.message
  }
}

async function openDetail(job, { keepOpen = false } = {}) {
  if (!keepOpen) detail.value = { public_id: job.public_id, name: job.name }
  try {
    const data = await adminGet(`/crawlers/jobs/${job.public_id}`)
    detail.value = {
      ...data,
      account: data.account
        ? {
            ...data.account,
            session_status_label: valueLabel(data.account.session_status),
            status_label: valueLabel(data.account.status),
          }
        : null,
      categoriesText: (data.categories || [])
        .map((item) => `${item.name}${item.include_descendants ? '（含子类目）' : ''}`)
        .join('、'),
      runs: (data.runs || []).map((run) => ({
        ...run,
        status_label: valueLabel(run.status),
        account_label: run.account_label || '—',
        started_at: run.started_at ? run.started_at.slice(5, 19).replace('T', ' ') : '—',
        finished_at: run.finished_at ? run.finished_at.slice(5, 19).replace('T', ' ') : '—',
      })),
      events: (data.events || []).map((event) => ({
        ...event,
        created_at: event.created_at ? event.created_at.slice(5, 19).replace('T', ' ') : '',
      })),
    }
  } catch (caught) {
    error.value = caught.message
    return
  }
  const latestRunning = (detail.value.runs || []).some((run) => run.status === 'RUNNING')
  if (latestRunning) {
    if (detailTimer) clearTimeout(detailTimer)
    detailTimer = setTimeout(
      () => openDetail({ public_id: job.public_id }, { keepOpen: true }),
      5000,
    )
  }
}

function closeDetail() {
  detail.value = null
  if (detailTimer) clearTimeout(detailTimer)
}

// ---- 账号 Tab 动作 ----
async function loadAccountGroups() {
  const data = await adminGet('/crawlers/account-groups')
  accountGroups.value = data.items || []
  if (!accountForm.account_group) {
    accountForm.account_group = accountGroups.value[0]?.name || 'default'
  }
  if (editingAccountId.value && !editForm.account_group) {
    editForm.account_group = accountGroups.value[0]?.name || 'default'
  }
}

async function submitGroupCreate() {
  error.value = ''
  message.value = ''
  if (!groupForm.name.trim()) {
    error.value = '请填写账号组名称。'
    return
  }
  try {
    const data = await adminWrite('/crawlers/account-groups', {
      name: groupForm.name.trim(),
      note: groupForm.note,
      reason: '从管理页面新增账号组',
    })
    message.value = `账号组「${data.name}」已创建，可直接用于账号。`
    groupForm.name = ''
    groupForm.note = ''
    showGroupCreate.value = false
    await loadAccountGroups()
  } catch (caught) {
    error.value = caught.message
  }
}

function startEditAccount(account) {
  error.value = ''
  message.value = ''
  editingAccountId.value = account.public_id
  editingAccountLabel.value = account.label
  editForm.label = account.label
  editForm.account_group = account.account_group
  editForm.note = account.note === '—' ? '' : account.note
}

function cancelEditAccount() {
  editingAccountId.value = ''
  editingAccountLabel.value = ''
}

async function submitAccountEdit() {
  error.value = ''
  message.value = ''
  try {
    await adminWrite(
      `/crawlers/accounts/${editingAccountId.value}`,
      {
        label: editForm.label,
        account_group: editForm.account_group,
        note: editForm.note,
        reason: '从管理页面编辑账号',
      },
      'PUT',
    )
    message.value = `账号「${editForm.label}」已保存。`
    cancelEditAccount()
    await loadAccounts()
    await loadAccountGroups()
  } catch (caught) {
    error.value = caught.message
  }
}

async function deleteAccount(account) {
  error.value = ''
  message.value = ''
  const reason = window.prompt(
    `确认删除账号「${account.label}」？\n\n删除后该账号从列表消失、已保存的会话 Cookie 立即销毁；` +
      '历史运行记录仍保留账号名，不会被改写。\n\n请填写删除原因（记入审计日志）：',
    '账号不再使用',
  )
  if (reason === null) return
  try {
    await adminWrite(
      `/crawlers/accounts/${account.public_id}`,
      { reason: reason || '从管理页面删除账号' },
      'DELETE',
    )
    message.value = `账号「${account.label}」已删除。`
    if (editingAccountId.value === account.public_id) cancelEditAccount()
    await loadAccounts()
    await loadAccountGroups()
  } catch (caught) {
    error.value = caught.message
  }
}

async function submitAccountCreate() {
  error.value = ''
  message.value = ''
  try {
    await adminWrite('/crawlers/accounts', { ...accountForm, reason: '从管理页面新增账号' })
    message.value = `账号「${accountForm.label}」已创建。点击「登录」打开浏览器完成 Facebook 登录。`
    accountForm.label = ''
    accountForm.note = ''
    showAccountCreate.value = false
    await loadAccounts()
    await loadAccountGroups()
  } catch (caught) {
    error.value = caught.message
  }
}

async function accountAction(account, action) {
  error.value = ''
  message.value = ''
  try {
    const data = await adminWrite(`/crawlers/accounts/${account.public_id}/actions`, {
      action,
      reason: `从管理页面${actionLabel(action)}`,
    })
    if (action === 'login') {
      loginPendingIds.value.add(account.public_id)
      message.value =
        '登录窗口已打开：请在弹出的浏览器中完成 Facebook 登录，本页会在保存会话后自动刷新。'
      scheduleAccountPoll()
    } else if (action === 'verify') {
      message.value =
        data.verified === true
          ? `账号「${account.label}」会话有效（在隔离无头浏览器中用该账号存储的 ${data.cookie_count} 条加密 Cookie 验证，与你本机浏览器无关）。`
          : `账号「${account.label}」会话检查未通过：${data.reason === 'SESSION_EXPIRED' ? '会话已过期，请重新登录' : data.reason === 'RISK_CONTROL_BLOCKED' ? '页面被风控拦截，稍后再试' : data.reason === 'NO_SESSION' ? '尚未登录保存过会话' : data.reason}`
    } else {
      message.value = `账号「${account.label}」已${actionLabel(action)}。`
    }
    await loadAccounts()
  } catch (caught) {
    error.value = caught.message
  }
}

function scheduleAccountPoll() {
  if (accountTimer) clearTimeout(accountTimer)
  accountTimer = setTimeout(async () => {
    await loadAccounts()
    const stillPending = [...loginPendingIds.value].some((id) => {
      const found = accounts.value.find((account) => account.public_id === id)
      return found && found.raw_session === 'UNKNOWN'
    })
    if (stillPending) scheduleAccountPoll()
    else loginPendingIds.value = new Set()
  }, 5000)
}

const hasLoginPending = computed(() => loginPendingIds.value.size > 0)
</script>

<template>
  <section aria-labelledby="crawlers-title">
    <h1 id="crawlers-title">爬取任务</h1>

    <div class="tabs" role="tablist">
      <button
        type="button"
        role="tab"
        :aria-selected="activeTab === 'jobs'"
        :class="{ 'tabs__tab--active': activeTab === 'jobs' }"
        @click="activeTab = 'jobs'"
      >
        任务
      </button>
      <button
        type="button"
        role="tab"
        :aria-selected="activeTab === 'accounts'"
        :class="{ 'tabs__tab--active': activeTab === 'accounts' }"
        @click="activeTab = 'accounts'"
      >
        爬虫账号
      </button>
    </div>

    <p v-if="message" class="notice" role="status">{{ message }}</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="hasLoginPending" class="notice" role="status">
      正在等待人工登录完成…（完成或超时后本页自动刷新）
    </p>

    <!-- ======================= 任务 Tab ======================= -->
    <div v-if="activeTab === 'jobs'">
      <div class="toolbar">
        <button type="button" @click="showCreate = !showCreate">
          {{ showCreate ? '取消创建' : '新建任务' }}
        </button>
        <button type="button" @click="loadJobs">刷新</button>
      </div>

      <div v-if="showCreate" class="create-form">
        <label>
          任务名称
          <input v-model="createForm.name" required />
        </label>
        <label>
          商品数量上限
          <input v-model.number="createForm.product_limit" type="number" min="1" required />
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
        <label>
          账号组
          <select v-model="createForm.account_group">
            <option v-for="group in accountGroups" :key="group.name" :value="group.name">
              {{ group.name }}（{{ group.account_count }} 个账号）
            </option>
          </select>
        </label>
        <label>
          爬虫账号
          <select v-model="createForm.account_public_id">
            <option value="">自动（按账号组挑可用账号）</option>
            <option
              v-for="account in selectableAccounts"
              :key="account.public_id"
              :value="account.public_id"
            >
              {{ account.label }}（{{ account.account_group }} · {{ account.session_status }}）
            </option>
          </select>
        </label>
        <p class="create-form__account-hint">
          指定账号后，爬虫每次请求都会带上该账号的登录 Cookie，并把它排在轮换池第一位；留空则在
          所选账号组内挑可用账号并轮换。组内没有可用账号时按匿名抓取——只有「会话有效」的账号才真正
          带得上登录态。
        </p>
        <div class="create-form__tree">
          <p class="create-form__tree-title">
            选择 Joybuy 类目（树版本 {{ tree.version || '未同步' }}）
          </p>
          <p class="create-form__tree-hint">
            类目按「中文名 / English name」一一对应展示；搜索框支持中英文与来源 ID。
          </p>
          <CategoryTreePicker v-model="selectedCategories" :categories="tree.categories" />
        </div>
        <button type="button" @click="submitCreate">创建任务</button>
      </div>

      <AdminTable
        :columns="jobColumns"
        :rows="jobs"
        :loading="loadingJobs"
        empty-text="暂无爬取任务。"
      >
        <template #actions="{ row }">
          <button type="button" @click="openDetail(row)">详情</button>
          <button
            v-if="['READY', 'PAUSED', 'FAILED'].includes(row.raw_status)"
            type="button"
            @click="jobAction(row, 'start')"
          >
            启动
          </button>
          <button
            v-if="row.raw_status === 'RUNNING'"
            type="button"
            @click="jobAction(row, 'pause')"
          >
            暂停
          </button>
          <button
            v-if="row.raw_status === 'PAUSED'"
            type="button"
            @click="jobAction(row, 'resume')"
          >
            继续
          </button>
          <button
            v-if="['RUNNING', 'PAUSED'].includes(row.raw_status)"
            type="button"
            @click="jobAction(row, 'cancel')"
          >
            取消
          </button>
          <button
            v-if="row.raw_status === 'FAILED'"
            type="button"
            @click="jobAction(row, 'requeue')"
          >
            重新入队
          </button>
        </template>
      </AdminTable>

      <!-- 任务详情抽屉 -->
      <div v-if="detail" class="detail" role="dialog" aria-label="任务详情">
        <div class="detail__head">
          <h2>任务详情：{{ detail.name }}</h2>
          <button type="button" @click="closeDetail">关闭</button>
        </div>
        <dl class="detail__meta">
          <div>
            <dt>状态</dt>
            <dd>{{ valueLabel(detail.status) }}</dd>
          </div>
          <div>
            <dt>类目选择</dt>
            <dd>{{ detail.categoriesText || '—' }}</dd>
          </div>
          <div>
            <dt>树版本</dt>
            <dd>{{ detail.source_tree_version || '—' }}</dd>
          </div>
          <div>
            <dt>商品上限</dt>
            <dd>{{ detail.product_limit }}</dd>
          </div>
          <div>
            <dt>同步模式</dt>
            <dd>{{ valueLabel(detail.sync_mode) }}</dd>
          </div>
          <div>
            <dt>爬虫账号</dt>
            <dd>
              {{
                detail.account
                  ? `${detail.account.label}（${detail.account.session_status_label}）`
                  : '自动（账号组 ' + (detail.account_group || 'default') + '）'
              }}
            </dd>
          </div>
          <div>
            <dt>评价目标数</dt>
            <dd>{{ detail.review_target }}</dd>
          </div>
        </dl>

        <h3>运行记录</h3>
        <table class="detail__table">
          <thead>
            <tr>
              <th>状态</th>
              <th>账号</th>
              <th>发现</th>
              <th>下载</th>
              <th>成功</th>
              <th>失败</th>
              <th>开始时间</th>
              <th>结束时间</th>
              <th>暂停原因</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="run in detail.runs" :key="run.public_id">
              <td>{{ run.status_label }}</td>
              <td>{{ run.account_label }}</td>
              <td>{{ run.discovered_count }}</td>
              <td>{{ run.downloaded_count }}</td>
              <td>{{ run.succeeded_count }}</td>
              <td>{{ run.failed_count }}</td>
              <td>{{ run.started_at }}</td>
              <td>{{ run.finished_at }}</td>
              <td>{{ run.pause_reason === 'NONE' ? '—' : valueLabel(run.pause_reason) }}</td>
            </tr>
            <tr v-if="(detail.runs || []).length === 0">
              <td colspan="9">尚未运行。</td>
            </tr>
          </tbody>
        </table>

        <h3>运行日志（最近 200 条）</h3>
        <ul class="detail__events">
          <li v-for="event in detail.events" :key="event.created_at + event.code">
            <span class="detail__event-time">{{ event.created_at }}</span>
            <span
              :class="['detail__event-level', `detail__event-level--${event.level.toLowerCase()}`]"
            >
              {{ valueLabel(event.level) }}
            </span>
            <strong v-if="event.code" :title="`事件码：${event.code}`">
              {{ eventCodeLabel(event.code) }}
            </strong>
            <span>{{ event.message }}</span>
          </li>
          <li v-if="(detail.events || []).length === 0">暂无日志。</li>
        </ul>
      </div>
    </div>

    <!-- ======================= 账号 Tab ======================= -->
    <div v-else>
      <p class="account-hint">
        爬虫账号只保存登录后的加密会话 Cookie；密码永远不会被收集或存储。点击「登录」会弹出真实
        Chrome 窗口，请你在窗口内自行完成 Facebook 登录，保存后任务在需要时自动使用该会话。
        <strong>账号身份说明：</strong>Joybuy 按 Facebook 身份识别账号——用哪个 Facebook
        账号登录，进来就是它绑定的 Joybuy 账号。弹出的浏览器与你的日常浏览器互相独立（Cookie
        互不可见），但身份是同一个；若需要独立的爬虫小号，请在登录窗口里换用另一个 Facebook
        账号登录。
      </p>
      <div class="toolbar">
        <button type="button" @click="showAccountCreate = !showAccountCreate">
          {{ showAccountCreate ? '取消新增' : '新增账号' }}
        </button>
        <button type="button" @click="loadAccounts">刷新</button>
      </div>

      <form v-if="showAccountCreate" class="create-form" @submit.prevent="submitAccountCreate">
        <label>
          账号名称
          <input v-model="accountForm.label" required placeholder="例如：FB 主账号" />
        </label>
        <label>
          账号组
          <select v-model="accountForm.account_group" required>
            <option v-if="accountGroups.length === 0" value="default">default（尚无账号组）</option>
            <option v-for="group in accountGroups" :key="group.name" :value="group.name">
              {{ group.name }}（{{ group.account_count }} 个账号）
            </option>
          </select>
        </label>
        <label>
          备注
          <input v-model="accountForm.note" placeholder="用途说明（可选）" />
        </label>
        <button type="submit">创建账号</button>
        <button type="button" @click="showGroupCreate = !showGroupCreate">
          {{ showGroupCreate ? '取消新增账号组' : '新增账号组' }}
        </button>
      </form>

      <form
        v-if="showGroupCreate"
        class="create-form group-form"
        @submit.prevent="submitGroupCreate"
      >
        <label>
          账号组名称
          <input v-model="groupForm.name" required placeholder="例如：数据抓取" />
        </label>
        <label>
          说明
          <input v-model="groupForm.note" placeholder="这一组账号的用途（可选）" />
        </label>
        <button type="submit">创建账号组</button>
        <p class="create-form__account-hint">
          账号组用来把多个账号归到同一池子里轮换；同一个组里的可用账号会被一次抓取轮流使用。
        </p>
      </form>

      <form v-if="editingAccountId" class="create-form" @submit.prevent="submitAccountEdit">
        <p class="create-form__tree-title">编辑账号：{{ editingAccountLabel }}</p>
        <label>
          账号名称
          <input v-model="editForm.label" required />
        </label>
        <label>
          账号组
          <select v-model="editForm.account_group" required>
            <option v-for="group in accountGroups" :key="group.name" :value="group.name">
              {{ group.name }}（{{ group.account_count }} 个账号）
            </option>
          </select>
        </label>
        <label>
          备注
          <input v-model="editForm.note" placeholder="用途说明（可选）" />
        </label>
        <button type="submit">保存</button>
        <button type="button" @click="cancelEditAccount">取消</button>
        <p class="create-form__account-hint">
          改账号组不会动已保存的会话，只是把它挪到另一个轮换池。
        </p>
      </form>

      <AdminTable
        :columns="accountColumns"
        :rows="accounts"
        :loading="loadingAccounts"
        empty-text="暂无爬虫账号。"
      >
        <template #actions="{ row }">
          <button
            v-if="row.raw_session !== 'VALID'"
            type="button"
            @click="accountAction(row, 'login')"
          >
            登录
          </button>
          <button
            v-if="row.raw_session !== 'UNKNOWN'"
            type="button"
            @click="accountAction(row, 'verify')"
          >
            验证会话
          </button>
          <button
            v-if="row.raw_session !== 'UNKNOWN'"
            type="button"
            @click="accountAction(row, 'logout')"
          >
            清除会话
          </button>
          <button
            v-if="row.raw_status === 'PAUSED_RISK_CONTROL'"
            type="button"
            @click="accountAction(row, 'reactivate')"
          >
            解除风控
          </button>
          <button
            v-if="row.raw_status === 'ACTIVE'"
            type="button"
            @click="accountAction(row, 'disable')"
          >
            停用
          </button>
          <button
            v-if="row.raw_status === 'DISABLED'"
            type="button"
            @click="accountAction(row, 'enable')"
          >
            启用
          </button>
          <button type="button" @click="startEditAccount(row)">编辑</button>
          <button type="button" @click="deleteAccount(row)">删除</button>
          <span v-if="row.login_pending" class="account-pending">等待登录…</span>
        </template>
      </AdminTable>
    </div>
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

.tabs__tab--active {
  font-weight: 600;
  border-color: var(--colour-accent, #1a56db);
}

.tabs button {
  min-height: 44px;
  padding: 0 var(--space-4);
  border: 1px solid var(--colour-border-strong);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  cursor: pointer;
  font: inherit;
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

.create-form__tree {
  grid-column: 1 / -1;
}

.create-form__tree-title {
  font-size: var(--font-size-sm);
  margin-bottom: var(--space-2);
}

.create-form__tree-hint {
  font-size: var(--font-size-xs, 0.75rem);
  color: var(--colour-text-soft, #666);
  margin-bottom: var(--space-2);
}

.group-form {
  border-left: 3px solid var(--colour-accent, #1a56db);
  padding-left: var(--space-3);
}

.create-form__account-hint {
  font-size: var(--font-size-xs, 0.75rem);
  color: var(--colour-text-soft, #666);
  margin: calc(var(--space-1) * -1) 0 var(--space-2);
  line-height: 1.5;
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

.detail {
  margin-top: var(--space-5);
  padding: var(--space-4);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
}

.detail__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.detail__head button {
  min-height: 44px;
  padding: 0 var(--space-4);
  border: 1px solid var(--colour-border-strong);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  cursor: pointer;
  font: inherit;
}

.detail__meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
  gap: var(--space-2) var(--space-4);
  margin: var(--space-3) 0;
}

.detail__meta dt {
  font-size: var(--font-size-sm);
  color: var(--colour-text-soft, #666);
}

.detail__table {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: var(--space-4);
}

.detail__table th,
.detail__table td {
  border: 1px solid var(--colour-border);
  padding: var(--space-1) var(--space-2);
  font-size: var(--font-size-sm);
  text-align: left;
}

.detail__events {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 16rem;
  overflow-y: auto;
  font-size: var(--font-size-sm);
}

.detail__events li {
  display: flex;
  gap: var(--space-2);
  padding: var(--space-1) 0;
  border-bottom: 1px dashed var(--colour-border);
}

.detail__event-time {
  color: var(--colour-text-soft, #888);
  white-space: nowrap;
}

.detail__event-level--error {
  color: var(--colour-error);
  font-weight: 600;
}

.detail__event-level--warning {
  color: #b45309;
  font-weight: 600;
}

.account-hint {
  font-size: var(--font-size-sm);
  color: var(--colour-text-soft, #666);
  margin-bottom: var(--space-3);
}

.account-pending {
  color: #b45309;
  font-size: var(--font-size-sm);
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
