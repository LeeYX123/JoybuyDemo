import { computed } from 'vue'
import { useCookie } from '#imports'

import { messages, pickName } from '../locales/messages'

// Lightweight storefront locale (docs/12: bilingual EN/ZH target state).
// Persisted in a cookie so SSR renders the same language as the browser.
export function useLocale() {
  const cookie = useCookie('joybuy-locale', {
    default: () => 'en',
    maxAge: 60 * 60 * 24 * 365,
    sameSite: 'lax',
  })

  const locale = computed(() => (cookie.value === 'zh' ? 'zh' : 'en'))

  function t(key) {
    return messages[locale.value]?.[key] ?? messages.en[key] ?? key
  }

  function setLocale(value) {
    cookie.value = value === 'zh' ? 'zh' : 'en'
  }

  function toggleLocale() {
    cookie.value = locale.value === 'zh' ? 'en' : 'zh'
  }

  // Category rows come from the API with name_en/name_zh.
  function categoryName(category) {
    return pickName(category, locale.value)
  }

  return { locale, t, setLocale, toggleLocale, categoryName }
}
