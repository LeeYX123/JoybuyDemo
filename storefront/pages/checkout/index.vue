<script setup>
import { computed, ref } from 'vue'
import { navigateTo, useHead, useRoute } from '#imports'

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

// 立即购买（2026-11-28）：PDP 带 ?offer=<offer_public_id>&qty=<n> 进来的
// 独立直购上下文——quote 与下单两步都透传给后端（不读写购物车），页面
// 顶部提示「正在单独购买该商品」；无 offer 参数时保持原购物车结账路径。
const route = useRoute()
const directPurchase = computed(() => {
  const offerPublicId = String(route.query.offer || '').trim()
  if (!offerPublicId) return null
  const parsedQty = Number(route.query.qty)
  const quantity = Number.isInteger(parsedQty) && parsedQty >= 1 && parsedQty <= 99 ? parsedQty : 1
  return { offerPublicId, quantity }
})

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
  const response = await getQuote(selectedAddressId.value, directPurchase.value)
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
  const response = await placeOrder(
    selectedAddressId.value,
    paymentMethod.value.toUpperCase(),
    directPurchase.value,
  )
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

      <!-- Step 1: delivery address（2026-11-28 二次改版：字段口径不变——
           选择已有地址下拉 / 无地址·县·城市栏 / 电话无前缀 / 仅必填非空；
           版式 1:1 对齐真站 checkout 灰底白卡 + 两列 40px 输入框 + 全宽红 Save）。 -->
      <section v-if="step === 'address'" class="checkout__step" aria-labelledby="address-heading">
        <div class="checkout__card">
          <div v-if="!selectedAddressId" class="checkout__warning" role="status">
            <svg class="checkout__warning-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
              <circle cx="8" cy="8" r="7" fill="#F9B22A" />
              <rect x="7.25" y="4" width="1.5" height="5.4" rx="0.75" fill="#fff" />
              <circle cx="8" cy="11.4" r="0.9" fill="#fff" />
            </svg>
            {{ t('checkout.noticeRequired') }}
          </div>
          <h2 id="address-heading">{{ t('checkout.addAddress') }}</h2>

          <form class="address-form" novalidate @submit.prevent="saveAddress">
            <!-- 原【国家/地区】位：选择已有地址，选中即回填并直接进入支付页。 -->
            <label class="address-form__field address-form__field--left">
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

            <label class="address-form__field address-form__field--left">
              <span>{{ t('checkout.fullName') }}</span>
              <input
                v-model="newAddress.full_name"
                type="text"
                :placeholder="t('checkout.fullNamePlaceholder')"
              />
            </label>

            <label class="address-form__field address-form__field--right">
              <span>{{ t('checkout.phone') }}</span>
              <!-- 去掉 GB(+44) 前缀选择：纯输入框，任意内容。 -->
              <input
                v-model="newAddress.phone"
                type="tel"
                :placeholder="t('checkout.phonePlaceholder')"
              />
            </label>

            <label class="address-form__field address-form__field--left">
              <span>{{ t('checkout.postcode') }}</span>
              <input
                v-model="newAddress.postcode"
                type="text"
                :placeholder="t('checkout.postcodePlaceholder')"
              />
            </label>

            <label class="address-form__field address-form__field--left">
              <span>{{ t('checkout.addressLine2') }}</span>
              <input
                v-model="newAddress.line2"
                type="text"
                :placeholder="t('checkout.addressLine2Placeholder')"
              />
            </label>

            <label class="address-form__field address-form__field--right">
              <span>{{ t('checkout.houseNumber') }}</span>
              <input v-model="newAddress.house_number" type="text" />
            </label>

            <label class="address-form__switch address-form__field--left">
              <input v-model="newAddress.is_default" type="checkbox" />
              <span>{{ t('checkout.setDefault') }}</span>
            </label>

            <button class="address-form__save" type="submit">{{ t('checkout.save') }}</button>
          </form>
        </div>
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

/* 结算地址卡（2026-11-28 二次改版，1:1 对齐真站 checkout）：
   灰底画布 + 白卡 + 浅黄提示条 + 两列 40px 输入框 + 全宽红 Save。 */
.checkout__step {
  padding: 24px;
  border-radius: 8px;
  background: #f7f8fa;
}

.checkout__card {
  padding: 24px 32px 32px;
  border-radius: 8px;
  background: var(--colour-surface);
}

.checkout__warning {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  padding: 10px 16px;
  border-radius: 8px;
  background: #fef6e8;
  color: #1a1a1a;
  font-size: 13px;
}

.checkout__warning-icon {
  flex: none;
}

.checkout__step .checkout__card h2 {
  margin: 0 0 20px;
  font-size: 18px;
  font-weight: var(--font-weight-bold);
  color: #1a1a1a;
}

/* 真站实测（viewport 1424）：输入框固定 390px，左列 x=64 / 右列 x=709
   → 列间距 255px；Save 412px 与左列同起点。卡片通栏（内容宽）。 */
.address-form {
  display: grid;
  grid-template-columns: 390px 390px;
  column-gap: 255px;
  row-gap: 20px;
}

.address-form__field--left {
  grid-column: 1;
}

.address-form__field--right {
  grid-column: 2;
}

.address-form__field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.address-form__field > span {
  font-size: 13px;
  font-weight: var(--font-weight-semibold);
  color: #1a1a1a;
}

.address-form__field input,
.address-form__field select {
  height: 40px;
  padding: 0 12px;
  border: 1px solid #ccced2;
  border-radius: 4px;
  font: inherit;
  font-size: 14px;
  background: var(--colour-surface);
  color: #1a1a1a;
}

.address-form__field input::placeholder {
  color: #a8aab4;
}

.address-form__field input:focus,
.address-form__field select:focus {
  border-color: #1a1a1a;
  outline: none;
}

.address-form__switch {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
  font-size: 13px;
  color: #1a1a1a;
}

/* Save 412px（真站实测），与左列同起点左对齐。 */
.address-form__save {
  grid-column: 1;
  width: 412px;
  height: 40px;
  border: 0;
  border-radius: 4px;
  background: #cc0c1c;
  color: var(--colour-white);
  cursor: pointer;
  font: inherit;
  font-size: 14px;
  font-weight: var(--font-weight-bold);
}

.address-form__save:hover {
  background: #b50b19;
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
