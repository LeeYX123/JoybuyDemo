<script setup>
import { onMounted, reactive, ref } from 'vue'

import SheetModal from '@/mobile/components/SheetModal.vue'
import { apiRequest, merchantWrite } from '@/lib/api'
import { showToast } from '@/shell'

// 手机壳通知中心（folio route 10）：全部/已读/未读 chips → 整行可点通知行
// （标题+摘要+时间+chevron，未读态区分）→ 点击打开详情 sheet（打开即已读，
// 走既有 /merchant/notifications/{id} 详情端点），详情内可回复（复用
// /merchant/notifications/{id}/replies）。

const STATE_TABS = [
  { key: 'ALL', label: '全部' },
  { key: 'UNREAD', label: '未读' },
  { key: 'READ', label: '已读' },
]

const state = reactive({
  tab: 'ALL',
  page: 1,
  loading: true,
  error: '',
  items: [],
  counts: {},
  total: 0,
})

const detail = reactive({
  open: false,
  loading: false,
  value: null,
  reply: '',
  busy: false,
  error: '',
})

async function load() {
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page: String(state.page), page_size: '10' })
    if (state.tab !== 'ALL') params.set('state', state.tab)
    const payload = await apiRequest(`/merchant/notifications?${params}`)
    state.items = payload.items || []
    state.counts = payload.counts || {}
    state.total = payload.total || 0
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

function selectTab(key) {
  state.tab = key
  state.page = 1
  load()
}

async function openDetail(row) {
  detail.open = true
  detail.loading = true
  detail.value = null
  detail.reply = ''
  detail.error = ''
  try {
    // 详情端点在打开时标记已读，随后刷新列表让未读态同步。
    const payload = await apiRequest(`/merchant/notifications/${row.id}`)
    detail.value = payload.notification
    await load()
  } catch (error) {
    state.error = error.message
    detail.open = false
  } finally {
    detail.loading = false
  }
}

async function submitReply() {
  const content = detail.reply.trim()
  if (!content || !detail.value) return
  detail.busy = true
  detail.error = ''
  try {
    const payload = await merchantWrite(`/merchant/notifications/${detail.value.id}/replies`, {
      content,
    })
    detail.value.replies.push(payload.reply)
    detail.value.reply_count += 1
    detail.reply = ''
    showToast('回复已发送')
  } catch (error) {
    detail.error = error.message
  } finally {
    detail.busy = false
  }
}

function fmtDate(value) {
  if (!value) return '—'
  return value.slice(0, 16).replace('T', ' ')
}

function summarize(text) {
  if (!text) return ''
  return text.length > 46 ? `${text.slice(0, 46)}…` : text
}

onMounted(load)
</script>

<template>
  <div class="m-page">
    <!-- chips（folio tabs → m-chips）。 -->
    <div class="m-chips" role="tablist" aria-label="通知状态">
      <button
        v-for="tab in STATE_TABS"
        :key="tab.key"
        type="button"
        class="m-chip"
        role="tab"
        :aria-selected="state.tab === tab.key"
        :class="{ 'is-active': state.tab === tab.key }"
        @click="selectTab(tab.key)"
      >
        {{ tab.label }}
        <span class="m-chip__count m-num">{{ state.counts[tab.key] ?? 0 }}</span>
      </button>
    </div>

    <p v-if="state.error" class="m-error">{{ state.error }}</p>
    <p v-if="state.loading" class="m-loading">加载中…</p>

    <!-- 整行可点通知行（folio merchant-notice-row）。 -->
    <section v-else-if="state.items.length" class="m-card">
      <button
        v-for="row in state.items"
        :key="row.id"
        type="button"
        class="m-notice-row"
        :data-read="row.read"
        :aria-label="row.read ? row.title : `未读通知：${row.title}`"
        @click="openDetail(row)"
      >
        <span class="m-notice-row__summary">
          <strong>{{ row.title }}</strong>
          <span>{{ summarize(row.content) }}</span>
          <small class="m-num">{{ fmtDate(row.created_at) }}</small>
        </span>
        <span class="m-notice-row__chevron" aria-hidden="true">›</span>
      </button>
    </section>
    <p v-else class="m-empty">该状态下没有通知。</p>

    <div v-if="state.total" class="m-pager">
      <button type="button" class="m-btn" :disabled="state.page <= 1" @click="state.page -= 1; load()">上一页</button>
      <span class="m-num">第 {{ state.page }} 页 · 共 {{ state.total }} 条</span>
      <button type="button" class="m-btn" :disabled="state.page * 10 >= state.total" @click="state.page += 1; load()">下一页</button>
    </div>

    <!-- 通知详情 sheet：内容/图片/关联订单/回复。 -->
    <SheetModal :open="detail.open" :title="detail.value?.title || '通知详情'" @close="detail.open = false">
      <p v-if="detail.loading" class="m-loading">加载中…</p>
      <template v-else-if="detail.value">
        <p class="m-hint" style="margin: 0 0 12px">{{ fmtDate(detail.value.created_at) }}<template v-if="detail.value.order"> ｜ 关联订单 {{ detail.value.order.order_no }}</template></p>
        <p class="m-notice-content" style="margin: 0">{{ detail.value.content }}</p>

        <div v-if="detail.value.images?.length" class="m-notice-images">
          <img v-for="url in detail.value.images" :key="url" :src="url" alt="通知配图" />
        </div>

        <div v-if="detail.value.replies?.length" class="m-notice-replies">
          <h3>回复（{{ detail.value.reply_count }}）</h3>
          <p v-for="reply in detail.value.replies" :key="reply.id" class="m-notice-reply">
            <b>{{ reply.author || (reply.role === 'MERCHANT' ? '我' : '平台') }}</b>
            <span>{{ reply.content }}</span>
            <small class="m-num">{{ fmtDate(reply.created_at) }}</small>
          </p>
        </div>

        <form class="m-sheet-form" @submit.prevent="submitReply">
          <label class="m-field">
            <span class="m-field__label">回复平台（可选）</span>
            <textarea v-model="detail.reply" class="m-textarea" rows="2" placeholder="填写回复内容" />
          </label>
          <p v-if="detail.error" class="m-error">{{ detail.error }}</p>
          <button type="submit" class="m-btn m-btn--primary m-btn--block" :disabled="detail.busy || !detail.reply.trim()">
            {{ detail.busy ? '发送中…' : '发送回复' }}
          </button>
        </form>
      </template>
    </SheetModal>
  </div>
</template>

<style scoped>
/* 通知行（folio merchant-notice-row：整行按钮、未读态区分）。 */
.m-notice-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--m-space-2);
  width: 100%;
  min-height: 66px;
  padding: var(--m-space-3) var(--m-space-3);
  border: 0;
  border-top: 1px solid var(--m-line);
  background: var(--m-paper);
  text-align: left;
  cursor: pointer;
  font: inherit;
}

.m-notice-row:first-child {
  border-top: 0;
}

.m-notice-row[data-read='false'] {
  background: #fffafc;
}

.m-notice-row[data-read='false'] .m-notice-row__summary strong {
  font-weight: 650;
}

.m-notice-row__summary {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.m-notice-row__summary strong {
  margin: 0;
  color: var(--m-ink);
  font-size: 14px;
  font-weight: 500;
  overflow-wrap: anywhere;
}

.m-notice-row__summary span {
  color: var(--m-muted);
  font-size: 13px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.m-notice-row__summary small {
  color: var(--m-muted);
  font-size: 12px;
}

.m-notice-row__chevron {
  color: var(--m-muted);
  font-size: 20px;
}

.m-pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--m-space-2);
}

.m-pager span {
  font-size: 12px;
  color: var(--m-muted);
}

.m-pager .m-btn {
  min-height: 40px;
  padding: 0 14px;
}

.m-notice-content {
  font-size: 14px;
  line-height: 1.7;
  color: var(--m-ink);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.m-notice-images {
  display: flex;
  gap: var(--m-space-2);
  flex-wrap: wrap;
  margin-top: 12px;
}

.m-notice-images img {
  width: 80px;
  height: 80px;
  object-fit: cover;
  border-radius: 5px;
  border: 1px solid var(--m-line);
}

.m-notice-replies {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--m-line);
}

.m-notice-replies h3 {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--m-ink);
}

.m-notice-reply {
  display: grid;
  gap: 2px;
  margin: 0 0 10px;
  padding: 8px 10px;
  border-radius: var(--m-radius);
  background: var(--m-canvas);
  font-size: 13px;
}

.m-notice-reply b {
  color: var(--m-ink);
}

.m-notice-reply span {
  color: var(--m-muted);
  overflow-wrap: anywhere;
}

.m-notice-reply small {
  color: var(--m-muted);
  font-size: 11px;
}

.m-sheet-form {
  display: grid;
  gap: var(--m-space-3);
  margin-top: 14px;
}
</style>
