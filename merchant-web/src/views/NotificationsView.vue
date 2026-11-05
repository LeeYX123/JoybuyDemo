<script setup>
import { onMounted, reactive } from 'vue'

import AppDrawer from '@/components/AppDrawer.vue'
import AppModal from '@/components/AppModal.vue'
import { apiRequest, merchantWrite } from '@/lib/api'

const STATE_TABS = [
  { key: 'ALL', label: '全部通知' },
  { key: 'UNREAD', label: '未读' },
  { key: 'READ', label: '已读' },
]

const state = reactive({
  tab: 'ALL',
  q: '',
  page: 1,
  loading: true,
  error: '',
  notice: '',
  items: [],
  counts: {},
  total: 0,
})

const detail = reactive({
  value: null,
  open: false,
  loading: false,
  reply: '',
  busy: false,
  error: '',
})

const viewer = reactive({ open: false, src: '' })

async function load() {
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page: String(state.page), page_size: '10' })
    if (state.tab !== 'ALL') params.set('state', state.tab)
    if (state.q.trim()) params.set('q', state.q.trim())
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

function search() {
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

function closeDetail() {
  if (detail.busy) return
  detail.open = false
  detail.value = null
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
  } catch (error) {
    detail.error = error.message
  } finally {
    detail.busy = false
  }
}

async function markAllRead() {
  state.error = ''
  try {
    const payload = await merchantWrite('/merchant/notifications/mark-all-read', {})
    state.notice = `已标记 ${payload.updated} 条通知为已读。`
    await load()
  } catch (error) {
    state.error = error.message
  }
}

function zoom(src) {
  viewer.src = src
  viewer.open = true
}

function closeViewer() {
  viewer.open = false
  viewer.src = ''
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
  <section>
    <div class="page-intro">
      <div>
        <h1>平台通知中心</h1>
        <p>普通通知与商品好评统一列表；平台新回复会让通知重新变为未读。</p>
      </div>
      <div class="page-intro__actions">
        <button type="button" class="btn btn--sm" @click="markAllRead">全部标记已读</button>
      </div>
    </div>

    <p v-if="state.error" class="notice notice--error">{{ state.error }}</p>
    <p v-if="state.notice" class="notice notice--ok">{{ state.notice }}</p>

    <div class="tabs">
      <button
        v-for="tab in STATE_TABS"
        :key="tab.key"
        type="button"
        :class="{ 'is-active': state.tab === tab.key }"
        @click="selectTab(tab.key)"
      >
        {{ tab.label }}
        <span class="tab-count">{{ state.counts[tab.key] ?? 0 }}</span>
      </button>
    </div>

    <div class="toolbar">
      <form class="filter-row" @submit.prevent="search">
        <input v-model="state.q" type="search" placeholder="搜索通知标题或内容" />
        <button type="submit" class="btn btn--primary">搜索</button>
      </form>
    </div>

    <div class="card">
      <div class="card__body">
        <p v-if="state.loading" class="inline-loading">加载中…</p>
        <ul v-else-if="state.items.length" class="notice-list">
          <li v-for="row in state.items" :key="row.id" :class="{ 'is-unread': !row.read }">
            <div class="notice-list__main">
              <div class="notice-list__head">
                <span v-if="!row.read" class="notice-dot" aria-label="未读"></span>
                <b>{{ row.title }}</b>
                <span v-if="row.kind === 'REVIEW'" class="tag tag--red">商品好评</span>
                <span class="cell-sub">{{ fmtDate(row.created_at) }}</span>
              </div>
              <p class="notice-list__summary">{{ summarize(row.content) }}</p>
              <p v-if="row.reply_count" class="cell-sub">已有 {{ row.reply_count }} 条回复</p>
            </div>
            <button type="button" class="btn btn--sm" @click="openDetail(row)">
              {{ row.kind === 'REVIEW' ? '查看好评' : '查看详情' }}
            </button>
          </li>
        </ul>
        <p v-else class="empty-state">没有符合条件的通知。</p>
      </div>
    </div>

    <AppDrawer :open="detail.open" title="通知详情" @close="closeDetail">
      <p v-if="detail.loading" class="inline-loading">加载中…</p>
      <template v-else-if="detail.value">
        <h2 class="notice-detail__title">{{ detail.value.title }}</h2>

        <template v-if="detail.value.kind === 'REVIEW'">
          <p class="review-stars" :aria-label="`${detail.value.rating} 星`">
            {{ '★'.repeat(detail.value.rating || 0)
            }}{{ '☆'.repeat(5 - (detail.value.rating || 0)) }}
          </p>
          <p class="review-content">{{ detail.value.content }}</p>
          <div v-if="detail.value.images?.length" class="review-images">
            <img
              v-for="src in detail.value.images"
              :key="src"
              :src="src"
              alt="评论图片"
              @click="zoom(src)"
            />
          </div>
          <p class="cell-sub">评论时间：{{ fmtDate(detail.value.created_at) }}</p>

          <template v-if="detail.value.product">
            <h3 class="section-title">商品信息</h3>
            <dl class="detail-grid">
              <div>
                <dt>商品</dt>
                <dd>{{ detail.value.product.name }}</dd>
              </div>
              <div>
                <dt>品类</dt>
                <dd>{{ detail.value.product.category || '—' }}</dd>
              </div>
              <div>
                <dt>零售价</dt>
                <dd class="num">¥ {{ detail.value.product.price || '—' }}</dd>
              </div>
              <div>
                <dt>成本价</dt>
                <dd class="num">¥ {{ detail.value.product.cost || '—' }}</dd>
              </div>
            </dl>
            <p class="hint-text">
              商品信息为推送时的快照，后续改价不影响这条好评；好评由平台运营推送，不代表买家公开评价。
            </p>
          </template>
        </template>

        <template v-else>
          <p class="muted-text">{{ detail.value.content }}</p>
          <p class="cell-sub">发送时间：{{ fmtDate(detail.value.created_at) }}</p>
        </template>

        <h3 class="section-title">往来回复</h3>
        <div v-if="detail.value.replies?.length" class="reply-list">
          <div
            v-for="reply in detail.value.replies"
            :key="reply.id"
            class="reply-item"
            :class="{ 'is-mine': reply.role === 'MERCHANT' }"
          >
            <div class="reply-item__meta">
              {{ reply.role === 'PLATFORM' ? '平台' : '本店' }} · {{ reply.author || '' }} ·
              {{ fmtDate(reply.created_at) }}
            </div>
            <div class="reply-item__body">{{ reply.content }}</div>
          </div>
        </div>
        <p v-else class="empty-state">还没有回复。</p>

        <label class="field">
          <span class="field__label">回复（1–1000 字）</span>
          <textarea v-model="detail.reply" rows="3" maxlength="1000" placeholder="输入回复内容" />
        </label>
        <p v-if="detail.error" class="notice notice--error">{{ detail.error }}</p>
        <div class="form-actions">
          <button
            type="button"
            class="btn btn--primary"
            :disabled="detail.busy || !detail.reply.trim()"
            @click="submitReply"
          >
            发送回复
          </button>
        </div>
      </template>
    </AppDrawer>

    <AppModal
      :open="viewer.open"
      title="查看图片"
      confirm-text="关闭"
      @cancel="closeViewer"
      @confirm="closeViewer"
    >
      <img v-if="viewer.src" class="image-viewer" :src="viewer.src" alt="评论图片" />
    </AppModal>
  </section>
</template>

<style scoped>
.tab-count {
  margin-left: 6px;
  font-size: 11px;
  color: var(--muted);
}

.filter-row {
  display: flex;
  gap: 8px;
  max-width: 420px;
}

.filter-row input {
  flex: 1;
}

.notice-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.notice-list li {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 4px;
  border-bottom: 1px solid var(--line);
}

.notice-list li:last-child {
  border-bottom: none;
}

.notice-list__main {
  flex: 1;
  min-width: 0;
}

.notice-list__head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.notice-list__head .cell-sub {
  margin-left: auto;
}

.notice-list__summary {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--muted);
}

.notice-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--red);
  display: inline-block;
}

.notice-detail__title {
  margin: 0 0 12px;
  font-size: 18px;
}

.review-stars {
  color: #f5a623;
  font-size: 20px;
  letter-spacing: 2px;
  margin: 0 0 8px;
}

.review-content {
  font-size: 14px;
  line-height: 1.7;
  margin: 0 0 12px;
}

.review-images {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.review-images img {
  width: 84px;
  height: 84px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid var(--line);
  cursor: zoom-in;
}

.reply-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 16px;
}

.reply-item__meta {
  font-size: 11px;
  color: var(--muted);
  margin-bottom: 4px;
}

.reply-item__body {
  background: #f5f7fa;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 13px;
  line-height: 1.6;
}

.reply-item.is-mine .reply-item__body {
  background: var(--red-soft);
}

.image-viewer {
  width: 100%;
  border-radius: 6px;
}
</style>
