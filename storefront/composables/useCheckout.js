import { computed } from 'vue'
import { useFetch, useRequestHeaders, useRuntimeConfig } from '#imports'

// Buyer checkout helpers: address CRUD, quote, order placement. All
// mutations happen in the browser with a CSRF token from the session.
export async function useCheckout() {
  const config = useRuntimeConfig()

  function api(path) {
    return import.meta.server ? `${config.apiBaseInternal}${path}` : `/api/v1${path}`
  }

  const { data: addresses, refresh } = await useFetch(() => api('/addresses'), {
    key: 'addresses',
    headers: { cookie: useRequestHeaders(['cookie']).cookie || '' },
  })

  const addressList = computed(() =>
    Array.isArray(addresses.value?.addresses) ? addresses.value.addresses : [],
  )

  async function createAddress(payload) {
    const session = await $fetch(api('/auth/buyer/session'), { credentials: 'include' })
    return $fetch(api('/addresses'), {
      method: 'POST',
      body: payload,
      headers: { 'X-CSRFToken': session?.csrf_token || '' },
      credentials: 'include',
      ignoreResponseError: true,
    }).finally(() => refresh())
  }

  async function getQuote(addressPublicId) {
    const session = await $fetch(api('/auth/buyer/session'), { credentials: 'include' })
    return $fetch(api('/checkout/quote'), {
      method: 'POST',
      body: { address_public_id: addressPublicId },
      headers: { 'X-CSRFToken': session?.csrf_token || '' },
      credentials: 'include',
      ignoreResponseError: true,
    })
  }

  async function placeOrder(addressPublicId) {
    const session = await $fetch(api('/auth/buyer/session'), { credentials: 'include' })
    return $fetch(api('/orders'), {
      method: 'POST',
      body: { address: { public_id: addressPublicId } },
      headers: { 'X-CSRFToken': session?.csrf_token || '' },
      credentials: 'include',
      ignoreResponseError: true,
    })
  }

  return { addressList, createAddress, getQuote, placeOrder }
}
