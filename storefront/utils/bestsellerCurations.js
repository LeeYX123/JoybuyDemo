// Home floor 【畅销榜单 / Bestsellers】curation rules (2026-11-27).
//
// Some tabs must not simply take the newest N products of the whole category
// subtree: the user asked for a fixed mix of two sub-categories, e.g.
// 家居生活 = 家具 3 + 床上用品 2 and 健康保健 = 维生素&补充剂 3 + 运动&体能 2.
//
// This module only holds the config plus the pure composition function.
// Fetching/fallback lives in `composables/useBestsellerFeed.js` so the desktop
// and mobile floors share exactly one implementation.
//
// Tabs that are not listed here keep the original behaviour: one
// `/api/v1/search?category=<slug>&sort=newest&page=1` request, first N items.

// Each segment is fetched with one plain search page (the API answers with 24
// items and ignores `page_size` as of 2026-11-27), which is far more than a
// 3-item segment needs; the extra candidates exist so de-duplication or an
// unusable card does not immediately starve the segment.
export const BESTSELLER_CURATIONS = {
  // 家居生活 (home-living, local_category id 2)
  'home-living': [
    { category: 'furniture', count: 3 }, // 家具 (id 114)
    { category: 'bedding-textiles', count: 2 }, // 床上用品 (id 5)
  ],
  // 健康保健 (health-wellness, local_category id 21)
  'health-wellness': [
    { category: 'nutrition-supplements', count: 3 }, // 维生素 & 补充剂 (id 22)
    { category: 'sports-nutrition-performance', count: 2 }, // 运动 & 体能 (id 74)
  ],
}

/**
 * Segments for a tab slug, or null when the tab keeps the plain single request.
 */
export function bestsellerSegments(slug) {
  const segments = BESTSELLER_CURATIONS[slug]
  return Array.isArray(segments) && segments.length > 0 ? segments : null
}

/** How many cards the curated row shows (sum of the configured counts). */
export function curationTotal(segments) {
  return segments.reduce((total, segment) => total + segment.count, 0)
}

/**
 * A card is worth showing only when the search payload still has the fields
 * the card renders. The API already filters unsellable products and hides
 * non-representative family members; this guard only refuses to fill a curated
 * slot with a card that would render broken (no image / no price).
 */
export function isRenderableCard(item) {
  if (!item || !item.spu_public_id) return false
  if (item.is_family_representative === false) return false
  const image = item.image_path || item.image
  if (typeof image !== 'string' || !image.trim()) return false
  const prices = [item.retail_price, item.family_max_price, item.price_min, item.price]
  return prices.some(
    (price) => price !== null && price !== undefined && String(price).trim() !== '',
  )
}

/**
 * Compose the curated row from per-segment candidate lists.
 *
 * - Segment order is preserved (primary sub-category first).
 * - Each segment contributes up to `count` unique products.
 * - One `spu_public_id` appears at most once; a duplicate never consumes a
 *   slot, so the next candidate of that segment is used instead.
 * - When a segment runs short, unused candidates of the other segment top the
 *   row up to `limit`.
 *
 * @returns {{ items: object[], complete: boolean }} `complete` is false when
 *   the candidates could not fill the row; the caller then falls back to the
 *   tab's original single-request list.
 */
export function composeCuratedItems(segments, candidateLists, limit = curationTotal(segments)) {
  const picked = []
  const seen = new Set()
  // Candidates beyond a segment's count are kept for the final top-up; they
  // are reserved so another segment cannot claim them as one of its own slots
  // (that would give the row 3 + 3 while still looking "deduped").
  const reserved = new Set()
  const spare = []

  segments.forEach((segment, index) => {
    const candidates = Array.isArray(candidateLists[index]) ? candidateLists[index] : []
    let taken = 0
    for (const item of candidates) {
      if (!isRenderableCard(item)) continue
      const id = item.spu_public_id
      if (seen.has(id) || reserved.has(id)) continue
      if (taken >= segment.count) {
        reserved.add(id)
        spare.push(item)
        continue
      }
      seen.add(id)
      picked.push(item)
      taken += 1
    }
  })

  for (const item of spare) {
    if (picked.length >= limit) break
    const id = item.spu_public_id
    if (seen.has(id)) continue
    seen.add(id)
    picked.push(item)
  }

  return { items: picked.slice(0, limit), complete: picked.length >= limit }
}
