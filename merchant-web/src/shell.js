import { defineAsyncComponent, defineComponent, h, ref } from 'vue'

// --------------------------------------------------------------------------
// 商家端「双壳」检测：同一 Vite app（:5174）、同一路由表、同一会话，
// 按 主机名 / 视口宽度 决定渲染手机壳还是桌面壳。
//
// 规则（派单口径）：
// 1. 主机名以 m. 开头（如 m.localhost:5174）→ 永远手机壳，与宽度无关；
// 2. 127.0.0.1 / localhost → 宽度 ≥768 桌面壳、<768 自动手机壳；
// 3. 跨阈值实时切换：matchMedia 监听，无 reload、无路由跳转，当前路由不变只换壳；
// 4. 不做任何 host 重定向（cookie 是 host-only，m.localhost 与 127.0.0.1
//    登录态各自独立——已知限制，不通过 SESSION_COOKIE_DOMAIN 解决）。
// --------------------------------------------------------------------------

function isForcedMobileHost() {
  return typeof window !== 'undefined' && window.location.hostname.startsWith('m.')
}

function detectInitialMobile() {
  if (typeof window === 'undefined') return false
  if (isForcedMobileHost()) return true
  return window.matchMedia('(max-width: 767.98px)').matches
}

export const isMobileShell = ref(detectInitialMobile())

let narrowMql = null
if (typeof window !== 'undefined') {
  narrowMql = window.matchMedia('(max-width: 767.98px)')
  const syncFromViewport = () => {
    // m. 主机名强制手机壳：宽度变化不改判（短路保住强制分支）。
    isMobileShell.value = isForcedMobileHost() || narrowMql.matches
  }
  if (narrowMql.addEventListener) {
    narrowMql.addEventListener('change', syncFromViewport)
  } else if (narrowMql.addListener) {
    // 兼容旧 WebKit（Safari < 14）；防御性保留，现代 Chrome 走 addEventListener。
    narrowMql.addListener(syncFromViewport)
  }
  // resize 兜底：真机旋转/部分嵌入式 WebView 改视口不派发 matchMedia change；
  // 同步读 hostname 与 mql.matches，重复赋同值对响应式无副作用。
  window.addEventListener('resize', syncFromViewport)
}

export function useMobileShell() {
  return {
    isMobileShell,
    isForcedMobile: isForcedMobileHost(),
  }
}

// --------------------------------------------------------------------------
// 全局 toast（手机壳专用）：底部浮层 + aria-live 文案由 MobileShell 渲染，
// 手机视图直接 import showToast 使用；桌面壳不挂载浮层、不受影响。
// --------------------------------------------------------------------------

const toastText = ref('')
let toastTimer = null

export function useMobileToast() {
  return toastText
}

export function showToast(message) {
  if (toastTimer) clearTimeout(toastTimer)
  // 同步赋值：rAF 在后台/被遮挡标签里会被节流，不能作为 toast 的渲染前提。
  toastText.value = message
  toastTimer = setTimeout(() => {
    toastText.value = ''
  }, 2600)
}

// --------------------------------------------------------------------------
// 路由级双壳包装：桌面视图一行不改，路由表保持一份。
// 用 defineAsyncComponent 保持桌面/手机视图各自的懒加载 chunk；
// 返回值是同步包装组件，渲染时按 isMobileShell 选择分支。
// --------------------------------------------------------------------------

export function dualShell(desktopLoader, mobileLoader, name = 'DualShellRoute') {
  const Desktop = desktopLoader ? defineAsyncComponent(desktopLoader) : null
  const Mobile = mobileLoader ? defineAsyncComponent(mobileLoader) : null
  return defineComponent({
    name,
    setup() {
      const { isMobileShell: mobile } = useMobileShell()
      return () => (mobile.value ? h(Mobile) : h(Desktop))
    },
  })
}
