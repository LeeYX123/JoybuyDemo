import { computed } from 'vue'
import { useAsyncData, useCookie, useRequestHeaders, useRuntimeConfig, useState } from '#imports'

// Buyer session state backed by WP-05 cookie sessions. SSR fetches Django
// directly (forwarding cookies); the client uses the same-origin proxy.
//
// 2026-11-24 缺陷修复：整页只发一次 session 请求。此前每个 ProductCard 都通过
// useWishlist → useBuyerAuth 各自注册一次 useFetch({ key: 'buyer-session' })，而
// Nuxt 的默认 dedupe:'cancel' 会把先前的同名请求 abort 掉，频道页实测 24 次
// 请求 / 23 次 abort。现在第一次调用负责唯一一次 useAsyncData 拉取并把结果写进
// useState（随 SSR payload 一起水合），其余调用只读共享状态，不再注册请求。
const SESSION_KEY = 'buyer-session'
const SESSION_DATA_KEY = 'buyer-session-data'
const SESSION_STARTED_KEY = 'buyer-session-started'

export function useBuyerAuth() {
  const config = useRuntimeConfig()
  const csrfCookie = useCookie('csrftoken')
  // 共享的会话数据（服务端 → payload → 客户端水合；客户端刷新时原地更新）。
  const session = useState(SESSION_DATA_KEY, () => null)
  // useState 在单个请求/单个 SPA 生命周期内是共享的：只有第一个调用者发起
  // 请求，后续调用者（每个 ProductCard 各一次）直接读上面的共享状态。
  const started = useState(SESSION_STARTED_KEY, () => false)

  function authUrl(path) {
    return import.meta.server
      ? `${config.apiBaseInternal}/auth/buyer${path}`
      : `/api/v1/auth/buyer${path}`
  }

  // 只读一次：SSR 需要它把会话写进 payload（头部/心形首屏即为正确状态），
  // 客户端在 SPA 导航后走同一份共享状态，不再按页重复请求。
  const requestHeaders = { cookie: useRequestHeaders(['cookie']).cookie || '' }

  if (!started.value) {
    started.value = true
    useAsyncData(
      SESSION_KEY,
      async () => {
        const response = await $fetch(authUrl('/session'), {
          headers: requestHeaders,
          credentials: 'include',
          ignoreResponseError: true,
        })
        // 写共享状态（useAsyncData 的 handler 在 Nuxt 请求上下文内运行，
        // useState 可用；SSR 时该值随 payload 序列化到客户端）。
        session.value = response ?? null
        return response ?? null
      },
      { dedupe: 'defer' },
    )
  }

  // 登录/登出/开店申请等写操作之后刷新共享会话（仅浏览器侧调用）。
  async function refresh() {
    const response = await $fetch(authUrl('/session'), {
      headers: requestHeaders,
      credentials: 'include',
      ignoreResponseError: true,
    })
    session.value = response ?? null
    return response
  }

  const data = computed(() => session.value)

  const isAuthenticated = computed(() => Boolean(data.value?.authenticated))
  const account = computed(() => data.value?.account || null)
  const csrfToken = computed(() => data.value?.csrf_token || csrfCookie.value || '')
  // 需求 12.2：开店申请状态随买家 session 一次带回（后端 _account_payload
  // 注入 merchant_application_status / merchant_id），头部入口不再单独发请求。
  const merchantApplicationStatus = computed(
    () => data.value?.account?.merchant_application_status || null,
  )
  // 需求 19.3-4：与商家沟通的白名单标记随买家 session 下发，商城端据此决定
  // 是否渲染【联系商家】入口（服务端仍会 403 兜底）。
  const purchaseWhitelisted = computed(() => Boolean(data.value?.account?.purchase_whitelisted))

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
    purchaseWhitelisted,
    refresh,
    sendVerificationCode,
    register,
    registerEmail,
    login,
    exchangeMerchantHandoff,
    logout,
  }
}
