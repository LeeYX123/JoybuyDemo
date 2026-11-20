import { computed, ref } from 'vue'

import { useBuyerAuth } from './useBuyerAuth'
import { useLocale } from './useLocale'
import { useUiToast } from './useUiToast'

// 购物端「申请店铺 / 商家中心」入口的唯一状态源。
//
// 需求 12.2（2026-11-19）：申请状态随买家 session 一次带回
// （GET /api/v1/auth/buyer/session 的 account.merchant_application_status，
// 后端 _account_payload 注入，SSR 首屏即正确），本组合式函数不再单独
// 请求 /api/v1/account/merchant-application。状态口径：
//   无申请 / REJECTED / PENDING -> 「申请店铺」 -> /account/apply-shop
//   APPROVED                    -> 「切换商家端」-> POST merchant-console-session
// 商家端是独立应用（merchant-web，5174），跳转地址由后端按当前请求主机
// 计算，前端不写死任何 host/port。
const ERROR_KEYS = {
  APPLICATION_NOT_APPROVED: 'merchantEntry.errorNotApproved',
  MERCHANT_ACCOUNT_MISSING: 'merchantEntry.errorMissing',
  MERCHANT_MEMBERSHIP_MISSING: 'merchantEntry.errorMissing',
  MERCHANT_ACCOUNT_DISABLED: 'merchantEntry.errorDisabled',
  BUYER_AUTH_REQUIRED: 'merchantEntry.errorSignIn',
}

export function useMerchantEntry() {
  const { isAuthenticated, merchantApplicationStatus, refresh: refreshSession } = useBuyerAuth()
  const { t } = useLocale()
  const { show } = useUiToast()
  const switching = ref(false)

  // 兼容旧签名：force 时刷新共享的买家 session（同一 key 只发一次请求，
  // 头部 / 账号侧栏 / 账号首页共用同一份派生状态）。
  async function loadStatus({ force = false } = {}) {
    if (!isAuthenticated.value) return merchantApplicationStatus.value
    if (!force) return merchantApplicationStatus.value
    try {
      await refreshSession()
    } catch {
      // 刷新失败时保持当前派生状态：入口降级为普通「申请店铺」链接。
    }
    return merchantApplicationStatus.value
  }

  const isConsoleEntry = computed(() => merchantApplicationStatus.value === 'APPROVED')

  const label = computed(() => {
    if (merchantApplicationStatus.value === 'PENDING') return t('merchantEntry.pending')
    if (merchantApplicationStatus.value === 'APPROVED') return t('merchantEntry.console')
    return t('merchantEntry.apply')
  })

  const description = computed(() => {
    if (merchantApplicationStatus.value === 'PENDING') return t('merchantEntry.pendingDesc')
    if (merchantApplicationStatus.value === 'APPROVED') return t('merchantEntry.consoleDesc')
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
    applicationStatus: merchantApplicationStatus,
    isConsoleEntry,
    label,
    description,
    linkTarget,
    switching,
    loadStatus,
    openMerchantConsole,
  }
}
