import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

const localeState = vi.hoisted(() => ({ locale: 'en' }))
const tState = vi.hoisted(() => ({ keys: {} }))

// 组件按 `locale.value` 取语言（真实 useLocale 返回 ref），mock 需提供 .value。
vi.mock('../composables/useLocale', () => ({
  useLocale: () => ({
    locale: {
      get value() {
        return localeState.locale
      },
    },
    t: (key) => tState.keys[key] || key,
  }),
}))

import CustomerServicePage from './CustomerServicePage.vue'
import { messages } from '../locales/messages'

// 批次 U（需求 17.5）：真站 customer-service 分类页版式自检（结构实测见
// var/customer_service_20261120/measurement.md）。
const RouterLinkStub = {
  name: 'RouterLinkStub',
  props: ['to'],
  template: '<a :href="to"><slot /></a>',
}

function mountPage(slug) {
  return mount(CustomerServicePage, {
    props: { slug },
    global: { stubs: { NuxtLink: RouterLinkStub } },
  })
}

beforeEachLocale('en')

function beforeEachLocale(locale) {
  localeState.locale = locale
  tState.keys = Object.fromEntries(
    Object.entries(messages[locale]).filter(([key]) => key.startsWith('help.')),
  )
}

describe('CustomerServicePage', () => {
  it('renders the real breadcrumb (root text + chevron + current category)', () => {
    const wrapper = mountPage('payment-and-invoice')
    const nav = wrapper.find('.cs-page__breadcrumb')
    expect(nav.attributes('aria-label')).toBe('breadcrumb')
    expect(nav.find('.cs-page__breadcrumb-root').text()).toBe('Customer Service')
    expect(nav.find('.cs-page__breadcrumb-root').element.tagName).toBe('SPAN')
    expect(nav.find('.cs-page__breadcrumb-sep').exists()).toBe(true)
    expect(nav.find('.cs-page__breadcrumb-current').text()).toBe('Checkout & Payments')
  })

  it('renders the real title card and 5 payment article rows with dividers', () => {
    const wrapper = mountPage('payment-and-invoice')
    expect(wrapper.find('.cs-page__title').text()).toBe('Checkout & Payments')
    const rows = wrapper.findAll('.cs-page__article-row')
    expect(rows).toHaveLength(5)
    expect(rows.map((row) => row.find('.cs-page__article-text').text())).toEqual([
      'Payment Methods',
      'How do I add or update my payment method?',
      'Where can I find and download my invoice?',
      'How do I apply a coupon or promo code?',
      'Why was my payment declined?',
    ])
    // 行间分隔：末行无下分隔线（真站 border-bottom 0.5px #E0E1E5）。
    const bordered = rows.filter((row) => !row.classes().includes('cs-page__article-row--last'))
    expect(bordered).toHaveLength(4)
    expect(rows[4].classes()).toContain('cs-page__article-row--last')
  })

  it('renders 11 return article rows', () => {
    const wrapper = mountPage('returns-and-refunds')
    expect(wrapper.find('.cs-page__title').text()).toBe('Returns & Refunds')
    expect(wrapper.findAll('.cs-page__article-row')).toHaveLength(11)
    expect(wrapper.text()).toContain('Submit a Complaint')
  })

  it('renders the real browse chips in real order; only the counterpart category is a link', () => {
    const pay = mountPage('payment-and-invoice')
    expect(pay.find('.cs-page__browse-title').text()).toBe('Browse by categories')
    const chips = pay.findAll('.cs-page__chip')
    expect(chips.map((chip) => chip.text())).toEqual([
      'My Orders',
      'Delivery & Tracking',
      'Returns & Refunds',
      'Pickup Service',
      'Installation & Recycling',
      'Promotions & Deals',
      'Account Settings',
    ])
    expect(pay.findAll('a.cs-page__chip')).toHaveLength(1)
    expect(pay.find('a.cs-page__chip').attributes('href')).toBe('/pages/returns-and-refunds')

    const returns = mountPage('returns-and-refunds')
    expect(returns.findAll('a.cs-page__chip')).toHaveLength(1)
    expect(returns.find('a.cs-page__chip').attributes('href')).toBe('/pages/payment-and-invoice')
    expect(returns.findAll('.cs-page__chip')[2].text()).toBe('Pickup Service')
  })

  it('renders the 24/7 right rail with search field and online chat button', () => {
    const wrapper = mountPage('payment-and-invoice')
    expect(wrapper.find('.cs-page__service-title').text()).toBe('24/7 Customer Service')
    const input = wrapper.find('.cs-page__search-input')
    expect(input.attributes('placeholder')).toBe('FAQs｜Search for help')
    expect(input.attributes('aria-label')).toBe('Search for help')
    const chat = wrapper.find('.cs-page__chat')
    expect(chat.text()).toBe('Online chat')
    expect(chat.find('svg').exists()).toBe(true)
    expect(wrapper.find('.cs-page__search-btn svg').exists()).toBe(true)
  })

  it('shows the replaced contact email (16.5 rule: Joybuyfumi@gmail.com)', () => {
    const wrapper = mountPage('returns-and-refunds')
    expect(wrapper.find('.cs-page__contact-label').text()).toBe('Service & contact :')
    const email = wrapper.find('.cs-page__contact-email')
    expect(email.text()).toBe('Joybuyfumi@gmail.com')
    expect(email.attributes('href')).toBe('mailto:Joybuyfumi@gmail.com')
  })

  it('renders the real zh copy under the zh locale', () => {
    beforeEachLocale('zh')
    try {
      const wrapper = mountPage('payment-and-invoice')
      expect(wrapper.find('.cs-page__breadcrumb-root').text()).toBe('客户服务')
      expect(wrapper.find('.cs-page__breadcrumb-current').text()).toBe('下单支付')
      expect(wrapper.find('.cs-page__title').text()).toBe('下单支付')
      expect(wrapper.find('.cs-page__article-text').text()).toBe('支付方式')
      expect(wrapper.find('.cs-page__browse-title').text()).toBe('类目查询')
      expect(wrapper.findAll('.cs-page__chip')[2].text()).toBe('退货与退款')
      expect(wrapper.find('.cs-page__service-title').text()).toBe('24/7客服')
      expect(wrapper.find('.cs-page__search-input').attributes('placeholder')).toBe(
        'FAQs｜查询帮助',
      )
      expect(wrapper.find('.cs-page__chat').text()).toBe('在线咨询')
      expect(wrapper.find('.cs-page__contact-label').text()).toBe('服务 & 联系：')

      const returns = mountPage('returns-and-refunds')
      expect(returns.find('.cs-page__title').text()).toBe('退货与退款')
      expect(returns.find('.cs-page__article-text').text()).toBe('法定撤销权')
    } finally {
      beforeEachLocale('en')
    }
  })

  it('keeps all visible copy free of joybuy domains', () => {
    for (const slug of ['payment-and-invoice', 'returns-and-refunds']) {
      const wrapper = mountPage(slug)
      expect(wrapper.html()).not.toMatch(/joybuy\.(com|co\.uk)/i)
    }
  })
})
