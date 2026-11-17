import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import CategoryTileGrid from './CategoryTileGrid.vue'

vi.mock('../assets/category-images', () => ({
  categoryImages: {
    'mobile-phones': '/images/categories/mobile-phones.webp',
  },
}))

const RouterLinkStub = {
  name: 'RouterLinkStub',
  props: ['to'],
  template: '<a :href="to"><slot /></a>',
}

const items = [
  { slug: 'mobile-phones', name_en: 'Phones', name_zh: '手机' },
  { slug: 'tablets', name_en: 'Tablets', name_zh: '平板电脑' },
]

function mountGrid(props = {}) {
  return mount(CategoryTileGrid, {
    props: { items, ...props },
    global: { stubs: { NuxtLink: RouterLinkStub } },
  })
}

describe('CategoryTileGrid', () => {
  it('renders one local tile per category and links to the category page', () => {
    const wrapper = mountGrid()
    const tiles = wrapper.findAll('.category-tile')
    expect(tiles).toHaveLength(2)
    expect(tiles.map((tile) => tile.attributes('href'))).toEqual(['/c/mobile-phones', '/c/tablets'])
    // Manifest hit first, local placeholder fallback for the rest.
    const images = wrapper.findAll('.category-tile__image')
    expect(images[0].attributes('src')).toBe('/images/categories/mobile-phones.webp')
    expect(images[1].attributes('src')).toBe('/images/categories/_placeholder.svg')
    for (const image of images) {
      expect(image.attributes('src')).not.toMatch(/^https?:/)
    }
  })

  it('marks only the active category as selected', () => {
    const wrapper = mountGrid({ activeSlug: 'tablets' })
    const tiles = wrapper.findAll('.category-tile')
    expect(tiles[0].classes()).not.toContain('category-tile--active')
    expect(tiles[1].classes()).toContain('category-tile--active')
  })

  it('emits the slug when a tile is clicked', async () => {
    const wrapper = mountGrid()
    await wrapper.findAll('.category-tile')[1].trigger('click')
    expect(wrapper.emitted('select')).toEqual([['tablets']])
  })
})
