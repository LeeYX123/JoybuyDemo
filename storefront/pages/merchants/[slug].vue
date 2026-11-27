<script setup>
// 商家主页（WP-42）：顶部商家头像/名称 + 右侧总关注/总曝光度，
// 下方为该商家当前上架的全部商品，可直接购买。
import { useLocale } from '../../composables/useLocale'
import { useBuyerAuth } from '../../composables/useBuyerAuth'
import { formatDisplayPrice } from '../../utils/display'
const route = useRoute()
const { t } = useLocale()

const slug = computed(() => String(route.params.slug || ''))

// 需求 19.1：只有「已登录 + 白名单买家」才渲染【联系商家】入口；
// 服务端仍会 403 兜底，面板收到 NOT_WHITELISTED 后回传 blocked 隐藏入口。
const { isAuthenticated, purchaseWhitelisted } = useBuyerAuth()
const chatOpen = ref(false)
const chatBlocked = ref(false)
const canContactSeller = computed(
  () => isAuthenticated.value && purchaseWhitelisted.value && !chatBlocked.value,
)
const chatMerchant = computed(() => ({
  slug: slug.value,
  display_name: merchant.value?.name || '',
  avatar_url: merchant.value?.avatar || '',
}))

function onChatBlocked() {
  chatBlocked.value = true
  chatOpen.value = false
}

// SSR 直连后端（apiBaseInternal），客户端走 devProxy（与 useSearch 同一模式）。
const config = useRuntimeConfig()
const detailUrl = computed(() =>
  import.meta.server
    ? `${config.apiBaseInternal}/merchants/${slug.value}`
    : `/api/v1/merchants/${slug.value}`,
)

const { data, status, error } = await useFetch(detailUrl, { key: `merchant-${slug.value}` })

const merchant = computed(() => data.value?.merchant || null)
const products = computed(() => merchant.value?.products || [])

useHead(() => ({
  title: merchant.value?.name
    ? `${merchant.value.name} · ${t('merchant.shopTitle')}`
    : t('merchant.shopTitle'),
}))
</script>

<template>
  <div class="shop-page">
    <div class="shop-page__inner">
      <p v-if="status === 'pending'" class="shop-page__hint">{{ t('common.loading') }}</p>
      <p v-else-if="error || !merchant" class="shop-page__hint">{{ t('merchant.notFound') }}</p>

      <template v-else>
        <header class="shop-header">
          <span class="shop-header__avatar">
            <img v-if="merchant.avatar" :src="merchant.avatar" :alt="merchant.name" />
            <template v-else>{{ merchant.name.slice(0, 1) }}</template>
          </span>
          <div class="shop-header__info">
            <h1>{{ merchant.name }}</h1>
            <p>{{ t('merchant.shopSubtitle') }}</p>
          </div>
          <dl class="shop-header__metrics">
            <div>
              <dt>{{ t('merchant.followers') }}</dt>
              <dd>{{ merchant.followers_total }}</dd>
            </div>
            <div>
              <dt>{{ t('merchant.exposure') }}</dt>
              <dd>{{ merchant.exposure_total }}</dd>
            </div>
          </dl>
          <button
            v-if="canContactSeller"
            class="shop-contact"
            type="button"
            data-testid="contact-seller"
            @click="chatOpen = true"
          >
            <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true">
              <path
                d="M3 4.5h14v9H8.5L5 16.5v-3H3z"
                fill="none"
                stroke="currentColor"
                stroke-width="1.4"
                stroke-linejoin="round"
              />
            </svg>
            {{ t('chat.contactSeller') }}
          </button>
        </header>

        <h2 class="shop-products__title">{{ t('merchant.productsTitle') }}</h2>
        <p v-if="!products.length" class="shop-page__hint">{{ t('merchant.noProducts') }}</p>
        <div v-else class="shop-products">
          <NuxtLink
            v-for="product in products"
            :key="product.offer_id"
            :to="`/p/${product.product_id}?offer=${product.offer_id}&from=merchant`"
            class="shop-product-card"
          >
            <span class="shop-product-card__media">
              <img v-if="product.image" :src="product.image" :alt="product.name" />
              <template v-else>···</template>
            </span>
            <span class="shop-product-card__name">{{ product.name }}</span>
            <span
              v-if="Number(product.rating_average) > 0 || product.sold_amount"
              class="shop-product-card__meta"
            >
              <span v-if="Number(product.rating_average) > 0" class="shop-product-card__rating">
                ★ {{ Number(product.rating_average).toFixed(1) }}
              </span>
              <span v-if="product.sold_amount" class="shop-product-card__sold">
                {{ t('product.soldCount', { n: product.sold_amount }) }}
              </span>
            </span>
            <b class="shop-product-card__price-row">
              <span class="shop-product-card__price">{{ formatDisplayPrice(product.price) }}</span>
              <!-- 商家页加购在价格右侧（真站商家店铺页口径，2026-11-27）；整卡仍可点进详情。 -->
              <span class="shop-product-card__add" :aria-label="t('detail.addToCart')">
                <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
                  <path d="M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6V5Z" fill="currentColor" />
                </svg>
              </span>
            </b>
          </NuxtLink>
        </div>
      </template>
    </div>

    <MerchantChatPanel
      :open="chatOpen"
      :merchant="chatMerchant"
      @close="chatOpen = false"
      @blocked="onChatBlocked"
    />
  </div>
</template>

<style scoped>
.shop-page {
  padding: 24px 0 48px;
}

.shop-page__inner {
  max-width: 1080px;
  margin: 0 auto;
  padding: 0 16px;
}

.shop-page__hint {
  color: #707070;
  font-size: 14px;
}

.shop-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  padding: 20px;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: #fff;
}

.shop-header__avatar {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  overflow: hidden;
  background: #f2f3f5;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  font-weight: 600;
  flex: none;
}

.shop-header__avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.shop-header__info {
  flex: 1;
}

.shop-header__info h1 {
  font-size: 20px;
  margin: 0 0 4px;
}

.shop-header__info p {
  margin: 0;
  font-size: 13px;
  color: #707070;
}

.shop-header__metrics {
  display: flex;
  gap: 28px;
  margin: 0;
}

.shop-header__metrics dt {
  font-size: 12px;
  color: #707070;
}

.shop-header__metrics dd {
  margin: 2px 0 0;
  font-size: 20px;
  font-weight: 700;
}

/* 需求 19.5：【联系商家】入口与店铺头同排，次要按钮样式（描边红字）。 */
.shop-contact {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: none;
  height: 40px;
  margin-left: auto;
  padding: 0 16px;
  border: 1px solid var(--colour-accent);
  border-radius: 4px;
  background: var(--colour-surface);
  color: var(--colour-accent);
  font: inherit;
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
}

.shop-contact:hover {
  background: var(--colour-accent-soft);
}

.shop-contact:focus-visible {
  outline: 2px solid var(--colour-focus-ring);
  outline-offset: 2px;
}

@media (max-width: 40rem) {
  .shop-header__metrics {
    gap: 20px;
  }

  .shop-contact {
    margin-left: 0;
  }
}

.shop-products__title {
  font-size: 16px;
  margin: 24px 0 12px;
}

.shop-products {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 14px;
}

.shop-product-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  border: 1px solid #ececec;
  border-radius: 10px;
  background: #fff;
  text-decoration: none;
  color: inherit;
}

.shop-product-card:hover {
  border-color: #e1251b;
}

.shop-product-card__media {
  aspect-ratio: 1;
  border-radius: 8px;
  overflow: hidden;
  background: #f7f7f7;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #b0b0b0;
}

.shop-product-card__media img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.shop-product-card__name {
  font-size: 13px;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 评分 | 已售行（ADR-0003）：商家页只显示此行，不显示自营徽标。 */
.shop-product-card__meta {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 18px;
  font-size: 12px;
  color: #1a1a1a;
}

.shop-product-card__sold {
  color: #666;
}

.shop-product-card__price-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: auto;
}

.shop-product-card__price {
  color: #e1251b;
  font-size: 15px;
}

/* 商家页加购按钮：价格行右端（真站商家店铺页口径）。 */
.shop-product-card__add {
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
