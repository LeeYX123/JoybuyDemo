import { describe, expect, it } from 'vitest'

import { findSkuForOffer, resolveSelectedSku } from './offerSelection'

function sku(publicId, offerId) {
  return { public_id: publicId, offer: offerId ? { public_id: offerId } : null }
}

describe('offerSelection', () => {
  const skus = [sku('sku-a', 'offer-a'), sku('sku-b', 'offer-b'), sku('sku-c')]

  it('finds the SKU that belongs to the requested merchant offer', () => {
    expect(findSkuForOffer(skus, 'offer-b')?.public_id).toBe('sku-b')
  })

  it('returns null when the offer is missing or unknown', () => {
    expect(findSkuForOffer(skus, '')).toBeNull()
    expect(findSkuForOffer(skus, 'offer-from-another-shop')).toBeNull()
    expect(findSkuForOffer(null, 'offer-a')).toBeNull()
  })

  it('prefers the merchant offer over the first purchasable SKU (需求 20.1)', () => {
    expect(resolveSelectedSku(skus, null, 'offer-b')?.public_id).toBe('sku-b')
  })

  it('keeps a manual variant selection', () => {
    expect(resolveSelectedSku(skus, 'sku-a', 'offer-b')?.public_id).toBe('sku-a')
  })

  it('falls back to the first SKU when the offer is not on this product', () => {
    expect(resolveSelectedSku(skus, null, 'offer-removed')?.public_id).toBe('sku-a')
  })

  it('returns null for an empty product', () => {
    expect(resolveSelectedSku([], null, 'offer-a')).toBeNull()
  })
})
