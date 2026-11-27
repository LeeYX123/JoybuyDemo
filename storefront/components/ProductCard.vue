<script setup>
import { computed, onMounted } from 'vue'
import { useLocale } from '../composables/useLocale'
import { useWishlist } from '../composables/useWishlist'

const { t } = useLocale()

import { formatDisplayPrice, isDeliveryLabel, isPromoLabel } from '../utils/display'

// Shared product card aligned to the joybuy.co.uk card spec (sampled from
// the Bestsellers floor, 2026-11-04): white 12px-radius card, full-width
// square image, 6px text inset, brand in bold, a two-line 16px/500 title
// clamped with an ellipsis, red price on the left with a 40px round add
// button on the right. Bestseller mode (`rank` > 0) shows the positional
// badge and hides the rating stars like the real floor; marketing labels
// ADR-0003（2026-11-27）：自营徽标（Sold by Joybuy）默认渲染、评分行全卡
// 显示、已售快照按真站样式展示；2026-11-03「营销标签一律不渲染」的旧口径
// 仅对 discount/promo/delivery 标签继续生效。商家页通过 show-self-operated
// 关闭徽标。An optional `viewed_count` on the product renders the real
// floor's "viewed in 72 hours" line when data exists.
const props = defineProps({
  product: {
    type: Object,
    required: true,
  },
  rank: {
    type: Number,
    default: 0,
  },
  // 频道页楼层卡不显示星级评分行（真站楼层卡没有评分，只有首页/搜索卡有）。
  // 默认 true，首页/搜索/精选好物的渲染结果不变。
  showRating: {
    type: Boolean,
    default: true,
  },
  // 频道页楼层卡价格口径（2026-11-23 用户拍板）：优先后台零售价
  // retail_price，缺失回退 price_min；不乘折扣、不显示划线原价/Promo 标签。
  useRetailPrice: {
    type: Boolean,
    default: false,
  },
  // 频道页卡片不显示品牌行（真站楼层卡没有品牌，2026-11-24）。默认 true，
  // 首页/搜索/购物车卡片渲染结果不变；频道页楼层仍由页面 :deep() 隐藏，
  // 精选好物走该 prop。
  showBrand: {
    type: Boolean,
    default: true,
  },
  // 自营徽标（ADR-0003）：默认显示「Sold by Joybuy / Joybuy自营」；
  // /merchants/ 商家店铺页不显示（用户 2026-11-27 口径），传 false 关闭。
  showSelfOperated: {
    type: Boolean,
    default: true,
  },
})

const price = computed(() => {
  if (props.useRetailPrice) {
    const raw = props.product.retail_price
    if (raw !== null && raw !== undefined && String(raw).trim() !== '') {
      // retail_price 契约是十进制字符串；万一带币种符号则原样展示。
      return formatDisplayPrice(raw) ?? String(raw).trim()
    }
  }
  return formatDisplayPrice(
    // 批次 DB（2026-11-27）：同款族卡片显示族内最高价；不在族里/缺价回退 price_min。
    props.product.family_max_price ?? props.product.price_min ?? props.product.price,
  )
})

// 划线原价：只在数据里真的带有更高的原价时渲染（真站折扣卡 14/500/20
// line-through）。搜索/推荐接口目前不返回原价字段，因此首页与搜索页的卡片
// 渲染结果不变；频道页的配色/字号由该页 :deep() 覆盖。
// 频道楼层走零售价口径 → 一律不出划线价（用户明确：不显示折扣）。
const originalPrice = computed(() => {
  if (props.useRetailPrice) return null
  const raw = props.product.original_price ?? props.product.compare_at_price ?? null
  if (raw === null || raw === undefined || raw === '') return null
  const original = Number(raw)
  const current = Number(props.product.price_min ?? props.product.price)
  if (!Number.isFinite(original) || !Number.isFinite(current) || original <= current) return null
  return formatDisplayPrice(original)
})

const image = computed(() => {
  const path = props.product.image_path || props.product.image
  return typeof path === 'string' && path ? path : ''
})

const href = computed(
  () => props.product.href || `/p/${props.product.spu_public_id || props.product.public_id || ''}`,
)

const brand = computed(() => {
  const name = props.product.brand_name || props.product.brand
  return typeof name === 'string' ? name : ''
})

const viewed = computed(() => {
  const count = Number(props.product.viewed_count ?? 0)
  return count > 0 ? `${count} people viewed in 72 hours` : ''
})

// 评分口径（2026-11-27）：搜索/推荐/CMS 接口返回 rating_average（十进制字符串）
// 与 rating_count（整数）。旧绑定 review_count 在真实接口数据上恒为 undefined，
// 导致卡片显示「(0)」。数量缺失或为 0 时不显示括号数字，绝不用 0 顶替；无评分
// 商品 rating_average 为 null，星级整行也不渲染。
const ratingValue = computed(() =>
  Number(props.product.rating_average ?? props.product.rating ?? 0),
)
// 评价数仍随评分行语义保留在 payload 上（ADR-0003 后卡片不展示评价数，
// 真站展示的是已售件数）；字段留给未来需要时使用。
const showRatingStars = computed(
  // ADR-0003（2026-11-27）：全站卡片显示评分行（真站楼层卡/营销页卡都有评分），
  // 不再限定 rank===0；无评分商品整行不渲染。
  () => props.showRating && ratingValue.value > 0,
)

// 已售快照（SpuDetail.sale_amount，如 "1.5k+"/"60+"）与自营徽标（ADR-0003）。
const soldAmount = computed(() => {
  const raw = props.product.sold_amount
  return typeof raw === 'string' && raw.trim() ? raw.trim() : ''
})
const showSold = computed(() => Boolean(soldAmount.value))
// 自营徽标：全站默认显示；/merchants/ 商家页由调用方传 false 隐藏。
const showSelfOperated = computed(() => props.showSelfOperated)

const badge = computed(() => {
  // Marketing labels (新客福利/优惠x%/送达/满减/自营) never render (req 5-6);
  // delivery-estimate and discount/promotion labels are suppressed by the
  // display rules too (2026-11-03 / 2026-11-25).
  // 频道楼层走零售价口径时连促销标签也不渲染（用户明确：不显示 Promo 标签）。
  if (props.useRetailPrice) return ''
  const label = props.product.badge
  if (!label || isDeliveryLabel(label) || isPromoLabel(label)) return ''
  return label
})

// Wishlist heart: session-backed, optimistic, and shared across every card.
const spuPublicId = computed(() =>
  String(props.product.spu_public_id || props.product.public_id || ''),
)
const { isFavourite, isPending, ensureLoaded, toggle } = useWishlist()
const wishlisted = computed(() => isFavourite(spuPublicId.value))
const wishPending = computed(() => isPending(spuPublicId.value))

onMounted(() => {
  ensureLoaded()
})

function toggleWishlist() {
  return toggle(spuPublicId.value)
}
</script>

<template>
  <article class="product-card">
    <span v-if="props.rank > 0" class="product-card__rank">{{ props.rank }}</span>
    <button
      class="product-card__wish"
      :class="{ 'product-card__wish--active': wishlisted }"
      type="button"
      :aria-label="wishlisted ? t('product.removeFromWishlist') : t('product.addToWishlist')"
      :aria-pressed="wishlisted"
      :disabled="wishPending"
      @click.stop.prevent="toggleWishlist"
    >
      <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
        <path
          d="M12 20.3 4.8 13a4.9 4.9 0 0 1 0-7 4.9 4.9 0 0 1 7 0l.2.2.2-.2a4.9 4.9 0 0 1 7 0 4.9 4.9 0 0 1 0 7L12 20.3Z"
          :fill="wishlisted ? 'currentColor' : 'none'"
          stroke="currentColor"
          stroke-width="1.6"
        />
      </svg>
    </button>
    <NuxtLink class="product-card__media" :to="href" tabindex="-1" aria-hidden="true">
      <img v-if="image" :src="image" alt="" loading="lazy" />
      <BaseSkeleton v-else variant="block" />
    </NuxtLink>
    <div class="product-card__body">
      <p v-if="props.showBrand && brand" class="product-card__brand">{{ brand }}</p>
      <h3 class="product-card__title">
        <NuxtLink class="product-card__title-link" :to="href">{{ props.product.title }}</NuxtLink>
      </h3>
      <p v-if="viewed" class="product-card__viewed">{{ viewed }}</p>
      <div v-if="showRatingStars || showSold" class="product-card__rating-row">
        <span v-if="showRatingStars" class="product-card__star" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="12" height="12">
            <path
              d="M12 2.6l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.5l-5.9 3.1 1.2-6.5L2.5 9.5l6.6-.9z"
              fill="currentColor"
            />
          </svg>
        </span>
        <span v-if="showRatingStars" class="product-card__rating-value">{{
          ratingValue.toFixed(1)
        }}</span>
        <span
          v-if="showRatingStars && showSold"
          class="product-card__rating-divider"
          aria-hidden="true"
        ></span>
        <span v-if="showSold" class="product-card__sold">{{
          t('product.soldCount', { n: soldAmount })
        }}</span>
      </div>
      <div class="product-card__footer">
        <p
          v-if="price"
          class="product-card__price"
          :class="{ 'product-card__price--discount': Boolean(originalPrice) }"
        >
          {{ price }}
          <s v-if="originalPrice" class="product-card__price-original">{{ originalPrice }}</s>
        </p>
        <span v-if="badge" class="product-card__badge">{{ badge }}</span>
      </div>
      <div v-if="showSelfOperated" class="product-card__self-operated">
        <span class="product-card__self-operated-left">
          <img
            class="product-card__self-operated-icon"
            src="/images/icons/sold-by-joybuy.png"
            alt=""
            loading="lazy"
          />
          <span>{{ t('product.soldByJoybuy') }}</span>
        </span>
        <NuxtLink class="product-card__add" :to="href" :aria-label="t('detail.addToCart')">
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
            <path d="M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6V5Z" fill="currentColor" />
          </svg>
        </NuxtLink>
      </div>
    </div>
  </article>
</template>

<style scoped>
/* Card: white, 12px radius; the image sits flush at the top and the text
 * block is inset by the real site's 6px. */
.product-card {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  border-radius: 12px;
  background: var(--colour-surface);
  overflow: hidden;
}

.product-card__rank {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px 0;
  background: #e4e6eb;
  color: var(--colour-text);
  font-size: 1.125rem;
  font-weight: var(--font-weight-regular);
}

.product-card__wish {
  position: absolute;
  top: var(--space-2);
  right: var(--space-2);
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--colour-text-secondary);
  cursor: pointer;
}

.product-card__wish:hover {
  background: var(--colour-hover);
}

.product-card__wish--active {
  color: var(--colour-accent);
}

.product-card__wish:disabled {
  cursor: progress;
  opacity: 0.65;
}

.product-card__media {
  display: block;
  flex-shrink: 0;
}

/* Image area bg #F5F5F5; multiply blend turns baked-in white backgrounds
 * into the same grey while transparent images show it through directly. */
.product-card__media {
  /* The grey area itself must be rounded on all four corners (the img is
   * rounded too, so no square grey corners peek out anywhere). */
  background: #f5f5f5;
  border-radius: 12px;
}

.product-card__media img,
.product-card__media :deep(*) {
  display: block;
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  /* Real card: the image carries its own 12px radius on all four corners. */
  border-radius: 12px;
  mix-blend-mode: multiply;
}

.product-card__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-2) 6px 6px;
  flex: 1;
}

.product-card__brand {
  margin: 0;
  overflow: visible;

  white-space: normal;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-bold);
  color: var(--colour-text);
  word-break: break-word;
}

/* Two-line clamp with ellipsis (real card: 16px/500, 22px line height).
 * 标题最多 2 行、超出用省略号（DOM 里保留全文，只做视觉截断）；min-height
 * 44 = 2×22，让 1 行标题的卡片与 2 行卡等高、网格不错位。 */
.product-card__title {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  min-height: 44px;
  margin: 0;
  font-size: 16px;
  font-weight: var(--font-weight-medium);
  line-height: 22px;
  color: #1a1a1a;
  word-break: break-word;
}

.product-card__title-link {
  text-decoration: none;
  color: inherit;
}

.product-card__viewed {
  margin: 0;
  color: var(--colour-muted);
  font-size: 13px;
}

/* 评分 | 已售行（真站 starRating 实测 2026-11-27）：黑色单星 + 数值 + 灰色竖线
 * + 已售，全行 14px / 行高 20 / #1A1A1A。 */
.product-card__rating-row {
  display: flex;
  align-items: center;
  gap: 4px;
  min-height: 20px;
  margin-top: 2px;
  color: var(--colour-text, #1a1a1a);
  font-size: 14px;
  line-height: 20px;
}

.product-card__star {
  display: inline-flex;
  color: var(--colour-text, #1a1a1a);
}

.product-card__rating-value {
  font-weight: var(--font-weight-medium, 500);
}

/* 评分与已售之间的灰色竖线（真站为分隔 SVG，这里用等价细线）。 */
.product-card__rating-divider {
  width: 1px;
  height: 12px;
  margin: 0 4px;
  background: var(--colour-border, #d5d5d5);
}

.product-card__sold {
  color: var(--colour-text, #1a1a1a);
}

/* 自营行（真站 marketingLabel 实测）：18px 品牌图标 + 14px/500 文本，
 * 【+】加购按钮移到本行右端（原在价格行右侧，2026-11-27 用户口径）。 */
.product-card__self-operated {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  margin-top: 4px;
  color: var(--colour-text, #1a1a1a);
  font-size: 14px;
  font-weight: var(--font-weight-medium, 500);
}

.product-card__self-operated-left {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.product-card__self-operated-icon {
  width: 18px;
  height: 18px;
  object-fit: contain;
  flex-shrink: 0;
}

.product-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  margin-top: auto;
  padding-top: var(--space-2);
}

.product-card__price {
  color: #1a1a1a;
  font-size: 1.125rem;
  font-weight: var(--font-weight-bold);
}

/* 折扣卡：现价红、原价划线（真站 18/700/24 + 14/500/20 line-through）。 */
.product-card__price--discount {
  color: #e1251b;
}

.product-card__price-original {
  margin-left: 6px;
  font-size: 14px;
  font-weight: 500;
  line-height: 20px;
  color: var(--colour-text-secondary);
}

.product-card__badge {
  padding: 0 var(--space-2);
  border-radius: var(--radius-pill);
  background: var(--colour-surface-muted);
  color: var(--colour-text-secondary);
  font-size: var(--font-size-xs);
}

.product-card__add {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--colour-surface-soft);
  color: var(--colour-text);
}

.product-card__add:hover {
  background: var(--colour-hover);
}
</style>
