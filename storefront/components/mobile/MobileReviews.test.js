import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import MobilePageHeader from './MobilePageHeader.vue'
import MobileReviews from './MobileReviews.vue'

// Mobile reviews (docs/20 §5.6, user decision): review semantics only — the
// header is 我的评价 ("My reviews") with to-review/reviewed tabs and NO Q&A
// tab. Empty body reuses the desktop reviews.empty copy.
const tabs = [
  { key: 'to_review', label: 'To review' },
  { key: 'reviewed', label: 'Reviewed' },
]

describe('MobileReviews', () => {
  it('renders 我的评价 + two tabs, and never a Q&A tab', async () => {
    const wrapper = mount(MobileReviews, {
      props: { tabs, activeTab: 'to_review' },
      global: {
        components: { MobilePageHeader },
        stubs: {
          NuxtLink: { template: '<a><slot /></a>' },
        },
      },
    })

    // Header: the review-only title, not the desktop "Reviews and Q&A".
    expect(wrapper.find('.m-page-head__title').text()).toBe('My reviews')

    // Exactly two tabs, no Q&A tab among them.
    const tabButtons = wrapper.findAll('.m-reviews__tab')
    expect(tabButtons).toHaveLength(2)
    expect(tabButtons.map((tab) => tab.text())).toEqual(['To review', 'Reviewed'])
    expect(tabButtons[0].classes()).toContain('m-reviews__tab--active')

    await tabButtons[1].trigger('click')
    expect(wrapper.emitted().tab[0]).toEqual(['reviewed'])

    // Empty state reuses the desktop copy.
    expect(wrapper.find('.m-reviews__empty').text()).toContain('No reviews')
  })
})
