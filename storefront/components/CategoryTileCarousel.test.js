import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import CategoryTileCarousel from './CategoryTileCarousel.vue'

vi.mock('../assets/category-images', () => ({
  categoryImages: {},
}))

const RouterLinkStub = {
  name: 'RouterLinkStub',
  props: ['to'],
  template: '<a :href="to"><slot /></a>',
}

const items = [
  { slug: 'mobile-phones', name_en: 'Phones', name_zh: '手机' },
  { slug: 'tablets', name_en: 'Tablets', name_zh: '平板电脑' },
  { slug: 'tvs', name_en: 'TVs', name_zh: '电视机' },
]

function mountCarousel() {
  return mount(CategoryTileCarousel, {
    props: { items, activeSlug: 'tablets' },
    global: { stubs: { NuxtLink: RouterLinkStub } },
  })
}

// jsdom has no layout engine, so the scroll metrics are stubbed and the
// component's scroll handler is used to recompute the nav state.
async function stubScroll(wrapper, { scrollWidth, clientWidth, scrollLeft = 0 }) {
  const track = wrapper.get('.category-carousel__track').element
  Object.defineProperty(track, 'scrollWidth', { value: scrollWidth, configurable: true })
  Object.defineProperty(track, 'clientWidth', { value: clientWidth, configurable: true })
  Object.defineProperty(track, 'scrollLeft', {
    value: scrollLeft,
    configurable: true,
    writable: true,
  })
  await wrapper.get('.category-carousel__track').trigger('scroll')
  return track
}

describe('CategoryTileCarousel', () => {
  it('hides the nav bar when the row fits', () => {
    const wrapper = mountCarousel()
    expect(wrapper.find('.category-carousel__nav').exists()).toBe(false)
    expect(wrapper.findAll('.category-tile')).toHaveLength(3)
  })

  it('shows arrows and a proportional thumb when the row overflows', async () => {
    const wrapper = mountCarousel()
    await stubScroll(wrapper, { scrollWidth: 400, clientWidth: 100 })

    expect(wrapper.find('.category-carousel__nav').exists()).toBe(true)
    const arrows = wrapper.findAll('.category-carousel__arrow')
    expect(arrows).toHaveLength(2)
    // At the start the previous arrow is disabled, next is available.
    expect(arrows[0].attributes('disabled')).toBeDefined()
    expect(arrows[1].attributes('disabled')).toBeUndefined()
    // Thumb spans the visible fraction of the track.
    expect(wrapper.get('.category-carousel__thumb').attributes('style')).toContain('width: 25%')
  })

  it('moves the thumb and arrow states as the row scrolls', async () => {
    const wrapper = mountCarousel()
    await stubScroll(wrapper, { scrollWidth: 400, clientWidth: 100, scrollLeft: 300 })

    const arrows = wrapper.findAll('.category-carousel__arrow')
    expect(arrows[0].attributes('disabled')).toBeUndefined()
    expect(arrows[1].attributes('disabled')).toBeDefined()
    expect(wrapper.get('.category-carousel__thumb').attributes('style')).toContain('left: 75%')
  })

  it('pages the track by one viewport per arrow click', async () => {
    const wrapper = mountCarousel()
    const track = await stubScroll(wrapper, { scrollWidth: 400, clientWidth: 100 })
    const scrollBy = vi.fn()
    track.scrollBy = scrollBy

    await wrapper.findAll('.category-carousel__arrow')[1].trigger('click')
    expect(scrollBy).toHaveBeenCalledWith({ left: 90, behavior: 'smooth' })
  })
})
