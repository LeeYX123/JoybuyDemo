<script setup>
import { computed, onMounted, reactive } from 'vue'

import AppDrawer from '@/components/AppDrawer.vue'
import AppPager from '@/components/AppPager.vue'
import { apiRequest, merchantWrite } from '@/lib/api'

const PAGE_SIZE = 9

const KIND_TABS = [
  { key: 'ALL', label: '全部活动' },
  { key: 'PERMANENT', label: '常驻活动' },
  { key: 'LIMITED', label: '限时活动' },
]

const COMMISSION_STATES = {
  PENDING_CALC: '待核算',
  PENDING_PAY: '待发放',
  PAID: '已到账',
}

const state = reactive({
  kind: 'ALL',
  page: 1,
  loading: true,
  error: '',
  notice: '',
  items: [],
  total: 0,
  hasNext: false,
  referral: null,
})

const detail = reactive({ value: null, open: false, busy: false })

const copied = reactive({ value: false })

const tiers = computed(() => state.referral?.tiers || [])

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

async function loadReferral() {
  try {
    state.referral = await apiRequest('/merchant/referral')
  } catch {
    state.referral = null
  }
}

function selectKind(key) {
  state.kind = key
  state.page = 1
  load()
}

function goPage(page) {
  state.page = page
  load()
}

async function openDetail(row) {
  detail.open = true
  detail.value = row
  try {
    const payload = await apiRequest(`/merchant/activities/${row.id}`)
    detail.value = payload.activity
  } catch (error) {
    state.error = error.message
  }
}

function closeDetail() {
  detail.open = false
  detail.value = null
}

async function join(activity) {
  if (!activity || activity.joined) return
  detail.busy = true
  state.error = ''
  try {
    const payload = await merchantWrite(`/merchant/activities/${activity.id}/join`, {})
    detail.value = payload.activity
    state.notice = payload.created ? '已参与活动。' : '该活动已参与过，无需重复参与。'
    await load()
  } catch (error) {
    state.error = error.message
  } finally {
    detail.busy = false
  }
}

async function copyCode() {
  if (!state.referral?.referral_code) return
  try {
    await navigator.clipboard.writeText(state.referral.referral_code)
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 1500)
  } catch {
    state.notice = `推荐码：${state.referral.referral_code}`
  }
}

function fmtDate(value) {
  if (!value) return '—'
  return value.slice(0, 10)
}

function periodLabel(activity) {
  if (!activity.end) return `${fmtDate(activity.start)} 起 · 长期有效`
  return `${fmtDate(activity.start)} 至 ${fmtDate(activity.end)}`
}

onMounted(async () => {
  await Promise.all([load(), loadReferral()])
})
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>平台活动中心</h1>
        <p>参与平台活动获得额外曝光；推荐新商家入驻可获返佣。</p>
      </div>
    </div>

    <p v-if="state.error" class="notice notice--error">{{ state.error }}</p>
    <p v-if="state.notice" class="notice notice--ok">{{ state.notice }}</p>

    <div class="card referral-card">
      <div class="card__head">
        <h2>推荐返佣</h2>
        <span class="tag tag--red">常驻活动</span>
      </div>
      <div class="card__body">
        <div class="referral-head">
          <div>
            <span class="referral-label">本店推荐码</span>
            <strong class="referral-code mono">{{ state.referral?.referral_code || '—' }}</strong>
          </div>
          <button type="button" class="btn btn--sm" @click="copyCode">
            {{ copied.value ? '已复制' : '复制推荐码' }}
          </button>
          <div class="referral-stats">
            <div>
              <span>已推荐商家</span>
              <b>{{ state.referral?.stats?.referred_count ?? 0 }}</b>
            </div>
            <div>
              <span>待发放返佣</span>
              <b class="num">¥ {{ state.referral?.stats?.pending_amount || '0.00' }}</b>
            </div>
            <div>
              <span>已到账返佣</span>
              <b class="num up">¥ {{ state.referral?.stats?.paid_amount || '0.00' }}</b>
            </div>
          </div>
        </div>

        <p class="hint-text">
          返佣有效期 {{ state.referral?.valid_months || 12 }} 个月；每月 1 日核算上一个自然月，
          客服确认后入钱包。未发放金额不计入可用余额。
        </p>

        <table class="data-table">
          <thead>
            <tr>
              <th>新人整月发货额</th>
              <th>返佣比例</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(tier, index) in tiers" :key="index">
              <td class="num">≥ ¥ {{ tier.min }}</td>
              <td class="num">{{ tier.rate }}%</td>
            </tr>
          </tbody>
        </table>

        <h3 class="section-title">返佣明细</h3>
        <table v-if="state.referral?.commissions?.length" class="data-table">
          <thead>
            <tr>
              <th>核算月份</th>
              <th>新人商家</th>
              <th>月发货额</th>
              <th>比例</th>
              <th>返佣金额</th>
              <th>状态</th>
              <th>到账时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in state.referral.commissions" :key="row.id">
              <td>{{ row.period }}</td>
              <td>{{ row.referee }}</td>
              <td class="num">¥ {{ row.shipped_amount }}</td>
              <td class="num">{{ row.rate }}%</td>
              <td class="num">¥ {{ row.amount }}</td>
              <td>
                <span
                  class="tag"
                  :class="{
                    'tag--warn': row.state === 'PENDING_PAY',
                    'tag--ok': row.state === 'PAID',
                  }"
                >
                  {{ COMMISSION_STATES[row.state] || row.state }}
                </span>
              </td>
              <td>{{ fmtDate(row.paid_at) }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="empty-state">还没有返佣记录，把推荐码分享给新商家即可开始。</p>
      </div>
    </div>

    <div class="tabs">
      <button
        v-for="tab in KIND_TABS"
        :key="tab.key"
        type="button"
        :class="{ 'is-active': state.kind === tab.key }"
        @click="selectKind(tab.key)"
      >
        {{ tab.label }}
      </button>
    </div>

    <p v-if="state.loading" class="inline-loading">加载中…</p>
    <p v-else-if="!state.items.length" class="empty-state">该类型下暂无活动。</p>
    <div v-else class="activity-grid">
      <article v-for="row in state.items" :key="row.id" class="activity-card">
        <div class="activity-card__media">
          <img v-if="row.image" :src="row.image" :alt="row.title" />
          <span v-else>活动</span>
        </div>
        <div class="activity-card__body">
          <div class="activity-card__head">
            <h3>{{ row.title }}</h3>
            <span class="tag" :class="{ 'tag--warn': row.state === 'ENDED' }">
              {{ row.state === 'ONGOING' ? '进行中' : '已结束' }}
            </span>
          </div>
          <p class="cell-sub">
            {{ periodLabel(row) }} ｜ {{ row.kind === 'LIMITED' ? '限时' : '常驻' }}
          </p>
          <p class="activity-card__desc">{{ row.description }}</p>
          <div class="activity-card__actions">
            <button type="button" class="btn btn--sm" @click="openDetail(row)">查看详情</button>
            <button
              type="button"
              class="btn btn--sm btn--primary"
              :disabled="row.joined || row.state === 'ENDED'"
              @click="join(row)"
            >
              {{ row.joined ? '已参与' : '参与活动' }}
            </button>
          </div>
        </div>
      </article>
    </div>

    <AppPager
      :page="state.page"
      :page-size="PAGE_SIZE"
      :total="state.total"
      :has-next="state.hasNext"
      @change="goPage"
    />

    <AppDrawer :open="detail.open" title="活动详情" @close="closeDetail">
      <template v-if="detail.value">
        <dl class="detail-grid">
          <div>
            <dt>活动标题</dt>
            <dd>{{ detail.value.title }}</dd>
          </div>
          <div>
            <dt>活动类型</dt>
            <dd>{{ detail.value.kind === 'LIMITED' ? '限时活动' : '常驻活动' }}</dd>
          </div>
          <div>
            <dt>活动时间</dt>
            <dd>{{ periodLabel(detail.value) }}</dd>
          </div>
          <div>
            <dt>状态</dt>
            <dd>{{ detail.value.state === 'ONGOING' ? '进行中' : '已结束' }}</dd>
          </div>
          <div v-if="detail.value.joined">
            <dt>本店参与时间</dt>
            <dd>{{ fmtDate(detail.value.joined_at) }}</dd>
          </div>
          <div v-if="detail.value.joined">
            <dt>已获曝光</dt>
            <dd class="num">{{ detail.value.exposure_added || 0 }}</dd>
          </div>
        </dl>
        <h3 class="section-title">活动说明</h3>
        <p class="muted-text">{{ detail.value.description }}</p>
        <img
          v-if="detail.value.image"
          class="activity-detail-img"
          :src="detail.value.image"
          alt=""
        />
        <div class="form-actions">
          <button
            type="button"
            class="btn btn--primary"
            :disabled="detail.busy || detail.value.joined || detail.value.state === 'ENDED'"
            @click="join(detail.value)"
          >
            {{ detail.value.joined ? '已参与' : '参与活动' }}
          </button>
        </div>
      </template>
    </AppDrawer>
  </section>
</template>

<style scoped>
.referral-card {
  margin-bottom: 20px;
}

.referral-head {
  display: flex;
  align-items: center;
  gap: 20px;
  flex-wrap: wrap;
}

.referral-label {
  display: block;
  font-size: 12px;
  color: var(--muted);
}

.referral-code {
  font-size: 22px;
  letter-spacing: 1px;
  color: var(--red);
}

.referral-stats {
  margin-left: auto;
  display: flex;
  gap: 28px;
}

.referral-stats span {
  display: block;
  font-size: 12px;
  color: var(--muted);
}

.referral-stats b {
  font-size: 16px;
}

.activity-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
}

.activity-card {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.activity-card__media {
  height: 120px;
  background: linear-gradient(135deg, #fff1f2, #ffe4e6);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--red);
  font-size: 13px;
  letter-spacing: 2px;
}

.activity-card__media img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.activity-card__body {
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
}

.activity-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.activity-card__head h3 {
  font-size: 15px;
  margin: 0;
}

.activity-card__desc {
  margin: 0;
  font-size: 13px;
  color: var(--muted);
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.activity-card__actions {
  display: flex;
  gap: 8px;
  margin-top: auto;
}

.activity-detail-img {
  width: 100%;
  border-radius: 8px;
  margin-top: 12px;
}
</style>
