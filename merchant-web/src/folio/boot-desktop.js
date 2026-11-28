// ---------------------------------------------------------------------------
// folio/boot-desktop.js — 商家端桌面版（index.html）的唯一入口脚本。
//
// 与手机版 boot.js 同构（会话门 → 空态屏 → 选店 → bootEngine），差异点：
// 1. 打标 window.__FOLIO_DESKTOP__ = true：api.js 据此注入 base-1..3 +
//    merchant-desktop.js（不注入 base-4 / merchant-mobile.js 手机壳）；
// 2. 路由直接用 location.pathname（桌面 index.html 就是 SPA 根，vite dev /
//    nginx 都有 history fallback），不做 ?p= 映射，不做 <760/>780 换文档协议
//    （那是 mobile 侧职责）；
// 3. 无登录屏：商家端不再提供登录表单（入口唯一化到购物端【切换商家端】）。
//    未登录 → 重定向回商城；只有「已登录但无绑定店铺」的空态屏（视觉复制自
//    boot.js，按钮为返回商城）。
// ---------------------------------------------------------------------------
import './boot.css'
import { apiRequest, setCurrentShop } from '../lib/api.js'
import {
  bootEngine,
  loadShops,
  logoutRequest,
  storefrontUrl,
} from './api.js'

// api.js 的 bootEngine 在注入引擎前读取该标记，必须最先就位。
window.__FOLIO_DESKTOP__ = true

// 路径 → 静态稿 route id（映射集合与 boot.js routeFromPath 33-51 行一致）。
function routeFromPath(path) {
  const order = String(path || '').match(/^\/orders\/([^/]+)/)
  if (order) {
    let orderId = order[1]
    try { orderId = decodeURIComponent(orderId) } catch { /* keep raw */ }
    return { route: 4, orderId }
  }
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
  }
  return { route: map[path] === undefined ? 0 : map[path] }
}

// entry route → 规范地址（未知路径统一落 /dashboard，与 boot-desktop 桌面壳口径一致）。
function canonicalPath(entry) {
  if (entry.route === 4 && entry.orderId) return '/orders/' + encodeURIComponent(entry.orderId)
  const paths = {
    0: '/dashboard',
    1: '/store',
    2: '/catalog',
    3: '/orders',
    5: '/wallet',
    6: '/deposit',
    7: '/after-sales',
    8: '/activities',
    9: '/messages',
    10: '/notifications',
  }
  return paths[entry.route] || '/dashboard'
}

// ---------------------------------------------------------------------------
// 空态屏（已登录但无绑定店铺；视觉复制自 boot.js，按钮为返回商城）
// ---------------------------------------------------------------------------
function authScreenHtml(title, subtitle, inner) {
  return `<div class="folio-auth"><div class="folio-auth-card"><span class="folio-auth-mark">寰</span><h1>${title}</h1><p class="folio-auth-sub">${subtitle}</p>${inner}</div></div>`
}

function showEmptyShop() {
  document.documentElement.dataset.folioGuest = ''
  const app = document.getElementById('app')
  app.innerHTML = authScreenHtml(
    '商家工作台',
    '',
    `<p class="folio-empty-text">该账号还没有绑定店铺</p><p class="folio-empty-hint">请联系平台客服完成店铺入驻与绑定后再回来。</p><button type="button" class="primary folio-submit" id="folioBackToMallButton">返回商城</button>`,
  )
  document.getElementById('folioBackToMallButton').addEventListener('click', async () => {
    await logoutRequest()
    location.replace(storefrontUrl())
  })
}

// ---------------------------------------------------------------------------
// 主流程
// ---------------------------------------------------------------------------
async function main() {
  const entry = routeFromPath(location.pathname)

  // 1. 会话门：未登录（直链/书签/会话过期）不渲染任何登录表单，直接回商城。
  document.documentElement.dataset.folioBoot = 'pending'
  const session = await apiRequest('/admin/auth/session').catch(() => null)
  if (!session || !session.authenticated) {
    delete document.documentElement.dataset.folioBoot
    location.replace(storefrontUrl())
    return
  }

  const shops = await loadShops().catch(() => [])
  if (!shops.length) {
    showEmptyShop()
    delete document.documentElement.dataset.folioBoot
    return
  }

  // 2. 选店（记忆上次选择，键与手机版一致）。
  let remembered = ''
  try { remembered = window.localStorage.getItem('joybuy.merchant.shop') || '' } catch { /* ignore */ }
  const initialShop = shops.some((s) => s.id === remembered) ? remembered : shops[0].id
  setCurrentShop(initialShop)

  // 3. 地址条规范化：未知路径、越界订单号都在引擎落位后统一还原成规范路径。
  if (location.pathname !== canonicalPath(entry)) {
    history.replaceState(null, '', canonicalPath(entry))
  }

  // 4. 注入静态稿引擎（base-1..3 + merchant-desktop.js，见 api.js bootEngine 桌面分支）
  //    并按入口路径落位。
  await bootEngine(entry)

  // 引擎落位可能与入口路径不同（如 /orders/:id 深链的单子不存在 → 回订单列表），
  // merchant-desktop.js 注入完成后会挂 __FOLIO_DESKTOP_SYNC__，这里做最终对齐。
  if (typeof window.__FOLIO_DESKTOP_SYNC__ === 'function') window.__FOLIO_DESKTOP_SYNC__()
  delete document.documentElement.dataset.folioBoot
}

main().catch((error) => {
  console.error('[folio-desktop] 启动失败:', error)
  const app = document.getElementById('app')
  if (app) {
    const banner = document.createElement('div')
    banner.id = 'folioBootError'
    banner.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:9999;background:#fff0f1;color:#ad263c;font-size:12px;padding:10px 14px;white-space:pre-wrap'
    banner.textContent = '[folio-desktop] 启动失败: ' + String((error && error.stack) || error)
    document.body.appendChild(banner)
  }
  delete document.documentElement.dataset.folioBoot
})
