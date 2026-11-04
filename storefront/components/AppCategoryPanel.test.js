import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AppCategoryPanel from './AppCategoryPanel.vue'

const RouterLinkStub = {
  name: 'RouterLinkStub',
  props: ['to'],
  template: '<a :href="to"><slot /></a>',
}

const categories = [
  {
    slug: 'home-living',
    name: 'Home & Living',
    name_en: 'Home & Living',
    name_zh: '家居生活',
    children: [
      { slug: 'kitchen-essentials', name_en: 'Kitchen Essentials', name_zh: '厨房用品' },
      { slug: 'bedding-textiles', name_en: 'Bedding & Textiles', name_zh: '床品家纺' },
    ],
  },
  {
    slug: 'electronics',
    name: 'Electronics',
    name_en: 'Electronics',
    name_zh: '电子产品',
    children: [{ slug: 'tv-audio', name_en: 'TV & Audio', name_zh: '电视与影音' }],
  },
]

function mountPanel(props = {}) {
  return mount(AppCategoryPanel, {
    props: { open: true, categories, ...props },
    global: { stubs: { NuxtLink: RouterLinkStub, Teleport: true } },
  })
}

describe('AppCategoryPanel', () => {
  it('lists every root and the children of the selected root only', async () => {
    const wrapper = mountPanel()
    expect(wrapper.findAll('.category-panel__root').map((item) => item.text())).toEqual([
      'Home & Living',
      'Electronics',
    ])
    // Strict linkage (requirement 1-2): only the selected root's children.
    expect(wrapper.findAll('.category-panel__child').map((link) => link.text())).toEqual([
      'Kitchen Essentials',
      'Bedding & Textiles',
    ])

    // Hover switches the children too (real-site behaviour), click works as
    // well; the hovered/active row is bold black, never the accent red.
    await wrapper.findAll('.category-panel__root')[1].trigger('mouseenter')
    expect(wrapper.findAll('.category-panel__child').map((link) => link.text())).toEqual([
      'TV & Audio',
    ])
    expect(wrapper.findAll('.category-panel__child')[0].attributes('href')).toBe('/c/tv-audio')

    await wrapper.findAll('.category-panel__root')[0].trigger('click')
    expect(wrapper.findAll('.category-panel__child').map((link) => link.text())).toEqual([
      'Kitchen Essentials',
      'Bedding & Textiles',
    ])
    const active = wrapper.get('.category-panel__root--active')
    expect(active.classes()).not.toContain('category-panel__root--red')
    expect(active.text()).toBe('Home & Living')
  })

  it('renders nothing when closed and emits close from the close button', async () => {
    expect(mountPanel({ open: false }).find('.category-panel').exists()).toBe(false)

    const wrapper = mountPanel()
    await wrapper.get('.category-panel__close').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })
})
