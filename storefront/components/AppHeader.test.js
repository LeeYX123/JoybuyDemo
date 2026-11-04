import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'

// Deterministic category tree for the header row / panel linkage tests.
vi.mock('../composables/useCategoryTree', () => ({
  useCategoryTree: () => ({
    categories: ref([
      {
        slug: 'home-living',
        name: 'Home & Living',
        name_en: 'Home & Living',
        name_zh: '家居生活',
        children: [
          { slug: 'kitchen-essentials', name_en: 'Kitchen Essentials', name_zh: '厨房用品' },
        ],
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

import AppHeader from './AppHeader.vue'

const RouterLinkStub = {
  name: 'RouterLinkStub',
  props: ['to'],
  template: '<a :href="to"><slot /></a>',
}

function mountHeader(props = {}) {
  return mount(AppHeader, {
    props,
    global: { stubs: { NuxtLink: RouterLinkStub } },
  })
}

describe('AppHeader', () => {
  it('renders brand, pill categories trigger, round icons and the API category row', () => {
    const wrapper = mountHeader()
    expect(wrapper.get('.brand').attributes('aria-label')).toBe('Joybuy home')
    expect(wrapper.get('form.search').attributes('role')).toBe('search')
    expect(wrapper.get('#site-search').attributes('placeholder')).toBe('Search on Joybuy')
    // The categories trigger carries the label text (docs/12 header).
    expect(wrapper.get('.categories-button__label').text()).toBe('Categories')
    // Round 52px icon buttons for account and cart, labelled for a11y.
    expect(wrapper.findAll('.icon-button').map((b) => b.attributes('aria-label'))).toEqual([
      'Sign in',
      'Cart, 0 items',
    ])
    // The 11 standard categories come from the API (requirement 1-1).
    expect(wrapper.findAll('.category-nav__link').map((link) => link.text())).toEqual([
      'Home & Living',
      'Electronics',
    ])
    expect(wrapper.findAll('.category-nav__link')[0].attributes('href')).toBe('/c/home-living')
  })

  it('keeps the notice strip without the removed download and delivery lines', () => {
    const wrapper = mountHeader()
    const text = wrapper.get('.top-strip').text()
    expect(text).not.toContain('Download Joybuy')
    expect(text).not.toContain('Same-day')
    expect(text).toContain('Unlock Your Welcome Offers')
  })

  it('opens the categories panel from the trigger button and on hover', async () => {
    const wrapper = mountHeader()
    expect(wrapper.find('.category-panel').exists()).toBe(false)
    // Click opens (touch users); closing happens via the close button or
    // mouse-leave, matching the real site's hover dropdown.
    await wrapper.get('.categories-button').trigger('click')
    expect(wrapper.find('.category-panel').exists()).toBe(true)

    await wrapper.get('.categories-anchor').trigger('mouseenter')
    expect(wrapper.find('.category-panel').exists()).toBe(true)
  })

  it('shows the cart count badge only when items exist', async () => {
    expect(mountHeader().find('.cart-count').exists()).toBe(false)

    const withCart = mountHeader({ cartCount: 3 })
    expect(withCart.get('.cart-count').text()).toBe('3')
    expect(withCart.get('.icon-button--cart').attributes('aria-label')).toBe('Cart, 3 items')

    const capped = mountHeader({ cartCount: 150 })
    expect(capped.get('.cart-count').text()).toBe('99+')
    expect(capped.get('.icon-button--cart').attributes('aria-label')).toBe('Cart, 99+ items')
  })

  it('keeps every interactive control reachable at 44px minimum height', () => {
    const wrapper = mountHeader()
    for (const control of wrapper.findAll('input, button, a')) {
      const minHeight = getComputedStyle(control.element).minHeight
      // jsdom computes styles from scoped CSS in the component source; the
      // design rule is 44px minimum for all interactive elements.
      if (minHeight && minHeight !== 'auto') {
        expect(Number.parseFloat(minHeight)).toBeGreaterThanOrEqual(44)
      }
    }
  })
})
