import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import AppCategoryPanel from './AppCategoryPanel.vue'

// The image manifest is generated offline (var/category_cards_20261111/) and
// maps slug -> local image path. Tests pin it so cases never depend on the
// real sync coverage: one fixture slug with an image, one without.
vi.mock('../assets/category-images', () => ({
  categoryImages: {
    'kitchen-essentials': '/images/categories/kitchen-essentials.webp',
  },
}))

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
    children: [
      {
        slug: 'soundbars-home-cinema',
        name_en: 'Soundbars & Home Cinema',
        name_zh: '音响 & 家庭影院',
      },
    ],
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
    expect(wrapper.findAll('.category-tile__name').map((item) => item.text())).toEqual([
      'Kitchen Essentials',
      'Bedding & Textiles',
    ])

    // Hover switches the children too (real-site behaviour), click works as
    // well; the hovered/active row is bold black, never the accent red.
    await wrapper.findAll('.category-panel__root')[1].trigger('mouseenter')
    expect(wrapper.findAll('.category-tile__name').map((item) => item.text())).toEqual([
      'Soundbars & Home Cinema',
    ])
    expect(wrapper.findAll('.category-tile')[0].attributes('href')).toBe('/c/soundbars-home-cinema')

    await wrapper.findAll('.category-panel__root')[0].trigger('click')
    expect(wrapper.findAll('.category-tile__name').map((item) => item.text())).toEqual([
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

  it('renders children as tile cards: image on top, name below (Joybuy style)', () => {
    const wrapper = mountPanel()
    const cards = wrapper.findAll('.category-tile')
    expect(cards).toHaveLength(2)
    for (const card of cards) {
      // Card anatomy: one square image + one name label, both inside the tile.
      const image = card.find('.category-tile__image')
      const name = card.find('.category-tile__name')
      expect(image.exists()).toBe(true)
      expect(name.exists()).toBe(true)
      expect(card.find('img').element).toBe(image.element)
      expect(image.attributes('alt')).toBe('')
      expect(name.text().length).toBeGreaterThan(0)
    }
  })

  it('takes card images from the local manifest and never renders missing slugs', () => {
    const wrapper = mountPanel()
    const images = wrapper.findAll('.category-tile__image')
    // Manifest hit: local asset path from assets/category-images.js.
    expect(images[0].attributes('src')).toBe('/images/categories/kitchen-essentials.webp')
    // No manifest entry: local placeholder fallback (layout must not break).
    expect(images[1].attributes('src')).toBe('/images/categories/_placeholder.svg')
    for (const image of images) {
      expect(image.attributes('src')).not.toMatch(/^https?:/)
      expect(image.attributes('src')).not.toContain('joy-sourcing')
    }
  })
})
