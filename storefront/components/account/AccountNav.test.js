import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// The seller entry status now comes from the shared buyer session payload
// (requirement 12.2): useMerchantEntry derives it from
// useBuyerAuth().merchantApplicationStatus instead of a dedicated fetch.
vi.mock('../../composables/useBuyerAuth', async () => {
  const { ref: createRef } = await import('vue')
  const authenticated = createRef(false)
  const applicationStatus = createRef(null)
  return {
    __setAuthenticated: (value) => {
      authenticated.value = value
    },
    __setApplicationStatus: (value) => {
      applicationStatus.value = value
    },
    useBuyerAuth: () => ({
      isAuthenticated: authenticated,
      account: createRef(null),
      merchantApplicationStatus: applicationStatus,
      logout: vi.fn(),
      refresh: vi.fn(async () => {}),
    }),
  }
})

import { __setApplicationStatus, __setAuthenticated } from '../../composables/useBuyerAuth'
import AccountNav from './AccountNav.vue'

const RouterLinkStub = {
  name: 'RouterLinkStub',
  props: ['to'],
  template: '<a :href="to"><slot /></a>',
}

async function settle() {
  await Promise.resolve()
  await Promise.resolve()
  await nextTick()
  await nextTick()
}

async function mountNav() {
  const wrapper = mount(AccountNav, {
    global: { stubs: { NuxtLink: RouterLinkStub } },
  })
  await settle()
  return wrapper
}

const wrapped = []

beforeEach(() => {
  __setAuthenticated(true)
  __setApplicationStatus(null)
  // Console switch posts need $fetch; entry rendering itself stays offline.
  vi.stubGlobal(
    '$fetch',
    vi.fn(async (url) => {
      if (String(url).includes('buyer/session')) return { csrf_token: 'csrf-token' }
      if (String(url).includes('merchant-console-session')) {
        return { url: 'http://localhost:5174/' }
      }
      return {}
    }),
  )
})

afterEach(() => {
  for (const wrapper of wrapped.splice(0)) wrapper.unmount()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('AccountNav merchant entry', () => {
  it('renders the real-site module rail plus the seller entry', async () => {
    const wrapper = await mountNav()
    wrapped.push(wrapper)
    const items = wrapper.findAll('.account-nav__item')
    expect(items.map((item) => item.text())).toEqual([
      'My account',
      'My orders',
      'After-sales',
      'Reviews and Q&A',
      'Favourites',
      'Joybuy balance',
      'Points',
      'Coupons',
      'Addresses',
      'Apply for a shop',
    ])
  })

  it('links the wishlist entry to our favourites page under our own naming', async () => {
    const wrapper = await mountNav()
    wrapped.push(wrapper)
    // 我的收藏 (not the real site's 心愿单 wording) — see CONTEXT.md.
    const favourites = wrapper.findAll('.account-nav__item')[4]
    expect(favourites.attributes('href')).toBe('/account/favourites')
    expect(favourites.text()).toBe('Favourites')
  })

  it('links to apply-shop when there is no application', async () => {
    const wrapper = await mountNav()
    wrapped.push(wrapper)
    const seller = wrapper.findAll('.account-nav__item')[9]
    expect(seller.element.tagName).toBe('A')
    expect(seller.attributes('href')).toBe('/account/apply-shop')
    expect(seller.text()).toBe('Apply for a shop')
  })

  it('links to apply-shop and says under review while PENDING', async () => {
    __setApplicationStatus('PENDING')
    const wrapper = await mountNav()
    wrapped.push(wrapper)
    const seller = wrapper.findAll('.account-nav__item')[9]
    expect(seller.element.tagName).toBe('A')
    expect(seller.attributes('href')).toBe('/account/apply-shop')
    expect(seller.text()).toBe('Application under review')
  })

  it('returns to the apply entry after REJECTED', async () => {
    __setApplicationStatus('REJECTED')
    const wrapper = await mountNav()
    wrapped.push(wrapper)
    const seller = wrapper.findAll('.account-nav__item')[9]
    expect(seller.element.tagName).toBe('A')
    expect(seller.text()).toBe('Apply for a shop')
  })

  it('becomes a Merchant Center action when APPROVED', async () => {
    __setApplicationStatus('APPROVED')
    const wrapper = await mountNav()
    wrapped.push(wrapper)
    const seller = wrapper.findAll('.account-nav__item')[9]
    expect(seller.element.tagName).toBe('BUTTON')
    expect(seller.attributes('href')).toBeUndefined()
    expect(seller.text()).toBe('Enter Merchant Center')
  })
})
