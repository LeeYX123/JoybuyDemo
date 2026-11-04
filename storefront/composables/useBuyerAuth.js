import { computed } from 'vue'
import { useCookie, useFetch, useRequestHeaders, useRuntimeConfig } from '#imports'

// Buyer session state backed by WP-05 cookie sessions. SSR fetches Django
// directly (forwarding cookies); the client uses the same-origin proxy.
export function useBuyerAuth() {
  const config = useRuntimeConfig()
  const csrfCookie = useCookie('csrftoken')

  function authUrl(path) {
    return import.meta.server
      ? `${config.apiBaseInternal}/auth/buyer${path}`
      : `/api/v1/auth/buyer${path}`
  }

  const { data, refresh } = useFetch(() => authUrl('/session'), {
    key: 'buyer-session',
    headers: { cookie: useRequestHeaders(['cookie']).cookie || '' },
  })

  const isAuthenticated = computed(() => Boolean(data.value?.authenticated))
  const account = computed(() => data.value?.account || null)
  const csrfToken = computed(() => data.value?.csrf_token || csrfCookie.value || '')

  async function post(path, body) {
    // Auth posts always happen in the browser: the CSRF cookie must live in
    // the browser jar, and an SSR-internal session fetch cannot set it. The
    // same-origin session call first refreshes both token and cookie.
    if (import.meta.server) {
      return null
    }
    const fresh = await $fetch(authUrl('/session'), { credentials: 'include' })
    const token = fresh?.csrf_token || csrfToken.value
    const response = await $fetch(authUrl(path), {
      method: 'POST',
      body,
      headers: { 'X-CSRFToken': token },
      credentials: 'include',
      ignoreResponseError: true,
    })
    await refresh()
    return response
  }

  async function sendVerificationCode(channel, target) {
    return post('/verification-codes', { channel, target, purpose: 'REGISTER' })
  }

  async function register(payload) {
    return post('/register', payload)
  }

  async function login(payload) {
    return post('/login', payload)
  }

  async function logout() {
    return post('/logout', {})
  }

  return {
    isAuthenticated,
    account,
    csrfToken,
    refresh,
    sendVerificationCode,
    register,
    login,
    logout,
  }
}
