<script setup>
import { computed } from 'vue'

import { formatDisplayPrice, isDeliveryLabel } from '../utils/display'

// Shared product card aligned to the joybuy.co.uk card spec (sampled from
// the Bestsellers floor, 2026-11-04): white 12px-radius card, full-width
// square image, 6px text inset, brand in bold, a two-line 16px/500 title
// clamped with an ellipsis, red price on the left with a 40px round add
// button on the right. Bestseller mode (`rank` > 0) shows the positional
// badge and hides the rating stars like the real floor; marketing labels
// never render (requirement 5-6). An optional `viewed_count` on the product
// renders the real floor's "viewed in 72 hours" line when data exists.
const props = defineProps({
  product: {
    type: Object,
    required: true,
  },
  rank: {
    type: Number,
    default: 0,
  },
})

const price = computed(() => formatDisplayPrice(props.product.price_min ?? props.product.price))

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

const badge = computed(() => {
  // Marketing labels (新客福利/优惠x%/送达/满减/自营) never render (req 5-6);
  // delivery-estimate labels are suppressed by the display rule too.
  return props.product.badge && !isDeliveryLabel(props.product.badge) ? props.product.badge : ''
})
</script>

<template>
  <article class="product-card">
    <span v-if="props.rank > 0" class="product-card__rank">{{ props.rank }}</span>
    <button class="product-card__wish" type="button" aria-label="Add to wishlist">
      <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
        <path
          d="M12 20.3 4.8 13a4.9 4.9 0 0 1 0-7 4.9 4.9 0 0 1 7 0l.2.2.2-.2a4.9 4.9 0 0 1 7 0 4.9 4.9 0 0 1 0 7L12 20.3Z"
          fill="none"
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
      <p v-if="brand" class="product-card__brand">{{ brand }}</p>
      <h3 class="product-card__title">
        <NuxtLink class="product-card__title-link" :to="href">{{ props.product.title }}</NuxtLink>
      </h3>
      <p v-if="viewed" class="product-card__viewed">{{ viewed }}</p>
      <BaseRatingStars
        v-if="props.rank === 0 && (props.product.rating || props.product.rating_average)"
        :rating="Number(props.product.rating_average ?? props.product.rating ?? 0)"
        :count="Number(props.product.review_count ?? 0)"
        show-count
      />
      <div class="product-card__footer">
        <p v-if="price" class="product-card__price">{{ price }}</p>
        <span v-if="badge" class="product-card__badge">{{ badge }}</span>
        <NuxtLink class="product-card__add" :to="href" aria-label="Add to cart">
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

.product-card__media {
  display: block;
  flex-shrink: 0;
}

/* Image area bg #F5F5F5; multiply blend turns baked-in white backgrounds
 * into the same grey while transparent images show it through directly. */
.product-card__media {
  background: #f5f5f5;
}

.product-card__media img,
.product-card__media :deep(*) {
  display: block;
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: 0;
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
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-bold);
  color: var(--colour-text);
}

/* Two-line clamp with ellipsis (real card: 16px/500, 22px line height). */
.product-card__title {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 44px;
  margin: 0;
  font-size: 16px;
  font-weight: var(--font-weight-medium);
  line-height: 22px;
  color: #1a1a1a;
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
