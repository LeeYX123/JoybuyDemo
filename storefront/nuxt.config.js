export default defineNuxtConfig({
  compatibilityDate: '2026-11-02',
  ssr: true,
  devtools: { enabled: false },
  css: ['~/assets/css/main.css'],
  runtimeConfig: {
    apiBaseInternal: process.env.NUXT_API_BASE_INTERNAL || 'http://127.0.0.1:8000/api/v1',
    public: {
      apiBase: process.env.NUXT_PUBLIC_API_BASE || '/api/v1',
      // Crisp 客服 Website ID（需求 11.2）：注册 crisp.chat 后获取，用环境
      // 变量注入；留空则完全不加载客服脚本、不报错。
      crispWebsiteId: process.env.NUXT_PUBLIC_CRISP_WEBSITE_ID || '',
      // 需求 21（批次 Y）：Crisp 原生挂件默认关闭，全站改用 SupportChatLauncher
      // 【客服】入口。需要回滚到 Crisp 原生圆形启动器时设
      // NUXT_PUBLIC_CRISP_WIDGET_ENABLED=true（后端消息镜像不受影响）。
      crispWidgetEnabled: process.env.NUXT_PUBLIC_CRISP_WIDGET_ENABLED === 'true',
      // 商家端跳转地址由后端 merchant-console-session 按当前请求主机返回
      // （生产用 MERCHANT_WEB_URL 覆盖），前端不再保存第二份 host 配置。
    },
  },
  nitro: {
    devProxy: {
      '/api': {
        target: 'http://127.0.0.1:8000/api',
        changeOrigin: true,
      },
      // Django serves /media in development; Nginx takes over in production.
      '/media': {
        target: 'http://127.0.0.1:8000/media',
        changeOrigin: true,
      },
    },
  },
  app: {
    head: {
      htmlAttrs: { lang: 'en-GB' },
      title: 'Joybuy',
      meta: [
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
        { name: 'robots', content: 'noindex, nofollow' },
        { name: 'color-scheme', content: 'light' },
      ],
    },
  },
})
