import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../composables/useCategoryTree', () => ({
  useCategoryTree: () => ({
    categories: ref([
      {
        slug: 'home-living',
        name: 'Home & Living',
        name_en: 'Home & Living',
        name_zh: '家居生活',
        children: [],
      },
      {
        slug: 'electronics',
        name: 'Electronics',
        name_en: 'Electronics',
        name_zh: '电子产品',
        children: [],
      },
      {
        slug: 'health-wellness',
        name: 'Health & Wellness',
        name_en: 'Health & Wellness',
        name_zh: '健康保健',
        children: [],
      },
    ]),
  }),
}))

// The floor loads the active tab's ranking via $fetch on tab switch; stub it.
// Responses are keyed by request URL so curated tabs (two sub-category
// requests) and plain tabs (one request) can be asserted separately.
const fetchMock = vi.fn(async (url) => responses[url] ?? { items: [] })
vi.stubGlobal('$fetch', fetchMock)

let responses = {}

function product(id) {
  return {
    spu_public_id: id,
    title: `Product ${id}`,
    brand: '',
    category_slug: 'health-wellness',
    price_min: '9.99',
    price_max: '9.99',
    retail_price: '9.99',
    currency: 'GBP',
    image_path: `/media/products/${id}.jpg`,
    is_family_representative: true,
  }
}

function page(ids) {
  return { page: 1, page_size: 24, total: ids.length, items: ids.map(product) }
}

const search = (slug) => `/api/v1/search?category=${slug}&sort=newest&page=1&market=GB&locale=en-GB`

import HomeBestsellers from './HomeBestsellers.vue'
import { stubCalls } from '../../tests/nuxt-imports-stub'

const RouterLinkStub = {
  name: 'RouterLinkStub',
  props: ['to'],
  template: '<a :href="to"><slot /></a>',
}

const ProductCardStub = {
  name: 'ProductCardStub',
  props: ['product', 'rank'],
  template: '<div class="product-card-stub" />',
}

function mountFloor() {
  return mount(HomeBestsellers, {
    global: { stubs: { NuxtLink: RouterLinkStub, ProductCard: ProductCardStub } },
  })
}

function cardIds(wrapper) {
  return wrapper
    .findAllComponents(ProductCardStub)
    .map((card) => card.props('product').spu_public_id)
}

function ranks(wrapper) {
  return wrapper.findAllComponents(ProductCardStub).map((card) => card.props('rank'))
}

describe('HomeBestsellers', () => {
  beforeEach(() => {
    fetchMock.mockClear()
    responses = {}
    stubCalls.length = 0
  })

  it('keys the SSR row on the locale so a language switch refetches', () => {
    mountFloor()
    const call = stubCalls.filter((entry) => entry.name === 'useAsyncData').at(-1)
    // Reactive key (computed), not a string frozen at setup.
    expect(call.args[0].value).toBe('home-bestsellers-GB-en-GB')
  })

  it('renders the floor title, View all link and one tab per category', () => {
    const wrapper = mountFloor()
    expect(wrapper.get('.home-bestsellers__title').text()).toBe('Bestsellers')
    expect(wrapper.get('.home-bestsellers__view-all').attributes('href')).toBe(
      '/promo/best-seller?category=home-living',
    )
    const tabs = wrapper.findAll('.home-bestsellers__tab')
    expect(tabs.map((tab) => tab.text())).toEqual([
      'Home & Living',
      'Electronics',
      'Health & Wellness',
    ])
    expect(tabs[0].classes()).toContain('home-bestsellers__tab--active')
  })

  it('switches the active tab on click and refreshes the ranking', async () => {
    const wrapper = mountFloor()
    responses[search('electronics')] = page(['e1', 'e2', 'e3', 'e4', 'e5', 'e6'])
    await wrapper.findAll('.home-bestsellers__tab')[1].trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.home-bestsellers__tab')[1].classes()).toContain(
      'home-bestsellers__tab--active',
    )
    // An uncurated tab keeps the original single request.
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/search?category=electronics&sort=newest&page=1&market=GB&locale=en-GB',
    )
    // View all follows the active tab.
    expect(wrapper.get('.home-bestsellers__view-all').attributes('href')).toBe(
      '/promo/best-seller?category=electronics',
    )
    expect(cardIds(wrapper)).toEqual(['e1', 'e2', 'e3', 'e4', 'e5'])
    expect(ranks(wrapper)).toEqual([1, 2, 3, 4, 5])
  })

  it('composes a curated tab from its two sub-categories in 3:2 order', async () => {
    const wrapper = mountFloor()
    responses[search('nutrition-supplements')] = page(['n1', 'n2', 'n3', 'n4'])
    responses[search('sports-nutrition-performance')] = page(['s1', 's2', 's3'])

    await wrapper.findAll('.home-bestsellers__tab')[2].trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/search?category=nutrition-supplements&sort=newest&page=1&market=GB&locale=en-GB',
    )
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/search?category=sports-nutrition-performance&sort=newest&page=1&market=GB&locale=en-GB',
    )
    expect(cardIds(wrapper)).toEqual(['n1', 'n2', 'n3', 's1', 's2'])
    expect(ranks(wrapper)).toEqual([1, 2, 3, 4, 5])
  })

  it('composes the home-living tab as 3 furniture + 2 bedding', async () => {
    const wrapper = mountFloor()
    responses[search('furniture')] = page(['f1', 'f2', 'f3', 'f4'])
    responses[search('bedding-textiles')] = page(['b1', 'b2'])

    await wrapper.findAll('.home-bestsellers__tab')[0].trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(cardIds(wrapper)).toEqual(['f1', 'f2', 'f3', 'b1', 'b2'])
  })
})
