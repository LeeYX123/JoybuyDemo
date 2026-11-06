import { computed } from 'vue'
import { useCookie } from '#imports'

import { useLocale } from './useLocale'

export const MARKET_OPTIONS = [
  {
    code: 'BE',
    name: 'Belgium',
    defaultLocale: 'nl-BE',
    locales: [
      { code: 'nl-BE', name: 'Nederlands' },
      { code: 'fr-BE', name: 'Français' },
      { code: 'de-BE', name: 'Deutsch' },
    ],
  },
  {
    code: 'DE',
    name: 'Germany',
    defaultLocale: 'de-DE',
    locales: [{ code: 'de-DE', name: 'Deutsch' }],
  },
  {
    code: 'FR',
    name: 'France',
    defaultLocale: 'fr-FR',
    locales: [{ code: 'fr-FR', name: 'Français' }],
  },
  {
    code: 'NL',
    name: 'Netherlands',
    defaultLocale: 'nl-NL',
    locales: [{ code: 'nl-NL', name: 'Nederlands' }],
  },
  {
    code: 'LU',
    name: 'Luxembourg',
    defaultLocale: 'lb-LU',
    locales: [
      { code: 'lb-LU', name: 'Lëtzebuergesch' },
      { code: 'fr-LU', name: 'Français' },
      { code: 'de-LU', name: 'Deutsch' },
    ],
  },
  {
    code: 'GB',
    name: 'United Kingdom',
    defaultLocale: 'en-GB',
    locales: [
      { code: 'en-GB', name: 'English' },
      { code: 'zh-CN', name: '中文（简体）' },
    ],
  },
]

export function useMarketLocale() {
  const marketCookie = useCookie('joybuy-market', {
    default: () => 'GB',
    maxAge: 60 * 60 * 24 * 365,
    sameSite: 'lax',
  })
  const { localeCode, setLocale } = useLocale()

  const market = computed(() =>
    MARKET_OPTIONS.some((item) => item.code === marketCookie.value) ? marketCookie.value : 'GB',
  )
  const marketOption = computed(
    () => MARKET_OPTIONS.find((item) => item.code === market.value) || MARKET_OPTIONS.at(-1),
  )
  const availableLocales = computed(() => marketOption.value.locales)

  function setMarket(value) {
    const selected = MARKET_OPTIONS.find((item) => item.code === value)
    if (!selected) return
    marketCookie.value = selected.code
    if (!selected.locales.some((item) => item.code === localeCode.value)) {
      setLocale(selected.defaultLocale)
    }
  }

  function setMarketLocale(value) {
    if (availableLocales.value.some((item) => item.code === value)) setLocale(value)
  }

  const apiQuery = computed(() => ({ market: market.value, locale: localeCode.value }))
  return {
    market,
    marketOption,
    localeCode,
    availableLocales,
    apiQuery,
    setMarket,
    setMarketLocale,
  }
}
