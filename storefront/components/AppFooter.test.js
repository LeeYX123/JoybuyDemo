import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AppFooter from './AppFooter.vue'

describe('AppFooter', () => {
  it('renders every link column with a heading', () => {
    const wrapper = mount(AppFooter)
    const titles = wrapper.findAll('.footer-column__title').map((node) => node.text())
    expect(titles).toEqual(['Customer service', 'About Joybuy', 'Payment & policies'])
    expect(wrapper.findAll('.footer-column__link').length).toBeGreaterThanOrEqual(9)
  })

  it('states the demo nature and local-asset policy in the legal row', () => {
    const wrapper = mount(AppFooter)
    const legal = wrapper.get('.site-footer__legal').text()
    expect(legal).toContain('Demo project')
    expect(legal).toContain('All assets served locally')
  })
})
