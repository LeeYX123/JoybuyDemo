<script setup>
import { onMounted, reactive, ref } from 'vue'

import AppModal from '@/components/AppModal.vue'
import { adminWrite } from '@/composables/useAdminApi'
import { apiRequest } from '@/lib/api'

const TABS = [
  { key: '', label: '全部会话' },
  { key: 'PENDING', label: '待回复' },
  { key: 'PROCESSING', label: '处理中' },
  { key: 'RESOLVED', label: '已解决' },
]

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

onMounted(load)
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>客服中心</h1>
        <p>接待商家咨询并跟进充值、保证金、解封等问题；回复本身不代替资金或解封操作。</p>
      </div>
      <div class="page-intro__actions">
        <button type="button" class="btn btn--primary" @click="createOpen = true">
          发起客服会话
        </button>
      </div>
    </div>

    <p v-if="state.error" class="notice notice--error" style="margin-bottom: 14px">
      {{ state.error }}
    </p>

    <div class="support-layout">
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

.support-filter {
  display: grid;
  gap: 8px;
  padding: 12px;
  border-bottom: 1px solid var(--panel-subtle-border);
  background: var(--panel-subtle);
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
