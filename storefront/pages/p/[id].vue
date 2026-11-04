<script setup>
import { computed, ref } from 'vue'
import { useFetch, useRuntimeConfig } from '#imports'

import { useBuyerAuth } from '../../composables/useBuyerAuth'
import { useCategoryTree } from '../../composables/useCategoryTree'
import { useCart } from '../../composables/useCart'
import { useLocale } from '../../composables/useLocale'
import { formatDisplayPrice, isDeliveryLabel } from '../../utils/display'

// Product detail aligned to docs/12 §6: breadcrumb row, full-width 24px/700
// title, thumb rail + 591px-class main image + buy panel (Buy now / Add to
// cart / quantity stepper / plain service-guarantee rows). Purchase actions
// are gated by the account whitelist flag (requirement 6-6).
const route = useRoute()
const { t, categoryName } = useLocale()

const publicId = computed(() => String(route.params.id || ''))
const config = useRuntimeConfig()

const { data, error } = await useFetch(
  () =>
    import.meta.server
      ? `${config.apiBaseInternal}/products/${publicId.value}`
      : `/api/v1/products/${publicId.value}`,
  { key: `product-${publicId.value}` },
)

const { isAuthenticated, account } = useBuyerAuth()

const selectedSkuId = ref(null)
const quantity = ref(1)

const { addItem } = await useCart()
const addState = ref('idle') // idle | adding | added | error

// Purchase gate (requirement 6-6): non-whitelisted accounts get the blocking
// popup for both actions; whitelisted accounts buy normally.
const showGatePopup = ref(false)

const isWhitelisted = computed(() => {
  if (!isAuthenticated.value) return false
  return account.value?.purchase_whitelisted !== false
})

function gateBlocked() {
  return !isWhitelisted.value
}

function onBuyNow() {
  if (gateBlocked()) {
    showGatePopup.value = true
    return
  }
  // Direct to the checkout address step (requirement 6-7: no confirm popup).
  navigateTo('/checkout')
}

async function onAddToCart() {
  if (gateBlocked()) {
    showGatePopup.value = true
    return
  }
  if (!offer.value?.is_purchasable) return
  addState.value = 'adding'
  const response = await addItem(offer.value.public_id, quantity.value)
  addState.value = response?.error ? 'error' : 'added'
  setTimeout(() => {
    addState.value = 'idle'
  }, 2000)
}

const skus = computed(() => (Array.isArray(data.value?.skus) ? data.value.skus : []))
const purchasableSkus = computed(() => skus.value.filter((sku) => sku.offer))
const selectedSku = computed(() => {
  const initial = purchasableSkus.value.find((sku) => sku.public_id === selectedSkuId.value)
  return initial || purchasableSkus.value[0] || null
})

const offer = computed(() => selectedSku.value?.offer || null)
// Business rule: one original price only — no strikethrough list price.
const price = computed(() => (offer.value ? formatDisplayPrice(offer.value.price) : null))

const variantAxes = computed(() => {
  const axes = new Map()
  for (const sku of purchasableSkus.value) {
    for (const [key, value] of Object.entries(sku.specification || {})) {
      if (!axes.has(key)) axes.set(key, new Set())
      axes.get(key).add(String(value))
    }
  }
  return [...axes.entries()].map(([name, values]) => ({ name, values: [...values] }))
})

function selectVariant(axisName, value) {
  for (const sku of purchasableSkus.value) {
    if (String(sku.specification?.[axisName]) === value) {
      selectedSkuId.value = sku.public_id
      return
    }
  }
}

const gallery = computed(() => (Array.isArray(data.value?.gallery) ? data.value.gallery : []))
const activeImage = ref('')
const currentImage = computed(() => activeImage.value || gallery.value[0]?.url || '')

// Breadcrumb from the shared category tree: root -> child -> product title
// (the API returns the product's own category slug; every level links to its
// listing page like the real top nav).
const { categories } = useCategoryTree()
const categoryTrail = computed(() => {
  const slug = data.value?.category_slug
  if (!slug) return []
  for (const root of categories.value) {
    if (root.slug === slug) return [root]
    for (const child of root.children || []) {
      if (child.slug === slug) return [root, child]
    }
  }
  return []
})

// Hover zoom: the real site shows an enlarged detail view to the right of
// the main image while the cursor moves over it.
const zoomVisible = ref(false)
const zoomPos = ref({ x: 50, y: 50 })

function onZoomMove(event) {
  const rect = event.currentTarget.getBoundingClientRect()
  zoomPos.value = {
    x: Math.min(100, Math.max(0, ((event.clientX - rect.left) / rect.width) * 100)),
    y: Math.min(100, Math.max(0, ((event.clientY - rect.top) / rect.height) * 100)),
  }
}

// Service guarantees: plain text rows, no accordion (requirement 6-4).
const guarantees = computed(() => [
  t('detail.guaranteeReturns'),
  t('detail.guaranteeWarranty'),
  t('detail.guaranteeSupport'),
])

function changeQuantity(delta) {
  quantity.value = Math.max(1, Math.min(99, quantity.value + delta))
}

useHead(() => ({ title: data.value?.title || 'Product' }))
</script>

<template>
  <AppContainer>
    <div v-if="error" class="detail-state" role="alert">
      <p>This product is not available.</p>
      <NuxtLink to="/">Continue shopping</NuxtLink>
    </div>

    <section v-else class="detail">
      <!-- Clickable top nav: Home / root category / child category / product
           (real-site breadcrumb, 16px, dark). -->
      <nav class="detail__crumbs" aria-label="Breadcrumb">
        <NuxtLink class="detail__crumb" to="/">Home</NuxtLink>
        <template v-for="node in categoryTrail" :key="node.slug">
          <span class="detail__crumb-sep" aria-hidden="true">/</span>
          <NuxtLink class="detail__crumb" :to="`/c/${node.slug}`">{{
            categoryName(node)
          }}</NuxtLink>
        </template>
        <span class="detail__crumb-sep" aria-hidden="true">/</span>
        <span class="detail__crumb detail__crumb--current">{{ data?.title }}</span>
      </nav>
      <p v-if="data?.brand" class="detail__brandline">{{ data.brand }}</p>
      <h1 class="detail__title">{{ data?.title }}</h1>

      <div class="detail__main">
        <div class="detail__thumbs">
          <button
            v-for="(asset, index) in gallery"
            :key="asset.url"
            type="button"
            class="detail__thumb"
            :class="{ 'detail__thumb--active': currentImage === asset.url }"
            @click="activeImage = asset.url"
          >
            <img :src="asset.url" :alt="`${data?.title} thumbnail ${index + 1}`" />
          </button>
        </div>

        <div
          class="detail__image"
          @mouseenter="zoomVisible = true"
          @mousemove="onZoomMove"
          @mouseleave="zoomVisible = false"
        >
          <img v-if="currentImage" :src="currentImage" :alt="data?.title" />
          <BaseSkeleton v-else variant="block" class="detail__image-placeholder" />
          <!-- Enlarged detail view shown to the right of the main image on
               hover (real-site magnifier). -->
          <div
            v-if="zoomVisible && currentImage"
            class="detail__zoom"
            :style="{
              backgroundImage: `url(${currentImage})`,
              backgroundPosition: `${zoomPos.x}% ${zoomPos.y}%`,
            }"
            aria-hidden="true"
          ></div>
        </div>

        <div class="detail__panel">
          <div v-if="offer" class="detail__price-block">
            <p class="detail__price">{{ price }}</p>
            <BaseBadge
              v-if="offer.promotion_label && !isDeliveryLabel(offer.promotion_label)"
              tone="promo"
            >
              {{ offer.promotion_label }}
            </BaseBadge>
          </div>
          <p v-if="offer" class="detail__inventory">{{ offer.inventory_display }} in stock</p>
          <p v-else class="detail__inventory detail__inventory--out" role="status">
            Currently unavailable
          </p>

          <div v-for="axis in variantAxes" :key="axis.name" class="detail__axis">
            <h2 class="detail__axis-name">{{ axis.name }}</h2>
            <div class="detail__axis-values">
              <button
                v-for="value in axis.values"
                :key="value"
                type="button"
                class="detail__variant"
                :class="{
                  'detail__variant--active':
                    String(selectedSku?.specification?.[axis.name]) === value,
                }"
                @click="selectVariant(axis.name, value)"
              >
                {{ value }}
              </button>
            </div>
          </div>

          <div class="detail__quantity">
            <span class="detail__quantity-label">Quantity</span>
            <div class="detail__stepper">
              <button type="button" aria-label="Decrease quantity" @click="changeQuantity(-1)">
                −
              </button>
              <span class="detail__stepper-value" aria-live="polite">{{ quantity }}</span>
              <button type="button" aria-label="Increase quantity" @click="changeQuantity(1)">
                +
              </button>
            </div>
          </div>

          <div class="detail__actions">
            <button class="detail__buy" type="button" :disabled="!offer" @click="onBuyNow">
              Buy now
            </button>
            <button
              class="detail__add"
              type="button"
              :disabled="!offer?.is_purchasable || addState === 'adding'"
              @click="onAddToCart"
            >
              {{
                addState === 'added'
                  ? 'Added to cart'
                  : addState === 'error'
                    ? 'Could not add'
                    : 'Add to cart'
              }}
            </button>
          </div>

          <ul class="detail__guarantees">
            <li v-for="line in guarantees" :key="line">{{ line }}</li>
          </ul>
        </div>
      </div>
    </section>

    <ProductReviews v-if="publicId && data" :product-id="publicId" />

    <section v-if="data?.description" class="detail__description" aria-labelledby="detail-heading">
      <h2 id="detail-heading">Product details</h2>
      <p>{{ data.description }}</p>
    </section>

    <!-- Purchase gate popup (requirement 6-6): non-whitelisted accounts. -->
    <Teleport to="body">
      <div v-if="showGatePopup" class="gate-popup" role="dialog" aria-modal="true">
        <div class="gate-popup__backdrop" @click="showGatePopup = false"></div>
        <div class="gate-popup__card">
          <p class="gate-popup__text">{{ t('gate.message') }}</p>
          <button class="gate-popup__ok" type="button" @click="showGatePopup = false">
            {{ t('gate.confirm') }}
          </button>
        </div>
      </div>
    </Teleport>
  </AppContainer>
</template>

<style scoped>
.detail {
  margin-block: var(--space-4);
}

/* Top nav: Home / categories / product, clickable like the real site. */
.detail__crumbs {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 24px;
  overflow: hidden;
  white-space: nowrap;
  font-size: var(--font-size-md);
  color: #1a1a1a;
}

.detail__crumb {
  color: #1a1a1a;
  text-decoration: none;
}

.detail__crumb:hover {
  text-decoration: underline;
}

.detail__crumb--current {
  cursor: default;
}

.detail__crumb-sep {
  color: var(--colour-muted);
}

.detail__brandline {
  margin: 0;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  color: #1a1a1a;
}

/* Full-width 24px/700 title (docs/12 §6 baseline). */
.detail__title {
  margin: var(--space-2) 0 var(--space-4);
  font-size: 1.5rem;
  font-weight: var(--font-weight-bold);
  line-height: var(--line-height-tight);
}

/* Real layout: 56px thumb rail, fluid main image, 671px buy panel. */
.detail__main {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr) 671px;
  gap: var(--space-4);
  align-items: start;
}

.detail__thumbs {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.detail__thumb {
  width: 56px;
  height: 56px;
  padding: 0;
  border: 1px solid var(--colour-border);
  border-radius: 4px;
  background: var(--colour-surface);
  cursor: pointer;
  overflow: hidden;
}

.detail__thumb--active {
  border-color: var(--colour-text);
}

.detail__thumb img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.detail__image {
  position: relative;
}

.detail__image img {
  display: block;
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  background: var(--colour-surface-soft);
}

/* Enlarged hover view: 2.5x detail panel floated over the buy panel side. */
.detail__zoom {
  position: absolute;
  top: 0;
  left: calc(100% + 16px);
  width: 100%;
  aspect-ratio: 1;
  z-index: 20;
  border: 1px solid var(--colour-border);
  border-radius: 8px;
  background-color: #f5f5f5;
  background-repeat: no-repeat;
  background-size: 250%;
  pointer-events: none;
  box-shadow: var(--shadow-overlay);
}

.detail__image-placeholder {
  aspect-ratio: 1;
}

/* Buy panel: price, variants, stepper, dual CTA, guarantee rows. */
.detail__panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  box-shadow: rgb(0 0 0 / 4%) 0 2px 12px 0;
}

.detail__price-block {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
}

.detail__price {
  color: var(--colour-accent);
  font-size: var(--font-size-3xl);
  font-weight: var(--font-weight-bold);
}

.detail__inventory {
  color: var(--colour-success);
  font-weight: var(--font-weight-semibold);
}

.detail__inventory--out {
  color: var(--colour-error);
}

.detail__axis-name {
  font-size: var(--font-size-sm);
  text-transform: capitalize;
  color: var(--colour-muted);
}

.detail__axis-values {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-2);
}

.detail__variant {
  min-height: 44px;
  padding: 0 var(--space-4);
  border: 1px solid var(--colour-border-strong);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  cursor: pointer;
  font: inherit;
}

.detail__variant--active {
  border-color: var(--colour-accent);
  color: var(--colour-accent);
  background: var(--colour-accent-soft);
  font-weight: var(--font-weight-semibold);
}

.detail__quantity {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.detail__quantity-label {
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}

.detail__stepper {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.detail__stepper button {
  width: 34px;
  height: 34px;
  border: 0;
  background: var(--colour-surface-soft);
  cursor: pointer;
  font-size: 1rem;
}

.detail__stepper button:hover {
  background: var(--colour-hover);
}

.detail__stepper-value {
  min-width: 47px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-bold);
}

.detail__actions {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-2);
}

/* Buy now / Add to cart: 48px, radius 4, real hover shades (#D14335/#282828). */
.detail__buy,
.detail__add {
  flex: 1;
  min-height: 48px;
  border: 0;
  border-radius: 4px;
  color: var(--colour-white);
  font-size: 1.125rem;
  font-weight: var(--font-weight-bold);
  cursor: pointer;
}

.detail__buy {
  background: #e1251b;
}

.detail__buy:hover:not(:disabled) {
  background: #d14335;
}

.detail__add {
  background: #1a1a1a;
}

.detail__add:hover:not(:disabled) {
  background: #282828;
}

.detail__buy:disabled,
.detail__add:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Plain guarantee rows, no arrows/expanders (requirement 6-4). */
.detail__guarantees {
  list-style: none;
  margin: var(--space-2) 0 0;
  padding: 0;
}

.detail__guarantees li {
  display: flex;
  align-items: center;
  min-height: 54px;
  border-top: 1px solid var(--colour-border);
  font-size: var(--font-size-md);
  color: var(--colour-text);
}

.detail__description {
  margin-block: var(--space-8);
  padding: var(--space-6);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-lg);
  background: var(--colour-surface);
}

.detail__description p {
  margin-top: var(--space-3);
  color: var(--colour-text-secondary);
}

.detail-state {
  margin-block: var(--space-12);
  text-align: center;
}

/* Blocking gate popup (docs/12 §6 新增元素). */
.gate-popup {
  position: fixed;
  inset: 0;
  z-index: 70;
  display: flex;
  align-items: center;
  justify-content: center;
}

.gate-popup__backdrop {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
}

.gate-popup__card {
  position: relative;
  width: min(400px, calc(100vw - 2rem));
  padding: var(--space-6);
  border-radius: var(--radius-lg);
  background: var(--colour-surface);
  text-align: center;
  box-shadow: var(--shadow-overlay);
}

.gate-popup__text {
  margin: 0 0 var(--space-5);
  font-size: var(--font-size-md);
  color: var(--colour-text);
}

.gate-popup__ok {
  min-height: 44px;
  padding: 0 var(--space-8);
  border: 0;
  border-radius: 4px;
  background: var(--colour-text);
  color: var(--colour-white);
  font: inherit;
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
}

@media (max-width: 64rem) {
  .detail__main {
    grid-template-columns: 1fr;
  }

  .detail__thumbs {
    flex-direction: row;
  }
}
</style>
