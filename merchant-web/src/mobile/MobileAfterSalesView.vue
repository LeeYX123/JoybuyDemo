<script setup>
import { onMounted, reactive, ref } from 'vue'

import SheetModal from '@/mobile/components/SheetModal.vue'
import { apiRequest, merchantWrite } from '@/lib/api'
import { showToast } from '@/shell'

// 手机壳售后中心（folio route 7）：chips → 售后卡片（类型+状态/标题/进度/
// 单号+关联订单/操作）+ 折叠「售后处理规则」。详情与处理动作走既有
// /merchant/after-sales/{id}/actions 端点（progress/result/escalate）。

const PAGE_SIZE = 10

const KIND_TABS = [
  { key: 'ALL', label: '全部售后' },
  { key: 'COMPLAINT', label: '用户投诉' },
  { key: 'RETURN', label: '退货订单' },
]

const KIND_LABELS = { COMPLAINT: '用户投诉', RETURN: '退货订单' }

const STATE_LABELS = {
  PENDING: '待处理',
  PROCESSING: '处理中',
  PLATFORM: '平台介入中',
  COMPLETED: '已完成',
  REJECTED: '已驳回',
}

const STATE_TAG = {
  PENDING: 'm-tag--warn',
  PROCESSING: 'm-tag--warn',
  PLATFORM: 'm-tag--danger',
  COMPLETED: 'm-tag--ok',
  REJECTED: 'm-tag--ok',
}

const state = reactive({
  kind: 'ALL',
  q: '',
  page: 1,
  loading: true,
  error: '',
  notice: '',
  items: [],
  counts: {},
  total: 0,
  hasNext: false,
})

const detail = reactive({
  open: false,
  loading: false,
  value: null,
  progress: '',
  result: '',
  note: '',
  busy: false,
  error: '',
})

async function load() {
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page: String(state.page), page_size: String(PAGE_SIZE) })
    if (state.kind !== 'ALL') params.set('kind', state.kind)
    if (state.q.trim()) params.set('q', state.q.trim())
    const payload = await apiRequest(`/merchant/after-sales?${params}`)
    state.items = payload.items || []
    state.counts = payload.counts || {}
    state.total = payload.total || 0
    state.hasNext = Boolean(payload.has_next)
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

function selectKind(key) {
  state.kind = key
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
  detail.error = ''
  detail.progress = ''
  detail.result = ''
  detail.note = ''
  try {
    const payload = await apiRequest(`/merchant/after-sales/${row.id}`)
    detail.value = payload.after_sale
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

async function submitAction(action) {
  if (!detail.value) return
  detail.busy = true
  detail.error = ''
  try {
    const payload =
      action === 'progress'
        ? { action, progress: detail.progress }
        : action === 'escalate'
          ? { action, note: detail.note }
          : { action, result: detail.result }
    await merchantWrite(`/merchant/after-sales/${detail.value.id}/actions`, payload)
    state.notice = '售后处理已更新。'
    showToast(state.notice)
    await openDetail({ id: detail.value.id })
    await load()
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

onMounted(load)
</script>

<template>
  <div class="m-page">
    <!-- chips。 -->
    <div class="m-chips" role="tablist" aria-label="售后类型">
      <button
        v-for="tab in KIND_TABS"
        :key="tab.key"
        type="button"
        class="m-chip"
        role="tab"
        :aria-selected="state.kind === tab.key"
        :class="{ 'is-active': state.kind === tab.key }"
        @click="selectKind(tab.key)"
      >
        {{ tab.label }}
        <span class="m-chip__count m-num">{{ state.counts[tab.key] ?? 0 }}</span>
      </button>
    </div>

    <!-- 搜索。 -->
    <form class="m-controls" role="search" @submit.prevent="search">
      <input
        v-model="state.q"
        class="m-controls__input"
        type="search"
        enterkeyhint="search"
        placeholder="搜索售后单号 / 订单号 / 问题描述"
        aria-label="搜索售后"
      />
      <button type="submit" class="m-controls__action">查询</button>
    </form>

    <p v-if="state.error" class="m-error">{{ state.error }}</p>
    <p v-if="state.notice" class="m-notice">{{ state.notice }}</p>
    <p v-if="state.loading" class="m-loading">加载中…</p>

    <!-- 售后卡片流（folio service-cases）。 -->
    <div v-else-if="state.items.length" class="m-cases">
      <article v-for="row in state.items" :key="row.id" class="m-case">
        <div class="m-case__heading">
          <span>{{ KIND_LABELS[row.kind] || row.kind }}</span>
          <span class="m-tag" :class="STATE_TAG[row.state]">
            {{ STATE_LABELS[row.state] || row.state }}
          </span>
        </div>
        <h2>{{ row.issue || '—' }}</h2>
        <p class="m-case__progress">处理进度：{{ row.progress || '暂无记录' }}</p>
        <dl>
          <div><dt>售后单号</dt><dd class="m-num">{{ row.id.slice(0, 8) }}…</dd></div>
          <div><dt>关联订单</dt><dd class="m-num">{{ row.order_id.slice(0, 8) }}…</dd></div>
          <div><dt>提交时间</dt><dd>{{ fmtDate(row.created_at) }}</dd></div>
        </dl>
        <div class="m-case__actions">
          <button type="button" class="m-btn" @click="openDetail(row)">
            {{ row.readonly ? '查看详情' : '处理售后' }}
          </button>
        </div>
      </article>
    </div>
    <p v-else class="m-empty">该类型下没有售后单。</p>

    <div v-if="state.total" class="m-pager">
      <button type="button" class="m-btn" :disabled="state.page <= 1" @click="state.page -= 1; load()">上一页</button>
      <span class="m-num">第 {{ state.page }} 页 · 共 {{ state.total }} 单</span>
      <button type="button" class="m-btn" :disabled="!state.hasNext" @click="state.page += 1; load()">下一页</button>
    </div>

    <!-- 折叠售后处理规则（folio mobile-disclosure）。 -->
    <details class="m-disclosure">
      <summary>售后处理规则</summary>
      <div class="m-disclosure__body m-hint">
        投诉咨询可以继续处理；订单收货成功后，不支持发起退货类售后。处理结果完成时必填结论，
        需要平台协助时可以申请平台介入。
      </div>
    </details>

    <!-- 售后详情 sheet：字段 + 处理历史 + 处理动作（progress / escalate / result）。 -->
    <SheetModal :open="detail.open" title="售后详情" @close="closeDetail">
      <p v-if="detail.loading" class="m-loading">加载中…</p>
      <template v-else-if="detail.value">
        <dl class="m-dl">
          <div><dt>售后单号</dt><dd class="m-num">{{ detail.value.id }}</dd></div>
          <div><dt>关联订单</dt><dd class="m-num">{{ detail.value.order_id }}</dd></div>
          <div><dt>类型</dt><dd>{{ KIND_LABELS[detail.value.kind] || detail.value.kind }}</dd></div>
          <div><dt>状态</dt><dd>{{ STATE_LABELS[detail.value.state] || detail.value.state }}</dd></div>
          <div><dt>提交时间</dt><dd>{{ fmtDate(detail.value.created_at) }}</dd></div>
          <div><dt>完成时间</dt><dd>{{ fmtDate(detail.value.completed_at) }}</dd></div>
        </dl>

        <h3 class="m-detail-title">问题描述</h3>
        <p class="m-hint" style="margin: 0">{{ detail.value.issue || '—' }}</p>

        <div v-if="detail.value.product" class="m-detail-block">
          <h3 class="m-detail-title">关联商品</h3>
          <p class="m-hint" style="margin: 0">
            {{ detail.value.product.title }} · 数量 {{ detail.value.product.quantity }} · 单价 ¥
            {{ detail.value.product.unit_price }}
          </p>
        </div>

        <div v-if="detail.value.events?.length" class="m-detail-block">
          <h3 class="m-detail-title">处理历史</h3>
          <ol class="m-events">
            <li v-for="event in detail.value.events" :key="event.id">
              <span class="m-events__title">
                {{ event.action }}
                <small>（{{ event.actor_label || event.actor }}）</small>
              </span>
              <small class="m-events__time">{{ fmtDate(event.created_at) }}</small>
              <span v-if="event.content" class="m-events__content">{{ event.content }}</span>
            </li>
          </ol>
        </div>

        <template v-if="!detail.value.readonly">
          <div class="m-detail-block">
            <label class="m-field">
              <span class="m-field__label">更新处理进度</span>
              <input v-model="detail.progress" class="m-input" type="text" placeholder="例如 已联系买家核实情况" />
            </label>
            <button
              type="button"
              class="m-btn m-btn--block"
              :disabled="detail.busy || !detail.progress"
              @click="submitAction('progress')"
            >
              保存进度
            </button>
            <label class="m-field">
              <span class="m-field__label">申请平台介入（可选说明）</span>
              <input v-model="detail.note" class="m-input" type="text" placeholder="说明需要平台协助的原因" />
            </label>
            <button
              type="button"
              class="m-btn m-btn--block"
              :disabled="detail.busy || detail.value.state === 'PLATFORM'"
              @click="submitAction('escalate')"
            >
              申请平台介入
            </button>
            <label class="m-field">
              <span class="m-field__label">处理结果（完成时必填）</span>
              <textarea v-model="detail.result" class="m-textarea" rows="3" placeholder="填写处理结论" />
            </label>
            <button
              type="button"
              class="m-btn m-btn--primary m-btn--block"
              :disabled="detail.busy || !detail.result"
              @click="submitAction('result')"
            >
              完成处理
            </button>
            <p v-if="detail.error" class="m-error">{{ detail.error }}</p>
          </div>
        </template>
      </template>
    </SheetModal>
  </div>
</template>

<style scoped>
.m-controls {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 4px 3px 12px;
  border: 1px solid var(--m-line);
  border-radius: 10px;
  background: var(--m-paper);
}

.m-controls__input {
  flex: 1 1 0;
  width: 0;
  min-width: 0;
  min-height: 40px;
  border: 0;
  background: transparent;
  font-size: 16px;
  color: var(--m-ink);
}

.m-controls__input:focus-visible {
  outline: none;
}

.m-controls__action {
  flex: none;
  min-height: 40px;
  padding: 0 10px;
  border: 0;
  background: transparent;
  color: var(--m-accent);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

/* 售后卡片（folio service-case）。 */
.m-cases {
  display: grid;
  gap: 14px;
}

.m-case {
  padding: 12px;
  border: 1px solid var(--m-line);
  border-radius: var(--m-radius);
  background: var(--m-paper);
}

.m-case__heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--m-space-2);
  font-size: 12px;
  color: var(--m-muted);
}

.m-case h2 {
  margin: 6px 0 4px;
  font-size: 15px;
  color: var(--m-ink);
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.m-case__progress {
  margin: 0;
  color: var(--m-muted);
  font-size: 13px;
  overflow-wrap: anywhere;
}

.m-case dl {
  display: grid;
  gap: 5px;
  margin: 10px 0 0;
  padding: 8px 0 0;
  border-top: 1px solid var(--m-line);
  font-size: 12px;
}

.m-case dl > div {
  display: flex;
  justify-content: space-between;
  gap: var(--m-space-2);
}

.m-case dt {
  color: var(--m-muted);
  flex: none;
}

.m-case dd {
  margin: 0;
  color: var(--m-ink);
  text-align: right;
  overflow-wrap: anywhere;
}

.m-case__actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}

.m-case__actions .m-btn {
  min-height: 40px;
  padding: 0 14px;
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

.m-disclosure {
  border: 1px solid var(--m-line);
  border-radius: var(--m-radius);
  background: var(--m-paper);
}

.m-disclosure summary {
  min-height: var(--m-target);
  padding: 12px;
  font-size: 14px;
  font-weight: 650;
  color: var(--m-ink);
  cursor: pointer;
  list-style: none;
}

.m-disclosure summary::-webkit-details-marker {
  display: none;
}

.m-disclosure__body {
  padding: 0 12px 12px;
}

/* 详情 sheet 内容。 */
.m-dl {
  display: grid;
  gap: 10px;
  margin: 0 0 4px;
}

.m-dl > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
}

.m-dl dt {
  color: var(--m-muted);
  flex: none;
}

.m-dl dd {
  margin: 0;
  color: var(--m-ink);
  text-align: right;
  overflow-wrap: anywhere;
}

.m-detail-title {
  margin: 14px 0 6px;
  font-size: 13px;
  color: var(--m-ink);
}

.m-detail-block {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--m-line);
  display: grid;
  gap: var(--m-space-2);
}

.m-events {
  margin: 0;
  padding: 0 0 0 16px;
  display: grid;
  gap: 8px;
}

.m-events li {
  display: grid;
  gap: 2px;
  font-size: 12px;
}

.m-events__title {
  color: var(--m-ink);
  font-weight: 600;
}

.m-events__title small {
  color: var(--m-muted);
  font-weight: 400;
}

.m-events__time {
  color: var(--m-muted);
}

.m-events__content {
  color: var(--m-muted);
  overflow-wrap: anywhere;
}
</style>
