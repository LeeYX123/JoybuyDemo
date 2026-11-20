import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

const localeState = vi.hoisted(() => ({ locale: 'en' }))
const tState = vi.hoisted(() => ({ keys: {} }))

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

import CsArticlePage from './CsArticlePage.vue'
import { csArticleBySlug } from '../content/help/csArticles'
import { messages } from '../locales/messages'

// 批次 0am（2026-11-20）：真站 customer-service 文章详情页版式自检
// （16 篇 = 支付 5 + 退货 11；结构实测见 var/cs_articles_20261120/measurement.md）。
const RouterLinkStub = {
  name: 'RouterLinkStub',
  props: ['to'],
  template: '<a :href="to"><slot /></a>',
}

function beforeEachLocale(locale) {
  localeState.locale = locale
  tState.keys = Object.fromEntries(
    Object.entries(messages[locale]).filter(([key]) => key.startsWith('help.')),
  )
}

function mountPage(slug) {
  return mount(CsArticlePage, {
    props: { slug },
    global: { stubs: { NuxtLink: RouterLinkStub } },
  })
}

beforeEachLocale('en')

describe('CsArticlePage', () => {
  it('renders breadcrumb with category link back to the list page and current article title', () => {
    const wrapper = mountPage('payment-methods')
    const nav = wrapper.find('.cs-article__breadcrumb')
    expect(nav.attributes('aria-label')).toBe('breadcrumb')
    expect(nav.find('.cs-article__breadcrumb-root').text()).toBe('Customer Service')
    const link = nav.find('.cs-article__breadcrumb-link')
    expect(link.text()).toBe('Checkout & Payments')
    expect(link.attributes('href')).toBe('/help/payment-and-invoice')
    expect(nav.find('.cs-article__breadcrumb-current').text()).toBe('Payment Methods')
  })

  it('renders the real title and body blocks for a payment article (payment-methods)', () => {
    const wrapper = mountPage('payment-methods')
    expect(wrapper.find('.cs-article__title').text()).toBe('Payment Methods')
    const ps = wrapper.findAll('.cs-article__paragraph')
    expect(ps).toHaveLength(1)
    expect(ps[0].text()).toContain('Joybuy supports the following payment options:')
    const list = wrapper.find('.cs-article__list')
    expect(list.element.tagName).toBe('UL')
    const items = list.findAll('li')
    expect(items).toHaveLength(9)
    expect(items[0].text()).toBe('VISA/MasterCard/JCB')
    expect(items[8].text()).toBe('NewPay')
    expect(wrapper.findAll('.cs-article__image')).toHaveLength(0)
  })

  it('renders the invoice article with real steps, two local images and closing paragraph', () => {
    const wrapper = mountPage('download-invoice')
    expect(wrapper.find('.cs-article__title').text()).toBe(
      'Where can I find and download my invoice?',
    )
    const imgs = wrapper.findAll('.cs-article__image')
    expect(imgs).toHaveLength(2)
    expect(imgs[0].attributes('src')).toBe('/images/help/download-invoice-en-1.png')
    expect(imgs[1].attributes('src')).toBe('/images/help/download-invoice-en-2.png')
    const text = wrapper.find('.cs-article__body').text()
    expect(text).toContain('1. Go to My Orders.')
    expect(text).toContain('3. Tap the Invoice button to download it.')
    expect(text).toContain('paper invoices are not included in shipments')
  })

  it('renders in-content related-article links as local /help/<slug> routes', () => {
    const wrapper = mountPage('statutory-rights')
    const links = wrapper.findAll('.cs-article__body a')
    const hrefs = links.map((link) => link.attributes('href'))
    expect(hrefs).toContain('/help/our-return-policy')
    expect(hrefs).toContain('/help/return-exceptions')
    for (const href of hrefs) {
      expect(href.startsWith('/help/') || href.startsWith('https://www.joyfumi.com')).toBe(true)
    }
  })

  it('renders the ordered complaint steps (en uses ol, zh uses ul as on the real site)', () => {
    const en = mountPage('submit-complaint')
    expect(en.find('.cs-article__list').element.tagName).toBe('OL')
    expect(en.findAll('.cs-article__list li')).toHaveLength(3)
    expect(en.text()).toContain('Joybuyfumi@gmail.com')

    beforeEachLocale('zh')
    try {
      const zh = mountPage('submit-complaint')
      expect(zh.find('.cs-article__list').element.tagName).toBe('UL')
      expect(zh.find('.cs-article__title').text()).toBe('提交投诉')
    } finally {
      beforeEachLocale('en')
    }
  })

  it('renders zh title, breadcrumb and body for a zh article', () => {
    beforeEachLocale('zh')
    try {
      const wrapper = mountPage('return-request')
      expect(wrapper.find('.cs-article__breadcrumb-link').text()).toBe('退货与退款')
      expect(wrapper.find('.cs-article__breadcrumb-link').attributes('href')).toBe(
        '/help/returns-and-refunds',
      )
      expect(wrapper.find('.cs-article__breadcrumb-current').text()).toBe('如何申请退货退款？')
      expect(wrapper.find('.cs-article__title').text()).toBe('如何申请退货退款？')
      expect(wrapper.findAll('.cs-article__image')).toHaveLength(1)
      expect(wrapper.findAll('.cs-article__image')[0].attributes('src')).toBe(
        '/images/help/return-request-zh-1.jpg',
      )
    } finally {
      beforeEachLocale('en')
    }
  })

  it('renders every registered article (16) without throwing, all content free of real domains', () => {
    for (const slug of Object.keys(csArticleBySlug)) {
      const wrapper = mountPage(slug)
      expect(wrapper.find('.cs-article__title').text()).toBe(csArticleBySlug[slug].title.en)
      expect(wrapper.html()).not.toMatch(/joybuy\.(co\.uk|com)/i)
      expect(wrapper.html()).not.toMatch(/support@joybuy\.com/i)
    }
  })
})
