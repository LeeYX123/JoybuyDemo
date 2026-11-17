import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import ChannelHeroCarousel from '../components/ChannelHeroCarousel.vue'

const RouterLinkStub = {
  name: 'RouterLinkStub',
  props: ['to'],
  template: '<a :href="to"><slot /></a>',
}

function mountCarousel(items) {
  return mount(ChannelHeroCarousel, {
    props: { items, fallbackTitle: 'Home & Living' },
    global: { stubs: { NuxtLink: RouterLinkStub } },
  })
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('ChannelHeroCarousel', () => {
  it('falls back to the gradient placeholder when there is no banner', () => {
    const wrapper = mountCarousel([])
    expect(wrapper.find('.channel-hero__name').text()).toBe('Home & Living')
    expect(wrapper.findAll('.channel-hero__img')).toHaveLength(0)
    expect(wrapper.find('.channel-hero__arrow').exists()).toBe(false)
  })

  it('renders a single banner statically', () => {
    const wrapper = mountCarousel([{ id: 'a', image_url: '/media/a.png', href: '/c/a' }])
    expect(wrapper.get('.channel-hero__link').attributes('href')).toBe('/c/a')
    expect(wrapper.find('.channel-hero__arrow').exists()).toBe(false)
    expect(wrapper.find('.channel-hero__dot').exists()).toBe(false)
  })

  it('switches slides with arrows, dots and the 5s autoplay', async () => {
    const wrapper = mountCarousel([
      { id: 'a', image_url: '/media/a.png', href: '/c/a' },
      { id: 'b', image_url: '/media/b.png', href: '' },
      { id: 'c', image_url: '/media/c.png', href: '' },
    ])
    const track = wrapper.get('.channel-hero__track')

    await wrapper.findAll('.channel-hero__arrow')[1].trigger('click')
    expect(track.attributes('style')).toContain('translateX(-100%)')

    // 5 秒后自动下一张（回到第 3 张），再下一张回到第 1 张。
    vi.advanceTimersByTime(5000)
    await wrapper.vm.$nextTick()
    expect(track.attributes('style')).toContain('translateX(-200%)')
    vi.advanceTimersByTime(5000)
    await wrapper.vm.$nextTick()
    expect(track.attributes('style')).toContain('translateX(-0%)')

    // hover 暂停：鼠标进入后 5 秒不再前进。
    await wrapper.get('.channel-hero').trigger('mouseenter')
    vi.advanceTimersByTime(5000)
    await wrapper.vm.$nextTick()
    expect(track.attributes('style')).toContain('translateX(-0%)')
    wrapper.unmount()
  })
})
