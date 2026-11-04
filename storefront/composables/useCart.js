import { computed } from 'vue'
import { useFetch, useRequestHeaders, useRuntimeConfig } from '#imports'

import { formatDisplayPrice } from '../utils/display'

// Cart state: reads render on the server with the buyer/cart cookies
// forwarded; mutations always run in the browser (anonymous token cookie is
// set by the backend response).
export async function useCart() {
  const config = useRuntimeConfig()

  function cartUrl(path = '') {
    return import.meta.server ? `${config.apiBaseInternal}/cart${path}` : `/api/v1/cart${path}`
  }

  const { data, refresh, error } = await useFetch(() => cartUrl(''), {
    key: 'cart',
    headers: { cookie: useRequestHeaders(['cookie']).cookie || '' },
  })

  const items = computed(() => (Array.isArray(data.value?.items) ? data.value.items : []))
  const subtotal = computed(() => data.value?.subtotal ?? null)
  const currency = computed(() => data.value?.currency || 'GBP')
  const needsAttention = computed(() => Boolean(data.value?.needs_attention))

  function formatMoney(value) {
    return formatDisplayPrice(value)
  }

  async function mutate(method, path, body) {
    // Django CSRF applies to cart writes too; refresh the browser-side
    // token through the same-origin session endpoint first.
    const session = await $fetch(
      import.meta.server
        ? `${config.apiBaseInternal}/auth/buyer/session`
        : '/api/v1/auth/buyer/session',
      { credentials: 'include' },
    )
    const response = await $fetch(cartUrl(path), {
      method,
      body,
      headers: { 'X-CSRFToken': session?.csrf_token || '' },
      credentials: 'include',
      ignoreResponseError: true,
    })
    await refresh()
    return response
  }

  async function addItem(offerPublicId, quantity = 1) {
    return mutate('POST', '/items', { offer_public_id: offerPublicId, quantity })
  }

  async function updateItem(itemPublicId, quantity) {
    return mutate('PATCH', `/items/${itemPublicId}`, { quantity })
  }

  async function removeItem(itemPublicId) {
    return mutate('DELETE', `/items/${itemPublicId}`)
  }

  return {
    items,
    subtotal,
    currency,
    needsAttention,
    error,
    formatMoney,
    refresh,
    addItem,
    updateItem,
    removeItem,
  }
}
