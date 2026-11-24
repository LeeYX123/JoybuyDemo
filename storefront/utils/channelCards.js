// 频道页活动卡片「多组」归一化（2026-11-23 契约升级）。
//
// 公开接口 GET /api/v1/cms/channel-page-cards?channel=<code>：
//   {
//     channel, layout,                       // layout = 第一个组的布局（兼容字段）
//     groups: [{ group_index, layout, count }],
//     items:  [{ id, image_url, link_url, sort_order, layout, group_index }],
//     total
//   }
// 渲染规则：
//   - 按 group_index 升序渲染各组，组内按 sort_order 升序；
//   - 每组按 layout 渲染：row2（2 张 620×200）、row3（3 张 410×200）、
//     row3_scroll（一屏 3 张 400.66×195.44，可横滑 + hover 箭头）；
//   - groups 缺失 → 按 items[].group_index / items[].layout 分桶兜底；
//   - layout 未知（含历史 grid2x2）→ 按张数推断（2→row2、3→row3、≥4→row3_scroll）。
// 归一化结果统一为 [{ index, layout, items }]，空数据返回 []（调用方整块不渲染）。
export const CARD_LAYOUTS = ['row2', 'row3', 'row3_scroll']

// 张数 → 布局：2 张两列、3 张三列、≥4 一屏三张可横滑（真站实测
// var/channel_styles_20261123/measurement.md §B.1）。1 张沿用三列位。
export function inferCardLayout(count) {
  const total = Number(count) || 0
  if (total === 2) return 'row2'
  if (total >= 4) return 'row3_scroll'
  return 'row3'
}

function knownLayout(value) {
  const layout = String(value || '').trim()
  return CARD_LAYOUTS.includes(layout) ? layout : ''
}

function sortOrderOf(item) {
  const value = Number(item?.sort_order)
  return Number.isFinite(value) ? value : 0
}

function groupIndexOf(item) {
  const value = Number(item?.group_index)
  return Number.isFinite(value) ? value : null
}

// 按 layout 分桶（保持首次出现顺序），用于 groups 缺失的兜底。
function bucketByLayout(cards) {
  const order = []
  const buckets = new Map()
  for (const card of cards) {
    const layout = knownLayout(card.layout)
    if (!buckets.has(layout)) {
      buckets.set(layout, [])
      order.push(layout)
    }
    buckets.get(layout).push(card)
  }
  return order.map((layout, index) => ({
    index,
    layout: layout || inferCardLayout(buckets.get(layout).length),
    items: buckets.get(layout),
  }))
}

// 按 items[].group_index 分桶（groups 缺失但有 group_index 时的兜底）。
function bucketByGroupIndex(cards) {
  const order = []
  const buckets = new Map()
  for (const card of cards) {
    const index = groupIndexOf(card)
    if (!buckets.has(index)) {
      buckets.set(index, [])
      order.push(index)
    }
    buckets.get(index).push(card)
  }
  order.sort((a, b) => (a ?? 0) - (b ?? 0))
  return order.map((index) => {
    const groupCards = buckets.get(index)
    const layout =
      groupCards.map((card) => knownLayout(card.layout)).find(Boolean) ||
      inferCardLayout(groupCards.length)
    return { index: index ?? 0, layout, items: groupCards }
  })
}

export function normalizeChannelCardGroups(items, groups) {
  const cards = (Array.isArray(items) ? items : [])
    .filter((item) => item && item.image_url)
    .slice()
    .sort((a, b) => sortOrderOf(a) - sortOrderOf(b))
  if (cards.length === 0) return []

  const declared = (Array.isArray(groups) ? groups : [])
    .filter((group) => group && groupIndexOf({ group_index: group.group_index }) !== null)
    .slice()
    .sort((a, b) => groupIndexOf(a) - groupIndexOf(b))

  if (declared.length > 0) {
    const hasItemIndex = cards.some((card) => groupIndexOf(card) !== null)
    const result = []
    let cursor = 0
    for (const group of declared) {
      let groupCards
      if (hasItemIndex) {
        const index = groupIndexOf(group)
        groupCards = cards.filter((card) => groupIndexOf(card) === index)
      } else {
        // items 没带 group_index 时按 groups[].count 顺序切分（容错后端过渡期）。
        const count = Math.max(0, Number(group.count) || 0)
        groupCards = cards.slice(cursor, cursor + count)
        cursor += groupCards.length
      }
      if (groupCards.length === 0) continue
      result.push({
        index: groupIndexOf(group) ?? result.length,
        layout: knownLayout(group.layout) || inferCardLayout(groupCards.length),
        items: groupCards,
      })
    }
    if (result.length > 0) return result
  }

  if (cards.some((card) => groupIndexOf(card) !== null)) {
    const grouped = bucketByGroupIndex(cards)
    if (grouped.length > 1) return grouped
  }

  if (cards.every((card) => knownLayout(card.layout))) {
    return bucketByLayout(cards)
  }

  return [{ index: 0, layout: inferCardLayout(cards.length), items: cards }]
}
