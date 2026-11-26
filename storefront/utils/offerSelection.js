// PDP offer→SKU 选择（需求 20.1）。
//
// 多个商家上架同一 SPU 时，PDP 默认「第一个可购 SKU」会把从商家 A 进入的
// 用户带到商家 B 的 offer。商家店铺页链接带 ?offer=<offer_id>&from=merchant，
// 这里负责优先命中该 offer 的 SKU；找不到时回落到默认 SKU（页面再提示）。
//
// 批次 DB（2026-11-27）：SKU 现在带**全部商家**的 offer 列表（sku.offers），
// 用户切商家后 URL 的 offer 可能不在 sku.offer（后端默认那个）上，因此这里
// 也要在 sku.offers 里匹配，否则切商家会把所选规格弹回 SKU[0]。
export function findSkuForOffer(skus, offerPublicId) {
  if (!offerPublicId || !Array.isArray(skus)) return null
  return (
    skus.find((sku) => sku?.offer?.public_id === offerPublicId) ||
    skus.find((sku) =>
      (Array.isArray(sku?.offers) ? sku.offers : []).some(
        (offer) => offer?.public_id === offerPublicId,
      ),
    ) ||
    null
  )
}

// 选择顺序：用户手动点选的 SKU → URL 带入 offer 的 SKU → 默认第一个可购 SKU。
export function resolveSelectedSku(skus, selectedSkuId, offerPublicId) {
  if (!Array.isArray(skus) || !skus.length) return null
  const explicit = skus.find((sku) => sku.public_id === selectedSkuId)
  return explicit || findSkuForOffer(skus, offerPublicId) || skus[0] || null
}
