import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// 页一 payload 固定（SSR 首屏 24 件）；"View more" 点击用 $fetch 追加页二。
const pageOne = {
  page: 1,
  page_size: 24,
  total: 48,
  items: Array.from({ length: 24 }, (_, i) => ({
    spu_public_id: `spu-${i + 1}`,
    title: `Reco Product ${i + 1}`,
    brand: 'BrandX',
    price_min: '9.99',
    currency: 'GBP',
    image_path: '',
  })),
}
const pageTwo = {
  page: 2,
  page_size: 24,
  total: 48,
  items: Array.from({ length: 24 }, (_, i) => ({
    spu_public_id: `spu-${i + 25}`,
    title: `Reco Product ${i + 25}`,
    brand: 'BrandX',
    price_min: '19.99',
    currency: 'GBP',
    image_path: '',
  })),
}

vi.mock('#imports', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    useFetch: () => ({ data: ref(ssrPayload), error: ref(null) }),
  }
})

const fetchMock = vi.fn(async () => pageTwo)
vi.stubGlobal('$fetch', fetchMock)

// 可变的 SSR 页一 payload（默认 total 48；补行动作用例换成大池 total 240）。
let ssrPayload = pageOne

import { defineComponent } from 'vue'
import HomeRecommended from './HomeRecommended.vue'

// 组件 setup 是 async（await useFetch，SSR 直出首屏）：async setup 必须挂在
// Suspense 边界里才会渲染，所以测试里包一层 Suspense 再 flush。
const SuspenseMount = defineComponent({
  components: { HomeRecommended },
  template: '<Suspense><HomeRecommended /></Suspense>',
})

describe('HomeRecommended', () => {
  beforeEach(() => {
    fetchMock.mockClear()
    ssrPayload = pageOne
    // 默认按桌面 5 列（无断点命中）。个别用例会覆盖以模拟 1024/768 视口。
    window.matchMedia = vi.fn(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
  })

  it('renders the floor title with the first SSR batch and no tab row', async () => {
    const wrapper = mount(SuspenseMount)
    await flushPromises()
    expect(wrapper.get('.home-reco__title').text()).toBe('Recommended for you')
    // 16.2 修正：首屏 24 件同样补齐到 5 的整数倍 → 25 件，末行满格。
    expect(wrapper.findAll('.home-reco__grid li')).toHaveLength(25)
    // 无个性化 tab 行（需求文档03 11.6）。
    expect(wrapper.find('.home-reco__tabs').exists()).toBe(false)
    expect(wrapper.get('.home-reco__more-btn').text()).toBe('View more')
  })

  it('fills the first screen with a cycled item from the pool head', async () => {
    const wrapper = mount(SuspenseMount, {
      global: {
        stubs: {
          ProductCard: { props: ['product'], template: '<span>{{ product.spu_public_id }}</span>' },
        },
      },
    })
    await flushPromises()
    const lis = wrapper.findAll('.home-reco__grid li')
    expect(lis).toHaveLength(25)
    expect(lis[24].text()).toBe('spu-1')
  })

  it('pads to the actual column count after hydration (3 columns at 1024)', async () => {
    // 1024 视口命中 ≤80rem（3 列）、不命中 ≤48rem：24 件正好整行，不再补。
    window.matchMedia = vi.fn((query) => ({
      matches: query.includes('80rem') && !query.includes('48rem'),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
    const wrapper = mount(SuspenseMount)
    await flushPromises()
    expect(wrapper.findAll('.home-reco__grid li')).toHaveLength(24)
    expect(24 % 3).toBe(0)
  })

  it('pads to 2 columns on mobile after hydration', async () => {
    window.matchMedia = vi.fn(() => ({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
    const wrapper = mount(SuspenseMount)
    await flushPromises()
    // 24 件在 2 列下本就整行；这里校验列数切换后仍无残缺末行。
    expect(wrapper.findAll('.home-reco__grid li')).toHaveLength(24)
    expect(24 % 2).toBe(0)
  })

  it('appends the next page on "View more" and ends at the pool total', async () => {
    // 商品卡换成能输出 spu id 的桩，便于校验补齐的两件确实来自池头。
    const wrapper = mount(SuspenseMount, {
      global: {
        stubs: {
          ProductCard: { props: ['product'], template: '<span>{{ product.spu_public_id }}</span>' },
        },
      },
    })
    await flushPromises()
    await wrapper.get('.home-reco__more-btn').trigger('click')
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/recommendations?page=2')
    // 16.2：追加 24 件后总数 48（不是 5 的倍数）→ 从池头循环补 2 件到 50，
    // 最后一行满 5 个（不留 3 件空缺、不用占位骨架/灰块）。
    expect(wrapper.findAll('.home-reco__grid li')).toHaveLength(50)
    expect(wrapper.findAll('.home-reco__grid li')[48].text()).toBe('spu-1')
    expect(wrapper.findAll('.home-reco__grid li')[49].text()).toBe('spu-2')
    // total 48 已拉满 → 按钮区变为「已加载全部」。（无重复由后端分页保证，
    // 后端 catalog.tests.test_search.RecommendationTests 覆盖。）
    expect(wrapper.find('.home-reco__more-btn').exists()).toBe(false)
    expect(wrapper.get('.home-reco__end').text()).toBe('All loaded')
  })

  it('keeps the last row full across consecutive appends (24-item batches)', async () => {
    // 大池（total 240）：页一 24 件，每点一次追加 24 件。
    ssrPayload = { ...pageOne, total: 240 }
    const wrapper = mount(SuspenseMount)
    await flushPromises()
    for (const expected of [50, 75]) {
      await wrapper.get('.home-reco__more-btn').trigger('click')
      await vi.waitFor(() => expect(wrapper.findAll('.home-reco__grid li')).toHaveLength(expected))
      expect(expected % 5).toBe(0)
    }
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(wrapper.find('.home-reco__more-btn').exists()).toBe(true)
  })
})
