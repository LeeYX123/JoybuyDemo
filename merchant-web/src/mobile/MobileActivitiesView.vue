<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import SheetModal from '@/mobile/components/SheetModal.vue'
import { apiRequest, merchantWrite } from '@/lib/api'
import { showToast } from '@/shell'

// 手机壳活动中心（folio route 8）：chips → 活动卡片 + 操作按钮独立行。
// 数据走既有 /merchant/activities + /merchant/activities/{id}/join。

const PAGE_SIZE = 9

const KIND_TABS = [
  { key: 'ALL', label: '全部活动' },
  { key: 'PERMANENT', label: '常驻活动' },
  { key: 'LIMITED', label: '限时活动' },
]

const KIND_LABELS = { PERMANENT: '常驻活动', LIMITED: '限时活动' }

const state = reactive({
  kind: 'ALL',
  page: 1,
  loading: true,
  error: '',
  notice: '',
  items: [],
  total: 0,
  hasNext: false,
})

const detail = ref(null)
const joinBusy = ref(false)

async function load() {
  state.loading = true
  state.error = ''
  try {
    const params = new URLSearchParams({ page: String(state.page), page_size: String(PAGE_SIZE) })
    if (state.kind !== 'ALL') params.set('kind', state.kind)
    const payload = await apiRequest(`/merchant/activities?${params}`)
    state.items = payload.items || []
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

async function openDetail(row) {
  detail.value = row
  try {
    const payload = await apiRequest(`/merchant/activities/${row.id}`)
    detail.value = payload.activity
  } catch (error) {
    state.error = error.message
  }
}

async function join(activity) {
  if (!activity || activity.joined) return
  joinBusy.value = true
  state.error = ''
  try {
    const payload = await merchantWrite(`/merchant/activities/${activity.id}/join`, {})
    // 仅在详情 sheet 已打开且是同一活动时同步状态，避免卡片参与后意外弹出 sheet。
    if (detail.value && detail.value.id === payload.activity.id) {
      detail.value = payload.activity
    }
    state.notice = payload.created ? '已记录参与意向。' : '该活动已参与过，无需重复参与。'
    showToast(state.notice)
    await load()
  } catch (error) {
    state.error = error.message
  } finally {
    joinBusy.value = false
  }
}

function fmtDate(value) {
  if (!value) return '—'
  return value.slice(0, 10)
}

function periodLabel(activity) {
  // 迭代02：常驻活动不展示任何时间（创建即生效）。
  if (!activity.start && !activity.end) return '长期有效 · 创建即生效'
  if (!activity.end) return `${fmtDate(activity.start)} 起 · 长期有效`
  return `${fmtDate(activity.start)} 至 ${fmtDate(activity.end)}`
}

const activityTag = computed(() => (item) => {
  if (item.state === 'ENDED') return { text: '已结束', cls: 'm-tag--gray' }
  if (item.state === 'UPCOMING') return { text: '即将开始', cls: 'm-tag--gray' }
  if (item.kind === 'LIMITED') return { text: '限时进行中', cls: 'm-tag--warn' }
  return { text: '进行中', cls: 'm-tag--ok' }
})

onMounted(load)
</script>

<template>
  <div class="m-page">
    <div class="m-chips" role="tablist" aria-label="活动类型">
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
      </button>
    </div>

    <p v-if="state.error" class="m-error">{{ state.error }}</p>
    <p v-if="state.notice" class="m-notice">{{ state.notice }}</p>
    <p v-if="state.loading" class="m-loading">加载中…</p>

    <!-- 活动卡片流（folio activity 卡片，操作按钮独立行）。 -->
    <div v-else-if="state.items.length" class="m-activities">
      <article v-for="row in state.items" :key="row.id" class="m-activity">
        <div class="m-activity__content">
          <span class="m-tag" :class="activityTag(row).cls">{{ activityTag(row).text }}</span>
          <h2>{{ row.title }}</h2>
          <p>{{ row.description || '面向正常接单商家开放，平台将依据商品表现安排曝光资源。' }}</p>
          <p class="m-activity__period">{{ periodLabel(row) }}</p>
        </div>
        <div class="m-activity__actions">
          <button type="button" class="m-btn" @click="openDetail(row)">查看活动</button>
          <button
            type="button"
            class="m-btn m-btn--primary"
            :disabled="row.joined || row.state !== 'ONGOING'"
            @click="join(row)"
          >
            {{ row.joined ? '已参与' : row.state === 'ONGOING' ? '参与活动' : '尚未开始' }}
          </button>
        </div>
      </article>
    </div>
    <p v-else class="m-empty">暂无该类型的活动。</p>

    <div v-if="state.total" class="m-pager">
      <button type="button" class="m-btn" :disabled="state.page <= 1" @click="state.page -= 1; load()">上一页</button>
      <span class="m-num">第 {{ state.page }} 页 · 共 {{ state.total }} 个</span>
      <button type="button" class="m-btn" :disabled="!state.hasNext" @click="state.page += 1; load()">下一页</button>
    </div>

    <SheetModal :open="Boolean(detail)" :title="detail?.title || '活动详情'" @close="detail = null">
      <template v-if="detail">
        <p class="m-hint" style="margin: 0">{{ detail.description || '面向正常接单商家开放。' }}</p>
        <dl class="m-dl">
          <div><dt>活动类型</dt><dd>{{ KIND_LABELS[detail.kind] || detail.kind }}</dd></div>
          <div><dt>活动时间</dt><dd>{{ periodLabel(detail) }}</dd></div>
          <div><dt>参与状态</dt><dd>{{ detail.joined ? '已参与' : '未参与' }}</dd></div>
          <div v-if="detail.joined_at"><dt>参与时间</dt><dd>{{ fmtDate(detail.joined_at) }}</dd></div>
        </dl>
        <p class="m-hint">点击参与仅记录您的意向，无需复杂报名流程；平台后续为参与商家增加曝光。</p>
        <button
          type="button"
          class="m-btn m-btn--primary m-btn--block"
          :disabled="detail.joined || joinBusy || detail.state !== 'ONGOING'"
          @click="join(detail)"
        >
          {{ detail.joined ? '已参与' : detail.state === 'ONGOING' ? '参与活动' : '尚未开始' }}
        </button>
      </template>
    </SheetModal>
  </div>
</template>

<style scoped>
/* 活动卡片（folio activity：单列，操作按钮独立行）。 */
.m-activities {
  display: grid;
  gap: 10px;
}

.m-activity {
  display: grid;
  gap: var(--m-space-2);
  padding: 12px;
  border: 1px solid var(--m-line);
  border-radius: var(--m-radius);
  background: var(--m-paper);
}

.m-activity__content p {
  margin: 4px 0;
  line-height: 1.5;
  color: var(--m-muted);
  font-size: 13px;
}

.m-activity__content h2 {
  margin: 6px 0 3px;
  font-size: 16px;
  color: var(--m-ink);
  overflow-wrap: anywhere;
}

.m-activity__period {
  font-size: 12px;
}

.m-activity__actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: var(--m-space-2);
  border-top: 1px solid var(--m-line);
  padding-top: 8px;
}

.m-activity__actions .m-btn {
  min-height: 40px;
  padding: 0 14px;
  min-width: 84px;
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

.m-dl {
  display: grid;
  gap: 10px;
  margin: 12px 0;
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
</style>
