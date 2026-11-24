import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import MobilePageHeader from './MobilePageHeader.vue'
import MobileReturns from './MobileReturns.vue'

// Mobile after-sales (docs/20 §5.5): the real-site tab row + honest empty
// card (same copy as the desktop returns.empty).
const tabs = [
  { key: 'all', label: 'All' },
  { key: 'in_progress', label: 'In progress' },
  { key: 'completed', label: 'Completed' },
  { key: 'canceled', label: 'Canceled' },
]

function mountReturns(extraProps = {}) {
  return mount(MobileReturns, {
    props: { tabs, activeTab: 'all', ...extraProps },
    global: {
      components: { MobilePageHeader },
      stubs: {
        NuxtLink: { template: '<a><slot /></a>' },
      },
    },
  })
}

describe('MobileReturns', () => {
  it('renders the tab row and emits the tab click', async () => {
    const wrapper = mountReturns()

    expect(wrapper.find('.m-page-head__title').text()).toBe('After-sales')

    const tabButtons = wrapper.findAll('.m-returns__tab')
    expect(tabButtons).toHaveLength(4)
    expect(tabButtons[0].classes()).toContain('m-returns__tab--active')

    await tabButtons[1].trigger('click')
    expect(wrapper.emitted().tab[0]).toEqual(['in_progress'])
  })

  it('shows the empty state', () => {
    const wrapper = mountReturns()

    const empty = wrapper.find('.m-returns__empty')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('No after-sales records.')
  })
})
