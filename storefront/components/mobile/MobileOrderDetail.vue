<script setup>
import { useLocale } from '../../composables/useLocale'

// Mobile order detail (docs/20 §5.2): status card (number/status/placed at/
// total), shipping-address card, item line cards, amount summary and the
// payment method row. Presentational — the confirm-receipt flow stays in
// pages/account/orders/[id].vue and is emitted back (ADR 0001: desktop
// template untouched).
defineProps({
  loading: { type: Boolean, default: false },
  notFound: { type: Boolean, default: false },
  order: { type: Object, default: null },
  confirming: { type: Boolean, default: false },
})

const emit = defineEmits(['confirm', 'back'])

const { t } = useLocale()
</script>

<template>
  <div class="m-odetail">
    <MobilePageHeader :title="t('orders.orderNumber')" @back="emit('back')" />

    <p v-if="loading" class="m-odetail__hint" role="status">{{ t('common.loading') }}</p>

    <p v-else-if="notFound" class="m-odetail__hint" role="alert">{{ t('order.notFound') }}</p>

    <template v-else-if="order">
      <!-- Status card -->
      <section class="m-odetail__card">
        <div class="m-odetail__status-row">
          <span class="m-odetail__number">#{{ order.number }}</span>
          <span class="m-odetail__badge">{{ order.statusLabel }}</span>
        </div>
        <dl class="m-odetail__meta">
          <div class="m-odetail__meta-row">
            <dt>{{ t('orders.placedAt') }}</dt>
            <dd>{{ order.placedAt }}</dd>
          </div>
          <div v-if="order.paymentMethod" class="m-odetail__meta-row">
            <dt>{{ t('orders.payment') }}</dt>
            <dd>{{ order.paymentMethod }}</dd>
          </div>
          <!-- 阶段 3：支付单号 / 物流单号整号展示，不截断。 -->
          <div
            v-for="number in order.paymentNumbers || []"
            :key="`pay-${number}`"
            class="m-odetail__meta-row"
          >
            <dt>{{ t('orders.paymentNumber') }}</dt>
            <dd class="m-odetail__id">{{ number }}</dd>
          </div>
          <div
            v-for="number in order.shipmentNumbers || []"
            :key="`ship-${number}`"
            class="m-odetail__meta-row"
          >
            <dt>{{ t('orders.shipmentNumber') }}</dt>
            <dd class="m-odetail__id">{{ number }}</dd>
          </div>
          <div class="m-odetail__meta-row">
            <dt>{{ t('orders.total') }}</dt>
            <dd class="m-odetail__total">{{ order.total }}</dd>
          </div>
        </dl>
      </section>

      <!-- Shipping address -->
      <section v-if="order.address" class="m-odetail__card">
        <h2 class="m-odetail__card-title">{{ t('addresses.title') }}</h2>
        <p class="m-odetail__address">{{ order.address }}</p>
      </section>

      <!-- Items -->
      <section class="m-odetail__card">
        <h2 class="m-odetail__card-title">{{ t('accountMenu.orders') }}</h2>
        <ul class="m-odetail__items">
          <li v-for="(item, index) in order.items" :key="index" class="m-odetail__item">
            <img
              v-if="item.image"
              class="m-odetail__img"
              :src="item.image"
              :alt="item.title"
              loading="lazy"
            />
            <span v-else class="m-odetail__img m-odetail__img--placeholder" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="22" height="22">
                <path
                  d="M12 2 3 7v10l9 5 9-5V7l-9-5Zm0 2.3L18.6 8 12 11.7 5.4 8 12 4.3ZM5 9.7l6 3.3v6.4l-6-3.3V9.7Zm8 9.7V13l6-3.3v6.4l-6 3.3Z"
                  fill="currentColor"
                />
              </svg>
            </span>
            <span class="m-odetail__item-name">{{ item.title }}</span>
            <span class="m-odetail__item-qty">×{{ item.qty }}</span>
            <span class="m-odetail__item-price">{{ item.price }}</span>
          </li>
        </ul>
      </section>

      <p v-if="order.completed" class="m-odetail__done">{{ t('order.completed') }}</p>

      <button
        v-else-if="order.showConfirm"
        type="button"
        class="m-odetail__confirm"
        :disabled="confirming"
        @click="emit('confirm')"
      >
        {{ confirming ? t('order.confirming') : t('order.confirmReceipt') }}
      </button>
    </template>
  </div>
</template>

<style scoped>
.m-odetail {
  min-height: 60vh;
  padding-bottom: 24px;
  background: #f5f6fa;
}

.m-odetail__hint {
  margin: 24px 16px;
  padding: 32px 16px;
  border-radius: 12px;
  background: #ffffff;
  color: #7a7d85;
  font-size: 15px;
  text-align: center;
}

.m-odetail__card {
  margin: 12px 16px 0;
  padding: 14px;
  border-radius: 12px;
  background: #ffffff;
}

.m-odetail__status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.m-odetail__number {
  color: #1a1a1a;
  font-size: 16px;
  font-weight: var(--font-weight-bold);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.m-odetail__badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 4px;
  background: #fff5e6;
  color: #995c00;
  font-size: 13px;
  font-weight: var(--font-weight-semibold);
}

.m-odetail__meta {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 12px 0 0;
}

.m-odetail__meta-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.m-odetail__meta-row dt {
  color: #7a7d85;
  font-size: 14px;
}

.m-odetail__id {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  /* 去截断：编号整号展示，窄屏允许折行，不用省略号也不裁切。 */
  white-space: normal;
  word-break: break-all;
  overflow: visible;
  max-width: none;
}

.m-odetail__meta-row dd {
  margin: 0;
  color: #1a1a1a;
  font-size: 14px;
  font-weight: var(--font-weight-semibold);
}

.m-odetail__total {
  color: #e1251b !important;
  font-size: 18px !important;
  font-weight: var(--font-weight-bold) !important;
}

.m-odetail__card-title {
  margin: 0;
  color: #1a1a1a;
  font-size: 15px;
  font-weight: var(--font-weight-bold);
}

.m-odetail__address {
  margin: 8px 0 0;
  color: #55565b;
  font-size: 14px;
  line-height: 1.5;
}

.m-odetail__items {
  display: flex;
  flex-direction: column;
  margin: 4px 0 0;
  padding: 0;
  list-style: none;
}

.m-odetail__item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid #f0f1f2;
}

.m-odetail__item:last-child {
  border-bottom: 0;
  padding-bottom: 0;
}

.m-odetail__img {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  flex-shrink: 0;
  border-radius: 8px;
  object-fit: cover;
  background: #f5f6fa;
  color: #c2c4cc;
}

.m-odetail__item-name {
  flex: 1;
  min-width: 0;
  display: block;

  overflow: visible;
  color: #1a1a1a;
  font-size: 14px;
  line-height: 20px;
  word-break: break-word;
}

.m-odetail__item-qty {
  color: #7a7d85;
  font-size: 13px;
  white-space: nowrap;
}

.m-odetail__item-price {
  color: #1a1a1a;
  font-size: 14px;
  font-weight: var(--font-weight-semibold);
  white-space: nowrap;
}

.m-odetail__done {
  margin: 16px 16px 0;
  padding: 14px;
  border-radius: 12px;
  background: #e8f7ec;
  color: #16a34a;
  font-size: 15px;
  font-weight: var(--font-weight-semibold);
  text-align: center;
}

.m-odetail__confirm {
  display: block;
  width: calc(100% - 32px);
  min-height: 48px;
  margin: 16px 16px 0;
  border: 0;
  border-radius: 24px;
  background: #e1251b;
  color: #ffffff;
  font: inherit;
  font-size: 16px;
  font-weight: var(--font-weight-bold);
  cursor: pointer;
}

.m-odetail__confirm:disabled {
  opacity: 0.6;
  cursor: progress;
}
</style>
