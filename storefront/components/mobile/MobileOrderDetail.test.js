import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import MobileOrderDetail from './MobileOrderDetail.vue'
import MobilePageHeader from './MobilePageHeader.vue'

// Mobile order detail (docs/20 §5.2): status card, shipping address, item
// lines, amounts + payment method. Confirm-receipt is emitted to the page.
const order = {
  number: 'ABC12345',
  statusLabel: 'Paid',
  placedAt: '2026-11-25 10:00',
  paymentMethod: 'Card ending 4242',
  total: '£25.80',
  address: 'Smoke Buyer · 10 Downing Street, London SW1A 2AA',
  items: [
    { title: 'Ceramic mug 350ml', qty: 2, price: '£12.90', image: '/images/mug.jpg' },
    { title: 'Linen cushion cover', qty: 1, price: '£8.50', image: '' },
  ],
  showConfirm: true,
  completed: false,
}

function mountDetail(extraProps = {}) {
  return mount(MobileOrderDetail, {
    props: { loading: false, notFound: false, order, confirming: false, ...extraProps },
    global: {
      components: { MobilePageHeader },
      stubs: {
        NuxtLink: { template: '<a><slot /></a>' },
      },
    },
  })
}

describe('MobileOrderDetail', () => {
  it('renders the status card, address, item lines and emits confirm', async () => {
    const wrapper = mountDetail()

    // Status card: number + badge + meta rows (placed at / payment / total).
    expect(wrapper.find('.m-page-head__title').text()).toBe('Order')
    expect(wrapper.find('.m-odetail__number').text()).toBe('#ABC12345')
    expect(wrapper.find('.m-odetail__badge').text()).toBe('Paid')
    const meta = wrapper.find('.m-odetail__meta').text()
    expect(meta).toContain('2026-11-25 10:00')
    expect(meta).toContain('Card ending 4242')
    expect(meta).toContain('£25.80')

    // Address + item lines.
    expect(wrapper.find('.m-odetail__address').text()).toContain('10 Downing Street')
    const items = wrapper.findAll('.m-odetail__item')
    expect(items).toHaveLength(2)
    expect(items[0].find('.m-odetail__item-name').text()).toBe('Ceramic mug 350ml')
    expect(items[0].find('.m-odetail__item-qty').text()).toBe('×2')
    expect(wrapper.findAll('.m-odetail__img--placeholder')).toHaveLength(1)

    // Confirm receipt: emitted to the page handler.
    await wrapper.find('.m-odetail__confirm').trigger('click')
    expect(wrapper.emitted().confirm).toHaveLength(1)
  })

  it('hides the confirm button when the order is completed', () => {
    const wrapper = mountDetail({ order: { ...order, showConfirm: false, completed: true } })

    expect(wrapper.find('.m-odetail__confirm').exists()).toBe(false)
    expect(wrapper.find('.m-odetail__done').exists()).toBe(true)
    expect(wrapper.find('.m-odetail__done').text()).toContain('Order completed')
  })

  it('shows the not-found hint without any card', () => {
    const wrapper = mountDetail({ notFound: true })

    expect(wrapper.find('.m-odetail__hint').text()).toContain('Order not found.')
    expect(wrapper.find('.m-odetail__card').exists()).toBe(false)
  })
})
