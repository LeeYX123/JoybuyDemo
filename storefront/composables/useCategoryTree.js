import { computed } from 'vue'
import { useFetch, useRuntimeConfig } from '#imports'
import { useMarketLocale } from './useMarketLocale'

// Shared category tree (roots + one child level) for the header category row
// and the Categories panel; SSR fetches Django directly, client uses proxy.
export function useCategoryTree() {
  const config = useRuntimeConfig()
  const { apiQuery } = useMarketLocale()
  const query = computed(() => new URLSearchParams(apiQuery.value).toString())
  const url = computed(() =>
    import.meta.server
      ? `${config.apiBaseInternal}/categories?${query.value}`
      : `/api/v1/categories?${query.value}`,
  )

  const { data } = useFetch(url, {
    key: `category-tree-${query.value}`,
    default: () => ({ categories: [] }),
  })

  const categories = computed(() => data.value?.categories || [])
  return { categories }
}
