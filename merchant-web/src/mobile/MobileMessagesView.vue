<script setup>
import { nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useMerchantSession } from '@/composables/useMerchantSession'
import { apiRequest, merchantWrite } from '@/lib/api'
import { showToast } from '@/shell'

// 手机壳消息中心（folio route 9）：单栏双态——列表态（会话列表，客服中心
// 置顶，后端本就把 PLATFORM_SUPPORT 排在最前）/ 会话态（标题=对方名、商品
// 上下文条、气泡历史、右下角发送按钮、textarea 自动增高）。
// README 验收②：无关联订单的会话不显示订单号——后端会话 payload 只带
// product 不带订单号，本页任何位置都不渲染订单号，回复不受影响。

const route = useRoute()
const router = useRouter()
const { can } = useMerchantSession()

const state = reactive({
  loading: true,
  error: '',
  conversations: [],
  active: null,
  activeId: '',
  loadingDetail: false,
  draft: '',
  sending: false,
})

// 'list' 显示会话列表，'thread' 显示聊天面板（单栏双态）。
const view = ref('list')
const historyEl = ref(null)
const draftEl = ref(null)

async function loadConversations() {
  state.loading = true
  state.error = ''
  try {
    const payload = await apiRequest('/merchant/conversations')
    state.conversations = payload.items || []
    // 首页宫格「联系平台客服」落点：?open=support 换写成 ?c=<客服会话id>
    // （replace 不新增历史）。此时 loading 仍为 true，watcher 会跳过，
    // 所以换写完必须手动同步一次视图状态。
    if (route.query.open === 'support') {
      const support = state.conversations.find((row) => row.kind === 'PLATFORM_SUPPORT')
      if (support) {
        await router.replace({ path: '/messages', query: { c: support.id } })
        syncViewFromQuery()
        return
      }
    }
    syncViewFromQuery()
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

function syncViewFromQuery() {
  const id = String(route.query.c || '')
  if (id && state.conversations.some((row) => row.id === id)) {
    openConversation(id, { push: false })
  } else {
    view.value = 'list'
    state.active = null
    state.activeId = ''
  }
}

watch(
  () => route.query.c,
  () => {
    if (!state.loading) syncViewFromQuery()
  },
)

async function openConversation(id, { push = true } = {}) {
  if (push) {
    // folio routeStack 语义：会话态写成一条历史（?c=<id>），顶栏「返回」
    // 先回到列表态，再返回才离开消息页。
    router.push({ path: '/messages', query: { c: id } })
    return
  }
  view.value = 'thread'
  state.activeId = id
  state.loadingDetail = true
  state.active = null
  try {
    const payload = await apiRequest(`/merchant/conversations/${id}`)
    state.active = payload.conversation
    const row = state.conversations.find((item) => item.id === id)
    if (row) row.unread = 0
    await scrollToBottom()
    focusDraft()
  } catch (error) {
    state.error = error.message
    view.value = 'list'
  } finally {
    state.loadingDetail = false
  }
}

async function scrollToBottom() {
  await nextTick()
  if (historyEl.value) historyEl.value.scrollTop = historyEl.value.scrollHeight
}

// textarea 自动增高：input 时先回 auto 再取 scrollHeight，上限 96px（folio）。
function autosize() {
  const el = draftEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(96, Math.max(44, el.scrollHeight))}px`
}

function focusDraft() {
  nextTick(() => autosize())
}

async function send() {
  const text = state.draft.trim()
  if (!text || !state.active || state.sending) return
  state.sending = true
  state.error = ''
  try {
    const payload = await merchantWrite(`/merchant/conversations/${state.active.id}/messages`, {
      text,
    })
    state.active.messages.push(payload.message)
    state.draft = ''
    autosize()
    const row = state.conversations.find((item) => item.id === state.active.id)
    if (row) {
      row.last_message = payload.message.text
      row.last_message_at = payload.message.created_at
    }
    await scrollToBottom()
  } catch (error) {
    state.error = error.message
  } finally {
    state.sending = false
  }
}

function fmtTime(value) {
  if (!value) return ''
  return value.slice(5, 16).replace('T', ' ')
}

function fmtFull(value) {
  if (!value) return ''
  return value.slice(5, 16).replace('T', ' ')
}

function onKeydown(event) {
  // 手机壳不做 Ctrl+Enter：Enter 换行、点发送按钮发送（folio 行为）。
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault()
    send()
  }
}

onMounted(loadConversations)
onBeforeUnmount(() => {
  document.body.classList.remove('m-sheet-locked')
})
</script>

<template>
  <div class="m-page m-msg">
    <p v-if="state.error" class="m-error">{{ state.error }}</p>

    <!-- 列表态：会话列表，客服中心置顶（backend 排序已保证）。 -->
    <section v-if="view === 'list'" class="m-conv-list" aria-label="会话列表">
      <p v-if="state.loading" class="m-loading">加载中…</p>
      <button
        v-for="row in state.conversations"
        :key="row.id"
        type="button"
        class="m-conv"
        :class="{ 'is-support': row.kind === 'PLATFORM_SUPPORT' }"
        @click="openConversation(row.id)"
      >
        <span class="m-conv__avatar" :class="{ 'is-support': row.kind === 'PLATFORM_SUPPORT' }">
          {{ row.kind === 'PLATFORM_SUPPORT' ? '客' : (row.peer_name || '买').slice(0, 1) }}
        </span>
        <span class="m-conv__main">
          <span class="m-conv__top">
            <b>{{ row.peer_name }}</b>
            <small>{{ fmtTime(row.last_message_at) }}</small>
          </span>
          <span class="m-conv__preview">{{ row.last_message || '暂无消息' }}</span>
        </span>
        <span v-if="row.unread" class="m-conv__badge m-num">{{ row.unread > 99 ? '99+' : row.unread }}</span>
      </button>
      <p v-if="!state.loading && !state.conversations.length" class="m-empty">还没有会话。</p>
    </section>

    <!-- 会话态：标题=对方名 + 商品上下文条 + 气泡历史 + 右下角发送。 -->
    <section v-else class="m-thread" aria-label="聊天">
      <header class="m-thread__head">
        <strong>{{ state.active?.peer_name || '…' }}</strong>
        <span class="m-hint">{{ state.active?.kind === 'PLATFORM_SUPPORT' ? '平台客服会话' : '买家商品咨询' }}</span>
      </header>

      <!-- 商品上下文条（无关联商品则整条隐藏；本页不显示订单号）。 -->
      <div v-if="state.active?.product" class="m-thread__product">
        <img v-if="state.active.product.image" :src="state.active.product.image" alt="" />
        <span v-else class="m-thread__product-empty" aria-hidden="true">无图</span>
        <span class="m-thread__product-info">
          <strong>{{ state.active.product.name }}</strong>
          <small>{{ state.active.product.category }}<template v-if="state.active.product.price"> ｜ ¥ {{ state.active.product.price }}</template></small>
        </span>
      </div>

      <div ref="historyEl" class="m-thread__history">
        <p v-if="state.loadingDetail" class="m-loading">加载中…</p>
        <template v-else-if="state.active">
          <div
            v-for="message in state.active.messages"
            :key="message.id"
            class="m-bubble-row"
            :class="{ 'is-mine': message.sender === 'MERCHANT' }"
          >
            <span class="m-bubble">
              <span class="m-bubble__text">{{ message.text }}</span>
              <time>{{ (message.author ? message.author + ' · ' : '') + fmtFull(message.created_at) }}</time>
            </span>
          </div>
          <p v-if="!state.active.messages?.length" class="m-empty">还没有消息，先打个招呼吧。</p>
        </template>
      </div>

      <footer class="m-thread__composer">
        <textarea
          ref="draftEl"
          v-model="state.draft"
          rows="1"
          placeholder="输入消息"
          aria-label="输入消息"
          @input="autosize"
          @keydown="onKeydown"
        />
        <button
          type="button"
          class="m-btn m-btn--primary m-thread__send"
          :disabled="state.sending || !state.draft.trim()"
          @click="send"
        >
          {{ state.sending ? '发送中…' : '发送' }}
        </button>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.m-msg {
  gap: 0;
}

/* 会话列表。 */
.m-conv-list {
  display: grid;
  gap: 0;
  background: var(--m-paper);
  border: 1px solid var(--m-line);
  border-radius: var(--m-radius);
  overflow: hidden;
}

.m-conv {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: 64px;
  padding: 10px 12px;
  border: 0;
  border-top: 1px solid var(--m-line);
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.m-conv:first-child {
  border-top: 0;
}

.m-conv.is-support {
  background: #fffafb;
  border-bottom: 1px solid #f1dce0;
}

.m-conv:active {
  background: var(--m-tint);
}

.m-conv__avatar {
  flex: none;
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: #e8edf5;
  color: #4a5a72;
  font-size: 13px;
}

.m-conv__avatar.is-support {
  background: var(--m-accent);
  color: #fff;
}

.m-conv__main {
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 3px;
}

.m-conv__top {
  display: flex;
  justify-content: space-between;
  gap: var(--m-space-2);
}

.m-conv__top b {
  font-size: 14px;
  color: var(--m-ink);
}

.m-conv__top small {
  color: var(--m-muted);
  font-size: 11px;
}

.m-conv__preview {
  font-size: 12px;
  color: var(--m-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.m-conv__badge {
  flex: none;
  display: grid;
  place-items: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: var(--m-accent);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
}

/* 会话态：占满视口剩余高度（folio thread 高度语义）。 */
.m-thread {
  display: flex;
  flex-direction: column;
  height: max(306px, calc(100dvh - 118px));
  min-height: 0;
  background: var(--m-paper);
  border: 1px solid var(--m-line);
  border-radius: var(--m-radius);
  overflow: hidden;
}

.m-thread__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 4px 10px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--m-line);
}

.m-thread__head strong {
  font-size: 17px;
  color: var(--m-ink);
  overflow-wrap: anywhere;
}

/* 商品上下文条。 */
.m-thread__product {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr);
  gap: 9px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--m-line);
  background: #fffdfd;
}

.m-thread__product img {
  width: 44px;
  height: 44px;
  border-radius: 5px;
  border: 1px solid var(--m-line);
  object-fit: cover;
  background: #f7f8fa;
}

.m-thread__product-empty {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border-radius: 5px;
  border: 1px solid var(--m-line);
  background: #f7f8fa;
  color: var(--m-muted);
  font-size: 10px;
}

.m-thread__product-info {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.m-thread__product-info strong {
  margin: 0;
  font-size: 13px;
  line-height: 1.35;
  color: var(--m-ink);
  overflow-wrap: anywhere;
}

.m-thread__product-info small {
  color: var(--m-muted);
  font-size: 12px;
  overflow-wrap: anywhere;
}

/* 气泡历史。 */
.m-thread__history {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 14px 12px 6px;
  background: var(--m-canvas);
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.m-bubble-row {
  display: flex;
  gap: 8px;
}

.m-bubble-row.is-mine {
  justify-content: flex-end;
}

.m-bubble {
  max-width: 85%;
  display: grid;
  gap: 4px;
}

.m-bubble__text {
  padding: 9px 11px;
  border-radius: 0 8px 8px 8px;
  background: var(--m-paper);
  border: 1px solid var(--m-line);
  color: var(--m-ink);
  font-size: 14px;
  line-height: 1.5;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
  word-break: break-word;
}

.m-bubble-row.is-mine .m-bubble__text {
  background: var(--m-tint);
  border-color: #f6dfe3;
  border-radius: 8px 0 8px 8px;
}

.m-bubble time {
  color: var(--m-muted);
  font-size: 11px;
}

.m-bubble-row.is-mine time {
  text-align: end;
}

/* 底部 composer：右下角发送按钮 + textarea 自动增高。 */
.m-thread__composer {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: var(--m-space-2);
  padding: 10px 12px max(10px, env(safe-area-inset-bottom));
  border-top: 1px solid var(--m-line);
  background: var(--m-paper);
}

.m-thread__composer textarea {
  display: block;
  min-width: 0;
  min-height: 44px;
  height: 44px;
  max-height: 96px;
  padding: 10px;
  border: 1px solid var(--m-line);
  border-radius: 9px;
  background: var(--m-canvas);
  color: var(--m-ink);
  font: inherit;
  font-size: 16px;
  line-height: 22px;
  resize: none;
}

.m-thread__send {
  min-width: 64px;
}
</style>
