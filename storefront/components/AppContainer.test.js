import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AppContainer from './AppContainer.vue'

describe('AppContainer', () => {
  it('renders content inside the responsive container', () => {
    const wrapper = mount(AppContainer, {
      slots: { default: '<p>Inside</p>' },
    })
    expect(wrapper.get('div.container').text()).toContain('Inside')
  })

  it('renders as a semantic element when requested', () => {
    const wrapper = mount(AppContainer, {
      props: { as: 'section' },
      slots: { default: 'x' },
    })
    expect(wrapper.element.tagName).toBe('SECTION')
  })

  it('supports the narrow variant', () => {
    const wrapper = mount(AppContainer, { props: { narrow: true } })
    expect(wrapper.get('.container--narrow').exists()).toBe(true)
  })
})
