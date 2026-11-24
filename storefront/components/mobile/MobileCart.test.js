import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import MobileCart from './MobileCart.vue'

// Mobile cart (docs/20 §3): presentational component fed resolved rows from
// pages/cart/index.vue (image/spec/line already resolved by the page's
// productMeta lookup). Tests assert against the English dictionary (the
// locale stub defaults en).
const rowA = {
  public_id: 'cart-item-1',
  spu_public_id: 'spu-1',
  title: 'Ceramic mug 350ml',
  quantity: 2,
  image: '/images/mug.jpg',
  spec: 'White',
  line: '£25.80',
  isValid: true,
}
const rowB = {
  public_id: 'cart-item-2',
  spu_public_id: 'spu-2',
  title: 'Linen cushion cover',
  quantity: 1,
  image: '',
  spec: '',
  line: '£8.50',
  isValid: true,
}

function mountCart(extraProps = {}) {
  return mount(MobileCart, {
    props: {
      rows: [rowA, rowB],
      subtotalText: '£34.30',
      selectedCount: 3,
      needsAttention: false,
      ...extraProps,
    },
    global: {
      stubs: {
        NuxtLink: { template: '<a><slot /></a>' },
        MobilePageHeader: { template: '<div class="m-page-head-stub" />' },
      },
    },
  })
}

describe('MobileCart', () => {
  it('renders line cards, the red total and emits step/remove/checkout', async () => {
    const wrapper = mountCart()

    // Line cards: one per row, 72px image, two-line title, spec, red price.
    const rows = wrapper.findAll('.m-cart__row')
    expect(rows).toHaveLength(2)
    expect(wrapper.find('.m-cart__img').attributes('src')).toBe('/images/mug.jpg')
    expect(rows[0].find('.m-cart__name').text()).toBe('Ceramic mug 350ml')
    expect(rows[0].find('.m-cart__spec').text()).toBe('White')
    expect(rows[0].find('.m-cart__price').text()).toBe('£25.80')
    // Second row has no image -> placeholder box.
    expect(wrapper.findAll('.m-cart__img--placeholder')).toHaveLength(1)

    // Stepper emits the same delta semantics as the desktop page.
    const stepper = rows[0].find('.m-cart__stepper')
    expect(stepper.find('.m-cart__step-value').text()).toBe('2')
    await stepper.find('button:last-child').trigger('click')
    expect(wrapper.emitted().step).toEqual([[rowA, 1]])
    await stepper.find('button:first-child').trigger('click')
    expect(wrapper.emitted().step[1]).toEqual([rowA, -1])

    // Delete emits the row for the page removeItem handler.
    await rows[0].find('.m-cart__delete').trigger('click')
    expect(wrapper.emitted().remove).toEqual([[rowA]])

    // Summary: red 20px/700 total + checkout button with the selected count.
    expect(wrapper.find('.m-cart__total-value').text()).toBe('£34.30')
    expect(wrapper.find('.m-cart__checkout').text()).toContain('Checkout')
    expect(wrapper.find('.m-cart__checkout').text()).toContain('(3)')
    await wrapper.find('.m-cart__checkout').trigger('click')
    expect(wrapper.emitted().checkout).toHaveLength(1)
  })

  it('shows the empty-cart state with the desktop copy', () => {
    const wrapper = mountCart({ rows: [], subtotalText: '', selectedCount: 0 })

    const state = wrapper.find('.m-cart__empty')
    expect(state.exists()).toBe(true)
    expect(state.attributes('role')).toBe('status')
    expect(state.text()).toContain('No items yet')
    expect(wrapper.find('a.m-cart__shopping').attributes('to')).toBe('/')
    expect(wrapper.find('.m-cart__list').exists()).toBe(false)
    expect(wrapper.find('.m-cart__summary').exists()).toBe(false)
  })
})
