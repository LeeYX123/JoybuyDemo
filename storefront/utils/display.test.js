import { describe, expect, it } from 'vitest'

import { formatDisplayPrice, isDeliveryLabel } from './display'

describe('formatDisplayPrice', () => {
  it('formats every price with the US dollar symbol', () => {
    expect(formatDisplayPrice('19.99')).toBe('$19.99')
    expect(formatDisplayPrice('39.5000')).toBe('$39.50')
    expect(formatDisplayPrice(54)).toBe('$54.00')
    expect(formatDisplayPrice(0)).toBe('$0.00')
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
