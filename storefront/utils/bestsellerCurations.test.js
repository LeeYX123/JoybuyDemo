import { describe, expect, it } from 'vitest'

import {
  BESTSELLER_CURATIONS,
  bestsellerSegments,
  composeCuratedItems,
  curationTotal,
  isRenderableCard,
} from './bestsellerCurations'

function product(id, extra = {}) {
  return {
    spu_public_id: id,
    title: `Product ${id}`,
    image_path: `/media/products/${id}.jpg`,
    price_min: '9.99',
    retail_price: '9.99',
    is_family_representative: true,
    ...extra,
  }
}

const ids = (items) => items.map((item) => item.spu_public_id)

describe('bestseller curation config', () => {
  it('declares the two curated tabs with 3:2 segments', () => {
    expect(bestsellerSegments('home-living')).toEqual([
      { category: 'furniture', count: 3 },
      { category: 'bedding-textiles', count: 2 },
    ])
    expect(bestsellerSegments('health-wellness')).toEqual([
      { category: 'nutrition-supplements', count: 3 },
      { category: 'sports-nutrition-performance', count: 2 },
    ])
    // Tabs outside the config keep the plain single request.
    expect(bestsellerSegments('electronics')).toBeNull()
    expect(bestsellerSegments('')).toBeNull()
    expect(curationTotal(BESTSELLER_CURATIONS['home-living'])).toBe(5)
    expect(curationTotal(BESTSELLER_CURATIONS['health-wellness'])).toBe(5)
  })

  it('only accepts cards that can actually render', () => {
    expect(isRenderableCard(product('a'))).toBe(true)
    expect(isRenderableCard(product('a', { image_path: '' }))).toBe(false)
    expect(isRenderableCard(product('a', { price_min: null, retail_price: '' }))).toBe(false)
    expect(isRenderableCard(product('a', { is_family_representative: false }))).toBe(false)
    expect(isRenderableCard(null)).toBe(false)
    // A family member hidden behind its representative must never slip in.
    expect(isRenderableCard(product('a', { is_family_representative: undefined }))).toBe(true)
  })
})

describe('composeCuratedItems', () => {
  const segments = bestsellerSegments('health-wellness')

  it('takes 3 from the primary sub-category then 2 from the secondary', () => {
    const { items, complete } = composeCuratedItems(segments, [
      [product('n1'), product('n2'), product('n3'), product('n4')],
      [product('s1'), product('s2'), product('s3')],
    ])
    expect(ids(items)).toEqual(['n1', 'n2', 'n3', 's1', 's2'])
    expect(complete).toBe(true)
  })

  it('never repeats a spu_public_id and pulls the next candidate instead', () => {
    const { items, complete } = composeCuratedItems(segments, [
      [product('n1'), product('n2'), product('n3'), product('n4')],
      // s1 also appears as the primary segment's 4th item (merged family).
      [product('s1'), product('n4'), product('s2')],
    ])
    expect(ids(items)).toEqual(['n1', 'n2', 'n3', 's1', 's2'])
    expect(new Set(ids(items)).size).toBe(5)
    expect(complete).toBe(true)
  })

  it('skips unusable cards when filling a segment', () => {
    const { items } = composeCuratedItems(segments, [
      [product('n1'), product('n2', { image_path: '' }), product('n3'), product('n4')],
      [product('s1'), product('s2')],
    ])
    expect(ids(items)).toEqual(['n1', 'n3', 'n4', 's1', 's2'])
  })

  it('tops a short sub-category up from the other sub-category, keeping order', () => {
    // Bedding can only supply 1 of its 2 slots; furniture's 4th candidate fills.
    const homeLiving = bestsellerSegments('home-living')
    const { items, complete } = composeCuratedItems(homeLiving, [
      [product('f1'), product('f2'), product('f3'), product('f4')],
      [product('b1')],
    ])
    expect(ids(items)).toEqual(['f1', 'f2', 'f3', 'b1', 'f4'])
    expect(complete).toBe(true)
  })

  it('reports an incomplete row when the candidates cannot fill it', () => {
    const homeLiving = bestsellerSegments('home-living')
    const { items, complete } = composeCuratedItems(homeLiving, [[product('f1')], [product('b1')]])
    expect(ids(items)).toEqual(['f1', 'b1'])
    expect(complete).toBe(false)
  })

  it('handles missing responses without throwing', () => {
    const { items, complete } = composeCuratedItems(segments, [[], undefined])
    expect(items).toEqual([])
    expect(complete).toBe(false)
  })
})
