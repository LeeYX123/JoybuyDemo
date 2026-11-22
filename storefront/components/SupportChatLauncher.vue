<script setup>
// 全站【客服】入口（需求 21 / 批次 Y，2026-11-22）。
//
// 右下角图标 + 文字按钮，点击展开浮层面板：买家 ↔ 平台客服会话
// （/api/v1/account/support-chat/*）。所有登录买家可用（不要求白名单）；
// 未登录点击先去登录页并带回跳（?next=）。打开后每 5s 轮询增量，关闭面板、
// 页面隐藏或组件卸载时停止。
//
// 与 MerchantChatPanel（用户 ↔ 商家）保持独立：两者接口/权限/文案都不同，
// 只借鉴其乐观发送 + 服务端认领的交互细节，不共享状态。
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { navigateTo, useRoute } from '#imports'

import { useBuyerAuth } from '../composables/useBuyerAuth'
import { useLocale } from '../composables/useLocale'

const MAX_LENGTH = 2000
const POLL_INTERVAL_MS = 5000
const TITLE_ID = 'support-chat-title'
const INPUT_ID = 'support-chat-input'
const BASE = '/api/v1/account/support-chat'

const { t, localeCode } = useLocale()
const { isAuthenticated } = useBuyerAuth()
const route = useRoute()

const open = ref(false)
const threadId = ref('')
const messages = ref([])
const loading = ref(false)
const loadError = ref(false)
const authRequired = ref(false)
const sending = ref(false)
const composeError = ref('')
const draft = ref('')

const listEl = ref(null)
const closeButton = ref(null)
const inputEl = ref(null)

let pollTimer = null
let pollInFlight = false

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

// 轮询游标 = 最后一条「已确认服务端消息」或「正在发送的乐观消息」的时间；
// 未发送成功的乐观气泡不推进游标，避免时钟偏差吞掉客服回复。
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

async function init() {
  threadId.value = ''
  messages.value = []
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
    const payload = await getJson('/messages')
    if (payload?.error) {
      if (!handleAccessError(payload)) loadError.value = true
      return
    }
    messages.value = (payload?.messages || []).map((raw) => serverMessage(raw))
    startPolling()
    await scrollToBottom()
    await nextTick()
    if (!authRequired.value) inputEl.value?.focus?.()
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
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

async function send() {
  const body = draft.value.trim()
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
    const payload = await getJson(`/messages${query}`)
    if (payload?.error) {
      handleAccessError(payload)
      return
    }
    if (mergeMessages(payload?.messages || [])) await scrollToBottom()
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
  if (event.key === 'Escape' && open.value) {
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
  if (typeof document !== 'undefined' && !document.hidden && open.value) poll()
}

watch(open, async (isOpen) => {
  if (typeof document === 'undefined') return
  if (isOpen) {
    await nextTick()
    closeButton.value?.focus?.()
    init()
    return
  }
  stopPolling()
  threadId.value = ''
  messages.value = []
  loading.value = false
  loadError.value = false
  authRequired.value = false
  composeError.value = ''
  draft.value = ''
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
      <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
        <path
          d="M4 13a8 8 0 0 1 16 0v3.5A2.5 2.5 0 0 1 17.5 19H16v-6h4M4 13v3.5A2.5 2.5 0 0 0 6.5 19H8v-6H4"
          fill="none"
          stroke="currentColor"
          stroke-width="1.6"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
      <span>{{ t('support.launcher') }}</span>
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
        <header class="support-chat__head">
          <span class="support-chat__avatar" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="20" height="20">
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
          <div class="support-chat__head-text">
            <h2 :id="TITLE_ID">{{ t('support.title') }}</h2>
            <p>{{ t('support.subtitle') }}</p>
          </div>
          <button
            ref="closeButton"
            class="support-chat__close"
            type="button"
            data-testid="support-chat-close"
            :aria-label="t('support.close')"
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
          class="support-chat__messages"
          role="log"
          aria-live="polite"
          :aria-label="t('support.messagesAria')"
        >
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
          <template v-else>
            <p v-if="!messages.length" class="support-chat__status" role="status">
              {{ t('support.empty') }}
            </p>
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
          </template>
        </div>

        <footer v-if="!authRequired" class="support-chat__compose">
          <label class="visually-hidden" :for="INPUT_ID">{{ t('support.messageAria') }}</label>
          <textarea
            :id="INPUT_ID"
            ref="inputEl"
            v-model="draft"
            class="support-chat__input"
            data-testid="support-chat-input"
            rows="2"
            :maxlength="MAX_LENGTH"
            :placeholder="t('support.placeholder')"
            @keydown="onComposerKeydown"
          ></textarea>
          <div class="support-chat__compose-row">
            <span class="support-chat__count">{{ draft.length }}/{{ MAX_LENGTH }}</span>
            <button
              class="support-chat__send"
              type="button"
              data-testid="support-chat-send"
              :disabled="!canSend"
              @click="send"
            >
              {{ sending ? t('support.sending') : t('support.send') }}
            </button>
          </div>
          <p v-if="composeError" class="support-chat__error" role="alert">{{ composeError }}</p>
        </footer>
      </section>
    </Transition>
  </div>
</template>

<style scoped>
/* 需求 21：右下角【客服】按钮（图标 + 文字），与 PDP【联系商家】(bottom 96px)
   纵向错开；PDP 底部购物条出现时 body 挂 pdp-buybar-visible，按钮整体上移。 */
.support-chat__launcher {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 1100;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 48px;
  padding: 0 20px;
  border: 1px solid var(--colour-accent);
  border-radius: var(--radius-pill);
  background: var(--colour-surface);
  box-shadow: 0 4px 14px rgb(0 0 0 / 16%);
  color: var(--colour-accent);
  font: inherit;
  font-size: 14px;
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
  transition:
    bottom 160ms ease,
    background 160ms ease;
}

.support-chat__launcher:hover {
  background: var(--colour-accent-soft);
}

/* 整段选择器必须一起放进 :global()：Vue scoped 编译器会丢弃
   `:global(body.x) .child` 里的后代部分（只剩 body.x 规则）。 */
:global(body.pdp-buybar-visible .support-chat__launcher) {
  bottom: 84px;
}

.support-chat__panel {
  position: fixed;
  right: 24px;
  bottom: 84px;
  z-index: 1100;
  display: flex;
  width: min(24rem, calc(100vw - 32px));
  height: min(34rem, calc(100vh - 120px));
  flex-direction: column;
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  box-shadow:
    rgb(0 0 0 / 20%) 0 8px 10px -5px,
    rgb(0 0 0 / 14%) 0 16px 24px 2px,
    rgb(0 0 0 / 12%) 0 6px 30px 5px;
  overflow: hidden;
}

:global(body.pdp-buybar-visible .support-chat__panel) {
  bottom: 144px;
}

.support-chat__head {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
  padding: 14px 10px 14px 16px;
  border-bottom: 1px solid var(--colour-surface-soft);
}

.support-chat__avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  flex: none;
  border-radius: 50%;
  background: var(--colour-accent-soft);
  color: var(--colour-accent);
}

.support-chat__head-text {
  flex: 1;
  min-width: 0;
}

.support-chat__head-text h2 {
  margin: 0;
  color: var(--colour-text);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  line-height: 1.3;
}

.support-chat__head-text p {
  margin: 2px 0 0;
  color: var(--colour-muted);
  font-size: var(--font-size-xs);
}

.support-chat__close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  flex: none;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--colour-text);
  cursor: pointer;
}

.support-chat__close:hover {
  background: var(--colour-hover);
}

.support-chat__messages {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
  padding: 16px;
}

.support-chat__status {
  margin: 16px 0;
  color: var(--colour-muted);
  font-size: var(--font-size-md);
  text-align: center;
}

.support-chat__notice {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  margin: auto 0;
  padding: 20px 12px;
  border-radius: var(--radius-md);
  background: var(--colour-surface-soft);
  color: var(--colour-text-secondary);
  font-size: var(--font-size-md);
  text-align: center;
}

.support-chat__notice p {
  margin: 0;
}

.support-chat__link {
  color: var(--colour-accent);
  font-weight: var(--font-weight-medium);
  text-decoration: none;
}

.support-chat__link:hover {
  text-decoration: underline;
}

.support-chat__retry {
  padding: 6px 16px;
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-sm);
  background: var(--colour-surface);
  color: var(--colour-text);
  font: inherit;
  font-size: var(--font-size-sm);
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
  font-size: var(--font-size-xs);
  text-decoration: underline;
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
  background: var(--colour-surface-soft);
  color: var(--colour-text);
}

.support-chat__bubble--mine {
  border-radius: 12px 12px 4px;
  background: var(--colour-accent);
  color: var(--colour-white);
}

.support-chat__bubble--pending {
  opacity: 0.65;
}

.support-chat__bubble--failed {
  background: var(--colour-error-soft);
  color: var(--colour-text);
}

.support-chat__text {
  margin: 0;
  font-size: var(--font-size-md);
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
  color: var(--colour-muted);
  font-size: 11px;
}

.support-chat__bubble--mine .support-chat__meta {
  color: rgb(255 255 255 / 75%);
}

.support-chat__bubble--failed .support-chat__meta {
  color: var(--colour-muted);
}

.support-chat__compose {
  flex-shrink: 0;
  padding: 10px 16px 14px;
  border-top: 1px solid var(--colour-surface-soft);
}

.support-chat__input {
  box-sizing: border-box;
  width: 100%;
  padding: 9px 12px;
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-sm);
  resize: none;
  color: var(--colour-text);
  font: inherit;
  font-size: var(--font-size-md);
  line-height: 1.5;
}

.support-chat__input:focus {
  border-color: var(--colour-text);
  outline: none;
}

.support-chat__compose-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 8px;
}

.support-chat__count {
  color: var(--colour-muted);
  font-size: var(--font-size-xs);
}

.support-chat__send {
  min-width: 88px;
  height: 34px;
  padding: 0 18px;
  border: 0;
  border-radius: var(--radius-sm);
  background: var(--colour-accent);
  color: var(--colour-white);
  font: inherit;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
}

.support-chat__send:hover:not(:disabled) {
  background: var(--colour-accent-dark);
}

.support-chat__send:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.support-chat__error {
  margin: 8px 0 0;
  color: var(--colour-error);
  font-size: var(--font-size-sm);
}

.support-chat__launcher:focus-visible,
.support-chat__close:focus-visible,
.support-chat__retry:focus-visible,
.support-chat__link:focus-visible,
.support-chat__input:focus-visible,
.support-chat__send:focus-visible {
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
  .support-chat__launcher {
    right: 16px;
    bottom: 16px;
  }

  .support-chat__panel {
    right: 8px;
    bottom: 76px;
    width: calc(100vw - 16px);
    height: min(34rem, calc(100vh - 96px));
  }

  :global(body.pdp-buybar-visible .support-chat__launcher) {
    bottom: 80px;
  }

  :global(body.pdp-buybar-visible .support-chat__panel) {
    bottom: 140px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .support-chat-pop-enter-active,
  .support-chat-pop-leave-active {
    transition: none;
  }
}
</style>
