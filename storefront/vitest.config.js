import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  root: fileURLToPath(new URL('.', import.meta.url)),
  plugins: [
    // Root-absolute template asset URLs (e.g. /images/logo.png) point at the
    // Nuxt public dir, which vitest does not serve; skip the asset transform.
    vue({ template: { transformAssetUrls: false } }),
  ],
  resolve: {
    alias: {
      '#imports': fileURLToPath(new URL('./tests/nuxt-imports-stub.js', import.meta.url)),
    },
  },
  test: {
    environment: 'happy-dom',
    include: ['**/*.test.js'],
  },
})
