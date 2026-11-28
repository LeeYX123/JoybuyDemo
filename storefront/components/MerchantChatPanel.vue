<script setup>
// 用户 ↔ 商家会话面板（需求 19 / 批次 V3）。
//
// 入口只在「已登录 + purchase_whitelisted」时由店铺页渲染；面板自身负责
// get-or-create 会话（POST threads）→ 拉消息 → 5s 轮询增量。403
// NOT_WHITELISTED 会在面板内提示并把 blocked 事件抛给父级隐藏入口。
//
// 交互/无障碍沿用 AddressDrawer：右侧抽屉 + backdrop、Escape 关闭、Tab 焦点
// 闭环、打开时锁 body 滚动、关闭后把焦点还给触发按钮。
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { useLocale } from '../composables/useLocale'
import { noAutofill } from '../utils/noAutofill'

const props = defineProps({
  open: { type: Boolean, default: false },
  merchant: { type: Object, default: null },
  // 需求 3：买家当前正在看的商品（SPU public_id）。打开面板和每次发消息都带上，
  // 服务端覆盖式更新会话的商品上下文，商家端据此切换「当前沟通的是哪件商品」。
  product: { type: String, default: '' },
})

const emit = defineEmits(['close', 'blocked'])

const { t, localeCode } = useLocale()

const MAX_LENGTH = 2000
const POLL_INTERVAL_MS = 5000
const TITLE_ID = 'merchant-chat-title'
const INPUT_ID = 'merchant-chat-input'

const threadId = ref('')
const messages = ref([])
const loading = ref(false)
const loadError = ref(false)
const blocked = ref(false)
const authRequired = ref(false)
const sending = ref(false)
const composeError = ref('')
const draft = ref('')

const panel = ref(null)
const listEl = ref(null)
const closeButton = ref(null)
const inputEl = ref(null)

let pollTimer = null
let pollInFlight = false
let previousActiveElement = null
let previousBodyOverflow = ''
let scrollLocked = false

const canSend = computed(
  () =>
    Boolean(draft.value.trim()) &&
    draft.value.trim().length <= MAX_LENGTH &&
    !sending.value &&
    !loading.value &&
    !loadError.value &&
    !blocked.value &&
    !authRequired.value &&
    Boolean(threadId.value),
)

// 轮询游标 = 最后一条「已确认服务端消息」或「正在发送的乐观消息」的时间。
// 首发慢 POST（真实 Crisp 约 3.7s）时游标不能为空，否则轮询会拉全量历史，
// 与本地乐观气泡撞出重复；失败的乐观气泡不推进游标（避免时钟偏差吞消息）。
const pollCursor = computed(() => {
  let bestTs = 0
  let bestValue = ''
  for (const message of messages.value) {
    if (!message.created_at) continue
    if (!message.serverId && !message.pending) continue
    const ts = Date.parse(message.created_at)
    if (Number.isNaN(ts)) continue
    if (ts >= bestTs) {
      bestTs = ts
      bestValue = message.created_at
    }
  }
  return bestValue
})

function chatUrl(path) {
  return `/api/v1/account/merchant-chat${path}`
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
  return $fetch(chatUrl(path), {
    method: 'POST',
    body,
    credentials: 'include',
    headers: { 'X-CSRFToken': token, 'Content-Type': 'application/json' },
    ignoreResponseError: true,
  })
}

async function getJson(path) {
  return $fetch(chatUrl(path), { credentials: 'include', ignoreResponseError: true })
}

// 401/403 是账号状态问题，不是网络错误：分别落到登录提示 / 白名单提示。
function handleAccessError(payload) {
  const code = payload?.error?.code
  if (code === 'NOT_WHITELISTED') {
    blocked.value = true
    stopPolling()
    emit('blocked')
    return true
  }
  if (code === 'BUYER_AUTH_REQUIRED') {
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
    // 批次 AA：平台客服在 Crisp 的人工回复回传为 sender_kind=support，单独标记。
    support: raw.sender_kind === 'support',
    body: raw.body || '',
    // 需求 2：商家端可以发图片，买家侧同步展示（图片消息可能没有文字）。
    image_url: raw.image_url || '',
    created_at: raw.created_at || '',
    pending: false,
    failed: false,
  }
}

// 去重键：已确认消息用服务端 id，乐观气泡用客户端 id（需求 19 修复）。
function messageIdentity(message) {
  if (message.serverId) return `srv:${message.serverId}`
  return message.clientId ? `cli:${message.clientId}` : ''
}

function removeMessage(message) {
  messages.value = messages.value.filter((item) => item !== message)
}

// 同一 serverId 只保留一条（轮询/POST 返回同时到达时的兜底）。
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

// 轮询拿到服务端消息时：已存在跳过；否则若与某条乐观气泡同文且同为买家
// 发出，则「认领」该气泡（原地补 serverId），绝不额外 append 一条。
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
  for (const raw of incoming) {
    changed = applyServerMessage(raw) || changed
  }
  return changed
}

async function init() {
  const slug = String(props.merchant?.slug || '')
  threadId.value = ''
  messages.value = []
  loading.value = true
  loadError.value = false
  blocked.value = false
  authRequired.value = false
  composeError.value = ''
  if (!slug) {
    loading.value = false
    loadError.value = true
    return
  }
  try {
    // 幂等 get-or-create：同一买家对同一商家永远拿到同一个会话。
    const created = await postJson('/threads', { merchant: slug, product: props.product || '' })
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
    const payload = await getJson(`/threads/${id}/messages`)
    if (payload?.error) {
      if (!handleAccessError(payload)) loadError.value = true
      return
    }
    messages.value = (payload?.messages || []).map(serverMessage)
    startPolling()
    await scrollToBottom()
    await nextTick()
    if (!blocked.value && !authRequired.value) inputEl.value?.focus?.()
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

// 发送（含失败重试）共用：POST 返回优先按 serverId 找到已有气泡（轮询可能
// 先到并已认领），否则按 clientId 原地替换该乐观气泡——绝不再 append 一条。
async function deliver(message) {
  message.pending = true
  message.failed = false
  composeError.value = ''
  try {
    const payload = await postJson(`/threads/${threadId.value}/messages`, {
      body: message.body,
      product: props.product || '',
    })
    if (payload?.error) {
      handleAccessError(payload)
      if (!message.serverId) {
        message.pending = false
        message.failed = true
      }
      composeError.value = t('chat.sendFailed')
      return
    }
    const raw = payload?.message
    if (raw?.id !== undefined && raw?.id !== null) {
      const existing = messages.value.find((item) => item.serverId === raw.id)
      const target = messages.value.find((item) => item.clientId === message.clientId) || message
      if (existing && existing !== target) {
        // 轮询已经渲染了这条服务端消息：丢弃本地占位，只保留一条。
        removeMessage(target)
        Object.assign(existing, serverMessage(raw, existing.clientId))
      } else {
        Object.assign(target, serverMessage(raw, target.clientId))
      }
      pruneDuplicateMessages()
    } else if (!message.serverId) {
      message.pending = false
    }
  } catch {
    if (!message.serverId) {
      message.pending = false
      message.failed = true
    }
    composeError.value = t('chat.sendFailed')
  }
}

async function send() {
  const body = draft.value.trim()
  if (!body || !threadId.value || sending.value) return
  if (body.length > MAX_LENGTH) {
    composeError.value = t('chat.tooLong', { max: MAX_LENGTH })
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
  draft.value = ''
  await scrollToBottom()
  try {
    await deliver(optimistic)
  } finally {
    sending.value = false
  }
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
    const after = pollCursor.value
    const query = after ? `?after=${encodeURIComponent(after)}` : ''
    const payload = await getJson(`/threads/${threadId.value}/messages${query}`)
    if (payload?.error) {
      if (payload.error.code === 'NOT_WHITELISTED') handleAccessError(payload)
      return
    }
    if (mergeMessages(payload?.messages || [])) await scrollToBottom()
  } catch {
    // 轮询失败静默，下一轮再试，避免每 5s 弹一次错误。
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

function close() {
  emit('close')
}

function lockScroll() {
  if (typeof document === 'undefined' || scrollLocked) return
  previousBodyOverflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
  scrollLocked = true
}

function unlockScroll() {
  if (typeof document === 'undefined' || !scrollLocked) return
  document.body.style.overflow = previousBodyOverflow
  scrollLocked = false
}

function restoreFocus() {
  const target = previousActiveElement
  previousActiveElement = null
  if (target && typeof target.focus === 'function' && document.contains(target)) {
    target.focus()
  }
}

function onKeydown(event) {
  if (!props.open) return
  if (event.key === 'Escape') {
    event.preventDefault()
    close()
    return
  }
  if (event.key !== 'Tab' || !panel.value) return
  const focusable = [
    ...panel.value.querySelectorAll(
      'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled])',
    ),
  ]
  if (!focusable.length) return
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

// Enter 发送、Shift+Enter 换行；输入法合成中的 Enter 不发送。
function onComposerKeydown(event) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  send()
}

function onVisibilityChange() {
  if (typeof document !== 'undefined' && !document.hidden && props.open) poll()
}

watch(
  () => props.open,
  async (isOpen) => {
    if (typeof document === 'undefined') return
    if (isOpen) {
      previousActiveElement = document.activeElement
      lockScroll()
      await nextTick()
      closeButton.value?.focus?.()
      init()
      return
    }
    stopPolling()
    unlockScroll()
    restoreFocus()
    threadId.value = ''
    messages.value = []
    loading.value = false
    loadError.value = false
    blocked.value = false
    authRequired.value = false
    composeError.value = ''
    draft.value = ''
  },
  { immediate: true },
)

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  document.addEventListener('visibilitychange', onVisibilityChange)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  document.removeEventListener('visibilitychange', onVisibilityChange)
  stopPolling()
  unlockScroll()
})
</script>

<template>
  <Transition name="chat-drawer">
    <div v-if="open" class="merchant-chat">
      <div class="merchant-chat__backdrop" @click="close"></div>
      <section
        ref="panel"
        class="merchant-chat__panel"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="TITLE_ID"
      >
        <header class="merchant-chat__head">
          <span class="merchant-chat__avatar">
            <img
              v-if="merchant?.avatar_url"
              :src="merchant.avatar_url"
              :alt="merchant.display_name || ''"
            />
            <template v-else>{{ String(merchant?.display_name || '?').slice(0, 1) }}</template>
          </span>
          <div class="merchant-chat__head-text">
            <h2 :id="TITLE_ID">{{ merchant?.display_name || t('chat.title') }}</h2>
            <p>{{ t('chat.subtitle') }}</p>
          </div>
          <button
            ref="closeButton"
            class="merchant-chat__close"
            type="button"
            :aria-label="t('chat.close')"
            @click="close"
          >
            <svg viewBox="0 0 20 20" width="20" height="20" aria-hidden="true">
              <path
                d="m5.832 5.833 8.333 8.334m-8.333 0 8.333-8.334"
                fill="none"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
            </svg>
          </button>
        </header>

        <div
          ref="listEl"
          class="merchant-chat__messages"
          role="log"
          aria-live="polite"
          :aria-label="t('chat.messagesAria')"
        >
          <p v-if="loading" class="merchant-chat__status" role="status">
            {{ t('chat.loading') }}
          </p>
          <div v-else-if="blocked" class="merchant-chat__notice" role="alert">
            {{ t('chat.notWhitelisted') }}
          </div>
          <div v-else-if="authRequired" class="merchant-chat__notice" role="alert">
            <p>{{ t('chat.signInRequired') }}</p>
            <NuxtLink class="merchant-chat__link" to="/auth/login" @click="close">
              {{ t('header.signIn') }}
            </NuxtLink>
          </div>
          <div v-else-if="loadError" class="merchant-chat__notice" role="alert">
            <p>{{ t('chat.loadFailed') }}</p>
            <button class="merchant-chat__retry" type="button" @click="init">
              {{ t('chat.retry') }}
            </button>
          </div>
          <template v-else>
            <p v-if="!messages.length" class="merchant-chat__status" role="status">
              {{ t('chat.empty') }}
            </p>
            <div
              v-for="message in messages"
              :key="message.key"
              class="merchant-chat__row"
              :class="{ 'merchant-chat__row--mine': message.mine }"
            >
              <div
                class="merchant-chat__bubble"
                :class="{
                  'merchant-chat__bubble--mine': message.mine,
                  'merchant-chat__bubble--support': message.support,
                  'merchant-chat__bubble--pending': message.pending,
                  'merchant-chat__bubble--failed': message.failed,
                }"
              >
                <p v-if="message.support" class="merchant-chat__tag">
                  {{ t('chat.supportLabel') }}
                </p>
                <img
                  v-if="message.image_url"
                  class="merchant-chat__image"
                  :src="message.image_url"
                  alt=""
                  loading="lazy"
                />
                <p v-if="message.body" class="merchant-chat__text">{{ message.body }}</p>
                <p class="merchant-chat__meta">
                  <span>{{ formatTime(message.created_at) }}</span>
                  <button
                    v-if="message.failed"
                    class="merchant-chat__retry merchant-chat__retry--inline"
                    type="button"
                    @click="retry(message)"
                  >
                    {{ t('chat.sendFailed') }}
                  </button>
                </p>
              </div>
            </div>
          </template>
        </div>

        <footer v-if="!blocked && !authRequired" class="merchant-chat__compose">
          <label class="visually-hidden" :for="INPUT_ID">{{ t('chat.messageAria') }}</label>
          <textarea
            :id="INPUT_ID"
            ref="inputEl"
            v-model="draft"
            class="merchant-chat__input"
            v-bind="noAutofill"
            rows="2"
            :maxlength="MAX_LENGTH"
            :placeholder="t('chat.placeholder')"
            @keydown="onComposerKeydown"
          ></textarea>
          <div class="merchant-chat__compose-row">
            <span class="merchant-chat__count">{{ draft.length }}/{{ MAX_LENGTH }}</span>
            <button class="merchant-chat__send" type="button" :disabled="!canSend" @click="send">
              {{ sending ? t('chat.sending') : t('chat.send') }}
            </button>
          </div>
          <p v-if="composeError" class="merchant-chat__error" role="alert">{{ composeError }}</p>
        </footer>
      </section>
    </div>
  </Transition>
</template>

<style scoped>
.merchant-chat {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: flex;
  justify-content: flex-end;
}

.merchant-chat__backdrop {
  position: absolute;
  inset: 0;
  background: rgb(0 0 0 / 50%);
}

/* 右侧抽屉：与 AddressDrawer 同一动效/阴影口径，宽度收窄到聊天场景。 */
.merchant-chat__panel {
  position: relative;
  display: flex;
  flex-direction: column;
  width: min(28rem, 100%);
  height: 100%;
  background: var(--colour-surface);
  box-shadow:
    rgb(0 0 0 / 20%) 0 8px 10px -5px,
    rgb(0 0 0 / 14%) 0 16px 24px 2px,
    rgb(0 0 0 / 12%) 0 6px 30px 5px;
}

.merchant-chat__head {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
  padding: 16px 12px 16px 24px;
  border-bottom: 1px solid var(--colour-surface-soft);
}

.merchant-chat__avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  flex: none;
  overflow: hidden;
  border-radius: 50%;
  background: var(--colour-surface-muted);
  color: var(--colour-text-secondary);
  font-size: 18px;
  font-weight: var(--font-weight-semibold);
}

.merchant-chat__avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.merchant-chat__head-text {
  flex: 1;
  min-width: 0;
}

.merchant-chat__head-text h2 {
  margin: 0;
  overflow: visible;
  color: var(--colour-text);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  line-height: 1.3;

  white-space: normal;
  word-break: break-word;
}

.merchant-chat__head-text p {
  margin: 2px 0 0;
  color: var(--colour-muted);
  font-size: var(--font-size-xs);
}

.merchant-chat__close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  flex: none;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--colour-text);
  cursor: pointer;
}

.merchant-chat__close:hover {
  background: var(--colour-hover);
}

.merchant-chat__messages {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
  padding: 20px 24px;
}

.merchant-chat__status {
  margin: 16px 0;
  color: var(--colour-muted);
  font-size: var(--font-size-md);
  text-align: center;
}

.merchant-chat__notice {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  margin: auto 0;
  padding: 24px 16px;
  border-radius: var(--radius-md);
  background: var(--colour-surface-soft);
  color: var(--colour-text-secondary);
  font-size: var(--font-size-md);
  text-align: center;
}

.merchant-chat__notice p {
  margin: 0;
}

.merchant-chat__link {
  color: var(--colour-accent);
  font-weight: var(--font-weight-medium);
  text-decoration: none;
}

.merchant-chat__link:hover {
  text-decoration: underline;
}

.merchant-chat__retry {
  padding: 6px 16px;
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-sm);
  background: var(--colour-surface);
  color: var(--colour-text);
  font: inherit;
  font-size: var(--font-size-sm);
  cursor: pointer;
}

.merchant-chat__retry:hover {
  border-color: var(--colour-accent);
  color: var(--colour-accent);
}

.merchant-chat__retry--inline {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--colour-error);
  font-size: var(--font-size-xs);
  text-decoration: underline;
}

.merchant-chat__row {
  display: flex;
  justify-content: flex-start;
}

.merchant-chat__row--mine {
  justify-content: flex-end;
}

.merchant-chat__bubble {
  max-width: 82%;
  padding: 10px 12px;
  border-radius: 12px 12px 12px 4px;
  background: var(--colour-surface-soft);
  color: var(--colour-text);
}

.merchant-chat__bubble--mine {
  border-radius: 12px 12px 4px;
  background: var(--colour-accent);
  color: var(--colour-white);
}

/* 批次 AA：平台客服（Crisp 人工回复）气泡——与"商家本人"区分开，浅底 + 左侧色条。 */
.merchant-chat__bubble--support {
  background: var(--colour-surface);
  border-left: 3px solid var(--colour-accent);
  color: var(--colour-text);
}

.merchant-chat__tag {
  margin: 0 0 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--colour-accent);
}

.merchant-chat__bubble--pending {
  opacity: 0.65;
}

.merchant-chat__bubble--failed {
  background: var(--colour-error-soft);
  color: var(--colour-text);
}

.merchant-chat__image {
  display: block;
  max-width: min(220px, 100%);
  max-height: 200px;
  border-radius: 8px;
  object-fit: contain;
}

.merchant-chat__image + .merchant-chat__text {
  margin-top: 6px;
}

.merchant-chat__text {
  margin: 0;
  font-size: var(--font-size-md);
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.merchant-chat__meta {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  margin: 4px 0 0;
  color: var(--colour-muted);
  font-size: 11px;
}

.merchant-chat__bubble--mine .merchant-chat__meta {
  color: rgb(255 255 255 / 75%);
}

.merchant-chat__bubble--failed .merchant-chat__meta {
  color: var(--colour-muted);
}

.merchant-chat__compose {
  flex-shrink: 0;
  padding: 12px 24px 20px;
  border-top: 1px solid var(--colour-surface-soft);
}

.merchant-chat__input {
  box-sizing: border-box;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-sm);
  resize: none;
  color: var(--colour-text);
  font: inherit;
  font-size: var(--font-size-md);
  line-height: 1.5;
}

.merchant-chat__input:focus {
  border-color: var(--colour-text);
  outline: none;
}

.merchant-chat__compose-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 8px;
}

.merchant-chat__count {
  color: var(--colour-muted);
  font-size: var(--font-size-xs);
}

.merchant-chat__send {
  min-width: 96px;
  height: 36px;
  padding: 0 20px;
  border: 0;
  border-radius: var(--radius-sm);
  background: var(--colour-accent);
  color: var(--colour-white);
  font: inherit;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
}

.merchant-chat__send:hover:not(:disabled) {
  background: var(--colour-accent-dark);
}

.merchant-chat__send:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.merchant-chat__error {
  margin: 8px 0 0;
  color: var(--colour-error);
  font-size: var(--font-size-sm);
}

.merchant-chat__close:focus-visible,
.merchant-chat__retry:focus-visible,
.merchant-chat__link:focus-visible,
.merchant-chat__input:focus-visible,
.merchant-chat__send:focus-visible {
  outline: 2px solid var(--colour-focus-ring);
  outline-offset: 2px;
}

.chat-drawer-enter-active,
.chat-drawer-leave-active {
  transition: opacity 225ms cubic-bezier(0.4, 0, 0.2, 1);
}

.chat-drawer-enter-active .merchant-chat__panel,
.chat-drawer-leave-active .merchant-chat__panel {
  transition: transform 225ms cubic-bezier(0, 0, 0.2, 1);
}

.chat-drawer-enter-from,
.chat-drawer-leave-to {
  opacity: 0;
}

.chat-drawer-enter-from .merchant-chat__panel,
.chat-drawer-leave-to .merchant-chat__panel {
  transform: translateX(100%);
}

@media (max-width: 48rem) {
  .merchant-chat__panel {
    width: 100%;
  }

  .merchant-chat__head {
    padding: 12px 8px 12px 16px;
  }

  .merchant-chat__messages {
    padding: 16px;
  }

  .merchant-chat__compose {
    padding: 12px 16px 16px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .chat-drawer-enter-active,
  .chat-drawer-leave-active,
  .chat-drawer-enter-active .merchant-chat__panel,
  .chat-drawer-leave-active .merchant-chat__panel {
    transition: none;
  }
}
</style>
