// 真站频道页 popular-category 精选子集（2026-11-23 实测抽取，见
// var/channel_styles_20261123/measurement.md §A.2）。顺序即展示顺序。
//
// 数据来源：登录态抓取的 SSR HTML（var/channel_styles_20261123/html/
// <channel_code>[_zh].html，抓取日期 2026-11-23），逐页抽出全部
// uk-pc-popular-category-* 模块内的条目（模块出现两次时按页面顺序合并），
// 名称取中文页（缺失回退英文），再按 href 的 l2 类目 id → 英文名 → 中文名
// 规范化比较映射到本地二级类目 slug。
//
// 只收录本地真实存在的二级 slug：真站每页只展示一组精选子集（不是整棵树），
// 其中 13 条在本地没有对应节点，已剔除（不要补占位），明细：
//   - home-living/Seasonal Decor
//   - home-living/Car Wash & Maintenance Tools
//   - home-living/Auto Accessories
//   - home-living/Watering & Garden Tools
//   - home-living/Car Electronics
//   - home-living/Car Lights
//   - outdoor-sports/Sports Equipment
//   - outdoor-sports/Camping & Hiking
//   - outdoor-sports/Sports Nutrition
//   - outdoor-sports/Smartwatches
//   - games-accessories/Monitors
//   - games-accessories/Gaming Keyboards
//   - games-accessories/Gaming Mice
//
// 另有跨一级的条目（真站把外部一级的叶子挂在本频道页）：带
// orderChannelTiles() 的页面只传本频道 children，宽父级 slug 会被过滤掉。
//   - home-living: diy-tools, fitness-training, outdoor-gear
//   - electronics: peripherals, desktop-pcs, laptops, gaming-pc-components, office-electronics, monitors
//   - outdoor-sports: sports-apparel-shoes
//   - games-accessories: gaming-memory-storage, gaming-pc-components
// 生成脚本：var/channel_styles_20261123/scripts/map_tile_lists.py
export const CHANNEL_TILE_LISTS = {
  'home-living': [
    'kitchen-essentials',
    'home-storage',
    'bedding-textiles',
    'bath',
    'home-decor',
    'party-decorations',
    'home-arts-craft-supplies',
    'gift-wrap-cards',
    'furniture',
    'diy-tools',
    'fitness-training',
    'outdoor-gear',
    'notebooks-pads-paper',
    'pens-pencils',
    'school-office-accessories',
    'mailing-supplies',
  ],
  electronics: [
    'mobile-phones',
    'headphones',
    'tablets',
    'speakers',
    'wearables',
    'peripherals',
    'desktop-pcs',
    'laptops',
    'gaming-pc-components',
    'cameras-photo',
    'office-electronics',
    'electronics-accessories',
    'monitors',
    'soundbars-home-cinema',
    'smart-home',
    'batteries',
  ],
  'beauty-personal-care': [
    'premium-beauty',
    'fragrance',
    'skincare',
    'makeup',
    'hair-styling',
    'body-hair-care',
    'sun-cream-lotion',
    'nails',
  ],
  'small-home-appliances': [
    'coffee-machines',
    'heating-cooling-purifier',
    'kettles-toasters',
    'fridges-freezers',
    'blenders-food-processors',
    'washing-machines',
    'tabletop-cooking',
    'hair-styling-tools',
    'air-fryers',
    'toothbrushes-flossers',
    'cleaning-appliances',
    'male-grooming',
    'ironing',
    'female-hair-removal',
    'microwaves-ovens',
    'kitchen-appliances',
    'cooker-hoods',
  ],
  'health-wellness': [
    'weight-management',
    'sexual-wellbeing-family-planning',
    'period-products-intimate-care',
    'sports-nutrition-performance',
    'nutrition-supplements',
    'pharmacy-health',
    'health-monitors',
    'electronic-therapy',
  ],
  'outdoor-sports': ['sports-apparel-shoes'],
  'pet-supplies': [
    'dog-food',
    'dog-treats',
    'smart-pet-appliances',
    'pet-health',
    'pet-accessories',
    'dog-toys',
    'cat-food',
    'cat-treats',
    'cat-litter',
    'pet-grooming',
    'small-animals',
    'cat-toys',
  ],
  'baby-toddler': [
    'infant-pre-school-toys',
    'dress-up-imaginative-play',
    'construction-toys',
    'games-puzzles',
    'play-figures',
    'dolls',
    'pocket-money-toys',
    'outdoor-toys',
    'baby-arts-crafts',
    'learning-discovery-science',
    'vehicles-remote-control',
    'electronic-toys-music',
    'soft-toys',
    'diapers-wipes',
    'baby-milk',
    'baby-food',
    'baby-toiletries',
    'baby-health',
    'strollers-travel',
    'baby-feeding',
    'nursery-bedding',
    'infant-pre-school-toys-activities',
    'baby-clothing',
    'safety-equipment',
  ],
  'games-accessories': [
    'controllers',
    'console-games',
    'consoles',
    'gaming-memory-storage',
    'gaming-pc-components',
    'steering-wheels',
  ],
}

export function channelTileList(slug) {
  return CHANNEL_TILE_LISTS[slug] || null
}
