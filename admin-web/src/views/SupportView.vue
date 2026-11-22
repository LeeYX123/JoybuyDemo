<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

import AppModal from '@/components/AppModal.vue'
import AppPager from '@/components/AppPager.vue'
import { adminWrite } from '@/composables/useAdminApi'
import { apiRequest } from '@/lib/api'

const TABS = [
  { key: '', label: '全部会话' },
  { key: 'PENDING', label: '待回复' },
  { key: 'PROCESSING', label: '处理中' },
  { key: 'RESOLVED', label: '已解决' },
]

// 需求 21（批次 Y）：客服中心两条并列的来信线——商家来信（原有
// SupportConversation 逻辑不动）+ 买家咨询（SupportChatThread，全站【客服】）。
const GROUP_TABS = [
  { key: 'merchant', label: '商家来信' },
  { key: 'buyer', label: '买家咨询' },
]

const group = ref('merchant')

const state = reactive({
  state: '',
  kind: '',
  q: '',
  items: [],
  loading: false,
  error: '',
})

const current = ref(null)
const currentLoading = ref(false)
const replyText = ref('')
const replyBusy = ref(false)

// 买家咨询：分页列表 + 手动/5s 轮询刷新的会话详情。
const buyerList = reactive({
  items: [],
  page: 1,
  pageSize: 20,
  total: 0,
  hasNext: false,
  loading: false,
  error: '',
})
const buyerCurrent = ref(null)
const buyerCurrentLoading = ref(false)
const buyerReply = ref('')
const buyerBusy = ref(false)

let pollTimer = null
let pollInFlight = false

const groupCounts = computed(() => ({
  merchant: state.items.length,
  buyer: buyerList.total,
}))

const createOpen = ref(false)
const createBusy = ref(false)
const createForm = reactive({ merchantQuery: '', merchantId: '' })
const merchantOptions = ref([])

async function load() {
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page_size: '50' })
    if (state.state) params.set('state', state.state)
    if (state.kind) params.set('kind', state.kind)
    if (state.q.trim()) params.set('q', state.q.trim())
    const payload = await apiRequest(`/support/conversations?${params}`)
    state.items = payload.items
    if (!current.value && payload.items.length) await openConversation(payload.items[0])
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

async function openConversation(row) {
  currentLoading.value = true
  try {
    const payload = await apiRequest(`/support/conversations/${row.id}`)
    current.value = payload.conversation
    replyText.value = ''
    await load()
  } catch (error) {
    state.error = error.message
  } finally {
    currentLoading.value = false
  }
}

async function sendReply() {
  if (!current.value || !replyText.value.trim()) return
  replyBusy.value = true
  try {
    await adminWrite(`/support/conversations/${current.value.id}`, {
      action: 'reply',
      text: replyText.value.trim(),
    })
    replyText.value = ''
    await openConversation({ id: current.value.id })
  } catch (error) {
    state.error = error.message
  } finally {
    replyBusy.value = false
  }
}

async function resolve() {
  if (!current.value) return
  try {
    await adminWrite(`/support/conversations/${current.value.id}`, { action: 'resolve' })
    await openConversation({ id: current.value.id })
  } catch (error) {
    state.error = error.message
  }
}

async function searchMerchants() {
  if (!createForm.merchantQuery.trim()) {
    merchantOptions.value = []
    return
  }
  try {
    const payload = await apiRequest(
      `/notifications/merchants?q=${encodeURIComponent(createForm.merchantQuery.trim())}`,
    )
    merchantOptions.value = payload.items
  } catch {
    merchantOptions.value = []
  }
}

async function submitCreate() {
  createBusy.value = true
  try {
    const payload = await adminWrite('/support/conversations', {
      merchant_id: createForm.merchantId,
    })
    createOpen.value = false
    current.value = payload.conversation
    await load()
  } catch (error) {
    state.error = error.message
  } finally {
    createBusy.value = false
  }
}

function formatTime(value) {
  return value ? value.replace('T', ' ').slice(5, 16) : '—'
}

function pickMerchant(option) {
  createForm.merchantId = option.id
  createForm.merchantQuery = option.name
  merchantOptions.value = []
}

// ---------------------------------------------------------------- 买家咨询
// 列表：GET /support-chat/threads（买家昵称 / 摘要 / 未读 / 时间）。
// 详情：GET /support-chat/threads/<uuid>/messages（打开即清零客服未读）。
// 回复：POST 同路径 body={body}。
// 刷新策略：5s 轮询（列表 + 当前打开的会话）；切到其它分组、页面隐藏或
// 组件卸载即停。手动「刷新」按钮同样可用。
const BUYER_POLL_MS = 5000

async function loadBuyerThreads(page = buyerList.page) {
  buyerList.loading = true
  buyerList.error = ''
  try {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(buyerList.pageSize),
    })
    const payload = await apiRequest(`/support-chat/threads?${params}`)
    buyerList.items = payload.items || []
    buyerList.page = payload.page || page
    buyerList.pageSize = payload.page_size || buyerList.pageSize
    buyerList.total = payload.total || 0
    buyerList.hasNext = Boolean(payload.has_next)
  } catch (error) {
    buyerList.error = error.message
  } finally {
    buyerList.loading = false
  }
}

async function openBuyerThread(row) {
  buyerCurrentLoading.value = true
  buyerList.error = ''
  try {
    const payload = await apiRequest(`/support-chat/threads/${row.id}/messages`)
    buyerCurrent.value = {
      id: row.id,
      buyer: payload.thread?.buyer || row.buyer,
      status: payload.thread?.status || row.status,
      messages: payload.messages || [],
    }
    buyerReply.value = ''
    // 打开会话后服务端已清零未读，本地同步掉角标（不重新整页拉取）。
    const local = buyerList.items.find((item) => item.id === row.id)
    if (local) local.unread = 0
  } catch (error) {
    buyerList.error = error.message
  } finally {
    buyerCurrentLoading.value = false
  }
}

async function sendBuyerReply() {
  if (!buyerCurrent.value || !buyerReply.value.trim()) return
  buyerBusy.value = true
  buyerList.error = ''
  try {
    const payload = await adminWrite(`/support-chat/threads/${buyerCurrent.value.id}/messages`, {
      body: buyerReply.value.trim(),
    })
    buyerCurrent.value.messages.push(payload.message)
    const local = buyerList.items.find((item) => item.id === buyerCurrent.value.id)
    if (local) {
      local.last_message = payload.message.body
      local.last_message_kind = payload.message.sender_kind
      local.last_message_at = payload.message.created_at
      local.unread = 0
    }
    buyerReply.value = ''
  } catch (error) {
    buyerList.error = error.message
  } finally {
    buyerBusy.value = false
  }
}

// 轮询：只在「买家咨询」分组且页面可见时执行；当前打开的会话按最后一条
// 消息 id 判断是否需要替换，避免无谓重渲染/滚动跳动。
async function pollBuyer() {
  if (group.value !== 'buyer' || pollInFlight) return
  if (typeof document !== 'undefined' && document.hidden) return
  pollInFlight = true
  try {
    const params = new URLSearchParams({
      page: String(buyerList.page),
      page_size: String(buyerList.pageSize),
    })
    const payload = await apiRequest(`/support-chat/threads?${params}`)
    const activeId = buyerCurrent.value?.id || ''
    buyerList.items = (payload.items || []).map((item) => {
      const unread = item.id === activeId ? 0 : item.unread
      return { ...item, unread }
    })
    buyerList.total = payload.total || 0
    buyerList.hasNext = Boolean(payload.has_next)
    if (!activeId) return
    const detail = await apiRequest(`/support-chat/threads/${activeId}/messages`)
    const incoming = detail.messages || []
    const previous = buyerCurrent.value.messages || []
    if (
      incoming.length !== previous.length ||
      incoming[incoming.length - 1]?.id !== previous[previous.length - 1]?.id
    ) {
      buyerCurrent.value.messages = incoming
    }
  } catch {
    // 轮询失败静默，手动刷新可重试。
  } finally {
    pollInFlight = false
  }
}

function selectGroup(key) {
  if (group.value === key) return
  group.value = key
  state.error = ''
  buyerList.error = ''
  if (key === 'buyer') {
    buyerCurrent.value = null
    buyerReply.value = ''
    loadBuyerThreads(1)
  } else {
    load()
  }
}

function goBuyerPage(page) {
  loadBuyerThreads(page)
}

function selectBuyerThread(row) {
  openBuyerThread(row)
}

function statusLabel(status) {
  return status === 'CLOSED' ? '已关闭' : '进行中'
}

onMounted(() => {
  load()
  pollTimer = setInterval(pollBuyer, BUYER_POLL_MS)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = null
})
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>客服中心</h1>
        <p>
          接待商家来信并跟进充值、保证金、解封等问题；买家经全站【客服】发来的咨询在「买家咨询」中单独列出，两者不混在一起。
        </p>
      </div>
      <div v-if="group === 'merchant'" class="page-intro__actions">
        <button type="button" class="btn btn--primary" @click="createOpen = true">
          发起客服会话
        </button>
      </div>
    </div>

    <div class="tabs">
      <button
        v-for="tab in GROUP_TABS"
        :key="tab.key"
        type="button"
        :class="{ 'is-active': group === tab.key }"
        @click="selectGroup(tab.key)"
      >
        {{ tab.label }}
        <span class="support-tab-count">{{ groupCounts[tab.key] ?? 0 }}</span>
      </button>
    </div>

    <p
      v-if="group === 'merchant' && state.error"
      class="notice notice--error"
      style="margin-bottom: 14px"
    >
      {{ state.error }}
    </p>

    <p
      v-if="group === 'buyer' && buyerList.error"
      class="notice notice--error"
      style="margin-bottom: 14px"
    >
      {{ buyerList.error }}
    </p>

    <div v-if="group === 'merchant'" class="support-layout">
      <div class="panel support-list">
        <div class="support-filter">
          <select v-model="state.state" @change="load">
            <option v-for="tab in TABS" :key="tab.key" :value="tab.key">{{ tab.label }}</option>
          </select>
          <select v-model="state.kind" @change="load">
            <option value="">全部类型</option>
            <option value="PLATFORM_SUPPORT">平台客服</option>
            <option value="BUYER">买家咨询</option>
          </select>
          <input v-model="state.q" type="search" placeholder="商家名称" @keyup.enter="load" />
        </div>
        <ul class="conversation-list">
          <li
            v-for="row in state.items"
            :key="row.id"
            :class="{ active: current?.id === row.id }"
            @click="openConversation(row)"
          >
            <div class="conversation-item">
              <div>
                <b>{{ row.merchant.name }}</b>
                <span class="cell-sub">
                  {{ row.kind === 'PLATFORM_SUPPORT' ? '平台客服' : '买家咨询' }} ·
                  {{
                    row.state === 'PENDING'
                      ? '待回复'
                      : row.state === 'PROCESSING'
                        ? '处理中'
                        : '已解决'
                  }}
                </span>
              </div>
              <div class="conversation-meta">
                <span>{{ formatTime(row.last_message_at) }}</span>
                <span v-if="row.unread" class="tag tag--warn">{{ row.unread }}</span>
              </div>
            </div>
            <p class="conversation-preview">{{ row.last_message || '（暂无消息）' }}</p>
          </li>
          <li v-if="!state.loading && state.items.length === 0" class="empty-state">暂无会话。</li>
        </ul>
      </div>

      <div class="panel support-chat">
        <p v-if="currentLoading" class="inline-loading">加载中…</p>
        <template v-else-if="current">
          <div class="panel__head">
            <h2>{{ current.merchant.name }}</h2>
            <div class="panel__actions">
              <span class="tag" :class="current.state === 'RESOLVED' ? 'tag--ok' : 'tag--warn'">
                {{
                  current.state === 'RESOLVED'
                    ? '已解决'
                    : current.state === 'PENDING'
                      ? '待回复'
                      : '处理中'
                }}
              </span>
              <button
                type="button"
                class="btn btn--sm"
                :disabled="current.state === 'RESOLVED'"
                @click="resolve"
              >
                标记已解决
              </button>
            </div>
          </div>

          <div v-if="current.product" class="support-product">
            <img v-if="current.product.image" :src="current.product.image" alt="" class="thumb" />
            <div>
              <b>{{ current.product.name }}</b>
              <span class="cell-sub">咨询来源商品 · {{ current.product.id }}</span>
            </div>
          </div>

          <div class="chat-body">
            <div
              v-for="message in current.messages"
              :key="message.id"
              class="chat-bubble"
              :class="message.sender === 'PLATFORM' ? 'mine' : ''"
            >
              <div class="chat-text">{{ message.text }}</div>
              <div class="chat-time">
                {{
                  message.sender === 'PLATFORM'
                    ? '平台'
                    : message.sender === 'MERCHANT'
                      ? '商家'
                      : '买家'
                }}
                · {{ message.author || '—' }} · {{ formatTime(message.created_at) }}
              </div>
            </div>
            <p v-if="!current.messages.length" class="empty-state">还没有消息。</p>
          </div>

          <div class="chat-input">
            <input
              v-model="replyText"
              type="text"
              placeholder="输入回复内容，按 Enter 或点击发送"
              @keyup.enter="sendReply"
            />
            <button
              type="button"
              class="btn btn--primary"
              :disabled="replyBusy || !replyText.trim()"
              @click="sendReply"
            >
              发送
            </button>
          </div>
        </template>
        <p v-else class="empty-state">从左侧选择一个会话。</p>
      </div>
    </div>

    <!-- 买家咨询：全站【客服】入口的买家来信（SupportChatThread）。 -->
    <div v-else class="support-layout">
      <div class="panel support-list">
        <div class="support-filter support-filter--buyer">
          <span>买家经全站【客服】发来的咨询独立成组；打开会话即清零未读。</span>
          <button
            type="button"
            class="btn btn--sm"
            :disabled="buyerList.loading"
            @click="loadBuyerThreads(buyerList.page)"
          >
            {{ buyerList.loading ? '刷新中…' : '刷新（每 5 秒自动）' }}
          </button>
        </div>
        <ul class="conversation-list">
          <li
            v-for="row in buyerList.items"
            :key="row.id"
            :class="{ active: buyerCurrent?.id === row.id }"
            @click="selectBuyerThread(row)"
          >
            <div class="conversation-item">
              <div>
                <b>{{ row.buyer?.display_name || '买家' }}</b>
                <span class="cell-sub">
                  买家咨询 ·
                  {{ row.last_message_kind === 'support' ? '客服已回复' : '等待回复' }} ·
                  {{ statusLabel(row.status) }}
                </span>
              </div>
              <div class="conversation-meta">
                <span>{{ formatTime(row.last_message_at) }}</span>
                <span v-if="row.unread" class="tag tag--warn">{{ row.unread }}</span>
              </div>
            </div>
            <p class="conversation-preview">{{ row.last_message || '（暂无消息）' }}</p>
          </li>
          <li v-if="!buyerList.loading && buyerList.items.length === 0" class="empty-state">
            还没有买家咨询。
          </li>
        </ul>
        <AppPager
          :page="buyerList.page"
          :page-size="buyerList.pageSize"
          :total="buyerList.total"
          :has-next="buyerList.hasNext"
          @change="goBuyerPage"
        />
      </div>

      <div class="panel support-chat">
        <p v-if="buyerCurrentLoading" class="inline-loading">加载中…</p>
        <template v-else-if="buyerCurrent">
          <div class="panel__head">
            <h2>{{ buyerCurrent.buyer?.display_name || '买家' }}</h2>
            <div class="panel__actions">
              <span class="tag tag--ok">{{ statusLabel(buyerCurrent.status) }}</span>
              <span v-if="buyerCurrent.buyer?.email" class="cell-sub">
                {{ buyerCurrent.buyer.email }}
              </span>
            </div>
          </div>

          <div class="chat-body">
            <div
              v-for="message in buyerCurrent.messages"
              :key="message.id"
              class="chat-bubble"
              :class="message.sender_kind === 'support' ? 'mine' : ''"
            >
              <div class="chat-text">{{ message.body }}</div>
              <div class="chat-time">
                {{
                  message.sender_kind === 'support'
                    ? '客服'
                    : buyerCurrent.buyer?.display_name || '买家'
                }}
                · {{ formatTime(message.created_at) }}
              </div>
            </div>
            <p v-if="!buyerCurrent.messages.length" class="empty-state">还没有消息。</p>
          </div>

          <div class="chat-input">
            <input
              v-model="buyerReply"
              type="text"
              maxlength="2000"
              placeholder="回复买家，按 Enter 或点击发送"
              @keyup.enter="sendBuyerReply"
            />
            <button
              type="button"
              class="btn btn--primary"
              :disabled="buyerBusy || !buyerReply.trim()"
              @click="sendBuyerReply"
            >
              发送
            </button>
          </div>
        </template>
        <p v-else class="empty-state">从左侧选择一个买家会话。</p>
      </div>
    </div>

    <AppModal
      v-if="createOpen"
      title="发起客服会话"
      confirm-text="创建"
      :busy="createBusy"
      @cancel="createOpen = false"
      @confirm="submitCreate"
    >
      <div class="field">
        <label for="support-merchant">店铺（输入名称搜索）</label>
        <input
          id="support-merchant"
          v-model="createForm.merchantQuery"
          type="search"
          @input="searchMerchants"
        />
        <div v-if="merchantOptions.length" class="thumb-row">
          <button
            v-for="option in merchantOptions"
            :key="option.id"
            type="button"
            class="btn btn--sm"
            @click="pickMerchant(option)"
          >
            {{ option.name }}
          </button>
        </div>
        <span class="field__hint">每个商家只有一条平台客服会话，重复创建会直接复用。</span>
      </div>
    </AppModal>
  </section>
</template>

<style scoped>
.support-layout {
  display: grid;
  gap: 14px;
  grid-template-columns: 320px 1fr;
  align-items: start;
}

.support-list {
  overflow: hidden;
}

.support-tab-count {
  display: inline-block;
  min-width: 18px;
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 9px;
  background: #eef2f8;
  color: #6a7990;
  font-size: 10px;
  line-height: 18px;
  text-align: center;
}

.tabs button.is-active .support-tab-count {
  background: #dfe9fb;
  color: var(--primary);
}

.support-filter {
  display: grid;
  gap: 8px;
  padding: 12px;
  border-bottom: 1px solid var(--panel-subtle-border);
  background: var(--panel-subtle);
}

.support-filter--buyer {
  grid-template-columns: 1fr auto;
  align-items: center;
  color: #6a7990;
  font-size: 11px;
  line-height: 1.5;
}

.support-filter select,
.support-filter input {
  min-height: 32px;
  padding: 6px 10px;
  border: 1px solid #d7e0ec;
  border-radius: 3px;
  background: #ffffff;
  font-size: 12px;
}

.conversation-list {
  margin: 0;
  padding: 0;
  list-style: none;
  max-height: 620px;
  overflow-y: auto;
}

.conversation-list li {
  padding: 12px 14px;
  border-bottom: 1px solid #eef2f7;
  border-left: 3px solid transparent;
  cursor: pointer;
}

.conversation-list li:hover {
  background: #f7f9fc;
}

.conversation-list li.active {
  background: #eaf1fd;
  border-left-color: var(--primary);
}

.conversation-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
}

.conversation-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #8493a9;
  font-size: 11px;
  white-space: nowrap;
}

.conversation-preview {
  margin: 6px 0 0;
  font-size: 11px;
  color: #8493a9;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.support-chat {
  display: flex;
  flex-direction: column;
  min-height: 480px;
}

.support-product {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 12px 20px 0;
  padding: 10px 12px;
  border: 1px solid var(--panel-subtle-border);
  border-radius: 3px;
  background: var(--panel-subtle);
  font-size: 12px;
}

.chat-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px 20px;
  max-height: 460px;
  overflow-y: auto;
}

.chat-bubble {
  align-self: flex-start;
  max-width: 78%;
}

.chat-bubble.mine {
  align-self: flex-end;
}

.chat-text {
  padding: 9px 12px;
  border: 1px solid #e4eaf2;
  border-radius: 4px;
  background: #f7f9fc;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.chat-bubble.mine .chat-text {
  background: #eaf1fd;
  border-color: #d4e1f7;
}

.chat-time {
  margin-top: 3px;
  font-size: 10px;
  color: #8493a9;
}

.chat-bubble.mine .chat-time {
  text-align: right;
}

.chat-input {
  display: flex;
  gap: 8px;
  padding: 12px 20px 16px;
  border-top: 1px solid var(--panel-subtle-border);
}

.chat-input input {
  flex: 1;
  min-height: 33px;
  padding: 7px 10px;
  border: 1px solid #d7e0ec;
  border-radius: 3px;
  font-size: 12px;
}

@media (max-width: 1000px) {
  .support-layout {
    grid-template-columns: 1fr;
  }
}
</style>
