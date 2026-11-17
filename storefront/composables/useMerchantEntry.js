import { computed, ref } from 'vue'

import { useBuyerAuth } from './useBuyerAuth'
import { useLocale } from './useLocale'
import { useUiToast } from './useUiToast'

// 购物端「申请店铺 / 商家中心」入口的唯一状态源。
//
// 状态来自 GET /api/v1/account/merchant-application：
//   无申请 / REJECTED -> 「申请店铺」       -> /account/apply-shop
//   PENDING           -> 「申请审核中」     -> /account/apply-shop（看进度）
//   APPROVED          -> 「进入商家中心」   -> POST merchant-console-session
// 商家端是独立应用（merchant-web，5174），跳转地址由后端按当前请求主机
// 计算，前端不写死任何 host/port。
const ERROR_KEYS = {
  APPLICATION_NOT_APPROVED: 'merchantEntry.errorNotApproved',
  MERCHANT_ACCOUNT_MISSING: 'merchantEntry.errorMissing',
  MERCHANT_MEMBERSHIP_MISSING: 'merchantEntry.errorMissing',
  MERCHANT_ACCOUNT_DISABLED: 'merchantEntry.errorDisabled',
  BUYER_AUTH_REQUIRED: 'merchantEntry.errorSignIn',
}

// Module-level cache so the header, account hub and sidebar share one fetch.
const applicationStatus = ref(null)
let loaded = false
let inFlight = null

export function useMerchantEntry() {
  const { isAuthenticated } = useBuyerAuth()
  const { t } = useLocale()
  const { show } = useUiToast()
  const switching = ref(false)

  async function loadStatus({ force = false } = {}) {
    if (!isAuthenticated.value) {
      applicationStatus.value = null
      loaded = false
      return null
    }
    if (!force && loaded) return applicationStatus.value
    if (inFlight) return inFlight

    inFlight = $fetch('/api/v1/account/merchant-application', { credentials: 'include' })
      .then((data) => {
        applicationStatus.value = data?.application?.status || null
        loaded = true
        return applicationStatus.value
      })
      .catch(() => {
        // 接口不可用时降级为普通「申请店铺」入口，不阻塞账号页。
        applicationStatus.value = null
        loaded = false
        return null
      })
      .finally(() => {
        inFlight = null
      })
    return inFlight
  }

  const isConsoleEntry = computed(() => applicationStatus.value === 'APPROVED')

  const label = computed(() => {
    if (applicationStatus.value === 'PENDING') return t('merchantEntry.pending')
    if (applicationStatus.value === 'APPROVED') return t('merchantEntry.console')
    return t('merchantEntry.apply')
  })

  const description = computed(() => {
    if (applicationStatus.value === 'PENDING') return t('merchantEntry.pendingDesc')
    if (applicationStatus.value === 'APPROVED') return t('merchantEntry.consoleDesc')
    return t('merchantEntry.applyDesc')
  })

  // null = 需要先换商家端会话，由 openMerchantConsole() 处理。
  const linkTarget = computed(() => (isConsoleEntry.value ? null : '/account/apply-shop'))

  async function openMerchantConsole() {
    if (!isAuthenticated.value) {
      show(t('merchantEntry.errorSignIn'), { type: 'error' })
      return false
    }
    if (switching.value) return false
    switching.value = true
    try {
      // 与 useBuyerAuth 一致：先从会话端点拿 csrftoken，再带 X-CSRFToken 提交。
      const fresh = await $fetch('/api/v1/auth/buyer/session', { credentials: 'include' })
      const response = await $fetch('/api/v1/account/merchant-console-session', {
        method: 'POST',
        headers: { 'X-CSRFToken': fresh?.csrf_token || '' },
        credentials: 'include',
        ignoreResponseError: true,
      })
      if (response?.error || !response?.url) {
        const key = ERROR_KEYS[response?.error?.code] || 'merchantEntry.errorGeneric'
        show(t(key), { type: 'error' })
        return false
      }
      window.location.assign(response.url)
      return true
    } catch {
      show(t('merchantEntry.errorGeneric'), { type: 'error' })
      return false
    } finally {
      switching.value = false
    }
  }

  return {
    applicationStatus,
    isConsoleEntry,
    label,
    description,
    linkTarget,
    switching,
    loadStatus,
    openMerchantConsole,
  }
}
