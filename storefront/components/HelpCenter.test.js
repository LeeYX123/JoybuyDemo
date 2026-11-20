import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

const localeState = vi.hoisted(() => ({ locale: 'en' }))

// 组件按 `locale.value` 取语言（真实 useLocale 返回 ref），mock 需提供 .value。
vi.mock('../composables/useLocale', () => ({
  useLocale: () => ({
    locale: {
      get value() {
        return localeState.locale
      },
    },
    t: (key) => key,
  }),
}))

import HelpCenter from './HelpCenter.vue'
import { helpPageBySlug } from '../content/helpPages'

// 批次 Q（需求 15.1）：左栏 tab + 右栏内容。tab 为路由切换（真站整页跳转），
// 当前项用--active 高亮 + aria-current=page。
const RouterLinkStub = {
  name: 'RouterLinkStub',
  props: ['to'],
  template: '<a :href="to"><slot /></a>',
}

function mountPage(slug) {
  return mount(HelpCenter, {
    props: { slug },
    global: { stubs: { NuxtLink: RouterLinkStub } },
  })
}

describe('HelpCenter', () => {
  it('renders the 5 real nav entries in order', () => {
    const wrapper = mountPage('privacy-policy')
    const links = wrapper.findAll('.help-center__nav-link')
    expect(links).toHaveLength(5)
    expect(links.map((link) => link.text())).toEqual([
      'Privacy Policy',
      'Terms of Sale',
      'Cookie Policy',
      'Terms of Use',
      'Accessibility Statement',
    ])
    expect(links.map((link) => link.attributes('href'))).toEqual([
      '/pages/privacy-policy',
      '/pages/terms-conditions',
      '/pages/cookie-policy',
      '/pages/terms-of-use',
      '/pages/accessibility-statement',
    ])
  })

  it('highlights the current entry only', () => {
    const wrapper = mountPage('cookie-policy')
    const active = wrapper.findAll('.help-center__nav-link--active')
    expect(active).toHaveLength(1)
    expect(active[0].text()).toBe('Cookie Policy')
    expect(active[0].attributes('aria-current')).toBe('page')
    expect(active[0].attributes('href')).toBe('/pages/cookie-policy')
    expect(wrapper.find('.help-center__title').text()).toBe('Cookie Policy')
  })

  it('renders the rich text blocks and the real 3-column table', () => {
    const wrapper = mountPage('privacy-policy')
    expect(wrapper.findAll('.help-center__paragraph').length).toBe(9)
    const rows = wrapper.findAll('.help-center__table tr')
    expect(rows).toHaveLength(9)
    expect(rows[0].findAll('td')).toHaveLength(3)
    expect(wrapper.text()).toContain('Jingdong Retail (UK) Limited')
    expect(wrapper.text()).toContain('Joybuyfumi@gmail.com')
    expect(wrapper.find('[href="mailto:Joybuyfumi@gmail.com"]').exists()).toBe(true)
  })

  it('shows the archived-version mark on the privacy page only', () => {
    expect(mountPage('privacy-policy').find('.help-center__archive').exists()).toBe(true)
    expect(mountPage('terms-conditions').find('.help-center__archive').exists()).toBe(false)
  })

  // 真站实测（var/policy_table_fix_20261120/measurement.md）：只有销售条款定义表首列加粗，
  // 隐私政策表格首列不加粗，故用块级 firstColBold 控制。
  it('bolds the first column only on the Terms of Sale definition table', () => {
    localeState.locale = 'zh'
    try {
      const terms = mountPage('terms-conditions')
      const rows = terms.findAll('.help-center__table tr')
      expect(rows.length).toBeGreaterThan(0)
      for (const row of rows) {
        const cells = row.findAll('td')
        expect(cells[0].classes()).toContain('help-center__table-cell--bold')
        expect(
          cells.slice(1).every((c) => !c.classes().includes('help-center__table-cell--bold')),
        ).toBe(true)
      }

      const privacy = mountPage('privacy-policy')
      expect(privacy.findAll('.help-center__table-cell--bold')).toHaveLength(0)
    } finally {
      localeState.locale = 'en'
    }
  })

  it('renders the real ordered/unordered lists', () => {
    const wrapper = mountPage('accessibility-statement')
    expect(wrapper.findAll('ol.help-center__list')).toHaveLength(1)
    expect(wrapper.findAll('ul.help-center__list')).toHaveLength(7)
    expect(wrapper.findAll('.help-center__list li')).toHaveLength(22)
  })

  // 批次 U（需求 17.5）：支付和发票 / 退货和退款改走 CustomerServicePage（真站
  // customer-service 版式），HelpCenter 只承载 5 个政策页；image 块仅政策页表格
  // 等富文本使用，两页旧的移动 help 文章聚合（含配图）已删除。
  it('no longer carries the two customer-service pages', () => {
    for (const slug of ['payment-and-invoice', 'returns-and-refunds']) {
      const page = helpPageBySlug[slug]
      expect(page.blocks).toBeUndefined()
    }
  })
})
