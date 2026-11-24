<script setup>
import { useLocale } from '../../composables/useLocale'

// Mobile checkout (docs/20 §4): address card (the 3-field form mirrors the
// desktop showNewForm logic — for a fresh account with no addresses the form
// is open by default, matching the desktop/e2e behaviour), item rows
// (48px image box + qty), amount summary (subtotal/delivery/total reusing the
// checkout.* copy), payment-method rows fed from the desktop paymentMethods
// data and a fixed bottom bar (total + 48px solid-red Pay now; Save during
// the address step). All business state (quote, address CRUD, order
// placement incl. the region-unsupported 422 handling) stays in
// pages/checkout/index.vue — props in, emits out (ADR 0001).
defineProps({
  step: { type: String, default: 'address' },
  addressList: { type: Array, default: () => [] },
  showNewForm: { type: Boolean, default: false },
  selectedAddressId: { type: String, default: '' },
  newAddress: { type: Object, default: null },
  error: { type: String, default: '' },
  submitting: { type: Boolean, default: false },
  paymentMethod: { type: String, default: 'balance' },
  paymentMethods: { type: Array, default: () => [] },
  selectedAddress: { type: Object, default: null },
  quoteItems: { type: Array, default: () => [] },
  subtotalText: { type: String, default: '—' },
  shippingText: { type: String, default: '—' },
  totalText: { type: String, default: '—' },
})

const emit = defineEmits([
  'select-address',
  'toggle-new-form',
  'update-address-field',
  'save-address',
  'change-step',
  'select-payment',
  'pay-now',
  'back',
])

const { t } = useLocale()
</script>

<template>
  <div class="m-checkout">
    <MobilePageHeader :title="t('checkout.title')" @back="emit('back')" />

    <div v-if="error" class="m-checkout__error" role="alert">{{ error }}</div>

    <!-- Step 1: delivery address (docs/12 §7 3-field form on mobile). -->
    <section v-if="step === 'address'" class="m-checkout__section">
      <h2 class="m-checkout__heading">{{ t('checkout.deliveryTo') }}</h2>

      <ul v-if="addressList.length > 0" class="m-checkout__addresses">
        <li v-for="address in addressList" :key="address.public_id">
          <label class="m-checkout__address">
            <input
              type="radio"
              name="m-address"
              :value="address.public_id"
              :checked="selectedAddressId === address.public_id"
              @change="emit('select-address', address.public_id)"
            />
            <span>
              {{ address.full_name }}, {{ address.line1 }}, {{ address.city }}
              {{ address.postcode }}
              <em v-if="!address.is_serviceable" class="m-checkout__unsupported">
                {{ t('checkout.notServiceable') }}
              </em>
            </span>
          </label>
        </li>
      </ul>

      <button
        v-if="addressList.length > 0"
        type="button"
        class="m-checkout__toggle"
        @click="emit('toggle-new-form')"
      >
        {{ showNewForm ? t('checkout.cancel') : t('checkout.addAddress') }}
      </button>

      <!-- Same placeholders as the desktop form (mobile form reuses the
           checkout.* keys); new accounts open this form by default. -->
      <form v-if="showNewForm" class="m-checkout__form" @submit.prevent="emit('save-address')">
        <label class="m-checkout__field">
          <span>{{ t('checkout.fullName') }}</span>
          <input
            :value="newAddress?.full_name || ''"
            :placeholder="t('checkout.fullNamePlaceholder')"
            required
            @input="emit('update-address-field', 'full_name', $event.target.value)"
          />
        </label>
        <label class="m-checkout__field">
          <span>{{ t('checkout.address') }}</span>
          <input
            :value="newAddress?.line1 || ''"
            :placeholder="t('checkout.addressPlaceholder')"
            required
            @input="emit('update-address-field', 'line1', $event.target.value)"
          />
        </label>
        <label class="m-checkout__field">
          <span>{{ t('checkout.phone') }}</span>
          <input
            :value="newAddress?.phone || ''"
            :placeholder="t('checkout.phonePlaceholder')"
            required
            @input="emit('update-address-field', 'phone', $event.target.value)"
          />
        </label>
      </form>
    </section>

    <!-- Step 2: payment (address card + items + methods + summary). -->
    <template v-else>
      <section class="m-checkout__card">
        <h2 class="m-checkout__heading">{{ t('checkout.deliveryTo') }}</h2>
        <p class="m-checkout__addr-name">{{ selectedAddress?.full_name }}</p>
        <p class="m-checkout__addr-text">
          {{
            [selectedAddress?.line1, selectedAddress?.city, selectedAddress?.postcode]
              .filter(Boolean)
              .join(', ')
          }}
        </p>
        <button
          class="m-checkout__change"
          type="button"
          :aria-label="t('checkout.deliveryTo')"
          @click="emit('change-step', 'address')"
        >
          ›
        </button>
      </section>

      <section class="m-checkout__card">
        <h2 class="m-checkout__heading">{{ t('checkout.items') }}</h2>
        <ul class="m-checkout__items">
          <li v-for="item in quoteItems" :key="item.offer_public_id" class="m-checkout__item">
            <span class="m-checkout__item-imgbox">
              <img
                v-if="item.image"
                :src="item.image"
                :alt="item.title"
                width="48"
                height="48"
                loading="lazy"
              />
            </span>
            <span class="m-checkout__item-title">{{ item.title }} × {{ item.quantity }}</span>
            <span class="m-checkout__item-price">{{ item.line }}</span>
          </li>
        </ul>
      </section>

      <section class="m-checkout__card">
        <h2 class="m-checkout__heading">{{ t('checkout.paymentMethod') }}</h2>
        <ul class="m-checkout__methods">
          <li v-for="method in paymentMethods" :key="method.value">
            <label class="m-checkout__method">
              <input
                type="radio"
                name="m-payment"
                :value="method.value"
                :checked="paymentMethod === method.value"
                @change="emit('select-payment', method.value)"
              />
              <span class="m-checkout__method-label">{{ method.label }}</span>
              <span v-if="method.note" class="m-checkout__method-note">{{ method.note }}</span>
            </label>
          </li>
        </ul>
      </section>

      <section class="m-checkout__card">
        <h2 class="m-checkout__heading">{{ t('checkout.summary') }}</h2>
        <dl class="m-checkout__totals">
          <div>
            <dt>{{ t('checkout.subtotal') }}</dt>
            <dd>{{ subtotalText }}</dd>
          </div>
          <div>
            <dt>{{ t('checkout.deliveryFee') }}</dt>
            <dd>{{ shippingText }}</dd>
          </div>
          <div class="m-checkout__totals-total">
            <dt>{{ t('checkout.orderTotal') }}</dt>
            <dd>{{ totalText }}</dd>
          </div>
        </dl>
        <p class="m-checkout__notice">{{ t('checkout.termsNotice') }}</p>
      </section>
    </template>

    <!-- Fixed bottom bar (docs/20 §0): Save during the address step, then
         total + 48px solid-red Pay now. -->
    <div class="m-checkout__bar">
      <template v-if="step === 'payment'">
        <span class="m-checkout__bar-total">{{ totalText }}</span>
        <button
          class="m-checkout__pay"
          type="button"
          :disabled="submitting"
          @click="emit('pay-now')"
        >
          {{ submitting ? t('checkout.paying') : t('checkout.payNow') }}
        </button>
      </template>
      <button v-else class="m-checkout__pay" type="button" @click="emit('save-address')">
        {{ t('checkout.save') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.m-checkout {
  /* Keep the page content clear of the fixed bottom bar. */
  min-height: 60vh;
  padding-bottom: 76px;
  background: #f5f6fa;
}

.m-checkout__error {
  margin: 12px 16px 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: #fdecea;
  color: #e1251b;
  font-size: 13px;
  line-height: 18px;
}

.m-checkout__section {
  padding: 12px 16px;
}

.m-checkout__heading {
  margin: 0 0 10px;
  color: #1a1a1a;
  font-size: 16px;
  font-weight: var(--font-weight-bold);
}

/* --- Address step --- */
.m-checkout__addresses {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.m-checkout__address {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px;
  border-radius: 12px;
  background: #ffffff;
  color: #1a1a1a;
  font-size: 14px;
  line-height: 20px;
}

.m-checkout__address input {
  margin: 2px 0 0;
  accent-color: #1a1a1a;
}

.m-checkout__unsupported {
  color: #e1251b;
  font-style: normal;
}

.m-checkout__toggle {
  margin-top: 12px;
  padding: 10px 14px;
  border: 1px solid #d5d7db;
  border-radius: 8px;
  background: #ffffff;
  color: #1a1a1a;
  font: inherit;
  font-size: 14px;
  cursor: pointer;
}

.m-checkout__form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 12px;
  padding: 16px;
  border-radius: 12px;
  background: #ffffff;
}

.m-checkout__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: #73757d;
  font-size: 13px;
}

.m-checkout__field input {
  min-height: 44px;
  padding: 0 12px;
  border: 1px solid #d5d7db;
  border-radius: 8px;
  font: inherit;
  font-size: 15px;
}

/* --- Payment step cards --- */
.m-checkout__card {
  position: relative;
  margin: 12px 16px 0;
  padding: 16px;
  border-radius: 12px;
  background: #ffffff;
}

.m-checkout__addr-name {
  margin: 0;
  color: #1a1a1a;
  font-size: 15px;
  font-weight: var(--font-weight-bold);
}

.m-checkout__addr-text {
  margin: 6px 0 0;
  color: #73757d;
  font-size: 14px;
  line-height: 20px;
}

.m-checkout__change {
  position: absolute;
  top: 50%;
  right: 12px;
  width: 40px;
  height: 40px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: #73757d;
  font-size: 20px;
  cursor: pointer;
}

/* Item rows: 48px image box + title × qty + line price. */
.m-checkout__items {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.m-checkout__item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.m-checkout__item-imgbox {
  display: inline-flex;
  width: 48px;
  height: 48px;
  flex-shrink: 0;
  overflow: hidden;
  border-radius: 8px;
  background: #f5f6fa;
}

.m-checkout__item-imgbox img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.m-checkout__item-title {
  flex: 1 1 auto;
  min-width: 0;
  color: #1a1a1a;
  font-size: 14px;
  line-height: 20px;
  word-break: break-word;
}

.m-checkout__item-price {
  flex-shrink: 0;
  color: #1a1a1a;
  font-size: 14px;
  font-weight: var(--font-weight-semibold);
}

.m-checkout__methods {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  list-style: none;
}

.m-checkout__method {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  color: #1a1a1a;
  font-size: 14px;
}

.m-checkout__method input {
  accent-color: #1a1a1a;
}

.m-checkout__method-label {
  font-weight: var(--font-weight-semibold);
}

.m-checkout__method-note {
  color: #888b94;
  font-size: 12px;
}

.m-checkout__totals {
  margin: 0;
}

.m-checkout__totals > div {
  display: flex;
  justify-content: space-between;
  padding-block: 4px;
  color: #55565b;
  font-size: 14px;
}

.m-checkout__totals-total {
  border-top: 1px solid #f0f1f2;
  color: #1a1a1a;
  font-weight: var(--font-weight-bold);
}

.m-checkout__totals dd {
  margin: 0;
}

.m-checkout__notice {
  margin: 10px 0 0;
  color: #888b94;
  font-size: 12px;
  line-height: 16px;
}

/* --- Fixed bottom bar (docs/20 §0: 56px + safe area, button 48px) --- */
.m-checkout__bar {
  position: fixed;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  gap: 12px;
  height: calc(56px + env(safe-area-inset-bottom));
  padding: 0 16px env(safe-area-inset-bottom);
  border-top: 1px solid #f0f1f2;
  background: #ffffff;
}

.m-checkout__bar-total {
  color: #e1251b;
  font-size: 18px;
  font-weight: var(--font-weight-bold);
}

.m-checkout__pay {
  flex: 1;
  min-width: 0;
  height: 48px;
  border: 0;
  border-radius: 24px;
  background: #e1251b;
  color: #ffffff;
  font: inherit;
  font-size: 16px;
  font-weight: var(--font-weight-bold);
  cursor: pointer;
}

.m-checkout__pay:hover:not(:disabled) {
  background: #d14335;
}

.m-checkout__pay:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
