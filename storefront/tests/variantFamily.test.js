import { describe, expect, it } from 'vitest'

import {
  familyMembers,
  memberLabel,
  merchantLabel,
  merchantOffers,
  preferredOfferId,
  resolveActiveOffer,
  siblingTarget,
} from '../utils/variantFamily'

const OFFER_A = {
  public_id: 'offer-a',
  price: '1499.0000',
  merchant: { public_id: 'merchant-a', display_name: 'Seller A', slug: 'seller-a' },
}
const OFFER_B = {
  public_id: 'offer-b',
  price: '1999.0000',
  merchant: { public_id: 'merchant-b', display_name: 'Seller B', slug: 'seller-b' },
}

const FAMILY = {
  variant_family: {
    family_key: 'title:d44d8a2619cb',
    axis_hint: 'Model/Style',
    representative_spu_public_id: 'spu-max',
    members: [
      {
        spu_public_id: 'spu-max',
        title: 'Hypershell X Max S',
        axis_label: 'Max S',
        is_current: true,
        skus: [{ sku_public_id: 'sku-max', offers: [OFFER_A] }],
      },
      {
        spu_public_id: 'spu-ultra',
        title: 'Hypershell X Ultra S',
        axis_label: 'Ultra S',
        is_current: false,
        skus: [{ sku_public_id: 'sku-ultra', offers: [OFFER_B] }],
      },
    ],
  },
}

describe('variantFamily helpers', () => {
  it('returns family members only for multi-SPU families', () => {
    expect(familyMembers(FAMILY)).toHaveLength(2)
    expect(familyMembers({ variant_family: null })).toEqual([])
    expect(
      familyMembers({ variant_family: { members: [FAMILY.variant_family.members[0]] } }),
    ).toEqual([])
  })

  it('falls back to the single offer when no offers list exists', () => {
    expect(merchantOffers({ offer: OFFER_A })).toEqual([OFFER_A])
    expect(merchantOffers(null)).toEqual([])
  })

  it('resolves the active offer by id, then default offer, then first', () => {
    const sku = { offer: OFFER_A, offers: [OFFER_A, OFFER_B] }
    expect(resolveActiveOffer(sku, 'offer-b')).toEqual(OFFER_B)
    expect(resolveActiveOffer(sku, 'missing')).toEqual(OFFER_A)
    expect(resolveActiveOffer({ offers: [OFFER_B] }, '')).toEqual(OFFER_B)
    expect(resolveActiveOffer({ offers: [] }, 'x')).toBeNull()
  })

  it('keeps the same seller across spec switches when possible', () => {
    const target = { offer: OFFER_A, offers: [OFFER_A, OFFER_B] }
    expect(preferredOfferId(target, OFFER_B)).toBe('offer-b')
    expect(preferredOfferId(target, { merchant: { public_id: 'nope' }, public_id: 'x' })).toBe('')
  })

  it('builds a sibling link carrying the same seller offer and from=merchant', () => {
    const target = siblingTarget(FAMILY.variant_family.members[1], OFFER_A, { from: 'merchant' })
    expect(target.path).toBe('/p/spu-ultra')
    // 对方只有 offer-b（不同商家）→ 不带 offer
    expect(target.query).toEqual({ from: 'merchant' })

    const sameSeller = siblingTarget(
      {
        spu_public_id: 'spu-ultra',
        skus: [{ offers: [{ ...OFFER_B, merchant: OFFER_A.merchant }] }],
      },
      OFFER_A,
    )
    expect(sameSeller.query.offer).toBe('offer-b')
  })

  it('labels members and sellers with readable fallbacks', () => {
    expect(memberLabel({ axis_label: 'Ultra S' })).toBe('Ultra S')
    expect(memberLabel({ title: 'Some product' })).toBe('Some product')
    expect(memberLabel({}, 2)).toBe('Option 3')
    expect(merchantLabel(OFFER_A)).toBe('Seller A')
    expect(merchantLabel(null)).toBe('')
  })
})
