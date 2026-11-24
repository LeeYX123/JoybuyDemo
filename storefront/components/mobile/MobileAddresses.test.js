import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import MobileAddresses from './MobileAddresses.vue'
import MobilePageHeader from './MobilePageHeader.vue'

// Mobile address book (docs/20 §5.4): delivery/pickup tabs, address cards
// (default badge, copy/edit/delete) and the inline add/edit form forwarding
// field edits as `field` events (the page owns the reactive form and
// validation).
const address = {
  publicId: 'addr-1',
  fullName: 'Smoke Buyer',
  phone: '+447000000123',
  lines: '10 Downing Street, London, SW1A 2AA',
  isDefault: true,
  isServiceable: true,
  // Raw payload is spread in so edit/setDefault receive the desktop shape.
  full_name: 'Smoke Buyer',
  line1: '10 Downing Street',
  city: 'London',
  postcode: 'SW1A 2AA',
}

const form = {
  full_name: '',
  phone: '',
  line1: '',
  line2: '',
  city: '',
  county: '',
  postcode: '',
  is_default: false,
}

function mountAddresses(extraProps = {}) {
  return mount(MobileAddresses, {
    props: {
      signedIn: true,
      loading: false,
      tab: 'delivery',
      tabs: [
        { key: 'delivery', label: 'Delivery' },
        { key: 'pickup', label: 'Pickup' },
      ],
      addresses: [address],
      showForm: false,
      formTitle: 'Add a new address',
      form: { ...form },
      formError: '',
      saving: false,
      addButtonLabel: 'Add new address',
      deleteTarget: null,
      deleting: false,
      ...extraProps,
    },
    global: {
      components: { MobilePageHeader },
      stubs: {
        NuxtLink: { template: '<a><slot /></a>' },
        Teleport: { template: '<div><slot /></div>' },
      },
    },
  })
}

describe('MobileAddresses', () => {
  it('renders the tabs, address cards with the default badge and emits actions', async () => {
    const wrapper = mountAddresses()

    expect(wrapper.find('.m-page-head__title').text()).toBe('Addresses')

    // Tab row: delivery active, pickup click emits the tab key.
    const tabs = wrapper.findAll('.m-addr__tab')
    expect(tabs).toHaveLength(2)
    expect(tabs[0].classes()).toContain('m-addr__tab--active')
    await tabs[1].trigger('click')
    expect(wrapper.emitted().tab[0]).toEqual(['pickup'])

    // Card: name/phone/lines + default badge; set-default disabled for default.
    const card = wrapper.find('.m-addr__card')
    expect(card.classes()).toContain('m-addr__card--default')
    expect(card.find('.m-addr__name').text()).toBe('Smoke Buyer')
    expect(card.find('.m-addr__phone').text()).toBe('+447000000123')
    expect(card.find('.m-addr__lines').text()).toContain('10 Downing Street')
    expect(card.find('.m-addr__default-badge').exists()).toBe(true)
    expect(card.find('.m-addr__card-action').attributes('disabled')).toBeDefined()

    // Icon actions: copy / edit / delete.
    await card.find('.m-addr__icon-btn:nth-child(1)').trigger('click')
    expect(wrapper.emitted().copy[0]).toEqual([address])
    await card.find('.m-addr__icon-btn:nth-child(2)').trigger('click')
    expect(wrapper.emitted().edit[0]).toEqual([address])
    await card.find('.m-addr__icon-btn:nth-child(3)').trigger('click')
    expect(wrapper.emitted().requestDelete[0]).toEqual([address])

    // Add button emits add.
    await wrapper.find('.m-addr__add').trigger('click')
    expect(wrapper.emitted().add).toHaveLength(1)
  })

  it('renders the inline form, forwards field edits and submits via save', async () => {
    const wrapper = mountAddresses({ showForm: true, formError: 'Enter a valid UK postcode.' })

    const formEl = wrapper.find('.m-addr__form')
    expect(formEl.exists()).toBe(true)
    expect(wrapper.find('.m-addr__form-title').text()).toBe('Add a new address')
    expect(wrapper.find('.m-addr__form-error').text()).toContain('Enter a valid UK postcode.')

    // Field edits are forwarded as field events (page owns the form object).
    const nameInput = formEl.findAll('input[type="text"]')[0]
    await nameInput.setValue('Jane Buyer')
    expect(wrapper.emitted().field[0]).toEqual(['full_name', 'Jane Buyer'])

    // Submit emits save; cancel emits closeForm.
    await formEl.trigger('submit')
    expect(wrapper.emitted().save).toHaveLength(1)
    await wrapper.find('.m-addr__btn-cancel').trigger('click')
    expect(wrapper.emitted().closeForm).toHaveLength(1)
  })

  it('shows the pickup empty state on the pickup tab', () => {
    const wrapper = mountAddresses({ tab: 'pickup' })

    expect(wrapper.find('.m-addr__empty').text()).toContain('No pickup points saved.')
    expect(wrapper.find('.m-addr__list').exists()).toBe(false)
  })

  it('renders the delete confirmation and emits confirm/cancel', async () => {
    const wrapper = mountAddresses({ deleteTarget: { ...address, fullName: 'Smoke Buyer' } })

    const modal = wrapper.find('.m-addr__modal-panel')
    expect(modal.exists()).toBe(true)
    expect(modal.find('.m-addr__modal-title').text()).toBe('Delete address')
    expect(modal.find('.m-addr__modal-text').text()).toContain('Smoke Buyer')

    await modal.find('.m-addr__btn-save').trigger('click')
    expect(wrapper.emitted().confirmDelete).toHaveLength(1)
    await modal.find('.m-addr__btn-cancel').trigger('click')
    expect(wrapper.emitted().cancelDelete).toHaveLength(1)
  })

  it('shows the sign-in prompt when signed out', () => {
    const wrapper = mountAddresses({ signedIn: false })

    expect(wrapper.find('.m-addr__empty').text()).toContain('Sign in')
    expect(wrapper.find('.m-addr__tabs').exists()).toBe(false)
  })
})
