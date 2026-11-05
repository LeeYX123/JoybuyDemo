<script setup>
import { onMounted, reactive } from 'vue'

import AppDrawer from '@/components/AppDrawer.vue'
import AppPager from '@/components/AppPager.vue'
import ImageUploader from '@/components/ImageUploader.vue'
import { apiRequest, merchantWrite } from '@/lib/api'

const PAGE_SIZE = 10

const KIND_TABS = [
  { key: 'ALL', label: '全部售后' },
  { key: 'COMPLAINT', label: '用户投诉' },
  { key: 'RETURN', label: '退货订单' },
]

const STATE_LABELS = {
  PENDING: '待处理',
  PROCESSING: '处理中',
  PLATFORM: '平台介入中',
  COMPLETED: '已完成',
  REJECTED: '已驳回',
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
  value: null,
  open: false,
  loading: false,
  progress: '',
  result: '',
  note: '',
  proof: [],
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

function goPage(page) {
  state.page = page
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
  detail.proof = []
  try {
    const payload = await apiRequest(`/merchant/after-sales/${row.id}`)
    detail.value = payload.after_sale
    detail.proof = [...(payload.after_sale.proof || [])]
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
          : action === 'proof'
            ? { action, images: detail.proof }
            : { action, result: detail.result }
    const response = await merchantWrite(
      `/merchant/after-sales/${detail.value.id}/actions`,
      payload,
    )
    detail.value = response.after_sale
    detail.progress = ''
    detail.result = ''
    detail.note = ''
    state.notice = '售后处理已更新。'
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
  <section>
    <div class="page-intro">
      <div>
        <h1>售后中心</h1>
        <p>投诉咨询可以继续处理；用户确认收货后不能再办理退货类售后。</p>
      </div>
    </div>

    <p v-if="state.error" class="notice notice--error">{{ state.error }}</p>
    <p v-if="state.notice" class="notice notice--ok">{{ state.notice }}</p>

    <div class="tabs">
      <button
        v-for="tab in KIND_TABS"
        :key="tab.key"
        type="button"
        :class="{ 'is-active': state.kind === tab.key }"
        @click="selectKind(tab.key)"
      >
        {{ tab.label }}
        <span class="tab-count">{{ state.counts[tab.key] ?? 0 }}</span>
      </button>
    </div>

    <div class="toolbar">
      <form class="filter-row" @submit.prevent="search">
        <input v-model="state.q" type="search" placeholder="售后单号 / 订单号 / 问题描述" />
        <button type="submit" class="btn btn--primary">查询</button>
      </form>
    </div>

    <div class="card">
      <div class="card__body">
        <p v-if="state.loading" class="inline-loading">加载中…</p>
        <table v-else-if="state.items.length" class="data-table">
          <thead>
            <tr>
              <th>售后单号</th>
              <th>关联订单</th>
              <th>类型</th>
              <th>问题</th>
              <th>状态</th>
              <th>处理进度</th>
              <th>提交时间</th>
              <th class="actions-col">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in state.items" :key="row.id">
              <td class="mono">{{ row.id.slice(0, 8) }}</td>
              <td class="mono">{{ row.order_id.slice(0, 8) }}</td>
              <td>{{ row.kind === 'RETURN' ? '退货订单' : '用户投诉' }}</td>
              <td class="cell-sub">{{ row.issue }}</td>
              <td>
                <span
                  class="tag"
                  :class="{
                    'tag--warn': ['PENDING', 'PROCESSING'].includes(row.state),
                    'tag--danger': row.state === 'PLATFORM',
                    'tag--ok': ['COMPLETED', 'REJECTED'].includes(row.state),
                  }"
                >
                  {{ STATE_LABELS[row.state] || row.state }}
                </span>
              </td>
              <td class="cell-sub">{{ row.progress || '—' }}</td>
              <td>{{ fmtDate(row.created_at) }}</td>
              <td class="actions-col">
                <button type="button" class="btn btn--sm" @click="openDetail(row)">
                  {{ row.readonly ? '查看详情' : '处理售后' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty-state">该类型下没有售后单。</p>
      </div>
    </div>

    <AppPager
      :page="state.page"
      :page-size="PAGE_SIZE"
      :total="state.total"
      :has-next="state.hasNext"
      @change="goPage"
    />

    <AppDrawer :open="detail.open" title="售后详情" wide @close="closeDetail">
      <p v-if="detail.loading" class="inline-loading">加载中…</p>
      <template v-else-if="detail.value">
        <dl class="detail-grid">
          <div>
            <dt>售后单号</dt>
            <dd class="mono">{{ detail.value.id }}</dd>
          </div>
          <div>
            <dt>关联订单</dt>
            <dd class="mono">{{ detail.value.order_id }}</dd>
          </div>
          <div>
            <dt>类型</dt>
            <dd>{{ detail.value.kind === 'RETURN' ? '退货订单' : '用户投诉' }}</dd>
          </div>
          <div>
            <dt>状态</dt>
            <dd>{{ STATE_LABELS[detail.value.state] || detail.value.state }}</dd>
          </div>
          <div>
            <dt>提交时间</dt>
            <dd>{{ fmtDate(detail.value.created_at) }}</dd>
          </div>
          <div>
            <dt>完成时间</dt>
            <dd>{{ fmtDate(detail.value.completed_at) }}</dd>
          </div>
        </dl>

        <h3 class="section-title">问题描述</h3>
        <p class="muted-text">{{ detail.value.issue || '—' }}</p>

        <template v-if="detail.value.product">
          <h3 class="section-title">关联商品</h3>
          <dl class="detail-grid">
            <div>
              <dt>商品</dt>
              <dd>{{ detail.value.product.title }}</dd>
            </div>
            <div>
              <dt>数量</dt>
              <dd class="num">{{ detail.value.product.quantity }}</dd>
            </div>
            <div>
              <dt>成交单价</dt>
              <dd class="num">¥ {{ detail.value.product.unit_price }}</dd>
            </div>
          </dl>
        </template>

        <template v-if="detail.value.proof?.length">
          <h3 class="section-title">处理凭证</h3>
          <div class="proof-row">
            <img v-for="url in detail.value.proof" :key="url" :src="url" alt="处理凭证" />
          </div>
        </template>

        <h3 class="section-title">处理历史</h3>
        <ol class="timeline">
          <li v-for="event in detail.value.events" :key="event.id">
            <span class="timeline__title">
              {{ event.action }}
              <span class="cell-sub">（{{ event.actor_label || event.actor }}）</span>
            </span>
            <span class="timeline__time">{{ fmtDate(event.created_at) }}</span>
            <span v-if="event.content" class="cell-sub">{{ event.content }}</span>
          </li>
        </ol>

        <template v-if="!detail.value.readonly">
          <h3 class="section-title">处理</h3>
          <p v-if="detail.error" class="notice notice--error">{{ detail.error }}</p>

          <ImageUploader
            v-model="detail.proof"
            purpose="review"
            multiple
            :max="5"
            :max-size-mb="1"
            label="处理凭证"
            hint="最多 5 张，上传后记得点「保存凭证」。"
          />
          <div class="form-actions">
            <button
              type="button"
              class="btn"
              :disabled="detail.busy"
              @click="submitAction('proof')"
            >
              保存凭证
            </button>
          </div>

          <label class="field">
            <span class="field__label">更新处理进度</span>
            <input v-model="detail.progress" type="text" placeholder="例如 已联系买家核实情况" />
          </label>
          <div class="form-actions">
            <button
              type="button"
              class="btn"
              :disabled="detail.busy || !detail.progress"
              @click="submitAction('progress')"
            >
              保存进度
            </button>
          </div>

          <label class="field">
            <span class="field__label">申请平台介入（可选说明）</span>
            <input v-model="detail.note" type="text" placeholder="说明需要平台协助的原因" />
          </label>
          <div class="form-actions">
            <button
              type="button"
              class="btn btn--danger"
              :disabled="detail.busy || detail.value.state === 'PLATFORM'"
              @click="submitAction('escalate')"
            >
              申请平台介入
            </button>
          </div>

          <label class="field">
            <span class="field__label">处理结果（完成时必填）</span>
            <textarea v-model="detail.result" rows="3" placeholder="填写处理结论" />
          </label>
          <div class="form-actions">
            <button
              type="button"
              class="btn btn--primary"
              :disabled="detail.busy || !detail.result"
              @click="submitAction('complete')"
            >
              完成处理
            </button>
          </div>
        </template>
        <p v-else class="notice notice--info">
          该售后单已{{ detail.value.state === 'COMPLETED' ? '完成' : '关闭' }}，仅可查看。
        </p>
      </template>
    </AppDrawer>
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
  max-width: 460px;
}

.filter-row input {
  flex: 1;
}

.proof-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.proof-row img {
  width: 84px;
  height: 84px;
  object-fit: cover;
  border: 1px solid var(--line);
  border-radius: 6px;
}
</style>
