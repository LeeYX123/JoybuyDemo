<script setup>
// 活动页/店铺页商品卡（2026-11-25）。按真站实测规格复刻：
// 卡宽 225（图 209 + 8px 内边距）、圆角 12、图圆角 8、标题 14/500 两行截断、
// 价格 18/700 #E1251B。整卡可点进我们的商品详情页（/p/<public_id>）。
// 2026-11-27（ADR-0003）：与列表卡同口径——评分行（黑星+数值|灰线|已售）、
// 「Sold by Joybuy」自营行（18px 品牌图标）+ 行右端【+】加购按钮。
import { computed } from 'vue'

import { useLocale } from '../../composables/useLocale'

const props = defineProps({
  product: {
    type: Object,
    required: true,
  },
})

const { t } = useLocale()

function priceLabel(product) {
  if (!product?.price) return ''
  const symbol = '$'
  const value = String(product.price)
  const [integer, decimals] = value.split('.')
  const minor = decimals === undefined ? '00' : decimals.padEnd(2, '0').slice(0, 2)
  return `${symbol}${integer}.${minor}`
}

const ratingValue = computed(() => Number(props.product.rating_average ?? 0))
const showRating = computed(() => ratingValue.value > 0)
const soldAmount = computed(() => {
  const raw = props.product.sold_amount
  return typeof raw === 'string' && raw.trim() ? raw.trim() : ''
})
const showSold = computed(() => Boolean(soldAmount.value))
</script>

<template>
  <NuxtLink class="activity-card" :to="product.href">
    <span class="activity-card__media">
      <img
        v-if="product.image_path"
        :src="product.image_path"
        :alt="product.title"
        loading="lazy"
      />
    </span>
    <span class="activity-card__title">{{ product.title }}</span>
    <span v-if="showRating || showSold" class="activity-card__rating-row">
      <span v-if="showRating" class="activity-card__star" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="12" height="12">
          <path
            d="M12 2.6l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.5l-5.9 3.1 1.2-6.5L2.5 9.5l6.6-.9z"
            fill="currentColor"
          />
        </svg>
      </span>
      <span v-if="showRating" class="activity-card__rating-value">{{
        ratingValue.toFixed(1)
      }}</span>
      <span
        v-if="showRating && showSold"
        class="activity-card__rating-divider"
        aria-hidden="true"
      ></span>
      <span v-if="showSold" class="activity-card__sold">{{
        t('product.soldCount', { n: soldAmount })
      }}</span>
    </span>
    <span v-if="priceLabel(product)" class="activity-card__price">{{ priceLabel(product) }}</span>
    <span class="activity-card__self-operated">
      <span class="activity-card__self-operated-left">
        <img
          class="activity-card__self-operated-icon"
          src="/images/icons/sold-by-joybuy.png"
          alt=""
          loading="lazy"
        />
        <span>{{ t('product.soldByJoybuy') }}</span>
      </span>
      <span class="activity-card__add" :aria-label="t('detail.addToCart')">
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path d="M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6V5Z" fill="currentColor" />
        </svg>
      </span>
    </span>
  </NuxtLink>
</template>

<style scoped>
.activity-card {
  display: flex;
  flex-direction: column;
  width: 100%;
  padding: 8px;
  background: #fff;
  border-radius: 12px;
  color: inherit;
  text-decoration: none;
}

.activity-card:hover .activity-card__title {
  text-decoration: underline;
}

.activity-card__media {
  display: block;
  width: 100%;
  aspect-ratio: 1;
  border-radius: 8px;
  overflow: hidden;
  /* 真站商品图区灰底 #f5f5f5；我们的主图是白底 JPG（真站用透明底图），
     用 multiply 混合让白底「融进」灰底，产品本身几乎不变色。 */
  background: #f5f5f5;
}

.activity-card__media img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  mix-blend-mode: multiply;
}

.activity-card__title {
  margin-top: 10px;
  font-size: 14px;
  font-weight: 500;
  line-height: 20px;
  color: #1a1a1a;
  /* 标题最多 2 行，超出省略号（min-height 40 = 2×20 保持卡片等高）。 */
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  min-height: 40px;
  word-break: break-word;
}

/* 评分行：与列表卡同口径（真站 starRating 14px/行高20）。 */
.activity-card__rating-row {
  display: flex;
  align-items: center;
  gap: 4px;
  min-height: 20px;
  margin-top: 4px;
  color: #1a1a1a;
  font-size: 14px;
  line-height: 20px;
}

.activity-card__star {
  display: inline-flex;
}

.activity-card__rating-value {
  font-weight: 500;
}

.activity-card__rating-divider {
  width: 1px;
  height: 12px;
  margin: 0 4px;
  background: #d5d5d5;
}

.activity-card__price {
  margin-top: 6px;
  font-size: 18px;
  font-weight: 700;
  line-height: 24px;
  color: #e1251b;
}

/* 自营行：18px 品牌图标 + 文本，行右端【+】加购（与列表卡同口径）。 */
.activity-card__self-operated {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 2px;
  color: #1a1a1a;
  font-size: 14px;
  font-weight: 500;
}

.activity-card__self-operated-left {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.activity-card__self-operated-icon {
  width: 18px;
  height: 18px;
  object-fit: contain;
  flex-shrink: 0;
}

.activity-card__add {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  border-radius: 50%;
  background: #f5f5f5;
  color: #1a1a1a;
}
</style>
