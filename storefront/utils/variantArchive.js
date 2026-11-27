// PDP 切规格的「变体档案」解析（批次 DA，2026-11-27）。
//
// 后台 `GET /api/v1/products/<id>?sku=<sku_public_id>` 会返回 `variant_archive`：
// - share_metadata = true（纯尺码/数量变体）：只切价格/库存/规格，档案里的
//   画廊/评分/详情一律**不采用**（用户 2026-11-27 拍板 Q1）；
// - share_metadata = false（型号/颜色等差异）：整套切换（画廊、评分、已售、
//   图文详情、标题）；档案缺图/缺详情时逐字段回退保留 SPU 的 base 数据。
//
// 这里的函数全部是纯函数，vitest 覆盖 true/false 两条路径。

export function resolveVariantArchive(payload, selectedSkuId) {
  const archive = payload?.variant_archive
  if (!archive) return null
  // 保守口径：只有明确不等于 true 的档案才允许换元数据（未知一律不换）。
  if (archive.share_metadata !== false) return null
  if (!selectedSkuId || String(archive.sku) !== String(selectedSkuId)) return null
  return archive
}

// 画廊是「数据驱动」的（用户 2026-11-27 口径）：只要当前选中的 SKU 在档案里
// 有自己的图，就换；档案缺失 / gallery 为空 / sku 对不上，一律保持 SPU 基础
// 画廊（不换，也绝不换成空画廊）。
//
// 注意：这里**不**看 share_metadata。share_metadata 只决定标题/评分/已售/详情
// 这些「整套元数据」要不要跟着换；画廊按各自 SKU 是否有图单独判定，所以纯尺码
// 规格只要自带一整套图也会换图。
export function resolveGalleryArchive(payload, selectedSkuId) {
  const archive = payload?.variant_archive
  if (!archive) return null
  if (!selectedSkuId || String(archive.sku) !== String(selectedSkuId)) return null
  const gallery = Array.isArray(archive.gallery) ? archive.gallery.filter(Boolean) : []
  return gallery.length ? archive : null
}

export function variantGallery(archive, baseGallery) {
  const gallery = Array.isArray(archive?.gallery) ? archive.gallery.filter(Boolean) : []
  if (gallery.length) return gallery
  return Array.isArray(baseGallery) ? baseGallery : []
}

export function variantTitleText(archive, baseTitle) {
  return archive?.title || baseTitle || ''
}

export function variantReviewSummary(archive, baseReview) {
  const summary = archive?.review_summary
  if (!summary) return baseReview || null
  const hasRating =
    (summary.average !== null && summary.average !== undefined && summary.average !== '') ||
    Number(summary.count || 0) > 0
  return hasRating ? summary : baseReview || null
}

export function variantSoldAmount(archive, baseAmount) {
  if (archive && typeof archive.sale_amount === 'string' && archive.sale_amount) {
    return archive.sale_amount
  }
  return baseAmount ?? null
}

// 档案 detail 逐字段回退：空数组/空串视为「没抓到」，继续用 base。
export function variantDetailField(archive, key, fallback) {
  const detail = archive?.detail
  if (!detail || !(key in detail)) return fallback
  const value = detail[key]
  if (value === null || value === undefined) return fallback
  if (Array.isArray(value) && value.length === 0) return fallback
  if (typeof value === 'string' && value === '') return fallback
  return value
}

// URL 查询串：切规格写 ?sku=，其它参数（offer/from）原样保留。
export function variantQuery(routeQuery, skuId) {
  const next = { ...(routeQuery || {}) }
  if (skuId) next.sku = String(skuId)
  else delete next.sku
  return next
}
