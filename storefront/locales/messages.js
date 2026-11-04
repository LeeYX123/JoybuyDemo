// Storefront UI dictionary (docs/12: bilingual EN/ZH target-state copy).
// Keys are grouped per surface; `en` is the fallback for every locale.
export const messages = {
  en: {
    'topStrip.region': 'UK | English',
    'topStrip.quality': 'Quality Guaranteed',
    'topStrip.support': '24/7 Customer Support',
    'topStrip.freeReturns': 'Free returns',
    'topStrip.welcomeOffers':
      'Unlock Your Welcome Offers: FREE Delivery | Up to 80% OFF | Free 30-day JoyPlus trial',
    'header.categories': 'Categories',
    'header.searchPlaceholder': 'Search on Joybuy',
    'header.searchLabel': 'Search products',
    'header.deliverTo': 'Deliver to',
    'header.myAccount': 'My account',
    'header.signIn': 'Sign in',
    'header.cart': 'Cart',
    'header.allCategories': 'Product categories',
    'header.accountAndCart': 'Account and cart',
    'accountMenu.orders': 'My orders',
    'accountMenu.reviews': 'Reviews and Q&A',
    'accountMenu.wishlist': 'Wishlist',
    'accountMenu.addresses': 'Addresses',
    'accountMenu.signOut': 'Sign out',
    'categoryPanel.close': 'Close categories panel',
    'addresses.title': 'Addresses',
    'addresses.empty': 'No saved addresses yet.',
    'detail.guaranteeReturns': '30 Days Free Returns',
    'detail.guaranteeWarranty': "1 Year Manufacturer's Warranty",
    'detail.guaranteeSupport': '24/7 Customer Support',
    'gate.message':
      'Our service is not yet available in your country. Purchasing is not supported at the moment.',
    'gate.confirm': 'OK',
    'checkout.balancePay': 'Balance payment',
  },
  zh: {
    'topStrip.region': '英国 | 中文',
    'topStrip.quality': '品质保证',
    'topStrip.support': '24/7 客户支持',
    'topStrip.freeReturns': '免费退货',
    'topStrip.welcomeOffers': '解锁新人福利：全场免邮 | 低至 2 折 | 免费试用 30 天',
    'header.categories': '分类',
    'header.searchPlaceholder': '搜索 Joybuy 商品',
    'header.searchLabel': '搜索商品',
    'header.deliverTo': '配送至',
    'header.myAccount': '我的账户',
    'header.signIn': '登录',
    'header.cart': '购物车',
    'header.allCategories': '全部类目',
    'header.accountAndCart': '账户与购物车',
    'accountMenu.orders': '我的订单',
    'accountMenu.reviews': '评价与问答',
    'accountMenu.wishlist': '我的收藏',
    'accountMenu.addresses': '收货地址',
    'accountMenu.signOut': '退出登录',
    'categoryPanel.close': '关闭分类面板',
    'addresses.title': '收货地址',
    'addresses.empty': '还没有保存的地址。',
    'detail.guaranteeReturns': '30 天内免费退货',
    'detail.guaranteeWarranty': '厂家保修 1 年',
    'detail.guaranteeSupport': '24/7 客户支持',
    'gate.message': '您当前的国家业务尚未开放，暂不支持购买',
    'gate.confirm': '确定',
    'checkout.balancePay': '余额支付',
  },
}

// Pick a bilingual label: `locale` wins, the other language is the fallback.
export function pickName(item, locale, prefix = 'name') {
  const primary = locale === 'zh' ? item[`${prefix}_zh`] : item[`${prefix}_en`]
  if (primary) return primary
  return locale === 'zh' ? item[`${prefix}_en`] || item[prefix] : item[prefix]
}
