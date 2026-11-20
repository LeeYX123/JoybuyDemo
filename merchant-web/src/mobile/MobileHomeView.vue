<script setup>
import { computed, onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'

import { useMerchantSession } from '@/composables/useMerchantSession'
import { apiRequest } from '@/lib/api'
import { showToast } from '@/shell'

// 手机壳首页（folio route 0 核心）：店铺身份卡 → 经营面板 4 格 →
// 业务模块分组宫格（badge 计数）→ 折叠「完整经营面板」（指标+图表直显数值）。
// 桌面壳的 /dashboard 也复用本视图（folio 把经营看板并进首页）。

const router = useRouter()
const { activeShop, can } = useMerchantSession()

const state = reactive({
  loading: true,
  error: '',
  overview: null,
  conversationUnread: 0,
  notificationUnread: 0,
})

async function load() {
  state.loading = true
  state.error = ''
  const tasks = [apiRequest('/merchant/overview?range=week')]
  // badge 计数来源：待发货数=overview、会话未读=conversations、通知未读=notifications counts。
  tasks.push(
    can('merchant.messages.use')
      ? apiRequest('/merchant/conversations')
      : Promise.resolve({ items: [] }),
  )
  tasks.push(
    can('merchant.notifications.view')
      ? apiRequest('/merchant/notifications?page=1&page_size=1')
      : Promise.resolve({ counts: {} }),
  )
  try {
    const [overview, conversations, notifications] = await Promise.all(tasks)
    state.overview = overview
    state.conversationUnread = (conversations.items || []).reduce(
      (sum, item) => sum + (item.unread || 0),
      0,
    )
    state.notificationUnread = notifications.counts?.UNREAD || 0
  } catch (error) {
    state.error = error.message
  } finally {
    state.loading = false
  }
}

const stats = computed(() => state.overview?.stats || {})

const STATUS_TEXT = { ACTIVE: '接单中', SUSPENDED: '已封店', PENDING_DEPOSIT: '待缴保证金' }
const statusText = computed(() => STATUS_TEXT[stats.value.store_status] || stats.value.store_status || '—')
const statusClass = computed(() => {
  if (stats.value.store_status === 'ACTIVE') return 'is-ok'
  if (stats.value.store_status === 'SUSPENDED') return 'is-danger'
  if (stats.value.store_status === 'PENDING_DEPOSIT') return 'is-warn'
  return ''
})

// 业务模块分组（folio groups）：入口按权限隐藏，保证金额外看 deposit_enabled。
const groups = computed(() => {
  const depositOn = Boolean(activeShop.value?.deposit_enabled)
  return [
    {
      title: '商品与经营',
      items: [
        {
          to: '/catalog?view=shop',
          label: '店铺商品',
          color: 'jade',
          icon: 'M4 10h16v10H4zM3 10l2-6h14l2 6M9 20v-6h6v6',
          permission: 'merchant.listings.manage',
        },
        {
          to: '/catalog',
          label: '商品上架中心',
          color: 'blue',
          icon: 'm3 7 9-4 9 4v10l-9 4-9-4zM3 7l9 4 9-4m-9 4v10',
          permission: 'merchant.listings.manage',
        },
        {
          to: '/orders',
          label: '订单管理',
          color: 'indigo',
          icon: 'M5 3h14v18H5zM8 8h8m-8 4h8m-8 4h5',
          permission: 'merchant.orders.manage',
          badge: stats.value.pending_shipment_count || 0,
          badgeSuffix: '笔待发货',
        },
        {
          to: '/activities',
          label: '平台活动',
          color: 'amber',
          icon: 'M4 6h16v14H4zM8 4v4m8-4v4M4 11h16',
          permission: 'merchant.activities.view',
        },
      ],
    },
    {
      title: '资金管理',
      items: [
        {
          to: '/wallet',
          label: '钱包管理',
          color: 'amber',
          icon: 'M3 5h18v15H3zM21 10h-7a2 2 0 0 0 0 4h7m-6-2h.01',
          permission: 'merchant.wallet.manage',
        },
        {
          to: '/deposit',
          label: '保证金管理',
          color: 'blue',
          icon: 'm12 3 8 3v5c0 5-3 8-8 10-5-2-8-5-8-10V6zM8 12l3 3 5-6',
          permission: 'merchant.deposit.view',
          requiresDeposit: true,
        },
      ],
    },
    {
      title: '售后与沟通',
      items: [
        {
          to: '/after-sales',
          label: '售后中心',
          color: 'rose',
          icon: 'M9 6 4 11l5 5m-5-5h10a5 5 0 0 1 0 10h-3',
          permission: 'merchant.aftersales.manage',
        },
        {
          to: '/messages',
          label: '消息中心',
          color: 'jade',
          icon: 'M20 11a8 8 0 0 1-8 8H5l1.5-3A8 8 0 1 1 20 11ZM9 11h6',
          permission: 'merchant.messages.use',
          badge: state.conversationUnread,
          badgeSuffix: '条未读',
        },
        {
          to: '/notifications',
          label: '平台通知',
          color: 'indigo',
          icon: 'M5 17h14l-2-3v-4a5 5 0 0 0-10 0v4zm5 3h4',
          permission: 'merchant.notifications.view',
          badge: state.notificationUnread,
          badgeSuffix: '条未读',
        },
        {
          to: '/messages?open=support',
          label: '联系平台客服',
          color: 'blue',
          icon: 'M4 13v-2a8 8 0 0 1 16 0v2M4 13h3v5H5a1 1 0 0 1-1-1zm16 0h-3v5h2a1 1 0 0 0 1-1zm-3 5c-1 2-2 3-5 3',
          permission: 'merchant.messages.use',
        },
      ],
    },
  ].map((group) => ({
    ...group,
    items: group.items.filter((item) => {
      if (item.permission && !can(item.permission)) return false
      if (item.requiresDeposit && !depositOn) return false
      return true
    }),
  }))
})

const visibleGroups = computed(() => groups.value.filter((group) => group.items.length > 0))

// 折叠面板 6 指标（店铺状态已放 4 格首格，这里不再重复）。
const detailMetrics = computed(() => [
  { label: '今日订单数量', value: stats.value.today_order_count ?? '—' },
  { label: '待发货订单', value: stats.value.pending_shipment_count ?? '—' },
  { label: '今日曝光度', value: stats.value.today_exposure ?? '—' },
  { label: '总关注', value: stats.value.follower_total ?? '—' },
  { label: '店铺信誉分', value: stats.value.credit_score ?? '—' },
  { label: '今日新增收益', value: `¥ ${stats.value.shipping_profit_today ?? '0.00'}` },
])

const orderBars = computed(() => state.overview?.charts?.order_bars || [])
const maxBar = computed(() => Math.max(1, ...orderBars.value.map((item) => item.count)))
const exposureTrend = computed(() => state.overview?.charts?.exposure_trend || [])
const maxExposure = computed(() => Math.max(1, ...exposureTrend.value.map((item) => item.exposure)))

const shopInitial = computed(() => (activeShop.value?.name || '店').slice(0, 1))

function copyShopId() {
  if (!activeShop.value?.id) return
  // 先提示再异步复制：clipboard 在部分环境（无头/非安全上下文）可能挂起或拒绝，
  // 不能让 toast 等它；复制失败时把 ID 直接抛进 toast 给用户看。
  showToast('店铺 ID 已复制')
  navigator.clipboard
    ?.writeText(activeShop.value.id)
    .then(() => showToast('店铺 ID 已复制'))
    .catch(() => showToast(activeShop.value.id))
}

onMounted(load)
</script>

<template>
  <div class="m-page m-home">
    <p v-if="state.error" class="m-error">
      {{ state.error }}
      <button type="button" class="m-retry" @click="load">重试</button>
    </p>
    <p v-else-if="state.loading" class="m-loading">加载中…</p>

    <template v-else>
      <!-- 店铺身份卡：头像 + 店名 + 复制 ID + 编辑资料入口（README 验收③）。 -->
      <section class="m-card m-identity">
        <span class="m-identity__avatar" aria-hidden="true">
          <img v-if="activeShop?.avatar" :src="activeShop.avatar" alt="" />
          <template v-else>{{ shopInitial }}</template>
        </span>
        <span class="m-identity__text">
          <strong class="m-identity__name">{{ activeShop?.name || '未选择店铺' }}</strong>
          <button type="button" class="m-identity__id" aria-label="复制店铺 ID" @click="copyShopId">
            ID {{ activeShop?.id ? activeShop.id.slice(0, 8) : '—' }}…
          </button>
        </span>
        <button type="button" class="m-identity__edit" @click="router.push('/store')">编辑资料</button>
      </section>

      <!-- 经营面板 4 格（folio work-grid：3 窄列 + 总关注加宽）。 -->
      <section class="m-card m-overview">
        <h2 class="m-overview__head">经营面板</h2>
        <div class="m-overview__grid">
          <div class="m-overview__cell">
            <span>店铺状态</span>
            <strong :class="statusClass">{{ statusText }}</strong>
          </div>
          <div class="m-overview__cell">
            <span>今日订单</span>
            <strong class="m-num">{{ stats.today_order_count ?? '—' }}</strong>
          </div>
          <div class="m-overview__cell">
            <span>今日曝光</span>
            <strong class="m-num">{{ stats.today_exposure ?? '—' }}</strong>
          </div>
          <div class="m-overview__cell m-overview__cell--wide">
            <span>总关注</span>
            <span class="m-overview__value-row">
              <strong class="m-num">{{ stats.follower_total ?? '—' }}</strong>
              <em v-if="stats.follower_delta" class="m-overview__delta">+{{ stats.follower_delta }}</em>
            </span>
          </div>
        </div>
      </section>

      <!-- 业务模块：三组宫格（folio folio-module-group）。 -->
      <section class="m-card">
        <h2 class="m-modules__head">业务模块</h2>
        <nav class="m-modules" aria-label="业务模块">
          <section v-for="group in visibleGroups" :key="group.title" class="m-modules__group">
            <h3>{{ group.title }}</h3>
            <button
              v-for="item in group.items"
              :key="item.to"
              type="button"
              :aria-label="item.badge ? `${item.label}，${item.badge} ${item.badgeSuffix}` : item.label"
              @click="router.push(item.to)"
            >
              <span class="m-module-icon" :class="item.color">
                <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
                  <path :d="item.icon" />
                </svg>
                <span v-if="item.badge" class="m-module-badge" aria-hidden="true">
                  {{ item.badge > 99 ? '99+' : item.badge }}
                </span>
              </span>
              <span>{{ item.label }}</span>
            </button>
          </section>
        </nav>
      </section>

      <!-- 折叠「完整经营面板」：6 指标 + 两图表（直显数值、不交互，README 验收③）。 -->
      <details class="m-card m-metrics">
        <summary>完整经营面板</summary>
        <div class="m-metrics__stats">
          <div v-for="metric in detailMetrics" :key="metric.label" class="m-metrics__stat">
            <span>{{ metric.label }}</span>
            <strong class="m-num">{{ metric.value }}</strong>
          </div>
        </div>

        <div class="m-chart">
          <h3>订单数量 <small>近一周 · 笔</small></h3>
          <div class="m-chart__plot" role="list">
            <div
              v-for="item in orderBars"
              :key="item.date"
              class="m-chart__col"
              role="listitem"
              :aria-label="`${item.date}，${item.count} 笔`"
            >
              <span class="m-chart__value m-num">{{ item.count }}</span>
              <i class="m-chart__bar" :style="{ height: `${Math.max(3, (item.count / maxBar) * 100)}%` }" />
              <span class="m-chart__date">{{ item.date.slice(5) }}</span>
            </div>
          </div>
        </div>

        <div class="m-chart m-chart--rows">
          <h3>曝光度趋势 <small>近一周</small></h3>
          <p v-if="!exposureTrend.length" class="m-hint">暂无曝光数据。</p>
          <div v-else class="m-chart__rows">
            <div v-for="item in exposureTrend" :key="item.date" class="m-chart__row">
              <span class="m-chart__row-date">{{ item.date.slice(5) }}</span>
              <span class="m-chart__track">
                <i :style="{ width: `${Math.max(2, (item.exposure / maxExposure) * 100)}%` }" />
              </span>
              <span class="m-chart__row-value m-num">{{ item.exposure }}</span>
            </div>
          </div>
        </div>
      </details>
    </template>
  </div>
</template>

<style scoped>
.m-retry {
  margin-left: 8px;
  border: 0;
  background: transparent;
  color: var(--m-accent);
  font-weight: 650;
  cursor: pointer;
}

/* 身份卡（folio merchant-shop-identity + concepts 44px 头像）。 */
.m-identity {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--m-space-3);
  padding: 14px;
}

.m-identity__avatar {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  overflow: hidden;
  border-radius: 50%;
  background: var(--m-tint);
  color: var(--m-accent);
  font-weight: 700;
}

.m-identity__avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.m-identity__text {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.m-identity__name {
  font-size: 16px;
  color: var(--m-ink);
  overflow-wrap: anywhere;
}

.m-identity__id {
  justify-self: start;
  min-height: 44px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--m-muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
  text-align: start;
}

.m-identity__edit {
  min-height: 44px;
  padding: 0 10px;
  border: 1px solid var(--m-line);
  border-radius: 7px;
  background: var(--m-paper);
  color: var(--m-accent);
  font-size: 13px;
  font-weight: 650;
  cursor: pointer;
}

/* 经营面板 4 格（folio：3 窄 + 1 宽）。 */
.m-overview__head,
.m-modules__head {
  margin: 0;
  padding: 12px 14px;
  font-size: 16px;
  font-weight: 650;
  color: var(--m-ink);
}

.m-overview__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr)) minmax(0, 1.65fr);
  border-top: 1px solid var(--m-line);
}

.m-overview__cell {
  display: grid;
  align-content: start;
  gap: 4px;
  min-height: 58px;
  padding: 8px 6px;
}

.m-overview__cell + .m-overview__cell {
  border-left: 1px solid var(--m-line);
}

.m-overview__cell span:first-child {
  font-size: 12px;
  font-weight: 650;
  color: var(--m-ink);
  line-height: 1.4;
}

.m-overview__cell strong {
  font-size: 19px;
  line-height: 1.25;
  color: var(--m-ink);
  overflow-wrap: anywhere;
}

.m-overview__cell strong.is-ok {
  color: var(--m-success);
}

.m-overview__cell strong.is-danger {
  color: var(--m-accent);
}

.m-overview__cell strong.is-warn {
  color: #bf812d;
}

.m-overview__value-row {
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.m-overview__delta {
  padding: 1px 4px;
  border-radius: 4px;
  background: var(--m-tint);
  color: var(--m-accent);
  font-size: 12px;
  font-weight: 700;
  font-style: normal;
  font-variant-numeric: tabular-nums;
}

/* 375px 及以下：4 格折两行（folio @359 断点的等价实现）。 */
@media (max-width: 379px) {
  .m-overview__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .m-overview__cell + .m-overview__cell {
    border-left: 0;
  }

  .m-overview__cell:nth-child(even) {
    border-left: 1px solid var(--m-line);
  }

  .m-overview__cell:nth-child(n + 3) {
    border-top: 1px solid var(--m-line);
  }
}

/* 分组宫格（folio folio-module-group）。 */
.m-modules {
  padding: 0 12px 6px;
}

.m-modules__group {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px 8px;
  padding: 12px 0;
}

.m-modules__group + .m-modules__group {
  border-top: 1px solid var(--m-line);
}

.m-modules__group h3 {
  grid-column: 1 / -1;
  margin: 0;
  font-size: 12px;
  font-weight: 650;
  color: var(--m-muted);
}

.m-modules__group button {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  min-height: 48px;
  min-width: 0;
  padding: 4px 2px;
  border: 0;
  border-radius: var(--m-radius);
  background: transparent;
  color: var(--m-ink);
  font-size: 12px;
  text-align: left;
  line-height: 1.35;
  cursor: pointer;
}

.m-modules__group button:hover {
  background: var(--m-canvas);
}

.m-module-icon {
  position: relative;
  flex: 0 0 32px;
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 9px;
  background: transparent;
  color: var(--m-accent);
}

.m-module-icon svg {
  width: 22px;
  height: 22px;
}

.m-module-icon.jade {
  background: #e5f5ed;
  color: #17664d;
}

.m-module-icon.blue {
  background: #e7f3fb;
  color: #155f86;
}

.m-module-icon.indigo {
  background: #eeedff;
  color: #4545a2;
}

.m-module-icon.amber {
  background: #fff0d9;
  color: #874a12;
}

.m-module-icon.rose {
  background: #feecef;
  color: #a63152;
}

.m-module-badge {
  position: absolute;
  right: -7px;
  top: -5px;
  min-width: 17px;
  padding: 1px 4px;
  border-radius: 12px;
  background: #ba2532;
  color: #fff;
  font: 700 10px/15px system-ui, sans-serif;
  text-align: center;
}

/* 折叠完整经营面板。 */
.m-metrics summary {
  min-height: var(--m-target);
  padding: 13px 14px;
  font-size: 14px;
  font-weight: 650;
  color: var(--m-ink);
  cursor: pointer;
  list-style: none;
}

.m-metrics summary::-webkit-details-marker {
  display: none;
}

.m-metrics summary::after {
  content: '';
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-left: 8px;
  border: solid var(--m-muted);
  border-width: 0 1.5px 1.5px 0;
  transform: translateY(-2px) rotate(45deg);
}

.m-metrics[open] summary::after {
  transform: translateY(1px) rotate(225deg);
}

.m-metrics__stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--m-space-2);
  padding: 0 14px 8px;
}

.m-metrics__stat {
  padding: 12px;
  border: 1px solid var(--m-line);
  border-radius: var(--m-radius);
  background: var(--m-paper);
}

.m-metrics__stat span {
  font-size: 12px;
  color: var(--m-muted);
}

.m-metrics__stat strong {
  display: block;
  margin-top: 8px;
  font-size: clamp(17px, 5vw, 22px);
  color: var(--m-ink);
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.m-chart {
  padding: 4px 14px 14px;
}

.m-chart h3 {
  margin: 8px 0 10px;
  font-size: 14px;
  color: var(--m-ink);
}

.m-chart h3 small {
  margin-left: 8px;
  font-size: 12px;
  font-weight: 400;
  color: var(--m-muted);
}

/* 柱状图直显数值（folio chart-direct-values）：数值在柱顶、日期在柱底、无交互。 */
.m-chart__plot {
  display: flex;
  align-items: stretch;
  gap: 6px;
  height: 164px;
  padding-top: 20px;
}

.m-chart__col {
  position: relative;
  flex: 1 1 0;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  align-items: center;
  min-width: 0;
}

.m-chart__value {
  position: absolute;
  top: -18px;
  font-size: 11px;
  font-weight: 650;
  color: var(--m-ink);
  white-space: nowrap;
}

.m-chart__bar {
  width: 100%;
  max-width: 30px;
  border-radius: 3px 3px 0 0;
  background: #f3b9bd;
}

.m-chart__col:last-child .m-chart__bar {
  background: var(--m-accent);
}

.m-chart__date {
  margin-top: 6px;
  font-size: 10px;
  color: var(--m-muted);
  white-space: nowrap;
}

.m-chart--rows {
  border-top: 1px solid var(--m-line);
}

.m-chart__rows {
  display: grid;
  gap: 8px;
}

.m-chart__row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
}

.m-chart__row-date {
  flex: 0 0 40px;
  color: var(--m-muted);
}

.m-chart__track {
  flex: 1;
  height: 10px;
  border-radius: 5px;
  background: #f0f4f9;
  overflow: hidden;
}

.m-chart__track i {
  display: block;
  height: 100%;
  border-radius: 5px;
  background: var(--m-accent);
}

.m-chart__row-value {
  flex: 0 0 44px;
  text-align: right;
  color: var(--m-ink);
}
</style>
