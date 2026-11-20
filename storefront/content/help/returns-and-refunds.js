// 批次 U（需求 17.5）：真站 Joybuy customer-service 分类页「Returns & Refunds」结构。
// 来源：2026-11-20 Playwright 实测真站 customer-service 的 Returns & Refunds 分类页
// （EN 完整 DOM/截图/样式 → var/customer_service_20261120/cs_returns_en.html、measurement.md）；
// ZH 文案来自同日真站存档 var/footer_help_20261120/cat_returns_zh.json。
// 结构与字号实测见 var/customer_service_20261120/measurement.md，渲染见
// components/CustomerServicePage.vue。
// 本页替换规则（需求 16.5 帮助中心口径）：联系行真站邮箱 → Joybuyfumi@gmail.com；
// 本页可见内容无真站域名网址、无区域类表述需要替换（16.5 第一条规则不适用）。
// 批次 S 的移动 help 文章聚合正文已整体移除（不再有 blocks 字段）。
export const returnsAndRefundsPage = {
  slug: 'returns-and-refunds',
  title: { en: 'Returns and Refunds', zh: '退货和退款' },
  customerService: {
    // 真站面包屑当前项 = 标题卡文案（EN Returns & Refunds / ZH 退货与退款）。
    category: { en: 'Returns & Refunds', zh: '退货与退款' },
    articles: [
      { en: 'Your Statutory Rights', zh: '法定撤销权' },
      { en: 'Our Return Policy', zh: '退货政策' },
      { en: 'Return Exceptions', zh: '不符合无理由退货的场景' },
      { en: 'Ineligible or Incorrect Returns', zh: '错误或不符合条件的退货' },
      { en: 'Refund Timing and Amount', zh: '退款说明' },
      { en: 'How do I return an item for a refund?', zh: '如何申请退货退款？' },
      { en: 'What is the return window for my order?', zh: '我的订单退货时限是多少？' },
      { en: 'Can I change my return method?', zh: '我可以更改退货方式吗？' },
      { en: 'How can I reschedule my return pickup?', zh: '如何重新预约退货取件时间？' },
      { en: 'Will I receive a full refund after return?', zh: '退货后我能收到全额退款吗？' },
      { en: 'Submit a Complaint', zh: '提交投诉' },
    ],
    // 真站「Browse by categories」chips，顺序按真站（不含本分类、第 3 位起与支付页不同；
    // 第 5 位为互链的支付分类）。
    categories: [
      { en: 'My Orders', zh: '我的订单' },
      { en: 'Delivery & Tracking', zh: '配送与包裹追踪' },
      { en: 'Pickup Service', zh: '自提服务' },
      { en: 'Installation & Recycling', zh: '安装与回收' },
      { en: 'Checkout & Payments', zh: '下单支付', slug: 'payment-and-invoice' },
      { en: 'Promotions & Deals', zh: '促销与优惠' },
      { en: 'Account Settings', zh: '账户设置' },
    ],
  },
}
