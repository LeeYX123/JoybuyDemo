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
// 其中部分条目在本地没有对应节点，已剔除（不要补占位），明细：
//   - home-living/Seasonal Decor（真站 l2=1580）
//   - home-living/Car Wash & Maintenance Tools（真站 l2=3902）
//   - home-living/Auto Accessories（真站 l2=3904）
//   - home-living/Car Electronics（真站 l2=3896）
//   - home-living/Car Lights（真站 l2=3898）
//   - games-accessories/Gaming Keyboards（真站 l3=5116）
//   - games-accessories/Gaming Mice（真站 l3=5117）
// 本地没有汽车/节庆装饰节点；游戏键盘与鼠标在本地只有合并后的
// computers-accessories/peripherals（「键盘、鼠标及输入设备」）一个节点，
// 两条真站卡片无法各自独立呈现，故一并跳过（不重复渲染同一节点）。
//
// 层级提升（真站卡片是三级、本地只有对应二级）：按语义就近映射到该二级节点。
//   - home-living/Watering & Garden Tools（真站 l3=3121，挂 Garden 下）
//     → outdoor-sports/garden「园艺 & 庭院工具」
//   - games-accessories/Monitors（真站 l3=1437，挂 Monitors 下）
//     → computers-accessories/monitors「显示器」
//
// 跨一级条目（真站把外部一级的叶子挂在本频道页）：频道页用「全树一级 children
// 的 slug → 节点」索引解析，跨根 slug 也能正常渲染，不会被过滤。
//   - home-living: garden, diy-tools, fitness-training, outdoor-gear
//   - electronics: peripherals, desktop-pcs, laptops, gaming-pc-components, office-electronics, monitors
//   - outdoor-sports: sports-nutrition-performance（health-wellness 根下）、
//     wearables（electronics 根下）
//   - games-accessories: gaming-memory-storage, gaming-pc-components, monitors
//
// 2026-11-24 批次 BA：outdoor-sports 真站 5 张按语义映射到本地节点补齐
// （真站 Sports Equipment → fitness-training「体育与休闲」、Camping & Hiking →
// outdoor-gear「户外」、Sports Nutrition → sports-nutrition-performance、
// Smartwatches → wearables）。此前只写 1 条，户外页因此只出 1 张卡；若某频道
// 清单解析后仍不足 2 张，频道页回退该品类树 children（见 pages/minihome/[code].vue）。
// 同日补齐 home-living（真站 22 张，本地可映射 17 张）与 games-accessories
// （真站 9 张，本地可映射 7 张），顺序严格按真站；缺失节点见上方清单。
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
    // Seasonal Decor / Car Wash & Maintenance Tools / Auto Accessories 本地无节点，跳过
    'furniture',
    'garden', // 真站 Watering & Garden Tools（outdoor-sports 根下）
    'diy-tools',
    'fitness-training',
    'outdoor-gear',
    'notebooks-pads-paper',
    'pens-pencils',
    'school-office-accessories',
    'mailing-supplies',
    // Car Electronics / Car Lights 本地无节点，跳过
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
  'outdoor-sports': [
    'sports-apparel-shoes',
    'fitness-training',
    'outdoor-gear',
    'sports-nutrition-performance',
    'wearables',
  ],
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
    'monitors', // 真站 Monitors（computers-accessories 根下）
    // Gaming Keyboards / Gaming Mice 本地只有合并的 peripherals，跳过
    'steering-wheels',
  ],
}

export function channelTileList(slug) {
  return CHANNEL_TILE_LISTS[slug] || null
}
