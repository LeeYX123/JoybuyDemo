// Crisp 客服挂件（需求 11.2）。仅在配置了 NUXT_PUBLIC_CRISP_WEBSITE_ID 时
// 注入官方脚本（client.crisp.chat —— 用户指定的外部服务，属"不得引用第三方
// CDN"铁律的显式例外）；未配置时什么都不加载、零报错。启动器使用 Crisp
// 自带的右下角聊天按钮，不自制 UI。
import { defineNuxtPlugin, useRuntimeConfig } from '#imports'

export default defineNuxtPlugin(() => {
  const websiteId = useRuntimeConfig().public.crispWebsiteId
  if (!websiteId) return

  window.$crisp = []
  window.CRISP_WEBSITE_ID = websiteId

  const script = document.createElement('script')
  script.src = `https://client.crisp.chat/l.js?website_id=${encodeURIComponent(websiteId)}`
  script.async = true
  document.head.appendChild(script)
})
