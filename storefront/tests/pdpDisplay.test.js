import { describe, expect, it } from 'vitest'

import { ratingAverageLabel, ratingCountLabel, soldCountLabel } from '../utils/pdpDisplay'

describe('PDP rating / sold display (需求 22.1-5)', () => {
  it('uses the stored sale amount when the API provides one', () => {
    expect(soldCountLabel('any-id', '10k+')).toBe('10k+')
    expect(soldCountLabel('any-id', ' 2.6k+ ')).toBe('2.6k+')
  })

  it('derives a stable 10k–30k label from the product id when the field is missing', () => {
    const first = soldCountLabel('3e75a502-c6e8-4328-9c28-487ed9f398ef')
    const second = soldCountLabel('3e75a502-c6e8-4328-9c28-487ed9f398ef')
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

  it('formats the review average and count, with a dash when there are no reviews', () => {
    expect(ratingAverageLabel({ average: '4.90', count: 1272 })).toBe('4.9')
    expect(ratingCountLabel({ average: '4.90', count: 1272 })).toBe(1272)
    expect(ratingAverageLabel({ average: null, count: 0 })).toBe('—')
    expect(ratingCountLabel(null)).toBe(0)
  })
})
