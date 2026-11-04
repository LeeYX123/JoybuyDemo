import { computed, ref } from 'vue'
import { useFetch, useRequestHeaders, useRuntimeConfig } from '#imports'

// Shared loader for buyer activity lists (favourites / recently-viewed).
// Reads render on the server via the internal base; mutations run in the
// browser with a fresh CSRF token from the same-origin session endpoint.
export async function useActivityList(resource) {
  const config = useRuntimeConfig()
  const page = ref(1)

  const url = computed(() =>
    import.meta.server
      ? `${config.apiBaseInternal}/buyer/${resource}?page=${page.value}`
      : `/api/v1/buyer/${resource}?page=${page.value}`,
  )

  const { data, refresh, error } = await useFetch(url, {
    key: `activity-${resource}-${page.value}`,
    headers: { cookie: useRequestHeaders(['cookie']).cookie || '' },
  })

  const items = computed(() => (Array.isArray(data.value?.items) ? data.value.items : []))
  const total = computed(() => data.value?.total ?? 0)
  const totalPages = computed(() => data.value?.total_pages ?? 0)

  function goToPage(next) {
    if (next >= 1 && (totalPages.value === 0 || next <= totalPages.value)) {
      page.value = next
    }
  }

  async function mutate(method, body) {
    const session = await $fetch(`/api/v1/auth/buyer/session`, {
      credentials: 'include',
    })
    return $fetch(`/api/v1/buyer/${resource}`, {
      method,
      body,
      headers: { 'X-CSRFToken': session?.csrf_token || '' },
      credentials: 'include',
      ignoreResponseError: true,
    }).finally(() => refresh())
  }

  async function clientDelete(spuPublicId) {
    return mutate('DELETE', { spu_public_id: spuPublicId })
  }

  async function clearAll() {
    return mutate('DELETE', undefined)
  }

  return { items, total, totalPages, page, error, refresh, goToPage, clientDelete, clearAll }
}
