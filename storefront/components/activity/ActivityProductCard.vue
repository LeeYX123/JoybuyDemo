<script setup>
// 活动页/店铺页商品卡（2026-11-25）。按真站实测规格复刻：
// 卡宽 225（图 209 + 8px 内边距）、圆角 12、图圆角 8、标题 14/500 两行截断、
// 价格 18/700 #E1251B。整卡可点进我们的商品详情页（/p/<public_id>）。
defineProps({
  product: {
    type: Object,
    required: true,
  },
})

function priceLabel(product) {
  if (!product?.price) return ''
  const symbol = product.currency === 'GBP' ? '£' : ''
  const value = String(product.price)
  const [integer, decimals] = value.split('.')
  const minor = decimals === undefined ? '00' : decimals.padEnd(2, '0').slice(0, 2)
  return `${symbol}${integer}.${minor}`
}
</script>

<template>
  <NuxtLink class="activity-card" :to="product.href">
    <span class="activity-card__media">
      <img v-if="product.image_path" :src="product.image_path" :alt="product.title" loading="lazy" />
    </span>
    <span class="activity-card__title">{{ product.title }}</span>
    <span v-if="priceLabel(product)" class="activity-card__price">{{ priceLabel(product) }}</span>
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
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 40px;
}

.activity-card__price {
  margin-top: 8px;
  font-size: 18px;
  font-weight: 700;
  line-height: 24px;
  color: #e1251b;
}
</style>
