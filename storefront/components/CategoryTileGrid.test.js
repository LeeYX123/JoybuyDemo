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

  // 13.1①② (2026-11-19): channel variant — grey block wraps only the image,
  // name sits outside with the measured type, tiles stack into row columns.
  it('channel variant wraps only the image in the grey block and keeps the name outside', () => {
    const wrapper = mountGrid({ variant: 'channel', nameChars: 9 })
    const grid = wrapper.get('.category-tiles')
    // 9-char names → 194px tile (6-char names would be 140px).
    expect(grid.attributes('style')).toContain('--tile-size: 194px')
    const tile = wrapper.get('.category-tile')
    expect(tile.classes()).not.toContain('category-tile--active')
    const media = tile.get('.category-tile__media')
    // The image lives inside the media block; the name is a sibling AFTER it.
    expect(media.find('.category-tile__image').exists()).toBe(true)
    const name = tile.get('.category-tile__name')
    expect(media.element.contains(name.element)).toBe(false)
    expect(name.classes()).toContain('category-tile__name')
  })

  it('channel variant uses the 140px tile size for 6-char names', () => {
    const wrapper = mountGrid({ variant: 'channel', nameChars: 6 })
    expect(wrapper.get('.category-tiles').attributes('style')).toContain('--tile-size: 140px')
  })

  it('channel variant stacks tiles into columns of the configured row count', () => {
    const wrapper = mountGrid({ variant: 'channel', columns: 2 })
    const columns = wrapper.findAll('.category-tiles__col')
    expect(columns).toHaveLength(1)
    expect(columns[0].findAll('.category-tile')).toHaveLength(2)
  })
})
