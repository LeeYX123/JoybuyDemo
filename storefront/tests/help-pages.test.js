import { describe, expect, it } from 'vitest'

import {
  helpNav,
  helpPages,
  helpPageBySlug,
  helpPagePath,
  resolveHelpSlug,
} from '../content/helpPages'

// 批次 Q（需求 15.1 / 15.2）数据自检：
// - 左栏 tab 的条目与顺序必须与真站一致（2026-11-20 实测：5 项，不分组件）；
// - 正文除邮箱外照抄真站：不得残留上一版（14.8）的公司/地区/域名替换痕迹；
// - 唯一允许替换的邮箱必须是 Joybuyfumi@gmail.com。
// 批次 U（需求 17.5）：支付和发票 / 退货和退款两页改为真站 customer-service
// 分类页结构（customerService{category,articles,categories}），不再有 blocks。

const REAL_NAV = [
  ['privacy-policy', 'Privacy Policy', '隐私政策'],
  ['terms-conditions', 'Terms of Sale', '销售条款'],
  ['cookie-policy', 'Cookie Policy', 'Cookie 政策'],
  ['terms-of-use', 'Terms of Use', 'Joybuy 使用条款'],
  ['accessibility-statement', 'Accessibility Statement', '无障碍声明'],
]

const POLICY_SLUGS = REAL_NAV.map(([slug]) => slug)
const CS_SLUGS = ['payment-and-invoice', 'returns-and-refunds']
const EMAIL_RE = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g

// 真站 customer-service 页正文（2026-11-20 实测，见 var/customer_service_20261120/）。
const REAL_CS = {
  'payment-and-invoice': {
    title: { en: 'Payment and Invoice', zh: '支付和发票' },
    category: { en: 'Checkout & Payments', zh: '下单支付' },
    articles: [
      ['Payment Methods', '支付方式'],
      ['How do I add or update my payment method?', '如何添加或更新我的付款方式？'],
      ['Where can I find and download my invoice?', '我可以在哪里找到并下载我的发票？'],
      ['How do I apply a coupon or promo code?', '如何使用优惠券或促销代码？'],
      ['Why was my payment declined?', '我的付款为什么被拒绝了？'],
    ],
    categories: [
      'My Orders',
      'Delivery & Tracking',
      'Returns & Refunds',
      'Pickup Service',
      'Installation & Recycling',
      'Promotions & Deals',
      'Account Settings',
    ],
  },
  'returns-and-refunds': {
    title: { en: 'Returns and Refunds', zh: '退货和退款' },
    category: { en: 'Returns & Refunds', zh: '退货与退款' },
    articles: [
      ['Your Statutory Rights', '法定撤销权'],
      ['Our Return Policy', '退货政策'],
      ['Return Exceptions', '不符合无理由退货的场景'],
      ['Ineligible or Incorrect Returns', '错误或不符合条件的退货'],
      ['Refund Timing and Amount', '退款说明'],
      ['How do I return an item for a refund?', '如何申请退货退款？'],
      ['What is the return window for my order?', '我的订单退货时限是多少？'],
      ['Can I change my return method?', '我可以更改退货方式吗？'],
      ['How can I reschedule my return pickup?', '如何重新预约退货取件时间？'],
      ['Will I receive a full refund after return?', '退货后我能收到全额退款吗？'],
      ['Submit a Complaint', '提交投诉'],
    ],
    categories: [
      'My Orders',
      'Delivery & Tracking',
      'Pickup Service',
      'Installation & Recycling',
      'Checkout & Payments',
      'Promotions & Deals',
      'Account Settings',
    ],
  },
}

function policyText(page) {
  return Object.values(page.blocks)
    .flat()
    .map((block) => {
      if (block.type === 'table') return block.rows.flat().join('\n')
      if (block.type === 'list') {
        return block.items
          .map((item) => item.map((seg) => (seg.br ? '\n' : seg.t)).join(''))
          .join('\n')
      }
      return block.segments.map((seg) => (seg.br ? '\n' : seg.t)).join('')
    })
    .join('\n')
}

describe('helpPages data', () => {
  it('exposes the 5 real help-center nav entries in real order', () => {
    // 批次 S：可路由页面共 7 个（新增支付和发票 / 退货和退款），但左栏仍为真站 5 项。
    expect(helpPages).toHaveLength(7)
    expect(helpNav).toHaveLength(5)
    expect(helpNav.map((item) => item.slug)).toEqual(POLICY_SLUGS)
    expect(helpNav.map((item) => item.title.en)).toEqual(REAL_NAV.map(([, en]) => en))
    expect(helpNav.map((item) => item.title.zh)).toEqual(REAL_NAV.map(([, , zh]) => zh))
    for (const [slug] of REAL_NAV) {
      expect(helpPageBySlug[slug]).toBeTruthy()
      expect(helpPagePath(slug)).toBe(`/pages/${slug}`)
    }
  })

  it('registers the two footer help pages outside the left nav', () => {
    for (const [slug, en, zh] of [
      ['payment-and-invoice', 'Payment and Invoice', '支付和发票'],
      ['returns-and-refunds', 'Returns and Refunds', '退货和退款'],
    ]) {
      expect(helpPageBySlug[slug]).toBeTruthy()
      expect(helpPageBySlug[slug].title.en).toBe(en)
      expect(helpPageBySlug[slug].title.zh).toBe(zh)
      expect(helpNav.map((item) => item.slug)).not.toContain(slug)
      expect(resolveHelpSlug(slug)).toBe(slug)
    }
  })

  it('uses the customer-service structure (no legacy article blocks)', () => {
    for (const slug of CS_SLUGS) {
      const page = helpPageBySlug[slug]
      expect(page.blocks).toBeUndefined()
      expect(page.customerService).toBeTruthy()
    }
  })

  it('carries the real customer-service category title and article list (5 + 11)', () => {
    for (const slug of CS_SLUGS) {
      const expected = REAL_CS[slug]
      const cs = helpPageBySlug[slug].customerService
      for (const lang of ['en', 'zh']) {
        expect(helpPageBySlug[slug].title[lang]).toBe(expected.title[lang])
        expect(cs.category[lang]).toBe(expected.category[lang])
        expect(cs.articles.map((a) => a[lang])).toEqual(
          expected.articles.map((pair) => (lang === 'en' ? pair[0] : pair[1])),
        )
      }
      expect(cs.articles).toHaveLength(slug === 'payment-and-invoice' ? 5 : 11)
    }
  })

  it('carries the real browse-by-categories chips in real order', () => {
    for (const slug of CS_SLUGS) {
      const cs = helpPageBySlug[slug].customerService
      expect(cs.categories.map((c) => c.en)).toEqual(REAL_CS[slug].categories)
      expect(cs.categories).toHaveLength(7)
    }
    // 互链 chip：支付页里的退货分类 / 退货页里的支付分类（本地互链）。
    const payCs = helpPageBySlug['payment-and-invoice'].customerService
    const retCs = helpPageBySlug['returns-and-refunds'].customerService
    expect(payCs.categories.find((c) => c.slug === 'returns-and-refunds')?.en).toBe(
      'Returns & Refunds',
    )
    expect(retCs.categories.find((c) => c.slug === 'payment-and-invoice')?.en).toBe(
      'Checkout & Payments',
    )
    // 其余 chips 无本地目标（不产生假链接）。
    for (const cs of [payCs, retCs]) {
      expect(cs.categories.filter((c) => c.slug)).toHaveLength(1)
    }
  })

  it('keeps policy pages with non-empty en + zh blocks (real zh, not machine translation)', () => {
    for (const slug of POLICY_SLUGS) {
      const page = helpPageBySlug[slug]
      expect(page.blocks.en.length).toBeGreaterThan(0)
      expect(page.blocks.zh.length).toBeGreaterThan(0)
      expect(policyText({ blocks: { en: page.blocks.en } }).length).toBeGreaterThan(200)
      expect(/[\u4e00-\u9fa5]/.test(policyText({ blocks: { zh: page.blocks.zh } }))).toBe(true)
    }
  })

  it('keeps customer-service pages bilingual with real zh copy', () => {
    for (const slug of CS_SLUGS) {
      const json = JSON.stringify(helpPageBySlug[slug].customerService)
      // 中文文案是真站现成的（存档 cat_pay_zh.json / cat_returns_zh.json）。
      expect(/[\u4e00-\u9fa5]/.test(json)).toBe(true)
      expect(json).toContain(REAL_CS[slug].category.zh)
    }
  })

  it('has no branded zendesk / joybuy domain left in any help page', () => {
    for (const page of helpPages) {
      const json = JSON.stringify(page.blocks || page.customerService)
      expect(json).not.toContain('zendesk')
      expect(json).not.toMatch(/joybuy\.(com|co\.uk)/i)
    }
  })

  it('resolves the real camel-case help paths too', () => {
    expect(resolveHelpSlug('privacy-policy')).toBe('privacy-policy')
    expect(resolveHelpSlug('TermsofUse')).toBe('terms-of-use')
    expect(resolveHelpSlug('AccessibilityStatement')).toBe('accessibility-statement')
    expect(resolveHelpSlug('termsofuse')).toBe('terms-of-use')
    expect(resolveHelpSlug('nope')).toBeNull()
  })

  it('replaces only emails, with Joybuyfumi@gmail.com (policy pages; cs email lives in the component)', () => {
    for (const slug of POLICY_SLUGS) {
      const page = helpPageBySlug[slug]
      const emails = [...new Set(policyText(page).match(EMAIL_RE) || [])]
      expect(emails).toEqual(emails.length ? ['Joybuyfumi@gmail.com'] : [])
    }
    // customer-service 两页数据里无邮箱，联系行邮箱在组件常量（16.5 口径替换）。
    for (const slug of CS_SLUGS) {
      const emails = JSON.stringify(helpPageBySlug[slug]).match(EMAIL_RE) || []
      expect(emails).toEqual([])
    }
  })

  it('keeps the real legal identity (no 14.8 sanitising left)', () => {
    const text = policyText(helpPageBySlug['privacy-policy'])
    expect(text).toContain('Jingdong Retail (UK) Limited')
    expect(text).toContain('15830555')
    expect(text).toContain('Floor 3, 20 King Street')
    expect(text).toContain('European Commission')
    for (const banned of ['(demo)', 'Asian Economic Area', 'Demo address']) {
      expect(text).not.toContain(banned)
    }
  })

  it('rewrites every real-site URL to www.joyfumi.com in the five policy pages', () => {
    for (const slug of POLICY_SLUGS) {
      const page = helpPageBySlug[slug]
      const text = policyText(page)
      const hrefs = Object.values(page.blocks)
        .flat()
        .flatMap((block) => (block.segments || block.items?.flat() || []).map((seg) => seg.href))
        .filter(Boolean)
      expect(text).not.toMatch(/joybuy\.(com|co\.uk)/i)
      for (const href of hrefs) {
        expect(href).not.toMatch(/joybuy\.(com|co\.uk)/i)
      }
      // 真站域名出现过的页面必须已换成 www.joyfumi.com（第三方外链不受影响）。
      expect([text, ...hrefs].join('\n')).toContain('www.joyfumi.com')
    }
  })

  it('keeps customer-service pages free of EU wording and joybuy links (16.5 rule)', () => {
    for (const slug of CS_SLUGS) {
      const json = JSON.stringify(helpPageBySlug[slug])
      expect(json).not.toMatch(/\bEU\b/)
      expect(json).not.toMatch(/European|Europe/)
      expect(json).not.toMatch(/欧盟|欧洲/)
      expect(json).not.toMatch(/joybuy\.(com|co\.uk)/i)
    }
    // 政策页维持 15.2 口径：EU / 欧洲 表述原样保留（只换网址与邮箱）。
    expect(policyText(helpPageBySlug['privacy-policy'])).toContain('European')
  })

  it('links policy pages through local routes instead of the real /help path', () => {
    for (const slug of POLICY_SLUGS) {
      const page = helpPageBySlug[slug]
      for (const block of Object.values(page.blocks).flat()) {
        const segments = block.segments || block.items?.flat() || []
        for (const seg of segments) {
          if (!seg.href) continue
          expect(seg.href).not.toContain('urldefense.com')
          expect(seg.href).not.toMatch(/^\/help\//)
        }
      }
    }
  })

  it('keeps the real ordered / unordered lists (zh TOC 11 items, accessibility bullets)', () => {
    const zhPrivacy = helpPageBySlug['privacy-policy'].blocks.zh.find((b) => b.type === 'list')
    expect(zhPrivacy.ordered).toBe(true)
    expect(zhPrivacy.items).toHaveLength(11)
    expect(
      zhPrivacy.items.map((item) => item.map((seg) => (seg.br ? '\n' : seg.t)).join('')).join('\n'),
    ).toContain('范围')

    const enA11y = helpPageBySlug['accessibility-statement'].blocks.en.filter(
      (b) => b.type === 'list',
    )
    expect(enA11y).toHaveLength(8)
    expect(enA11y.filter((b) => b.ordered)).toHaveLength(1)
    expect(enA11y.reduce((sum, b) => sum + b.items.length, 0)).toBe(22)
  })
})
