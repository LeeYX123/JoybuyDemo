// 同款族（批次 DB，2026-11-27）：PDP「规格 × 商家」两级选择 + 兄弟商品跳转。
//
// 数据结构（后端 GET /api/v1/products/<id>）：
//   variant_family = {
//     family_key, kind, axis_name, axis_hint, representative_spu_public_id, is_representative,
//     members: [{ spu_public_id, title, axis_label, is_current, price_min, price_max,
//                 skus: [{ sku_public_id, axis_label, specification, offers: [offer…] }] }]
//   }
// 合并族（1 SPU 多 SKU）的 variant_family 为 null，仍走 DA 的 ?sku= 档案。
//
// 本模块只做纯计算，方便 vitest 覆盖（不依赖 Nuxt）。

/** 族成员列表（只保留有可购 offer 的成员；当前商品永远在列表里）。 */
export function familyMembers(detail) {
  const family = detail?.variant_family
  const members = Array.isArray(family?.members) ? family.members : []
  if (members.length < 2) return []
  return members
}

/** 某个 SKU 的全部商家 offer（后端 ``skus[].offers``，按价格升序）。 */
export function merchantOffers(sku) {
  const offers = Array.isArray(sku?.offers) ? sku.offers.filter(Boolean) : []
  if (offers.length) return offers
  return sku?.offer ? [sku.offer] : []
}

/**
 * 当前生效的 offer：URL/用户选的 offer 命中则用它，否则用后端默认 offer。
 * 返回 null 表示该规格无任何商家在售。
 */
export function resolveActiveOffer(sku, offerPublicId) {
  const offers = merchantOffers(sku)
  if (!offers.length) return null
  if (offerPublicId) {
    const matched = offers.find((offer) => offer.public_id === offerPublicId)
    if (matched) return matched
  }
  return sku?.offer || offers[0] || null
}

/** 切到某规格时尽量保持同一商家（跨规格保留商家上下文）。 */
export function preferredOfferId(sku, currentOffer) {
  const offers = merchantOffers(sku)
  if (!offers.length) return ''
  const merchantId = currentOffer?.merchant?.public_id
  if (merchantId) {
    const sameMerchant = offers.find((offer) => offer.merchant?.public_id === merchantId)
    if (sameMerchant) return sameMerchant.public_id
  }
  return ''
}

/**
 * 点兄弟商品时的跳转目标：``/p/<兄弟 SPU>`` + 尽量带上同一商家的 ``?offer=``。
 *
 * 优先在兄弟商品的任一个 SKU 里找「当前商家」的 offer（Q10：默认选中该商家）；
 * 找不到就不带 offer（对方页面按默认商家展示）。``from=merchant`` 原样带上。
 */
export function siblingTarget(member, currentOffer, routeQuery = {}) {
  const query = {}
  const merchantId = currentOffer?.merchant?.public_id
  if (merchantId) {
    for (const sku of member?.skus || []) {
      const matched = (sku.offers || []).find((offer) => offer.merchant?.public_id === merchantId)
      if (matched) {
        query.offer = matched.public_id
        break
      }
    }
  }
  if (routeQuery?.from) query.from = routeQuery.from
  return { path: `/p/${member?.spu_public_id || ''}`, query }
}

/** 已知规格轴名（没有后端 axis_name 时的兜底白名单，仅用于判断前缀能否安全剥掉）。 */
const KNOWN_AXIS_NAMES = new Set([
  'colour',
  'color',
  'size',
  'style',
  'model',
  'colour/colour',
  'color/colour',
  '颜色',
  '尺码',
  '型号',
  '系列',
  '规格',
])

/**
 * 去掉「规格名: 值」里的规格名前缀（DB axis_label 形如 "Colour: 黑色3"）。
 * 只按第一个 ": " 切分，且前缀必须是已知规格名 —— 否则像 "Ratio 16: 9" 这种
 * 值本身带冒号的标签会被切坏。
 */
export function stripAxisPrefix(label, axisName = '') {
  const text = String(label || '').trim()
  const separator = text.indexOf(': ')
  if (separator <= 0) return text
  const prefix = text.slice(0, separator).trim().toLowerCase()
  const known = axisName ? String(axisName).trim().toLowerCase() : ''
  if (known ? prefix === known : KNOWN_AXIS_NAMES.has(prefix)) {
    return text.slice(separator + 2).trim() || text
  }
  return text
}

/** 兄弟商品的展示标签：只显示取值（剥掉 "Colour: " 这类轴名前缀），其次标题，最后「选项 N」。 */
export function memberLabel(member, index = 0, axisName = '') {
  const label = stripAxisPrefix(member?.axis_label, axisName)
  if (label) return label
  const title = String(member?.title || '').trim()
  // 2026-11-27 去截断：兄弟商品标签展示完整标题（不再截到 60 字）。
  if (title) return title
  return `Option ${index + 1}`
}

/** 商家按钮的展示名（同名商家去重后仍按 offer 区分价格）。 */
export function merchantLabel(offer) {
  return offer?.merchant?.display_name || offer?.merchant?.slug || ''
}
