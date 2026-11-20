import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AppFooter from './AppFooter.vue'

// 需求 12.1（批次 E）→ 需求 16.5（批次 S）：页脚 1:1 复刻真站 footer_jdiFooter——
// 三列 10 链接（Get to know us 3 / Our policies 5 / Let us help you 2），
// 全部指向本地内容页 /pages/<slug>；© 行与演示声明保留。
const NuxtLinkStub = {
  name: 'NuxtLinkStub',
  props: ['to'],
  template: '<a :href="to"><slot /></a>',
}

function mountFooter() {
  return mount(AppFooter, { global: { stubs: { NuxtLink: NuxtLinkStub } } })
}

describe('AppFooter', () => {
  it('renders the three real-site columns with their links', () => {
    const wrapper = mountFooter()
    const titles = wrapper.findAll('.footer-column__title').map((node) => node.text())
    expect(titles).toEqual(['Get to know us', 'Our policies', 'Let us help you'])
    expect(wrapper.findAll('.footer-column__link').length).toBe(10)
  })

  it('links every footer entry to its local content page slug', () => {
    const wrapper = mountFooter()
    const hrefs = wrapper.findAll('.footer-column__link').map((node) => node.attributes('href'))
    expect(hrefs).toEqual([
      '/pages/contact-us',
      '/pages/about-us',
      '/pages/joybuy-news',
      '/pages/cookie-policy',
      '/pages/privacy-policy',
      '/pages/terms-conditions',
      '/pages/terms-of-use',
      '/pages/accessibility-statement',
      '/pages/payment-and-invoice',
      '/pages/returns-and-refunds',
    ])
  })

  it('drops JoyPlus and keeps the policy + help columns per requirement 16.5', () => {
    const wrapper = mountFooter()
    const hrefs = wrapper.findAll('.footer-column__link').map((node) => node.attributes('href'))
    const labels = wrapper.findAll('.footer-column__link').map((node) => node.text())
    expect(hrefs).not.toContain('/pages/joyplus')
    expect(labels).not.toContain('JoyPlus')
    expect(labels).toContain('Terms of Sale')
    expect(labels).toContain('Accessibility Statement')
    expect(labels).toContain('Payment and invoice')
    expect(labels).toContain('Returns and refunds')
  })

  it('renders the real-site top row, newsletter, app QR and We support row', () => {
    const wrapper = mountFooter()
    // 需求 13.6（批次 M）：顶行（logo+口号 / 语言·货币·国家）与中部（订阅 + App 下载）
    // 注释不渲染（代码保留），We support 支付行保留。
    expect(wrapper.find('.footer-top').exists()).toBe(false)
    expect(wrapper.find('.footer-top__slogan').exists()).toBe(false)
    expect(wrapper.find('.footer-middle').exists()).toBe(false)
    expect(wrapper.find('.footer-middle__qr').exists()).toBe(false)
    expect(wrapper.findAll('.footer-support__icon').length).toBe(7)
  })

  it('states the demo nature in the legal block', () => {
    const wrapper = mountFooter()
    const legal = wrapper
      .findAll('.footer-legal')
      .map((node) => node.text())
      .join(' ')
    expect(legal).toContain('demo replica')
    // 需求 13.6：最底部【内部研究演示项目…】声明行去掉。
    expect(legal).not.toContain('Demo project')
  })

  // 需求 17.4：三栏条目间距收紧为真站节奏（14px 字号、列表 gap 16px、
  // 相邻链接 y 差 37px）。间距值属计算样式，vitest（happy-dom，css 不注入）
  // 测不到，由 Playwright e2e 实测相邻链接 y 差值；这里断言承载结构完整。
  it('keeps the tightened column list structure for the real-site rhythm', () => {
    const wrapper = mountFooter()
    const lists = wrapper.findAll('.footer-column__list')
    expect(lists.length).toBe(3)
    // 每栏条目数与 16.5 口径一致（3 / 5 / 2），条目仍为链接元素。
    expect(lists.map((list) => list.findAll('.footer-column__link').length)).toEqual([3, 5, 2])
  })
})
