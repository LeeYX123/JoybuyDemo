// PDP 顶部「评分 | 已售」展示值（需求文档03 22.1-5、23.1-2/3）。
//
// 真站口径：商品名下方一行「★ 4.8 | 已售 7k+ 件」；评价条数按 23.1-2 不再
// 展示。评分来自详情接口的 review_summary；销量用后端已落库的
// SpuDetail.sale_amount（详情接口顶层 sale_amount，展示字符串如 "10k+"）。
// 只有接口返回 null（没有 SpuDetail 行）时才用 public_id 的 FNV-1a 哈希生成
// 10k–30k 的**展示占位**值：同一商品每次刷新结果完全一致，绝不是运行时
// 随机数，也不覆盖真实数据。
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

function trimNumber(value) {
  return String(Number(Number(value).toFixed(1)))
}

// 需求 23.1-3：已售展示值必须带「+」。源站串里 13,691 条本身带 +（如
// "1.5k+"），但还有 2,920 条是纯数字（如 "461"），直接透出会变成「已售461件」。
// 纯数字按真站风格缩写：>= 1000 → k（12000→12k+、1500→1.5k+），< 1000 → 原数
// 取整（40→40+）；已带单位/加号的归一化后原样保留（"1.5k+"→"1.5k+"）。
export function soldCountLabel(publicId, saleAmount) {
  const stored = String(saleAmount || '').trim()
  if (!stored) {
    const span = SOLD_MAX_K - SOLD_MIN_K + 1
    return `${SOLD_MIN_K + (hashString(publicId) % span)}k+`
  }
  const match = /^([0-9]+(?:\.[0-9]+)?)\s*([kKmM]?)\+?$/.exec(stored.replaceAll(',', ''))
  if (!match) return stored.endsWith('+') ? stored : `${stored}+`
  const numeric = Number(match[1])
  const unit = match[2].toLowerCase()
  if (unit) return `${trimNumber(numeric)}${unit}+`
  if (numeric >= 1000) return `${trimNumber(Math.round(numeric / 100) / 10)}k+`
  return `${Math.round(numeric)}+`
}

export function ratingAverageLabel(reviewSummary) {
  const average = Number(reviewSummary?.average)
  return Number.isFinite(average) && average > 0 ? average.toFixed(1) : '—'
}
