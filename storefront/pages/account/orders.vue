<script setup>
import { computed } from 'vue'
import { useFetch, useRequestHeaders, useRuntimeConfig } from '#imports'

import { formatDisplayPrice } from '../../utils/display'

// Buyer orders: pending and canceled (phase 1 states). The pay button
// surfaces the region-unsupported business error from the backend.
const config = useRuntimeConfig()

const url = computed(() =>
  import.meta.server ? `${config.apiBaseInternal}/orders` : `/api/v1/orders`,
)

const { data, refresh } = await useFetch(url, {
  key: 'buyer-orders',
  headers: { cookie: useRequestHeaders(['cookie']).cookie || '' },
})

const orders = computed(() => (Array.isArray(data.value?.orders) ? data.value.orders : []))

async function tryPay(publicId) {
  const session = await $fetch(
    import.meta.server
      ? `${config.apiBaseInternal}/auth/buyer/session`
      : '/api/v1/auth/buyer/session',
    { credentials: 'include' },
  )
  const response = await $fetch(`/api/v1/orders/${publicId}/payment-attempt`, {
    method: 'POST',
    headers: { 'X-CSRFToken': session?.csrf_token || '' },
    credentials: 'include',
    ignoreResponseError: true,
  })
  if (response?.error) {
    // docs/06 §4.2: the pay button always ends here in phase 1.
    window.alert('当前地区暂不支持 / Payment is not available in your region.')
  }
  await refresh()
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
          <div class="order-row__info">
            <span class="order-row__id">#{{ order.public_id.slice(0, 8) }}</span>
            <span class="order-row__status" :class="{ canceled: order.status === 'CANCELED' }">
              {{ order.status === 'CANCELED' ? 'Canceled' : 'Pending payment' }}
            </span>
            <span class="order-row__meta">
              {{ order.item_count }} item(s) · {{ formatDisplayPrice(order.total) }}
            </span>
          </div>
          <BaseButton
            v-if="order.status !== 'CANCELED'"
            variant="primary"
            @click="tryPay(order.public_id)"
          >
            Pay now
          </BaseButton>
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

.order-row__id {
  font-weight: var(--font-weight-semibold);
}

.order-row__status {
  display: block;
  color: var(--colour-warning);
  font-size: var(--font-size-sm);
}

.order-row__status.canceled {
  color: var(--colour-error);
}

.order-row__meta {
  display: block;
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}
</style>
