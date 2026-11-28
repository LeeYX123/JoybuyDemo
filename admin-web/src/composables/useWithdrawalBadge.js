import { onBeforeUnmount, onMounted, reactive } from 'vue'

import { apiRequest } from '@/lib/api'

// 【资金审核】待审计数（2026-11-28 用户要求：商家一申请就 +1，审核了就减少）。
//
// 数据源是轻量 COUNT 端点 /finance/withdrawals/counts（只两条 COUNT，不取明细）：
// - 模块级单例状态，侧边导航徽标与资金审核页共用，避免各自请求；
// - 刷新时机：应用启动、路由切换（由调用方触发）、审核/打回/转账动作成功后；
// - 轮询：45s 一次，且仅在页面可见（document.hidden 跳过），页面重新可见时立即补一次。
const POLL_MS = 45000

const badge = reactive({
  pending: 0,
  transferring: 0,
  loaded: false,
})

let inFlight = null
let timer = null

export async function refreshWithdrawalBadge() {
  if (inFlight) return inFlight
  inFlight = apiRequest('/finance/withdrawals/counts')
    .then((payload) => {
      badge.pending = Number(payload?.pending) || 0
      badge.transferring = Number(payload?.transferring) || 0
      badge.loaded = true
      return badge
    })
    .catch(() => {
      // 无权限 / 网络失败时静默（徽标不显示错误，避免污染导航）。
      return badge
    })
    .finally(() => {
      inFlight = null
    })
  return inFlight
}

function tick() {
  if (typeof document !== 'undefined' && document.hidden) return
  refreshWithdrawalBadge()
}

function onVisibilityChange() {
  if (!document.hidden) refreshWithdrawalBadge()
}

// 在侧边导航（常驻组件）里调用一次，负责全局轮询生命周期。
export function useWithdrawalBadgePolling() {
  onMounted(() => {
    refreshWithdrawalBadge()
    timer = setInterval(tick, POLL_MS)
    document.addEventListener('visibilitychange', onVisibilityChange)
  })
  onBeforeUnmount(() => {
    if (timer) clearInterval(timer)
    timer = null
    document.removeEventListener('visibilitychange', onVisibilityChange)
  })
}

export function useWithdrawalBadge() {
  return { badge, refreshWithdrawalBadge }
}
