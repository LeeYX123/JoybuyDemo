<script setup>
import { nextTick, onMounted, reactive, ref } from 'vue'

import { apiRequest, merchantWrite } from '@/lib/api'

const state = reactive({
  loading: true,
  error: '',
  notice: '',
  conversations: [],
  activeId: '',
  active: null,
  loadingDetail: false,
  draft: '',
  sending: false,
})

const listEl = ref(null)

async function loadConversations() {
  state.loading = true
  state.error = ''
  try {
    const payload = await apiRequest('/merchant/conversations')
    state.conversations = payload.items || []
    if (!state.activeId && state.conversations.length) {
      await selectConversation(state.conversations[0].id)
    } else if (state.activeId) {
      await selectConversation(state.activeId, true)
    }
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

async function selectConversation(id, silent = false) {
  state.activeId = id
  state.loadingDetail = true
  if (!silent) state.active = null
  try {
    const payload = await apiRequest(`/merchant/conversations/${id}`)
    state.active = payload.conversation
    const row = state.conversations.find((item) => item.id === id)
    if (row) row.unread = 0
    await scrollToBottom()
  } catch (error) {
    state.error = error.message
  } finally {
    state.loadingDetail = false
  }
}

async function scrollToBottom() {
  await nextTick()
  if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
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

onMounted(loadConversations)
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>消息中心</h1>
        <p>客服中心用于充值与保证金沟通，买家咨询按商品来源单独列出，两者不混在一起。</p>
      </div>
    </div>

    <p v-if="state.error" class="notice notice--error">{{ state.error }}</p>

    <div class="chat-shell">
      <aside class="chat-list">
        <p v-if="state.loading" class="inline-loading">加载中…</p>
        <button
          v-for="row in state.conversations"
          :key="row.id"
          type="button"
          class="chat-list__item"
          :class="{ 'is-active': row.id === state.activeId }"
          @click="selectConversation(row.id)"
        >
          <span
            class="chat-list__avatar"
            :class="{ 'is-support': row.kind === 'PLATFORM_SUPPORT' }"
          >
            {{ row.kind === 'PLATFORM_SUPPORT' ? '客' : '买' }}
          </span>
          <span class="chat-list__main">
            <span class="chat-list__top">
              <b>{{ row.peer_name }}</b>
              <small>{{ fmtTime(row.last_message_at) }}</small>
            </span>
            <span class="chat-list__preview">{{ row.last_message || '暂无消息' }}</span>
          </span>
          <span v-if="row.unread" class="chat-list__badge">{{ row.unread }}</span>
        </button>
        <p v-if="!state.loading && !state.conversations.length" class="empty-state">还没有会话。</p>
      </aside>

      <section class="chat-panel">
        <template v-if="state.active">
          <header class="chat-panel__head">
            <div>
              <strong>{{ state.active.peer_name }}</strong>
              <span v-if="state.active.state" class="tag">{{ state.active.state }}</span>
            </div>
            <span class="cell-sub">{{
              state.active.kind === 'PLATFORM_SUPPORT' ? '平台客服会话' : '买家商品咨询'
            }}</span>
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
              :class="{ 'is-mine': message.sender === 'MERCHANT' }"
            >
              <div class="chat-bubble__meta">
                {{ message.author || message.sender }} · {{ fmtFull(message.created_at) }}
              </div>
              <div class="chat-bubble__text">{{ message.text }}</div>
            </div>
            <p v-if="!state.active.messages?.length" class="empty-state">
              还没有消息，先打个招呼吧。
            </p>
          </div>

          <footer class="chat-compose">
            <textarea
              v-model="state.draft"
              rows="3"
              placeholder="输入消息，Ctrl + Enter 发送"
              @keydown="onKeydown"
            />
            <div class="chat-compose__actions">
              <span class="hint-text">Ctrl + Enter 发送</span>
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
.chat-shell {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 16px;
  height: calc(100vh - 210px);
  min-height: 480px;
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
  padding: 12px 16px;
  border-bottom: 1px solid var(--line);
}

.chat-panel__head strong {
  margin-right: 8px;
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
</style>
