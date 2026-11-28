import { computed } from 'vue'
import { refreshNuxtData, useFetch, useRequestHeaders, useRuntimeConfig } from '#imports'

import { formatDisplayPrice } from '../utils/display'

// Cart writes shared by the composable and lightweight callers (product
// cards): Django CSRF applies to cart writes, so refresh the browser-side
// token through the same-origin session endpoint first. The browser only —
// mutations never run during SSR.
async function writeCart(method, path, body) {
  const session = await $fetch('/api/v1/auth/buyer/session', { credentials: 'include' })
  const response = await $fetch(`/api/v1/cart${path}`, {
    method,
    body,
    headers: { 'X-CSRFToken': session?.csrf_token || '' },
    credentials: 'include',
    ignoreResponseError: true,
  })
  return response
}

function addItemBody(target, quantity) {
  // 加购入参二选一（2026-11-28）：详情页传 offer_public_id（字符串，原签名
  // 不变）；列表卡片【+】拿不到 offer，传 `{ spu_public_id }`，后端按当前
  // 市场解析成最低价 ACTIVE Offer 后走同一条加购逻辑。
  return target && typeof target === 'object'
    ? { quantity, ...target }
    : { offer_public_id: target, quantity }
}

// 只写不读的购物车动作（2026-11-28 卡片【+】用）：**不调用 useFetch**。
// 列表页每张卡都调 useCart() 会各自发起一次 key='cart' 的读请求，SSR 时
// 没有购物车 cookie 的每个子请求都会新建一个匿名购物车（实测列表页
// 一次渲染 +5 条 cart 行）；这里只写，写完统一刷新共享的 'cart' 数据，
// 头部角标照常更新。
export function useCartActions() {
  async function addItem(target, quantity = 1) {
    const response = await writeCart('POST', '/items', addItemBody(target, quantity))
    await refreshNuxtData('cart')
    return response
  }

  return { addItem }
}

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
    const response = await writeCart(method, path, body)
    await refresh()
    return response
  }

  async function addItem(target, quantity = 1) {
    return mutate('POST', '/items', addItemBody(target, quantity))
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
