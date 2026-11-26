import { describe, expect, it } from 'vitest'

import { findSkuForOffer, resolveSelectedSku } from '../utils/offerSelection'

// 批次 DB：SKU 带全部商家 offer（sku.offers）后，切商家写进 URL 的 offer
// 必须仍能匹配回同一个 SKU，否则所选规格会被弹回 SKU[0]。
const SKU_A = {
  public_id: 'sku-a',
  offer: { public_id: 'offer-a1' },
  offers: [{ public_id: 'offer-a1' }, { public_id: 'offer-a2' }],
}
const SKU_B = { public_id: 'sku-b', offer: { public_id: 'offer-b1' }, offers: [] }

describe('offerSelection', () => {
  it('matches an offer from the sku offers list (second seller)', () => {
    expect(findSkuForOffer([SKU_A, SKU_B], 'offer-a2')).toBe(SKU_A)
    expect(findSkuForOffer([SKU_A, SKU_B], 'offer-b1')).toBe(SKU_B)
    expect(findSkuForOffer([SKU_A, SKU_B], 'unknown')).toBeNull()
    expect(findSkuForOffer(null, 'x')).toBeNull()
  })

  it('prefers explicit sku, then offer-matched sku, then first sku', () => {
    expect(resolveSelectedSku([SKU_A, SKU_B], 'sku-b', 'offer-a2')).toBe(SKU_B)
    expect(resolveSelectedSku([SKU_A, SKU_B], null, 'offer-a2')).toBe(SKU_A)
    expect(resolveSelectedSku([SKU_A, SKU_B], null, '')).toBe(SKU_A)
    expect(resolveSelectedSku([], null, 'x')).toBeNull()
  })
})
