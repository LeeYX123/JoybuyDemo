import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import MobileDrawer from './MobileDrawer.vue'

// Drawer structure replicates the real-site screenshot
// (var/mjoybuy_survey_20261124/drawer_real.png): 320px panel, user area,
// bold Categories/Joybuy Home rows, then 57px item rows. 优惠券 dropped;
// 语言/设置&隐私 open dedicated pages (2026-11-24 account-page batch).
// Tests assert against the English dictionary (the locale stub defaults en).
async function openDrawer() {
  const wrapper = mount(MobileDrawer, {
    props: { open: true },
    global: {
      stubs: {
        Teleport: { template: '<div><slot /></div>' },
        NuxtLink: { template: '<a><slot /></a>' },
      },
    },
  })
  await wrapper.vm.$nextTick()
  return wrapper
}

describe('MobileDrawer', () => {
  it('renders nothing when closed', () => {
    const wrapper = mount(MobileDrawer, { props: { open: false } })
    expect(wrapper.find('.m-drawer').exists()).toBe(false)
  })

  it('shows the Categories row pointing at the category landing page', async () => {
    const wrapper = await openDrawer()
    const rows = wrapper.findAll('.m-drawer__row')
    const categoriesRow = rows.find((row) => row.text().includes('Categories'))
    expect(categoriesRow).toBeDefined()
    expect(categoriesRow.element.tagName).toBe('A')
  })

  it('shows the core item rows and drops the coupons module', async () => {
    const wrapper = await openDrawer()
    const text = wrapper.find('.m-drawer__body').text()
    for (const label of ['Orders', 'Messages', 'Wishlist', 'Addresses', 'Language', 'Settings']) {
      expect(text).toContain(label)
    }
    expect(text).not.toContain('Coupons')
  })

  it('links Language and Settings & privacy to their dedicated pages', async () => {
    const wrapper = await openDrawer()
    const targets = wrapper.findAll('a.m-drawer__row').map((row) => row.attributes('to'))
    expect(targets).toContain('/account/language')
    expect(targets).toContain('/account/settings')
  })

  it('links Messages to the mobile messages page (docs/20 §5.7)', async () => {
    const wrapper = await openDrawer()
    const targets = wrapper.findAll('a.m-drawer__row').map((row) => row.attributes('to'))
    expect(targets).toContain('/account/messages')
    expect(targets).not.toContain('/help/customer-service')
  })

  it('emits close when the backdrop is clicked', async () => {
    const wrapper = await openDrawer()
    await wrapper.find('.m-drawer__backdrop').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })
})
