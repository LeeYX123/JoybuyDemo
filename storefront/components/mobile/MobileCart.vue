<script setup>
import { useLocale } from '../../composables/useLocale'

// Mobile cart (docs/20 §3): 72px-square line cards (two-line title, red unit
// price, quantity stepper, delete), a summary block with the 20px/700 red
// total and the full-width 48px solid-red checkout button, and the empty-cart
// state reusing the desktop cart.empty/cart.goShopping copy. No floating
// bottom bar — the checkout button lives inside the summary block. All
// business state (selection, mutations, product images/specs) stays in
// pages/cart/index.vue — this component receives resolved rows as props and
// emits user actions back (ADR 0001: desktop template untouched).
defineProps({
  rows: { type: Array, default: () => [] },
  subtotalText: { type: String, default: '' },
  selectedCount: { type: Number, default: 0 },
  needsAttention: { type: Boolean, default: false },
})

const emit = defineEmits(['step', 'remove', 'checkout', 'back'])

const { t } = useLocale()
</script>

<template>
  <div class="m-cart">
    <MobilePageHeader :title="t('cart.title')" @back="emit('back')" />

    <!-- Empty cart (docs/20 §3, desktop cart.empty copy). -->
    <div v-if="rows.length === 0" class="m-cart__empty" role="status">
      <p class="m-cart__empty-text">{{ t('cart.empty') }}</p>
      <NuxtLink to="/" class="m-cart__shopping">{{ t('cart.goShopping') }}</NuxtLink>
    </div>

    <template v-else>
      <p v-if="needsAttention" class="m-cart__notice" role="alert">
        {{ t('cart.priceChangedNotice') }}
      </p>

      <!-- Line cards: white radius-12 cards with 8px gaps. -->
      <ul class="m-cart__list">
        <li
          v-for="row in rows"
          :key="row.public_id"
          class="m-cart__row"
          :class="{ 'm-cart__row--invalid': !row.isValid }"
        >
          <NuxtLink class="m-cart__img-link" :to="`/p/${row.spu_public_id}`">
            <img
              v-if="row.image"
              class="m-cart__img"
              :src="row.image"
              :alt="row.title"
              width="72"
              height="72"
              loading="lazy"
            />
            <span v-else class="m-cart__img m-cart__img--placeholder" aria-hidden="true"></span>
          </NuxtLink>

          <div class="m-cart__body">
            <NuxtLink class="m-cart__name" :to="`/p/${row.spu_public_id}`">
              {{ row.title }}
            </NuxtLink>
            <p v-if="row.spec" class="m-cart__spec">{{ row.spec }}</p>
            <span v-if="row.isValid" class="m-cart__price">{{ row.line }}</span>

            <div class="m-cart__actions">
              <div v-if="row.isValid" class="m-cart__stepper" :aria-label="t('cart.quantity')">
                <button
                  type="button"
                  class="m-cart__step-btn"
                  :disabled="row.quantity <= 1"
                  aria-label="-"
                  @click="emit('step', row, -1)"
                >
                  −
                </button>
                <span class="m-cart__step-value" aria-live="polite">{{ row.quantity }}</span>
                <button
                  type="button"
                  class="m-cart__step-btn"
                  aria-label="+"
                  @click="emit('step', row, 1)"
                >
                  +
                </button>
              </div>
              <button type="button" class="m-cart__delete" @click="emit('remove', row)">
                {{ t('cart.remove') }}
              </button>
            </div>
          </div>
        </li>
      </ul>

      <!-- Summary block: red 20px/700 total + full-width 48px solid-red
           checkout button (docs/20 §3, no floating bar). -->
      <section class="m-cart__summary">
        <div class="m-cart__total-row">
          <span class="m-cart__total-label">{{ t('cart.subtotal') }}</span>
          <strong class="m-cart__total-value">{{ subtotalText || '—' }}</strong>
        </div>
        <button type="button" class="m-cart__checkout" @click="emit('checkout')">
          {{ t('cart.goToCheckout') }} ({{ selectedCount }})
        </button>
        <p class="m-cart__secure">{{ t('cart.securePayment') }}</p>
      </section>
    </template>
  </div>
</template>

<style scoped>
.m-cart {
  min-height: 60vh;
  padding-bottom: 24px;
  background: #f5f6fa;
}

/* --- Empty state --- */
.m-cart__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin: 24px 16px;
  padding: 40px 16px;
  border-radius: 12px;
  background: #ffffff;
}

.m-cart__empty-text {
  margin: 0;
  color: #c2c4cc;
  font-size: 18px;
  line-height: 24px;
}

.m-cart__shopping {
  display: inline-block;
  margin-top: 12px;
  padding: 8px 16px;
  border: 1px solid #888b94;
  border-radius: 4px;
  color: #1a1a1a;
  font-size: 14px;
  text-decoration: none;
}

/* --- Price-changed notice --- */
.m-cart__notice {
  margin: 12px 16px 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: #fff5e6;
  color: #995c00;
  font-size: 13px;
  line-height: 18px;
}

/* --- Line cards --- */
.m-cart__list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 12px 16px 0;
  padding: 0;
  list-style: none;
}

.m-cart__row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  border-radius: 12px;
  background: #ffffff;
}

.m-cart__row--invalid .m-cart__name,
.m-cart__row--invalid .m-cart__img {
  opacity: 0.5;
}

.m-cart__img {
  display: block;
  width: 72px;
  height: 72px;
  flex-shrink: 0;
  border-radius: 8px;
  object-fit: contain;
  background: #ffffff;
}

.m-cart__img--placeholder {
  background: #f5f6fa;
}

.m-cart__body {
  flex: 1 1 auto;
  min-width: 0;
}

.m-cart__name {
  display: -webkit-box;
  overflow: hidden;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  color: #1a1a1a;
  font-size: 14px;
  font-weight: 500;
  line-height: 20px;
  text-decoration: none;
  word-break: break-word;
}

.m-cart__spec {
  margin: 4px 0 0;
  color: #888b94;
  font-size: 12px;
  line-height: 16px;
  word-break: break-all;
}

/* Unit price: site red (docs/19 §0 #E1251B family). */
.m-cart__price {
  display: block;
  margin-top: 4px;
  color: #e1251b;
  font-size: 15px;
  font-weight: var(--font-weight-bold);
  line-height: 20px;
}

.m-cart__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 10px;
}

.m-cart__stepper {
  display: inline-flex;
  align-items: center;
  height: 32px;
  border: 1px solid #e0e1e5;
  border-radius: 16px;
  overflow: hidden;
  background: #ffffff;
}

.m-cart__step-btn {
  width: 32px;
  height: 100%;
  padding: 0;
  border: 0;
  background: #ffffff;
  color: #1a1a1a;
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
}

.m-cart__step-btn:disabled {
  color: #c2c4cc;
  cursor: not-allowed;
}

.m-cart__step-value {
  min-width: 36px;
  color: #1a1a1a;
  font-size: 14px;
  font-weight: 500;
  text-align: center;
}

.m-cart__delete {
  height: 32px;
  padding: 0;
  border: 0;
  background: none;
  color: #73757d;
  font-size: 13px;
  cursor: pointer;
}

/* --- Summary block --- */
.m-cart__summary {
  margin: 12px 16px 0;
  padding: 16px;
  border-radius: 12px;
  background: #ffffff;
}

.m-cart__total-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}

.m-cart__total-label {
  color: #1a1a1a;
  font-size: 14px;
  line-height: 20px;
}

/* Total: red 20px/700 (docs/20 §3). */
.m-cart__total-value {
  color: #e1251b;
  font-size: 20px;
  font-weight: var(--font-weight-bold);
  line-height: 24px;
}

/* Checkout button: full-width 48px solid red. */
.m-cart__checkout {
  width: 100%;
  height: 48px;
  margin-top: 12px;
  padding: 0 16px;
  border: 0;
  border-radius: 24px;
  background: #e1251b;
  color: #ffffff;
  font: inherit;
  font-size: 16px;
  font-weight: var(--font-weight-bold);
  cursor: pointer;
}

.m-cart__checkout:hover {
  background: #d14335;
}

.m-cart__secure {
  margin: 10px 0 0;
  color: #888b94;
  font-size: 12px;
  line-height: 16px;
  text-align: center;
}
</style>
