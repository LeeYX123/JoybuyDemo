import { describe, expect, it } from 'vitest'

import { ratingAverageLabel, soldCountLabel } from '../utils/pdpDisplay'

describe('PDP rating / sold display (需求 22.1-5、23.1-2/3)', () => {
  it('always keeps the "+" on stored sale amounts (23.1-3)', () => {
    expect(soldCountLabel('any-id', '10k+')).toBe('10k+')
    expect(soldCountLabel('any-id', ' 2.6k+ ')).toBe('2.6k+')
    expect(soldCountLabel('any-id', '40')).toBe('40+')
    expect(soldCountLabel('any-id', '461')).toBe('461+')
    expect(soldCountLabel('any-id', '12k')).toBe('12k+')
    expect(soldCountLabel('any-id', '1.5K+')).toBe('1.5k+')
  })

  it('abbreviates plain numbers >= 1000 in the real-site k style', () => {
    expect(soldCountLabel('any-id', '12000')).toBe('12k+')
    expect(soldCountLabel('any-id', '1500')).toBe('1.5k+')
    expect(soldCountLabel('any-id', '1,200')).toBe('1.2k+')
  })

  it('derives a stable 10k–30k label from the product id when the field is missing', () => {
    const first = soldCountLabel('3e75a502-c6e8-4328-9c28-487ed9f398ef', null)
    const second = soldCountLabel('3e75a502-c6e8-4328-9c28-487ed9f398ef', '')
    expect(first).toBe(second)
    expect(first).toMatch(/^\d{2}k\+$/)
    const numeric = Number(first.replace('k+', ''))
    expect(numeric).toBeGreaterThanOrEqual(10)
    expect(numeric).toBeLessThanOrEqual(30)
  })

  it('gives different products different stable labels', () => {
    const labels = new Set(['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'].map((id) => soldCountLabel(id)))
    expect(labels.size).toBeGreaterThan(1)
  })

  it('formats the review average, with a dash when there are no reviews', () => {
    expect(ratingAverageLabel({ average: '4.90', count: 1272 })).toBe('4.9')
    expect(ratingAverageLabel({ average: null, count: 0 })).toBe('—')
    expect(ratingAverageLabel(null)).toBe('—')
  })
})
