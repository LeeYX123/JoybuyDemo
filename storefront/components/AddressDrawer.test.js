import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import AddressDrawer from './AddressDrawer.vue'

// The delivery drawer's country/region control is a custom listbox because a
// native <select> cannot render the local CSS flags inside its options. These
// tests pin the user-visible rule: flag on the left, country name on the
// right, in the trigger and in every dropdown row.

let wrapper

function mountDrawer() {
  wrapper = mount(AddressDrawer, {
    props: { open: true, authenticated: false },
  })
  return wrapper
}

afterEach(() => {
  wrapper?.unmount()
  wrapper = null
})

describe('AddressDrawer country listbox', () => {
  it('renders the trigger as flag, then name, with listbox aria attributes', () => {
    mountDrawer()
    const trigger = wrapper.find('.country-select')
    expect(trigger.exists()).toBe(true)
    expect(trigger.attributes('aria-haspopup')).toBe('listbox')
    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(trigger.attributes('aria-controls')).toBe('address-drawer-country-listbox')
    expect(trigger.attributes('aria-label')).toBe('Country/region: United Kingdom')

    const children = [...trigger.element.children]
    const flagIndex = children.findIndex((el) => el.classList.contains('country-flag'))
    const nameIndex = children.findIndex((el) => el.classList.contains('country-select__name'))
    expect(flagIndex).toBeGreaterThanOrEqual(0)
    expect(flagIndex).toBeLessThan(nameIndex)
    expect(children[nameIndex].textContent.trim()).toBe('United Kingdom')
  })

  it('opens a listbox whose every row is flag, then name, with the selection marked', async () => {
    mountDrawer()
    await wrapper.find('.country-select').trigger('click')

    const listbox = wrapper.find('[role="listbox"]')
    expect(listbox.exists()).toBe(true)
    expect(listbox.attributes('id')).toBe('address-drawer-country-listbox')
    expect(wrapper.find('.country-select').attributes('aria-expanded')).toBe('true')

    const options = wrapper.findAll('[role="option"]')
    expect(options).toHaveLength(6)
    for (const option of options) {
      const children = [...option.element.children]
      const flagIndex = children.findIndex((el) => el.classList.contains('country-flag'))
      const nameIndex = children.findIndex((el) => el.classList.contains('country-menu__name'))
      expect(flagIndex).toBeGreaterThanOrEqual(0)
      expect(flagIndex).toBeLessThan(nameIndex)
    }

    const selected = options.find((option) => option.attributes('aria-selected') === 'true')
    expect(selected.text()).toContain('United Kingdom')
    expect(selected.find('.country-menu__check').exists()).toBe(true)
  })

  it('selects a country on click, emits country-change and closes the listbox', async () => {
    mountDrawer()
    await wrapper.find('.country-select').trigger('click')

    const germany = wrapper
      .findAll('[role="option"]')
      .find((option) => option.text().includes('Germany'))
    await germany.trigger('click')

    expect(wrapper.emitted('country-change')).toEqual([['DE']])
    expect(wrapper.find('[role="listbox"]').exists()).toBe(false)
    expect(wrapper.find('.country-select__name').text()).toBe('Germany')
    const flag = wrapper.find('.country-select .country-flag')
    expect(flag.classes()).toContain('country-flag--de')
  })

  it('closes on Escape without closing the drawer and on an outside pointerdown', async () => {
    mountDrawer()
    await wrapper.find('.country-select').trigger('click')
    const option = wrapper.find('[role="option"]')
    await option.trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('[role="listbox"]').exists()).toBe(false)
    expect(wrapper.emitted('close')).toBeUndefined()

    await wrapper.find('.country-select').trigger('click')
    expect(wrapper.find('[role="listbox"]').exists()).toBe(true)
    document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[role="listbox"]').exists()).toBe(false)
  })
})
