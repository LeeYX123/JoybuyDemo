<script setup>
import { onMounted, reactive, ref } from 'vue'

import AppDrawer from '@/components/AppDrawer.vue'
import AppModal from '@/components/AppModal.vue'
import AppPager from '@/components/AppPager.vue'
import StatusTag from '@/components/StatusTag.vue'
import { adminWrite } from '@/composables/useAdminApi'
import { apiRequest } from '@/lib/api'

const TABS = [
  { key: '', label: '全部售后' },
  { key: 'PENDING', label: '待处理' },
  { key: 'PROCESSING', label: '处理中' },
  { key: 'PLATFORM', label: '平台介入中' },
  { key: 'COMPLETED', label: '已完成' },
]

const KIND_TABS = [
  { key: '', label: '全部类型' },
  { key: 'COMPLAINT', label: '用户投诉' },
  { key: 'RETURN', label: '退货订单' },
]

const state = reactive({
  state: '',
  kind: '',
  q: '',
  page: 1,
  items: [],
  meta: { total: 0, page_size: 20, has_next: false },
  loading: false,
  error: '',
})

const detail = ref(null)
const detailLoading = ref(false)

const decideOpen = ref(false)
const decideBusy = ref(false)
const decideError = ref('')
const decideForm = reactive({ decision: 'COMPLETE', result: '' })

async function load(resetPage = false) {
  if (resetPage) state.page = 1
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page: String(state.page) })
    if (state.state) params.set('state', state.state)
    if (state.kind) params.set('kind', state.kind)
    if (state.q.trim()) params.set('q', state.q.trim())
    const payload = await apiRequest(`/after-sales?${params}`)
    state.items = payload.items
    state.meta = payload
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

async function openDetail(row) {
  detail.value = null
  detailLoading.value = true
  try {
    const payload = await apiRequest(`/after-sales/${row.id}`)
    detail.value = payload.after_sale
  } catch (error) {
    state.error = error.message
  } finally {
    detailLoading.value = false
  }
}

function openDecide(decision = 'COMPLETE') {
  decideForm.decision = decision
  decideForm.result = ''
  decideError.value = ''
  decideOpen.value = true
}

async function submitDecide() {
  if (!detail.value) return
  decideBusy.value = true
  decideError.value = ''
  try {
    const payload = await adminWrite(`/after-sales/${detail.value.id}/actions`, {
      action: 'decide',
      decision: decideForm.decision,
      result: decideForm.result,
    })
    detail.value = payload.after_sale
    decideOpen.value = false
    await load()
  } catch (error) {
    decideError.value = error.message
  } finally {
    decideBusy.value = false
  }
}

function formatTime(value) {
  if (!value) return '—'
  return value.replace('T', ' ').slice(0, 16)
}

function goPage(page) {
  state.page = page
  load()
}

function selectState(key) {
  state.state = key
  load(true)
}

function resetFilters() {
  state.q = ''
  state.kind = ''
  state.state = ''
  load(true)
}

function closeDetail() {
  detail.value = null
  detailLoading.value = false
}

onMounted(load)
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>售后处理</h1>
        <p>
          查看商家售后、介入争议并记录结论。完成售后不等于自动退款，资金处理仍在资金审核模块单独确认。
        </p>
      </div>
    </div>

    <div class="panel">
      <div class="tabs">
        <button
          v-for="tab in TABS"
          :key="tab.key"
          type="button"
          :class="{ 'is-active': state.state === tab.key }"
          @click="selectState(tab.key)"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="toolbar">
        <select v-model="state.kind" @change="load(true)">
          <option v-for="item in KIND_TABS" :key="item.key" :value="item.key">
            {{ item.label }}
          </option>
        </select>
        <input
          v-model="state.q"
          type="search"
          placeholder="商家名称或问题描述"
          @keyup.enter="load(true)"
        />
        <button type="button" class="btn" @click="load(true)">查询</button>
        <button type="button" class="btn" @click="resetFilters">重置</button>
      </div>

      <p v-if="state.error" class="notice notice--error" style="margin: 16px 20px">
        {{ state.error }}
      </p>

      <div class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>售后单号</th>
              <th>商家</th>
              <th>类型</th>
              <th>问题</th>
              <th>状态</th>
              <th>处理进度</th>
              <th>提交时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in state.items" :key="row.id">
              <td>{{ row.id.slice(0, 8) }}</td>
              <td>{{ row.merchant.name }}</td>
              <td>{{ row.kind === 'RETURN' ? '退货订单' : '用户投诉' }}</td>
              <td style="max-width: 320px">{{ row.issue || '—' }}</td>
              <td><StatusTag :value="row.state" /></td>
              <td>{{ row.progress || '—' }}</td>
              <td>{{ formatTime(row.created_at) }}</td>
              <td>
                <div class="row-actions">
                  <button type="button" class="btn btn--sm" @click="openDetail(row)">详情</button>
                </div>
              </td>
            </tr>
            <tr v-if="!state.loading && state.items.length === 0">
              <td colspan="8" class="data-table__empty">没有匹配的售后记录。</td>
            </tr>
            <tr v-if="state.loading">
              <td colspan="8" class="data-table__empty">加载中…</td>
            </tr>
          </tbody>
        </table>
      </div>

      <AppPager
        :page="state.meta.page || 1"
        :page-size="state.meta.page_size || 20"
        :total="state.meta.total || 0"
        :has-next="state.meta.has_next"
        @change="goPage"
      />
    </div>

    <AppDrawer
      v-if="detail || detailLoading"
      :title="detail ? `售后 ${detail.id.slice(0, 8)}` : '售后详情'"
      wide
      @close="closeDetail"
    >
      <p v-if="detailLoading" class="inline-loading">加载中…</p>
      <template v-if="detail">
        <dl class="detail-grid">
          <div>
            <dt>商家</dt>
            <dd>{{ detail.merchant.name }}</dd>
          </div>
          <div>
            <dt>关联订单</dt>
            <dd>{{ detail.order_id }}</dd>
          </div>
          <div>
            <dt>类型</dt>
            <dd>{{ detail.kind === 'RETURN' ? '退货订单' : '用户投诉' }}</dd>
          </div>
          <div>
            <dt>状态</dt>
            <dd><StatusTag :value="detail.state" /></dd>
          </div>
          <div>
            <dt>当前进度</dt>
            <dd>{{ detail.progress || '—' }}</dd>
          </div>
          <div>
            <dt>订单状态</dt>
            <dd>{{ detail.order_status }}</dd>
          </div>
          <div>
            <dt>提交时间</dt>
            <dd>{{ formatTime(detail.created_at) }}</dd>
          </div>
          <div>
            <dt>完成时间</dt>
            <dd>{{ formatTime(detail.completed_at) }}</dd>
          </div>
        </dl>

        <h3 class="section-title">问题描述</h3>
        <p style="white-space: pre-wrap">{{ detail.issue || '暂无描述。' }}</p>

        <h3 v-if="detail.proof?.length" class="section-title">凭证</h3>
        <div v-if="detail.proof?.length" class="thumb-row">
          <img v-for="url in detail.proof" :key="url" :src="url" alt="" class="thumb thumb--lg" />
        </div>

        <h3 v-if="detail.result" class="section-title">处理结果</h3>
        <p v-if="detail.result" style="white-space: pre-wrap">{{ detail.result }}</p>

        <h3 class="section-title">处理时间线</h3>
        <ol v-if="detail.events?.length" class="timeline">
          <li v-for="event in detail.events" :key="event.id" class="is-done">
            <div class="timeline__title">
              {{ event.action }} · {{ event.actor_label || event.actor }}
            </div>
            <div class="timeline__time">{{ formatTime(event.created_at) }}</div>
            <p v-if="event.content" style="margin: 6px 0 0; font-size: 12px">{{ event.content }}</p>
          </li>
        </ol>
        <p v-else class="empty-state">暂无处理记录。</p>
      </template>

      <template v-if="detail" #footer>
        <button
          type="button"
          class="btn"
          :disabled="detail.state === 'COMPLETED' || detail.state === 'REJECTED'"
          @click="openDecide('INVESTIGATE')"
        >
          继续核实
        </button>
        <button
          type="button"
          class="btn btn--danger"
          :disabled="detail.state === 'COMPLETED' || detail.state === 'REJECTED'"
          @click="openDecide('REJECT_RETURN')"
        >
          驳回退货申请
        </button>
        <button
          type="button"
          class="btn btn--primary"
          :disabled="detail.state === 'COMPLETED' || detail.state === 'REJECTED'"
          @click="openDecide('COMPLETE')"
        >
          完成处理
        </button>
      </template>
    </AppDrawer>

    <AppModal
      v-if="decideOpen"
      title="平台处理结论"
      confirm-text="提交结论"
      :busy="decideBusy"
      @cancel="decideOpen = false"
      @confirm="submitDecide"
    >
      <p v-if="decideError" class="notice notice--error">{{ decideError }}</p>
      <div class="field">
        <span class="field__label">结论</span>
        <label class="checkline">
          <input v-model="decideForm.decision" type="radio" value="INVESTIGATE" /> 继续核实
        </label>
        <label class="checkline">
          <input v-model="decideForm.decision" type="radio" value="COMPLETE" /> 完成处理
        </label>
        <label class="checkline">
          <input v-model="decideForm.decision" type="radio" value="REJECT_RETURN" /> 驳回退货申请
        </label>
      </div>
      <div class="field" style="margin-top: 12px">
        <label for="decide-result">处理结果（选填）</label>
        <textarea id="decide-result" v-model="decideForm.result" rows="3" />
      </div>
    </AppModal>
  </section>
</template>
