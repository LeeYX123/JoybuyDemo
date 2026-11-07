<script setup>
import { computed } from 'vue'
import { useFetch, useRequestHeaders, useRuntimeConfig } from '#imports'

import { formatDisplayPrice } from '../../../utils/display'

// 买家订单列表（迭代02）：下单即支付成功（PAID），展示状态/金额，
// 点击进入订单详情（详情里可确认收货）。
const config = useRuntimeConfig()

const url = computed(() =>
  import.meta.server ? `${config.apiBaseInternal}/orders` : `/api/v1/orders`,
)

const { data } = await useFetch(url, {
  key: 'buyer-orders',
  headers: {
    cookie: useRequestHeaders(['cookie']).cookie || '',
    // 迭代02：时间展示按看的人所在时区（后端按此头转换，只影响展示）。
    'X-Client-Timezone':
      typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone || '' : '',
  },
})

const orders = computed(() => (Array.isArray(data.value?.orders) ? data.value.orders : []))

const STATUS_LABELS = {
  PAID: '已支付 / Paid',
  PENDING_PAYMENT: '待支付 / Pending payment',
  CANCELED: '已取消 / Canceled',
}

function statusClass(status) {
  if (status === 'PAID') return 'paid'
  if (status === 'CANCELED') return 'canceled'
  return ''
}

useHead({ title: 'Your orders' })
</script>

<template>
  <AppContainer narrow>
    <section class="orders" aria-labelledby="orders-title">
      <h1 id="orders-title">Your orders</h1>

      <p v-if="orders.length === 0" class="orders__empty" role="status">You have no orders yet.</p>

      <ul class="orders__list">
        <li v-for="order in orders" :key="order.public_id" class="order-row">
          <NuxtLink :to="`/account/orders/${order.public_id}`" class="order-row__info">
            <span class="order-row__id">#{{ order.public_id.slice(0, 8) }}</span>
            <span class="order-row__status" :class="statusClass(order.status)">
              {{ STATUS_LABELS[order.status] || order.status }}
            </span>
            <span class="order-row__meta">
              {{ order.item_count }} item(s) · {{ formatDisplayPrice(order.total) }}
            </span>
          </NuxtLink>
          <NuxtLink :to="`/account/orders/${order.public_id}`" class="order-row__link">
            View details →
          </NuxtLink>
        </li>
      </ul>
    </section>
  </AppContainer>
</template>

<style scoped>
.orders {
  margin-block: var(--space-10);
}

.orders__empty {
  margin-top: var(--space-5);
  color: var(--colour-muted);
}

.orders__list {
  margin-top: var(--space-5);
}

.order-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  border-top: 1px solid var(--colour-border);
  padding-block: var(--space-4);
}

.order-row__info {
  display: block;
  color: inherit;
  text-decoration: none;
}

.order-row__id {
  font-weight: var(--font-weight-semibold);
}

.order-row__status {
  display: block;
  color: var(--colour-warning);
  font-size: var(--font-size-sm);
}

.order-row__status.paid {
  color: var(--colour-success, #16a34a);
}

.order-row__status.canceled {
  color: var(--colour-error);
}

.order-row__meta {
  display: block;
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}

.order-row__link {
  color: var(--colour-text);
  font-size: var(--font-size-sm);
}
</style>
