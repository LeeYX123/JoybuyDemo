import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'

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
    ]),
  }),
}))

// The floor loads the active tab's ranking via $fetch on tab switch; stub it.
const fetchMock = vi.fn(async () => ({ items: [] }))
vi.stubGlobal('$fetch', fetchMock)

import HomeBestsellers from './HomeBestsellers.vue'

const RouterLinkStub = {
  name: 'RouterLinkStub',
  props: ['to'],
  template: '<a :href="to"><slot /></a>',
}

function mountFloor() {
  return mount(HomeBestsellers, {
    global: { stubs: { NuxtLink: RouterLinkStub } },
  })
}

describe('HomeBestsellers', () => {
  it('renders the floor title, View all link and one tab per category', () => {
    const wrapper = mountFloor()
    expect(wrapper.get('.home-bestsellers__title').text()).toBe('Bestsellers')
    expect(wrapper.get('.home-bestsellers__view-all').attributes('href')).toBe(
      '/promo/best-seller?category=home-living',
    )
    const tabs = wrapper.findAll('.home-bestsellers__tab')
    expect(tabs.map((tab) => tab.text())).toEqual(['Home & Living', 'Electronics'])
    expect(tabs[0].classes()).toContain('home-bestsellers__tab--active')
  })

  it('switches the active tab on click and refreshes the ranking', async () => {
    const wrapper = mountFloor()
    fetchMock.mockClear()
    await wrapper.findAll('.home-bestsellers__tab')[1].trigger('click')
    expect(wrapper.findAll('.home-bestsellers__tab')[1].classes()).toContain(
      'home-bestsellers__tab--active',
    )
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/search?category=electronics&sort=rating_desc&page=1',
    )
    // View all follows the active tab.
    expect(wrapper.get('.home-bestsellers__view-all').attributes('href')).toBe(
      '/promo/best-seller?category=electronics',
    )
  })
})
