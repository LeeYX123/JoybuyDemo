import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, Suspense } from 'vue'
import { describe, expect, it, vi, beforeEach } from 'vitest'

// The component reads market/locale query + locale strings; stub them like the
// other component tests do.
vi.mock('../composables/useMarketLocale', () => ({
  useMarketLocale: () => ({ apiQuery: { market: 'GB', locale: 'en-GB' } }),
}))

vi.mock('../composables/useLocale', () => ({
  useLocale: () => ({
    t: (key) =>
      ({
        'reco.pickedForYou': 'Picked for you',
        'reco.viewMore': 'View more',
        'reco.loading': 'Loading…',
      })[key] || key,
  }),
}))

// SSR first batch comes from useFetch (mutable per test); later batches from
// global $fetch.
const fetchCalls = []
let fetchNextBatch = { items: [] }
let ssrPayload = {
  items: [{ spu_public_id: 'reco-1', title: 'First Batch A', price_min: 1.5 }],
  total: 24,
  total_pages: 2,
  page: 1,
  page_size: 12,
}

vi.mock('#imports', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    useFetch: () => {
      fetchCalls.push({ name: 'useFetch' })
      return { data: { value: ssrPayload }, error: { value: null }, refresh: async () => {} }
    },
    useRuntimeConfig: () => ({
      apiBaseInternal: 'http://127.0.0.1:8000/api/v1',
      public: { apiBase: '/api/v1' },
    }),
  }
})

import ChannelPickedForYou from './ChannelPickedForYou.vue'
import ProductCard from './ProductCard.vue'
import BaseRatingStars from './BaseRatingStars.vue'

const RouterLinkStub = {
  name: 'RouterLinkStub',
  props: ['to'],
  template: '<a :href="to"><slot /></a>',
}

// IntersectionObserver stand-in that lets the test fire the callback.
let observerCallback = null

class MockIntersectionObserver {
  constructor(callback) {
    observerCallback = callback
    this.observed = []
  }

  observe(el) {
    this.observed.push(el)
  }

  disconnect() {
    this.observed = []
  }

  unobserve() {}
}

// The component awaits useFetch in setup, so it must mount inside a Suspense
// boundary like the Nuxt page outlet does. Props are mutable per test (e.g.
// the channel page's moreLabel) so a single holder covers every case.
const recoProps = { value: { categorySlug: 'home-living' } }
const RecoHolder = defineComponent({
  setup() {
    return () =>
      h(Suspense, null, {
        default: () => h(ChannelPickedForYou, recoProps.value),
      })
  },
})

async function mountReco() {
  const wrapper = mount(RecoHolder, {
    global: { stubs: { NuxtLink: RouterLinkStub, ProductCard: true } },
  })
  // Async setup resolves on the microtask queue; flush it so onMounted ran.
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  fetchCalls.length = 0
  recoProps.value = { categorySlug: 'home-living' }
  fetchNextBatch = { items: [] }
  ssrPayload = {
    items: [{ spu_public_id: 'reco-1', title: 'First Batch A', price_min: 1.5 }],
    total: 24,
    total_pages: 2,
    page: 1,
    page_size: 12,
  }
  observerCallback = null
  globalThis.IntersectionObserver = MockIntersectionObserver
  globalThis.$fetch = async (url) => {
    fetchCalls.push({ url })
    return fetchNextBatch
  }
})

describe('ChannelPickedForYou (13.4)', () => {
  it('renders the first SSR batch as borderless cards with the module title', async () => {
    const wrapper = await mountReco()
    expect(wrapper.get('.picked-for-you__title').text()).toBe('Picked for you')
    expect(wrapper.findAll('.picked-for-you__grid li')).toHaveLength(1)
    // The View more button must NOT exist before the first automatic load.
    expect(wrapper.find('.picked-for-you__more-btn').exists()).toBe(false)
  })

  it('auto-loads the next batch once when the module bottom scrolls into view', async () => {
    fetchNextBatch = {
      items: [
        { spu_public_id: 'reco-2', title: 'Second Batch B', price_min: 2.5 },
        { spu_public_id: 'reco-3', title: 'Second Batch C', price_min: 3.5 },
      ],
    }
    const wrapper = await mountReco()
    expect(observerCallback).toBeTypeOf('function')
    // Simulate the sentinel entering the viewport.
    observerCallback([{ isIntersecting: true }])
    await vi.waitFor(() => expect(fetchCalls).toHaveLength(2))
    // The follow-up request cycles: category + page=2 + cycle=1.
    const url = fetchCalls[1].url
    expect(url).toContain('/recommendations?')
    expect(url).toContain('category=home-living')
    expect(url).toContain('page=2')
    expect(url).toContain('cycle=1')
    await flushPromises()
    expect(wrapper.findAll('.picked-for-you__grid li')).toHaveLength(3)
    // After the first automatic load the View more button appears.
    expect(wrapper.get('.picked-for-you__more-btn').text()).toBe('View more')
    // A second intersection must not fire another automatic load.
    observerCallback([{ isIntersecting: true }])
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(fetchCalls).toHaveLength(2)
  })

  it('loads further batches on View more clicks (pool cycles server-side)', async () => {
    fetchNextBatch = { items: [{ spu_public_id: 'reco-9', title: 'Third Batch D', price_min: 4 }] }
    const wrapper = await mountReco()
    observerCallback([{ isIntersecting: true }])
    await vi.waitFor(() => expect(wrapper.find('.picked-for-you__more-btn').exists()).toBe(true))
    await wrapper.get('.picked-for-you__more-btn').trigger('click')
    await vi.waitFor(() => expect(fetchCalls).toHaveLength(3))
    expect(fetchCalls[2].url).toContain('page=3')
    expect(fetchCalls[2].url).toContain('cycle=1')
    await flushPromises()
    expect(wrapper.findAll('.picked-for-you__grid li')).toHaveLength(3)
  })

  it('hides the whole module when the category pool is empty', async () => {
    ssrPayload = { items: [], total: 0, total_pages: 1, page: 1, page_size: 12 }
    const wrapper = await mountReco()
    expect(wrapper.find('.picked-for-you').exists()).toBe(false)
  })

  // 需求 16.4：频道页把按钮文案覆盖为【更多 / More】；不传时保持购物车页的
  // 既有「查看更多」（上方用例已覆盖默认值）。
  it('accepts a caller-provided more label (channel pages use「More」)', async () => {
    recoProps.value = { moreLabel: 'More' }
    const wrapper = await mountReco()
    observerCallback([{ isIntersecting: true }])
    await vi.waitFor(() => expect(wrapper.find('.picked-for-you__more-btn').exists()).toBe(true))
    // 按钮同时带共享组件类，样式与首页【查看更多】同一份实现。
    expect(wrapper.get('.picked-for-you__more-btn').classes()).toContain('app-more-btn')
    expect(wrapper.get('.picked-for-you__more-btn').text()).toBe('More')
  })

  // 2026-11-24 频道页口径：卡片与楼层卡同款——无评分行、无品牌行、价格走
  // retail_price 优先（推荐接口没有该字段时回退 price_min，不出现 $0.00）。
  it('renders channel-page cards like floor cards when the page opts in', async () => {
    ssrPayload = {
      items: [
        {
          spu_public_id: 'reco-rated',
          title: 'Rated thing',
          brand: 'ACME',
          price_min: 1.5,
          rating_average: '4.5',
          rating_count: 9,
          original_price: 9.9,
        },
        {
          spu_public_id: 'reco-retail',
          title: 'Retail priced',
          brand: 'ACME',
          price_min: 8.5,
          retail_price: '12.0000',
        },
      ],
      total: 2,
      total_pages: 1,
      page: 1,
      page_size: 24,
    }
    recoProps.value = {
      categorySlug: 'home-living',
      showRating: false,
      useRetailPrice: true,
      showBrand: false,
    }
    const wrapper = mount(RecoHolder, {
      global: {
        components: { ProductCard, BaseRatingStars },
        stubs: { NuxtLink: RouterLinkStub, BaseSkeleton: true },
      },
    })
    await flushPromises()
    const cards = wrapper.findAll('.product-card')
    expect(cards).toHaveLength(2)
    // 无评分行、无品牌行、无划线原价。
    expect(wrapper.find('.rating-stars').exists()).toBe(false)
    expect(wrapper.find('.product-card__brand').exists()).toBe(false)
    expect(wrapper.find('s').exists()).toBe(false)
    // 有 retail_price 用它；没有则回退 price_min。
    expect(cards[0].get('.product-card__price').text()).toBe('$1.50')
    expect(cards[1].get('.product-card__price').text()).toBe('$12.00')
    wrapper.unmount()
  })

  // 默认值（购物车页复用）保持改前行为：有评分行、普通 price_min 口径。
  it('keeps the cart-page defaults (rating row shown, price_min price)', async () => {
    ssrPayload = {
      items: [
        {
          spu_public_id: 'reco-rated',
          title: 'Rated thing',
          brand: 'ACME',
          price_min: 1.5,
          rating_average: '4.5',
          rating_count: 9,
        },
      ],
      total: 1,
      total_pages: 1,
      page: 1,
      page_size: 24,
    }
    const wrapper = mount(RecoHolder, {
      global: {
        components: { ProductCard, BaseRatingStars },
        stubs: { NuxtLink: RouterLinkStub, BaseSkeleton: true },
      },
    })
    await flushPromises()
    expect(wrapper.find('.rating-stars').exists()).toBe(true)
    expect(wrapper.get('.product-card__brand').text()).toBe('ACME')
    expect(wrapper.get('.product-card__price').text()).toBe('$1.50')
    wrapper.unmount()
  })

  // 需求 13.7-3：购物车页复用——不传 categorySlug = 全库池（URL 不带 category 参数）。
  it('requests the whole pool without a category param when categorySlug is omitted', async () => {
    const AllPoolHolder = defineComponent({
      setup() {
        return () => h(Suspense, null, { default: () => h(ChannelPickedForYou) })
      },
    })
    fetchNextBatch = { items: [{ spu_public_id: 'reco-2', title: 'Pool B', price_min: 2 }] }
    const wrapper = mount(AllPoolHolder, {
      global: { stubs: { NuxtLink: RouterLinkStub, ProductCard: true } },
    })
    await flushPromises()
    observerCallback([{ isIntersecting: true }])
    await vi.waitFor(() => expect(fetchCalls).toHaveLength(2))
    const url = fetchCalls[1].url
    expect(url).toContain('/recommendations?')
    expect(url).not.toContain('category=')
    expect(url).toContain('page=2')
    expect(url).toContain('cycle=1')
    await flushPromises()
    expect(wrapper.findAll('.picked-for-you__grid li')).toHaveLength(2)
  })
})
