<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { navigateTo, useHead } from '#imports'

import { useCart } from '~/composables/useCart'
import { useLocale } from '../../composables/useLocale'
import { useMarketLocale } from '../../composables/useMarketLocale'

// 批次 D（功能需求迭代文档03 11.9）：购物车页 1:1 复刻 Joybuy /cart。
// 批次 G（12.3）：按商家分组渲染白卡（后端 item.merchant 增量字段）；
// 组内全选/顶部全选联动，仅是展示层状态。数据契约不变：仍走 useCart
// （GET /api/v1/cart、PATCH/DELETE /cart/items/:id），去结算仍跳现有 /checkout
// （无参数）。真站实测数值见 var/cart_page_20261119/measurement.md 与
// var/cart_merchant_group_20261119/measurement.md（配送/自提 tabs 已去掉）。
// 批次 M（13.7，2026-11-20）：①左侧 <h1> 去掉（真站 SSR 0 个 h1，标签页标题保留）；
// ②右侧合计下方补支付图标行（真站 paymentLogos 顺序，本地 pdp-services SVG）；
// ③页面底部加【精选好物】（ChannelPickedForYou 不带 category = 全库池，交互同 13.4）。

const { items, subtotal, needsAttention, formatMoney, updateItem, removeItem } = await useCart()

const { t } = useLocale()
const { apiQuery } = useMarketLocale()

useHead({ title: () => t('cart.title') })

// 真站购物车 paymentLogos 顺序（var/header_footer_cart_20261119/measurement.md §2）：
// Amex → Visa → Mastercard → (Maestro) → PayPal → WeChat → Google → Apple → Klarna →
// (iDEAL/Bancontact)。本地无 Maestro/iDEAL/Bancontact SVG，取可用的 8 个按真站顺序。
const paymentIcons = [
  { name: 'American Express', src: '/images/pdp-services/payment-american-express.svg' },
  { name: 'Visa', src: '/images/pdp-services/payment-visa.svg' },
  { name: 'Mastercard', src: '/images/pdp-services/payment-mastercard.svg' },
  { name: 'PayPal', src: '/images/pdp-services/payment-paypal.svg' },
  { name: 'WeChat Pay', src: '/images/pdp-services/payment-wechat-pay.svg' },
  { name: 'Google Pay', src: '/images/pdp-services/payment-google-pay.svg' },
  { name: 'Apple Pay', src: '/images/pdp-services/payment-apple-pay.svg' },
  { name: 'Klarna', src: '/images/pdp-services/payment-klarna.svg' },
]

// 展示层增强：商品图 + 规格。只读复用现有 GET /api/v1/products/:id，
// 以 offer_public_id 对上购物车行取规格，不改任何后端契约。
const productMeta = ref({}) // spu_public_id -> { image, specByOffer: { offerId: spec } }
const QUANTITY_MAX = 99

const validItems = computed(() => items.value.filter((item) => item.is_valid))
const selectableIds = computed(() => validItems.value.map((item) => item.public_id))

const selectedIds = ref(new Set())
watch(
  items,
  (list) => {
    const valid = new Set(list.filter((item) => item.is_valid).map((item) => item.public_id))
    const next = new Set([...selectedIds.value].filter((id) => valid.has(id)))
    if (next.size === 0) {
      for (const id of valid) next.add(id)
    }
    selectedIds.value = next
  },
  { immediate: true },
)

const selectedCount = computed(() => {
  const ids = selectedIds.value
  return validItems.value
    .filter((item) => ids.has(item.public_id))
    .reduce((sum, item) => sum + item.quantity, 0)
})

const allSelected = computed(
  () =>
    selectableIds.value.length > 0 && selectableIds.value.every((id) => selectedIds.value.has(id)),
)

// 顶部全选半选态：部分组/部分行选中（同组选口径）
const topIndeterminate = computed(() => {
  const picked = selectableIds.value.filter((id) => selectedIds.value.has(id)).length
  return picked > 0 && picked < selectableIds.value.length
})

// 批次 G：按商家分组（保序：按行首次出现的顺序）。后端 item.merchant 缺失
// （旧 payload 防御）时整行归入 Joybuy 官营组，观感与批次 D 单卡一致。
const DEFAULT_MERCHANT = { merchant_id: '', merchant_name: 'Joybuy', merchant_avatar_url: '' }

const merchantGroups = computed(() => {
  const groups = []
  const index = new Map()
  for (const item of items.value) {
    const merchant = item.merchant || DEFAULT_MERCHANT
    const key = merchant.merchant_id || merchant.merchant_name || DEFAULT_MERCHANT.merchant_name
    let group = index.get(key)
    if (!group) {
      group = { key, merchant, items: [] }
      index.set(key, group)
      groups.push(group)
    }
    group.items.push(item)
  }
  return groups
})

function groupSelectableIds(group) {
  return group.items.filter((item) => item.is_valid).map((item) => item.public_id)
}

function isGroupAllSelected(group) {
  const ids = groupSelectableIds(group)
  return ids.length > 0 && ids.every((id) => selectedIds.value.has(id))
}

// 半选：组内部分选中（真站实车不可测，按同站 JDICheckbox 口径做 indeterminate）
function isGroupIndeterminate(group) {
  const ids = groupSelectableIds(group)
  const picked = ids.filter((id) => selectedIds.value.has(id)).length
  return picked > 0 && picked < ids.length
}

function toggleGroup(group) {
  const ids = groupSelectableIds(group)
  const next = new Set(selectedIds.value)
  if (isGroupAllSelected(group)) ids.forEach((id) => next.delete(id))
  else ids.forEach((id) => next.add(id))
  selectedIds.value = next
}

function toggleItem(item) {
  if (!item.is_valid) return
  const next = new Set(selectedIds.value)
  if (next.has(item.public_id)) next.delete(item.public_id)
  else next.add(item.public_id)
  selectedIds.value = next
}

function toggleAll() {
  selectedIds.value = allSelected.value ? new Set() : new Set(selectableIds.value)
}

// useLocale 的 t 不做插值，{name} 在页内替换（文案见 cart.fulfilledByMerchant）
function fulfilledText(merchantName) {
  return t('cart.fulfilledByMerchant').replace('{name}', merchantName)
}

function lineTotal(item) {
  return formatMoney(Number(item.price) * item.quantity)
}

async function onQuantityStep(item, delta) {
  const quantity = item.quantity + delta
  if (quantity < 1 || quantity > QUANTITY_MAX) return
  await updateItem(item.public_id, quantity)
}

async function onQuantityInput(item, event) {
  const quantity = Number.parseInt(event.target.value, 10)
  if (
    Number.isInteger(quantity) &&
    quantity >= 1 &&
    quantity <= QUANTITY_MAX &&
    quantity !== item.quantity
  ) {
    await updateItem(item.public_id, quantity)
  } else {
    event.target.value = String(item.quantity)
  }
}

async function onRemove(item) {
  await removeItem(item.public_id)
  const next = new Set(selectedIds.value)
  next.delete(item.public_id)
  selectedIds.value = next
}

// 展示层增强：商品图 + 规格。只读复用现有 GET /api/v1/products/:id，
// 以 offer_public_id 对上购物车行取规格，不改任何后端契约。
onMounted(async () => {
  const spuIds = [...new Set(items.value.map((item) => item.spu_public_id))]
  await Promise.all(
    spuIds.map(async (spuId) => {
      try {
        const detail = await $fetch(
          `/api/v1/products/${spuId}${apiQuery.value ? `?${apiQuery.value}` : ''}`,
        )
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
        // 展示层增强失败不阻塞购物车主流程
      }
    }),
  )
})

// 契约不变：去结算仍走现有 /checkout（结算项以购物车后端数据为准）
function goCheckout() {
  if (items.value.length === 0) return
  navigateTo('/checkout')
}

function metaFor(item) {
  return productMeta.value[item.spu_public_id] || null
}

function specFor(item) {
  const raw = metaFor(item)?.specByOffer?.[item.offer_public_id]
  if (!raw) return ''
  // 后端规格可能是对象（{Model: "...", Series: "..."}）或 JSON 字符串——按真站 PDP
  // 口径展示为取值以 " / " 连接（如 "D9 Max Gen2 / Robot Vacuum"）。
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

function imageFor(item) {
  return metaFor(item)?.image || ''
}
</script>

<template>
  <div class="cart-page">
    <AppContainer class="cart-page__container">
      <div class="cart-page__columns">
        <div class="cart-page__left">
          <!-- 空购物车态（真站 emptyFloorView） -->
          <div v-if="items.length === 0" class="cart-card cart-card--empty" role="status">
            <div class="cart-card__empty-inner">
              <div class="cart-card__empty-row">
                <CartEmptyIllustration />
                <span class="cart-card__empty-text">{{ t('cart.empty') }}</span>
              </div>
              <NuxtLink to="/" class="cart-card__shopping-btn">{{ t('cart.goShopping') }}</NuxtLink>
            </div>
          </div>

          <template v-else>
            <div class="cart-card cart-card--head">
              <!-- 需求 13.7-1：左侧 <h1> 去掉（真站 /cart 无标题；useHead 标签页标题保留）。
                   真站此处为【配送/自提】tabs，按需求 11.9 去掉 -->
              <!-- 批次 G：顶部全选 = 所有组全选（与组全选联动）。单商家时只有
                   一张组卡，组头勾选已覆盖全部商品，故隐藏顶部行以保持批次 D 单卡观感 -->
              <div v-if="merchantGroups.length > 1" class="cart-head__select-row">
                <label class="cart-checkbox">
                  <input
                    type="checkbox"
                    :checked="allSelected"
                    :indeterminate.prop="topIndeterminate"
                    :disabled="selectableIds.length === 0"
                    :aria-label="t('cart.selectAll')"
                    @change="toggleAll"
                  />
                  <span class="cart-checkbox__label">{{ t('cart.selectAll') }}</span>
                </label>
              </div>
            </div>

            <p v-if="needsAttention" class="cart-page__notice" role="alert">
              {{ t('cart.priceChangedNotice') }}
            </p>

            <!-- 批次 G：按商家分组白卡（后端 item.merchant 增量字段；组头 =
                 组内全选 + 商家头像(有则显示) + 店名，单商家观感与批次 D 一致） -->
            <div
              v-for="group in merchantGroups"
              :key="group.key"
              class="cart-card cart-card--group"
            >
              <div class="cart-group__select-row">
                <label class="cart-checkbox">
                  <input
                    type="checkbox"
                    :checked="isGroupAllSelected(group)"
                    :indeterminate.prop="isGroupIndeterminate(group)"
                    :disabled="groupSelectableIds(group).length === 0"
                    :aria-label="`${t('cart.selectAll')} - ${group.merchant.merchant_name}`"
                    @change="toggleGroup(group)"
                  />
                </label>
                <div class="cart-group__identity">
                  <div class="cart-group__identity-row">
                    <span v-if="group.merchant.merchant_avatar_url" class="cart-group__avatar">
                      <img
                        :src="group.merchant.merchant_avatar_url"
                        :alt="group.merchant.merchant_name"
                        loading="lazy"
                      />
                    </span>
                    <span class="cart-group__store">{{ group.merchant.merchant_name }}</span>
                  </div>
                  <p class="cart-group__fulfilled">
                    {{ fulfilledText(group.merchant.merchant_name) }}
                  </p>
                </div>
              </div>

              <ul class="cart-group__list">
                <li
                  v-for="item in group.items"
                  :key="item.public_id"
                  class="cart-item"
                  :class="{ 'cart-item--invalid': !item.is_valid }"
                >
                  <span class="cart-item__check">
                    <input
                      type="checkbox"
                      :checked="selectedIds.has(item.public_id)"
                      :disabled="!item.is_valid"
                      :aria-label="item.title"
                      @change="toggleItem(item)"
                    />
                  </span>

                  <NuxtLink class="cart-item__img-link" :to="`/p/${item.spu_public_id}`">
                    <img
                      v-if="imageFor(item)"
                      class="cart-item__img"
                      :src="imageFor(item)"
                      :alt="item.title"
                      width="120"
                      height="120"
                      loading="lazy"
                    />
                    <span
                      v-else
                      class="cart-item__img cart-item__img--placeholder"
                      aria-hidden="true"
                    ></span>
                  </NuxtLink>

                  <div class="cart-item__body">
                    <div class="cart-item__top">
                      <div class="cart-item__text">
                        <NuxtLink class="cart-item__name" :to="`/p/${item.spu_public_id}`">
                          {{ item.title }}
                        </NuxtLink>
                        <p v-if="specFor(item)" class="cart-item__spec">{{ specFor(item) }}</p>
                        <p v-if="item.issue" class="cart-item__issue" role="status">
                          {{
                            item.issue === 'SKU_NOT_AVAILABLE'
                              ? t('cart.noLongerAvailable')
                              : t('cart.stockReduced')
                          }}
                        </p>
                      </div>
                      <div class="cart-item__price-col">
                        <span v-if="item.is_valid" class="cart-item__line">{{
                          lineTotal(item)
                        }}</span>
                      </div>
                    </div>

                    <div class="cart-item__actions">
                      <div
                        v-if="item.is_valid"
                        class="cart-item__stepper"
                        :aria-label="t('cart.quantity')"
                      >
                        <button
                          type="button"
                          class="cart-item__step-btn"
                          :disabled="item.quantity <= 1"
                          :aria-label="'-'"
                          @click="onQuantityStep(item, -1)"
                        >
                          −
                        </button>
                        <input
                          type="number"
                          class="cart-item__step-value"
                          min="1"
                          :max="QUANTITY_MAX"
                          :value="item.quantity"
                          :aria-label="t('cart.quantity')"
                          @change="onQuantityInput(item, $event)"
                        />
                        <button
                          type="button"
                          class="cart-item__step-btn"
                          :disabled="item.quantity >= QUANTITY_MAX"
                          :aria-label="'+'"
                          @click="onQuantityStep(item, 1)"
                        >
                          +
                        </button>
                      </div>
                      <span v-else class="cart-item__outstock"
                        >{{ item.inventory_display }} {{ t('product.inStock') }}</span
                      >
                      <button type="button" class="cart-item__delete" @click="onRemove(item)">
                        {{ t('cart.remove') }}
                      </button>
                    </div>
                  </div>
                </li>
              </ul>
            </div>
          </template>
        </div>

        <!-- 结算栏（真站 cartOrder） -->
        <aside class="cart-page__right">
          <div class="cart-summary">
            <h2 class="cart-summary__title">{{ t('cart.summaryTitle') }}</h2>

            <div v-if="items.length === 0" class="cart-summary__empty" role="status">
              <CartEmptyIllustration />
              <span class="cart-summary__empty-text">{{ t('cart.emptySummary') }}</span>
            </div>

            <template v-else>
              <div class="cart-summary__subtotal">
                <span class="cart-summary__subtotal-label">{{ t('cart.subtotal') }}</span>
                <strong class="cart-summary__subtotal-value">{{
                  formatMoney(subtotal) ?? '—'
                }}</strong>
              </div>
            </template>

            <div class="cart-summary__checkout-link">
              <button
                type="button"
                class="cart-summary__checkout"
                :disabled="items.length === 0"
                @click="goCheckout"
              >
                {{ t('cart.goToCheckout') }} ({{ selectedCount }})
              </button>
            </div>
            <p class="cart-summary__secure">{{ t('cart.securePayment') }}</p>
            <!-- 需求 13.7-2：合计下方支付图标行（真站 paymentLogos 顺序，本地托管 SVG） -->
            <div class="cart-summary__payments">
              <img
                v-for="brand in paymentIcons"
                :key="brand.name"
                class="cart-summary__payment-icon"
                :src="brand.src"
                :alt="brand.name"
                width="32"
                height="20"
                loading="lazy"
              />
            </div>
          </div>
        </aside>
      </div>

      <!-- 需求 13.7-3：底部【精选好物】——全库随机（不带 category），交互四步同 13.4 -->
      <ChannelPickedForYou class="cart-page__picked" />
    </AppContainer>
  </div>
</template>

<style scoped>
/* 全宽灰底（真站 cart_container: bg #F5F6FA, padding 32px 0） */
.cart-page {
  min-height: 60vh;
  padding: 32px 0;
  background: #f5f6fa;
}

/* 购物车内容区按真站 /cart 实测（2026-11-19，1440 视口内容 1344px、起点 x=48、
   左栏 884px）：只在购物车页子树内覆盖 --container-max（AppContainer 读的就是它），
   全局 token 1608px 不动。用 calc 是因为 --container-max 是含左右 padding 的盒宽。 */
.cart-page__container {
  --container-max: calc(1344px + 2 * var(--container-pad));
}

.cart-page__columns {
  display: flex;
  gap: 24px;
  align-items: flex-start;
}

.cart-page__left {
  flex: 1 1 auto;
  min-width: 0;
}

.cart-page__right {
  flex: 0 0 436px;
  position: sticky;
  top: 24px;
}

/* 白卡（真站 radius 8px 白底） */
.cart-card {
  border-radius: 8px;
  background: #fff;
}

/* 需求 13.7-1：h1 标题已删；多商家时头部卡只剩全选行 */
.cart-card--head {
  padding: 8px 0 16px;
}

.cart-page__notice {
  margin-top: 10px;
  padding: 12px 16px;
  border-radius: 8px;
  background: #fff5e6;
  color: #995c00;
  font-size: 14px;
  line-height: 20px;
}

.cart-card--group {
  margin-top: 10px;
  padding-bottom: 16px;
}

/* 顶部全选行（批次 G：真站实车不可测，沿用组头口径并对齐卡片左边距） */
.cart-head__select-row {
  display: flex;
  align-items: center;
  padding: 8px 16px 0;
}

.cart-group__select-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  min-height: 48px;
  padding: 16px 16px 0;
}

.cart-group__identity {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.cart-group__identity-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

/* 商家头像（批次 G：真站购物车懒加载 chunk 拿不到，按同站 token 近似：
   24px 方块、radius 4、灰底占位；间距 8px 与 PDP storeTitleInfoFloor 一致） */
.cart-group__avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  flex-shrink: 0;
  overflow: hidden;
  border-radius: 4px;
  background: #f5f6fa;
}

.cart-group__avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.cart-group__store {
  font-size: 16px;
  font-weight: 600;
  line-height: 22px;
  color: #1a1a1a;
}

.cart-group__fulfilled {
  font-size: 12px;
  line-height: 16px;
  color: #888b94;
}

.cart-group__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

/* 商品行（真站 cartList_cartItem: flex, padding-left 18px, margin-top 16px） */
.cart-item {
  display: flex;
  align-items: flex-start;
  margin-top: 16px;
  padding: 0 16px 0 18px;
}

.cart-item--invalid .cart-item__name,
.cart-item--invalid .cart-item__img {
  opacity: 0.5;
}

.cart-item__check {
  display: flex;
  align-items: center;
  margin-top: 50px;
}

/* 勾选框（真站 JDICheckbox: 20x20 radius 4 border #73757D；选中 bg #1A1A1A） */
.cart-checkbox input,
.cart-item__check input {
  appearance: none;
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border: 1px solid #73757d;
  border-radius: 4px;
  background: #fff center / 12px 12px no-repeat;
  cursor: pointer;
  transition: all 0.2s ease-in-out;
  margin: 0 2px;
}

.cart-checkbox input:checked,
.cart-item__check input:checked {
  border: none;
  background-color: #1a1a1a;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M2.5 6.5 5 9l4.5-6' fill='none' stroke='%23fff' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
}

/* 半选态（批次 G：组/顶部部分选中）：同 JDICheckbox 选中口径，图标换成白色横杠 */
.cart-checkbox input:indeterminate,
.cart-item__check input:indeterminate {
  border: none;
  background-color: #1a1a1a;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M2.5 6h7' fill='none' stroke='%23fff' stroke-width='1.6' stroke-linecap='round'/%3E%3C/svg%3E");
}

.cart-checkbox input:disabled,
.cart-item__check input:disabled {
  border-color: #e0e1e5;
  background-color: #edeff2;
  cursor: not-allowed;
}

.cart-checkbox {
  display: inline-flex;
  align-items: center;
  cursor: pointer;
}

.cart-checkbox__label {
  margin-left: 8px;
  font-size: 16px;
  line-height: 22px;
  color: #1a1a1a;
}

/* 商品图（真站 cartList_skuImg: 120x120 radius 8 contain） */
.cart-item__img-link {
  margin-left: 12px;
  flex-shrink: 0;
}

.cart-item__img {
  display: block;
  width: 120px;
  height: 120px;
  border-radius: 8px;
  object-fit: contain;
  background: #fff;
}

.cart-item__img--placeholder {
  background: #f5f6fa;
}

.cart-item__body {
  flex: 1 1 auto;
  min-width: 0;
  padding-left: 16px;
}

.cart-item__top {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.cart-item__text {
  flex: 1 1 auto;
  min-width: 0;
}

.cart-item__name {
  display: -webkit-box;
  overflow: hidden;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  text-overflow: ellipsis;
  word-break: break-word;
  font-size: 16px;
  font-weight: 500;
  line-height: 22px;
  color: #1a1a1a;
  text-decoration: none;
}

.cart-item__name:hover {
  color: #e1251b;
}

.cart-item__spec {
  margin-top: 8px;
  font-size: 14px;
  line-height: 20px;
  color: #888b94;
  word-break: break-all;
}

.cart-item__issue {
  margin-top: 8px;
  font-size: 14px;
  line-height: 18px;
  color: #888b94;
}

/* 价格列（真站 cartList_priceItem: width 204px 右对齐） */
.cart-item__price-col {
  flex: 0 0 204px;
  text-align: right;
}

.cart-item__line {
  font-size: 16px;
  font-weight: 700;
  line-height: 22px;
  color: #1a1a1a;
}

/* 数量步进器 + 删除（真站 cartList_counterBox 120x36 / counterDelete 下划线） */
.cart-item__actions {
  display: flex;
  align-items: center;
  margin-top: 16px;
  padding-bottom: 32px;
}

.cart-item__stepper {
  display: flex;
  align-items: center;
  width: 120px;
  height: 36px;
  border: 1px solid #e0e1e5;
  border-radius: 4px;
  overflow: hidden;
  background: #fff;
}

.cart-item__step-btn {
  width: 32px;
  height: 100%;
  border: 0;
  background: #fff;
  color: #1a1a1a;
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
}

.cart-item__step-btn:disabled {
  color: #c2c4cc;
  cursor: not-allowed;
}

.cart-item__step-value {
  width: 54px;
  height: 100%;
  border: 0;
  border-inline: 1px solid #f0f1f2;
  text-align: center;
  font-size: 14px;
  font-weight: 500;
  color: #1a1a1a;
  appearance: textfield;
  -moz-appearance: textfield;
}

.cart-item__step-value::-webkit-outer-spin-button,
.cart-item__step-value::-webkit-inner-spin-button {
  appearance: none;
  margin: 0;
}

.cart-item__outstock {
  font-size: 14px;
  color: #888b94;
}

.cart-item__delete {
  margin-left: 28px;
  height: 36px;
  border: 0;
  background: none;
  padding: 0;
  color: #1a1a1a;
  font-size: 14px;
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
}

/* 空购物车态（真站 emptyFloorView） */
.cart-card--empty {
  margin-top: 10px;
  min-height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.cart-card__empty-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.cart-card__empty-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.cart-card__empty-text {
  font-size: 18px;
  line-height: 24px;
  color: #c2c4cc;
}

.cart-card__shopping-btn {
  display: block;
  margin-top: 12px;
  padding: 8px 12px;
  border: 1px solid #888b94;
  border-radius: 4px;
  background: transparent;
  color: #1a1a1a;
  font-size: 14px;
  line-height: 18px;
  text-decoration: none;
}

.cart-card__shopping-btn:hover {
  background: #f5f6fa;
}

/* 结算栏（真站 cartOrder_container: padding 32px 16px 16px） */
.cart-summary {
  padding: 32px 16px 16px;
  border-radius: 8px;
  background: #fff;
}

.cart-summary__title {
  font-size: 24px;
  font-weight: 700;
  line-height: 24px;
  color: #1a1a1a;
}

.cart-summary__empty {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 24px;
}

.cart-summary__empty-text {
  font-size: 18px;
  line-height: 24px;
  color: #73757d;
}

.cart-summary__subtotal {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-top: 24px;
  padding: 12px 0;
}

.cart-summary__subtotal-label {
  font-size: 16px;
  line-height: 24px;
  color: #1a1a1a;
}

.cart-summary__subtotal-value {
  font-size: 20px;
  font-weight: 700;
  line-height: 24px;
  color: #1a1a1a;
}

/* 结算按钮（真站 cartOrder_button-check: bg #E1251B / hover #990915 / disabled #FF9FA7） */
.cart-summary__checkout-link {
  display: block;
  margin: 16px 0 0;
}

.cart-summary__checkout {
  width: 100%;
  height: 48px;
  padding: 12px 16px;
  border: 0;
  border-radius: 4px;
  background: #e1251b;
  color: #fff;
  font-size: 18px;
  font-weight: 700;
  line-height: 24px;
  cursor: pointer;
}

.cart-summary__checkout:hover:not(:disabled) {
  background: #990915;
}

.cart-summary__checkout:disabled {
  background: #ff9fa7;
  cursor: not-allowed;
}

.cart-summary__secure {
  margin-top: 8px;
  font-size: 14px;
  line-height: 36px;
  color: #505259;
}

/* 需求 13.7-2：支付图标行（真站 paymentLogos：本地 32x20 SVG，8px 间距） */
.cart-summary__payments {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}

.cart-summary__payment-icon {
  display: block;
  width: 32px;
  height: 20px;
}

/* 需求 13.7-3：购物车底部精选好物（组件默认 6 列网格，此处只补与上方卡区的间距） */
.cart-page__picked {
  margin-top: 24px;
  padding-bottom: 8px;
}

@media (max-width: 64rem) {
  .cart-page__columns {
    flex-direction: column;
  }

  .cart-page__right {
    position: static;
    width: 100%;
    flex-basis: auto;
  }

  .cart-item__price-col {
    flex-basis: auto;
  }

  .cart-item__actions {
    padding-bottom: 16px;
  }
}
</style>
