<script setup>
import { computed, onMounted, reactive, ref } from 'vue'

import { apiRequest } from '@/lib/api'

const state = reactive({
  loading: true,
  error: '',
  data: null,
})

const chartRange = ref('week')

const today = computed(() => {
  const now = new Date()
  return `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日`
})

const bars = computed(() => state.data?.charts?.order_bars || [])
const maxBar = computed(() => Math.max(1, ...bars.value.map((item) => item.count)))
const exposureTrend = computed(() => state.data?.charts?.exposure_trend || [])
const maxExposure = computed(() => Math.max(1, ...exposureTrend.value.map((item) => item.exposure)))
const categoryShare = computed(() => state.data?.charts?.category_share || [])
const categoryTotal = computed(() => categoryShare.value.reduce((sum, item) => sum + item.count, 0))
const notifications = computed(() => state.data?.notifications || [])

const statusText = computed(() => {
  // 文档 M01 §6：店铺状态只有「接单中」「已封店」两个。
  const status = state.data?.stats?.store_status
  if (status === 'SUSPENDED') return '已封店'
  if (status === 'ACTIVE') return '接单中'
  if (status === 'PENDING_DEPOSIT') return '待缴保证金'
  return status || '—'
})

// 店铺状态颜色：接单中=绿、已封店=红、待缴保证金=橙，其余灰。
const statusColorClass = computed(() => {
  const status = state.data?.stats?.store_status
  if (status === 'ACTIVE') return 'status-active'
  if (status === 'SUSPENDED') return 'status-suspended'
  if (status === 'PENDING_DEPOSIT') return 'status-pending'
  return 'status-muted'
})

async function load() {
  state.loading = true
  state.error = ''
  try {
    state.data = await apiRequest(`/merchant/overview?range=${chartRange.value}`)
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

function switchRange(range) {
  if (chartRange.value === range) return
  chartRange.value = range
  load()
}

function dayLabel(value) {
  return value.slice(5)
}

onMounted(load)
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>经营看板</h1>
        <p>连接全球生意，从掌握每一个经营信号开始。</p>
      </div>
      <div class="page-intro__actions">
        <span class="tag">{{ today }}</span>
      </div>
    </div>

    <p v-if="state.error" class="notice notice--error">{{ state.error }}</p>
    <p v-if="state.loading" class="inline-loading">加载中…</p>

    <template v-if="state.data">
      <div class="welcome-strip">
        <div>
          店铺当前状态：<b :class="statusColorClass">{{ statusText }}</b>
          <template v-if="state.data.stats.pending_shipment_count">
            ｜ 你有 <b>{{ state.data.stats.pending_shipment_count }}</b> 笔订单待发货
          </template>
          <template v-if="state.data.stats.pending_after_sales">
            ｜ <b>{{ state.data.stats.pending_after_sales }}</b> 个售后待处理
          </template>
        </div>
        <RouterLink to="/orders" class="btn btn--sm">前往处理 →</RouterLink>
      </div>

      <div class="stat-grid">
        <div class="stat-card">
          <div class="stat-card__label">今日订单数量</div>
          <div class="stat-card__value">{{ state.data.stats.today_order_count }}</div>
          <div class="stat-card__hint">购买成功（已付款）才算</div>
        </div>
        <div class="stat-card">
          <div class="stat-card__label">待发货订单</div>
          <div class="stat-card__value">{{ state.data.stats.pending_shipment_count }}</div>
          <div class="stat-card__hint">
            待发货金额 ¥ {{ state.data.stats.pending_order_amount }}
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-card__label">今日曝光度</div>
          <div class="stat-card__value">{{ state.data.stats.today_exposure }}</div>
          <div class="stat-card__hint">当日累计，每天自动清零</div>
        </div>
        <div class="stat-card">
          <div class="stat-card__label">总关注</div>
          <div class="stat-card__value">
            {{ state.data.stats.follower_total }}
            <span v-if="state.data.stats.follower_delta" class="follow-delta">
              +{{ state.data.stats.follower_delta }}
            </span>
          </div>
          <div class="stat-card__hint">
            {{ state.data.stats.follower_delta ? '今日新增累计' : '今日无新增' }}
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-card__label">店铺状态</div>
          <div class="stat-card__value" :class="statusColorClass" style="font-size: 20px">
            ● {{ statusText }}
          </div>
          <div class="stat-card__hint">
            {{ state.data.merchant.can_operate ? '平台自动接单中' : '请联系平台客服' }}
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-card__label">店铺信誉分</div>
          <div class="stat-card__value">{{ state.data.stats.credit_score }}</div>
          <div class="stat-card__hint">满分 100 分</div>
        </div>
      </div>

      <div class="dashboard-grid">
        <div class="card">
          <div class="card__head">
            <h2>订单数量</h2>
            <div class="card__actions">
              <div class="range-switch">
                <button
                  type="button"
                  class="range-switch__btn"
                  :class="{ 'range-switch__btn--active': chartRange === 'week' }"
                  @click="switchRange('week')"
                >
                  近一周
                </button>
                <button
                  type="button"
                  class="range-switch__btn"
                  :class="{ 'range-switch__btn--active': chartRange === 'month' }"
                  @click="switchRange('month')"
                >
                  近一月
                </button>
              </div>
              <span class="tag">今日新增收益 ¥ {{ state.data.stats.shipping_profit_today }}</span>
            </div>
          </div>
          <div class="card__body">
            <div class="bar-chart">
              <div v-for="item in bars" :key="item.date" class="bar-chart__item">
                <span class="bar-chart__value">{{ item.count || '' }}</span>
                <div
                  class="bar-chart__bar"
                  :style="{ height: `${Math.max(3, (item.count / maxBar) * 100)}%` }"
                  :title="`${item.date} · ${item.count} 笔`"
                />
                <span class="bar-chart__label">{{ dayLabel(item.date) }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card__head"><h2>订单品类占比</h2></div>
          <div class="card__body">
            <p class="card__note">按已付款订单量统计</p>
            <table v-if="categoryShare.length" class="data-table">
              <thead>
                <tr>
                  <th>品类</th>
                  <th>订单数</th>
                  <th>占比</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in categoryShare" :key="row.category">
                  <td>{{ row.category }}</td>
                  <td class="num">{{ row.count }}</td>
                  <td class="num">
                    {{ categoryTotal ? ((row.count / categoryTotal) * 100).toFixed(1) : '0.0' }}%
                  </td>
                </tr>
              </tbody>
            </table>
            <p v-else class="empty-state">还没有订单数据。</p>
          </div>
        </div>
      </div>

      <div class="dashboard-grid">
        <div class="card">
          <div class="card__head">
            <h2>曝光度趋势</h2>
            <div class="card__actions">
              <div class="range-switch">
                <button
                  type="button"
                  class="range-switch__btn"
                  :class="{ 'range-switch__btn--active': chartRange === 'week' }"
                  @click="switchRange('week')"
                >
                  近一周
                </button>
                <button
                  type="button"
                  class="range-switch__btn"
                  :class="{ 'range-switch__btn--active': chartRange === 'month' }"
                  @click="switchRange('month')"
                >
                  近一月
                </button>
              </div>
            </div>
          </div>
          <div class="card__body">
            <div v-if="exposureTrend.length" class="exposure-trend">
              <div v-for="item in exposureTrend" :key="item.date" class="exposure-trend__row">
                <span class="exposure-trend__date">{{ dayLabel(item.date) }}</span>
                <div class="exposure-trend__track">
                  <div
                    class="exposure-trend__bar"
                    :style="{ width: `${Math.max(2, (item.exposure / maxExposure) * 100)}%` }"
                  />
                </div>
                <span class="exposure-trend__value">{{ item.exposure }}</span>
              </div>
            </div>
            <p v-else class="empty-state">
              暂无曝光数据。平台在【商家关注与曝光】里调整曝光后会在这里显示。
            </p>
          </div>
        </div>

        <div class="card">
          <div class="card__head">
            <h2>平台经营通知</h2>
            <div class="card__actions">
              <RouterLink to="/notifications" class="card__link">查看全部 →</RouterLink>
            </div>
          </div>
          <div class="card__body">
            <ul v-if="notifications.length" class="notice-list">
              <li v-for="item in notifications" :key="item.id" class="notice-list__item">
                <span class="notice-list__title">{{ item.title }}</span>
                <span class="notice-list__content">{{ item.content }}</span>
                <span class="notice-list__time">{{ item.created_at?.slice(0, 10) }}</span>
              </li>
            </ul>
            <p v-else class="empty-state">暂无平台通知。</p>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card__head"><h2>资金概览</h2></div>
        <div class="card__body">
          <dl class="detail-grid">
            <div>
              <dt>钱包可用余额</dt>
              <dd>¥ {{ state.data.stats.wallet_balance }}</dd>
            </div>
            <div>
              <dt>保证金</dt>
              <dd>
                {{ state.data.merchant.deposit_enabled ? '已启用' : '无需缴纳' }}
              </dd>
            </div>
            <div>
              <dt>信誉分</dt>
              <dd>{{ state.data.stats.credit_score }}</dd>
            </div>
            <div>
              <dt>当前角色</dt>
              <dd>{{ state.data.merchant.role || '—' }}</dd>
            </div>
          </dl>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.status-active {
  color: #16a34a;
}

.status-suspended {
  color: #e1251b;
}

.status-pending {
  color: #d97706;
}

.status-muted {
  color: var(--muted, #78869a);
}

.dashboard-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: 1.35fr 1fr;
  margin-bottom: 16px;
}

@media (max-width: 1100px) {
  .dashboard-grid {
    grid-template-columns: 1fr;
  }
}

.range-switch {
  display: inline-flex;
  border: 1px solid var(--border, #e2e8f0);
  border-radius: 6px;
  overflow: hidden;
}

.range-switch__btn {
  border: none;
  background: #fff;
  padding: 4px 12px;
  font-size: 12px;
  color: var(--muted, #78869a);
  cursor: pointer;
}

.range-switch__btn--active {
  background: var(--primary, #2563eb);
  color: #fff;
}

.follow-delta {
  color: #e1251b;
  font-size: 14px;
  margin-left: 4px;
}

.card__note {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--muted, #78869a);
}

.card__link {
  font-size: 12px;
  color: var(--primary, #2563eb);
  text-decoration: none;
}

.exposure-trend {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.exposure-trend__row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
}

.exposure-trend__date {
  width: 44px;
  color: var(--muted, #78869a);
}

.exposure-trend__track {
  flex: 1;
  height: 10px;
  background: #f0f4f9;
  border-radius: 5px;
  overflow: hidden;
}

.exposure-trend__bar {
  height: 100%;
  background: var(--primary, #2563eb);
  border-radius: 5px;
}

.exposure-trend__value {
  width: 48px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.notice-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.notice-list__item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  background: #f8fafc;
  border-radius: 6px;
}

.notice-list__title {
  font-weight: 600;
  font-size: 13px;
}

.notice-list__content {
  font-size: 12px;
  color: var(--muted, #78869a);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.notice-list__time {
  font-size: 11px;
  color: var(--muted, #78869a);
}
</style>
