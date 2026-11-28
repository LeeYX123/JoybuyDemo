import { computed, ref } from 'vue'

import { ApiError, apiRequest, merchantWrite, setCurrentShop } from '@/lib/api'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

const LOGIN_MESSAGES = {
  INVALID_STAFF_CREDENTIALS: '邮箱或密码不正确。',
  STAFF_ACCOUNT_DISABLED: '该账号已被停用。',
  STAFF_LOGIN_RATE_LIMITED: '尝试次数过多，请稍后再试。',
}

// 商家端会话：复用平台员工登录（/admin/auth/*），再用 /merchant/shops
// 解析出可操作的店铺。店铺上下文始终显式传给后端，不做隐式猜测。
const session = ref({ authenticated: false, staff: null, csrf_token: '' })
const shops = ref([])
const activeShopId = ref('')
const loaded = ref(false)

export function useMerchantSession() {
  const staff = computed(() => session.value.staff)
  const isAuthenticated = computed(() => session.value.authenticated)
  const activeShop = computed(
    () => shops.value.find((shop) => shop.id === activeShopId.value) || null,
  )
  const permissions = computed(() => new Set(activeShop.value?.permissions || []))

  function applyShop(id) {
    activeShopId.value = id || ''
    setCurrentShop(activeShopId.value)
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('joybuy.merchant.shop', activeShopId.value)
    }
  }

  async function loadShops() {
    const payload = await apiRequest('/merchant/shops')
    shops.value = payload.items || []
    if (!shops.value.length) {
      applyShop('')
      return shops.value
    }
    const remembered =
      typeof window !== 'undefined' ? window.localStorage.getItem('joybuy.merchant.shop') : ''
    const exists = shops.value.some((shop) => shop.id === remembered)
    applyShop(exists ? remembered : shops.value[0].id)
    return shops.value
  }

  async function loadSession() {
    try {
      const payload = await apiRequest('/admin/auth/session')
      session.value = payload
      if (payload.authenticated) await loadShops()
    } catch {
      session.value = { authenticated: false, staff: null, csrf_token: '' }
      shops.value = []
      applyShop('')
    }
    loaded.value = true
    return session.value
  }

  async function login(email, password) {
    // 登录接口不依赖店铺上下文，直接用原始请求（先取 CSRF，再带 token 提交）。
    const fresh = await apiRequest('/admin/auth/session')
    const response = await fetch(`${API_BASE_URL}/admin/auth/login`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': fresh.csrf_token || '',
      },
      body: JSON.stringify({ email, password }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok) {
      const code = payload?.error?.code || 'API_ERROR'
      const message = LOGIN_MESSAGES[code] || payload?.error?.message || '登录失败，请稍后再试。'
      throw new ApiError(message, { status: response.status, code })
    }
    await loadSession()
    return session.value
  }

  async function logout() {
    try {
      await merchantWrite('/admin/auth/logout', {}, 'POST')
    } finally {
      session.value = { authenticated: false, staff: null, csrf_token: '' }
      shops.value = []
      applyShop('')
    }
  }

  function can(permission) {
    return permissions.value.has(permission)
  }

  function switchShop(id) {
    applyShop(id)
  }

  return {
    session,
    staff,
    shops,
    activeShop,
    activeShopId,
    isAuthenticated,
    loaded,
    permissions,
    loadSession,
    loadShops,
    login,
    logout,
    can,
    switchShop,
  }
}
