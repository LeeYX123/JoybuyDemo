// 批次 Q（需求 15.1 / 15.2）：真站 help 中心（/help/*）的页面注册表。
// 2026-11-20 实测真站左侧导航共 5 项，顺序如下（真站为静态列表，不分组建）：
//   Privacy Policy → Terms of Sale → Cookie Policy → Terms of Use → Accessibility Statement
// 每页正文见 ./help/<slug>.js（除邮箱 → Joybuyfumi@gmail.com 外全文照抄真站）。
// 路由：真站是整页跳转 /help/<slug>；本地同时保留 /pages/<slug> 作为页脚入口，
// 两个路由渲染同一套左 tab + 右内容版式（见 components/HelpCenter.vue）。
import { privacyPolicyPage } from './help/privacy-policy'
import { termsConditionsPage } from './help/terms-conditions'
import { cookiePolicyPage } from './help/cookie-policy'
import { termsOfUsePage } from './help/terms-of-use'
import { accessibilityStatementPage } from './help/accessibility-statement'
import { paymentAndInvoicePage } from './help/payment-and-invoice'
import { returnsAndRefundsPage } from './help/returns-and-refunds'

// 批次 S（需求 16.5）新增、批次 U（需求 17.5）重做的两个 customer-service 页。
// 真站 help 中心左栏只有 5 项政策/条款页，这两项属于客户服务分类（footer 入口），
// 因此只注册路由、不进左栏 tab（见下面的 helpNav）。
// 批次 U 起这两页的数据结构是 customerService{category,articles,categories}
// （真站 /customer-service/<Category> 分类页），不再有 blocks；渲染走
// components/CustomerServicePage.vue，5 个政策页仍走 components/HelpCenter.vue。
export const helpPages = [
  privacyPolicyPage,
  termsConditionsPage,
  cookiePolicyPage,
  termsOfUsePage,
  accessibilityStatementPage,
  paymentAndInvoicePage,
  returnsAndRefundsPage,
]

export const helpPageBySlug = Object.fromEntries(helpPages.map((page) => [page.slug, page]))

// 左栏 tab 数据（顺序即真站顺序；真站不含支付和发票 / 退货和退款）。
export const helpNav = [
  privacyPolicyPage,
  termsConditionsPage,
  cookiePolicyPage,
  termsOfUsePage,
  accessibilityStatementPage,
].map((page) => ({ slug: page.slug, title: page.title }))

export function helpPagePath(slug) {
  return `/pages/${slug}`
}

// 真站两条路径是驼峰（/help/TermsofUse、/help/AccessibilityStatement），本地 slug 是
// kebab-case；这里把真站写法（大小写不敏感）映射回本地 slug，保证真站 URL 也可达。
const REAL_SLUG_ALIASES = {
  termsofuse: 'terms-of-use',
  accessibilitystatement: 'accessibility-statement',
}

export function resolveHelpSlug(raw) {
  const slug = String(raw || '')
  if (helpPageBySlug[slug]) return slug
  return REAL_SLUG_ALIASES[slug.toLowerCase()] || null
}
