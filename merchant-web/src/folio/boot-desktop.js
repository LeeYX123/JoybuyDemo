// ---------------------------------------------------------------------------
// folio/boot-desktop.js — 商家端桌面版（index.html）的唯一入口脚本。
//
// 与手机版 boot.js 同构（登录门 → 空态屏 → 选店 → bootEngine），差异点：
// 1. 打标 window.__FOLIO_DESKTOP__ = true：api.js 据此注入 base-1..3 +
//    merchant-desktop.js（不注入 base-4 / merchant-mobile.js 手机壳）；
// 2. 路由直接用 location.pathname（桌面 index.html 就是 SPA 根，vite dev /
//    nginx 都有 history fallback），不做 ?p= 映射，不做 <760/>780 换文档协议
//    （那是 mobile 侧职责）；
// 3. 登录屏 / 空态屏标记来源：最小复制自 src/folio/boot.js showLogin/showEmptyShop
//    （boot.js 60-97 行，文案改为桌面版口径；boot.js 本身一字未动，手机路径零影响）。
// ---------------------------------------------------------------------------
import './boot.css'
import { apiRequest, setCurrentShop } from '../lib/api.js'
import {
  bootEngine,
  loginRequest,
  loadShops,
  logoutRequest,
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
    '/login': 0,
    '/no-shop': 0,
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
// 登录屏 / 空态屏（复制自 boot.js 56-97 行；文案改桌面版口径）
// ---------------------------------------------------------------------------
function authScreenHtml(title, subtitle, inner) {
  return `<div class="folio-auth"><div class="folio-auth-card"><span class="folio-auth-mark">寰</span><h1>${title}</h1><p class="folio-auth-sub">${subtitle}</p>${inner}</div></div>`
}

function showLogin() {
  document.documentElement.dataset.folioGuest = ''
  const app = document.getElementById('app')
  app.innerHTML = authScreenHtml(
    '商家工作台',
    '寰球优选 · 商家端桌面版，请使用商家账号登录',
    `<form id="folioLoginForm"><label class="folio-field"><span>邮箱</span><input id="folioEmail" type="email" autocomplete="username" placeholder="请输入商家账号邮箱" required></label><label class="folio-field"><span>密码</span><input id="folioPassword" type="password" autocomplete="current-password" placeholder="请输入密码" required></label><p id="folioLoginError" class="folio-error" role="alert"></p><button type="submit" class="primary folio-submit">登录</button></form>`,
  )
  const form = document.getElementById('folioLoginForm')
  form.addEventListener('submit', async (event) => {
    event.preventDefault()
    const error = document.getElementById('folioLoginError')
    const button = form.querySelector('.folio-submit')
    error.textContent = ''
    button.disabled = true
    try {
      await loginRequest(
        document.getElementById('folioEmail').value.trim(),
        document.getElementById('folioPassword').value,
      )
      location.replace('/dashboard')
    } catch (err) {
      error.textContent = err.message || '登录失败，请稍后再试。'
      button.disabled = false
    }
  })
}

function showEmptyShop() {
  document.documentElement.dataset.folioGuest = ''
  const app = document.getElementById('app')
  app.innerHTML = authScreenHtml(
    '商家工作台',
    '',
    `<p class="folio-empty-text">该账号还没有绑定店铺</p><p class="folio-empty-hint">请联系平台客服完成店铺入驻与绑定后再登录。</p><button type="button" class="primary folio-submit" id="folioLogoutButton">退出登录</button>`,
  )
  document.getElementById('folioLogoutButton').addEventListener('click', async () => {
    await logoutRequest()
    location.replace('/login')
  })
}

// ---------------------------------------------------------------------------
// 主流程
// ---------------------------------------------------------------------------
async function main() {
  const entry = routeFromPath(location.pathname)

  // 1. 登录门。
  document.documentElement.dataset.folioBoot = 'pending'
  const session = await apiRequest('/admin/auth/session').catch(() => null)
  if (!session || !session.authenticated) {
    // 已登录访问 /login 才会走到这里之前被拦截；未登录统一渲染登录屏（含 /login）。
    showLogin()
    delete document.documentElement.dataset.folioBoot
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

  // 3. 地址条规范化：/login、未知路径、越界订单号都在引擎落位后统一还原成规范路径。
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
