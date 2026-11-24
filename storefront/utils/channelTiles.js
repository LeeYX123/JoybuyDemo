// 频道页二级品类卡配置（需求文档03 13.1①②，真站实测 2026-11-23 复核见
// var/channel_styles_20261123/measurement.md §A）。
//
// 行数/每行个数/名称宽度全部数据驱动（不允许在组件里 if-else 硬编码频道）：
// - rows: 卡片区可见行数（列内竖排的张数，余量横向滑动）
// - perRow: 每行可见卡片数（真站 140px 卡一行 8 张、194px 卡一行 6 张；
//   这是「至少能放下几列」的上限，卡宽会按容器宽度与 gap 反算，见
//   CategoryTileGrid 的 --tiles-per-row）
// - fill: 多行时卡片按行刷还是按列刷。真站两种实现：① 两个独立 1 行模块
//   上下叠（家居/宠物/母婴）→ 第一行是清单前 N 个（row）；② 一个 2 行模块
//   内部每列竖排 2 张（电子/家电）→ 列内相邻（column，默认）
// - nameChars: 名称换行宽度（6 字宽 → 140px 卡；9 字宽 → 194px 卡）
// - maxVisible: 最多渲染的二级卡数（余量进横滑/查看全部）
// - hiddenTiles: 仅该频道页隐藏的二级卡（13.1② 宠物页「其他动物用品」；
//   分类下拉是后端树，不受影响）
// - showTitle: 卡片区上方显示【分类导航 / Category Navigation】（健康保健）
//
// 2026-11-23 实测（9 频道）修正：electronics / health / pets 用 big 卡（194），
// beauty 只有 1 行，outdoor 只有 5 张、每行 5 张。
export const CHANNEL_TILE_CONFIG = {
  'home-living': { rows: 2, perRow: 8, nameChars: 6, maxVisible: 22, fill: 'row' },
  electronics: { rows: 2, perRow: 6, nameChars: 9, maxVisible: 22 },
  'beauty-personal-care': { rows: 1, perRow: 8, nameChars: 6, maxVisible: 22 },
  'small-home-appliances': { rows: 2, perRow: 8, nameChars: 6, maxVisible: 22 },
  'health-wellness': { rows: 1, perRow: 6, nameChars: 9, maxVisible: 22, showTitle: true },
  'outdoor-sports': { rows: 1, perRow: 5, nameChars: 9, maxVisible: 22 },
  'pet-supplies': {
    rows: 2,
    perRow: 6,
    nameChars: 9,
    maxVisible: 22,
    fill: 'row',
    hiddenTiles: ['other-animals'],
  },
  'baby-toddler': { rows: 2, perRow: 6, nameChars: 9, maxVisible: 22, fill: 'row' },
  'games-accessories': { rows: 1, perRow: 6, nameChars: 9, maxVisible: 22 },
}

// 未在表里的频道（隐藏一级被直链进频道页等）用家居生活的默认规格兜底。
export const DEFAULT_TILE_CONFIG = {
  rows: 2,
  perRow: 8,
  nameChars: 6,
  maxVisible: 22,
  fill: 'row',
}

export function channelTileConfig(slug) {
  return CHANNEL_TILE_CONFIG[slug] || DEFAULT_TILE_CONFIG
}

// 名称字宽 → 卡片宽度（真站两种规格的实测值：小卡 140、大卡 194，
// measurement.md §A.1；名称文本宽 = 卡宽 − 20）。
export const TILE_SIZE_BY_NAME_CHARS = {
  6: '140px',
  9: '194px',
}

// 按频道精选清单（storefront/utils/channelTileLists.js，另一批次提供）取卡片：
// 清单顺序即展示顺序；清单里在本地树中找不到的 slug 跳过（可选回调上报，
// 页面只在 dev 下 warn 一次）。真站清单含跨一级的 L2（家居页挂了 diy-tools
// 等），所以 lookup 通常是「全树一级 children 的 slug → 节点」Map，而不是本
// 频道的 children 数组。
// - lookup: Map / 数组 / (slug) => 节点
// - 返回 null 表示该频道没有清单（调用方保持后端树顺序）
export function orderChannelTiles(orderedSlugs, lookup, onMissing) {
  if (!Array.isArray(orderedSlugs) || orderedSlugs.length === 0) return null
  const get =
    typeof lookup === 'function'
      ? lookup
      : lookup instanceof Map
        ? (slug) => lookup.get(slug)
        : (slug) => (lookup || []).find((child) => child.slug === slug)
  const tiles = []
  for (const slug of orderedSlugs) {
    const node = get(slug)
    if (!node) {
      onMissing?.(slug)
      continue
    }
    tiles.push(node)
  }
  return tiles
}
