export default defineNuxtConfig({
  compatibilityDate: '2026-11-02',
  ssr: true,
  devtools: { enabled: false },
  css: ['~/assets/css/main.css'],
  runtimeConfig: {
    apiBaseInternal: process.env.NUXT_API_BASE_INTERNAL || 'http://127.0.0.1:8000/api/v1',
    public: {
      apiBase: process.env.NUXT_PUBLIC_API_BASE || '/api/v1',
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
