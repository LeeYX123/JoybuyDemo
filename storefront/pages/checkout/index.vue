<script setup>
import { computed, ref, watch } from 'vue'
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
// 选中即回填下方输入框并直接进入支付页；【地址】查找框（真站 Address*）删除，
// 但 Address Line 1*（必填，门牌号/楼栋/街道）保留——用户澄清纠正；
// 电话号码去掉 GB(+44) 前缀、纯输入框；仅必填非空，无格式校验。城市兜底 London。
const newAddress = ref({
  full_name: '',
  phone: '',
  postcode: '',
  line1: '',
  line2: '',
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
    is_default: Boolean(address.is_default),
  }
  selectedAddressId.value = address.public_id
  enterPayment()
}

async function saveAddress() {
  error.value = ''
  // 仅非空校验（不做任何格式校验）；移动端表单仍是 3 字段（无邮编/行1 之外的输入），
  // 邮编必填只在桌面端生效；Address Line 1* 桌面端必填（用户澄清恢复）。
  const postcodeValue = (newAddress.value.postcode || '').trim()
  if (
    !newAddress.value.full_name.trim() ||
    !newAddress.value.phone.trim() ||
    (!isMobileHost.value &&
      (!postcodeValue || !newAddress.value.line1.trim()))
  ) {
    error.value = t('checkout.errorRequiredFields')
    return
  }
  const payload = {
    ...newAddress.value,
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
    image: metaFor(item)?.image || '',
  })),
)

// 展示层增强（2026-11-28）：支付页商品行带缩略图 + 规格——复用购物车同款
// 模式：只读 GET /api/v1/products/:id，以 offer_public_id 对上行取规格。
const productMeta = ref({}) // spu_public_id -> { image, specByOffer: { offerId: spec } }

watch(
  () => quote.value?.items,
  async (items) => {
    if (!Array.isArray(items) || !items.length) return
    const spuIds = [...new Set(items.map((item) => item.spu_public_id).filter(Boolean))]
    await Promise.all(
      spuIds.map(async (spuId) => {
        if (productMeta.value[spuId]) return
        try {
          const detail = await $fetch(`/api/v1/products/${spuId}`)
          if (!detail) return
          const specByOffer = {}
          for (const sku of Array.isArray(detail.skus) ? detail.skus : []) {
            if (sku?.offer?.public_id) specByOffer[sku.offer.public_id] = sku.specification || ''
          }
          productMeta.value = {
            ...productMeta.value,
            [spuId]: { image: detail.gallery?.[0]?.url || '', specByOffer },
          }
        } catch {
          // 展示层增强失败不阻塞结算主流程
        }
      }),
    )
  },
  { immediate: true },
)

function metaFor(item) {
  return productMeta.value[item.spu_public_id] || null
}

function specFor(item) {
  const raw = metaFor(item)?.specByOffer?.[item.offer_public_id]
  if (!raw) return ''
  let parsed = raw
  if (typeof parsed === 'string') {
    try {
      parsed = JSON.parse(parsed)
    } catch {
      return parsed
    }
  }
  if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
    return Object.values(parsed)
      .map((value) => String(value).trim())
      .filter(Boolean)
      .join(' / ')
  }
  return String(parsed)
}
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
// 2026-11-28 二次改版：去掉微信支付；Google Pay / Apple Pay 左侧带 icon；
// 银行卡品牌组单独渲染（见模板，8 品牌）。
// 2026-11-28 行列表最终口径（用户拍板）：只保留 余额支付/Google Pay/
// PayPal/Klarna，icon 为官方 logo（Wikimedia Commons 下载）。
const paymentMethods = computed(() => [
  {
    value: 'balance',
    label: t('checkout.balancePay'),
    note: balanceDisplay.value ? `Balance: ${balanceDisplay.value}` : '',
  },
  { value: 'google_pay', label: 'Google Pay', icon: '/images/pdp-services/payment-google-pay.svg' },
  { value: 'paypal', label: 'PayPal', icon: '/images/pdp-services/payment-paypal.svg' },
  { value: 'klarna', label: t('checkout.klarna'), icon: '/images/pdp-services/payment-klarna.svg' },
])

// 2026-11-28 支付页改版：银行卡下按品牌直记支付方式，选中哪个品牌图标，
// 订单就记哪个支付方式，管理端可见。白名单演示口径：任选即支付成功。
// 2026-11-28 按真站 checkout 实拍核对（WorkBuddy 浏览器）：银行卡 8 品牌
// = Visa/Mastercard/Maestro/AmEx/Diners/Discover/JCB/银联（第 8 个是银联，
// 用户已核对），全部使用真站提取的 SVG，不再自行新增品牌。
const cardBrands = [
  { value: 'VISA', icon: '/images/pdp-services/payment-visa.svg', label: 'Visa' },
  { value: 'MASTERCARD', icon: '/images/pdp-services/payment-mastercard.svg', label: 'Mastercard' },
  { value: 'MAESTRO', icon: '/images/pdp-services/payment-maestro.svg', label: 'Maestro' },
  { value: 'AMEX', icon: '/images/pdp-services/payment-american-express.svg', label: 'American Express' },
  { value: 'DINERS', icon: '/images/pdp-services/payment-dinersclub.svg', label: 'Diners Club' },
  { value: 'DISCOVER', icon: '/images/pdp-services/payment-discover.svg', label: 'Discover' },
  { value: 'JCB', icon: '/images/pdp-services/payment-jcb.svg', label: 'JCB' },
  { value: 'UNIONPAY', icon: '/images/pdp-services/payment-unionpay.svg', label: '银联' },
]

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
              <span>{{ t('checkout.addressLine1') }}</span>
              <input
                v-model="newAddress.line1"
                type="text"
                :placeholder="t('checkout.addressLine1Placeholder')"
              />
            </label>

            <label class="address-form__field address-form__field--right">
              <span>{{ t('checkout.addressLine2') }}</span>
              <input
                v-model="newAddress.line2"
                type="text"
                :placeholder="t('checkout.addressLine2Placeholder')"
              />
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
                <li
                  v-for="item in quote?.items || []"
                  :key="item.offer_public_id"
                  class="quote-item"
                >
                  <NuxtLink class="quote-item__img-link" :to="`/p/${item.spu_public_id}`">
                    <img
                      v-if="metaFor(item)?.image"
                      class="quote-item__img"
                      :src="metaFor(item).image"
                      :alt="item.title"
                      width="96"
                      height="96"
                    />
                    <span
                      v-else
                      class="quote-item__img quote-item__img--placeholder"
                      aria-hidden="true"
                    ></span>
                  </NuxtLink>
                  <div class="quote-item__body">
                    <NuxtLink class="quote-item__name" :to="`/p/${item.spu_public_id}`">
                      {{ item.title }}
                    </NuxtLink>
                    <p v-if="specFor(item)" class="quote-item__spec">{{ specFor(item) }}</p>
                    <p class="quote-item__qty">Qty: {{ item.quantity }}</p>
                  </div>
                  <span class="quote-item__line">
                    {{ formatMoney(Number(item.price) * item.quantity) }}
                  </span>
                </li>
              </ul>
            </div>

            <div class="pay-card">
              <h3>{{ t('checkout.paymentMethod') }}</h3>

              <!-- 2026-11-28 二次改版：银行卡分组提到最前，8 个品牌 icon
                   （真站口径），选中即记录对应支付方式，无卡号输入框。 -->
              <h3 class="pay-brands__title">{{ t('checkout.cardTitle') }}</h3>
              <div class="pay-brands" role="radiogroup" :aria-label="t('checkout.cardTitle')">
                <label
                  v-for="brand in cardBrands"
                  :key="brand.value"
                  class="pay-brand"
                  :class="{ 'pay-brand--active': paymentMethod === brand.value }"
                >
                  <input
                    v-model="paymentMethod"
                    type="radio"
                    name="payment"
                    :value="brand.value"
                  />
                  <img :src="brand.icon" :alt="brand.label" />
                </label>
              </div>

              <ul class="pay-methods">
                <li v-for="method in paymentMethods" :key="method.value">
                  <label class="pay-methods__option">
                    <input
                      v-model="paymentMethod"
                      type="radio"
                      name="payment"
                      :value="method.value"
                    />
                    <img
                      v-if="method.icon"
                      class="pay-methods__icon"
                      :src="method.icon"
                      :alt="method.label"
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
            <!-- 2026-11-28：优惠明细/配送费行移除，仅保留 小计 + 订单合计。 -->
            <dl class="quote-totals">
              <div class="quote-totals__row">
                <dt>{{ t('checkout.subtotal') }}</dt>
                <dd>{{ formatMoney(quote?.subtotal) }}</dd>
              </div>
              <div class="quote-totals__total">
                <dt>{{ t('checkout.orderTotal') }}</dt>
                <dd>{{ formatMoney(quote?.total) }}</dd>
              </div>
            </dl>
            <button class="pay-now" type="button" :disabled="submitting || !quote" @click="payNow">
              {{ submitting ? t('checkout.paying') : t('checkout.payNow') }}
            </button>
            <!-- 条款声明（2026-11-28）：使用条款/隐私与Cookie政策可点击跳转。 -->
            <p class="checkout__notice">
              {{ t('checkout.termsPrefix') }}
              <NuxtLink class="checkout__notice-link" to="/pages/terms-conditions">
                {{ t('checkout.termsTerms') }}
              </NuxtLink>{{ t('checkout.termsMiddle') }}
              <NuxtLink class="checkout__notice-link" to="/pages/privacy-policy">
                {{ t('checkout.termsPrivacy') }}
              </NuxtLink>{{ t('checkout.termsSuffix') }}
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
  gap: 0;
  margin: 0;
  padding: 0;
  list-style: none;
}

/* 商品行（2026-11-28）：缩略图 + 标题/规格/数量 + 行小计，行间分隔线。 */
.quote-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 0;
}

.quote-item + .quote-item {
  border-top: 1px solid #f0f1f3;
}

.quote-item__img-link {
  flex: none;
}

.quote-item__img {
  display: block;
  width: 96px;
  height: 96px;
  border: 1px solid #eef0f2;
  border-radius: 4px;
  object-fit: cover;
  background: #f7f8fa;
}

.quote-item__img--placeholder {
  display: block;
}

.quote-item__body {
  flex: 1;
  min-width: 0;
}

.quote-item__name {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  color: #1a1a1a;
  font-size: 14px;
  line-height: 1.45;
  text-decoration: none;
}

.quote-item__name:hover {
  text-decoration: underline;
}

.quote-item__spec {
  margin: 4px 0 0;
  color: #999;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quote-item__qty {
  margin: 6px 0 0;
  color: #666;
  font-size: 12px;
}

.quote-item__line {
  flex: none;
  align-self: center;
  font-size: 16px;
  font-weight: var(--font-weight-bold);
  color: #1a1a1a;
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

/* 银行卡品牌直选（2026-11-28 改版）：icon 行，选中态红框。 */
.pay-brands__title {
  margin: var(--space-4) 0 var(--space-2);
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: #1a1a1a;
}

.pay-brands {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.pay-brand {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 44px;
  padding: 4px 8px;
  border: 1px solid #ccced2;
  border-radius: 4px;
  cursor: pointer;
  background: var(--colour-surface);
}

.pay-brand img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.pay-brand input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.pay-brand--active {
  border-color: #cc0c1c;
  box-shadow: 0 0 0 1px #cc0c1c;
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

/* 2026-11-28：小计加黑加粗 + 行距加大；订单合计更大更粗（含价格）。 */
.quote-totals__row {
  padding-block: var(--space-2);
}

.quote-totals__row dt {
  font-weight: var(--font-weight-bold);
  color: #1a1a1a;
}

.quote-totals__row dd {
  color: #1a1a1a;
}

.quote-totals > div {
  display: flex;
  justify-content: space-between;
  padding-block: var(--space-1);
}

.quote-totals__total {
  margin-top: var(--space-3);
  padding-block: var(--space-2) 0;
  border-top: 1px solid var(--colour-border);
}

.quote-totals__total dt {
  font-size: 16px;
  font-weight: var(--font-weight-bold);
  color: #1a1a1a;
}

.quote-totals__total dd {
  font-size: 20px;
  font-weight: var(--font-weight-bold);
  color: #1a1a1a;
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

.checkout__notice-link {
  color: var(--colour-text);
  text-decoration: underline;
}

.pay-methods__icon {
  width: 28px;
  height: 20px;
  object-fit: contain;
  flex: none;
}

@media (max-width: 64rem) {
  .checkout__columns {
    grid-template-columns: 1fr;
  }
}
</style>
