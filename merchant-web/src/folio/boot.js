// ---------------------------------------------------------------------------
// folio/boot.js — mobile.html 的唯一入口脚本。
//
// 职责：
// 1. 桌面↔手机切换协议：非 m. 主机且视口 >780 → 弹回桌面文档（index.html），
//    带 250ms 防抖滞回；入口路径 ?p= 映射到静态稿 route 并还原干净地址。
// 2. 会话门：先 /admin/auth/session —— 未登录直接回商城（商家端不提供登录
//    表单，入口唯一化到购物端【切换商家端】）；已登录但无绑定店铺渲染空态屏
//    （按钮=返回商城）；通过后才拉数据、按原顺序注入 base-1..4.js +
//    merchant-mobile.js（静态稿引擎），再由 api.js 接数据。
// ---------------------------------------------------------------------------
import './boot.css'
import { apiRequest, setCurrentShop } from '../lib/api.js'
import {
  bootEngine,
  loadShops,
  logoutRequest,
  storefrontUrl,
} from './api.js'

const MOBILE_HOST = typeof location !== 'undefined' && location.hostname.startsWith('m.')

function safePath(raw) {
  try {
    const url = new URL(raw, location.origin)
    if (url.origin !== location.origin) return '/'
    return url.pathname + url.search
  } catch {
    return '/'
  }
}

// 入口路径（?p=）→ 静态稿 route id。
function routeFromPath(path) {
  const order = String(path || '').match(/^\/orders\/([^/]+)/)
  if (order) return { route: 4, orderId: order[1] }
  const map = {
    '/': 0,
    '/dashboard': 0,
    '/store': 1,
    '/catalog': 2,
    '/orders': 3,
    '/wallet': 5,
    '/deposit': 6,
    '/after-sales': 7,
    '/activities': 8,
    '/messages': 9,
    '/notifications': 10,
    '/login': 0,
  }
  return { route: map[path] === undefined ? 0 : map[path] }
}

// ---------------------------------------------------------------------------
// 空态屏（folio 视觉，颜色取 :root[data-design=studio] tokens）；登录屏已移除
// ---------------------------------------------------------------------------
function authScreenHtml(title, subtitle, inner) {
  return `<div class="folio-auth"><div class="folio-auth-card"><span class="folio-auth-mark">寰</span><h1>${title}</h1><p class="folio-auth-sub">${subtitle}</p>${inner}</div></div>`
}

function showEmptyShop(logout) {
  document.documentElement.dataset.folioGuest = ''
  const app = document.getElementById('app')
  app.innerHTML = authScreenHtml(
    '商家工作台',
    '',
    `<p class="folio-empty-text">该账号还没有绑定店铺</p><p class="folio-empty-hint">请联系平台客服完成店铺入驻与绑定后再回来。</p><button type="button" class="primary folio-submit" id="folioBackToMallButton">返回商城</button>`,
  )
  document.getElementById('folioBackToMallButton').addEventListener('click', logout)
}

// ---------------------------------------------------------------------------
// 主流程
// ---------------------------------------------------------------------------
async function main() {
  const params = new URLSearchParams(location.search)
  const entryPath = safePath(params.get('p') || '/')

  // 1. 回桌面协议：非 m. 主机且足够宽 → 换文档回桌面（滞回 780）。
  if (!MOBILE_HOST && window.innerWidth > 780) {
    location.replace(entryPath || '/')
    return
  }
  // 地址条还原成干净路径（刷新时经 Vite SPA fallback → index.html → 再回手机）。
  if (params.get('p')) {
    history.replaceState(null, '', entryPath)
  }

  // 2. 滞回监听：拉宽过阈值回桌面（m. 主机永不回）。
  let resizeTimer = null
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer)
    resizeTimer = setTimeout(() => {
      if (!location.hostname.startsWith('m.') && window.innerWidth > 780) {
        location.replace(location.pathname + location.search)
      }
    }, 250)
  })

  // 3. 会话门：未登录（直链/书签/会话过期）不渲染任何登录表单，直接回商城。
  document.documentElement.dataset.folioBoot = 'pending'
  const session = await apiRequest('/admin/auth/session').catch(() => null)
  if (!session || !session.authenticated) {
    delete document.documentElement.dataset.folioBoot
    location.replace(storefrontUrl())
    return
  }

  const shops = await loadShops().catch(() => [])
  if (!shops.length) {
    showEmptyShop(async () => {
      await logoutRequest()
      location.replace(storefrontUrl())
    })
    delete document.documentElement.dataset.folioBoot
    return
  }

  // 4. 选店（记忆上次选择）→ 拉数 → 注入静态稿引擎 → 接数据。
  let remembered = ''
  try { remembered = window.localStorage.getItem('joybuy.merchant.shop') || '' } catch { /* ignore */ }
  const initialShop = shops.some((s) => s.id === remembered) ? remembered : shops[0].id
  setCurrentShop(initialShop)

  await bootEngine(routeFromPath(entryPath))
  delete document.documentElement.dataset.folioBoot
}

main().catch((error) => {
  console.error('[folio] 启动失败:', error)
  const app = document.getElementById('app')
  if (app) {
    const banner = document.createElement('div')
    banner.id = 'folioBootError'
    banner.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:9999;background:#fff0f1;color:#ad263c;font-size:12px;padding:10px 14px;white-space:pre-wrap'
    banner.textContent = '[folio] 启动失败: ' + String((error && error.stack) || error)
    document.body.appendChild(banner)
  }
  delete document.documentElement.dataset.folioBoot
})
