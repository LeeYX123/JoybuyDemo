<script setup>
import { computed, ref } from 'vue'
import { useFetch, useRequestHeaders, useRouter, useRuntimeConfig } from '#imports'

import { useLocale } from '../../../composables/useLocale'
import { useMobileView } from '../../../composables/useMobileView'
import { formatDisplayPrice } from '../../../utils/display'

// 订单详情（迭代02）：状态/金额/支付方式/商品行/地址，
// 存在未完成商家子单时显示【确认收货】——点击即全部完成并回款商家。
const route = useRoute()
const router = useRouter()
const { t } = useLocale()
const config = useRuntimeConfig()
// ADR 0001: on the m. host the same payload renders the mobile order detail
// (docs/20 §5.2); the desktop template below is untouched.
const { isMobileHost } = useMobileView()

const publicId = computed(() => String(route.params.id || ''))

const detailUrl = computed(() =>
  import.meta.server
    ? `${config.apiBaseInternal}/orders/${publicId.value}`
    : `/api/v1/orders/${publicId.value}`,
)

const { data, status, error, refresh } = await useFetch(detailUrl, {
  key: `buyer-order-${publicId.value}`,
  headers: {
    cookie: useRequestHeaders(['cookie']).cookie || '',
    // 迭代02：时间展示按看的人所在时区（后端按此头转换，只影响展示）。
    'X-Client-Timezone':
      typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone || '' : '',
  },
})

const order = computed(() => data.value || null)
const merchantOrders = computed(() =>
  Array.isArray(order.value?.merchant_orders) ? order.value.merchant_orders : [],
)
const allCompleted = computed(
  () => merchantOrders.value.length > 0 && merchantOrders.value.every((m) => m.progress >= 7),
)

// 2026-11-27 全站编号改造：订单详情内嵌 payments / shipments（后端阶段 2 已直出
// public_id），这里只做展示，不截断——JYPAY/JYLOG + 日期 + 6 位必须整号可见。
const paymentNumbers = computed(() =>
  (Array.isArray(order.value?.payments) ? order.value.payments : [])
    .map((payment) => String(payment.public_id || ''))
    .filter(Boolean),
)
const shipmentNumbers = computed(() =>
  (Array.isArray(order.value?.shipments) ? order.value.shipments : [])
    .map((shipment) => String(shipment.public_id || ''))
    .filter(Boolean),
)

const confirming = ref(false)
const confirmError = ref('')

async function confirmReceipt() {
  confirming.value = true
  confirmError.value = ''
  try {
    const session = await $fetch(
      import.meta.server
        ? `${config.apiBaseInternal}/auth/buyer/session`
        : '/api/v1/auth/buyer/session',
      { credentials: 'include' },
    )
    const response = await $fetch(`/api/v1/orders/${publicId.value}/confirm-receipt`, {
      method: 'POST',
      headers: { 'X-CSRFToken': session?.csrf_token || '' },
      credentials: 'include',
      ignoreResponseError: true,
    })
    if (response?.error) {
      confirmError.value = response.error.message || 'Could not confirm the receipt.'
    } else {
      await refresh()
    }
  } catch (err) {
    confirmError.value = err?.message || 'Could not confirm the receipt.'
  } finally {
    confirming.value = false
  }
}

// 2026-11-28 三态口径：详情与列表同源，优先用后端 `state`
// （TO_SHIP/SHIPPED/COMPLETED）；未付款仍按原状态展示。
// 2026-11-29 用户口径：购物端没有「已取消」概念，CANCELED 不映射文案，
// 直接落到三态兜底（买家从不展示「已取消」）。
const STATUS_KEYS = {
  TO_SHIP: 'orders.statusToShip',
  SHIPPED: 'orders.statusShipped',
  COMPLETED: 'orders.statusCompleted',
  PAID: 'orders.statusPaid',
  PENDING_PAYMENT: 'orders.statusPendingPayment',
}

function statusLabel(order) {
  const key = order?.state || order?.status
  return t(STATUS_KEYS[key] || 'orders.statusToShip')
}

// Mobile detail view model (docs/20 §5.2): status card / address / items /
// amounts / payment method; confirm-receipt flags reuse the desktop logic.
const mobileOrder = computed(() => {
  if (!order.value) return null
  const shipping = order.value.shipping_address
  return {
    number: String(order.value.public_id || '').toUpperCase(),
    statusLabel: statusLabel(order.value),
    placedAt: order.value.created_at?.slice(0, 16).replace('T', ' ') || '',
    paymentMethod: order.value.payment_method || '',
    total: formatDisplayPrice(order.value.total),
    address: shipping
      ? `${shipping.full_name} · ${shipping.line1}, ${shipping.city} ${shipping.postcode}`
      : '',
    items: (Array.isArray(order.value.items) ? order.value.items : []).map((item) => ({
      title: item.title,
      qty: item.quantity,
      price: formatDisplayPrice(item.unit_price),
      image: item.image_path || '',
    })),
    showConfirm: !allCompleted.value && order.value.status === 'PAID',
    completed: allCompleted.value,
    paymentNumbers: paymentNumbers.value,
    shipmentNumbers: shipmentNumbers.value,
  }
})

useHead(() => ({
  title: order.value
    ? `${t('orders.orderNumber')} #${String(order.value.public_id || '').toUpperCase()}`
    : t('orders.orderNumber'),
}))
</script>

<template>
  <!-- ADR 0001: mobile host renders the docs/20 §5.2 mobile order detail;
       the desktop template below is untouched. -->
  <MobileOrderDetail
    v-if="isMobileHost"
    :loading="status === 'pending'"
    :not-found="Boolean(error)"
    :order="mobileOrder"
    :confirming="confirming"
    @back="router.back()"
    @confirm="confirmReceipt"
  />
  <AppContainer v-else narrow>
    <section class="order-detail" aria-labelledby="order-title">
      <NuxtLink to="/account/orders" class="order-detail__back">{{
        t('orders.backToOrders')
      }}</NuxtLink>

      <p v-if="status === 'pending'" class="order-detail__hint">{{ t('common.loading') }}</p>
      <template v-else-if="order">
        <h1 id="order-title">
          {{ t('orders.orderNumber') }} #{{ String(order.public_id).toUpperCase() }}
        </h1>

        <dl class="order-detail__meta">
          <div>
            <dt>{{ t('orders.status') }}</dt>
            <dd>{{ statusLabel(order) }}</dd>
          </div>
          <div>
            <dt>{{ t('orders.placedAt') }}</dt>
            <dd>{{ order.created_at?.slice(0, 16).replace('T', ' ') }}</dd>
          </div>
          <div v-if="order.payment_method">
            <dt>{{ t('orders.payment') }}</dt>
            <dd>{{ order.payment_method }}</dd>
          </div>
          <!-- 阶段 3：支付单号 / 物流单号整号展示（不截断）。 -->
          <div v-if="paymentNumbers.length">
            <dt>{{ t('orders.paymentNumber') }}</dt>
            <dd class="order-detail__ids">
              <span v-for="number in paymentNumbers" :key="number">{{ number }}</span>
            </dd>
          </div>
          <div v-if="shipmentNumbers.length">
            <dt>{{ t('orders.shipmentNumber') }}</dt>
            <dd class="order-detail__ids">
              <span v-for="number in shipmentNumbers" :key="number">{{ number }}</span>
            </dd>
          </div>
          <div>
            <dt>{{ t('orders.total') }}</dt>
            <dd>{{ formatDisplayPrice(order.total) }}</dd>
          </div>
        </dl>

        <ul class="order-detail__items">
          <li v-for="(item, index) in order.items" :key="index">
            <span class="order-detail__item-name">{{ item.title }}</span>
            <span class="order-detail__item-qty">×{{ item.quantity }}</span>
            <b>{{ formatDisplayPrice(item.unit_price) }}</b>
          </li>
        </ul>

        <address class="order-detail__address">
          {{ order.shipping_address?.full_name }} · {{ order.shipping_address?.line1 }},
          {{ order.shipping_address?.city }} {{ order.shipping_address?.postcode }}
        </address>

        <p v-if="confirmError" class="order-detail__error" role="alert">{{ confirmError }}</p>

        <BaseButton
          v-if="!allCompleted && order.status === 'PAID'"
          variant="primary"
          :disabled="confirming"
          @click="confirmReceipt"
        >
          {{ confirming ? t('order.confirming') : t('order.confirmReceipt') }}
        </BaseButton>
        <p v-else-if="allCompleted" class="order-detail__done">
          {{ t('order.completed') }}
        </p>
      </template>
      <p v-else-if="error" class="order-detail__hint">{{ t('order.notFound') }}</p>
    </section>
  </AppContainer>
</template>

<style scoped>
.order-detail {
  margin-block: var(--space-10);
}

.order-detail__back {
  display: inline-block;
  margin-bottom: var(--space-4);
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
  text-decoration: none;
}

.order-detail__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-6);
  margin: var(--space-4) 0;
}

.order-detail__meta dt {
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}

.order-detail__meta dd {
  margin: 2px 0 0;
  font-weight: var(--font-weight-semibold);
}

/* 完整编号：等宽 + 不换行（JYPAY/JYLOG 17 位） */
.order-detail__ids {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: var(--font-size-sm);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.order-detail__items {
  list-style: none;
  margin: var(--space-5) 0;
  padding: 0;
}

.order-detail__items li {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  border-top: 1px solid var(--colour-border);
  padding-block: var(--space-3);
}

.order-detail__item-name {
  flex: 1;
}

.order-detail__item-qty {
  color: var(--colour-muted);
}

.order-detail__address {
  font-style: normal;
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}

.order-detail__hint {
  color: var(--colour-muted);
}

.order-detail__error {
  color: var(--colour-error);
}

.order-detail__done {
  color: var(--colour-success, #16a34a);
  font-weight: var(--font-weight-semibold);
}
</style>
