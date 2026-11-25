import { useBuyerAuth } from '../composables/useBuyerAuth'

// 2026-11-25 缺陷修复（桌面 /account 被渲染成 480px 手机卡片）：
// 买家会话此前是全站懒加载的——AppHeader 里第一次 useBuyerAuth() 发起
// /api/v1/auth/buyer/session 请求，但没有任何地方 await 它。SSR 可能在这条请求
// 返回之前就完成首帧渲染，于是 header 渲染出 Sign in、/account 走进 v-else 的
// .profile-signed-out 分支；而 Nuxt 随后仍把这批数据写进 payload（已登录），
// 客户端水合时登录态内容找不到对应 DOM，只能补进 SSR 留下的
// .profile-signed-out（max-width 30rem）里 → 内容区仅 ~414px、模块卡三列挤成
// 竖排中文。实测同一次请求的 SSR HTML 与 payload 登录态不一致（hydration
// mismatch），复现率约 1/3。
//
// 在 SSR 渲染前 await 同一份会话请求（ensureSession 只等已发起的那次请求，
// 不会新增请求），让 header 与所有页面在首帧就拿到正确登录态。
export default defineNuxtPlugin(async () => {
  const { ensureSession } = useBuyerAuth()
  await ensureSession()
})
