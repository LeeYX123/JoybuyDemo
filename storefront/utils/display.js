// Storefront display rules for prices and promo badges.
//
// These rules live purely in the display layer; crawled and stored data is
// never rewritten to match them.
//
// - Prices render with the "$" symbol everywhere (site-wide rule, 2026-11-27):
//   the user explicitly requires "$" across the whole storefront, overriding
//   the 2026-11-27 GBP attempt. Amounts are formatted with en-US.
// - Delivery-estimate labels ("arrives today" style) are never rendered;
//   matching badge text is suppressed at render time (2026-11-03 requirement).
// - Discount/promotion labels ("70% off", "Save 60% on RRP", "-30%", "满减")
//   are never rendered either; matching label text is suppressed at render
//   time (2026-11-25 requirement). Backend data keeps its `promotion_label`.

export function formatDisplayPrice(value) {
  if (value === null || value === undefined || value === '') {
    return null
  }
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) {
    return null
  }
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(numeric)
  } catch {
    return `$${numeric.toFixed(2)}`
  }
}

const DELIVERY_LABEL_PATTERN =
  /(今日|明天|明日|送达|送货|\b(?:deliver\w*|dispatch\w*|ship\w*|arriv\w*|get it by)\b)/i

export function isDeliveryLabel(text) {
  return typeof text === 'string' && DELIVERY_LABEL_PATTERN.test(text)
}

// Product marketing labels that must never reach the page: percentage-off
// badges, "Save x%", struck-through style wording, and the usual Chinese
// discount phrases. Crawled values stay in the database untouched.
const PROMO_LABEL_PATTERN =
  /(\d+\s*%\s*off|\d+\s*%\s*折扣|save\s*\d+\s*%|-?\d+\s*%\s*(?:off|优惠)|-\s*\d+\s*%|优惠\s*\d+|折扣|立减|满减|促销|discount|promotion|was\s*[$£€])/i

export function isPromoLabel(text) {
  return typeof text === 'string' && PROMO_LABEL_PATTERN.test(text)
}
