import { describe, expect, it } from 'vitest'

import { formatDisplayPrice, isDeliveryLabel, isPromoLabel } from './display'

describe('formatDisplayPrice', () => {
  it('formats every price with the US dollar symbol', () => {
    expect(formatDisplayPrice('19.99')).toBe('£19.99')
    expect(formatDisplayPrice('39.5000')).toBe('£39.50')
    expect(formatDisplayPrice(54)).toBe('£54.00')
    expect(formatDisplayPrice(0)).toBe('£0.00')
  })

  it('returns null for empty or non-numeric values', () => {
    expect(formatDisplayPrice(null)).toBeNull()
    expect(formatDisplayPrice(undefined)).toBeNull()
    expect(formatDisplayPrice('')).toBeNull()
    expect(formatDisplayPrice('not-a-price')).toBeNull()
  })
})

describe('isDeliveryLabel', () => {
  it('detects delivery-estimate label text in English and Chinese', () => {
    expect(isDeliveryLabel('Arrives today')).toBe(true)
    expect(isDeliveryLabel('Get it by tomorrow')).toBe(true)
    expect(isDeliveryLabel('FREE delivery')).toBe(true)
    expect(isDeliveryLabel('Ships in 24 hours')).toBe(true)
    expect(isDeliveryLabel('今日前送达')).toBe(true)
    expect(isDeliveryLabel('明日到达')).toBe(true)
  })

  it('keeps regular promo labels', () => {
    expect(isDeliveryLabel('Flash Sale')).toBe(false)
    expect(isDeliveryLabel('New')).toBe(false)
    expect(isDeliveryLabel('999+ sold')).toBe(false)
  })

  it('returns false for non-string values', () => {
    expect(isDeliveryLabel(null)).toBe(false)
    expect(isDeliveryLabel(undefined)).toBe(false)
    expect(isDeliveryLabel(42)).toBe(false)
  })
})

describe('isPromoLabel', () => {
  it('detects discount wording in English and Chinese', () => {
    expect(isPromoLabel('70% off')).toBe(true)
    expect(isPromoLabel('81% OFF')).toBe(true)
    expect(isPromoLabel('Save 60% on RRP')).toBe(true)
    expect(isPromoLabel('-30%')).toBe(true)
    expect(isPromoLabel('满减 20')).toBe(true)
    expect(isPromoLabel('立减 $5')).toBe(true)
    expect(isPromoLabel('限时折扣')).toBe(true)
    expect(isPromoLabel('优惠 30%')).toBe(true)
    expect(isPromoLabel('Was $49.99')).toBe(true)
    expect(isPromoLabel('Big discount')).toBe(true)
  })

  it('keeps neutral badges', () => {
    expect(isPromoLabel('New')).toBe(false)
    expect(isPromoLabel('Bestseller')).toBe(false)
    expect(isPromoLabel('999+ sold')).toBe(false)
    expect(isPromoLabel('Arrives today')).toBe(false)
  })

  it('returns false for non-string values', () => {
    expect(isPromoLabel(null)).toBe(false)
    expect(isPromoLabel(undefined)).toBe(false)
    expect(isPromoLabel(42)).toBe(false)
  })
})
