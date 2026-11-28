// 未登录访问 /account/* 一律重定向回登录页（用户口径 2026-11-28）：
// 不再渲染 .profile-signed-out 卡片（登录提示 + 「前往登录」按钮），而是
// 服务端/客户端导航阶段直接跳走，登录后可回到原目标。
//
// 挂在 global 中间件：SSR 与客户端 SPA 导航都生效。会话在 SSR 由
// buyer-session.server.js 插件渲染前已 await（首帧即正确），因此
// isAuthenticated 在中间件里就是可靠值，无需额外请求。
export default defineNuxtRouteMiddleware((to) => {
  if (!to.path.startsWith('/account')) return
  // 登录页本身不在 /account 前缀下，无需排除；语言页/订单页等全部受保护。
  const { isAuthenticated } = useBuyerAuth()
  if (isAuthenticated.value) return
  return navigateTo('/auth/login', { redirectCode: 302 })
})
