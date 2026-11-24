import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import MobileListing from './MobileListing.vue'

// Mobile listing (docs/20 §1): toolbar (result count + sort select), 2-column
// product grid and the prev/next pager. useSearch is mocked with the same
// payload shape the desktop listing consumes (items/total/total_pages);
// tests assert against the English dictionary (the locale stub defaults en).
vi.mock('../../composables/useSearchApi', async () => {
  const { ref } = await import('vue')
  const state = {
    data: ref({
      items: [
        {
          spu_public_id: 'spu-1',
          title: 'Ceramic mug 350ml',
          retail_price: '12.90',
          image_path: '/images/mug.jpg',
        },
        {
          spu_public_id: 'spu-2',
          title: 'Linen cushion cover',
          retail_price: null,
          price_min: 8.5,
          image_path: '',
        },
        {
          spu_public_id: 'spu-3',
          title: 'Oak serving tray',
          price_min: 21,
        },
      ],
      total: 3,
      total_pages: 2,
    }),
    error: ref(null),
    status: ref('success'),
  }
  return {
    // Shared reactive state: a test can swap the payload before mounting.
    useSearch: () => state,
  }
})

function mountListing() {
  return mount(MobileListing, {
    props: { mode: 'category', slug: 'home-living' },
    global: {
      stubs: {
        NuxtLink: { template: '<a><slot /></a>' },
      },
    },
  })
}

describe('MobileListing', () => {
  it('renders the toolbar, 2-column cards and the pager', () => {
    const wrapper = mountListing()

    // Toolbar: result count + sort select with the listing.sort* options.
    expect(wrapper.find('.m-list__toolbar').exists()).toBe(true)
    expect(wrapper.find('.m-list__count').text()).toContain('3')
    const options = wrapper.findAll('option')
    expect(options).toHaveLength(4)
    expect(options.map((option) => option.element.value)).toEqual([
      'relevance',
      'price_asc',
      'price_desc',
      'rating_desc',
    ])

    // Grid: one card per item, price falls back retail_price -> price_min.
    const cards = wrapper.findAll('.m-list__card')
    expect(cards).toHaveLength(3)
    expect(wrapper.find('.m-list__price').text()).toBe('12.90')

    // Pager: prev/next buttons + current x/y indicator.
    expect(wrapper.find('.m-list__pager').exists()).toBe(true)
    expect(wrapper.find('.m-list__pager-page').text()).toBe('Page 1 of 2')
    const pagerButtons = wrapper.findAll('.m-list__pager-btn')
    expect(pagerButtons[0].attributes('disabled')).toBeDefined()
    expect(pagerButtons[1].attributes('disabled')).toBeUndefined()
  })

  it('shows the friendly empty state when the API returns no items', async () => {
    const { useSearch } = await import('../../composables/useSearchApi')
    useSearch().data.value = { items: [], total: 0, total_pages: 0 }

    const wrapper = mountListing()
    const state = wrapper.find('.m-list__state')
    expect(state.exists()).toBe(true)
    expect(state.attributes('role')).toBe('status')
    expect(wrapper.find('.m-list__grid').exists()).toBe(false)
    expect(wrapper.find('.m-list__pager').exists()).toBe(false)
  })
})
