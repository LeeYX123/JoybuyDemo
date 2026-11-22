// PDP 顶部「评分 + 已售」展示值（需求文档03 22.1-5）。
//
// 真站口径：商品名下方一行「★ 4.8 (70+ 评价) | 已售 7k+ 件」。评分来自详情
// 接口的 review_summary；销量用后端已落库的 SpuDetail.sale_amount（详情接口
// 顶层 sale_amount，展示字符串如 "10k+"）。只有接口返回 null（没有
// SpuDetail 行）时才用 public_id 的 FNV-1a 哈希生成 10k–30k 的**展示占位**
// 值：同一商品每次刷新结果完全一致，绝不是运行时随机数，也不覆盖真实数据。
const SOLD_MIN_K = 10
const SOLD_MAX_K = 30

function hashString(value) {
  let hash = 2166136261
  const text = String(value || '')
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return Math.abs(hash)
}

export function soldCountLabel(publicId, saleAmount) {
  const stored = String(saleAmount || '').trim()
  if (stored) return stored
  const span = SOLD_MAX_K - SOLD_MIN_K + 1
  return `${SOLD_MIN_K + (hashString(publicId) % span)}k+`
}

export function ratingAverageLabel(reviewSummary) {
  const average = Number(reviewSummary?.average)
  return Number.isFinite(average) && average > 0 ? average.toFixed(1) : '—'
}

export function ratingCountLabel(reviewSummary) {
  const count = Number(reviewSummary?.count)
  return Number.isFinite(count) && count > 0 ? Math.round(count) : 0
}
