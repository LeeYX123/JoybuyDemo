// 批次 U（需求 17.5）：真站 Joybuy customer-service 分类页「Checkout & Payments」结构。
// 来源：2026-11-20 Playwright 实测真站 customer-service 的 Checkout & Payments 分类页
// （EN 完整 DOM/截图/样式 → var/customer_service_20261120/cs_pay_en.html、measurement.md）；
// ZH 文案来自同日真站存档 var/footer_help_20261120/cat_pay_zh.json。
// 结构与字号实测见 var/customer_service_20261120/measurement.md，渲染见
// components/CustomerServicePage.vue。
// 本页替换规则（需求 16.5 帮助中心口径）：联系行真站邮箱 → Joybuyfumi@gmail.com；
// 本页可见内容无真站域名网址、无区域类表述需要替换（16.5 第一条规则不适用）。
// 批次 S 的移动 help 文章聚合正文已整体移除（不再有 blocks 字段）。
export const paymentAndInvoicePage = {
  slug: 'payment-and-invoice',
  title: { en: 'Payment and Invoice', zh: '支付和发票' },
  customerService: {
    // 真站面包屑当前项 = 标题卡文案（EN Checkout & Payments / ZH 下单支付）。
    category: { en: 'Checkout & Payments', zh: '下单支付' },
    articles: [
      { en: 'Payment Methods', zh: '支付方式' },
      { en: 'How do I add or update my payment method?', zh: '如何添加或更新我的付款方式？' },
      { en: 'Where can I find and download my invoice?', zh: '我可以在哪里找到并下载我的发票？' },
      { en: 'How do I apply a coupon or promo code?', zh: '如何使用优惠券或促销代码？' },
      { en: 'Why was my payment declined?', zh: '我的付款为什么被拒绝了？' },
    ],
    // 真站「Browse by categories」chips，顺序按真站（不含本分类；第 3 位为互链的退货分类）。
    categories: [
      { en: 'My Orders', zh: '我的订单' },
      { en: 'Delivery & Tracking', zh: '配送与包裹追踪' },
      { en: 'Returns & Refunds', zh: '退货与退款', slug: 'returns-and-refunds' },
      { en: 'Pickup Service', zh: '自提服务' },
      { en: 'Installation & Recycling', zh: '安装与回收' },
      { en: 'Promotions & Deals', zh: '促销与优惠' },
      { en: 'Account Settings', zh: '账户设置' },
    ],
  },
}
