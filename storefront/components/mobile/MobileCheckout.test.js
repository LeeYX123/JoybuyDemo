import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import MobileCheckout from './MobileCheckout.vue'

// Mobile checkout (docs/20 §4): presentational component fed the resolved
// checkout state from pages/checkout/index.vue. The address form mirrors the
// desktop showNewForm logic (fresh account -> open by default). Tests assert
// against the English dictionary (the locale stub defaults en).
const address = {
  public_id: 'addr-1',
  full_name: 'Funnel Buyer',
  line1: '10 Downing Street',
  city: 'London',
  postcode: 'SW1A 1AA',
  is_serviceable: true,
}
const quoteItems = [
  {
    offer_public_id: 'offer-1',
    title: 'Ceramic mug 350ml',
    quantity: 2,
    line: '£25.80',
    image: '',
  },
]

function mountCheckout(extraProps = {}) {
  return mount(MobileCheckout, {
    props: {
      step: 'address',
      addressList: [],
      showNewForm: true,
      selectedAddressId: '',
      newAddress: { full_name: '', line1: '', phone: '' },
      error: '',
      submitting: false,
      paymentMethod: 'balance',
      paymentMethods: [
        { value: 'balance', label: 'Balance payment', note: 'Balance: £2.00' },
        { value: 'card', label: 'Credit/Debit Card', note: '' },
      ],
      selectedAddress: null,
      quoteItems,
      subtotalText: '£25.80',
      shippingText: 'Free',
      totalText: '£25.80',
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

describe('MobileCheckout', () => {
  it('opens the address form for a new account and emits field/save events', async () => {
    const wrapper = mountCheckout()

    // Fresh account (empty address list): the 3-field form is open by
    // default — same behaviour the desktop/e2e rely on.
    const form = wrapper.find('.m-checkout__form')
    expect(form.exists()).toBe(true)
    const inputs = form.findAll('input')
    expect(inputs).toHaveLength(3)
    expect(inputs[0].attributes('placeholder')).toBe('First name and surname')
    expect(inputs[1].attributes('placeholder')).toBe('Address')
    expect(inputs[2].attributes('placeholder')).toBe('Phone number')

    // Typing emits field-level updates for the page's newAddress ref.
    await inputs[0].setValue('Funnel Buyer')
    expect(wrapper.emitted()['update-address-field']).toEqual([['full_name', 'Funnel Buyer']])

    // Bottom bar Save triggers the page save handler (saveAddress vs
    // useSelectedAddress decided by the page).
    await wrapper.find('.m-checkout__pay').trigger('click')
    expect(wrapper.emitted()['save-address']).toHaveLength(1)
  })

  it('renders the payment step with items, methods, totals and the Pay now bar', async () => {
    const wrapper = mountCheckout({
      step: 'payment',
      showNewForm: false,
      selectedAddress: address,
    })

    // Address card with the change (›) control back to the address step.
    expect(wrapper.find('.m-checkout__addr-name').text()).toBe('Funnel Buyer')
    expect(wrapper.find('.m-checkout__addr-text').text()).toContain('10 Downing Street')
    await wrapper.find('.m-checkout__change').trigger('click')
    expect(wrapper.emitted()['change-step']).toEqual([['address']])

    // Item rows: title × qty + 48px image box (placeholder when no image).
    const items = wrapper.findAll('.m-checkout__item')
    expect(items).toHaveLength(1)
    expect(items[0].find('.m-checkout__item-title').text()).toBe('Ceramic mug 350ml × 2')
    expect(items[0].find('.m-checkout__item-price').text()).toBe('£25.80')
    expect(wrapper.find('.m-checkout__item-imgbox').exists()).toBe(true)

    // Payment methods: rows from the desktop paymentMethods data.
    const methods = wrapper.findAll('.m-checkout__method')
    expect(methods).toHaveLength(2)
    expect(methods[0].text()).toContain('Balance: £2.00')
    await methods[1].find('input').setValue(true)
    expect(wrapper.emitted()['select-payment']).toEqual([['card']])

    // Summary: subtotal / delivery fee / order total.
    const totals = wrapper.findAll('.m-checkout__totals > div')
    expect(totals).toHaveLength(3)
    expect(totals[0].text()).toContain('£25.80')
    expect(totals[1].text()).toContain('Free')
    expect(totals[2].text()).toContain('£25.80')

    // Bottom bar: total + Pay now; submitting state swaps the label and
    // disables the button.
    expect(wrapper.find('.m-checkout__bar-total').text()).toBe('£25.80')
    expect(wrapper.find('.m-checkout__pay').text()).toBe('Pay now')
    await wrapper.find('.m-checkout__pay').trigger('click')
    expect(wrapper.emitted()['pay-now']).toHaveLength(1)
  })

  it('disables Pay now while submitting and shows the error alert', () => {
    const wrapper = mountCheckout({
      step: 'payment',
      showNewForm: false,
      submitting: true,
      error: 'Payment is not available in your region.',
    })

    expect(wrapper.find('.m-checkout__error').attributes('role')).toBe('alert')
    expect(wrapper.find('.m-checkout__error').text()).toContain('not available')
    expect(wrapper.find('.m-checkout__pay').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.m-checkout__pay').text()).toBe('Paying…')
  })
})
