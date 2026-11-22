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
  // 需求 12.2：开店申请状态随买家 session 一次带回（后端 _account_payload
  // 注入 merchant_application_status / merchant_id），头部入口不再单独发请求。
  const merchantApplicationStatus = computed(
    () => data.value?.account?.merchant_application_status || null,
  )

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

  // 迭代02：邮箱手动注册（免验证码：自填账号 + 密码即可注册成功）。
  async function registerEmail(email, password) {
    return post('/register/email', { email, password })
  }

  async function login(payload) {
    return post('/login', payload)
  }

  // 商家端「切换去商城」：兑换后端签发的一次性 handoff token。同源 POST，
  // CSRF 沿用 post() 的「先 GET session 取 csrftoken 再带 X-CSRFToken」约定；
  // 成功后 session cookie 由后端写在 storefront 自己的 host 上（host-only）。
  async function exchangeMerchantHandoff(token) {
    return post('/merchant-handoff', { token })
  }

  async function logout() {
    return post('/logout', {})
  }

  return {
    isAuthenticated,
    account,
    csrfToken,
    merchantApplicationStatus,
    refresh,
    sendVerificationCode,
    register,
    registerEmail,
    login,
    exchangeMerchantHandoff,
    logout,
  }
}
