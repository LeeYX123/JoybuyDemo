<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useFetch, useRuntimeConfig } from '#imports'

import { useBuyerAuth } from '../../composables/useBuyerAuth'
import { useCategoryTree } from '../../composables/useCategoryTree'
import { useCart } from '../../composables/useCart'
import { useLocale } from '../../composables/useLocale'
import { useMarketLocale } from '../../composables/useMarketLocale'
import { useWishlist } from '../../composables/useWishlist'
import { formatDisplayPrice, isDeliveryLabel } from '../../utils/display'

// Product detail aligned to docs/12 §6: breadcrumb row, full-width 24px/700
// title, thumb rail + 591px-class main image + buy panel (Buy now / Add to
// cart / quantity stepper / plain service-guarantee rows). Purchase actions
// are gated by the account whitelist flag (requirement 6-6).
const route = useRoute()
const { t, categoryName } = useLocale()

const publicId = computed(() => String(route.params.id || ''))
const config = useRuntimeConfig()
const { apiQuery } = useMarketLocale()
const productQuery = computed(() => new URLSearchParams(apiQuery.value).toString())

const { data, error } = await useFetch(
  () =>
    import.meta.server
      ? `${config.apiBaseInternal}/products/${publicId.value}?${productQuery.value}`
      : `/api/v1/products/${publicId.value}?${productQuery.value}`,
  {
    // Reactive key: a template-string key is frozen at setup, so the payload
    // cache keeps serving the first locale after the header switches
    // market/language (same bug class as useActivityList). The key must track
    // publicId + market/locale query to trigger the refetch.
    key: computed(() => `product-${publicId.value}-${productQuery.value}`),
  },
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
  // WP-42 拍板：以后端返回的白名单标识为准，未拿到标识按不可购买处理。
  return account.value?.purchase_whitelisted === true
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
  // 后端白名单兜底：即使前端判断通过，后端返回 NOT_WHITELISTED 也弹拦截弹窗。
  if (response?.error?.code === 'NOT_WHITELISTED') {
    addState.value = 'idle'
    showGatePopup.value = true
    return
  }
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

const specOptions = computed(() =>
  Array.isArray(data.value?.spec_options) ? data.value.spec_options : [],
)
// 详情区（图文/规格表/spec_options）是否命中了译文行（spu_detail_translation）。
const isDetailTranslated = computed(() => data.value?.detail_translated === true)

// 规格匹配基准：默认用「权威值」——有 spec_options 时轴名/轴值来自源语言，
// 而 sku.specification 可能是本地化译文，两者不能直接相等比较，统一改用未
// 翻译的 canonical_specification。没有 spec_options 的历史商品由
// sku.specification 反推轴名（轴名本身已是译文），此时必须继续用译文。
// 例外（2026-11-17）：后端详情接口接上 spu_detail_translation 后，
// spec_options 也可能已是译文（detail_translated=true）；此时如果详情译文
// 与 SKU 规格译文来自同一术语缓存（specification_translated=true），两边
// 语言一致，必须改用译文对译文匹配，否则译文的轴名与 canonical 的规格键
// 对不上，多规格选中态会跳变。展示（价格条/规格文本/title）仍用
// sku.specification。
function matchSpec(sku) {
  if (specOptions.value.length && isDetailTranslated.value && sku?.specification_translated) {
    return sku.specification
  }
  return specOptions.value.length
    ? (sku?.canonical_specification ?? sku?.specification)
    : sku?.specification
}

// 爬虫商品按 1 SPU = 1 SKU 导入，但 SpuDetail.spec_options 可能残留源站的
// 多规格轴（值指向未导入的源 SKU）——这些按钮点了永远找不到候选 SKU，表现为
// 「规格无法选择」。唯一可购 SKU 时不再渲染规格交互区（selectedSku 已兜底
// 自动选中唯一 SKU），规格信息只读展示；多 SKU 商品过滤掉解析不到可购 SKU
// 的规格值，避免死按钮。
const isSingleSku = computed(() => purchasableSkus.value.length <= 1)

function resolvesToPurchasableSku(axisName, value) {
  const skuIds = Array.isArray(value.sku_ids) ? value.sku_ids : []
  return purchasableSkus.value.some(
    (sku) =>
      String(matchSpec(sku)?.[axisName]) === String(value.value) || skuIds.includes(sku.public_id),
  )
}

const variantAxes = computed(() => {
  if (isSingleSku.value) return []
  // 爬虫给出 spec_options 时优先用它：保留源站维度顺序、系列在前，
  // 并带上 s96 规格图与 SKU 映射；历史商品回退到 SKU 规格推导。
  if (specOptions.value.length) {
    return specOptions.value
      .filter((option) => Array.isArray(option.values) && option.values.length)
      .map((option) => ({
        name: option.name,
        values: option.values
          .map((value) => ({
            value: String(value.value),
            image_url: value.image_url || '',
            sku_ids: Array.isArray(value.sku_ids) ? value.sku_ids : [],
          }))
          .filter((value) => resolvesToPurchasableSku(option.name, value)),
      }))
      .filter((axis) => axis.values.length)
  }
  const axes = new Map()
  for (const sku of purchasableSkus.value) {
    // 反推轴：轴名与轴值都来自 sku.specification，匹配必须同样用译文。
    for (const [key, value] of Object.entries(sku.specification || {})) {
      if (!axes.has(key)) axes.set(key, new Set())
      axes.get(key).add(String(value))
    }
  }
  return [...axes.entries()].map(([name, values]) => ({
    name,
    values: [...values].map((value) => ({ value, image_url: '', sku_ids: [] })),
  }))
})

function selectVariant(axisName, optionValue) {
  const value = typeof optionValue === 'string' ? optionValue : optionValue.value
  const skuIds = typeof optionValue === 'string' ? [] : optionValue.sku_ids || []
  let candidates = purchasableSkus.value.filter(
    (sku) => String(matchSpec(sku)?.[axisName]) === value,
  )
  if (!candidates.length && skuIds.length) {
    // 规格维度名会随页面语言变化（系列/Series、颜色/Colour）。SKU 规格名
    // 与 spec_options 名不一致时，用 sku_ids 映射兜底，避免点了没反应。
    candidates = purchasableSkus.value.filter((sku) => skuIds.includes(sku.public_id))
  }
  if (skuIds.length) {
    const known = candidates.filter((sku) => skuIds.includes(sku.public_id))
    if (known.length) candidates = known
  }
  if (!candidates.length) return
  // 多维商品：优先保留当前 SKU 在其它维度上的选择，避免只换一个维度
  // 就跳到完全不相关的组合。
  const current = selectedSku.value
  if (current) {
    const currentSpec = matchSpec(current) || {}
    const matching = candidates.filter((sku) =>
      Object.entries(matchSpec(sku) || {}).every(
        ([name, specValue]) => name === axisName || String(specValue) === String(currentSpec[name]),
      ),
    )
    if (matching.length) {
      selectedSkuId.value = matching[0].public_id
      return
    }
  }
  selectedSkuId.value = candidates[0].public_id
}

const gallery = computed(() => (Array.isArray(data.value?.gallery) ? data.value.gallery : []))
const videos = computed(() => (Array.isArray(data.value?.videos) ? data.value.videos : []))

// 画廊媒体：视频排在图片前面（Joybuy 详情页顺序），图片保持原顺序。
const mediaItems = computed(() => {
  const items = []
  videos.value.forEach((video, index) => {
    items.push({
      key: `video-${index}`,
      type: 'video',
      url: video.url,
      poster: video.poster || '',
    })
  })
  gallery.value.forEach((asset, index) => {
    items.push({ key: `image-${index}-${asset.url}`, type: 'image', url: asset.url })
  })
  return items
})

const activeMediaKey = ref('')
const currentMedia = computed(() => {
  if (!mediaItems.value.length) return null
  const selected = mediaItems.value.find((item) => item.key === activeMediaKey.value)
  return selected || mediaItems.value[0]
})
const currentImage = computed(() =>
  currentMedia.value?.type === 'image' ? currentMedia.value.url : '',
)
const currentVideo = computed(() =>
  currentMedia.value?.type === 'video' ? currentMedia.value : null,
)

// 画廊缩略图轨（Joybuy 样式）：轨高与主图一致，超出部分藏起来，
// 底部半透明下拉按钮点开后浮层展开全部缩略图。
const imageEl = ref(null)
const galleryHeight = ref(0)
const thumbsEl = ref(null)
const thumbsExpanded = ref(false)
const thumbsOverflow = ref(false)
let imageResizeObserver = null

function measureGalleryHeight() {
  if (!imageEl.value) return
  galleryHeight.value = Math.round(imageEl.value.getBoundingClientRect().height)
  nextTick(measureThumbs)
}

function measureThumbs() {
  if (thumbsExpanded.value) return
  const el = thumbsEl.value
  if (!el) return
  thumbsOverflow.value = el.scrollHeight > el.clientHeight + 1
}

function toggleThumbs() {
  thumbsExpanded.value = !thumbsExpanded.value
  if (!thumbsExpanded.value) nextTick(measureThumbs)
}

function selectMedia(item) {
  activeMediaKey.value = item.key
  if (thumbsExpanded.value) {
    thumbsExpanded.value = false
    nextTick(measureThumbs)
  }
}

// 滚动过主图后出现底部购物条；滑回顶部（主图仍在视口内）即消失。
const stickyBarVisible = ref(false)

function onScroll() {
  const el = imageEl.value
  stickyBarVisible.value = Boolean(el) && el.getBoundingClientRect().bottom < 0
}

const stickySpecText = computed(() => {
  const spec = selectedSku.value?.specification || {}
  return Object.values(spec)
    .map((value) => String(value || '').trim())
    .filter(Boolean)
    .join(' / ')
})

// Wishlist on the detail page shares the same session-backed set as the cards.
const { isFavourite, isPending, ensureLoaded, toggle } = useWishlist()
const wishlisted = computed(() => isFavourite(publicId.value))
const wishPending = computed(() => isPending(publicId.value))

onMounted(() => {
  ensureLoaded()
  nextTick(() => {
    measureGalleryHeight()
    measureThumbs()
  })
  if (typeof ResizeObserver !== 'undefined' && imageEl.value) {
    imageResizeObserver = new ResizeObserver(measureGalleryHeight)
    imageResizeObserver.observe(imageEl.value)
  }
  onScroll()
  window.addEventListener('scroll', onScroll, { passive: true })
  window.addEventListener('resize', measureGalleryHeight)
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', onScroll)
  window.removeEventListener('resize', measureGalleryHeight)
  imageResizeObserver?.disconnect()
  imageResizeObserver = null
})

watch(
  () => mediaItems.value.length,
  () => nextTick(measureThumbs),
)

const contentSections = computed(() =>
  Array.isArray(data.value?.content_sections) ? data.value.content_sections : [],
)
const specificationTables = computed(() =>
  Array.isArray(data.value?.specification_tables) ? data.value.specification_tables : [],
)
const aiSummaryText = computed(() => data.value?.ai_summary || '')

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

// 商品自身的 Joybuy 类目（最多两级，如 厨具餐具 / 锅具）；新商品优先展示。
// 历史商品没有 product_category 时回退到上面的本地类目树，避免页面退化。
const productCategoryCrumb = computed(() =>
  Array.isArray(data.value?.category_breadcrumb) ? data.value.category_breadcrumb : [],
)

// Hover zoom: the real site shows an enlarged detail view to the right of
// the main image while the cursor moves over it.
const zoomVisible = ref(false)
const zoomPos = ref({ x: 50, y: 50 })
// The blue dotted selection mask marks the region shown in the zoom panel:
// mask is 40% of the image (1 / 2.5 zoom), centred on the cursor, clamped.
const zoomMaskStyle = ref({})

// 视频不参与放大镜：只有图片媒体才显示悬停缩放。
function onZoomEnter() {
  if (currentImage.value) zoomVisible.value = true
}

function onZoomLeave() {
  zoomVisible.value = false
}

function onZoomMove(event) {
  if (!currentImage.value) return
  const rect = event.currentTarget.getBoundingClientRect()
  const xPct = Math.min(100, Math.max(0, ((event.clientX - rect.left) / rect.width) * 100))
  const yPct = Math.min(100, Math.max(0, ((event.clientY - rect.top) / rect.height) * 100))
  zoomPos.value = { x: xPct, y: yPct }
  const half = 20 // 40% mask, centred on the cursor
  const left = Math.min(100 - half * 2, Math.max(0, xPct - half))
  const top = Math.min(100 - half * 2, Math.max(0, yPct - half))
  zoomMaskStyle.value = { left: `${left}%`, top: `${top}%` }
}

// Service guarantees: plain text rows, no accordion (requirement 6-4).
const guarantees = computed(() => [
  t('detail.guaranteeReturns'),
  t('detail.guaranteeWarranty'),
  t('detail.guaranteeSupport'),
])

// 【我们支持】支付图标区（需求文档03 11.8）：真站 PDP footer「We support」行实测
// 复刻（9 个支付 SVG 各 32x20，顺序 = American Express→Klarna）。图标已下载到
// storefront/public/images/pdp-services/ 本地托管（项目铁律：无第三方 CDN）。
const paymentIcons = [
  { src: '/images/pdp-services/payment-american-express.svg', alt: 'American Express' },
  { src: '/images/pdp-services/payment-visa.svg', alt: 'Visa' },
  { src: '/images/pdp-services/payment-mastercard.svg', alt: 'Mastercard' },
  { src: '/images/pdp-services/payment-unionpay.svg', alt: 'UnionPay' },
  { src: '/images/pdp-services/payment-paypal.svg', alt: 'PayPal' },
  { src: '/images/pdp-services/payment-wechat-pay.svg', alt: 'WeChat Pay' },
  { src: '/images/pdp-services/payment-google-pay.svg', alt: 'Google Pay' },
  { src: '/images/pdp-services/payment-apple-pay.svg', alt: 'Apple Pay' },
  { src: '/images/pdp-services/payment-klarna.svg', alt: 'Klarna' },
]

function changeQuantity(delta) {
  quantity.value = Math.max(1, Math.min(99, quantity.value + delta))
}

useHead(() => ({ title: data.value?.title || 'Product' }))
</script>

<template>
  <div class="detail-page-bg">
    <AppContainer>
      <div v-if="error" class="detail-state" role="alert">
        <!-- 迭代02：平台下架/商家下架统一提示「商品已下架，无法查看」。 -->
        <p>
          {{
            error?.statusCode === 404
              ? t('product.unavailable')
              : error?.message || t('product.unavailable')
          }}
        </p>
        <NuxtLink to="/">{{ t('detail.continueShopping') }}</NuxtLink>
      </div>

      <section v-else class="detail">
        <!-- Clickable top nav: Home / 商品类目（最多两级）/ product title.
           历史商品没有商品类目时回退到本地类目树（Home / root / child / title）。 -->
        <nav class="detail__crumbs" :aria-label="t('breadcrumb.home')">
          <NuxtLink class="detail__crumb" to="/">{{ t('detail.home') }}</NuxtLink>
          <template v-if="productCategoryCrumb.length">
            <template v-for="node in productCategoryCrumb" :key="node.id">
              <span class="detail__crumb-sep" aria-hidden="true">/</span>
              <span class="detail__crumb">{{ node.name }}</span>
            </template>
          </template>
          <template v-else>
            <template v-for="node in categoryTrail" :key="node.slug">
              <span class="detail__crumb-sep" aria-hidden="true">/</span>
              <NuxtLink class="detail__crumb" :to="`/c/${node.slug}`">{{
                categoryName(node)
              }}</NuxtLink>
            </template>
          </template>
          <span class="detail__crumb-sep" aria-hidden="true">/</span>
          <span class="detail__crumb detail__crumb--current">{{ data?.title }}</span>
        </nav>
        <p v-if="data?.brand" class="detail__brandline">{{ data.brand }}</p>
        <h1 class="detail__title">{{ data?.title }}</h1>

        <div class="detail__main">
          <div
            class="detail__thumbs-rail"
            :style="galleryHeight ? { height: `${galleryHeight}px` } : undefined"
          >
            <div
              ref="thumbsEl"
              class="detail__thumbs"
              :class="{ 'detail__thumbs--expanded': thumbsExpanded }"
            >
              <button
                v-for="(item, index) in mediaItems"
                :key="item.key"
                type="button"
                class="detail__thumb"
                :class="{ 'detail__thumb--active': currentMedia?.key === item.key }"
                :aria-label="
                  item.type === 'video'
                    ? `${data?.title} video ${index + 1}`
                    : `${data?.title} thumbnail ${index + 1}`
                "
                @click="selectMedia(item)"
              >
                <img
                  v-if="item.type === 'image' || item.poster"
                  :src="item.type === 'image' ? item.url : item.poster"
                  :alt="
                    item.type === 'video'
                      ? `${data?.title} video preview`
                      : `${data?.title} thumbnail ${index + 1}`
                  "
                />
                <span v-else class="detail__thumb-video" aria-hidden="true">▶</span>
                <span v-if="item.type === 'video'" class="detail__thumb-play" aria-hidden="true"
                  >▶</span
                >
              </button>
            </div>
            <!-- 缩略图超出主图高度时的半透明下拉按钮（Joybuy 同款交互）。 -->
            <button
              v-if="thumbsOverflow || thumbsExpanded"
              class="detail__thumbs-toggle"
              type="button"
              :aria-expanded="thumbsExpanded"
              :aria-label="thumbsExpanded ? '收起商品图片' : '展开更多商品图片'"
              @click="toggleThumbs"
            >
              <span class="detail__thumbs-toggle-caret" :class="{ 'is-open': thumbsExpanded }"
                >⌄</span
              >
            </button>
          </div>

          <div
            ref="imageEl"
            class="detail__image"
            :class="{ 'detail__image--video': currentVideo }"
            @mouseenter="onZoomEnter"
            @mousemove="onZoomMove"
            @mouseleave="onZoomLeave"
          >
            <!-- 视频排在画廊第一位；本地 /media 文件 + 源站封面，不引用 CDN。 -->
            <video
              v-if="currentVideo"
              :key="currentVideo.url"
              class="detail__video"
              :src="currentVideo.url"
              :poster="currentVideo.poster || undefined"
              controls
              playsinline
              preload="metadata"
            >
              Your browser does not support embedded video.
            </video>
            <img v-else-if="currentImage" :src="currentImage" :alt="data?.title" />
            <BaseSkeleton v-else variant="block" class="detail__image-placeholder" />
            <!-- Blue dotted selection mask over the hovered region (real site). -->
            <div
              v-if="zoomVisible && currentImage"
              class="detail__zoom-mask"
              :style="zoomMaskStyle"
              aria-hidden="true"
            ></div>
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
            <!-- 需求文档03 11.7：真站 PDP 无库存展示行（实测 var/reco_pdp_20261119/），
                 999+/库存数据字段保留在后端响应里，仅不再渲染。 -->
            <p v-if="!offer" class="detail__inventory detail__inventory--out" role="status">
              {{ t('product.unavailableShort') }}
            </p>

            <!-- 单 SKU/空规格：不做规格交互，只读展示唯一 SKU 的规格值。 -->
            <p v-if="isSingleSku && stickySpecText" class="detail__spec-readonly">
              {{ stickySpecText }}
            </p>

            <div v-for="axis in variantAxes" :key="axis.name" class="detail__axis">
              <h2 class="detail__axis-name">{{ axis.name }}</h2>
              <div class="detail__axis-values">
                <button
                  v-for="value in axis.values"
                  :key="value.value"
                  type="button"
                  class="detail__variant"
                  :class="{
                    'detail__variant--active':
                      String(matchSpec(selectedSku)?.[axis.name]) === value.value ||
                      value.sku_ids.includes(selectedSku?.public_id),
                  }"
                  @click="selectVariant(axis.name, value)"
                >
                  <img
                    v-if="value.image_url"
                    class="detail__variant-image"
                    :src="value.image_url"
                    :alt="value.value"
                  />
                  <span>{{ value.value }}</span>
                </button>
              </div>
            </div>

            <div class="detail__quantity">
              <span class="detail__quantity-label">{{ t('detail.quantity') }}</span>
              <div class="detail__stepper">
                <button
                  type="button"
                  :aria-label="t('detail.decreaseQty')"
                  @click="changeQuantity(-1)"
                >
                  −
                </button>
                <span class="detail__stepper-value" aria-live="polite">{{ quantity }}</span>
                <button
                  type="button"
                  :aria-label="t('detail.increaseQty')"
                  @click="changeQuantity(1)"
                >
                  +
                </button>
              </div>
            </div>

            <button
              class="detail__wish"
              :class="{ 'detail__wish--active': wishlisted }"
              type="button"
              :aria-pressed="wishlisted"
              :disabled="wishPending"
              @click="toggle(publicId)"
            >
              <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
                <path
                  d="M12 20.3 4.8 13a4.9 4.9 0 0 1 0-7 4.9 4.9 0 0 1 7 0l.2.2.2-.2a4.9 4.9 0 0 1 7 0 4.9 4.9 0 0 1 0 7L12 20.3Z"
                  :fill="wishlisted ? 'currentColor' : 'none'"
                  stroke="currentColor"
                  stroke-width="1.6"
                />
              </svg>
              {{ wishlisted ? t('product.removeFromWishlist') : t('product.addToWishlist') }}
            </button>

            <div class="detail__actions">
              <button class="detail__buy" type="button" :disabled="!offer" @click="onBuyNow">
                {{ t('detail.buyNow') }}
              </button>
              <button
                class="detail__add"
                type="button"
                :disabled="!offer?.is_purchasable || addState === 'adding'"
                @click="onAddToCart"
              >
                {{
                  addState === 'added'
                    ? t('detail.addedToCart')
                    : addState === 'error'
                      ? t('detail.couldNotAdd')
                      : t('detail.addToCart')
                }}
              </button>
            </div>

            <ul class="detail__guarantees">
              <li v-for="line in guarantees" :key="line">{{ line }}</li>
            </ul>
          </div>
        </div>
      </section>

      <!-- 图文详情：区块标题 -> heading/paragraph 有序块 -> 区块图片。 -->
      <section
        v-if="contentSections.length"
        class="detail__description detail__content"
        aria-labelledby="detail-heading"
      >
        <h2 id="detail-heading">{{ t('detail.productDetails') }}</h2>
        <article
          v-for="(section, sectionIndex) in contentSections"
          :key="`${section.title || 'section'}-${sectionIndex}`"
          class="detail__content-section"
        >
          <h3 v-if="section.title" class="detail__content-title">{{ section.title }}</h3>
          <template v-for="(block, blockIndex) in section.blocks || []" :key="blockIndex">
            <h4 v-if="block.type === 'heading'" class="detail__content-heading">
              {{ block.text }}
            </h4>
            <p v-else class="detail__content-paragraph">{{ block.text }}</p>
          </template>
          <div v-if="section.images?.length" class="detail__content-images">
            <img
              v-for="(image, imageIndex) in section.images"
              :key="image"
              :src="image"
              :alt="`${section.title || data?.title} ${imageIndex + 1}`"
              loading="lazy"
            />
          </div>
        </article>
      </section>

      <!-- 历史商品没有结构化区块时回退到 description 纯文本。 -->
      <section
        v-else-if="data?.description"
        class="detail__description"
        aria-labelledby="detail-heading"
      >
        <h2 id="detail-heading">{{ t('detail.productDetails') }}</h2>
        <p class="detail__description-text">{{ data.description }}</p>
      </section>

      <!-- 规格参数：每个分组一张两列表格（属性 | 值），行序按源站。 -->
      <section
        v-if="specificationTables.length"
        class="detail__specs"
        aria-labelledby="specs-heading"
      >
        <h2 id="specs-heading">{{ t('detail.specifications') }}</h2>
        <div
          v-for="(table, tableIndex) in specificationTables"
          :key="`${table.title || 'spec'}-${tableIndex}`"
          class="detail__spec-group"
        >
          <h3 v-if="table.title" class="detail__spec-title">{{ table.title }}</h3>
          <table class="detail__spec-table">
            <tbody>
              <tr v-for="(row, rowIndex) in table.rows || []" :key="rowIndex">
                <th scope="row">{{ row.name }}</th>
                <td>{{ row.value }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- 视频也可在详情下方直接播放（画廊第一位仍是同一条视频）。 -->
      <section v-if="videos.length" class="detail__videos" aria-labelledby="videos-heading">
        <h2 id="videos-heading">{{ t('detail.productVideos') }}</h2>
        <div class="detail__video-list">
          <video
            v-for="(video, videoIndex) in videos"
            :key="`${video.url}-${videoIndex}`"
            :src="video.url"
            :poster="video.poster || undefined"
            controls
            playsinline
            preload="metadata"
          >
            Your browser does not support embedded video.
          </video>
        </div>
      </section>

      <!-- 评价区放在页面最后：左侧评分分布，右侧 AI 评价总结（Joybuy 布局）。 -->
      <ProductReviews
        v-if="publicId && data"
        :product-id="publicId"
        :ai-summary="aiSummaryText"
        :review-summary="data?.review_summary"
      />

      <!-- 我们支持：支付图标区（需求文档03 11.8，真站 footer「We support」行实测复刻）。 -->
      <section class="detail__support" aria-labelledby="support-heading">
        <h2 id="support-heading" class="detail__support-title">{{ t('pdp.supportTitle') }}</h2>
        <ul class="detail__support-icons">
          <li v-for="icon in paymentIcons" :key="icon.alt">
            <img :src="icon.src" :alt="icon.alt" width="32" height="20" loading="lazy" />
          </li>
        </ul>
      </section>

      <!-- 底部吸附购物条：滑过主图区后固定显示，滑回顶部即消失（Joybuy 交互）。 -->
      <div v-if="stickyBarVisible && data" class="buy-bar">
        <div class="buy-bar__inner">
          <img
            v-if="currentImage || gallery[0]?.url"
            class="buy-bar__thumb"
            :src="currentImage || gallery[0]?.url"
            :alt="data.title"
          />
          <div class="buy-bar__info">
            <p class="buy-bar__title">{{ data.title }}</p>
            <p v-if="stickySpecText" class="buy-bar__spec">{{ stickySpecText }}</p>
          </div>
          <p v-if="price" class="buy-bar__price">{{ price }}</p>
          <div class="buy-bar__actions">
            <button class="buy-bar__buy" type="button" :disabled="!offer" @click="onBuyNow">
              Buy now
            </button>
            <button
              class="buy-bar__add"
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
        </div>
      </div>

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
  </div>
</template>

<style scoped>
.detail-page-bg {
  /* Detail page area is white, full-bleed (real site). */
  margin-top: 0;
  margin-inline: calc(50% - 50vw);
  background: #ffffff;
}

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
  font-size: 14px;
  font-weight: var(--font-weight-bold);
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
  /* 缩略图轨高度由 JS 对齐主图（不是整行高度，右侧面板通常更高）。 */
  align-items: start;
}

.detail__thumbs-rail {
  position: relative;
  width: 56px;
  min-height: 0;
}

.detail__thumbs {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  height: 100%;
  max-height: 100%;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-width: none;
}

.detail__thumbs::-webkit-scrollbar {
  display: none;
}

/* 展开态：缩略图浮层压在页面上，点选后自动收起。 */
.detail__thumbs--expanded {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 20;
  height: auto;
  max-height: none;
  overflow: visible;
  padding: var(--space-2);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  box-shadow: 0 12px 28px rgb(0 0 0 / 18%);
}

/* 半透明下拉按钮：浮在缩略图轨底部，提示还有更多图片。 */
.detail__thumbs-toggle {
  position: absolute;
  bottom: var(--space-1);
  left: 50%;
  display: flex;
  width: 40px;
  height: 28px;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: none;
  border-radius: var(--radius-pill);
  background: rgb(26 26 26 / 62%);
  box-shadow: 0 2px 8px rgb(0 0 0 / 25%);
  color: var(--colour-white);
  cursor: pointer;
  transform: translateX(-50%);
  backdrop-filter: blur(2px);
  z-index: 5;
}

.detail__thumbs-toggle:hover {
  background: rgb(26 26 26 / 78%);
}

.detail__thumbs-toggle-caret {
  font-size: 1.125rem;
  line-height: 1;
  transition: transform 160ms ease;
}

.detail__thumbs-toggle-caret.is-open {
  transform: rotate(180deg);
}

.detail__thumb {
  position: relative;
  flex: none;
  width: 56px;
  height: 56px;
  padding: 0;
  border: 2px solid var(--colour-border);
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

/* 没有封面图的视频缩略图：深色底 + 播放三角。 */
.detail__thumb-video {
  display: flex;
  width: 100%;
  height: 100%;
  align-items: center;
  justify-content: center;
  background: #1a1a1a;
  color: var(--colour-white);
  font-size: 1.125rem;
}

.detail__thumb-play {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--colour-white);
  font-size: 1.125rem;
  text-shadow: 0 1px 4px rgb(0 0 0 / 60%);
  pointer-events: none;
}

.detail__image {
  position: relative;
  background: #eeeff0;
}

.detail__image img {
  display: block;
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  background: #eeeff0;
}

/* 画廊视频：与主图同尺寸，完整显示不裁切（竖屏视频也不变形）。 */
.detail__video {
  display: block;
  width: 100%;
  aspect-ratio: 1;
  background: #000000;
  object-fit: contain;
}

/* Blue dotted selection mask (real-site hover affordance): 40% box, dense
 * blue dot grid over a translucent blue wash. */
.detail__zoom-mask {
  position: absolute;
  width: 40%;
  aspect-ratio: 1;
  z-index: 5;
  pointer-events: none;
  background-color: rgb(26 115 232 / 14%);
  background-image: radial-gradient(rgb(0 102 255 / 60%) 1px, transparent 1.5px);
  background-size: 7px 7px;
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
  background-color: #eeeff0;
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

/* 单 SKU/空规格：只读规格展示（无交互按钮）。 */
.detail__spec-readonly {
  margin: 0;
  font-size: var(--font-size-md);
  color: var(--colour-text-secondary);
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
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 44px;
  padding: 0 var(--space-4);
  border: 1px solid var(--colour-border-strong);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  cursor: pointer;
  font: inherit;
}

.detail__variant-image {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  object-fit: cover;
}

.detail__variant--active {
  border-color: var(--colour-accent);
  color: var(--colour-accent);
  background: var(--colour-accent-soft);
  font-weight: var(--font-weight-semibold);
}

/* 真站 dpCounter_counterBoxWrapper 实测：padding 12px 0，label margin-bottom 12px
   （需求文档03 11.7，var/reco_pdp_20261119/measurement.md）。 */
.detail__quantity {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 12px 0;
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

/* 三段间距按真站实测调大（需求文档03 11.7）：真站相邻区块 12px + 数量块自带
   padding 12px 0 → 数量→收藏视觉 24px、收藏→按钮区 12px（原 8px）。 */
.detail__actions {
  display: flex;
  gap: var(--space-2);
  margin-top: 12px;
}

.detail__wish {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  width: 100%;
  min-height: 44px;
  margin-top: 12px;
  border: 1px solid var(--colour-border-strong);
  border-radius: 4px;
  background: var(--colour-surface);
  color: var(--colour-text);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
}

.detail__wish:hover:not(:disabled) {
  background: var(--colour-surface-muted);
}

.detail__wish--active {
  border-color: var(--colour-accent);
  color: var(--colour-accent);
  background: var(--colour-accent-soft);
}

.detail__wish:disabled {
  cursor: progress;
  opacity: 0.65;
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

/* 我们支持：真站 footer_footerPay 实测（padding 26px 0，标题 14px/400 #505259
   margin-right 16px，图标各 32x20）。 */
.detail__support {
  display: flex;
  align-items: center;
  margin-top: var(--space-8);
  padding: 26px 0;
  border-top: 1px solid var(--colour-border);
}

.detail__support-title {
  margin: 0 16px 0 0;
  font-size: 14px;
  font-weight: var(--font-weight-regular);
  color: #505259;
}

.detail__support-icons {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.detail__support-icons img {
  display: block;
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

.detail__description-text {
  white-space: pre-line;
}

/* --- 图文详情（区块 -> heading/paragraph -> 图片） --- */
.detail__content-section + .detail__content-section {
  margin-top: var(--space-8);
  padding-top: var(--space-6);
  border-top: 1px solid var(--colour-border);
}

.detail__content-title {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  color: #1a1a1a;
}

/* 子标题：比正文大一号、加粗、加黑（docs/14 §7.7，与 Joybuy 一致）。 */
.detail__content-heading {
  margin-top: var(--space-5);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  color: #1a1a1a;
}

.detail__content-paragraph {
  position: relative;
  margin-top: var(--space-3);
  padding-left: 1.1em;
  color: var(--colour-text-secondary);
  white-space: pre-line;
}

/* 段落前加「·」项目符号（对应富文本里的「-」列表项渲染效果）。 */
.detail__content-paragraph::before {
  content: '·';
  position: absolute;
  left: 0.15em;
  color: var(--colour-text);
  font-weight: var(--font-weight-bold);
}

.detail__content-images {
  display: grid;
  /* 与 Joybuy 一致：图文详情的图片一张占满一行，宽度铺满详情内容区。 */
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-4);
  margin-top: var(--space-4);
}

.detail__content-images img {
  display: block;
  width: 100%;
  height: auto;
  border-radius: var(--radius-md);
  background: var(--colour-surface-muted);
}

/* --- 底部吸附购物条（滑过主图区后出现） --- */
.buy-bar {
  position: fixed;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 40;
  /* Joybuy 底部吸附条实测高度 68px（m.joybuy.co.uk bottomBarFloor）。 */
  height: 68px;
  border-top: 1px solid var(--colour-border);
  background: rgb(255 255 255 / 97%);
  box-shadow: 0 -6px 18px rgb(0 0 0 / 8%);
}

.buy-bar__inner {
  display: flex;
  width: 100%;
  max-width: var(--container-max);
  height: 100%;
  align-items: center;
  gap: var(--space-4);
  margin-inline: auto;
  padding-inline: var(--container-pad);
}

.buy-bar__thumb {
  width: 48px;
  height: 48px;
  flex: none;
  border: 1px solid var(--colour-border);
  border-radius: 4px;
  object-fit: cover;
}

.buy-bar__info {
  min-width: 0;
  flex: 1;
}

.buy-bar__title {
  overflow: hidden;
  color: #1a1a1a;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-bold);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.buy-bar__spec {
  margin-top: 2px;
  overflow: hidden;
  color: var(--colour-text-secondary);
  font-size: var(--font-size-sm);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.buy-bar__price {
  flex: none;
  color: var(--colour-text);
  font-size: 1.25rem;
  font-weight: var(--font-weight-bold);
}

.buy-bar__actions {
  display: flex;
  flex: none;
  gap: var(--space-2);
}

.buy-bar__buy,
.buy-bar__add {
  min-width: 148px;
  height: 40px;
  padding-inline: var(--space-4);
  border: none;
  border-radius: 4px;
  color: var(--colour-white);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
}

.buy-bar__buy {
  background: var(--colour-accent);
}

.buy-bar__add {
  background: #1a1a1a;
}

.buy-bar__buy:disabled,
.buy-bar__add:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

@media (max-width: 48rem) {
  .buy-bar__inner {
    gap: var(--space-2);
  }

  .buy-bar__thumb {
    width: 40px;
    height: 40px;
  }

  .buy-bar__spec {
    display: none;
  }

  .buy-bar__price {
    font-size: var(--font-size-md);
  }

  .buy-bar__buy,
  .buy-bar__add {
    min-width: 0;
    height: 40px;
    padding-inline: var(--space-3);
    font-size: var(--font-size-sm);
  }
}

/* --- 规格参数：每组一张两列表格 --- */
.detail__specs {
  margin-block: var(--space-8);
  padding: var(--space-6);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-lg);
  background: var(--colour-surface);
}

.detail__spec-group {
  margin-top: var(--space-5);
}

.detail__spec-title {
  margin-bottom: var(--space-2);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  color: #1a1a1a;
}

.detail__spec-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-md);
}

.detail__spec-table th,
.detail__spec-table td {
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--colour-border);
  text-align: left;
  vertical-align: top;
}

.detail__spec-table tbody th {
  width: 32%;
  background: var(--colour-surface-soft);
  color: var(--colour-text);
  font-weight: var(--font-weight-semibold);
}

.detail__spec-table tbody td {
  color: var(--colour-text-secondary);
}

/* --- 详情下方视频 --- */
.detail__videos {
  margin-block: var(--space-8);
}

.detail__video-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--space-4);
  margin-top: var(--space-4);
}

.detail__video-list video {
  display: block;
  width: 100%;
  border-radius: var(--radius-md);
  background: #000000;
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

  /* 窄屏缩略图改横向滚动，不再受主图高度约束。 */
  .detail__thumbs-rail {
    height: auto !important;
  }

  .detail__thumbs {
    flex-direction: row;
    height: auto;
    max-height: none;
    overflow-x: auto;
    overflow-y: hidden;
  }

  .detail__thumbs-toggle {
    display: none;
  }
}
</style>
