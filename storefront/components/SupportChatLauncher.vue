<script setup>
// 全站【客服】入口（需求 21 / 批次 Y；需求 23.3 / 批次 AB 按真站重做）。
//
// 右下角图标 + 文字按钮，点击展开浮层面板：先看到会话列表（现阶段只有一条
// 【客户服务】），点进去是会话视图 —— 居中客服头像 + 欢迎语 + 三条常见问题
// （点击即作为消息发送）+【发送订单】+ 输入框（发送图标在框内右侧）。
//
// 真站实测（var/cs_sync_panel_20261123/findings.md C2/C3）：面板 375 宽、
// 80% 高（max 720）、right 84 / bottom 104.5、#F5F6FA 底、8px 圆角、
// #F0F1F2 边框、0 2px 16px rgba(0,0,0,.078)、z-index 1200；header 60px 白底，
// 左【清除】16 / 中【客服】24px700 / 右【×】16；列表项 padding 12×16、头像 60
// 圆、标题 16/600 #1A1A1A、时间 12 #505259、摘要 14/500 两行截断、
// 未读 16px #E1251B、hover rgba(0,16,71,.102)。
// 会话内首屏真站未实测（需登录），按需求 23.3 + 用户描述实现（推定）。
//
// 数据仍走买家 ↔ 平台客服接口 /api/v1/account/support-chat/*（批次 X）；
// 订单来自 /api/v1/orders。保留未登录引导、5s 轮询（进入会话视图才启用）、
// 2000 字上限、乐观发送、失败重试、发送中禁用。
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { navigateTo, useRoute } from '#imports'

import { useBuyerAuth } from '../composables/useBuyerAuth'
import { useLocale } from '../composables/useLocale'
import { noAutofill } from '../utils/noAutofill'

const MAX_LENGTH = 2000
const MAX_ORDERS = 3
const POLL_INTERVAL_MS = 5000
const TITLE_ID = 'support-chat-title'
const ORDER_TITLE_ID = 'support-chat-order-title'
const INPUT_ID = 'support-chat-input'
const BASE = '/api/v1/account/support-chat'
const ORDERS_URL = '/api/v1/orders'

const ORDER_STATUS_KEYS = {
  PENDING_PAYMENT: 'orders.statusPendingPayment',
  PROCESSING: 'orders.statusProcessing',
  SHIPPED: 'orders.statusShipped',
  COMPLETED: 'orders.statusCompleted',
  CANCELED: 'orders.statusCanceled',
}

const { t, localeCode } = useLocale()
const { isAuthenticated } = useBuyerAuth()
const route = useRoute()

const open = ref(false)
// 'list' = 会话列表（默认首屏），'conversation' = 会话视图。
const view = ref('list')
const threadId = ref('')
const messages = ref([])
const loading = ref(false)
const loadError = ref(false)
const authRequired = ref(false)
const sending = ref(false)
const composeError = ref('')
const draft = ref('')

// 列表卡片元信息：最后一条正文/时间、未读数（来自 POST /thread 的 payload）。
const lastPreview = ref('')
const lastMessageAt = ref('')
const unreadCount = ref(0)
// 轮询游标独立于 messages：点【清除】清屏后游标不回退，否则下一轮又会把
// 后端历史拉回来。
const cursor = ref('')
const cleared = ref(false)

// 【发送订单】弹层。
const ordersOpen = ref(false)
const ordersLoading = ref(false)
const ordersError = ref(false)
const orders = ref([])
const selectedOrders = ref([])

const listEl = ref(null)
const closeButton = ref(null)
const inputEl = ref(null)

let pollTimer = null
let pollInFlight = false

const faqs = computed(() => [t('support.faq1'), t('support.faq2'), t('support.faq3')])

const showFaq = computed(
  () =>
    view.value === 'conversation' &&
    !messages.value.length &&
    !loading.value &&
    !loadError.value &&
    !authRequired.value,
)

const canClear = computed(() => view.value === 'conversation' && messages.value.length > 0)

const canSend = computed(
  () =>
    Boolean(draft.value.trim()) &&
    draft.value.trim().length <= MAX_LENGTH &&
    !sending.value &&
    !loading.value &&
    !loadError.value &&
    !authRequired.value &&
    Boolean(threadId.value),
)

const listPreview = computed(() => lastPreview.value || t('support.listPreview'))

function loginUrl() {
  const next = route.fullPath || '/'
  return `/auth/login?next=${encodeURIComponent(next)}`
}

async function csrfToken() {
  try {
    const session = await $fetch('/api/v1/auth/buyer/session', {
      credentials: 'include',
      ignoreResponseError: true,
    })
    return session?.csrf_token || ''
  } catch {
    return ''
  }
}

async function postJson(path, body) {
  const token = await csrfToken()
  return $fetch(`${BASE}${path}`, {
    method: 'POST',
    body,
    credentials: 'include',
    headers: { 'X-CSRFToken': token, 'Content-Type': 'application/json' },
    ignoreResponseError: true,
  })
}

async function getJson(path) {
  return $fetch(`${BASE}${path}`, { credentials: 'include', ignoreResponseError: true })
}

function handleAccessError(payload) {
  if (payload?.error?.code === 'BUYER_AUTH_REQUIRED') {
    authRequired.value = true
    stopPolling()
    return true
  }
  return false
}

function makeClientId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `local-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function serverMessage(raw, clientId = '') {
  return {
    key: `srv-${raw.id}`,
    clientId,
    serverId: raw.id,
    mine: raw.sender_kind === 'buyer',
    body: raw.body || '',
    created_at: raw.created_at || '',
    pending: false,
    failed: false,
  }
}

function messageIdentity(message) {
  if (message.serverId) return `srv:${message.serverId}`
  return message.clientId ? `cli:${message.clientId}` : ''
}

function removeMessage(message) {
  messages.value = messages.value.filter((item) => item !== message)
}

function pruneDuplicateMessages() {
  const seen = new Set()
  const next = []
  for (const message of messages.value) {
    const identity = messageIdentity(message)
    if (identity && seen.has(identity)) continue
    if (identity) seen.add(identity)
    next.push(message)
  }
  if (next.length !== messages.value.length) messages.value = next
}

// 轮询/POST 返回同一条消息时只保留一条：优先「认领」本地乐观气泡（原地补
// serverId），绝不额外 append。
function applyServerMessage(raw) {
  if (raw?.id === undefined || raw?.id === null) return false
  if (messages.value.some((message) => message.serverId === raw.id)) return false
  const optimistic =
    raw.sender_kind === 'buyer'
      ? messages.value.find(
          (message) =>
            !message.serverId &&
            Boolean(message.clientId) &&
            message.mine &&
            message.body === (raw.body || ''),
        )
      : null
  if (optimistic) {
    Object.assign(optimistic, serverMessage(raw, optimistic.clientId))
  } else {
    messages.value.push(serverMessage(raw))
  }
  pruneDuplicateMessages()
  return true
}

function mergeMessages(incoming) {
  if (!Array.isArray(incoming) || !incoming.length) return false
  let changed = false
  for (const raw of incoming) changed = applyServerMessage(raw) || changed
  return changed
}

function bumpCursor(value) {
  if (!value) return
  const next = Date.parse(value)
  if (Number.isNaN(next)) return
  const current = Date.parse(cursor.value)
  if (!cursor.value || Number.isNaN(current) || next >= current) cursor.value = value
}

function syncCursor() {
  let bestTs = 0
  let bestValue = ''
  for (const message of messages.value) {
    if (!message.created_at) continue
    const ts = Date.parse(message.created_at)
    if (Number.isNaN(ts)) continue
    if (ts >= bestTs) {
      bestTs = ts
      bestValue = message.created_at
    }
  }
  if (bestValue) cursor.value = bestValue
}

// 未读数只取 POST /thread（get-or-create）那一刻的值：GET /messages 会顺手
// 把买家未读清零，用它的 payload 覆盖会把列表红点抹掉。
function applyThreadMeta(thread, { withUnread = false } = {}) {
  if (!thread) return
  if (thread.last_message_at) lastMessageAt.value = thread.last_message_at
  if (withUnread && Number.isFinite(Number(thread.buyer_unread))) {
    unreadCount.value = Number(thread.buyer_unread) || 0
  }
}

function applyPreviewFromMessages() {
  const last = [...messages.value]
    .reverse()
    .find((message) => message.created_at && !message.pending && !message.failed)
  if (last) {
    lastPreview.value = last.body
    lastMessageAt.value = last.created_at
  }
}

async function init() {
  threadId.value = ''
  messages.value = []
  cursor.value = ''
  cleared.value = false
  lastPreview.value = ''
  lastMessageAt.value = ''
  unreadCount.value = 0
  loading.value = true
  loadError.value = false
  authRequired.value = false
  composeError.value = ''
  try {
    // 幂等 get-or-create：同一买家永远拿到同一个平台客服会话。
    const created = await postJson('/thread', {})
    if (created?.error) {
      if (!handleAccessError(created)) loadError.value = true
      return
    }
    const id = created?.thread?.id || ''
    if (!id) {
      loadError.value = true
      return
    }
    threadId.value = id
    applyThreadMeta(created.thread, { withUnread: true })
    const payload = await getJson('/messages')
    if (payload?.error) {
      if (!handleAccessError(payload)) loadError.value = true
      return
    }
    messages.value = (payload?.messages || []).map((raw) => serverMessage(raw))
    applyThreadMeta(payload?.thread)
    applyPreviewFromMessages()
    syncCursor()
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

// 重新拉整段历史（【清除】后从列表再次进入会话时用，Q4：只清显示不删库）。
async function reloadHistory() {
  if (!threadId.value) return
  try {
    const payload = await getJson('/messages')
    if (payload?.error) {
      handleAccessError(payload)
      return
    }
    messages.value = (payload?.messages || []).map((raw) => serverMessage(raw))
    applyThreadMeta(payload?.thread)
    applyPreviewFromMessages()
    syncCursor()
  } catch {
    // 拉取失败保持当前视图，下一次轮询/重进再试。
  }
}

async function deliver(message) {
  message.pending = true
  message.failed = false
  composeError.value = ''
  try {
    const payload = await postJson('/messages', { body: message.body })
    if (payload?.error) {
      handleAccessError(payload)
      if (!message.serverId) {
        message.pending = false
        message.failed = true
      }
      composeError.value = t('support.sendFailed')
      return
    }
    const raw = payload?.message
    if (raw?.id !== undefined && raw?.id !== null) {
      const existing = messages.value.find((item) => item.serverId === raw.id)
      const target = messages.value.find((item) => item.clientId === message.clientId) || message
      if (existing && existing !== target) {
        removeMessage(target)
        Object.assign(existing, serverMessage(raw, existing.clientId))
      } else {
        Object.assign(target, serverMessage(raw, target.clientId))
      }
      pruneDuplicateMessages()
      bumpCursor(raw.created_at || message.created_at)
      lastPreview.value = message.body
      lastMessageAt.value = raw.created_at || message.created_at || lastMessageAt.value
    } else if (!message.serverId) {
      message.pending = false
    }
  } catch {
    if (!message.serverId) {
      message.pending = false
      message.failed = true
    }
    composeError.value = t('support.sendFailed')
  }
}

// FAQ / 订单文本都走这里：与手动输入完全同一条发送链路（乐观气泡 + 失败重试）。
async function sendText(rawBody) {
  const body = String(rawBody || '').trim()
  if (!body || !threadId.value || sending.value) return
  if (body.length > MAX_LENGTH) {
    composeError.value = t('support.tooLong', { max: MAX_LENGTH })
    return
  }
  sending.value = true
  const clientId = makeClientId()
  const optimistic = {
    key: `local-${clientId}`,
    clientId,
    serverId: null,
    mine: true,
    body,
    created_at: new Date().toISOString(),
    pending: true,
    failed: false,
  }
  messages.value.push(optimistic)
  await scrollToBottom()
  try {
    await deliver(optimistic)
  } finally {
    sending.value = false
  }
}

async function send() {
  if (!canSend.value) return
  const body = draft.value.trim()
  draft.value = ''
  await sendText(body)
}

async function retry(message) {
  if (!message || sending.value || !threadId.value) return
  sending.value = true
  try {
    await deliver(message)
  } finally {
    sending.value = false
  }
}

async function poll() {
  if (!threadId.value || pollInFlight || typeof document === 'undefined' || document.hidden) return
  pollInFlight = true
  try {
    const after = cursor.value
    const query = after ? `?after=${encodeURIComponent(after)}` : ''
    const payload = await getJson(`/messages${query}`)
    if (payload?.error) {
      handleAccessError(payload)
      return
    }
    const incoming = payload?.messages || []
    if (mergeMessages(incoming)) {
      const last = incoming[incoming.length - 1]
      if (last) {
        bumpCursor(last.created_at)
        lastPreview.value = last.body || lastPreview.value
        lastMessageAt.value = last.created_at || lastMessageAt.value
      }
      await scrollToBottom()
    } else if (incoming.length) {
      bumpCursor(incoming[incoming.length - 1].created_at)
    }
    if (payload?.thread) applyThreadMeta(payload.thread)
  } catch {
    // 轮询失败静默，下一轮再试。
  } finally {
    pollInFlight = false
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(poll, POLL_INTERVAL_MS)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function scrollToBottom() {
  await nextTick()
  if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
}

function formatTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  try {
    return new Intl.DateTimeFormat(localeCode.value, {
      hour: '2-digit',
      minute: '2-digit',
    }).format(date)
  } catch {
    return ''
  }
}

// ---------------------------- 视图切换 ----------------------------

async function enterConversation() {
  if (authRequired.value || loadError.value) return
  view.value = 'conversation'
  composeError.value = ''
  if (cleared.value) await reloadHistory()
  cleared.value = false
  startPolling()
  await scrollToBottom()
  await nextTick()
  inputEl.value?.focus?.()
}

function backToList() {
  stopPolling()
  applyPreviewFromMessages()
  view.value = 'list'
}

// Q4：【清除】只清用户侧显示——本地把已渲染消息清空，游标不回退（轮询不会
// 把历史重新拉回来）；不调后端、不删数据库。后端当前没有买家侧清除接口。
// 从列表再次进入会话时会重新拉历史。
function clearConversation() {
  if (!canClear.value) return
  messages.value = []
  lastPreview.value = ''
  composeError.value = ''
  cleared.value = true
}

// ---------------------------- 发送订单 ----------------------------

// 2026-11-27 全站编号改造：订单号 JYO+YYYYMMDD+6 位，整号展示（截前 8 位会撞车）。
function orderNumberLabel(value) {
  return String(value || '').toUpperCase()
}

function orderAmount(order) {
  const numeric = Number(order?.total)
  if (!Number.isFinite(numeric)) return ''
  try {
    // 全站统一 $ 符号（2026-11-27 站点规则），不再按订单货币切换符号。
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(numeric)
  } catch {
    return String(order?.total ?? '')
  }
}

function orderStateLabel(order) {
  return t(ORDER_STATUS_KEYS[order?.state] || 'orders.statusProcessing')
}

function orderLine(order) {
  return t('support.orderMessage', {
    id: order.public_id,
    amount: orderAmount(order),
    status: orderStateLabel(order),
  })
}

async function loadOrders() {
  ordersLoading.value = true
  ordersError.value = false
  try {
    const payload = await $fetch(ORDERS_URL, {
      credentials: 'include',
      ignoreResponseError: true,
    })
    if (payload?.error || !Array.isArray(payload?.orders)) {
      ordersError.value = true
      return
    }
    orders.value = payload.orders.slice(0, MAX_ORDERS)
  } catch {
    ordersError.value = true
  } finally {
    ordersLoading.value = false
  }
}

function openOrders() {
  if (!threadId.value || sending.value) return
  ordersOpen.value = true
  selectedOrders.value = []
  ordersError.value = false
  if (!orders.value.length) loadOrders()
}

function closeOrders() {
  ordersOpen.value = false
  selectedOrders.value = []
}

function toggleOrder(publicId) {
  if (selectedOrders.value.includes(publicId)) {
    selectedOrders.value = selectedOrders.value.filter((id) => id !== publicId)
    return
  }
  selectedOrders.value = [...selectedOrders.value, publicId]
}

async function confirmOrders() {
  if (!selectedOrders.value.length || sending.value) return
  const chosen = orders.value.filter((order) => selectedOrders.value.includes(order.public_id))
  if (!chosen.length) return
  const body = chosen.map(orderLine).join('\n')
  closeOrders()
  await sendText(body)
}

// ---------------------------- 开关与键盘 ----------------------------

// 未登录：先去登录页，成功后由 AuthForm 的 ?next= 约定回到当前页。
function toggle() {
  if (!isAuthenticated.value) {
    open.value = false
    navigateTo(loginUrl())
    return
  }
  open.value = !open.value
}

function close() {
  open.value = false
}

function onKeydown(event) {
  if (event.key !== 'Escape') return
  if (ordersOpen.value) {
    event.preventDefault()
    closeOrders()
    return
  }
  if (open.value) {
    event.preventDefault()
    close()
  }
}

// Enter 发送、Shift+Enter 换行；输入法合成中的 Enter 不发送。
function onComposerKeydown(event) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  send()
}

function onVisibilityChange() {
  if (typeof document !== 'undefined' && !document.hidden && open.value) {
    if (view.value === 'conversation') poll()
  }
}

watch(open, async (isOpen) => {
  if (typeof document === 'undefined') return
  if (isOpen) {
    view.value = 'list'
    await nextTick()
    closeButton.value?.focus?.()
    init()
    return
  }
  stopPolling()
  threadId.value = ''
  messages.value = []
  cursor.value = ''
  cleared.value = false
  lastPreview.value = ''
  lastMessageAt.value = ''
  unreadCount.value = 0
  loading.value = false
  loadError.value = false
  authRequired.value = false
  composeError.value = ''
  draft.value = ''
  ordersOpen.value = false
  orders.value = []
  selectedOrders.value = []
  ordersError.value = false
  ordersLoading.value = false
  view.value = 'list'
})

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  document.addEventListener('visibilitychange', onVisibilityChange)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  document.removeEventListener('visibilitychange', onVisibilityChange)
  stopPolling()
})
</script>

<template>
  <div class="support-chat">
    <button
      class="support-chat__launcher"
      type="button"
      data-testid="support-chat-launcher"
      :aria-expanded="open"
      aria-controls="support-chat-panel"
      :aria-label="t('support.launcher')"
      @click="toggle"
    >
      <!-- 真站右下角【客服】图标（joybuy-icons U+E601）：头戴式耳机 + 笑脸。 -->
      <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
        <path
          d="M4.2 13.6v-1.2a7.8 7.8 0 0 1 15.6 0v1.2"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
        />
        <path
          d="M4.2 13.2a1.6 1.6 0 0 1 3.2 0v4.2a1.6 1.6 0 0 1-3.2 0v-4.2Zm12.4 0a1.6 1.6 0 0 1 3.2 0v4.2a1.6 1.6 0 0 1-3.2 0v-4.2Z"
          fill="currentColor"
        />
        <path
          d="M9.3 14.2c1.6 1.7 3.8 1.7 5.4 0"
          fill="none"
          stroke="currentColor"
          stroke-width="1.7"
          stroke-linecap="round"
        />
      </svg>
      <span class="support-chat__label">{{ t('support.launcher') }}</span>
    </button>

    <Transition name="support-chat-pop">
      <section
        v-if="open"
        id="support-chat-panel"
        class="support-chat__panel"
        role="dialog"
        aria-modal="false"
        :aria-labelledby="TITLE_ID"
        data-testid="support-chat-panel"
      >
        <!-- 真站 header：60px 白底，左【清除】/ 中【客服】24px700 / 右【×】。 -->
        <header class="support-chat__head">
          <button
            class="support-chat__icon-btn support-chat__icon-btn--left"
            type="button"
            data-testid="support-chat-clear"
            :disabled="!canClear"
            :aria-label="t('support.clear')"
            :title="t('support.clear')"
            @click="clearConversation"
          >
            <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
              <path
                d="M4.6 15.2 13.1 6.7a2 2 0 0 1 2.8 0l1.4 1.4a2 2 0 0 1 0 2.8l-8.5 8.5H4.6v-4.2Z"
                fill="none"
                stroke="currentColor"
                stroke-width="1.6"
                stroke-linejoin="round"
              />
              <path d="M13 20h6.4" fill="none" stroke="currentColor" stroke-width="1.6" />
            </svg>
          </button>
          <h2 :id="TITLE_ID" class="support-chat__title">{{ t('support.headerTitle') }}</h2>
          <button
            ref="closeButton"
            class="support-chat__icon-btn support-chat__icon-btn--right"
            type="button"
            data-testid="support-chat-close"
            :aria-label="t('support.close')"
            @click="close"
          >
            <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
              <path
                d="m6 6 12 12M18 6 6 18"
                fill="none"
                stroke="currentColor"
                stroke-width="1.6"
                stroke-linecap="round"
              />
            </svg>
          </button>
        </header>

        <!-- 会话列表：现阶段只有一条【客户服务】，结构预留多会话。 -->
        <div v-if="view === 'list'" class="support-chat__body" data-testid="support-chat-list">
          <p v-if="loading" class="support-chat__status" role="status">
            {{ t('support.loading') }}
          </p>
          <div v-else-if="authRequired" class="support-chat__notice" role="alert">
            <p>{{ t('support.signInRequired') }}</p>
            <NuxtLink class="support-chat__link" :to="loginUrl()" @click="close">
              {{ t('header.signIn') }}
            </NuxtLink>
          </div>
          <div v-else-if="loadError" class="support-chat__notice" role="alert">
            <p>{{ t('support.loadFailed') }}</p>
            <button class="support-chat__retry" type="button" @click="init">
              {{ t('support.retry') }}
            </button>
          </div>
          <ul v-else class="support-chat__list" :aria-label="t('support.listAria')">
            <li class="support-chat__item-box">
              <button
                class="support-chat__item"
                type="button"
                data-testid="support-chat-list-item"
                @click="enterConversation"
              >
                <span class="support-chat__item-avatar" aria-hidden="true">
                  <svg viewBox="0 0 24 24" width="32" height="32">
                    <path
                      d="M4 13a8 8 0 0 1 16 0v3.5A2.5 2.5 0 0 1 17.5 19H16v-6h4M4 13v3.5A2.5 2.5 0 0 0 6.5 19H8v-6H4"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="1.6"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                  </svg>
                </span>
                <span class="support-chat__item-main">
                  <span class="support-chat__item-head">
                    <span class="support-chat__item-title">{{ t('support.listTitle') }}</span>
                    <span
                      v-if="unreadCount"
                      class="support-chat__unread"
                      :aria-label="t('support.unreadAria', { count: unreadCount })"
                    >
                      {{ unreadCount > 99 ? '99+' : unreadCount }}
                    </span>
                    <span class="support-chat__item-time">{{ formatTime(lastMessageAt) }}</span>
                  </span>
                  <span class="support-chat__item-summary">{{ listPreview }}</span>
                </span>
              </button>
            </li>
          </ul>
        </div>

        <!-- 会话视图：居中头像 + 欢迎语 + 三条 FAQ（点击即发送）+ 发送订单 + 输入框。 -->
        <div v-else class="support-chat__conversation" data-testid="support-chat-conversation">
          <button
            class="support-chat__back"
            type="button"
            data-testid="support-chat-back"
            @click="backToList"
          >
            <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
              <path
                d="M10 3 5 8l5 5"
                fill="none"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            <span>{{ t('support.back') }}</span>
          </button>

          <div
            ref="listEl"
            class="support-chat__messages"
            role="log"
            aria-live="polite"
            :aria-label="t('support.messagesAria')"
          >
            <div class="support-chat__welcome" data-testid="support-chat-welcome">
              <span class="support-chat__welcome-avatar" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="34" height="34">
                  <path
                    d="M4 13a8 8 0 0 1 16 0v3.5A2.5 2.5 0 0 1 17.5 19H16v-6h4M4 13v3.5A2.5 2.5 0 0 0 6.5 19H8v-6H4"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
              </span>
              <p class="support-chat__welcome-text">{{ t('support.welcome') }}</p>
              <div v-if="showFaq" class="support-chat__faqs">
                <button
                  v-for="faq in faqs"
                  :key="faq"
                  class="support-chat__faq"
                  type="button"
                  data-testid="support-chat-faq"
                  :disabled="sending"
                  @click="sendText(faq)"
                >
                  {{ faq }}
                </button>
              </div>
            </div>

            <div
              v-for="message in messages"
              :key="message.key"
              class="support-chat__row"
              :class="{ 'support-chat__row--mine': message.mine }"
            >
              <div
                class="support-chat__bubble"
                :class="{
                  'support-chat__bubble--mine': message.mine,
                  'support-chat__bubble--pending': message.pending,
                  'support-chat__bubble--failed': message.failed,
                }"
              >
                <p class="support-chat__text">{{ message.body }}</p>
                <p class="support-chat__meta">
                  <span>{{ formatTime(message.created_at) }}</span>
                  <button
                    v-if="message.failed"
                    class="support-chat__retry support-chat__retry--inline"
                    type="button"
                    @click="retry(message)"
                  >
                    {{ t('support.sendFailed') }}
                  </button>
                </p>
              </div>
            </div>
          </div>

          <footer class="support-chat__compose">
            <div class="support-chat__toolbar">
              <button
                class="support-chat__order-btn"
                type="button"
                data-testid="support-chat-order-open"
                :disabled="loading || sending || !threadId"
                @click="openOrders"
              >
                <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
                  <path
                    d="M3 1.5h10v13l-2.5-1.6L8 14.5 5.5 12.9 3 14.5v-13Z"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.3"
                    stroke-linejoin="round"
                  />
                  <path
                    d="M5.5 5h5M5.5 7.8h5"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.3"
                  />
                </svg>
                <span>{{ t('support.sendOrder') }}</span>
              </button>
            </div>
            <label class="visually-hidden" :for="INPUT_ID">{{ t('support.messageAria') }}</label>
            <div class="support-chat__field">
              <textarea
                :id="INPUT_ID"
                ref="inputEl"
                v-model="draft"
                class="support-chat__input"
                v-bind="noAutofill"
                data-testid="support-chat-input"
                rows="1"
                :maxlength="MAX_LENGTH"
                :placeholder="t('support.placeholder')"
                @keydown="onComposerKeydown"
              ></textarea>
              <!-- 发送图标在输入框内右侧（需求 23.3）。 -->
              <button
                class="support-chat__send"
                type="button"
                data-testid="support-chat-send"
                :aria-label="t('support.send')"
                :title="t('support.send')"
                :disabled="!canSend"
                @click="send"
              >
                <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
                  <path
                    d="M3 10 17 3l-4.2 14-3.1-5.1L3 10Z"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.5"
                    stroke-linejoin="round"
                  />
                </svg>
              </button>
            </div>
            <p v-if="draft.length > MAX_LENGTH - 200" class="support-chat__count">
              {{ draft.length }}/{{ MAX_LENGTH }}
            </p>
            <p v-if="composeError" class="support-chat__error" role="alert">{{ composeError }}</p>
          </footer>
        </div>

        <!-- 【发送订单】弹层：最近 3 笔订单，可多选，拼成一条文本消息发送。 -->
        <div
          v-if="ordersOpen"
          class="support-chat__overlay"
          data-testid="support-chat-order-dialog"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="ORDER_TITLE_ID"
          @click.self="closeOrders"
        >
          <div class="support-chat__sheet">
            <h3 :id="ORDER_TITLE_ID" class="support-chat__sheet-title">
              {{ t('support.orderDialogTitle') }}
            </h3>
            <p class="support-chat__sheet-desc">{{ t('support.orderDialogDesc') }}</p>
            <p v-if="ordersLoading" class="support-chat__status" role="status">
              {{ t('support.loading') }}
            </p>
            <div v-else-if="ordersError" class="support-chat__sheet-error" role="alert">
              <p>{{ t('support.orderFailed') }}</p>
              <button class="support-chat__retry" type="button" @click="loadOrders">
                {{ t('support.retry') }}
              </button>
            </div>
            <p v-else-if="!orders.length" class="support-chat__status" role="status">
              {{ t('support.orderEmpty') }}
            </p>
            <ul v-else class="support-chat__orders">
              <li v-for="order in orders" :key="order.public_id">
                <label class="support-chat__order-item">
                  <input
                    type="checkbox"
                    data-testid="support-chat-order-checkbox"
                    :checked="selectedOrders.includes(order.public_id)"
                    @change="toggleOrder(order.public_id)"
                  />
                  <span class="support-chat__order-main">
                    <span class="support-chat__order-id"
                      >#{{ orderNumberLabel(order.public_id) }}</span
                    >
                    <span class="support-chat__order-meta">
                      {{ orderAmount(order) }} · {{ orderStateLabel(order) }}
                    </span>
                  </span>
                </label>
              </li>
            </ul>
            <div class="support-chat__sheet-actions">
              <button
                class="support-chat__sheet-btn"
                type="button"
                data-testid="support-chat-order-cancel"
                @click="closeOrders"
              >
                {{ t('support.cancel') }}
              </button>
              <button
                class="support-chat__sheet-btn support-chat__sheet-btn--primary"
                type="button"
                data-testid="support-chat-order-confirm"
                :disabled="!selectedOrders.length || sending"
                @click="confirmOrders"
              >
                {{ t('support.orderConfirm', { count: selectedOrders.length }) }}
              </button>
            </div>
          </div>
        </div>
      </section>
    </Transition>
  </div>
</template>

<style scoped>
/* 需求 22.2（2026-11-22 真站实测）：Joybuy 首页右下角 floating toolbar 的
   【客服】入口 —— 贴右边缘（right 0）、距底 100px，80×60（min-height 48 +
   padding 8/5），白底、1px rgba(0,0,0,.059) 左边框（右边框无）、圆角
   8px 0 0 8px，图标 24px 在上、文字 12px 在下，hover 仅文字下划线。
   实测值来源 var/z2_support_account_20261122/real_toolbar_measure.json +
   CSS bundle ea4701f5901099fe.css（.FloatingToolBarBtn_floatingBtn__7gO95）。 */
.support-chat__launcher {
  position: fixed;
  right: 0;
  bottom: 100px;
  z-index: 1100;
  box-sizing: border-box;
  display: inline-flex;
  width: 80px;
  min-height: 48px;
  height: 60px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 8px 5px;
  border: 1px solid rgb(0 0 0 / 5.9%);
  border-right: none;
  border-radius: 8px 0 0 8px;
  background: #fff;
  color: #1a1a1a;
  font: inherit;
  font-size: 12px;
  line-height: 16px;
  cursor: pointer;
  transition: bottom 160ms ease;
}

.support-chat__launcher:hover {
  background: #fff;
  text-decoration: underline;
}

.support-chat__label {
  font-size: 12px;
  line-height: 16px;
}

.support-chat__launcher svg {
  flex: none;
}

/* 2026-11-27：PDP【联系商家】已改成与本按钮同款（贴右 80 宽、60 高以上），
   两者改为纵向堆叠：【客服】仍在 bottom 100（顶边 160），【联系商家】底边 168
   （8px gap），互不重叠。因此 body.pdp-merchant-contact 不再需要上移客服按钮，
   也不要再给两者加相互位移规则（改宽度/高度时同步改 PDP 的 .detail__contact）。 */

/* 真站客服面板（findings C2）：375 宽、80% 高（max 720）、right 84 /
   bottom 104.5、#F5F6FA 底、8px 圆角、#F0F1F2 边框、
   0 2px 16px rgba(0,0,0,.078)、z-index 1200。 */
.support-chat__panel {
  position: fixed;
  right: 84px;
  bottom: 104.5px;
  z-index: 1200;
  display: flex;
  box-sizing: border-box;
  width: 375px;
  height: 80%;
  max-height: 720px;
  flex-direction: column;
  border: 1px solid #f0f1f2;
  border-radius: 8px;
  background: #f5f6fa;
  box-shadow: 0 2px 16px 0 rgb(0 0 0 / 7.8%);
  overflow: hidden;
}

/* 面板底边与按钮底边对齐即可：面板 right 84，与贴右的 80 宽按钮不横向相交。 */

/* header：60px 白底，标题 24px/700 #1a1a1a，左右图标 24px 距边 16px。 */
.support-chat__head {
  position: relative;
  display: flex;
  height: 60px;
  flex: none;
  align-items: center;
  justify-content: center;
  border-top-left-radius: 8px;
  border-top-right-radius: 8px;
  background: #fff;
}

.support-chat__title {
  margin: 0;
  color: #1a1a1a;
  font-size: 24px;
  font-weight: 700;
  line-height: 32px;
  text-align: center;
}

.support-chat__icon-btn {
  position: absolute;
  top: 50%;
  display: inline-flex;
  width: 24px;
  height: 24px;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 0;
  background: transparent;
  color: #1a1a1a;
  cursor: pointer;
  transform: translateY(-50%);
}

.support-chat__icon-btn--left {
  left: 16px;
}

.support-chat__icon-btn--right {
  right: 16px;
}

.support-chat__icon-btn:disabled {
  color: #c4c6cc;
  cursor: not-allowed;
}

.support-chat__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  overflow-y: auto;
  background: #f5f6fa;
}

.support-chat__list {
  margin: 0;
  padding: 8px 0 0;
  list-style: none;
}

.support-chat__item-box {
  margin-bottom: 8px;
  background: #fff;
}

.support-chat__item {
  display: flex;
  width: 100%;
  box-sizing: border-box;
  padding: 12px 16px;
  border: 0;
  background: #fff;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.support-chat__item:hover {
  background: rgb(0 16 71 / 10.2%);
}

.support-chat__item-avatar {
  display: inline-flex;
  width: 60px;
  height: 60px;
  flex: none;
  align-items: center;
  justify-content: center;
  margin: 3px 8px 0 0;
  border-radius: 100%;
  background: #eef0f6;
  color: #1a1a1a;
  overflow: hidden;
}

.support-chat__item-main {
  display: block;
  flex: 1;
  min-width: 0;
}

.support-chat__item-head {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.support-chat__item-title {
  flex: 1;
  min-width: 0;
  color: #1a1a1a;
  font-size: 16px;
  font-weight: 600;
  line-height: 22px;
  overflow: visible;

  white-space: normal;
  word-break: break-word;
}

.support-chat__item-time {
  flex: none;
  color: #505259;
  font-size: 12px;
  font-weight: 400;
  line-height: 22px;
  white-space: nowrap;
}

.support-chat__unread {
  flex: none;
  width: 16px;
  height: 16px;
  margin-top: 3px;
  border-radius: 100%;
  background: #e1251b;
  color: #fff;
  font-size: 10px;
  line-height: 16px;
  text-align: center;
}

.support-chat__item-summary {
  display: block;
  min-height: 40px;
  margin: 4px 0;
  color: #505259;
  font-size: 14px;
  font-weight: 500;
  line-height: 20px;
  overflow: visible;
  word-break: break-word;
}

.support-chat__status {
  margin: 16px 0;
  color: #505259;
  font-size: 14px;
  text-align: center;
}

.support-chat__notice {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  margin: 16px;
  padding: 20px 12px;
  border-radius: 8px;
  background: #fff;
  color: #505259;
  font-size: 14px;
  text-align: center;
}

.support-chat__notice p {
  margin: 0;
}

.support-chat__link {
  color: var(--colour-accent);
  font-weight: 500;
  text-decoration: none;
}

.support-chat__link:hover {
  text-decoration: underline;
}

.support-chat__retry {
  padding: 6px 16px;
  border: 1px solid #d9dee5;
  border-radius: 4px;
  background: #fff;
  color: #1a1a1a;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}

.support-chat__retry:hover {
  border-color: var(--colour-accent);
  color: var(--colour-accent);
}

.support-chat__retry--inline {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--colour-error);
  font-size: 11px;
  text-decoration: underline;
}

/* 会话视图：白底（真站 .style_wrapper-type-0 实测 #fff）。 */
.support-chat__conversation {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  background: #fff;
}

.support-chat__back {
  display: inline-flex;
  height: 34px;
  flex: none;
  align-items: center;
  gap: 2px;
  padding: 0 12px 0 8px;
  border: 0;
  border-bottom: 1px solid #f5f6fa;
  background: #fff;
  color: #505259;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}

.support-chat__back:hover {
  color: #1a1a1a;
}

.support-chat__messages {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
  padding: 16px;
}

/* 首屏：客服头像居中靠上 + 欢迎语 + 三条常见问题（推定，真站未实测）。 */
.support-chat__welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 8px 0 4px;
}

.support-chat__welcome-avatar {
  display: inline-flex;
  width: 64px;
  height: 64px;
  align-items: center;
  justify-content: center;
  border-radius: 100%;
  background: #eef0f6;
  color: #1a1a1a;
}

.support-chat__welcome-text {
  max-width: 300px;
  margin: 0;
  color: #505259;
  font-size: 14px;
  line-height: 1.6;
  text-align: center;
}

.support-chat__faqs {
  display: flex;
  width: 100%;
  flex-direction: column;
  gap: 8px;
}

.support-chat__faq {
  width: 100%;
  min-height: 40px;
  padding: 9px 14px;
  border: 1px solid #e7e8ea;
  border-radius: 8px;
  background: #fff;
  color: #1a1a1a;
  font: inherit;
  font-size: 14px;
  line-height: 20px;
  text-align: center;
  cursor: pointer;
}

.support-chat__faq:hover:not(:disabled) {
  background: rgb(0 16 71 / 6%);
}

.support-chat__faq:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.support-chat__row {
  display: flex;
  justify-content: flex-start;
}

.support-chat__row--mine {
  justify-content: flex-end;
}

.support-chat__bubble {
  max-width: 82%;
  padding: 9px 12px;
  border-radius: 12px 12px 12px 4px;
  background: #f5f6fa;
  color: #1a1a1a;
}

.support-chat__bubble--mine {
  border-radius: 12px 12px 4px;
  background: var(--colour-accent);
  color: #fff;
}

.support-chat__bubble--pending {
  opacity: 0.65;
}

.support-chat__bubble--failed {
  background: var(--colour-error-soft);
  color: #1a1a1a;
}

.support-chat__text {
  margin: 0;
  font-size: 14px;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.support-chat__meta {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  margin: 4px 0 0;
  color: #8a8d94;
  font-size: 11px;
}

.support-chat__bubble--mine .support-chat__meta {
  color: rgb(255 255 255 / 75%);
}

.support-chat__bubble--failed .support-chat__meta {
  color: #8a8d94;
}

.support-chat__compose {
  flex-shrink: 0;
  padding: 8px 12px 12px;
  border-top: 1px solid #f0f1f2;
  background: #fff;
}

.support-chat__toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.support-chat__order-btn {
  display: inline-flex;
  height: 32px;
  align-items: center;
  gap: 6px;
  padding: 0 12px;
  border: 1px solid #e7e8ea;
  border-radius: 16px;
  background: #fff;
  color: #1a1a1a;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}

.support-chat__order-btn:hover:not(:disabled) {
  border-color: #1a1a1a;
}

.support-chat__order-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

/* 输入框：单行圆角框，发送图标在框内右侧。 */
.support-chat__field {
  position: relative;
  display: flex;
}

.support-chat__input {
  box-sizing: border-box;
  width: 100%;
  min-height: 40px;
  max-height: 92px;
  padding: 10px 46px 10px 14px;
  border: 1px solid #e7e8ea;
  border-radius: 20px;
  background: #f5f6fa;
  resize: none;
  color: #1a1a1a;
  font: inherit;
  font-size: 14px;
  line-height: 20px;
}

.support-chat__input:focus {
  border-color: #1a1a1a;
  background: #fff;
  outline: none;
}

.support-chat__send {
  position: absolute;
  top: 50%;
  right: 5px;
  display: inline-flex;
  width: 32px;
  height: 32px;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: var(--colour-accent);
  color: #fff;
  cursor: pointer;
  transform: translateY(-50%);
}

.support-chat__send:hover:not(:disabled) {
  background: var(--colour-accent-dark);
}

.support-chat__send:disabled {
  background: #d5d7dc;
  cursor: not-allowed;
}

.support-chat__count {
  margin: 4px 0 0;
  color: #8a8d94;
  font-size: 11px;
  text-align: right;
}

.support-chat__error {
  margin: 6px 0 0;
  color: var(--colour-error);
  font-size: 13px;
}

/* 【发送订单】弹层：覆盖在面板内，白底卡片。 */
.support-chat__overlay {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  background: rgb(0 0 0 / 45%);
}

.support-chat__sheet {
  display: flex;
  width: 100%;
  max-height: 100%;
  flex-direction: column;
  padding: 16px;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 8px 24px rgb(0 0 0 / 18%);
  overflow-y: auto;
}

.support-chat__sheet-title {
  margin: 0;
  color: #1a1a1a;
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
}

.support-chat__sheet-desc {
  margin: 4px 0 12px;
  color: #505259;
  font-size: 13px;
  line-height: 18px;
}

.support-chat__sheet-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: #505259;
  font-size: 13px;
}

.support-chat__sheet-error p {
  margin: 0;
}

.support-chat__orders {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.support-chat__order-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid #e7e8ea;
  border-radius: 8px;
  cursor: pointer;
}

.support-chat__order-item:hover {
  background: #f5f6fa;
}

.support-chat__order-item input {
  width: 16px;
  height: 16px;
  flex: none;
  accent-color: var(--colour-accent);
}

.support-chat__order-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.support-chat__order-id {
  color: #1a1a1a;
  font-size: 14px;
  font-weight: 600;
  line-height: 20px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.support-chat__order-meta {
  color: #505259;
  font-size: 12px;
  line-height: 18px;
}

.support-chat__sheet-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}

.support-chat__sheet-btn {
  height: 34px;
  padding: 0 16px;
  border: 1px solid #d9dee5;
  border-radius: 17px;
  background: #fff;
  color: #1a1a1a;
  font: inherit;
  font-size: 14px;
  cursor: pointer;
}

.support-chat__sheet-btn--primary {
  border-color: var(--colour-accent);
  background: var(--colour-accent);
  color: #fff;
}

.support-chat__sheet-btn--primary:hover:not(:disabled) {
  background: var(--colour-accent-dark);
}

.support-chat__sheet-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.support-chat__launcher:focus-visible,
.support-chat__icon-btn:focus-visible,
.support-chat__item:focus-visible,
.support-chat__back:focus-visible,
.support-chat__faq:focus-visible,
.support-chat__order-btn:focus-visible,
.support-chat__send:focus-visible,
.support-chat__retry:focus-visible,
.support-chat__link:focus-visible,
.support-chat__input:focus-visible,
.support-chat__sheet-btn:focus-visible {
  outline: 2px solid var(--colour-focus-ring);
  outline-offset: 2px;
}

.support-chat-pop-enter-active,
.support-chat-pop-leave-active {
  transition:
    opacity 160ms ease,
    transform 160ms ease;
}

.support-chat-pop-enter-from,
.support-chat-pop-leave-to {
  opacity: 0;
  transform: translateY(12px);
}

@media (max-width: 40rem) {
  /* 小屏沿用真站贴边形态（right 0），仅把距底抬高避让移动端浏览器工具条。 */
  .support-chat__launcher {
    bottom: 84px;
    width: 72px;
  }

  .support-chat__panel {
    right: 8px;
    bottom: 152px;
    width: calc(100vw - 16px);
    height: calc(100vh - 240px);
    max-height: none;
  }

  /* 手机版（MobilePDP）没有【联系商家】入口，客服按钮保持 bottom 84 不动。 */
}

@media (prefers-reduced-motion: reduce) {
  .support-chat-pop-enter-active,
  .support-chat-pop-leave-active {
    transition: none;
  }
}
</style>
