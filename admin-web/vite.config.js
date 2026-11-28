import { readFile, stat } from 'node:fs/promises'
import { extname, join, normalize, resolve, sep } from 'node:path'
import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// 管理端页面里的图片来自业务数据，形如 /images/activity/pages/<id>/hero.webp——
// 这些文件由购物端仓库的静态目录提供（生产由前端构建产物 / Nginx 直接服务）。
// 从 admin-web/vite.config.js 出发实际路径是 ../storefront/public；
// 必须在前端 dev server 里本地托管，否则 5173 会把它当 SPA 路由回退成
// index.html（200 + text/html），表现为「所有活动卡片图片加载不出来」。
const STOREFRONT_PUBLIC = fileURLToPath(new URL('../storefront/public', import.meta.url))
const STATIC_PREFIXES = ['/images/', '/videos/', '/fonts/']

const MIME_TYPES = {
  '.webp': 'image/webp',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.avif': 'image/avif',
  '.ico': 'image/x-icon',
  '.mp4': 'video/mp4',
  '.webm': 'video/webm',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
}

function storefrontStaticPlugin() {
  return {
    name: 'joybuy-storefront-static',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const rawUrl = req.url || ''
        if (!STATIC_PREFIXES.some((prefix) => rawUrl.startsWith(prefix))) return next()
        const pathname = decodeURIComponent(rawUrl.split('?')[0].split('#')[0])
        // 防目录穿越：归一化后必须仍在 storefront/public 之内。
        const target = resolve(join(STOREFRONT_PUBLIC, normalize(pathname)))
        if (target !== STOREFRONT_PUBLIC && !target.startsWith(STOREFRONT_PUBLIC + sep)) {
          res.statusCode = 403
          res.end('Forbidden')
          return
        }
        try {
          const info = await stat(target)
          if (!info.isFile()) return next()
          const body = await readFile(target)
          res.setHeader(
            'Content-Type',
            MIME_TYPES[extname(target).toLowerCase()] || 'application/octet-stream',
          )
          res.setHeader('Content-Length', String(body.length))
          res.setHeader('Cache-Control', 'no-cache')
          res.end(body)
        } catch {
          // 静态资源缺失时直接 404：不能回退 SPA index.html（否则「图片坏了」
          // 会以 200 + text/html 的假成功出现，排查时极易误判）。
          res.statusCode = 404
          res.setHeader('Content-Type', 'text/plain; charset=utf-8')
          res.end('Not Found')
        }
      })
    },
  }
}

export default defineConfig({
  plugins: [vue(), storefrontStaticPlugin()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    // 允许读取同级 storefront/public（vite 默认只允许项目根）。
    fs: {
      allow: [fileURLToPath(new URL('..', import.meta.url))],
    },
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
    port: 5173,
  },
})
