import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import CategoryTileCarousel from './CategoryTileCarousel.vue'
import { recallStripScroll, rememberStripScroll } from '../utils/categoryStripScroll'

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

// jsdom/happy-dom have no layout engine, so the scroll metrics are stubbed and
// the component's scroll handler (rAF-coalesced) is flushed before asserting.
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
  await nextFrame()
  return track
}

async function nextFrame() {
  await new Promise((resolve) => requestAnimationFrame(() => resolve()))
  await new Promise((resolve) => requestAnimationFrame(() => resolve()))
}

describe('CategoryTileCarousel', () => {
  it('hides the nav bar when the row fits', () => {
    const wrapper = mountCarousel()
    expect(wrapper.find('.category-carousel__nav').exists()).toBe(false)
    expect(wrapper.findAll('.category-tile')).toHaveLength(3)
  })

  it('shows both arrows when the row overflows', async () => {
    const wrapper = mountCarousel()
    await stubScroll(wrapper, { scrollWidth: 400, clientWidth: 100 })

    expect(wrapper.find('.category-carousel__nav').exists()).toBe(true)
    const arrows = wrapper.findAll('.category-carousel__arrow')
    expect(arrows).toHaveLength(2)
    // At the start the previous arrow is disabled, next is available.
    expect(arrows[0].attributes('disabled')).toBeDefined()
    expect(arrows[1].attributes('disabled')).toBeUndefined()
    // The thumb spans the visible fraction of the track (hidden until hover,
    // which jsdom cannot evaluate — the e2e covers visibility). Pixels, not %:
    // 100/400 of a 100px bar = 25px.
    expect(wrapper.get('.category-carousel__thumb').attributes('style')).toContain('width: 25px')
  })

  it('moves the thumb and arrow states as the row scrolls', async () => {
    const wrapper = mountCarousel()
    await stubScroll(wrapper, { scrollWidth: 400, clientWidth: 100, scrollLeft: 300 })

    const arrows = wrapper.findAll('.category-carousel__arrow')
    expect(arrows[0].attributes('disabled')).toBeUndefined()
    expect(arrows[1].attributes('disabled')).toBeDefined()
    expect(wrapper.get('.category-carousel__thumb').attributes('style')).toContain('left: 75px')
  })

  it('pages the track by one viewport per arrow click', async () => {
    const wrapper = mountCarousel()
    const track = await stubScroll(wrapper, { scrollWidth: 400, clientWidth: 100 })
    const scrollBy = vi.fn()
    track.scrollBy = scrollBy

    await wrapper.findAll('.category-carousel__arrow')[1].trigger('click')
    expect(scrollBy).toHaveBeenCalledWith({ left: 90, behavior: 'smooth' })
  })

  // 2026-11-27: switching to a sibling L2 re-mounts the listing strip, so the
  // offset is remembered per parent-category key (utils/categoryStripScroll).
  it('remembers the offset for a scroll key and restores it on the next mount', async () => {
    const wrapper = mount(CategoryTileCarousel, {
      props: { items, activeSlug: 'tablets', scrollKey: 'parent-a' },
      global: { stubs: { NuxtLink: RouterLinkStub } },
    })
    await stubScroll(wrapper, { scrollWidth: 2000, clientWidth: 1000, scrollLeft: 640 })
    wrapper.unmount()

    expect(recallStripScroll('parent-a')).toEqual({ left: 640, ratio: 0.64, width: 2000 })
  })

  it('does not remember anything without a scroll key (channel page)', async () => {
    const wrapper = mountCarousel()
    await stubScroll(wrapper, { scrollWidth: 2000, clientWidth: 1000, scrollLeft: 500 })
    wrapper.unmount()

    expect(recallStripScroll('')).toBeUndefined()
    expect(rememberStripScroll('', { left: 1 })).toBeUndefined()
  })

  // 2026-11-27: the 4px bottom bar is a real drag handle (users drag it).
  // happy-dom has no layout, so the bar rect is stubbed: 100px bar (== the
  // stubbed clientWidth), thumb 25px, scrollable range 300px → 4px per px.
  it('drags the bottom thumb to scroll the track', async () => {
    const wrapper = mountCarousel()
    const track = await stubScroll(wrapper, { scrollWidth: 400, clientWidth: 100 })
    const bar = wrapper.get('.category-carousel__bar')
    bar.element.getBoundingClientRect = () => ({
      left: 0,
      right: 100,
      top: 0,
      bottom: 4,
      width: 100,
      height: 4,
      x: 0,
      y: 0,
    })

    // thumb = 25px, usable = 75px; pointer at 50 → thumb start 37.5 → 37.5×4 = 150
    await bar.trigger('pointerdown', { clientX: 50, pointerId: 1, button: 0 })
    expect(track.scrollLeft).toBe(150)

    await bar.trigger('pointermove', { clientX: 100, pointerId: 1 })
    expect(track.scrollLeft).toBe(300)

    await bar.trigger('pointermove', { clientX: 0, pointerId: 1 })
    expect(track.scrollLeft).toBe(0)

    // After pointerup further moves are ignored.
    await bar.trigger('pointerup', { pointerId: 1 })
    await bar.trigger('pointermove', { clientX: 100, pointerId: 1 })
    expect(track.scrollLeft).toBe(0)
  })

  // Regression (2026-11-27 "thumb thrashing"): while a drag is in progress the
  // scroll events fired by our own writes must not move the thumb — the pointer
  // is the only writer. A stray restore/sync used to yank scrollLeft back to 0.
  it('freezes the thumb position while dragging, re-aligns on pointerup', async () => {
    const wrapper = mountCarousel()
    const track = await stubScroll(wrapper, { scrollWidth: 400, clientWidth: 100 })
    const bar = wrapper.get('.category-carousel__bar')
    bar.element.getBoundingClientRect = () => ({
      left: 0,
      right: 100,
      top: 0,
      bottom: 4,
      width: 100,
      height: 4,
      x: 0,
      y: 0,
    })

    await bar.trigger('pointerdown', { clientX: 50, pointerId: 1, button: 0 })
    const dragged = wrapper.get('.category-carousel__thumb').attributes('style')
    expect(dragged).toContain('left: 38px')

    // Simulate a scroll event (e.g. an external write) mid-drag.
    track.scrollLeft = 300
    await wrapper.get('.category-carousel__track').trigger('scroll')
    await nextFrame()
    expect(wrapper.get('.category-carousel__thumb').attributes('style')).toBe(dragged)

    // Pointerup re-aligns the thumb with the real scrollLeft.
    await bar.trigger('pointerup', { pointerId: 1 })
    await nextFrame()
    expect(wrapper.get('.category-carousel__thumb').attributes('style')).toContain('left: 75px')
  })
})
