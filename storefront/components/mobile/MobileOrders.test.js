import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import MobileOrders from './MobileOrders.vue'
import MobilePageHeader from './MobilePageHeader.vue'

// Mobile order list (docs/20 §5.1): tab row + order cards (status badge,
// first item image, number/date/total, view-details link). The page feeds
// resolved rows; tests assert against the English dictionary (the locale
// stub defaults en).
const tabs = [
  { key: 'all', label: 'All' },
  { key: 'to_ship', label: 'To ship' },
  { key: 'shipped', label: 'Shipped' },
  { key: 'completed', label: 'Completed' },
]

const orders = [
  {
    publicId: 'abc12345-6789',
    number: 'ABC12345',
    date: '2026-11-25 10:00',
    statusLabel: 'Pending payment',
    statusClass: 'pending',
    total: '£25.80',
    image: '/images/mug.jpg',
    title: 'Ceramic mug 350ml',
  },
  {
    publicId: 'def87654-3210',
    number: 'DEF87654',
    date: '2026-11-24 09:00',
    statusLabel: 'To receive',
    statusClass: 'shipped',
    total: '£8.50',
    image: '',
    title: 'Linen cushion cover',
  },
]

function mountOrders(extraProps = {}) {
  return mount(MobileOrders, {
    props: {
      signedIn: true,
      loading: false,
      tabs,
      activeTab: 'all',
      orders,
      ...extraProps,
    },
    global: {
      components: { MobilePageHeader },
      stubs: {
        NuxtLink: { template: '<a><slot /></a>' },
      },
    },
  })
}

describe('MobileOrders', () => {
  it('renders the tab row and order cards with badge/image/total/details', async () => {
    const wrapper = mountOrders()

    // Header: "My orders" via MobilePageHeader.
    expect(wrapper.find('.m-page-head__title').text()).toBe('My orders')

    // Tab row: labels only (2026-11-28 状态 tab 去数量), selected tab gets
    // the active underline class.
    const tabButtons = wrapper.findAll('.m-orders__tab')
    expect(tabButtons).toHaveLength(4)
    expect(tabButtons[0].classes()).toContain('m-orders__tab--active')
    expect(tabButtons[1].text()).toContain('To ship')
    expect(wrapper.find('.m-orders__tab-count').exists()).toBe(false)

    // Cards: badge + number + image + total + detail link.
    const cards = wrapper.findAll('.m-orders__card')
    expect(cards).toHaveLength(2)
    expect(cards[0].find('.m-orders__badge').text()).toBe('Pending payment')
    expect(cards[0].find('.m-orders__number').text()).toBe('#ABC12345')
    expect(cards[0].find('.m-orders__img').attributes('src')).toBe('/images/mug.jpg')
    expect(cards[0].find('.m-orders__total').text()).toContain('£25.80')
    await tabButtons[1].trigger('click')
    expect(wrapper.emitted().tab[0]).toEqual(['to_ship'])
    expect(cards[0].find('.m-orders__detail').attributes('to')).toBe(
      '/account/orders/abc12345-6789',
    )

    // Second card has no image -> placeholder box.
    expect(wrapper.findAll('.m-orders__img--placeholder')).toHaveLength(1)
  })

  it('shows the empty state and emits the tab click', () => {
    const wrapper = mountOrders({ orders: [], tabs: tabs.slice(0, 1) })

    const empty = wrapper.find('.m-orders__empty')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('No orders in this tab.')
    expect(wrapper.find('.m-orders__list').exists()).toBe(false)
  })

  it('shows the sign-in prompt when signed out', () => {
    const wrapper = mountOrders({ signedIn: false })

    const empty = wrapper.find('.m-orders__empty')
    expect(empty.text()).toContain('Sign in to see your orders.')
    expect(wrapper.find('a.m-orders__signin').attributes('to')).toBe('/auth/login')
    expect(wrapper.find('.m-orders__tabs').exists()).toBe(false)
  })
})
