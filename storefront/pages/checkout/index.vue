<script setup>
import { computed, ref } from 'vue'
import { navigateTo, useHead } from '#imports'

import { useBuyerAuth } from '../../composables/useBuyerAuth'
import { useCheckout } from '../../composables/useCheckout'
import { useLocale } from '../../composables/useLocale'
import { formatDisplayPrice } from '../../utils/display'

// Checkout aligned to docs/12 §7/§8: step 1 = 3-field address form
// (Full name / Address / Phone, Save jumps straight to payment), step 2 =
// payment page (balance method first, retained card/GPay/Klarna options,
// reduced Summary without discount lines). Wallet deduction lands with the
// phase-3 backend; Pay now places the pending order as before.
const { addressList, createAddress, getQuote, placeOrder } = await useCheckout()
const { account } = useBuyerAuth()
const { t } = useLocale()

const step = ref('address') // address | payment
const selectedAddressId = ref('')
const showNewForm = ref(!addressList.value?.length)
const quote = ref(null)
const error = ref('')
const submitting = ref(false)
const paymentMethod = ref('balance')

const selectedAddress = computed(
  () => addressList.value?.find((a) => a.public_id === selectedAddressId.value) || null,
)

const newAddress = ref({ full_name: '', line1: '', phone: '' })

async function saveAddress() {
  error.value = ''
  const payload = {
    ...newAddress.value,
    // The backend still validates city/postcode for the GB service range;
    // the 3-field target form auto-fills demo defaults until phase 3.
    city: newAddress.value.city || 'London',
    postcode: newAddress.value.postcode || 'SW1A 1AA',
  }
  const response = await createAddress(payload)
  if (response?.error) {
    error.value = response.error.message || 'Could not save the address.'
    return
  }
  showNewForm.value = false
  selectedAddressId.value = response.public_id
  newAddress.value = { full_name: '', line1: '', phone: '' }
  await enterPayment()
}

async function useSelectedAddress() {
  error.value = ''
  if (!selectedAddressId.value) return
  await enterPayment()
}

async function enterPayment() {
  const response = await getQuote(selectedAddressId.value)
  if (response?.error) {
    error.value = response.error.message || 'Could not build the quote.'
    return
  }
  quote.value = response
  step.value = 'payment'
}

async function payNow() {
  submitting.value = true
  error.value = ''
  const response = await placeOrder(selectedAddressId.value)
  submitting.value = false
  if (response?.error) {
    error.value = response.error.message || 'Could not place the order.'
    return
  }
  navigateTo('/account/orders')
}

function formatMoney(value) {
  if (!value) return '—'
  return formatDisplayPrice(value) ?? '—'
}

const balanceDisplay = computed(() => {
  // Wallet balances arrive with the phase-3 backend; show the placeholder.
  return account.value?.wallet_balance != null
    ? formatDisplayPrice(account.value.wallet_balance)
    : null
})

const paymentMethods = computed(() => [
  {
    value: 'balance',
    label: t('checkout.balancePay'),
    note: balanceDisplay.value ? `Balance: ${balanceDisplay.value}` : '',
  },
  { value: 'card', label: 'Credit/Debit Card', note: '' },
  { value: 'google_pay', label: 'Google Pay', note: '' },
  { value: 'klarna', label: 'Klarna', note: '' },
])

useHead({ title: 'Checkout' })
</script>

<template>
  <AppContainer>
    <section class="checkout" aria-labelledby="checkout-title">
      <h1 id="checkout-title" class="visually-hidden">Checkout</h1>

      <div v-if="error" class="checkout__error" role="alert">{{ error }}</div>

      <!-- Step 1: delivery address (docs/12 §7, 3-field form). -->
      <section v-if="step === 'address'" class="checkout__step" aria-labelledby="address-heading">
        <h2 id="address-heading">Delivery to</h2>
        <ul v-if="addressList.length > 0" class="address-list">
          <li v-for="address in addressList" :key="address.public_id">
            <label class="address-option">
              <input
                v-model="selectedAddressId"
                type="radio"
                name="address"
                :value="address.public_id"
              />
              <span>
                {{ address.full_name }}, {{ address.line1 }}, {{ address.city }}
                {{ address.postcode }}
                <em v-if="!address.is_serviceable" class="address-unsupported">
                  — not serviceable
                </em>
              </span>
            </label>
          </li>
        </ul>

        <button type="button" class="checkout__secondary" @click="showNewForm = !showNewForm">
          {{ showNewForm ? 'Cancel' : 'Add a new address' }}
        </button>

        <form v-if="showNewForm" class="address-form" @submit.prevent="saveAddress">
          <label class="address-form__field">
            <span>Full name*</span>
            <input v-model="newAddress.full_name" placeholder="First name and surname" required />
          </label>
          <label class="address-form__field">
            <span>Address</span>
            <input v-model="newAddress.line1" placeholder="Address" required />
          </label>
          <label class="address-form__field">
            <span>Phone number*</span>
            <input v-model="newAddress.phone" placeholder="Phone number" required />
          </label>
          <button class="address-form__save" type="submit">Save</button>
        </form>

        <button
          v-else-if="selectedAddressId"
          class="checkout__continue"
          type="button"
          @click="useSelectedAddress"
        >
          Save
        </button>
      </section>

      <!-- Step 2: payment page (docs/12 §8). -->
      <section v-else class="checkout__payment" aria-labelledby="payment-heading">
        <h2 id="payment-heading" class="visually-hidden">Payment</h2>
        <div class="checkout__columns">
          <div class="checkout__left">
            <div class="pay-card pay-card--address">
              <h3>Delivery to</h3>
              <p class="pay-card__name">{{ selectedAddress?.full_name }}</p>
              <p class="pay-card__text">
                {{
                  [selectedAddress?.line1, selectedAddress?.city, selectedAddress?.postcode]
                    .filter(Boolean)
                    .join(', ')
                }}
              </p>
              <button class="pay-card__change" type="button" @click="step = 'address'">›</button>
            </div>

            <div class="pay-card">
              <h3>Items</h3>
              <ul class="quote-items">
                <li v-for="item in quote?.items || []" :key="item.offer_public_id">
                  <span>{{ item.title }} × {{ item.quantity }}</span>
                  <span>{{ formatMoney(Number(item.price) * item.quantity) }}</span>
                </li>
              </ul>
            </div>

            <div class="pay-card">
              <h3>Payment method</h3>
              <ul class="pay-methods">
                <li v-for="method in paymentMethods" :key="method.value">
                  <label class="pay-methods__option">
                    <input
                      v-model="paymentMethod"
                      type="radio"
                      name="payment"
                      :value="method.value"
                    />
                    <span class="pay-methods__label">{{ method.label }}</span>
                    <span v-if="method.note" class="pay-methods__note">{{ method.note }}</span>
                  </label>
                </li>
              </ul>
            </div>
          </div>

          <aside class="checkout__summary">
            <h3>Summary</h3>
            <dl class="quote-totals">
              <div>
                <dt>Subtotal</dt>
                <dd>{{ formatMoney(quote?.subtotal) }}</dd>
              </div>
              <div>
                <dt>Delivery fee</dt>
                <dd>
                  {{
                    quote?.shipping_method === 'FREE' ? 'Free' : formatMoney(quote?.shipping_cost)
                  }}
                </dd>
              </div>
              <div class="quote-totals__total">
                <dt>Order Total (VAT included)</dt>
                <dd>{{ formatMoney(quote?.total) }}</dd>
              </div>
            </dl>
            <button class="pay-now" type="button" :disabled="submitting || !quote" @click="payNow">
              {{ submitting ? 'Paying…' : 'Pay now' }}
            </button>
            <p class="checkout__notice">
              By placing your order you agree to Joybuy's terms. The balance method deducts the
              wallet balance once the wallet backend is enabled.
            </p>
          </aside>
        </div>
      </section>
    </section>
  </AppContainer>
</template>

<style scoped>
.checkout {
  margin-block: var(--space-6);
}

.checkout__step h2,
.pay-card h3,
.checkout__summary h3 {
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
}

.checkout__error {
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  background: var(--colour-error-soft);
  color: var(--colour-error);
  font-size: var(--font-size-sm);
}

.address-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-block: var(--space-3);
}

.address-option {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-height: 44px;
}

.address-unsupported {
  color: var(--colour-error);
}

/* 3-field address form (docs/12 §7): two-column grid, black Save bottom-right. */
.address-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3) var(--space-4);
  max-width: 46rem;
  margin-top: var(--space-4);
  padding: var(--space-4);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  box-shadow: rgb(0 0 0 / 4%) 0 2px 12px 0;
}

.address-form__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  font-size: var(--font-size-sm);
  color: var(--colour-text-secondary);
}

.address-form__field input {
  min-height: 44px;
  padding: 0 var(--space-3);
  border: 1px solid var(--colour-border);
  border-radius: 4px;
  font: inherit;
}

.address-form__save {
  grid-column: 2;
  justify-self: end;
  min-width: 88px;
  min-height: 40px;
  border: 0;
  border-radius: 4px;
  background: var(--colour-text);
  color: var(--colour-white);
  cursor: pointer;
  font: inherit;
  font-weight: var(--font-weight-semibold);
}

.checkout__secondary,
.checkout__continue {
  min-height: 44px;
  margin-top: var(--space-3);
  padding: 0 var(--space-4);
  border: 1px solid var(--colour-border-strong);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  cursor: pointer;
}

.checkout__continue {
  min-width: 88px;
  border: 0;
  border-radius: 4px;
  background: var(--colour-text);
  color: var(--colour-white);
}

/* Payment page: 62/33 columns, white cards on the soft canvas. */
.checkout__payment {
  margin-top: var(--space-4);
}

.checkout__columns {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 400px;
  gap: 24px;
  align-items: start;
}

.checkout__left {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.pay-card {
  position: relative;
  padding: var(--space-4);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  box-shadow: rgb(0 0 0 / 4%) 0 2px 12px 0;
}

.pay-card__name {
  margin: 0;
  font-weight: var(--font-weight-bold);
}

.pay-card__text {
  margin: var(--space-1) 0 0;
  color: var(--colour-text-secondary);
}

.pay-card__change {
  position: absolute;
  top: 50%;
  right: var(--space-4);
  width: 40px;
  height: 40px;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--colour-text-secondary);
  font-size: 1.25rem;
  cursor: pointer;
}

.pay-card__change:hover {
  background: var(--colour-hover);
}

.quote-items {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.quote-items li {
  display: flex;
  justify-content: space-between;
  gap: var(--space-4);
}

.pay-methods {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  list-style: none;
}

.pay-methods__option {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-height: 56px;
  cursor: pointer;
}

.pay-methods__label {
  font-weight: var(--font-weight-semibold);
}

.pay-methods__note {
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}

.checkout__summary {
  padding: var(--space-4);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  box-shadow: rgb(0 0 0 / 4%) 0 2px 12px 0;
}

.quote-totals {
  margin-block: var(--space-3);
}

.quote-totals > div {
  display: flex;
  justify-content: space-between;
  padding-block: var(--space-1);
}

.quote-totals__total {
  border-top: 1px solid var(--colour-border);
  font-weight: var(--font-weight-bold);
}

/* Pay now: full-width red button, 48px, radius 8 (docs/12 §8). */
.pay-now {
  width: 100%;
  min-height: 48px;
  border: 0;
  border-radius: 8px;
  background: #e1251b;
  color: var(--colour-white);
  font-size: 1.125rem;
  font-weight: var(--font-weight-bold);
  cursor: pointer;
}

.pay-now:hover:not(:disabled) {
  background: #d14335;
}

.pay-now:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.checkout__notice {
  margin-top: var(--space-3);
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}

@media (max-width: 64rem) {
  .checkout__columns {
    grid-template-columns: 1fr;
  }
}
</style>
