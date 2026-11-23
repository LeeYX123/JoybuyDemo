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
  // 全局请求超时兜底（2026-11-23）：useFetch 默认会无限等待——后端宕机或
  // devProxy 卡死时页面会永久转圈。这里给所有 useFetch 一个默认 timeout，
  // 超时后由页面已有的 error 分支接管，用户看到"加载失败"而不是转圈。
  // 页面显式传 timeout 时仍以页面为准。
  experimental: {
    defaults: {
      useFetch: {
        timeout: 15_000,
      },
    },
  },
  nitro: {
    // 开发代理（仅 dev 生效；生产由 Nginx 处理）。
    //
    // 2026-11-23 事故：后端宕机/重启后，代理的 keep-alive 连接池会残留死连接，
    // 之后每个 /api 请求都无限挂起（页面永久转圈），只有重启 nuxt 才能恢复。
    // 因此这里显式关掉连接复用（agent: false = 每次请求新建连接）并加超时：
    // 后端不可用时快速失败而不是挂死，后端恢复后也无需重启 dev server。
    devProxy: {
      '/api': {
        target: 'http://127.0.0.1:8000/api',
        changeOrigin: true,
        agent: false,
        // 8s 内无响应就断开，避免用户长时间干等（本地接口正常 <200ms）。
        timeout: 8_000,
        proxyTimeout: 8_000,
      },
      // Django serves /media in development; Nginx takes over in production.
      '/media': {
        target: 'http://127.0.0.1:8000/media',
        changeOrigin: true,
        agent: false,
        timeout: 20_000,
        proxyTimeout: 20_000,
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
