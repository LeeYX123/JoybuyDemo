import { computed } from 'vue'
import { useFetch, useRuntimeConfig } from '#imports'

// Shared category tree (roots + one child level) for the header category row
// and the Categories panel; SSR fetches Django directly, client uses proxy.
export function useCategoryTree() {
  const config = useRuntimeConfig()
  const url = computed(() =>
    import.meta.server ? `${config.apiBaseInternal}/categories` : '/api/v1/categories',
  )

  const { data } = useFetch(url, {
    key: 'category-tree',
    default: () => ({ categories: [] }),
  })

  const categories = computed(() => data.value?.categories || [])
  return { categories }
}
