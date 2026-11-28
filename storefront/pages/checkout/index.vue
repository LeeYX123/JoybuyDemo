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

// 2026-11-28 地址表单改版（用户拍板）：国家/地区改为【选择已有地址】下拉——
// 选中即回填下方输入框并直接进入支付页；【地址】【县】【城镇/城市】栏删除；
// 电话号码去掉 GB(+44) 前缀、纯输入框；所有输入框不做格式校验、仅必填非空。
// line1 由【门牌号 + 地址行 2】组合（后端 line1 已改为可选），城市兜底 London。
const newAddress = ref({
  full_name: '',
  phone: '',
  postcode: '',
  line1: '',
  line2: '',
  house_number: '',
  is_default: false,
})

// 「选择已有地址」下拉：选中已有地址 → 回填表单 → 直接进入支付页。
const pickExistingId = ref('')
const pickExistingPlaceholder = computed(() =>
  addressList.value?.length ? t('checkout.pickExisting') : t('checkout.pickExistingEmpty'),
)

function onPickExisting() {
  error.value = ''
  const address = addressList.value?.find((a) => a.public_id === pickExistingId.value)
  if (!address) return
  newAddress.value = {
    full_name: address.full_name || '',
    phone: address.phone || '',
    postcode: address.postcode || '',
    line1: address.line1 || '',
    line2: address.line2 || '',
    house_number: address.house_number || '',
    is_default: Boolean(address.is_default),
  }
  selectedAddressId.value = address.public_id
  enterPayment()
}

async function saveAddress() {
  error.value = ''
  // 仅非空校验（不做任何格式校验）；移动端表单仍是 3 字段（无邮编输入框），
  // 邮编必填只在桌面端生效。line1 由门牌号 + 地址行 2 组合，两者都空时回退
  // line1 本身（移动端表单直接编辑 line1，保持兼容）。
  const postcodeValue = (newAddress.value.postcode || '').trim()
  if (
    !newAddress.value.full_name.trim() ||
    !newAddress.value.phone.trim() ||
    (!isMobileHost.value && !postcodeValue)
  ) {
    error.value = t('checkout.errorRequiredFields')
    return
  }
  const composed = [newAddress.value.house_number, newAddress.value.line2]
    .map((v) => (v || '').trim())
    .filter(Boolean)
    .join(' ')
  const payload = {
    ...newAddress.value,
    line1: composed || newAddress.value.line1 || '',
    // 后端仍要求 city 非空（配送范围 GB）；城市栏已删，兜底默认值。
    city: 'London',
    postcode: postcodeValue || 'SW1A 1AA',
  }
  const response = await createAddress(payload)
  if (response?.error) {
    error.value = response.error.message || 'Could not save the address.'
    return
  }
  showNewForm.value = false
  selectedAddressId.value = response.public_id
  newAddress.value = {
    full_name: '',
    phone: '',
    postcode: '',
    line1: '',
    line2: '',
    house_number: '',
    is_default: false,
  }
  pickExistingId.value = ''
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
  // WP-42（文档 M01 §1）：演示性质支付——选择任一支付方式点【下单】即支付成功。
  const response = await placeOrder(selectedAddressId.value, paymentMethod.value.toUpperCase())
  submitting.value = false
  if (response?.error) {
    const code = response.error?.code || ''
    if (code === 'NOT_WHITELISTED') {
      error.value = t('gate.messageWhitelist')
    } else if (code === 'PAYMENT_DISABLED') {
      // 管理端编辑关闭支付权限（2026-11-27）：与白名单拦截同样走本地化文案。
      error.value = t('gate.messagePaymentDisabled')
    } else {
      error.value = response.error.message || 'Could not place the order.'
    }
    return
  }
  navigateTo('/account/orders')
}

function formatMoney(value) {
  if (!value) return '—'
  return formatDisplayPrice(value) ?? '—'
}

const balanceDisplay = computed(() => {
  // 迭代02：余额支付真扣 BuyerAccount.balance，登录后展示真实余额。
  return account.value?.balance != null ? formatDisplayPrice(account.value.balance) : null
})

// ADR 0001: on the m. host the same checkout state renders the mobile
// checkout (docs/20 §4); the desktop template below is untouched. Quote
// money is pre-formatted here so the mobile component stays presentational.
const { isMobileHost } = useMobileView()

const mobileQuoteItems = computed(() =>
  (quote.value?.items || []).map((item) => ({
    offer_public_id: item.offer_public_id,
    title: item.title,
    quantity: item.quantity,
    line: formatMoney(Number(item.price) * item.quantity) ?? '—',
    image: '',
  })),
)
const mobileSubtotalText = computed(() => formatMoney(quote.value?.subtotal) ?? '—')
const mobileShippingText = computed(() =>
  quote.value?.shipping_method === 'FREE'
    ? t('checkout.free')
    : (formatMoney(quote.value?.shipping_cost) ?? '—'),
)
const mobileTotalText = computed(() => formatMoney(quote.value?.total) ?? '—')

function updateAddressField(field, value) {
  newAddress.value[field] = value
}

// Bottom-bar Save: new form open -> create the address; otherwise continue
// with the selected one (same branch as the desktop buttons).
function mobileSaveAddress() {
  if (showNewForm.value) saveAddress()
  else useSelectedAddress()
}
const paymentMethods = computed(() => [
  {
    value: 'balance',
    label: t('checkout.balancePay'),
    note: balanceDisplay.value ? `Balance: ${balanceDisplay.value}` : '',
  },
  { value: 'card', label: t('checkout.card'), note: '' },
  { value: 'google_pay', label: 'Google Pay', note: '' },
  { value: 'apple_pay', label: 'Apple Pay', note: '' },
  { value: 'wechat_pay', label: t('checkout.wechatPay'), note: '' },
  { value: 'klarna', label: t('checkout.klarna'), note: '' },
])

useHead({ title: 'Checkout' })
</script>

<template>
  <!-- ADR 0001: mobile host renders the docs/20 §4 mobile checkout. -->
  <MobileCheckout
    v-if="isMobileHost"
    :step="step"
    :address-list="addressList"
    :show-new-form="showNewForm"
    :selected-address-id="selectedAddressId"
    :new-address="newAddress"
    :error="error"
    :submitting="submitting"
    :payment-method="paymentMethod"
    :payment-methods="paymentMethods"
    :selected-address="selectedAddress"
    :quote-items="mobileQuoteItems"
    :subtotal-text="mobileSubtotalText"
    :shipping-text="mobileShippingText"
    :total-text="mobileTotalText"
    @select-address="selectedAddressId = $event"
    @toggle-new-form="showNewForm = !showNewForm"
    @update-address-field="updateAddressField"
    @save-address="mobileSaveAddress"
    @change-step="step = $event"
    @select-payment="paymentMethod = $event"
    @pay-now="payNow"
    @back="navigateTo('/cart')"
  />
  <AppContainer v-else>
    <section class="checkout" aria-labelledby="checkout-title">
      <h1 id="checkout-title" class="visually-hidden">{{ t('checkout.title') }}</h1>

      <div v-if="error" class="checkout__error" role="alert">{{ error }}</div>

      <!-- Step 1: delivery address (2026-11-28 改版：选择已有地址 + 精简表单，
           无格式校验、仅必填非空；字段变更记录见脚本区注释）。 -->
      <section v-if="step === 'address'" class="checkout__step" aria-labelledby="address-heading">
        <div v-if="!selectedAddressId" class="checkout__warning" role="status">
          {{ t('checkout.noticeRequired') }}
        </div>
        <h2 id="address-heading">{{ t('checkout.addAddress') }}</h2>

        <form class="address-form" novalidate @submit.prevent="saveAddress">
          <!-- 国家/地区改为选择已有地址：选中即回填表单并直接进入支付页。 -->
          <label class="address-form__field">
            <span>{{ t('checkout.pickExisting') }}</span>
            <select v-model="pickExistingId" @change="onPickExisting">
              <option value="">{{ pickExistingPlaceholder }}</option>
              <option
                v-for="address in addressList"
                :key="address.public_id"
                :value="address.public_id"
              >
                {{ address.full_name }}，{{ address.line1 }} {{ address.postcode }}
              </option>
            </select>
          </label>

          <label class="address-form__field">
            <span>{{ t('checkout.fullName') }}</span>
            <input
              v-model="newAddress.full_name"
              type="text"
              :placeholder="t('checkout.fullNamePlaceholder')"
            />
          </label>

          <label class="address-form__field">
            <span>{{ t('checkout.phone') }}</span>
            <!-- 去掉 GB(+44) 前缀选择：纯输入框，任意内容。 -->
            <input v-model="newAddress.phone" type="tel" :placeholder="t('checkout.phonePlaceholder')" />
          </label>

          <label class="address-form__field">
            <span>{{ t('checkout.postcode') }}</span>
            <input
              v-model="newAddress.postcode"
              type="text"
              :placeholder="t('checkout.postcodePlaceholder')"
            />
          </label>

          <label class="address-form__field">
            <span>{{ t('checkout.addressLine2') }}</span>
            <input v-model="newAddress.line2" type="text" />
          </label>

          <label class="address-form__field">
            <span>{{ t('checkout.houseNumber') }}</span>
            <input v-model="newAddress.house_number" type="text" />
          </label>

          <label class="address-form__switch">
            <input v-model="newAddress.is_default" type="checkbox" />
            <span>{{ t('checkout.setDefault') }}</span>
          </label>

          <button class="address-form__save" type="submit">{{ t('checkout.save') }}</button>
        </form>
      </section>

      <!-- Step 2: payment page (docs/12 §8). -->
      <section v-else class="checkout__payment" aria-labelledby="payment-heading">
        <h2 id="payment-heading" class="visually-hidden">{{ t('checkout.payment') }}</h2>
        <div class="checkout__columns">
          <div class="checkout__left">
            <div class="pay-card pay-card--address">
              <h3>{{ t('checkout.deliveryTo') }}</h3>
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
              <h3>{{ t('checkout.items') }}</h3>
              <ul class="quote-items">
                <li v-for="item in quote?.items || []" :key="item.offer_public_id">
                  <span>{{ item.title }} × {{ item.quantity }}</span>
                  <span>{{ formatMoney(Number(item.price) * item.quantity) }}</span>
                </li>
              </ul>
            </div>

            <div class="pay-card">
              <h3>{{ t('checkout.paymentMethod') }}</h3>
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
            <h3>{{ t('checkout.summary') }}</h3>
            <dl class="quote-totals">
              <div>
                <dt>{{ t('checkout.subtotal') }}</dt>
                <dd>{{ formatMoney(quote?.subtotal) }}</dd>
              </div>
              <div>
                <dt>{{ t('checkout.deliveryFee') }}</dt>
                <dd>
                  {{
                    quote?.shipping_method === 'FREE'
                      ? t('checkout.free')
                      : formatMoney(quote?.shipping_cost)
                  }}
                </dd>
              </div>
              <div class="quote-totals__total">
                <dt>{{ t('checkout.orderTotal') }}</dt>
                <dd>{{ formatMoney(quote?.total) }}</dd>
              </div>
            </dl>
            <button class="pay-now" type="button" :disabled="submitting || !quote" @click="payNow">
              {{ submitting ? t('checkout.paying') : t('checkout.payNow') }}
            </button>
            <p class="checkout__notice">
              {{ t('checkout.termsNotice') }}
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

/* 请输入您的收货地址提示条（真站截图同款浅黄底）。 */
.checkout__warning {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  background: #fff8e1;
  color: #8a6d1a;
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

.address-form__field input,
.address-form__field select {
  min-height: 44px;
  padding: 0 var(--space-3);
  border: 1px solid var(--colour-border);
  border-radius: 4px;
  font: inherit;
  background: var(--colour-surface);
  color: var(--colour-text);
}

/* 选择已有地址下拉（原国家/地区位）：占位/选项文字颜色与输入框一致。 */
.address-form__field select {
  appearance: auto;
}

.address-form__switch {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-sm);
  color: var(--colour-text-secondary);
}

/* 保存按钮红色主按钮（真站截图同款）。 */
.address-form__save {
  grid-column: 2;
  justify-self: end;
  min-width: 88px;
  min-height: 40px;
  border: 0;
  border-radius: 4px;
  background: #cc0c1c;
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
