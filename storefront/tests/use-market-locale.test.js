import { describe, expect, it } from 'vitest'

import { MARKET_OPTIONS } from '../composables/useMarketLocale'

describe('European market locale options', () => {
  it('contains the six requested markets', () => {
    expect(MARKET_OPTIONS.map((item) => item.code).sort()).toEqual([
      'BE',
      'DE',
      'FR',
      'GB',
      'LU',
      'NL',
    ])
  })

  it('supports multilingual Belgium and Luxembourg', () => {
    const belgium = MARKET_OPTIONS.find((item) => item.code === 'BE')
    const luxembourg = MARKET_OPTIONS.find((item) => item.code === 'LU')
    expect(belgium.locales.map((item) => item.code)).toEqual(['nl-BE', 'fr-BE', 'de-BE'])
    expect(luxembourg.locales.map((item) => item.code)).toEqual(['lb-LU', 'fr-LU', 'de-LU'])
  })
})
