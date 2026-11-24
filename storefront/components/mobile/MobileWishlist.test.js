import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import MobilePageHeader from './MobilePageHeader.vue'
import MobileWishlist from './MobileWishlist.vue'

// Mobile wishlist (docs/20 §5.3): 2-column product cards (same style as the
// mobile listing) with a remove button per card; removal is emitted with the
// spu id so the page keeps useWishlist in sync.
const items = [
  { spuId: 'spu-1', title: 'Ceramic mug 350ml', price: '£12.90', image: '/images/mug.jpg' },
  { spuId: 'spu-2', title: 'Linen cushion cover', price: '£8.50', image: '' },
]

function mountWishlist(props = {}) {
  return mount(MobileWishlist, {
    props: { items, ...props },
    global: {
      components: { MobilePageHeader },
      stubs: {
        NuxtLink: { template: '<a><slot /></a>' },
      },
    },
  })
}

describe('MobileWishlist', () => {
  it('renders 2-column product cards and emits remove with the spu id', async () => {
    const wrapper = mountWishlist()

    expect(wrapper.find('.m-page-head__title').text()).toBe('Favourites')

    const cards = wrapper.findAll('.m-wish__card')
    expect(cards).toHaveLength(2)
    expect(cards[0].attributes('to')).toBe('/p/spu-1')
    expect(wrapper.find('.m-wish__img').attributes('src')).toBe('/images/mug.jpg')
    expect(cards[0].find('.m-wish__name').text()).toBe('Ceramic mug 350ml')
    expect(cards[0].find('.m-wish__price').text()).toBe('£12.90')

    // Second card has no image -> falls back to the local logo placeholder.
    expect(wrapper.findAll('.m-wish__img')[1].attributes('src')).toBe('/images/logo.png')

    await wrapper.findAll('.m-wish__remove')[0].trigger('click')
    expect(wrapper.emitted().remove[0]).toEqual(['spu-1'])
  })

  it('shows the empty state when the wishlist is empty', () => {
    const wrapper = mountWishlist({ items: [] })

    const empty = wrapper.find('.m-wish__empty')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('Your wishlist is empty.')
    expect(wrapper.find('a.m-wish__shopping').attributes('to')).toBe('/')
    expect(wrapper.find('.m-wish__grid').exists()).toBe(false)
  })
})
