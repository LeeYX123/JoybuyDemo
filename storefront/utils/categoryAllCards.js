// 批次 CA：分类下拉「查看全部 <一级品类>」卡的固定图片常量。
//
// 每个一级品类固定选用它下面某一个二级品类的本地卡图（选定后不随接口
// 数据变化；新增一级品类时在这里补一行，缺省回落到占位图）。
export const L1_ALL_CARD_IMAGES = {
  'home-living': '/images/categories/home-decor.webp',
  electronics: '/images/categories/mobile-phones.webp',
  'beauty-personal-care': '/images/categories/premium-beauty.webp',
  'small-home-appliances': '/images/categories/heating-cooling-purifier.webp',
  'health-wellness': '/images/categories/nutrition-supplements.webp',
  'computers-accessories': '/images/categories/gaming-memory-storage.webp',
  'clothing-accessories': '/images/categories/shoes-boots.webp',
  'outdoor-sports': '/images/categories/outdoor-gear.webp',
  'pet-supplies': '/images/categories/cat-food.webp',
  'baby-toddler': '/images/categories/infant-pre-school-toys.webp',
  'games-accessories': '/images/categories/pc-gaming.webp',
}

export const ALL_CARD_FALLBACK_IMAGE = '/images/categories/_placeholder.svg'

export function allCardImage(slug) {
  return L1_ALL_CARD_IMAGES[slug] || ALL_CARD_FALLBACK_IMAGE
}
