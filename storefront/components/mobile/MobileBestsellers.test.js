import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../composables/useCategoryTree', () => ({
  useCategoryTree: () => ({
    categories: ref([
      { slug: 'home-living', name: 'Home & Living', name_en: 'Home & Living', children: [] },
      { slug: 'electronics', name: 'Electronics', name_en: 'Electronics', children: [] },
      {
        slug: 'health-wellness',
        name: 'Health & Wellness',
        name_en: 'Health & Wellness',
        children: [],
      },
    ]),
  }),
}))

vi.mock('../../composables/useWishlist', () => ({
  useWishlist: () => ({ isFavourite: () => false, toggle: () => {} }),
}))

// Same curation contract as the desktop floor: curated tabs fire one request
// per configured sub-category, everything else keeps the single request.
const fetchMock = vi.fn(async (url) => responses[url] ?? { items: [] })
vi.stubGlobal('$fetch', fetchMock)

let responses = {}

function product(id) {
  return {
    spu_public_id: id,
    title: `Product ${id}`,
    price_min: '9.99',
    retail_price: '9.99',
    image_path: `/media/products/${id}.jpg`,
    is_family_representative: true,
  }
}

const page = (ids) => ({ page: 1, page_size: 24, total: ids.length, items: ids.map(product) })
const search = (slug) => `/api/v1/search?category=${slug}&sort=newest&page=1&market=GB&locale=en-GB`

import MobileBestsellers from './MobileBestsellers.vue'
import { stubCalls } from '../../tests/nuxt-imports-stub'

const RouterLinkStub = {
  name: 'RouterLinkStub',
  props: ['to'],
  template: '<a :href="to"><slot /></a>',
}

function mountFloor() {
  return mount(MobileBestsellers, {
    global: { stubs: { NuxtLink: RouterLinkStub } },
  })
}

const names = (wrapper) => wrapper.findAll('.m-best__name').map((node) => node.text())

describe('MobileBestsellers', () => {
  beforeEach(() => {
    fetchMock.mockClear()
    responses = {}
    stubCalls.length = 0
  })

  it('keys the SSR row on the locale so a language switch refetches', () => {
    mountFloor()
    const call = stubCalls.filter((entry) => entry.name === 'useAsyncData').at(-1)
    // Reactive key (computed), not a string frozen at setup.
    expect(call.args[0].value).toBe('mobile-bestsellers-GB-en-GB')
  })

  it('shows the curated 3:2 row on a curated tab', async () => {
    const wrapper = mountFloor()
    responses[search('nutrition-supplements')] = page(['n1', 'n2', 'n3', 'n4'])
    responses[search('sports-nutrition-performance')] = page(['s1', 's2'])

    await wrapper.findAll('.m-best__tab')[2].trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(names(wrapper)).toEqual([
      'Product n1',
      'Product n2',
      'Product n3',
      'Product s1',
      'Product s2',
    ])
  })

  it('keeps the single request and up-to-10 cards on other tabs', async () => {
    const wrapper = mountFloor()
    responses[search('electronics')] = page(['e1', 'e2', 'e3', 'e4', 'e5', 'e6', 'e7', 'e8'])

    await wrapper.findAll('.m-best__tab')[1].trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith(search('electronics'))
    expect(names(wrapper)).toHaveLength(8)
  })
})
