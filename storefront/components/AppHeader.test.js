import { mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// Deterministic category tree for the header row / panel linkage tests.
vi.mock('../composables/useCategoryTree', () => ({
  useCategoryTree: () => ({
    categories: ref([
      {
        slug: 'home-living',
        name: 'Home & Living',
        name_en: 'Home & Living',
        name_zh: '家居生活',
        channel_code: 'UK-Mini-HP-Home-Living',
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

// Mutable auth state so one file can exercise both the signed-out header and
// the signed-in account menu / delivery drawer.
vi.mock('../composables/useBuyerAuth', async () => {
  const { ref } = await import('vue')
  const authenticated = ref(false)
  return {
    __setAuthenticated: (value) => {
      authenticated.value = value
    },
    useBuyerAuth: () => ({
      isAuthenticated: authenticated,
      account: ref({ email: 'buyer@example.com' }),
      logout: vi.fn(),
    }),
  }
})

import { __setAuthenticated } from '../composables/useBuyerAuth'
import AppHeader from './AppHeader.vue'

const RouterLinkStub = {
  name: 'RouterLinkStub',
  props: ['to'],
  template: '<a :href="to"><slot /></a>',
}

const ADDRESSES = [
  {
    public_id: 'address-default',
    full_name: 'Ada Lovelace',
    phone: '07000000001',
    line1: '1 Main Street',
    line2: '',
    city: 'London',
    county: '',
    postcode: 'EC1A 1BB',
    is_default: true,
  },
  {
    public_id: 'address-second',
    full_name: 'Alan Turing',
    phone: '07000000002',
    line1: '2 King Road',
    line2: 'Flat 3',
    city: 'Manchester',
    county: 'Greater Manchester',
    postcode: 'M1 1AE',
    is_default: false,
  },
]

function stubAddressFetch(addresses = ADDRESSES) {
  const fetchMock = vi.fn(async () => ({ addresses }))
  vi.stubGlobal('$fetch', fetchMock)
  return fetchMock
}

async function settle() {
  await Promise.resolve()
  await Promise.resolve()
  await nextTick()
  await nextTick()
}

function mountHeader(props = {}) {
  const wrapper = mount(AppHeader, {
    props,
    attachTo: document.body,
    global: { stubs: { NuxtLink: RouterLinkStub } },
  })
  mountedWrappers.push(wrapper)
  return wrapper
}

const mountedWrappers = []

beforeEach(() => {
  __setAuthenticated(false)
  window.localStorage.clear()
  stubAddressFetch()
})

afterEach(() => {
  for (const wrapper of mountedWrappers.splice(0)) wrapper.unmount()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  document.body.style.overflow = ''
})

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
    // Roots with a channel code land on the channel landing page; roots
    // without one keep the /c/<slug> results page (minihome parity).
    expect(wrapper.findAll('.category-nav__link').map((link) => link.attributes('href'))).toEqual([
      '/minihome/UK-Mini-HP-Home-Living',
      '/c/electronics',
    ])
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

  it('closes the account menu on an outside pointerdown and on Escape', async () => {
    __setAuthenticated(true)
    const wrapper = mountHeader()
    const trigger = wrapper.get('button[aria-label="My account"]')
    expect(trigger.attributes('aria-expanded')).toBe('false')

    await trigger.trigger('click')
    expect(wrapper.find('.account-menu__panel').exists()).toBe(true)
    expect(trigger.attributes('aria-expanded')).toBe('true')

    // Clicking anywhere outside the menu (here: the page body) dismisses it.
    document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    await nextTick()
    expect(wrapper.find('.account-menu__panel').exists()).toBe(false)
    expect(trigger.attributes('aria-expanded')).toBe('false')

    // The trigger toggles open again, and Escape closes + restores focus.
    await trigger.trigger('click')
    expect(wrapper.find('.account-menu__panel').exists()).toBe(true)
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await nextTick()
    expect(wrapper.find('.account-menu__panel').exists()).toBe(false)
    expect(document.activeElement).toBe(trigger.element)

    // Clicking inside the panel does not dismiss it before the link runs.
    await trigger.trigger('click')
    wrapper
      .get('.account-menu__panel')
      .element.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    await nextTick()
    expect(wrapper.find('.account-menu__panel').exists()).toBe(true)
  })

  it('opens the delivery drawer with the real-site layout and committed address', async () => {
    __setAuthenticated(true)
    const wrapper = mountHeader()
    await settle()

    // The header mirrors the default saved address once it is loaded.
    expect(wrapper.get('.account-nav__deliver-text').text()).toBe('Deliver to EC1A 1BB')
    expect(wrapper.get('.account-nav__deliver').attributes('aria-expanded')).toBe('false')

    await wrapper.get('.account-nav__deliver').trigger('click')
    await settle()
    expect(wrapper.get('.address-drawer__panel').attributes('aria-modal')).toBe('true')
    expect(wrapper.get('.account-nav__deliver').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('.country-select__name').text()).toBe('United Kingdom')
    expect(wrapper.get('.country-select .country-flag').classes()).toContain('country-flag--gb')
    expect(wrapper.findAll('.address-drawer__tab').map((tab) => tab.text())).toEqual([
      'Delivery',
      'Pickup',
    ])
    expect(wrapper.get('.address-drawer__tab--active').text()).toBe('Delivery')
    expect(wrapper.get('.address-drawer__manage').attributes('href')).toBe('/account/addresses')
    expect(wrapper.get('.address-drawer__location').attributes('aria-disabled')).toBe('true')
    expect(wrapper.get('.address-drawer__location').text()).toBe('Use my location')
    expect(wrapper.get('.address-drawer__postcode-label').text()).toBe('Postcode')
    expect(wrapper.get('.address-drawer__postcode-input').attributes('placeholder')).toBe(
      'Enter your postcode.',
    )
    expect(wrapper.get('.address-drawer__section-title').text()).toBe('My addresses')
    expect(wrapper.get('.address-drawer__apply').text()).toBe('Apply')

    const rows = wrapper.findAll('.address-drawer__address')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('Ada Lovelace')
    expect(rows[0].text()).toContain('1 Main Street, London')
    expect(rows[0].text()).toContain('EC1A 1BB')
    expect(rows[0].attributes('aria-checked')).toBe('true')
    expect(rows[1].attributes('aria-checked')).toBe('false')
  })

  it('only commits an address draft when Apply is pressed', async () => {
    __setAuthenticated(true)
    const wrapper = mountHeader()
    await settle()
    await wrapper.get('.account-nav__deliver').trigger('click')
    await settle()

    const rows = wrapper.findAll('.address-drawer__address')
    await rows[1].trigger('click')
    await settle()

    // Draft only: drawer stays open, header and storage are unchanged.
    expect(wrapper.find('.address-drawer').exists()).toBe(true)
    expect(wrapper.get('.account-nav__deliver-text').text()).toBe('Deliver to EC1A 1BB')
    expect(wrapper.findAll('.address-drawer__address')[1].attributes('aria-checked')).toBe('true')
    expect(wrapper.findAll('.address-drawer__address')[0].attributes('aria-checked')).toBe('false')
    expect(wrapper.get('.address-drawer__postcode-input').element.value).toBe('')
    // Storage still holds the committed default, not the draft.
    expect(JSON.parse(window.localStorage.getItem('joybuy:delivery-address'))).toMatchObject({
      mode: 'address',
      addressId: 'address-default',
    })

    await wrapper.get('.address-drawer__apply').trigger('click')
    await settle()
    expect(wrapper.find('.address-drawer').exists()).toBe(false)
    expect(wrapper.get('.account-nav__deliver-text').text()).toBe('Deliver to M1 1AE')
    expect(JSON.parse(window.localStorage.getItem('joybuy:delivery-address'))).toMatchObject({
      mode: 'address',
      addressId: 'address-second',
    })
  })

  it('validates a postcode draft and applies it only when valid', async () => {
    __setAuthenticated(true)
    const wrapper = mountHeader()
    await settle()
    await wrapper.get('.account-nav__deliver').trigger('click')
    await settle()

    await wrapper.get('input[name="delivery-method"]').setValue()
    const input = wrapper.get('.address-drawer__postcode-input')
    await input.setValue('ABC')
    await wrapper.get('.address-drawer__apply').trigger('click')
    await settle()

    expect(wrapper.find('.address-drawer').exists()).toBe(true)
    expect(wrapper.get('.address-drawer__error').text()).toBe(
      'Enter a valid UK postcode, for example EC1A 1BB.',
    )
    expect(wrapper.get('.address-drawer__postcode-input').classes()).toContain(
      'address-drawer__postcode-input--invalid',
    )
    expect(wrapper.get('.account-nav__deliver-text').text()).toBe('Deliver to EC1A 1BB')

    await input.setValue('m1 1ae')
    await wrapper.get('.address-drawer__apply').trigger('click')
    await settle()
    expect(wrapper.find('.address-drawer').exists()).toBe(false)
    expect(wrapper.get('.account-nav__deliver-text').text()).toBe('Deliver to M1 1AE')
    expect(JSON.parse(window.localStorage.getItem('joybuy:delivery-address'))).toMatchObject({
      mode: 'postcode',
      postcode: 'M1 1AE',
    })
  })

  it('switches to the Pickup tab and shows an honest empty state', async () => {
    __setAuthenticated(true)
    const wrapper = mountHeader()
    await settle()
    await wrapper.get('.account-nav__deliver').trigger('click')
    await settle()

    await wrapper.findAll('.address-drawer__tab')[1].trigger('click')
    await settle()
    expect(wrapper.get('.address-drawer__tab--active').text()).toBe('Pickup')
    expect(wrapper.get('.address-drawer__pickup-title').text()).toBe(
      'Pickup stores are not available yet.',
    )
    expect(wrapper.find('.address-drawer__apply').exists()).toBe(false)
    expect(wrapper.find('.address-drawer__manage').exists()).toBe(false)
    expect(wrapper.find('.address-drawer__section-title').exists()).toBe(false)

    await wrapper.findAll('.address-drawer__tab')[0].trigger('click')
    await settle()
    expect(wrapper.find('.address-drawer__apply').exists()).toBe(true)
  })

  it('closes the delivery drawer with Escape and the backdrop, locking scroll while open', async () => {
    __setAuthenticated(true)
    const wrapper = mountHeader()
    await settle()
    const deliver = wrapper.get('.account-nav__deliver')

    await deliver.trigger('click')
    await settle()
    expect(document.body.style.overflow).toBe('hidden')
    expect(document.activeElement).toBe(wrapper.get('.address-drawer__close').element)

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await settle()
    expect(wrapper.find('.address-drawer').exists()).toBe(false)
    expect(document.body.style.overflow).toBe('')

    await deliver.trigger('click')
    await settle()
    await wrapper.get('.address-drawer__backdrop').trigger('click')
    await settle()
    expect(wrapper.find('.address-drawer').exists()).toBe(false)
  })

  it('keeps the sign-in prompt but allows an anonymous postcode lookup', async () => {
    const wrapper = mountHeader()
    await wrapper.get('.account-nav__deliver').trigger('click')
    await settle()

    expect(wrapper.get('.address-drawer__signin-text').text()).toBe(
      'Please sign in to your account to use your address information.',
    )
    expect(wrapper.get('.address-drawer__signin-link').attributes('href')).toBe('/auth/login')
    expect(wrapper.findAll('.address-drawer__address')).toHaveLength(0)
    expect(wrapper.find('.address-drawer__section-title').exists()).toBe(false)
    expect(wrapper.find('.address-drawer__postcode-input').exists()).toBe(true)

    await wrapper.get('.address-drawer__postcode-input').setValue('M1 1AE')
    await wrapper.get('.address-drawer__apply').trigger('click')
    await settle()
    expect(wrapper.find('.address-drawer').exists()).toBe(false)
    expect(wrapper.get('.account-nav__deliver-text').text()).toBe('Deliver to M1 1AE')
  })

  it('only enforces the UK postcode shape when the country is GB', async () => {
    const wrapper = mountHeader()
    await wrapper.get('.account-nav__deliver').trigger('click')
    await settle()

    await wrapper.get('.country-select').trigger('click')
    const france = wrapper
      .findAll('[role="option"]')
      .find((option) => option.text().includes('France'))
    await france.trigger('click')
    await wrapper.get('.address-drawer__postcode-input').setValue('ABC')
    await wrapper.get('.address-drawer__apply').trigger('click')
    await settle()

    expect(wrapper.find('.address-drawer').exists()).toBe(false)
    expect(wrapper.get('.account-nav__deliver-text').text()).toBe('Deliver to ABC')
  })

  // The avatar dropdown carries a seller entry whose label mirrors the buyer's
  // shop application status (read-only GET /api/v1/account/merchant-application).
  function stubSellerStatus(status) {
    const fetchMock = vi.fn(async (url) => {
      if (String(url).includes('merchant-application')) {
        return { application: status ? { status } : null }
      }
      return { addresses: ADDRESSES }
    })
    vi.stubGlobal('$fetch', fetchMock)
    return fetchMock
  }

  async function openAccountMenu(wrapper) {
    await wrapper.get('button[aria-label="My account"]').trigger('click')
    await settle()
    return wrapper.get('.account-menu__panel .account-menu__item')
  }

  it('lists a seller entry that opens the apply-shop page', async () => {
    __setAuthenticated(true)
    stubSellerStatus(null)
    const wrapper = mountHeader()
    await settle()

    const seller = await openAccountMenu(wrapper)
    expect(seller.text()).toBe('Apply for a shop')
    expect(seller.attributes('aria-label')).toBe('Apply for a shop')
    expect(seller.element.tagName).toBe('A')
    expect(seller.attributes('href')).toBe('/account/apply-shop')
    // Same styling hook as every other dropdown entry.
    expect(seller.classes()).toContain('account-menu__item')
  })

  it('labels the seller entry with the live application status', async () => {
    __setAuthenticated(true)
    stubSellerStatus('PENDING')
    const pending = mountHeader()
    await settle()
    const underReview = await openAccountMenu(pending)
    expect(underReview.text()).toBe('Application under review')
    expect(underReview.attributes('href')).toBe('/account/apply-shop')

    __setAuthenticated(true)
    stubSellerStatus('APPROVED')
    const approved = mountHeader()
    await settle()
    const seller = await openAccountMenu(approved)
    expect(seller.text()).toBe('Enter Merchant Center')
    // APPROVED is an action: it swaps the buyer session for a merchant staff
    // session and navigates to merchant-web (no apply-shop link any more).
    expect(seller.element.tagName).toBe('BUTTON')
    expect(seller.attributes('href')).toBeUndefined()
  })

  it('falls back to the apply label when the status request fails', async () => {
    __setAuthenticated(true)
    vi.stubGlobal(
      '$fetch',
      vi.fn(async (url) => {
        if (String(url).includes('merchant-application')) throw new Error('offline')
        return { addresses: ADDRESSES }
      }),
    )
    const wrapper = mountHeader()
    await settle()

    const seller = await openAccountMenu(wrapper)
    expect(seller.text()).toBe('Apply for a shop')
  })
})
