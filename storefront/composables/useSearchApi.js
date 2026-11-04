import { computed } from 'vue'
import { useFetch, useRuntimeConfig } from '#imports'

// Shared composable for the storefront search API (SSR direct, client proxied).
export function useSearch(params) {
  const query = computed(() => {
    const search = new URLSearchParams()
    for (const [key, value] of Object.entries(params.value || {})) {
      if (value !== undefined && value !== null && value !== '') {
        search.set(key, String(value))
      }
    }
    return search.toString()
  })

  const config = useRuntimeConfig()
  const url = computed(() =>
    import.meta.server
      ? `${config.apiBaseInternal}/search${query.value ? `?${query.value}` : ''}`
      : `/api/v1/search${query.value ? `?${query.value}` : ''}`,
  )

  return useFetch(url, { key: `search-${JSON.stringify(params.value || {})}` })
}
