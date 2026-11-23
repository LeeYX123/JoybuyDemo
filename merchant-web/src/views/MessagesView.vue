<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

import { apiRequest, merchantWrite } from '@/lib/api'

// 「消息中心」两条并列的会话线（需求 19.3-3）：
// - support：商家 ↔ 平台客服（原 SupportConversation，行为保持不变）；
// - buyer：买家 ↔ 商家一对一会话（批次 V2 新接口 /merchant/chats）。
// 两条线共用同一套列表/聊天面板布局，通过 source 适配不同 payload。
const MAX_BUYER_MESSAGE = 2000
const POLL_INTERVAL_MS = 5000

const TABS = [
  { key: 'support', label: '客服会话' },
  { key: 'buyer', label: '买家咨询' },
]

const state = reactive({
  tab: 'support',
  loading: true,
  error: '',
  supportRows: [],
  buyerRows: [],
  activeId: '',
  active: null,
  loadingDetail: false,
  draft: '',
  sending: false,
})

const listEl = ref(null)
let pollTimer = null
let pollInFlight = false

// 移动端（≤768px）单列态：'list' 显示会话列表，'chat' 显示聊天面板；桌面档不受影响。
const mobilePane = ref('list')

const rows = computed(() => (state.tab === 'buyer' ? state.buyerRows : state.supportRows))
const activeEmptyText = computed(() =>
  state.tab === 'buyer' ? '还没有消息，等待买家发起咨询。' : '还没有消息，先打个招呼吧。',
)
const composePlaceholder = computed(() =>
  state.tab === 'buyer' ? '回复买家，Ctrl + Enter 发送' : '输入消息，Ctrl + Enter 发送',
)

const tabCounts = computed(() => ({
  support: state.supportRows.length,
  buyer: state.buyerRows.length,
}))

function normalizeSupportRow(item) {
  return {
    id: item.id,
    source: 'support',
    kind: item.kind,
    peerName: item.peer_name,
    preview: item.last_message || '暂无消息',
    time: item.last_message_at,
    unread: item.unread || 0,
  }
}

function normalizeBuyerRow(item) {
  return {
    id: item.id,
    source: 'buyer',
    kind: 'BUYER_CHAT',
    peerName: item.buyer?.display_name || '买家',
    preview: item.last_message || '暂无消息',
    time: item.last_message_at,
    unread: item.unread || 0,
  }
}

function buyerMessages(payload, row) {
  return (payload.messages || []).map((message) => ({
    id: `buyer-${message.id}`,
    mine: message.sender_kind === 'merchant',
    // 批次 AA：Crisp 人工回复回传为 sender_kind=support —— 既不是"我"也不是买家。
    support: message.sender_kind === 'support',
    author:
      message.sender_kind === 'merchant'
        ? '我'
        : message.sender_kind === 'support'
          ? '平台客服'
          : row?.peerName || '买家',
    text: message.body,
    created_at: message.created_at,
  }))
}

function supportMessages(conversation) {
  return (conversation.messages || []).map((message) => ({
    id: `support-${message.id}`,
    mine: message.sender === 'MERCHANT',
    author: message.author || message.sender,
    text: message.text,
    created_at: message.created_at,
  }))
}

async function loadRows() {
  state.loading = true
  state.error = ''
  try {
    if (state.tab === 'buyer') {
      const payload = await apiRequest('/merchant/chats')
      state.buyerRows = (payload.items || []).map(normalizeBuyerRow)
    } else {
      const payload = await apiRequest('/merchant/conversations')
      state.supportRows = (payload.items || []).map(normalizeSupportRow)
    }
    const stillThere = rows.value.some((row) => row.id === state.activeId)
    if (!stillThere) {
      state.activeId = ''
      state.active = null
      // 客服会话保持原行为（进页自动打开第一条）；买家咨询不自动打开，
      // 否则一进 tab 就会把未读清零，列表上的未读角标永远看不到。
      if (state.tab === 'support' && rows.value.length) {
        await selectRow(rows.value[0].id)
      }
    } else {
      await selectRow(state.activeId, true)
    }
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

async function selectRow(id, silent = false) {
  state.activeId = id
  const row = rows.value.find((item) => item.id === id)
  state.loadingDetail = true
  if (!silent) state.active = null
  try {
    if (state.tab === 'buyer') {
      const payload = await apiRequest(`/merchant/chats/${id}/messages`)
      const thread = payload.thread || {}
      state.active = {
        id,
        source: 'buyer',
        peerName: thread.buyer?.display_name || row?.peerName || '买家',
        kindLabel: '买家咨询',
        state: '',
        product: null,
        messages: buyerMessages(payload, row),
      }
      if (row) row.unread = 0
    } else {
      const payload = await apiRequest(`/merchant/conversations/${id}`)
      const conversation = payload.conversation
      state.active = {
        id,
        source: 'support',
        peerName: conversation.peer_name,
        kindLabel: conversation.kind === 'PLATFORM_SUPPORT' ? '平台客服会话' : '买家商品咨询',
        state: conversation.state,
        product: conversation.product,
        messages: supportMessages(conversation),
      }
      if (row) row.unread = 0
    }
    await scrollToBottom()
  } catch (error) {
    state.error = error.message
  } finally {
    state.loadingDetail = false
  }
}

function openRow(id) {
  mobilePane.value = 'chat'
  selectRow(id)
}

function selectTab(tab) {
  if (state.tab === tab) return
  state.tab = tab
  state.activeId = ''
  state.active = null
  state.draft = ''
  state.error = ''
  mobilePane.value = 'list'
  loadRows()
}

async function refreshActive() {
  await loadRows()
}

async function scrollToBottom() {
  await nextTick()
  if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
}

async function send() {
  const text = state.draft.trim()
  if (!text || !state.active || state.sending) return
  if (state.active.source === 'buyer' && text.length > MAX_BUYER_MESSAGE) {
    state.error = `消息不能超过 ${MAX_BUYER_MESSAGE} 字。`
    return
  }
  state.sending = true
  state.error = ''
  try {
    if (state.active.source === 'buyer') {
      const payload = await merchantWrite(`/merchant/chats/${state.active.id}/messages`, {
        body: text,
      })
      state.active.messages.push({
        id: `buyer-${payload.message.id}`,
        mine: true,
        author: '我',
        text: payload.message.body,
        created_at: payload.message.created_at,
      })
      const row = state.buyerRows.find((item) => item.id === state.active.id)
      if (row) {
        row.preview = payload.message.body
        row.time = payload.message.created_at
        row.unread = 0
      }
    } else {
      const payload = await merchantWrite(`/merchant/conversations/${state.active.id}/messages`, {
        text,
      })
      state.active.messages.push({
        id: `support-${payload.message.id}`,
        mine: true,
        author: payload.message.author || '我',
        text: payload.message.text,
        created_at: payload.message.created_at,
      })
      const row = state.supportRows.find((item) => item.id === state.active.id)
      if (row) {
        row.preview = payload.message.text
        row.time = payload.message.created_at
      }
    }
    state.draft = ''
    await scrollToBottom()
  } catch (error) {
    state.error = error.message
  } finally {
    state.sending = false
  }
}

function onKeydown(event) {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    event.preventDefault()
    send()
  }
}

function fmtTime(value) {
  if (!value) return ''
  return value.slice(5, 16).replace('T', ' ')
}

function fmtFull(value) {
  if (!value) return ''
  return value.slice(0, 16).replace('T', ' ')
}

// 5 秒轮询（两个 tab 都轮）：列表未读/摘要 + 当前会话新消息（服务器无 after 参数，
// 按最后一条 id 判断是否需要替换，避免无谓重渲染/跳动）。
// 批次 AA：客服会话 tab 也轮询 —— 后端在打开会话时顺带拉取 Crisp 人工回复
// （线程节流 20s），因此平台客服在 Crisp Inbox 的回复 5s 内即可出现在商家端。
async function pollBuyer() {
  if (state.tab !== 'buyer' || pollInFlight) return
  if (typeof document !== 'undefined' && document.hidden) return
  pollInFlight = true
  try {
    const payload = await apiRequest('/merchant/chats')
    const nextRows = (payload.items || []).map(normalizeBuyerRow)
    if (state.activeId) {
      // 打开中的会话服务端已清零商家未读，轮询不应把角标又画回来。
      const current = nextRows.find((row) => row.id === state.activeId)
      if (current) current.unread = 0
    }
    state.buyerRows = nextRows
    if (!state.activeId || state.active?.source !== 'buyer') return
    const detail = await apiRequest(`/merchant/chats/${state.activeId}/messages`)
    const row = state.buyerRows.find((item) => item.id === state.activeId)
    const incoming = buyerMessages(detail, row)
    const previous = state.active.messages
    const lastIncoming = incoming[incoming.length - 1]?.id || ''
    const lastPrevious = previous[previous.length - 1]?.id || ''
    if (lastIncoming !== lastPrevious) {
      state.active.messages = incoming
      if (row) row.unread = 0
      await scrollToBottom()
    }
  } catch {
    // 轮询失败静默；手动「刷新」可重试。
  } finally {
    pollInFlight = false
  }
}

async function pollSupport() {
  if (state.tab !== 'support' || pollInFlight) return
  if (typeof document !== 'undefined' && document.hidden) return
  pollInFlight = true
  try {
    const payload = await apiRequest('/merchant/conversations')
    const nextRows = (payload.items || []).map(normalizeSupportRow)
    if (state.activeId) {
      const current = nextRows.find((row) => row.id === state.activeId)
      if (current) current.unread = 0
    }
    state.supportRows = nextRows
    if (!state.activeId || state.active?.source !== 'support') return
    // GET 详情同时触发后端拉取 Crisp 人工回复（线程节流 20s），因此每轮都请求。
    const detail = await apiRequest(`/merchant/conversations/${state.activeId}`)
    const incoming = supportMessages(detail.conversation || {})
    const lastIncoming = incoming[incoming.length - 1]?.id || ''
    const lastPrevious = state.active.messages[state.active.messages.length - 1]?.id || ''
    if (lastIncoming !== lastPrevious) {
      state.active.messages = incoming
      const row = state.supportRows.find((item) => item.id === state.activeId)
      if (row) row.unread = 0
      await scrollToBottom()
    }
  } catch {
    // 轮询失败静默；手动「刷新」可重试。
  } finally {
    pollInFlight = false
  }
}

function pollActiveTab() {
  if (state.tab === 'support') {
    pollSupport()
  } else {
    pollBuyer()
  }
}

onMounted(() => {
  loadRows()
  pollTimer = setInterval(pollActiveTab, POLL_INTERVAL_MS)
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
        <h1>消息中心</h1>
        <p>
          客服中心用于充值与保证金沟通；买家一对一咨询在「买家咨询」中单独列出，两者不混在一起。
        </p>
      </div>
    </div>

    <div class="tabs">
      <button
        v-for="tab in TABS"
        :key="tab.key"
        type="button"
        :class="{ 'is-active': state.tab === tab.key }"
        @click="selectTab(tab.key)"
      >
        {{ tab.label }}
        <span class="tab-count">{{ tabCounts[tab.key] ?? 0 }}</span>
      </button>
      <button type="button" class="tabs__refresh" :disabled="state.loading" @click="refreshActive">
        {{ state.tab === 'buyer' ? '刷新（每 5 秒自动）' : '刷新' }}
      </button>
    </div>

    <p v-if="state.error" class="notice notice--error">{{ state.error }}</p>

    <div class="chat-shell" :class="{ 'is-chat-pane': mobilePane === 'chat' }">
      <aside class="chat-list">
        <p v-if="state.loading" class="inline-loading">加载中…</p>
        <button
          v-for="row in rows"
          :key="row.id"
          type="button"
          class="chat-list__item"
          :class="{ 'is-active': row.id === state.activeId }"
          @click="openRow(row.id)"
        >
          <span
            class="chat-list__avatar"
            :class="{
              'is-support': row.source === 'support' && row.kind === 'PLATFORM_SUPPORT',
              'is-buyer': row.source === 'buyer',
            }"
          >
            {{ row.source === 'buyer' ? '买' : row.kind === 'PLATFORM_SUPPORT' ? '客' : '买' }}
          </span>
          <span class="chat-list__main">
            <span class="chat-list__top">
              <b>{{ row.peerName }}</b>
              <small>{{ fmtTime(row.time) }}</small>
            </span>
            <span class="chat-list__preview">{{ row.preview }}</span>
          </span>
          <span v-if="row.unread" class="chat-list__badge">{{ row.unread }}</span>
        </button>
        <p v-if="!state.loading && !rows.length" class="empty-state">
          {{ state.tab === 'buyer' ? '还没有买家咨询。' : '还没有会话。' }}
        </p>
      </aside>

      <section class="chat-panel">
        <template v-if="state.active">
          <header class="chat-panel__head">
            <div class="chat-panel__head-left">
              <button
                type="button"
                class="chat-back"
                aria-label="返回会话列表"
                @click="mobilePane = 'list'"
              >
                ← 返回
              </button>
              <strong>{{ state.active.peerName }}</strong>
              <span v-if="state.active.state" class="tag">{{ state.active.state }}</span>
            </div>
            <span class="cell-sub">{{ state.active.kindLabel }}</span>
          </header>

          <div v-if="state.active.product" class="chat-product">
            <img v-if="state.active.product.image" :src="state.active.product.image" alt="" />
            <div class="chat-product__info">
              <span class="cell-sub">咨询商品</span>
              <strong>{{ state.active.product.name }}</strong>
              <span class="cell-sub">
                {{ state.active.product.category }} ｜ ¥ {{ state.active.product.price }} ｜
                <span class="mono">{{ state.active.product.id.slice(0, 8) }}…</span>
              </span>
            </div>
          </div>

          <div ref="listEl" class="chat-messages">
            <p v-if="state.loadingDetail" class="inline-loading">加载中…</p>
            <div
              v-for="message in state.active.messages"
              :key="message.id"
              class="chat-bubble"
              :class="{ 'is-mine': message.mine, 'is-support': message.support }"
            >
              <div class="chat-bubble__meta">
                {{ message.author }} · {{ fmtFull(message.created_at) }}
              </div>
              <div class="chat-bubble__text">{{ message.text }}</div>
            </div>
            <p v-if="!state.active.messages?.length" class="empty-state">
              {{ activeEmptyText }}
            </p>
          </div>

          <footer class="chat-compose">
            <textarea
              v-model="state.draft"
              rows="3"
              :maxlength="state.active.source === 'buyer' ? MAX_BUYER_MESSAGE : undefined"
              :placeholder="composePlaceholder"
              @keydown="onKeydown"
            />
            <div class="chat-compose__actions">
              <span class="hint-text">
                <template v-if="state.active.source === 'buyer'">
                  {{ state.draft.length }}/{{ MAX_BUYER_MESSAGE }} · Ctrl + Enter 发送
                </template>
                <template v-else>Ctrl + Enter 发送</template>
              </span>
              <button
                type="button"
                class="btn btn--primary"
                :disabled="state.sending || !state.draft.trim()"
                @click="send"
              >
                {{ state.sending ? '发送中…' : '发送' }}
              </button>
            </div>
          </footer>
        </template>
        <p v-else class="empty-state">选择左侧会话开始沟通。</p>
      </section>
    </div>
  </section>
</template>

<style scoped>
.tab-count {
  margin-left: 6px;
  font-size: 11px;
  color: var(--muted);
}

/* tab 行 + 刷新按钮：一行放下，窄屏可横滚。 */
.tabs {
  flex-wrap: nowrap;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  align-items: center;
}

.tabs::-webkit-scrollbar {
  display: none;
}

.tabs__refresh {
  flex: none;
  margin-left: auto;
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: 5px;
  background: #ffffff;
  color: #505765;
  font-size: 12px;
  line-height: 1.6;
  white-space: nowrap;
  cursor: pointer;
}

.tabs__refresh:hover:not(:disabled) {
  border-color: var(--red);
  color: var(--red);
}

.tabs__refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.chat-shell {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 16px;
  height: calc(100vh - 250px);
  min-height: 480px;
  margin-top: 16px;
}

.chat-list {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow-y: auto;
  padding: 8px;
}

.chat-list__item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  border: none;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  text-align: left;
}

.chat-list__item:hover {
  background: #f7f8fa;
}

.chat-list__item.is-active {
  background: var(--red-soft);
}

.chat-list__avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: #e8edf5;
  color: #4a5a72;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  flex: none;
}

.chat-list__avatar.is-support {
  background: var(--red);
  color: #fff;
}

/* 买家咨询用绿色区分平台客服（红），避免两条线混淆。 */
.chat-list__avatar.is-buyer {
  background: #e7f3ec;
  color: #1f6b45;
}

.chat-list__main {
  flex: 1;
  min-width: 0;
}

.chat-list__top {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
}

.chat-list__top small {
  color: var(--muted);
  font-size: 11px;
}

.chat-list__preview {
  display: block;
  font-size: 12px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-list__badge {
  background: var(--red);
  color: #fff;
  border-radius: 10px;
  font-size: 11px;
  padding: 1px 6px;
}

.chat-panel {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.chat-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--line);
}

.chat-panel__head-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.chat-panel__head-left strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 移动端返回按钮：桌面（>768px）恒隐藏，桌面行为不变。 */
.chat-back {
  display: none;
  flex: none;
  align-items: center;
  min-height: 34px;
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #ffffff;
  color: #505765;
  font-size: 13px;
  cursor: pointer;
}

.chat-back:hover {
  border-color: var(--red);
  color: var(--red);
}

.chat-product {
  display: flex;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--line);
  background: #fafbfd;
}

.chat-product img {
  width: 52px;
  height: 52px;
  object-fit: contain;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 6px;
}

.chat-product__info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chat-bubble {
  max-width: 72%;
  align-self: flex-start;
}

.chat-bubble.is-mine {
  align-self: flex-end;
}

.chat-bubble__meta {
  font-size: 11px;
  color: var(--muted);
  margin-bottom: 4px;
}

.chat-bubble.is-mine .chat-bubble__meta {
  text-align: right;
}

.chat-bubble__text {
  background: #f2f4f7;
  padding: 10px 12px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.chat-bubble.is-mine .chat-bubble__text {
  background: var(--red);
  color: #fff;
}

/* 批次 AA：平台客服（Crisp 人工回复）气泡——浅红底 + 左侧色条，区别于「我」和买家。 */
.chat-bubble.is-support .chat-bubble__text {
  background: #fff5f4;
  border-left: 3px solid var(--red);
}

.chat-bubble.is-support .chat-bubble__meta {
  color: var(--red);
  font-weight: 600;
}

.chat-compose {
  border-top: 1px solid var(--line);
  padding: 12px 16px;
}

.chat-compose textarea {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 8px 10px;
  font-family: inherit;
  font-size: 13px;
  resize: vertical;
}

.chat-compose__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
}

/* ≤960px：双栏收窄但不溢出（列表 240px，聊天面板弹性收窄）。 */
@media (max-width: 960px) {
  .chat-shell {
    grid-template-columns: minmax(0, 240px) minmax(0, 1fr);
    gap: 12px;
  }

  .chat-list,
  .chat-panel {
    min-width: 0;
  }
}

/* ≤768px：单列 + 组件内切换（默认会话列表，点会话进聊天，返回按钮回列表）。 */
@media (max-width: 768px) {
  .chat-shell {
    grid-template-columns: 1fr;
    height: calc(100vh - 230px);
    min-height: 420px;
  }

  .chat-back {
    display: inline-flex;
  }

  .chat-panel {
    display: none;
  }

  .chat-shell.is-chat-pane .chat-list {
    display: none;
  }

  .chat-shell.is-chat-pane .chat-panel {
    display: flex;
  }

  .chat-bubble {
    max-width: 86%;
  }

  .chat-compose__actions {
    gap: 8px;
  }
}
</style>
