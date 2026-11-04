// Storefront display rules for prices and promo badges.
//
// These rules live purely in the display layer; crawled and stored data is
// never rewritten to match them.
//
// - Every price is rendered with the US dollar symbol regardless of the
//   currency stored on the source data (2026-11-03 requirement).
// - Delivery-estimate labels ("arrives today" style) are never rendered;
//   matching badge text is suppressed at render time (2026-11-03 requirement).

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
