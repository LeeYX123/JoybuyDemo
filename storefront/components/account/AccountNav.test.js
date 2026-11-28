import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AccountNav from './AccountNav.vue'

// 2026-11-28（用户要求）：账号侧栏不再有商家入口（含 APPROVED 态的
// 「进入商家中心」按钮）；进入商家端只保留页头右上角的【切换商家端】pill。
const RouterLinkStub = {
  name: 'RouterLinkStub',
  props: ['to'],
  template: '<a :href="to"><slot /></a>',
}

function mountNav() {
  return mount(AccountNav, {
    global: { stubs: { NuxtLink: RouterLinkStub } },
  })
}

describe('AccountNav', () => {
  it('renders the real-site module rail only (no merchant entry)', () => {
    const wrapper = mountNav()
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
    ])
    expect(wrapper.find('button').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Merchant Center')
    expect(wrapper.text()).not.toContain('Apply for a shop')
  })

  it('links the wishlist entry to our favourites page under our own naming', () => {
    const wrapper = mountNav()
    // 我的收藏 (not the real site's 心愿单 wording) — see CONTEXT.md.
    const favourites = wrapper.findAll('.account-nav__item')[4]
    expect(favourites.attributes('href')).toBe('/account/favourites')
    expect(favourites.text()).toBe('Favourites')
  })

  it('keeps every sidebar link pointing at an account sub-page', () => {
    const wrapper = mountNav()
    const hrefs = wrapper.findAll('.account-nav__item').map((item) => item.attributes('href'))
    expect(hrefs).toEqual([
      '/account',
      '/account/orders',
      '/account/returns',
      '/account/reviews',
      '/account/favourites',
      '/account/balance',
      '/account/points',
      '/account/coupons',
      '/account/addresses',
    ])
  })
})
