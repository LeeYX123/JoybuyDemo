import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import MobileMessages from './MobileMessages.vue'
import MobilePageHeader from './MobilePageHeader.vue'

// Mobile messages (docs/20 §5.7): two tabs — 客服 support entry card and
// 订单 status notifications built from the recent orders at page level.
const notifications = [
  {
    key: 'order-1',
    publicId: 'abc12345-6789',
    number: 'ABC12345',
    statusLabel: 'Pending payment',
    statusClass: 'pending',
    date: '2026-11-25 10:00',
  },
]

function mountMessages(props = {}) {
  return mount(MobileMessages, {
    props: { signedIn: true, notifications, ...props },
    global: {
      components: { MobilePageHeader },
      stubs: {
        NuxtLink: { template: '<a><slot /></a>' },
      },
    },
  })
}

describe('MobileMessages', () => {
  it('defaults to the support tab with the entry card', async () => {
    const wrapper = mountMessages()

    expect(wrapper.find('.m-page-head__title').text()).toBe('Messages')

    // Two tabs, support active by default.
    const tabButtons = wrapper.findAll('.m-msg__tab')
    expect(tabButtons).toHaveLength(2)
    expect(tabButtons[0].classes()).toContain('m-msg__tab--active')
    expect(tabButtons[0].text()).toBe('Customer service')

    // Support card: description + 在线咨询 button to the customer-service page.
    expect(wrapper.find('.m-msg__desc').text()).toContain('24/7')
    expect(wrapper.find('a.m-msg__cta').attributes('to')).toBe('/help/customer-service')
    expect(wrapper.find('a.m-msg__cta').text()).toBe('Online chat')

    // Switching to the orders tab shows the notification list.
    await tabButtons[1].trigger('click')
    const rows = wrapper.findAll('.m-msg__card--row')
    expect(rows).toHaveLength(1)
    expect(rows[0].find('.m-msg__row-title').text()).toContain('#ABC12345')
    expect(rows[0].find('.m-msg__row-title').text()).toContain('Pending payment')
    expect(rows[0].find('.m-msg__row-link').attributes('to')).toBe('/account/orders/abc12345-6789')
  })

  it('shows the orders-tab empty state for a signed-in user without orders', async () => {
    const wrapper = mountMessages({ notifications: [] })

    await wrapper.findAll('.m-msg__tab')[1].trigger('click')
    expect(wrapper.find('.m-msg__empty-text').text()).toContain('No order updates yet.')
    expect(wrapper.find('.m-msg__card--row').exists()).toBe(false)
  })

  it('asks the signed-out user to sign in on the orders tab', async () => {
    const wrapper = mountMessages({ signedIn: false })

    await wrapper.findAll('.m-msg__tab')[1].trigger('click')
    expect(wrapper.find('.m-msg__empty-text').text()).toContain('Sign in to see your orders.')
    expect(wrapper.find('a.m-msg__signin').attributes('to')).toBe('/auth/login')
  })
})
