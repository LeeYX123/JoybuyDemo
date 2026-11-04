import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import BaseBadge from './BaseBadge.vue'
import BaseButton from './BaseButton.vue'
import BaseRatingStars from './BaseRatingStars.vue'
import BaseSkeleton from './BaseSkeleton.vue'

describe('BaseButton', () => {
  it('emits click only when enabled', async () => {
    const enabled = mount(BaseButton)
    await enabled.trigger('click')
    expect(enabled.emitted('click')).toHaveLength(1)

    const disabled = mount(BaseButton, { props: { disabled: true } })
    expect(disabled.get('button').attributes('disabled')).toBeDefined()
    await disabled.trigger('click')
    expect(disabled.emitted('click')).toBeUndefined()
  })

  it('rejects unknown variants and sizes via the prop validators', () => {
    const validators = BaseButton.props
    expect(validators.variant.validator('neon')).toBe(false)
    expect(validators.variant.validator('primary')).toBe(true)
    expect(validators.size.validator('xl')).toBe(false)
    expect(validators.size.validator('lg')).toBe(true)
  })
})

describe('BaseBadge', () => {
  it('renders the requested tone', () => {
    const wrapper = mount(BaseBadge, { props: { tone: 'promo' }, slots: { default: '-30%' } })
    expect(wrapper.get('.base-badge--promo').text()).toBe('-30%')
  })

  it('rejects unknown tones via the prop validator', () => {
    expect(BaseBadge.props.tone.validator('gold')).toBe(false)
    expect(BaseBadge.props.tone.validator('success')).toBe(true)
  })
})

describe('BaseSkeleton', () => {
  it('renders decorative variants without content', () => {
    for (const variant of ['text', 'block', 'circle']) {
      const wrapper = mount(BaseSkeleton, { props: { variant } })
      expect(wrapper.get(`.base-skeleton--${variant}`).attributes('aria-hidden')).toBe('true')
    }
    expect(BaseSkeleton.props.variant.validator('wave')).toBe(false)
  })
})

describe('BaseRatingStars', () => {
  it('fills rounded stars and formats counts for en-GB', () => {
    const wrapper = mount(BaseRatingStars, { props: { rating: 4.4, count: 1234, showCount: true } })
    expect(wrapper.get('.rating-stars').attributes('aria-label')).toBe('Rated 4.4 out of 5')
    expect(wrapper.findAll('.star--filled')).toHaveLength(4)
    expect(wrapper.get('.rating-stars__count').text()).toBe('(1,234)')
  })

  it('clamps ratings outside the 0-5 range', () => {
    const wrapper = mount(BaseRatingStars, { props: { rating: 9 } })
    expect(wrapper.findAll('.star--filled')).toHaveLength(5)
  })
})
