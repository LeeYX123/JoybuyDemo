import { cpSync, mkdirSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

const here = dirname(fileURLToPath(import.meta.url))

// api.js 在运行时按 /src/folio/*.js 注入 classic 引擎脚本（base-1..3 + 桌面/手机壳），
// 这些路径是字符串不是 import，rollup 不会打包它们；构建后必须原样拷进 dist，
// 否则 dist 里的 index.html / mobile.html 会在注入引擎时 404（dev 下由 vite 静态服务）。
function copyFolioEngineScripts() {
  return {
    apply: 'build',
    closeBundle() {
      const outDir = resolve(here, 'dist/src/folio')
      mkdirSync(outDir, { recursive: true })
      for (const name of [
        'base-1.js',
        'base-2.js',
        'base-3.js',
        'base-4.js',
        'merchant-desktop.js',
        'merchant-mobile.js',
      ]) {
        cpSync(join(here, 'src/folio', name), join(outDir, name))
      }
    },
  }
}

export default defineConfig({
  plugins: [vue(), copyFolioEngineScripts()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    rollupOptions: {
      // 多页入口：index.html = folio 静态稿桌面版（boot-desktop.js）；mobile.html = folio 静态稿手机版。
      input: {
        main: 'index.html',
        mobile: 'mobile.html',
      },
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5174,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      // 上传后的图片由后端 /media/ 前缀提供（生产由 Nginx 直接服务），
      // 开发环境必须代理过去，否则 <img src="/media/..."> 会 404。
      '/media': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: '127.0.0.1',
    port: 5174,
  },
})
