<script setup>
import { computed } from 'vue'
import { useFetch, useHead, useRequestHeaders, useRouter, useRuntimeConfig } from '#imports'

import { useBuyerAuth } from '../../composables/useBuyerAuth'
import { useLocale } from '../../composables/useLocale'

// Messages (docs/20 §5.7, mobile-only surface): the drawer「消息」row lands
// here. Two tabs — 客服 (entry to /help/customer-service) and 订单 (order
// status notifications built from the same orders endpoint the account hub
// uses; the backend has no dedicated notifications API yet). There is no
// desktop counterpart, so the mobile component renders on both hosts.
const { t } = useLocale()
const { isAuthenticated } = useBuyerAuth()
const router = useRouter()
const config = useRuntimeConfig()

const ordersUrl = computed(() =>
  import.meta.server ? `${config.apiBaseInternal}/orders` : '/api/v1/orders',
)

const { data } = await useFetch(ordersUrl, {
  key: 'buyer-orders',
  headers: {
    cookie: useRequestHeaders(['cookie']).cookie || '',
    'X-Client-Timezone':
      typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone || '' : '',
  },
})

// 2026-11-29 用户口径：购物端没有「已取消」概念，买家侧不展示 CANCELED。
const orders = computed(() =>
  (Array.isArray(data.value?.orders) ? data.value.orders : []).filter(
    (order) => order.state !== 'CANCELED',
  ),
)

const STATUS_CLASSES = {
  PENDING_PAYMENT: 'pending',
  TO_SHIP: 'pending',
  SHIPPED: 'shipped',
  COMPLETED: 'completed',
}

const STATUS_KEYS = {
  PENDING_PAYMENT: 'orders.statusPendingPayment',
  TO_SHIP: 'orders.statusToShip',
  SHIPPED: 'orders.statusShipped',
  COMPLETED: 'orders.statusCompleted',
}

// Most recent orders first, capped to keep the feed short.
const notifications = computed(() =>
  orders.value.slice(0, 10).map((order) => ({
    key: order.public_id,
    publicId: order.public_id,
    // 2026-11-27 全站编号改造：显示完整订单号（JYO+YYYYMMDD+6 位），不截断。
    number: String(order.public_id || '').toUpperCase(),
    statusLabel: t(STATUS_KEYS[order.state] || 'orders.statusToShip'),
    statusClass: STATUS_CLASSES[order.state] || 'pending',
    date: String(order.created_at || '')
      .slice(0, 16)
      .replace('T', ' '),
  })),
)

useHead(() => ({ title: t('mobile.messages.title') }))
</script>

<template>
  <MobileMessages
    :signed-in="isAuthenticated"
    :notifications="notifications"
    @back="router.back()"
  />
</template>
