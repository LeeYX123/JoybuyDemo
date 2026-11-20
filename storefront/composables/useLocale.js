import { computed } from 'vue'
import { useCookie } from '#imports'

import { messages, pickName } from '../locales/messages'

const localeAliases = {
  en: 'en-GB',
  zh: 'zh-CN',
  de: 'de-DE',
  fr: 'fr-FR',
  nl: 'nl-NL',
  lb: 'lb-LU',
}

// Locale is persisted as a full BCP-47-like code. UI copy may fall back to
// English while product content and specifications still use the exact locale.
export function useLocale() {
  const cookie = useCookie('joybuy-locale', {
    default: () => 'en',
    maxAge: 60 * 60 * 24 * 365,
    sameSite: 'lax',
  })

  const localeCode = computed(() => localeAliases[cookie.value] || cookie.value || 'en-GB')
  const locale = computed(() => localeCode.value.split('-')[0].toLowerCase())

  function t(key, params) {
    let text = messages[locale.value]?.[key] ?? messages.en[key] ?? key
    if (params) {
      for (const [name, value] of Object.entries(params)) {
        text = text.replaceAll(`{${name}}`, String(value))
      }
    }
    return text
  }

  function setLocale(value) {
    cookie.value = localeAliases[value] || value || 'en-GB'
  }

  function toggleLocale() {
    cookie.value = locale.value === 'zh' ? 'en-GB' : 'zh-CN'
  }

  // Category rows come from the API with name_en/name_zh.
  function categoryName(category) {
    return pickName(category, locale.value)
  }

  return { locale, localeCode, t, setLocale, toggleLocale, categoryName }
}
