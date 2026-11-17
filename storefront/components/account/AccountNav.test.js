import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../composables/useBuyerAuth', async () => {
  const { ref: createRef } = await import('vue')
  const authenticated = createRef(false)
  return {
    __setAuthenticated: (value) => {
      authenticated.value = value
    },
    useBuyerAuth: () => ({
      isAuthenticated: authenticated,
      account: createRef(null),
      logout: vi.fn(),
    }),
  }
})

import { __setAuthenticated } from '../../composables/useBuyerAuth'
import AccountNav from './AccountNav.vue'

const RouterLinkStub = {
  name: 'RouterLinkStub',
  props: ['to'],
  template: '<a :href="to"><slot /></a>',
}

function stubFetch(status) {
  vi.stubGlobal(
    '$fetch',
    vi.fn(async (url) => {
      if (String(url).includes('merchant-application')) {
        return { application: status ? { status } : null }
      }
      if (String(url).includes('buyer/session')) return { csrf_token: 'csrf-token' }
      if (String(url).includes('merchant-console-session')) {
        return { url: 'http://localhost:5174/' }
      }
      return {}
    }),
  )
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
  stubFetch(null)
})

afterEach(() => {
  for (const wrapper of wrapped.splice(0)) wrapper.unmount()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('AccountNav merchant entry', () => {
  it('keeps the four base modules and adds the seller entry', async () => {
    const wrapper = await mountNav()
    wrapped.push(wrapper)
    const items = wrapper.findAll('.account-nav__item')
    expect(items.map((item) => item.text())).toEqual([
      'My orders',
      'After-sales',
      'Reviews and Q&A',
      'Addresses',
      'Apply for a shop',
    ])
  })

  it('links to apply-shop when there is no application', async () => {
    const wrapper = await mountNav()
    wrapped.push(wrapper)
    const seller = wrapper.findAll('.account-nav__item')[4]
    expect(seller.element.tagName).toBe('A')
    expect(seller.attributes('href')).toBe('/account/apply-shop')
    expect(seller.text()).toBe('Apply for a shop')
  })

  it('links to apply-shop and says under review while PENDING', async () => {
    stubFetch('PENDING')
    const wrapper = await mountNav()
    wrapped.push(wrapper)
    const seller = wrapper.findAll('.account-nav__item')[4]
    expect(seller.element.tagName).toBe('A')
    expect(seller.attributes('href')).toBe('/account/apply-shop')
    expect(seller.text()).toBe('Application under review')
  })

  it('returns to the apply entry after REJECTED', async () => {
    stubFetch('REJECTED')
    const wrapper = await mountNav()
    wrapped.push(wrapper)
    const seller = wrapper.findAll('.account-nav__item')[4]
    expect(seller.element.tagName).toBe('A')
    expect(seller.text()).toBe('Apply for a shop')
  })

  it('becomes a Merchant Center action when APPROVED', async () => {
    stubFetch('APPROVED')
    const wrapper = await mountNav()
    wrapped.push(wrapper)
    const seller = wrapper.findAll('.account-nav__item')[4]
    expect(seller.element.tagName).toBe('BUTTON')
    expect(seller.attributes('href')).toBeUndefined()
    expect(seller.text()).toBe('Enter Merchant Center')
  })
})
