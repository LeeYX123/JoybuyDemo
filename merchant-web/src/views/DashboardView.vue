<script setup>
import { computed, onMounted, reactive } from 'vue'

import { apiRequest } from '@/lib/api'

const state = reactive({
  loading: true,
  error: '',
  data: null,
})

const today = computed(() => {
  const now = new Date()
  return `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日`
})

const bars = computed(() => state.data?.charts?.order_bars || [])
const maxBar = computed(() => Math.max(1, ...bars.value.map((item) => item.count)))
const categoryShare = computed(() => state.data?.charts?.category_share || [])
const categoryTotal = computed(() => categoryShare.value.reduce((sum, item) => sum + item.count, 0))

const statusText = computed(() => {
  const status = state.data?.stats?.store_status
  if (status === 'ACTIVE') return '接单中'
  if (status === 'SUSPENDED') return '已封店'
  if (status === 'PENDING_DEPOSIT') return '待缴保证金'
  return status || '—'
})

async function load() {
  state.loading = true
  state.error = ''
  try {
    state.data = await apiRequest('/merchant/overview')
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
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
          店铺当前状态：<b>{{ statusText }}</b>
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
          <div class="stat-card__hint">按业务日下单数量</div>
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
          <div class="stat-card__hint">平台累计曝光</div>
        </div>
        <div class="stat-card">
          <div class="stat-card__label">总关注</div>
          <div class="stat-card__value">{{ state.data.stats.follower_total }}</div>
          <div class="stat-card__hint">
            <span v-if="state.data.stats.follower_delta" class="up">
              今日 +{{ state.data.stats.follower_delta }}
            </span>
            <span v-else>今日无新增</span>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-card__label">店铺状态</div>
          <div class="stat-card__value" style="font-size: 20px">● {{ statusText }}</div>
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
            <h2>近一周订单</h2>
            <div class="card__actions">
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
</style>
