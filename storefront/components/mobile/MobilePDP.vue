<script setup>
import { computed, ref, watch } from 'vue'

import { useLocale } from '../../composables/useLocale'
import { formatDisplayPrice } from '../../utils/display'

// Mobile product detail (docs/20 §2): full-width square gallery with dot
// indicators (static display, no swipe gestures), a 16px/700 two-line title
// with promo badge and 22px/700 red price, variant-axis pills + quantity
// stepper, the service-guarantee row, a collapsed "Product details" card
// (spec tables + detail images) and a fixed bottom purchase bar (wishlist
// heart + outlined-red add-to-cart + solid-red buy-now). All business logic
// (variant resolution, cart/wishlist/purchase-gate handling) stays in
// pages/p/[id].vue — this component receives the resolved reactive state as
// props and emits user actions back (ADR 0001: desktop template untouched).
const props = defineProps({
  data: { type: Object, default: null },
  error: { type: Object, default: null },
  mediaItems: { type: Array, default: () => [] },
  offer: { type: Object, default: null },
  price: { type: String, default: '' },
  variantAxes: { type: Array, default: () => [] },
  selectedSku: { type: Object, default: null },
  selectedSkuSpec: { type: Object, default: null },
  isSingleSku: { type: Boolean, default: false },
  readonlySpec: { type: String, default: '' },
  quantity: { type: Number, default: 1 },
  addState: { type: String, default: 'idle' },
  wishlisted: { type: Boolean, default: false },
  wishPending: { type: Boolean, default: false },
  contentSections: { type: Array, default: () => [] },
  specificationTables: { type: Array, default: () => [] },
  // 批次 DB（Q9/Q10）：族内兄弟商品（型号轴）与当前规格的商家 list。
  familyMembers: { type: Array, default: () => [] },
  familyAxisName: { type: String, default: '' },
  merchants: { type: Array, default: () => [] },
})

const emit = defineEmits([
  'select-variant',
  'change-quantity',
  'add-to-cart',
  'buy-now',
  'toggle-wishlist',
  'select-merchant',
  'go-family-member',
])

const { t } = useLocale()

// Gallery: videos keep the static poster frame; every media item gets a dot.
const activeMediaIndex = ref(0)
const mediaImages = computed(() =>
  props.mediaItems.map((item) => ({
    key: item.key,
    url: item.type === 'image' ? item.url : item.poster || '',
  })),
)
// 切规格换画廊（批次 DA）后回到第一张：旧下标可能超出新画廊长度，否则主图
// 会变成空白占位。
watch(
  () => mediaImages.value.map((item) => item.key).join('|'),
  () => {
    activeMediaIndex.value = 0
  },
)
const currentImage = computed(() => {
  const active = mediaImages.value[activeMediaIndex.value] || mediaImages.value[0]
  return active?.url || ''
})

function selectMedia(index) {
  activeMediaIndex.value = index
}

const errorText = computed(() =>
  props.error?.statusCode === 404
    ? t('product.unavailable')
    : props.error?.message || t('product.unavailable'),
)

// Same active-value check as the desktop variant buttons, fed the resolved
// matchSpec(selectedSku) via the selectedSkuSpec prop.
function isValueActive(axis, value) {
  return (
    String(props.selectedSkuSpec?.[axis.name]) === String(value.value) ||
    (Array.isArray(value.sku_ids) && value.sku_ids.includes(props.selectedSku?.public_id))
  )
}

// 真站轴标题是「轴名: 当前值」，值加粗 600
// （var/pdp_spec_ui_20261127/measurements.md §1）。
function axisSelectedValue(axis) {
  const value = props.selectedSkuSpec?.[axis.name]
  return value === undefined || value === null ? '' : String(value)
}

const guaranteeItems = computed(() => [
  { key: 'returns', label: t('detail.guaranteeReturns') },
  { key: 'warranty', label: t('detail.guaranteeWarranty') },
  { key: 'support', label: t('detail.guaranteeSupport') },
])

const detailsOpen = ref(false)
const hasDetails = computed(
  () =>
    props.specificationTables.length > 0 ||
    props.contentSections.length > 0 ||
    Boolean(props.data?.description),
)

const addLabel = computed(() =>
  props.addState === 'added'
    ? t('detail.addedToCart')
    : props.addState === 'error'
      ? t('detail.couldNotAdd')
      : t('detail.addToCart'),
)
</script>

<template>
  <div class="m-pdp">
    <div v-if="error" class="m-pdp__state" role="alert">
      <p>{{ errorText }}</p>
      <NuxtLink to="/">{{ t('detail.continueShopping') }}</NuxtLink>
    </div>

    <template v-else>
      <!-- Gallery: full-width square image + dot indicators (docs/20 §2). -->
      <div class="m-pdp__gallery">
        <img
          v-if="currentImage"
          class="m-pdp__main-img"
          :src="currentImage"
          :alt="data?.title || ''"
        />
        <div v-else class="m-pdp__img-placeholder" aria-hidden="true"></div>
        <div v-if="mediaImages.length > 1" class="m-pdp__dots">
          <button
            v-for="(item, index) in mediaImages"
            :key="item.key"
            type="button"
            class="m-pdp__dot"
            :class="{ 'm-pdp__dot--active': index === activeMediaIndex }"
            :aria-label="t('mobile.pdp.galleryDot', { n: index + 1 })"
            @click="selectMedia(index)"
          ></button>
        </div>
      </div>

      <!-- Info block: title / promo badge / red price / seller row. -->
      <div class="m-pdp__info">
        <h1 class="m-pdp__title">{{ data?.title }}</h1>
        <span v-if="offer?.promotion_label" class="m-pdp__promo">{{ offer.promotion_label }}</span>
        <p v-if="price" class="m-pdp__price">{{ price }}</p>
        <p v-if="!offer" class="m-pdp__unavailable" role="status">
          {{ t('product.unavailableShort') }}
        </p>
        <p v-if="offer?.merchant?.display_name" class="m-pdp__seller">
          <span>{{ t('pdp.sellerLabel') }}</span>
          <span class="m-pdp__seller-name">{{ offer.merchant.display_name }}</span>
        </p>
      </div>

      <!-- Variant axes + quantity stepper (docs/20 §2). -->
      <div class="m-pdp__variants">
        <p v-if="isSingleSku && readonlySpec && !variantAxes.length" class="m-pdp__spec-readonly">
          {{ readonlySpec }}
        </p>
        <!-- 批次 DB：族内兄弟商品（型号/系列）整页跳转。 -->
        <div v-if="familyMembers.length > 1" class="m-pdp__axis m-pdp__axis--family">
          <span class="m-pdp__axis-name">{{ familyAxisName }}</span>
          <div class="m-pdp__axis-values">
            <button
              v-for="(member, index) in familyMembers"
              :key="member.spu_public_id"
              type="button"
              class="m-pdp__variant"
              :class="{ 'm-pdp__variant--active': member.is_current }"
              @click="emit('go-family-member', member)"
            >
              <span>{{ member.axis_label || member.title || 'Option ' + (index + 1) }}</span>
            </button>
          </div>
        </div>

        <div v-for="axis in variantAxes" :key="axis.name" class="m-pdp__axis m-pdp__axis--spec">
          <span class="m-pdp__axis-name">
            <span class="m-pdp__axis-label">{{ axis.name }}:</span>
            <span class="m-pdp__axis-selected">{{ axisSelectedValue(axis) }}</span>
          </span>
          <div class="m-pdp__axis-values">
            <button
              v-for="value in axis.values"
              :key="value.value"
              type="button"
              class="m-pdp__variant"
              :class="[
                axis.has_image ? 'm-pdp__variant--spec-image' : 'm-pdp__variant--spec',
                { 'm-pdp__variant--active': isValueActive(axis, value) },
              ]"
              @click="emit('select-variant', axis.name, value)"
            >
              <img
                v-if="value.image_url"
                class="m-pdp__variant-image"
                :src="value.image_url"
                alt=""
              />
              <span class="m-pdp__variant-label">{{ value.value }}</span>
            </button>
          </div>
        </div>

        <!-- 批次 DB：同一规格的多商家（切商家只改价格/库存/加购 offer）。 -->
        <div v-if="merchants.length > 1" class="m-pdp__axis m-pdp__axis--merchant">
          <span class="m-pdp__axis-name">{{ t('detail.sellerAxis') }}</span>
          <div class="m-pdp__axis-values">
            <button
              v-for="entry in merchants"
              :key="entry.public_id"
              type="button"
              class="m-pdp__variant"
              :class="{ 'm-pdp__variant--active': offer?.public_id === entry.public_id }"
              @click="emit('select-merchant', entry)"
            >
              <span
                >{{ entry.merchant?.display_name || '' }} ·
                {{ formatDisplayPrice(entry.price) }}</span
              >
            </button>
          </div>
        </div>

        <div class="m-pdp__quantity">
          <span class="m-pdp__quantity-label">{{ t('detail.quantity') }}</span>
          <div class="m-pdp__stepper">
            <button
              type="button"
              :aria-label="t('detail.decreaseQty')"
              @click="emit('change-quantity', -1)"
            >
              −
            </button>
            <span class="m-pdp__stepper-value" aria-live="polite">{{ quantity }}</span>
            <button
              type="button"
              :aria-label="t('detail.increaseQty')"
              @click="emit('change-quantity', 1)"
            >
              +
            </button>
          </div>
        </div>
      </div>

      <!-- Service guarantee row (docs/20 §2, desktop detail.guarantee* copy). -->
      <ul class="m-pdp__guarantees">
        <li v-for="item in guaranteeItems" :key="item.key" class="m-pdp__guarantee">
          <svg
            v-if="item.key === 'returns'"
            class="m-pdp__guarantee-icon"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              d="M4 9h13a3 3 0 0 1 3 3v3a3 3 0 0 1-3 3h-8l-2.5 2v-2H4a3 3 0 0 1-3-3v-3a3 3 0 0 1 3-3z"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
              transform="translate(1.5 -1)"
            />
          </svg>
          <svg
            v-else-if="item.key === 'warranty'"
            class="m-pdp__guarantee-icon"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              d="M12 3l7 2.5v5.2c0 4.6-3 8.4-7 10.3-4-1.9-7-5.7-7-10.3V5.5z"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
              stroke-linejoin="round"
            />
            <path d="M9 12l2.2 2.2L15.5 10" fill="none" stroke="currentColor" stroke-width="1.6" />
          </svg>
          <svg v-else class="m-pdp__guarantee-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path
              d="M4 12a8 8 0 0 1 16 0v5a3 3 0 0 1-3 3h-2v-6h3m-14-2a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-2a2 2 0 0 1 2-2zm14 0a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-2a2 2 0 0 1 2-2z"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
              stroke-linejoin="round"
            />
          </svg>
          <span>{{ item.label }}</span>
        </li>
      </ul>

      <!-- "Product details" card: collapsed by default, expands to the spec
           tables + detail images (docs/20 §2). -->
      <section v-if="hasDetails" class="m-pdp__details">
        <button
          type="button"
          class="m-pdp__details-head"
          :aria-expanded="detailsOpen"
          @click="detailsOpen = !detailsOpen"
        >
          <span>{{ t('detail.productDetails') }}</span>
          <span class="m-pdp__details-toggle">{{
            detailsOpen ? t('mobile.pdp.collapse') : t('mobile.pdp.expand')
          }}</span>
        </button>
        <div v-if="detailsOpen" class="m-pdp__details-body">
          <template v-if="contentSections.length">
            <article
              v-for="(section, sectionIndex) in contentSections"
              :key="`${section.title || 'section'}-${sectionIndex}`"
              class="m-pdp__content-section"
            >
              <h3 v-if="section.title" class="m-pdp__content-title">{{ section.title }}</h3>
              <p
                v-for="(block, blockIndex) in section.blocks || []"
                :key="blockIndex"
                class="m-pdp__content-paragraph"
              >
                {{ block.text }}
              </p>
              <img
                v-for="(image, imageIndex) in section.images || []"
                :key="image"
                class="m-pdp__content-img"
                :src="image"
                :alt="`${section.title || data?.title || ''} ${imageIndex + 1}`"
                loading="lazy"
                decoding="async"
              />
            </article>
          </template>
          <p v-else-if="data?.description" class="m-pdp__description">{{ data.description }}</p>

          <div
            v-for="(table, tableIndex) in specificationTables"
            :key="`${table.title || 'spec'}-${tableIndex}`"
            class="m-pdp__spec-group"
          >
            <h3 v-if="table.title" class="m-pdp__spec-title">{{ table.title }}</h3>
            <table class="m-pdp__spec-table">
              <tbody>
                <tr v-for="(row, rowIndex) in table.rows || []" :key="rowIndex">
                  <th scope="row">{{ row.name }}</th>
                  <td>{{ row.value }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <!-- Fixed bottom purchase bar (docs/20 §0): 56px + safe area, wishlist
           heart + outlined-red add + solid-red buy. Sits under the floating
           support launcher (z-index 1100). -->
      <div class="m-pdp__buybar">
        <button
          class="m-pdp__wish"
          :class="{ 'm-pdp__wish--active': wishlisted }"
          type="button"
          :aria-pressed="wishlisted"
          :aria-label="wishlisted ? t('product.removeFromWishlist') : t('product.addToWishlist')"
          :disabled="wishPending"
          @click="emit('toggle-wishlist')"
        >
          <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
            <path
              d="M12 20.3 4.8 13a4.9 4.9 0 0 1 0-7 4.9 4.9 0 0 1 7 0l.2.2.2-.2a4.9 4.9 0 0 1 7 0 4.9 4.9 0 0 1 0 7L12 20.3Z"
              :fill="wishlisted ? 'currentColor' : 'none'"
              stroke="currentColor"
              stroke-width="1.6"
            />
          </svg>
        </button>
        <button
          class="m-pdp__add"
          type="button"
          :disabled="!offer?.is_purchasable || addState === 'adding'"
          @click="emit('add-to-cart')"
        >
          {{ addLabel }}
        </button>
        <button class="m-pdp__buy" type="button" :disabled="!offer" @click="emit('buy-now')">
          {{ t('detail.buyNow') }}
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.m-pdp {
  /* Keep the page content clear of the fixed purchase bar. */
  padding-bottom: 76px;
  background: #f5f6fa;
  min-height: 60vh;
}

.m-pdp__state {
  margin: 32px 16px;
  padding: 24px 16px;
  border: 1px dashed #c7c9cf;
  border-radius: 12px;
  background: #ffffff;
  color: #7a7d85;
  font-size: 15px;
  text-align: center;
}

.m-pdp__state a {
  display: inline-block;
  margin-top: 12px;
  color: #1a1a1a;
  font-weight: var(--font-weight-semibold);
}

/* --- Gallery --- */
.m-pdp__gallery {
  position: relative;
  background: #ffffff;
}

.m-pdp__main-img {
  display: block;
  width: 100%;
  aspect-ratio: 1 / 1;
  object-fit: cover;
  background: #eceef1;
}

.m-pdp__img-placeholder {
  width: 100%;
  aspect-ratio: 1 / 1;
  background: #eceef1;
}

.m-pdp__dots {
  position: absolute;
  bottom: 12px;
  left: 50%;
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 6px;
  /* 合并族画廊可能几十张图：旧版 29 个圆点在 375 宽下横向溢出 13px。
     这里允许换行并限制在画廊宽度内，避免移动端横向滚动。 */
  max-width: calc(100% - 24px);
  transform: translateX(-50%);
}

.m-pdp__dot {
  width: 8px;
  height: 8px;
  padding: 0;
  border: 1px solid rgb(26 26 26 / 35%);
  border-radius: 50%;
  background: rgb(255 255 255 / 65%);
  cursor: pointer;
}

.m-pdp__dot--active {
  border-color: #ffffff;
  background: #1a1a1a;
}

/* --- Info block --- */
.m-pdp__info {
  padding: 12px 16px 4px;
}

.m-pdp__title {
  display: block;

  overflow: visible;
  margin: 0;
  color: #1a1a1a;
  font-size: 16px;
  font-weight: var(--font-weight-bold);
  line-height: 22px;
  word-break: break-word;
}

.m-pdp__promo {
  display: inline-block;
  margin-top: 8px;
  padding: 2px 8px;
  border-radius: 4px;
  background: #fdecea;
  color: #e1251b;
  font-size: 12px;
  font-weight: var(--font-weight-semibold);
}

.m-pdp__price {
  margin: 8px 0 0;
  color: #e1251b;
  font-size: 22px;
  font-weight: var(--font-weight-bold);
  line-height: 28px;
}

.m-pdp__unavailable {
  margin: 8px 0 0;
  color: #e1251b;
  font-size: 14px;
  font-weight: var(--font-weight-semibold);
}

.m-pdp__seller {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 10px 0 0;
  color: #55565b;
  font-size: 13px;
}

.m-pdp__seller-name {
  color: #1a1a1a;
  font-weight: var(--font-weight-semibold);
}

/* --- Variants + quantity --- */
.m-pdp__variants {
  margin-top: 8px;
  padding: 12px 16px;
  background: #ffffff;
}

.m-pdp__spec-readonly {
  margin: 0;
  color: #55565b;
  font-size: 14px;
}

.m-pdp__axis {
  margin-top: 4px;
}

.m-pdp__axis + .m-pdp__axis {
  margin-top: 12px;
}

.m-pdp__axis-name {
  display: block;
  color: #7a7d85;
  font-size: 14px;
}

.m-pdp__axis-values {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.m-pdp__variant {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 14px;
  border: 1px solid #d5d7db;
  border-radius: 18px;
  background: #ffffff;
  color: #1a1a1a;
  font: inherit;
  font-size: 14px;
  cursor: pointer;
}

.m-pdp__variant--active {
  border: 2px solid #1a1a1a;
  padding: 0 13px;
  color: #1a1a1a;
  font-weight: var(--font-weight-semibold);
}

.m-pdp__variant-image {
  width: 24px;
  height: 24px;
  border-radius: 4px;
  object-fit: cover;
}

/* --- 规格轴：与桌面同一份真站实测（var/pdp_spec_ui_20261127/measurements.md）。
   标题 16px/500/#1a1a1a（当前值 600）、标题下间距 12、选项 gap 8；
   有图 = 80 宽卡片（图 72×72 在上、名 14px/500 在下）；
   无图 = 文字胶囊 8px 12px、圆角 4、底色 #f5f6fa；
   选中只换边框 #1a1a1a + 字重 600，底色与文字色不变。 */
.m-pdp__axis--spec {
  padding: 12px 0;
}

.m-pdp__axis--spec + .m-pdp__axis--spec {
  margin-top: 0;
}

.m-pdp__axis--spec .m-pdp__axis-name {
  color: #1a1a1a;
  font-size: 16px;
  font-weight: 500;
  line-height: 22px;
}

.m-pdp__axis--spec .m-pdp__axis-label {
  margin-right: 4px;
}

.m-pdp__axis--spec .m-pdp__axis-selected {
  font-weight: 600;
}

.m-pdp__axis--spec .m-pdp__axis-values {
  margin-top: 12px;
}

.m-pdp__variant--spec-image {
  flex-direction: column;
  align-items: center;
  gap: 0;
  width: 80px;
  height: auto;
  min-height: 36px;
  padding: 3px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: #f5f6fa;
  color: #1a1a1a;
  font-size: 14px;
  font-weight: 500;
}

.m-pdp__variant--spec-image .m-pdp__variant-image {
  width: 72px;
  height: 72px;
  border-radius: 3px;
  object-fit: contain;
  background: #ffffff;
}

.m-pdp__variant--spec-image .m-pdp__variant-label {
  width: 100%;
  margin-top: 3px;
  padding: 0 8px;
  font-size: 14px;
  font-weight: 500;
  line-height: 20px;
  text-align: center;
  overflow: visible;
  white-space: normal;
  word-break: break-word;
}

.m-pdp__variant--spec {
  gap: 0;
  height: auto;
  min-height: 36px;
  padding: 8px 12px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: #f5f6fa;
  color: #1a1a1a;
  font-size: 14px;
  font-weight: 500;
  line-height: 20px;
}

.m-pdp__variant--spec-image:hover,
.m-pdp__variant--spec:hover {
  background: rgba(0, 16, 71, 0.06);
}

.m-pdp__variant--spec-image.m-pdp__variant--active,
.m-pdp__variant--spec.m-pdp__variant--active {
  border: 1px solid #1a1a1a;
  background: #f5f6fa;
  color: #1a1a1a;
}

.m-pdp__variant--spec.m-pdp__variant--active {
  font-weight: 600;
}

.m-pdp__variant--spec-image.m-pdp__variant--active .m-pdp__variant-label {
  font-weight: 600;
}

.m-pdp__quantity {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
}

.m-pdp__quantity-label {
  color: #7a7d85;
  font-size: 14px;
}

.m-pdp__stepper {
  display: inline-flex;
  align-items: center;
  border: 1px solid #d5d7db;
  border-radius: 8px;
  overflow: hidden;
}

.m-pdp__stepper button {
  width: 36px;
  height: 36px;
  border: 0;
  background: #f5f6fa;
  color: #1a1a1a;
  cursor: pointer;
  font-size: 16px;
}

.m-pdp__stepper-value {
  min-width: 44px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #1a1a1a;
  font-size: 14px;
  font-weight: var(--font-weight-bold);
}

/* --- Guarantee rows --- */
.m-pdp__guarantees {
  display: flex;
  gap: 12px;
  margin: 8px 0 0;
  padding: 12px 16px;
  background: #ffffff;
  list-style: none;
}

.m-pdp__guarantee {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-width: 0;
  color: #1a1a1a;
  font-size: 12px;
  text-align: center;
}

.m-pdp__guarantee-icon {
  flex: none;
  width: 18px;
  height: 18px;
  color: #1a1a1a;
}

/* --- Details card --- */
.m-pdp__details {
  margin-top: 8px;
  background: #ffffff;
}

.m-pdp__details-head {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border: 0;
  background: none;
  color: #1a1a1a;
  font: inherit;
  font-size: 15px;
  font-weight: var(--font-weight-bold);
  text-align: left;
  cursor: pointer;
}

.m-pdp__details-toggle {
  color: #7a7d85;
  font-size: 13px;
  font-weight: 400;
}

.m-pdp__details-body {
  padding: 0 16px 16px;
  border-top: 1px solid #f0f1f2;
}

.m-pdp__content-section + .m-pdp__content-section {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #f0f1f2;
}

.m-pdp__content-title {
  margin: 12px 0 0;
  color: #1a1a1a;
  font-size: 15px;
  font-weight: var(--font-weight-bold);
}

.m-pdp__content-paragraph {
  margin: 8px 0 0;
  color: #55565b;
  font-size: 14px;
  line-height: 20px;
}

/* Detail images stack vertically at full card width (docs/20 §2). */
.m-pdp__content-img {
  display: block;
  width: 100%;
  height: auto;
  margin-top: 12px;
  border-radius: 8px;
  background: #eceef1;
}

.m-pdp__description {
  margin: 12px 0 0;
  color: #55565b;
  font-size: 14px;
  line-height: 20px;
  white-space: pre-line;
}

.m-pdp__spec-group {
  margin-top: 16px;
}

.m-pdp__spec-title {
  margin: 0 0 8px;
  color: #1a1a1a;
  font-size: 14px;
  font-weight: var(--font-weight-bold);
}

.m-pdp__spec-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.m-pdp__spec-table th,
.m-pdp__spec-table td {
  padding: 8px 10px;
  border: 1px solid #eceef1;
  text-align: left;
  vertical-align: top;
}

.m-pdp__spec-table tbody th {
  width: 34%;
  background: #f5f6fa;
  color: #1a1a1a;
  font-weight: var(--font-weight-semibold);
}

.m-pdp__spec-table tbody td {
  color: #55565b;
}

/* --- Fixed purchase bar (docs/20 §0: 56px + safe area, buttons 48px) --- */
.m-pdp__buybar {
  position: fixed;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  gap: 10px;
  height: calc(56px + env(safe-area-inset-bottom));
  padding: 0 12px env(safe-area-inset-bottom);
  border-top: 1px solid #f0f1f2;
  background: #ffffff;
}

.m-pdp__wish {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  padding: 0;
  border: 0;
  background: none;
  color: #1a1a1a;
  cursor: pointer;
}

.m-pdp__wish--active {
  color: #e1251b;
}

.m-pdp__wish:disabled {
  cursor: progress;
  opacity: 0.65;
}

.m-pdp__add,
.m-pdp__buy {
  flex: 1;
  min-width: 0;
  height: 48px;
  border-radius: 24px;
  color: #e1251b;
  font: inherit;
  font-size: 15px;
  font-weight: var(--font-weight-bold);
  cursor: pointer;
}

.m-pdp__add {
  border: 1px solid #e1251b;
  background: #ffffff;
}

.m-pdp__add:hover:not(:disabled) {
  background: #fdecea;
}

.m-pdp__buy {
  border: 0;
  background: #e1251b;
  color: #ffffff;
}

.m-pdp__buy:hover:not(:disabled) {
  background: #d14335;
}

.m-pdp__add:disabled,
.m-pdp__buy:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
