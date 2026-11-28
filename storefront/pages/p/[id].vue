<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useFetch, useRuntimeConfig } from '#imports'

import { useBuyerAuth } from '../../composables/useBuyerAuth'
import { useCategoryTree } from '../../composables/useCategoryTree'
import { useCart } from '../../composables/useCart'
import { useLocale } from '../../composables/useLocale'
import { useMarketLocale } from '../../composables/useMarketLocale'
import { useWishlist } from '../../composables/useWishlist'
import { formatDisplayPrice } from '../../utils/display'
import { categoryHref } from '../../utils/categoryLinks'
import { findSkuForOffer, resolveSelectedSku } from '../../utils/offerSelection'
import {
  familyMembers,
  memberLabel,
  merchantLabel,
  merchantOffers,
  preferredOfferId,
  resolveActiveOffer,
  siblingTarget,
} from '../../utils/variantFamily'
import { resolveProductCategoryCrumbs } from '../../utils/pdpBreadcrumb'
import { ratingAverageLabel, soldCountLabel } from '../../utils/pdpDisplay'
import {
  resolveGalleryArchive,
  resolveVariantArchive,
  variantDetailField,
  variantGallery,
  variantQuery,
  variantReviewSummary,
  variantSoldAmount,
  variantTitleText,
} from '../../utils/variantArchive'

// Product detail aligned to docs/12 §6: breadcrumb row, full-width 24px/700
// title, thumb rail + 591px-class main image + buy panel (Buy now / Add to
// cart / quantity stepper / plain service-guarantee rows). Purchase actions
// are gated by the account whitelist flag (requirement 6-6).
const route = useRoute()
const { t, categoryName } = useLocale()

const publicId = computed(() => String(route.params.id || ''))
// 需求 20.1/20.3：商家店铺页链接带 ?offer=<offer_id>&from=merchant。
const requestedOfferId = computed(() => String(route.query.offer || ''))
// 批次 DA：切规格后 URL 带 ?sku=<sku_public_id>（单 URL 可分享；刷新/前进
// 后退都能还原所选规格）。服务端按它返回 variant_archive。
const requestedSkuId = computed(() => String(route.query.sku || ''))
const fromMerchant = computed(() => route.query.from === 'merchant')
const config = useRuntimeConfig()
const { apiQuery } = useMarketLocale()
// 只含市场/语言与商家 offer：作为 useFetch 的缓存 key。切规格不改 key，
// 由 watch(requestedSkuId) 手动 refresh()，避免 data 被清空导致整页闪白。
const productQuery = computed(() => {
  const params = new URLSearchParams(apiQuery.value)
  // 带上 offer 让后端返回该商家自己的 offer（同款多商家时默认 first 会串商家）。
  // 用 offerForRequest（不是 requestedOfferId）：切换商家不重取。
  if (offerForRequest.value) params.set('offer', offerForRequest.value)
  return params.toString()
})
const requestQuery = computed(() => {
  const params = new URLSearchParams(productQuery.value)
  if (requestedSkuId.value) params.set('sku', requestedSkuId.value)
  return params.toString()
})
// 批次 DB：商家轴切换不应触发整页 re-fetch（否则 data 被清空、整页闪白，与
// 批次 DA 的 ?sku= 同一类坑）。fetch key 里的 offer 只在**商品变化**时更新；
// 商家切换只改本地 activeOfferId + URL，价格/库存直接用 skus[].offers 算。
const offerForRequest = ref(requestedOfferId.value)
watch(publicId, () => {
  offerForRequest.value = String(route.query.offer || '')
})

const { data, error, refresh } = await useFetch(
  () =>
    import.meta.server
      ? `${config.apiBaseInternal}/products/${publicId.value}?${requestQuery.value}`
      : `/api/v1/products/${publicId.value}?${requestQuery.value}`,
  {
    // Reactive key: a template-string key is frozen at setup, so the payload
    // cache keeps serving the first locale after the header switches
    // market/language (same bug class as useActivityList). The key must track
    // publicId + market/locale query to trigger the refetch. 切规格的 ?sku=
    // 不进 key（见 requestQuery），由下面的 watcher 显式 refresh()。
    key: computed(() => `product-${publicId.value}-${productQuery.value}`),
    watch: false,
  },
)

const { isAuthenticated, account, purchaseWhitelisted } = useBuyerAuth()

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
  if (!offer.value?.public_id) return
  // 立即购买（2026-11-28 修复：此前不带商品直接跳 /checkout，空购物车被
  // quote 判 CART_INVALID）：独立直购上下文，不写购物车——带当前 offer 与
  // 数量进结账页（?offer=<offer_public_id>&qty=<n>），结账页两步都透传。
  const query = new URLSearchParams()
  query.set('offer', offer.value.public_id)
  query.set('qty', String(Math.max(1, Number(quantity.value) || 1)))
  navigateTo(`/checkout?${query.toString()}`)
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
// URL 带入的 offer 是否命中本商品的某个 SKU（命中即「商家上下文已确定」）。
const requestedOfferSku = computed(() =>
  findSkuForOffer(purchasableSkus.value, requestedOfferId.value),
)
const selectedSku = computed(() =>
  resolveSelectedSku(purchasableSkus.value, selectedSkuId.value, requestedOfferId.value),
)
// 带 offer 进来但详情里没有该 offer（商家已下架/规格不匹配）→ 回落默认 + 明确提示。
const offerFallbackNotice = computed(
  () =>
    Boolean(requestedOfferId.value) &&
    Boolean(data.value) &&
    !requestedOfferSku.value &&
    purchasableSkus.value.length > 0,
)

// 批次 DA：URL 的 ?sku= 是所选规格的事实来源（分享/刷新/前进后退一致）。
function syncSelectedSkuFromQuery() {
  const skuId = requestedSkuId.value
  if (!skuId) {
    selectedSkuId.value = null
    return
  }
  if (purchasableSkus.value.some((sku) => sku.public_id === skuId)) {
    selectedSkuId.value = skuId
  }
}
watch(requestedSkuId, (value, oldValue) => {
  syncSelectedSkuFromQuery()
  // 只有 sku 变化才重取；商品/语言变化由 useFetch 的 key 负责。
  if (value !== oldValue) void refresh()
})
// 首次渲染（含 SSR）与商品/语言切换后 data 重新到达时，按 URL 对齐选中 SKU，
// 否则 ?sku= 分享链接首次渲染会退回默认规格、档案不生效。
watch([publicId, purchasableSkus], syncSelectedSkuFromQuery, { immediate: true })

// 批次 DB（Q9/Q10）：商家轴。selectedSku.offers 是该规格的全部商家 offer，
// activeOfferId 来自 URL ?offer= 或用户点选；命中不了时回退后端默认 offer。
const activeOfferId = ref(String(route.query.offer || ''))
watch(requestedOfferId, (value) => {
  activeOfferId.value = value
})
const offer = computed(() => resolveActiveOffer(selectedSku.value, activeOfferId.value))
const skuMerchants = computed(() => merchantOffers(selectedSku.value))
const hasMerchantAxis = computed(() => skuMerchants.value.length > 1)
const familyMemberList = computed(() => familyMembers(data.value))
const hasFamilyAxis = computed(() => familyMemberList.value.length > 1)
const familyAxisName = computed(
  () =>
    String(data.value?.variant_family?.axis_name || '').trim() ||
    String(data.value?.variant_family?.axis_hint || '').trim() ||
    t('detail.modelAxis'),
)

function selectMerchant(offerEntry) {
  if (!offerEntry?.public_id || activeOfferId.value === offerEntry.public_id) return
  activeOfferId.value = offerEntry.public_id
  // 写回 URL（可分享、刷新后仍是该商家）；不触发 re-fetch（key 用 offerForRequest）。
  void router.replace({ query: { ...route.query, offer: offerEntry.public_id } })
}

function goToFamilyMember(member) {
  if (!member?.spu_public_id || member.is_current) return
  const target = siblingTarget(member, offer.value, route.query)
  void navigateTo(target)
}
// Business rule: one original price only — no strikethrough list price.
const price = computed(() => (offer.value ? formatDisplayPrice(offer.value.price) : null))

const router = useRouter()

// 批次 DA：当前所选规格的「整档切换」档案。只有 share_metadata=false 且
// 档案 sku 与当前选中 SKU 一致时才生效；其余情况返回 null，标题/评分/已售/
// 详情保持 SPU 级。注意**画廊不在这里**：画廊按 SKU 是否有自己的图单独判定
// （见下方 galleryArchive），纯尺码规格也可能换图。
const variantArchive = computed(() =>
  resolveVariantArchive(data.value, selectedSku.value?.public_id),
)
const displayTitle = computed(() => variantTitleText(variantArchive.value, data.value?.title))

// 需求 20.3：PDP 右下角【联系商家】。仅「已登录 + 白名单 + 来自商家店铺页
// 且能从 offer 确定商家」时显示；面板必须绑定该商品 offer 的商家，不能用
// 全局默认商家。直达 /p/<id>（无 from=merchant）一律不显示。
const chatOpen = ref(false)
const chatBlocked = ref(false)
const contactMerchant = computed(() => requestedOfferSku.value?.offer?.merchant || null)
const canContactSeller = computed(
  () =>
    isAuthenticated.value &&
    purchaseWhitelisted.value &&
    fromMerchant.value &&
    Boolean(contactMerchant.value?.slug) &&
    !chatBlocked.value,
)
const chatMerchant = computed(() => ({
  slug: contactMerchant.value?.slug || '',
  display_name: contactMerchant.value?.display_name || '',
  avatar_url: contactMerchant.value?.avatar_url || '',
}))

function onChatBlocked() {
  chatBlocked.value = true
  chatOpen.value = false
}

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
  // 爬虫给出 spec_options 时优先用它：保留源站维度顺序、系列在前，
  // 并带上 s96 规格图与 SKU 映射；历史商品回退到 SKU 规格推导。
  if (specOptions.value.length) {
    const fromSpecOptions = specOptions.value
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
      .map((axis) => ({
        ...axis,
        // 真站按「该维度有没有规格图」决定渲染图片卡还是文字胶囊
        // （var/pdp_spec_ui_20261127/measurements.md §3/§4）。
        has_image: axis.values.some((value) => Boolean(value.image_url)),
      }))
    // 同款多规格合并（批次 CB2）后，保留 SPU 的 spec_options 可能仍是源站
    // 单规格残留（或详情译文行残留），过滤后一个可购规格值都不剩。此时必须
    // 回退到 SKU 规格反推，否则多 SKU 商品规格区一片空白、无法切换。
    if (fromSpecOptions.length) return fromSpecOptions
  }
  // 单 SKU：反推轴只会造出点了没反应的单值按钮，保持只读展示。但上面
  // spec_options 能解析到唯一可购 SKU 的轴（如单个 Capacity: 5000mAh 的
  // 真实规格）要照真站渲染成卡片，所以这个短路必须排在 spec_options 之后。
  if (isSingleSku.value) return []
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

// 真站轴标题是「轴名: 当前值」，值加粗 600
// （var/pdp_spec_ui_20261127/measurements.md §1）。
function axisSelectedValue(axis) {
  const spec = matchSpec(selectedSku.value) || {}
  const value = spec[axis.name]
  return value === undefined || value === null ? '' : String(value)
}

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
  let target = candidates[0]
  const current = selectedSku.value
  if (current) {
    const currentSpec = matchSpec(current) || {}
    const matching = candidates.filter((sku) =>
      Object.entries(matchSpec(sku) || {}).every(
        ([name, specValue]) => name === axisName || String(specValue) === String(currentSpec[name]),
      ),
    )
    if (matching.length) target = matching[0]
  }
  if (selectedSkuId.value === target.public_id) return
  selectedSkuId.value = target.public_id
  // 批次 DB：切规格时尽量停在同一个商家（该商家卖这个规格才切过去），
  // 否则清掉 offer 回到后端默认商家。
  const nextOfferId = preferredOfferId(target, offer.value)
  activeOfferId.value = nextOfferId
  // 批次 DA：把所选规格写进 URL（保留 offer/from 等其它参数），触发上面的
  // watcher refresh() 重取带 ?sku= 的详情；URL 因此可分享、可前进/后退。
  const query = variantQuery(route.query, target.public_id)
  if (nextOfferId) query.offer = nextOfferId
  else delete query.offer
  void router.replace({ query })
}

const baseGallery = computed(() => (Array.isArray(data.value?.gallery) ? data.value.gallery : []))
// 批次 DA（用户 2026-11-27 口径「有该规格自己的画廊数据就换，没有就不换」）：
// 画廊按 SKU 自己的档案图判定，与 share_metadata 无关。档案缺失/sku 未对上/
// 档案 gallery 为空 → galleryArchive 为 null → 保持 SPU 基础画廊（不出现空白）。
const galleryArchive = computed(() =>
  resolveGalleryArchive(data.value, selectedSku.value?.public_id),
)
// 档案有图用档案图；档案缺图回退保留 SPU 的图。
const gallery = computed(() => variantGallery(galleryArchive.value, baseGallery.value))
const videos = computed(() => (Array.isArray(data.value?.videos) ? data.value.videos : []))

// 画廊媒体：视频排在图片前面（Joybuy 详情页顺序），图片保持原顺序。
// 视频是 SPU 级数据（档案没有视频快照），切规格时不跟着换，但也**不能把视频
// 挤掉**：切完规格后视频仍排第一，用户点缩略图即可看新规格的图。
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
// 画廊随规格变化后回到第一项（旧 key 可能在新画廊里不存在）：媒体列表
// （含视频/图片）任一 key 变化即重置。
watch(
  () => mediaItems.value.map((item) => item.key).join('|'),
  () => {
    activeMediaKey.value = ''
  },
)
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

// 需求 20.3：入口与右下角 Crisp 客服启动器不重叠 → 入口显示期间隐藏 Crisp
// 挂件（body 类 + 页面级 :global 样式），离开页面或入口消失即恢复。
const CRISP_HIDE_CLASS = 'pdp-merchant-contact'
watch(
  canContactSeller,
  (hidden) => {
    if (typeof document === 'undefined') return
    document.body.classList.toggle(CRISP_HIDE_CLASS, hidden)
  },
  { immediate: true },
)

// 需求 21（批次 Y）：底部购物条出现时 body 挂 pdp-buybar-visible。购物条高
// 68px，全局【客服】（bottom 100）与【联系商家】（bottom 168）都在它上方，
// 不再需要随购物条上移；该类名保留给其它联动规则/后续调整使用。
const BUYBAR_CLASS = 'pdp-buybar-visible'
watch(
  stickyBarVisible,
  (visible) => {
    if (typeof document === 'undefined') return
    document.body.classList.toggle(BUYBAR_CLASS, visible)
  },
  { immediate: true },
)

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
  if (typeof document !== 'undefined') {
    document.body.classList.remove(CRISP_HIDE_CLASS)
    document.body.classList.remove(BUYBAR_CLASS)
  }
})

watch(
  () => mediaItems.value.length,
  () => nextTick(measureThumbs),
)

// ADR 0001: on the m. host the same detail payload renders the mobile PDP
// (docs/20 §2); the desktop template below is untouched. The mobile
// component is presentational — it receives the resolved state as props and
// emits actions back to the handlers above.
const { isMobileHost } = useMobileView()
// Same active-value basis as the desktop variant buttons (matchSpec).
const selectedSkuSpec = computed(() => matchSpec(selectedSku.value))

const contentSections = computed(() =>
  variantDetailField(
    variantArchive.value,
    'content_sections',
    Array.isArray(data.value?.content_sections) ? data.value.content_sections : [],
  ),
)
const specificationTables = computed(() =>
  variantDetailField(
    variantArchive.value,
    'specification_tables',
    Array.isArray(data.value?.specification_tables) ? data.value.specification_tables : [],
  ),
)
const aiSummaryText = computed(
  () => variantDetailField(variantArchive.value, 'ai_summary', data.value?.ai_summary || '') || '',
)

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

// 需求 22.1-6：面包屑每一级都可点击。商品类目（product_category）只有源站
// 数字 id；链接优先用后端增量返回的 ``local_slug``（ProductCategory →
// LocalCategory 映射），没有映射时按「父级 + 名称」在本地类目树里定位
// （见 utils/pdpBreadcrumb.js），链接口径 L1 → /minihome/<code>、
// L2 → /c/<slug>（复用 utils/categoryLinks）。类目名优先显示本地化名称
// （源站面包屑是中文原名）。
const breadcrumbNodes = computed(() => {
  const crumbs = productCategoryCrumb.value
  if (!crumbs.length) {
    return categoryTrail.value.map((node) => ({
      key: `trail-${node.slug}`,
      label: categoryName(node),
      to: categoryHref(node),
    }))
  }
  return resolveProductCategoryCrumbs(crumbs, categories.value, categoryName)
})

// 需求 22.1-5 / 23.1-2：商品名下方「评分 | 已售 x+ 件」，评价条数不展示。
// 评分用 review_summary（本地评价优先、爬虫快照兜底）；销量用后端已落库的
// sale_amount，接口返回 null 时才用确定性展示占位值（见 utils/pdpDisplay.js）。
// 批次 DA：share_metadata=false 的档案优先用自己的评分/已售快照（缺数据回退）。
const reviewSummary = computed(() =>
  variantReviewSummary(variantArchive.value, data.value?.review_summary || null),
)
const ratingAverage = computed(() => ratingAverageLabel(reviewSummary.value))
const soldAmount = computed(() => variantSoldAmount(variantArchive.value, data.value?.sale_amount))
const soldCount = computed(() => soldCountLabel(publicId.value, soldAmount.value))
// 移动端复用同一份 payload：把档案里的标题/评分/已售/详情覆盖进去，避免
// MobilePDP 读 base data 时「桌面变了、手机没变」。
const displayData = computed(() => {
  if (!variantArchive.value) return data.value
  return {
    ...(data.value || {}),
    title: displayTitle.value,
    review_summary: reviewSummary.value,
    sale_amount: soldAmount.value,
    content_sections: contentSections.value,
    specification_tables: specificationTables.value,
    ai_summary: aiSummaryText.value,
  }
})
// 需求 23.1-3：已售图标 tooltip，hover 与键盘 focus 都显示。
const soldTipOpen = ref(false)

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

// 服务承诺三项：真站为可展开 accordion（需求 22.1-3）。顺序按真站实测：
// 30 天退货 → 24/7 客户支持 → 厂家保修；行高 54、16px/600，展开正文
// 14px/20、行首无缩进，chevron 旋转 180°。
const guaranteeItems = computed(() => [
  {
    key: 'returns',
    label: t('detail.guaranteeReturns'),
    detail: t('pdp.guaranteeReturnsDetail'),
  },
  {
    key: 'support',
    label: t('detail.guaranteeSupport'),
    detail: t('pdp.guaranteeSupportDetail'),
  },
  {
    key: 'warranty',
    label: t('detail.guaranteeWarranty'),
    detail: t('pdp.guaranteeWarrantyDetail'),
  },
])

const openGuarantee = ref('')

function toggleGuarantee(key) {
  openGuarantee.value = openGuarantee.value === key ? '' : key
}

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

useHead(() => ({ title: displayTitle.value || 'Product' }))
</script>

<template>
  <MobilePDP
    v-if="isMobileHost"
    :data="displayData"
    :error="error"
    :media-items="mediaItems"
    :offer="offer"
    :price="price"
    :variant-axes="variantAxes"
    :selected-sku="selectedSku"
    :selected-sku-spec="selectedSkuSpec"
    :is-single-sku="isSingleSku"
    :readonly-spec="stickySpecText"
    :quantity="quantity"
    :add-state="addState"
    :wishlisted="wishlisted"
    :wish-pending="wishPending"
    :content-sections="contentSections"
    :specification-tables="specificationTables"
    :family-members="familyMemberList"
    :family-axis-name="familyAxisName"
    :merchants="skuMerchants"
    @select-variant="selectVariant"
    @change-quantity="changeQuantity"
    @add-to-cart="onAddToCart"
    @buy-now="onBuyNow"
    @toggle-wishlist="toggle(publicId)"
    @select-merchant="selectMerchant"
    @go-family-member="goToFamilyMember"
  />
  <div v-else class="detail-page-bg">
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
          <template v-for="node in breadcrumbNodes" :key="node.key">
            <span class="detail__crumb-sep" aria-hidden="true">/</span>
            <NuxtLink v-if="node.to" class="detail__crumb" :to="node.to">{{ node.label }}</NuxtLink>
            <span v-else class="detail__crumb">{{ node.label }}</span>
          </template>
          <span class="detail__crumb-sep" aria-hidden="true">/</span>
          <span class="detail__crumb detail__crumb--current">{{ displayTitle }}</span>
        </nav>
        <p v-if="data?.brand" class="detail__brandline">{{ data.brand }}</p>
        <h1 class="detail__title">{{ displayTitle }}</h1>

        <!-- 需求 22.1-5 / 23.1-2：商品名下方「评分 | 已售 x+ 件」。评价条数
             按 23.1-2 不展示；评分与已售之间的灰色竖线按用户口径保留。 -->
        <div v-if="data" class="detail__rating" data-testid="pdp-rating">
          <svg class="detail__rating-star" viewBox="0 0 20 20" aria-hidden="true">
            <path
              d="M10 1.6l2.5 5.2 5.7.8-4.1 4 1 5.6-5.1-2.7-5.1 2.7 1-5.6-4.1-4 5.7-.8z"
              fill="currentColor"
            />
          </svg>
          <span class="detail__rating-average">{{ ratingAverage }}</span>
          <span class="detail__rating-divider" aria-hidden="true"></span>
          <span
            class="detail__sold-block"
            @mouseenter="soldTipOpen = true"
            @mouseleave="soldTipOpen = false"
          >
            <span class="detail__sold" data-testid="pdp-sold">{{
              t('pdp.soldCount', { count: soldCount })
            }}</span>
            <!-- 需求 23.1-3：已售右侧图标，hover / 键盘 focus 显示「销量解读」。
                 真站同位置是 20px 图标按钮，弹层标题「销量解读」（英文站
                 Sales Details），链接 /help/salesdetails。 -->
            <button
              type="button"
              class="detail__sold-tip"
              data-testid="pdp-sold-tip"
              :aria-label="t('pdp.soldTooltipTitle')"
              :aria-describedby="soldTipOpen ? 'pdp-sold-tooltip' : undefined"
              @focus="soldTipOpen = true"
              @blur="soldTipOpen = false"
              @click="soldTipOpen = !soldTipOpen"
            >
              <svg viewBox="0 0 20 20" aria-hidden="true">
                <circle cx="10" cy="10" r="8.25" fill="none" stroke="currentColor" />
                <path
                  d="M10 8.6v5.1"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.6"
                  stroke-linecap="round"
                />
                <circle cx="10" cy="6.1" r="1" fill="currentColor" />
              </svg>
            </button>
            <span
              v-if="soldTipOpen"
              id="pdp-sold-tooltip"
              class="detail__sold-tooltip"
              role="tooltip"
            >
              <strong>{{ t('pdp.soldTooltipTitle') }}</strong>
              <span>{{ t('pdp.soldTooltip') }}</span>
            </span>
          </span>
        </div>

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
                    ? `${displayTitle} video ${index + 1}`
                    : `${displayTitle} thumbnail ${index + 1}`
                "
                @click="selectMedia(item)"
              >
                <img
                  v-if="item.type === 'image' || item.poster"
                  :src="item.type === 'image' ? item.url : item.poster"
                  :alt="
                    item.type === 'video'
                      ? `${displayTitle} video preview`
                      : `${displayTitle} thumbnail ${index + 1}`
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
            <img v-else-if="currentImage" :src="currentImage" :alt="displayTitle" />
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

          <div
            class="detail__panel"
            :data-offer-id="offer?.public_id || ''"
            :data-merchant-slug="offer?.merchant?.slug || ''"
          >
            <!-- 需求（2026-11-25）：价格区不再渲染任何促销徽标（如 "70% off"）；
                 后端 offer.promotion_label 保留，仅展示层不展示。 -->
            <div v-if="offer" class="detail__price-block">
              <p class="detail__price">{{ price }}</p>
            </div>
            <!-- 需求 20.1：URL 带入的商家 offer 不在此商品里 → 回落默认并明确提示。 -->
            <p v-if="offerFallbackNotice" class="detail__offer-notice" role="status">
              {{ t('chat.offerFallback') }}
            </p>
            <!-- 需求文档03 11.7：真站 PDP 无库存展示行（实测 var/reco_pdp_20261119/），
                 999+/库存数据字段保留在后端响应里，仅不再渲染。 -->
            <p v-if="!offer" class="detail__inventory detail__inventory--out" role="status">
              {{ t('product.unavailableShort') }}
            </p>

            <!-- 单 SKU/空规格：不做规格交互，只读展示唯一 SKU 的规格值。
                 spec_options 能解析成规格卡时（如只一个 Capacity 值）改走卡片，不重复出文本。 -->
            <p
              v-if="isSingleSku && stickySpecText && !variantAxes.length"
              class="detail__spec-readonly"
            >
              {{ stickySpecText }}
            </p>

            <!-- 批次 DB（Q9）：族内兄弟商品 = 外层「型号/系列」选择；点击整页跳转
                 到兄弟商品（真站做法），并尽量带上同一商家的 ?offer=。 -->
            <div v-if="hasFamilyAxis" class="detail__axis detail__axis--family">
              <h2 class="detail__axis-name">{{ familyAxisName }}</h2>
              <div class="detail__axis-values">
                <button
                  v-for="(member, index) in familyMemberList"
                  :key="member.spu_public_id"
                  type="button"
                  class="detail__variant detail__variant--link"
                  :class="{ 'detail__variant--active': member.is_current }"
                  :aria-current="member.is_current ? 'true' : undefined"
                  :data-family-spu="member.spu_public_id"
                  @click="goToFamilyMember(member)"
                >
                  <span>{{ memberLabel(member, index, familyAxisName) }}</span>
                </button>
              </div>
            </div>

            <div
              v-for="axis in variantAxes"
              :key="axis.name"
              class="detail__axis detail__axis--spec"
            >
              <h2 class="detail__axis-name">
                <span class="detail__axis-label">{{ axis.name }}:</span>
                <span class="detail__axis-selected">{{ axisSelectedValue(axis) }}</span>
              </h2>
              <div class="detail__axis-values">
                <button
                  v-for="value in axis.values"
                  :key="value.value"
                  type="button"
                  class="detail__variant"
                  :class="[
                    axis.has_image ? 'detail__variant--spec-image' : 'detail__variant--spec',
                    {
                      'detail__variant--active':
                        String(matchSpec(selectedSku)?.[axis.name]) === value.value ||
                        value.sku_ids.includes(selectedSku?.public_id),
                    },
                  ]"
                  @click="selectVariant(axis.name, value)"
                >
                  <img
                    v-if="value.image_url"
                    class="detail__variant-image"
                    :src="value.image_url"
                    alt=""
                  />
                  <span class="detail__variant-label">{{ value.value }}</span>
                </button>
              </div>
            </div>

            <!-- 批次 DB（Q9/Q10）：商家轴。同一规格可能多个商家在售，切换只改
                 价格/库存/加购 offer 与 URL，不重新拉整页数据。 -->
            <div v-if="hasMerchantAxis" class="detail__axis detail__axis--merchant">
              <h2 class="detail__axis-name">{{ t('detail.sellerAxis') }}</h2>
              <div class="detail__axis-values">
                <button
                  v-for="entry in skuMerchants"
                  :key="entry.public_id"
                  type="button"
                  class="detail__variant detail__variant--merchant"
                  :class="{ 'detail__variant--active': offer?.public_id === entry.public_id }"
                  :data-offer-id="entry.public_id"
                  :data-merchant-slug="entry.merchant?.slug || ''"
                  @click="selectMerchant(entry)"
                >
                  <span class="detail__merchant-name">{{ merchantLabel(entry) }}</span>
                  <span class="detail__merchant-price">{{ formatDisplayPrice(entry.price) }}</span>
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

            <!-- 需求 22.1-4：配送与服务承诺（位于 30 天退货上方），含销售及
                 配送方 + Joybuy 图标（真站 24px/600 标题、16px/500 销售方行）。 -->
            <section class="detail__promise" data-testid="pdp-delivery-promise">
              <h2 class="detail__promise-title">{{ t('pdp.deliveryTitle') }}</h2>
              <p class="detail__seller" data-testid="pdp-seller">
                <span>{{ t('pdp.sellerLabel') }}</span>
                <img
                  class="detail__seller-logo"
                  src="/images/news/logo.svg"
                  alt="Joybuy"
                  width="66"
                  height="18"
                />
              </p>
            </section>

            <!-- 需求 22.1-3：三项服务承诺可点击展开；chevron 展开时旋转。 -->
            <ul class="detail__guarantees">
              <li
                v-for="item in guaranteeItems"
                :key="item.key"
                class="detail__guarantee"
                :class="{ 'detail__guarantee--open': openGuarantee === item.key }"
              >
                <button
                  class="detail__guarantee-summary"
                  type="button"
                  :aria-expanded="openGuarantee === item.key"
                  @click="toggleGuarantee(item.key)"
                >
                  <span>{{ item.label }}</span>
                  <svg
                    class="detail__guarantee-caret"
                    viewBox="0 0 24 24"
                    width="24"
                    height="24"
                    aria-hidden="true"
                  >
                    <path
                      d="M6 9.5l6 6 6-6"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="1.8"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                  </svg>
                </button>
                <div v-if="openGuarantee === item.key" class="detail__guarantee-detail">
                  <p>{{ item.detail }}</p>
                </div>
              </li>
            </ul>

            <!-- 需求 22.1-1：【我们支持】+ 支付图标紧跟购买区（真站 footer 实测
                 14px/400 #505259、图标 32x20；位置按本轮要求放在右栏购买区下方）。 -->
            <section class="detail__support" aria-labelledby="support-heading">
              <h2 id="support-heading" class="detail__support-title">
                {{ t('pdp.supportTitle') }}
              </h2>
              <ul class="detail__support-icons">
                <li v-for="icon in paymentIcons" :key="icon.alt">
                  <img :src="icon.src" :alt="icon.alt" width="32" height="20" loading="lazy" />
                </li>
              </ul>
            </section>
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
              :alt="`${section.title || displayTitle} ${imageIndex + 1}`"
              loading="lazy"
              decoding="async"
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
        :review-summary="reviewSummary"
      />

      <!-- 我们支持已移到右栏购买区下方（需求 22.1-1），页面底部不再渲染。 -->

      <!-- 底部吸附购物条：滑过主图区后固定显示，滑回顶部即消失（Joybuy 交互）。 -->
      <div v-if="stickyBarVisible && data" class="buy-bar">
        <div class="buy-bar__inner">
          <img
            v-if="currentImage || gallery[0]?.url"
            class="buy-bar__thumb"
            :src="currentImage || gallery[0]?.url"
            :alt="displayTitle"
          />
          <div class="buy-bar__info">
            <p class="buy-bar__title">{{ displayTitle }}</p>
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

      <!-- 需求 20.3：PDP 右下角【联系商家】（2026-11-27 起与【客服】同款：
           贴右边缘、80 宽、图标 24 在上文字 12px 在下，纵向堆在【客服】上方）。
           入口显示期间 Crisp 启动器由 body 类隐藏，避免与业务按钮在右下角重叠。 -->
      <button
        v-if="canContactSeller"
        class="detail__contact"
        type="button"
        data-testid="pdp-contact-seller"
        @click="chatOpen = true"
      >
        <svg viewBox="0 0 20 20" width="24" height="24" aria-hidden="true">
          <path
            d="M3 4.5h14v9H8.5L5 16.5v-3H3z"
            fill="none"
            stroke="currentColor"
            stroke-width="1.4"
            stroke-linejoin="round"
          />
        </svg>
        <span>{{ t('chat.contactSeller') }}</span>
      </button>

      <MerchantChatPanel
        :open="chatOpen"
        :merchant="chatMerchant"
        @close="chatOpen = false"
        @blocked="onChatBlocked"
      />

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

/* Top nav: Home / categories / product, clickable like the real site
   (real 16px/500, gap 8, margin-bottom 16). */
.detail__crumbs {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 24px;
  margin-bottom: 16px;
  overflow: hidden;
  white-space: nowrap;
  font-size: 16px;
  font-weight: 500;
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

/* 需求 22.1-5 / 23.1-2：商品名下方「评分 | 已售」，真站 16px/400 黑字、
   行高 38px；不再显示评价条数。 */
.detail__rating {
  display: flex;
  align-items: center;
  min-height: 38px;
  margin: -8px 0 12px;
  font-size: 16px;
  line-height: 24px;
  color: #1a1a1a;
}

.detail__rating-star {
  width: 16px;
  height: 16px;
  margin-right: 4px;
  color: #1a1a1a;
}

.detail__rating-average {
  margin-right: 8px;
}

/* 用户口径：评分与已售之间保留灰色竖线（真站同位置也有 divisionLine）。 */
.detail__rating-divider {
  flex: none;
  width: 1px;
  height: 14px;
  margin: 0 8px 0 0;
  background: #e0e1e5;
}

/* 需求 23.1-3：已售文案 + 右侧 20px 图标 + hover/focus tooltip。 */
.detail__sold-block {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.detail__sold-tip {
  display: inline-flex;
  width: 20px;
  height: 20px;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 0;
  background: none;
  color: #757a82;
  cursor: pointer;
}

.detail__sold-tip svg {
  width: 18px;
  height: 18px;
}

.detail__sold-tip:hover,
.detail__sold-tip:focus-visible {
  color: #1a1a1a;
}

.detail__sold-tip:focus-visible {
  outline: 2px solid #1a1a1a;
  outline-offset: 1px;
  border-radius: 50%;
}

.detail__sold-tooltip {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: max-content;
  max-width: min(320px, 70vw);
  padding: 8px 10px;
  border: 1px solid #e0e1e5;
  border-radius: 6px;
  background: var(--colour-white, #ffffff);
  box-shadow: 0 4px 16px rgb(0 0 0 / 12%);
  color: #505259;
  font-size: 12px;
  line-height: 18px;
  font-weight: 400;
  z-index: 30;
}

.detail__sold-tooltip strong {
  color: #1a1a1a;
  font-size: 12px;
  font-weight: 600;
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

/* 需求 22.1-7：主图圆角（真站 wrapper radius 16px）+ 背景 #F5F5F5。
   圆角加在图片本身而非容器 overflow:hidden，否则悬停放大层会被裁掉。 */
.detail__image {
  position: relative;
  border-radius: 16px;
  background: #f5f5f5;
}

.detail__image img {
  display: block;
  width: 100%;
  aspect-ratio: 1;
  border-radius: 16px;
  object-fit: cover;
  background: #f5f5f5;
}

/* 画廊视频：与主图同尺寸，完整显示不裁切（竖屏视频也不变形）。 */
.detail__video {
  display: block;
  width: 100%;
  aspect-ratio: 1;
  border-radius: 16px;
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

/* --- 规格轴（真站 imageDimensionItem / seriesDimension 实测复刻）---------
   数值来源：var/pdp_spec_ui_20261127/measurements.md（1440 宽 getComputedStyle）。
   真站按「该维度有没有规格图」二选一渲染：图片卡 80×103（图 72×72 在上、名在下）
   或文字胶囊（padding 8px 12px）。选中态只换边框色 + 字重 600，底色/文字色不变。
   作用域限定 --spec，避免影响族轴（--family）与商家轴（--merchant）。 */
.detail__axis--spec {
  padding: 12px 0;
}

.detail__axis--spec .detail__axis-name {
  color: #1a1a1a;
  font-size: 16px;
  font-weight: 500;
  line-height: 22px;
  text-transform: none;
  margin-bottom: 12px;
}

.detail__axis--spec .detail__axis-label {
  margin-right: 4px;
}

.detail__axis--spec .detail__axis-selected {
  font-weight: 600;
}

.detail__axis--spec .detail__axis-values {
  gap: 8px;
  margin-top: 0;
}

/* 图片型：竖向卡片，图在上、名在下。 */
.detail__variant--spec-image {
  flex-direction: column;
  align-items: center;
  gap: 0;
  width: 80px;
  min-height: 36px;
  padding: 3px;
  border-color: transparent;
  border-radius: 4px;
  background: #f5f6fa;
  color: #1a1a1a;
}

.detail__variant--spec-image .detail__variant-image {
  width: 72px;
  height: 72px;
  border-radius: 3px;
  object-fit: contain;
  background: #fff;
}

.detail__variant--spec-image .detail__variant-label {
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

/* 文字型：只有名称的胶囊。 */
.detail__variant--spec {
  gap: 0;
  min-height: 36px;
  padding: 8px 12px;
  border-color: transparent;
  border-radius: 4px;
  background: #f5f6fa;
  color: #1a1a1a;
  font-size: 14px;
  font-weight: 500;
  line-height: 20px;
}

.detail__variant--spec-image:hover,
.detail__variant--spec:hover {
  background: rgba(0, 16, 71, 0.06);
}

/* 选中态：边框 #1a1a1a、字重 600；底色与文字色保持未选中值。 */
.detail__variant--spec-image.detail__variant--active,
.detail__variant--spec.detail__variant--active {
  border-color: #1a1a1a;
  background: #f5f6fa;
  color: #1a1a1a;
}

.detail__variant--spec.detail__variant--active {
  font-weight: 600;
}

.detail__variant--spec-image.detail__variant--active .detail__variant-label {
  font-weight: 600;
}

/* 批次 DB（Q9）：族内兄弟商品（整页跳转）与商家轴按钮。 */
.detail__variant--link {
  text-decoration: none;
}

.detail__variant--merchant {
  flex-direction: column;
  align-items: flex-start;
  gap: 0;
  padding: 6px var(--space-4);
}

.detail__merchant-name {
  font-size: var(--font-size-sm);
}

.detail__merchant-price {
  color: var(--colour-muted);
  font-size: var(--font-size-xs);
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

/* 需求 22.1-4 / 23.1-1：配送与服务承诺。真站 section padding 8px 0、标题
   24px/600 line-height 48，销售方行 16px/500 line-height 22。
   横线按 23.1-1：只在【配送与服务承诺】顶部一条（真站独立分隔元素
   0.5px #E0E1E5 margin 12px 0；这里用等价的 1px border + 12px 上下留白，
   见 HANDOFF 0bp）。 */
.detail__promise {
  margin-top: 12px;
  padding: 12px 0 0;
  border-top: 1px solid #e0e1e5;
}

.detail__promise-title {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  line-height: 48px;
  color: #1a1a1a;
}

.detail__seller {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 16px;
  font-weight: 500;
  line-height: 22px;
  color: #1a1a1a;
}

.detail__seller-logo {
  display: block;
  width: auto;
  height: 18px;
}

/* 需求 22.1-3 / 23.1-1：服务承诺 accordion。真站行高 54、16px/600、右内边距
   16，展开正文 14px/400 line-height 20、底部留白 20，chevron 展开旋转 180°。
   23.1-1：承诺行之间、列表上下都不画横线（真站承诺行本身无 border）。 */
.detail__guarantees {
  list-style: none;
  margin: 0;
  padding: 0;
}

.detail__guarantee-summary {
  display: flex;
  width: 100%;
  min-height: 54px;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px 0 0;
  border: 0;
  background: none;
  color: #1a1a1a;
  font: inherit;
  font-size: 16px;
  font-weight: 600;
  line-height: 22px;
  text-align: left;
  cursor: pointer;
}

.detail__guarantee-caret {
  flex: none;
  transition: transform 180ms ease;
}

.detail__guarantee--open .detail__guarantee-caret {
  transform: rotate(180deg);
}

.detail__guarantee-detail p {
  margin: 0;
  padding: 0 16px 20px 0;
  color: #1a1a1a;
  font-size: 14px;
  font-weight: 400;
  line-height: 20px;
  white-space: pre-line;
}

/* 需求 22.1-1：我们支持 + 支付图标（真站 footer_footerPay 实测：标题
   14px/400 #505259 margin-right 16px，图标各 32x20），现位于右栏购买区下方。 */
/* 需求 22.1-1 / 23.1-1：我们支持 + 支付图标（真站 footer_footerPay 实测：
   标题 14px/400 #505259 margin-right 16px，图标各 32x20）。横线按 23.1-1
   只在这一块顶部一条（与【配送与服务承诺】顶部同规格）。 */
.detail__support {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px 0;
  margin-top: 12px;
  padding: 12px 0 0;
  border-top: 1px solid #e0e1e5;
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
  /* 与 Joybuy 一致：一张图占一行，但按原图宽度显示、左对齐，不放大
     （功能需求迭代文档03 §24；真站 .Image_longImageWrap > .Image_longImage 实测行为）。 */
  grid-template-columns: minmax(0, 1fr);
  justify-items: start;
  gap: var(--space-4);
  margin-top: var(--space-4);
}

.detail__content-images img {
  display: block;
  /* 原图窄于容器时保持原宽（左对齐、右侧留白）；宽于容器时才等比缩到容器宽。 */
  width: auto;
  max-width: 100%;
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
  overflow: visible;
  color: #1a1a1a;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-bold);

  white-space: normal;
  word-break: break-word;
}

.buy-bar__spec {
  margin-top: 2px;
  overflow: visible;
  color: var(--colour-text-secondary);
  font-size: var(--font-size-sm);

  white-space: normal;
  word-break: break-word;
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

/* 需求 20.1：商家 offer 未命中时的回落提示（浅橙底，不抢占商品主信息）。 */
.detail__offer-notice {
  margin: 0;
  padding: 10px 12px;
  border: 1px solid #f3c9a2;
  border-radius: 6px;
  background: #fff6ec;
  color: #8a4b12;
  font-size: var(--font-size-sm);
}

/* 需求 20.3：PDP 右下角【联系商家】浮动入口。
   2026-11-27 用户要求：样式与全站右下角【客服】入口完全同款
   （SupportChatLauncher 的 .support-chat__launcher，真站 #jdi-floating-toolbar
   实测）：贴右边缘 right 0、宽 80、白底、1px rgba(0,0,0,.059) 左边框（无右边框）、
   圆角 8px 0 0 8px、图标 24px 在上、文字 12px 在下、hover 仅文字下划线。
   位置：与【客服】（bottom 100、高 60，顶边 160）纵向堆叠，底边 168（留 8px gap），
   两者不重叠；底部购物条只有 68px 高，两者都在它上方，无需随购物条上移。 */
.detail__contact {
  position: fixed;
  right: 0;
  bottom: 168px;
  z-index: 45;
  box-sizing: border-box;
  display: inline-flex;
  width: 80px;
  /* 与【客服】同宽同款：单行文案（如 联系商家）渲染 62px（图标 24 + gap 4 +
     文字 16 + 内边距 16 + 边框 2，与客服按钮 60px 只差 2px 的可视误差）；
     EN 的 Contact seller 在 80px 宽内必然折两行 → 按内容变高（78）。
     图标/字号/内边距/边框/圆角都与客服完全一致。 */
  min-height: 60px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: auto;
  gap: 4px;
  padding: 8px 5px;
  border: 1px solid rgb(0 0 0 / 5.9%);
  border-right: none;
  border-radius: 8px 0 0 8px;
  background: #fff;
  box-shadow: none;
  color: #1a1a1a;
  font: inherit;
  font-size: 12px;
  line-height: 16px;
  white-space: normal;
  cursor: pointer;
  transition: bottom 160ms ease;
}

.detail__contact svg {
  flex: none;
}

.detail__contact span {
  font-size: 12px;
  line-height: 16px;
  text-align: center;
}

.detail__contact:hover {
  background: #fff;
  text-decoration: underline;
}

.detail__contact:focus-visible {
  outline: 2px solid var(--colour-focus-ring);
  outline-offset: 2px;
}

/* 小屏（≤40rem，例如 375 宽窗口）与【客服】同步收窄到 72 宽：
   客服 bottom 84（顶边 144），入口底边 152 保持 8px gap。 */
@media (max-width: 40rem) {
  .detail__contact {
    bottom: 152px;
    width: 72px;
  }
}

/* 入口显示期间隐藏 Crisp 启动器，避免与业务按钮在右下角重叠。 */
:global(body.pdp-merchant-contact #crisp-chatbox),
:global(body.pdp-merchant-contact .crisp-client) {
  display: none !important;
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
