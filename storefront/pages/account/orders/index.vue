<script setup>
import { computed, ref, watch } from 'vue'
import { useFetch, useHead, useRequestHeaders, useRoute, useRuntimeConfig } from '#imports'

import { useBuyerAuth } from '../../../composables/useBuyerAuth'
import { useLocale } from '../../../composables/useLocale'
import { useMobileView } from '../../../composables/useMobileView'
import { formatDisplayPrice } from '../../../utils/display'

import AccountEmpty from '../../../components/account/AccountEmpty.vue'
import AccountPager from '../../../components/account/AccountPager.vue'
import AccountShell from '../../../components/account/AccountShell.vue'
import AccountTabs from '../../../components/account/AccountTabs.vue'

// 2026-11-28 统一三态口径：全部 / 待发货 / 已发货 / 已完成。
// 状态由后端 `state` 按物流节点阈值给出（progress<1=待发货、1–6=已发货、
// >=7=已完成）；取消单 / 未付款单只在【全部】里出现，卡片仍带状态徽标。
const { t } = useLocale()
const { isAuthenticated } = useBuyerAuth()
const route = useRoute()
const config = useRuntimeConfig()
// ADR 0001: on the m. host the same payload renders the mobile order list
// (docs/20 §5.1); the desktop AccountShell below is untouched.
const { isMobileHost } = useMobileView()

const ordersUrl = computed(() =>
  import.meta.server ? `${config.apiBaseInternal}/orders` : '/api/v1/orders',
)

const { data, status } = await useFetch(ordersUrl, {
  key: 'buyer-orders',
  headers: {
    cookie: useRequestHeaders(['cookie']).cookie || '',
    // 迭代02：时间展示按看的人所在时区（后端按此头转换，只影响展示）。
    'X-Client-Timezone':
      typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone || '' : '',
  },
})

const orders = computed(() => (Array.isArray(data.value?.orders) ? data.value.orders : []))

const TAB_KEYS = ['all', 'to_ship', 'shipped', 'completed']
const initialTab = String(route.query?.tab || '')
const activeTab = ref(TAB_KEYS.includes(initialTab) ? initialTab : 'all')

// 2026-11-28：状态 tab 只留状态名，去掉数量角标（数量此前由前端统计，
// 真站 tab 无计数；接口未动）。
const tabs = computed(() => [
  { key: 'all', label: t('orders.tabAll') },
  { key: 'to_ship', label: t('orders.tabToShip') },
  { key: 'shipped', label: t('orders.tabShipped') },
  { key: 'completed', label: t('orders.tabCompleted') },
])

const filteredOrders = computed(() => {
  if (activeTab.value === 'all') return orders.value
  const wanted = {
    to_ship: 'TO_SHIP',
    shipped: 'SHIPPED',
    completed: 'COMPLETED',
  }[activeTab.value]
  return orders.value.filter((order) => order.state === wanted)
})

const PAGE_SIZE = 10
const page = ref(1)
const totalPages = computed(() => Math.max(1, Math.ceil(filteredOrders.value.length / PAGE_SIZE)))
const pagedOrders = computed(() => {
  const start = (page.value - 1) * PAGE_SIZE
  return filteredOrders.value.slice(start, start + PAGE_SIZE)
})

watch(activeTab, () => {
  page.value = 1
})

watch(totalPages, (value) => {
  if (page.value > value) page.value = value
})

function goToPage(next) {
  if (next >= 1 && next <= totalPages.value) page.value = next
}

const STATUS_KEYS = {
  PENDING_PAYMENT: 'orders.statusPendingPayment',
  TO_SHIP: 'orders.statusToShip',
  SHIPPED: 'orders.statusShipped',
  COMPLETED: 'orders.statusCompleted',
  CANCELED: 'orders.statusCanceled',
}

function stateLabel(order) {
  return t(STATUS_KEYS[order.state] || 'orders.statusToShip')
}

function stateClass(order) {
  if (order.state === 'COMPLETED') return 'completed'
  if (order.state === 'CANCELED') return 'canceled'
  if (order.state === 'SHIPPED') return 'shipped'
  return 'pending'
}

function formatDate(value) {
  if (!value) return ''
  return String(value).slice(0, 16).replace('T', ' ')
}

function itemPrice(item) {
  return formatDisplayPrice(item.unit_price)
}

function orderTotal(order) {
  return formatDisplayPrice(order.total)
}

// Mobile order cards (docs/20 §5.1): status badge, first item image,
// number/date/total, view-details link. Formatting reuses the desktop helpers.
const mobileOrders = computed(() =>
  pagedOrders.value.map((order) => {
    const first = Array.isArray(order.items) ? order.items[0] : null
    return {
      publicId: order.public_id,
      // 2026-11-27 全站编号改造：订单号是 JYO+YYYYMMDD+6 位，截前 8 位会撞车，
      // 一律显示完整编号（CSS 用等宽字体 + nowrap 防换行）。
      number: String(order.public_id || '').toUpperCase(),
      date: formatDate(order.created_at),
      statusLabel: stateLabel(order),
      statusClass: stateClass(order),
      total: orderTotal(order),
      image: first?.image_path || '',
      title: first?.title || '',
    }
  }),
)

useHead(() => ({ title: t('accountMenu.orders') }))
</script>

<template>
  <!-- ADR 0001: mobile host renders the docs/20 §5.1 mobile order list;
       the desktop AccountShell below is untouched. -->
  <MobileOrders
    v-if="isMobileHost"
    :signed-in="isAuthenticated"
    :loading="status === 'pending'"
    :tabs="tabs"
    :active-tab="activeTab"
    :orders="mobileOrders"
    @tab="activeTab = $event"
  />
  <AccountShell v-else :title="t('accountMenu.orders')">
    <template #tabs>
      <AccountTabs v-model="activeTab" :tabs="tabs" />
    </template>

    <div v-if="!isAuthenticated" class="orders-signed-out">
      <AccountEmpty :message="t('orders.signInRequired')" :note="t('orders.signInNote')" compact />
      <div class="orders-signed-out__actions">
        <NuxtLink to="/auth/login"
          ><BaseButton variant="primary">{{ t('header.signIn') }}</BaseButton></NuxtLink
        >
      </div>
    </div>

    <div v-else-if="status === 'pending'" class="orders-skeleton" aria-hidden="true">
      <div v-for="index in 2" :key="index" class="order-card order-card--skeleton">
        <BaseSkeleton variant="text" />
        <div class="order-card__skeleton-row">
          <BaseSkeleton variant="block" />
          <BaseSkeleton variant="text" />
        </div>
      </div>
    </div>

    <AccountEmpty
      v-else-if="filteredOrders.length === 0"
      :message="t('orders.emptyTab')"
      :note="t('orders.emptyTabNote')"
    />

    <template v-else>
      <ul class="orders-list">
        <li v-for="order in pagedOrders" :key="order.public_id">
          <article class="order-card">
            <header class="order-card__head">
              <div class="order-card__meta">
                <span class="order-card__number">#{{ String(order.public_id).toUpperCase() }}</span>
                <span class="order-card__date">{{ formatDate(order.created_at) }}</span>
              </div>
              <span class="order-card__state" :class="`order-card__state--${stateClass(order)}`">
                {{ stateLabel(order) }}
              </span>
            </header>

            <ul class="order-card__items">
              <li v-for="(item, index) in order.items" :key="index" class="order-item">
                <NuxtLink
                  v-if="item.spu_public_id"
                  class="order-item__media"
                  :to="`/p/${item.spu_public_id}`"
                  tabindex="-1"
                  aria-hidden="true"
                >
                  <img v-if="item.image_path" :src="item.image_path" alt="" loading="lazy" />
                  <span v-else class="order-item__placeholder">
                    <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
                      <path
                        d="M12 2 3 7v10l9 5 9-5V7l-9-5Zm0 2.3L18.6 8 12 11.7 5.4 8 12 4.3ZM5 9.7l6 3.3v6.4l-6-3.3V9.7Zm8 9.7V13l6-3.3v6.4l-6 3.3Z"
                        fill="currentColor"
                      />
                    </svg>
                  </span>
                </NuxtLink>
                <span v-else class="order-item__media order-item__placeholder">
                  <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
                    <path
                      d="M12 2 3 7v10l9 5 9-5V7l-9-5Zm0 2.3L18.6 8 12 11.7 5.4 8 12 4.3ZM5 9.7l6 3.3v6.4l-6-3.3V9.7Zm8 9.7V13l6-3.3v6.4l-6 3.3Z"
                      fill="currentColor"
                    />
                  </svg>
                </span>
                <div class="order-item__body">
                  <NuxtLink
                    v-if="item.spu_public_id"
                    class="order-item__title"
                    :to="`/p/${item.spu_public_id}`"
                  >
                    {{ item.title }}
                  </NuxtLink>
                  <span v-else class="order-item__title">{{ item.title }}</span>
                  <span class="order-item__qty"
                    >{{ t('orders.quantity') }}: {{ item.quantity }}</span
                  >
                </div>
                <span class="order-item__price">{{ itemPrice(item) }}</span>
              </li>
            </ul>

            <footer class="order-card__foot">
              <span class="order-card__total">
                {{ t('orders.total') }}
                <strong>{{ orderTotal(order) }}</strong>
              </span>
              <NuxtLink class="order-card__detail" :to="`/account/orders/${order.public_id}`">
                {{ t('orders.viewDetails') }}
              </NuxtLink>
            </footer>
          </article>
        </li>
      </ul>

      <AccountPager :page="page" :total-pages="totalPages" @change="goToPage" />
    </template>
  </AccountShell>
</template>

<style scoped>
.orders-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin: var(--space-4) 0 0;
  padding: 0;
  list-style: none;
}

.order-card {
  border: 1px solid var(--colour-border);
  border-radius: 4px;
  background: var(--colour-surface);
}

.order-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--colour-border);
}

.order-card__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-3);
}

.order-card__number {
  font-weight: var(--font-weight-semibold);
  /* 新编号（JYO+YYYYMMDD+6 位）必须整号可见：等宽 + 不换行，父容器可横向滚动。 */
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.order-card__date {
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}

.order-card__state {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
}

.order-card__state--pending {
  color: var(--colour-warning);
}

.order-card__state--shipped {
  color: var(--colour-info);
}

.order-card__state--completed {
  color: var(--colour-success);
}

.order-card__state--canceled {
  color: var(--colour-muted);
}

.order-card__items {
  margin: 0;
  padding: 0 var(--space-4);
  list-style: none;
}

.order-item {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-4) 0;
  border-bottom: 1px solid var(--colour-surface-muted);
}

.order-item:last-child {
  border-bottom: 0;
}

.order-item__media {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
  flex: 0 0 auto;
  border-radius: var(--radius-md);
  background: var(--colour-surface-soft);
  overflow: hidden;
}

.order-item__media img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  mix-blend-mode: multiply;
}

.order-item__placeholder {
  color: var(--colour-border-strong);
}

.order-item__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.order-item__title {
  display: block;

  overflow: visible;
  color: var(--colour-text);
  font-size: var(--font-size-md);
  text-decoration: none;
  word-break: break-word;
}

.order-item__title:hover {
  color: var(--colour-accent);
}

.order-item__qty {
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}

.order-item__price {
  color: var(--colour-text);
  font-weight: var(--font-weight-semibold);
}

.order-card__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-4);
  border-top: 1px solid var(--colour-border);
}

.order-card__total {
  color: var(--colour-text-secondary);
  font-size: var(--font-size-md);
}

.order-card__total strong {
  margin-left: var(--space-2);
  color: var(--colour-text);
  font-size: var(--font-size-lg);
}

.order-card__detail {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 40px;
  padding: 0 var(--space-4);
  border: 1px solid var(--colour-border-strong);
  border-radius: var(--radius-pill);
  color: var(--colour-text);
  font-size: var(--font-size-md);
  text-decoration: none;
}

.order-card__detail:hover {
  background: var(--colour-surface-muted);
}

.orders-signed-out {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.orders-signed-out__actions {
  padding-bottom: var(--space-8);
}

.orders-signed-out__actions :deep(a) {
  text-decoration: none;
}

.orders-skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin-top: var(--space-4);
}

.order-card--skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
}

.order-card__skeleton-row {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.order-card__skeleton-row :deep(.base-skeleton--block) {
  width: 72px;
  flex: 0 0 auto;
}
</style>
