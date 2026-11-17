import { describe, expect, it } from 'vitest'

import { categoryHref } from '../utils/categoryLinks'

describe('categoryHref', () => {
  it('links an L1 with a channel code to the channel landing page', () => {
    expect(categoryHref({ slug: 'home-living', channel_code: 'UK-Mini-HP-Home-Living' })).toBe(
      '/minihome/UK-Mini-HP-Home-Living',
    )
  })

  it('falls back to the results page when the root has no channel code', () => {
    expect(categoryHref({ slug: 'outdoor-sports', channel_code: null })).toBe('/c/outdoor-sports')
    expect(categoryHref({ slug: 'computers-accessories' })).toBe('/c/computers-accessories')
    // 非字符串的脏值同样降级，不进入 /minihome/。
    expect(categoryHref({ slug: 'electronics', channel_code: 123 })).toBe('/c/electronics')
  })

  it('returns an empty href for missing categories', () => {
    expect(categoryHref(null)).toBe('')
    expect(categoryHref({})).toBe('')
  })
})
