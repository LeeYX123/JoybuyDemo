// 频道页二级品类卡配置（需求文档03 13.1①②，2026-11-19 真站实测见
// var/channel_styles_20261119/measurement.md）。
//
// 行数/每行个数/名称宽度全部数据驱动（不允许在组件里 if-else 硬编码频道）：
// - rows: 卡片区行数（余量横向滑动）
// - perRow: 每行卡片数（真站 140px 卡一行 8 张、194px 卡一行 6 张）
// - nameChars: 名称换行宽度（6 字宽 → 140px 图容器；9 字宽 → 194px 图容器）
// - maxVisible: 最多渲染的二级卡数（余量进横滑/查看全部）
// - hiddenTiles: 仅该频道页隐藏的二级卡（13.1② 宠物页「其他动物用品」；
//   分类下拉是后端树，不受影响）
// - showTitle: 卡片区上方显示【分类导航 / Category Navigation】（健康保健）
export const CHANNEL_TILE_CONFIG = {
  'home-living': { rows: 2, perRow: 8, nameChars: 6, maxVisible: 22 },
  electronics: { rows: 2, perRow: 8, nameChars: 6, maxVisible: 22 },
  'beauty-personal-care': { rows: 2, perRow: 8, nameChars: 6, maxVisible: 22 },
  'small-home-appliances': { rows: 2, perRow: 8, nameChars: 6, maxVisible: 22 },
  'health-wellness': { rows: 1, perRow: 8, nameChars: 6, maxVisible: 22, showTitle: true },
  'outdoor-sports': { rows: 1, perRow: 6, nameChars: 9, maxVisible: 22 },
  'pet-supplies': {
    rows: 2,
    perRow: 6,
    nameChars: 6,
    maxVisible: 22,
    hiddenTiles: ['other-animals'],
  },
  'baby-toddler': { rows: 2, perRow: 6, nameChars: 9, maxVisible: 22 },
  'games-accessories': { rows: 1, perRow: 6, nameChars: 9, maxVisible: 22 },
}

// 未在表里的频道（隐藏一级被直链进频道页等）用家居生活的默认规格兜底。
export const DEFAULT_TILE_CONFIG = { rows: 2, perRow: 8, nameChars: 6, maxVisible: 22 }

export function channelTileConfig(slug) {
  return CHANNEL_TILE_CONFIG[slug] || DEFAULT_TILE_CONFIG
}

// 名称字宽 → 图片容器边长（真站两种规格的实测值，measurement.md §1）。
export const TILE_SIZE_BY_NAME_CHARS = {
  6: '140px',
  9: '194px',
}
