import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

// 慢网络下 /active、/store 在 pending 阶段渲染骨架（2026-11-26 用户反馈：
// 之前先闪一帧「This page is not available」）。骨架形状要对齐真实布局：
// 店铺页有黑条，活动页没有；都含 hero + 两层 5 列商品卡占位。
vi.mock('../composables/useLocale', () => ({
  useLocale: () => ({ t: (key) => key, locale: { value: 'en' } }),
}))

import ActivityPageSkeleton from '../components/activity/ActivityPageSkeleton.vue'

describe('ActivityPageSkeleton', () => {
  it('activity kind renders hero + floors without the store bar', () => {
    const wrapper = mount(ActivityPageSkeleton, { props: { kind: 'activity' } })
    expect(wrapper.find('.activity-skeleton__store-bar').exists()).toBe(false)
    expect(wrapper.find('.activity-skeleton__hero').exists()).toBe(true)
    expect(wrapper.findAll('.activity-skeleton__floor')).toHaveLength(2)
    expect(wrapper.findAll('.activity-skeleton__card')).toHaveLength(10)
    expect(wrapper.find('.activity-skeleton').attributes('aria-busy')).toBe('true')
    expect(wrapper.find('.activity-skeleton__sr').text()).toBe('activity.loading')
  })

  it('store kind prepends the store header bar skeleton', () => {
    const wrapper = mount(ActivityPageSkeleton, { props: { kind: 'store' } })
    expect(wrapper.find('.activity-skeleton__store-bar').exists()).toBe(true)
    expect(wrapper.find('.activity-skeleton__store-name').exists()).toBe(true)
    expect(wrapper.findAll('.activity-skeleton__floor')).toHaveLength(2)
  })
})
