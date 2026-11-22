// Crisp 客服挂件（需求 11.2）。仅在配置了 NUXT_PUBLIC_CRISP_WEBSITE_ID 时
// 注入官方脚本（client.crisp.chat —— 用户指定的外部服务，属"不得引用第三方
// CDN"铁律的显式例外）；未配置时什么都不加载、零报错。
//
// 需求 21（批次 Y，2026-11-22）：全站改用自研【客服】入口
// （components/SupportChatLauncher.vue），Crisp 原生圆形启动器默认关闭。
// 开关 NUXT_PUBLIC_CRISP_WIDGET_ENABLED=true 可回滚到原生挂件（消息镜像不受
// 影响，后端仍照常把会话写进 Crisp Inbox）。
import { defineNuxtPlugin, useRuntimeConfig } from '#imports'

export default defineNuxtPlugin(() => {
  const config = useRuntimeConfig()
  if (!config.public.crispWidgetEnabled) return

  const websiteId = config.public.crispWebsiteId
  if (!websiteId) return

  window.$crisp = []
  window.CRISP_WEBSITE_ID = websiteId

  const script = document.createElement('script')
  script.src = `https://client.crisp.chat/l.js?website_id=${encodeURIComponent(websiteId)}`
  script.async = true
  document.head.appendChild(script)
})
