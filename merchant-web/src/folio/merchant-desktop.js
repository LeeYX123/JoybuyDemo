/* eslint-disable no-undef */
// ---------------------------------------------------------------------------
// folio/merchant-desktop.js — 商家端桌面版壳（classic script，与 base-1..3.js
// 共享同一全局词法环境：go/render/current/orders/shopProfile 等均由 base 注入）。
//
// 职责（对应静态稿桌面文档，不注入手机壳 base-4 / merchant-mobile.js）：
// 1. header topright 接线到静态稿「最终覆盖态」：平台通知 go(10) / 联系客服
//    support() / 店铺头像+店名 / 切换回商城（.web-storefront-switch → 真实
//    POST /merchant/switch-to-mall，照抄 merchant-mobile.js 256-275 行实现）；
//    账号区加轻量下拉（编辑店铺资料 / 退出登录 → POST /admin/auth/logout → 回商城）；
//    中文/EN 与手机版同口径：只写 localStorage joybuy.merchant.language。
// 2. 路由同步：go(i) 包装 → history.pushState 真实路径；popstate → 按路径回跳；
//    /orders/:id 深链由 __JOYPLAY_ACTIONS__.openOrder（api.js 桌面分支）落位；
//    未知路径 → /dashboard。路径集合沿用 boot.js 33-51 行（旧 Vue 路由书签不断）。
// 3. 多店切换：shops.length>1 时 topright 出现 select，行为与手机版相同。
// ---------------------------------------------------------------------------
(() => {
  // 与 merchant-mobile.js 相同的守卫口径：桌面标记未置（误注入）或平台演示面板时不接管。
  if (window.__FOLIO_DESKTOP__ !== true || location.hash === '#platform-admin') return

  const topright = document.querySelector('.topright')
  const app = document.getElementById('app')
  const overlay = document.getElementById('overlay')

  // --- 语言偏好（与手机版同键同口径：仅持久化，静态稿没有 EN 文案） ---
  const LANGUAGE_KEY = 'joybuy.merchant.language'
  let selectedLanguage = '简体中文'
  try {
    const saved = window.localStorage.getItem(LANGUAGE_KEY)
    if (saved === '简体中文' || saved === 'English') selectedLanguage = saved
  } catch { /* ignore */ }

  function setLanguage(option) {
    selectedLanguage = option
    try { window.localStorage.setItem(LANGUAGE_KEY, option) } catch { /* ignore */ }
    paintTopright()
    toast(option === 'English' ? '已选择 English（界面文案暂未翻译）' : '已切换为简体中文')
  }

  // --- 切换回商城（POST /merchant/switch-to-mall → redirect_url），照抄手机版 ---
  async function switchToMall() {
    const button = topright.querySelector('.web-storefront-switch')
    if (button && button.disabled) return
    const actions = window.__JOYPLAY_ACTIONS__
    if (!actions || !actions.switchToMall) { toast('商城地址未配置'); return }
    if (button) {
      button.disabled = true
      button.setAttribute('aria-busy', 'true')
    }
    try {
      await actions.switchToMall()
    } catch (error) {
      toast((error && error.message) || '切换失败，请稍后重试')
    } finally {
      if (button) {
        button.disabled = false
        button.removeAttribute('aria-busy')
      }
    }
  }

  // --- topright：静态稿最终覆盖态 + 桌面接线件（每次 render 后重绘） ---
  function paintTopright() {
    if (!topright) return
    const name = String(shopProfile.name || '')
    const shops = window.__JOYPLAY_SHOPS__ || []
    const shopSelect = shops.length > 1
      ? `<select class="folio-shop-switch" aria-label="切换店铺">${shops.map((s) =>
        `<option value="${esc(s.id)}"${s.id === window.__JOYPLAY_SHOP_ID__ ? ' selected' : ''}>${esc(s.name)}</option>`).join('')}</select>`
      : ''
    const langLabel = selectedLanguage === 'English' ? 'EN' : '中文'
    const chosen = ' style="color:var(--red);font-weight:650"'
    topright.innerHTML =
      '<button onclick="go(10)">♧ 平台通知 <span class="red">●</span></button>' +
      '<button onclick="support()">♧ 联系客服</button>' +
      '<span style="color:#e2e5e9">│</span>' +
      `<span class="folio-shell-menu"><button type="button" class="folio-shell-trigger" aria-haspopup="true" aria-expanded="false">${profileAvatar('avatar')}<span>账号</span><span style="color:#9aa0ab">⌄</span></button>` +
      `<span class="folio-shell-panel"><span class="folio-shell-info">寰球优选 · 商家工作空间<br>商家编号 ${esc(immutableShopId || '—')}</span>` +
      '<button type="button" data-folio-action="edit-profile">编辑店铺资料</button>' +
      '<button type="button" data-folio-action="logout">退出登录</button></span></span>' +
      `<span class="topright-shop-name" title="${esc(name)}">${esc(name)}</span>` +
      shopSelect +
      `<span class="folio-shell-menu"><button type="button" class="folio-shell-trigger" aria-haspopup="true" aria-expanded="false"><span>${langLabel}</span><span style="color:#9aa0ab">⌄</span></button>` +
      '<span class="folio-shell-panel">' +
      `<button type="button" data-folio-action="language" data-language="简体中文"${selectedLanguage === '简体中文' ? chosen : ''}>简体中文</button>` +
      `<button type="button" data-folio-action="language" data-language="English"${selectedLanguage === 'English' ? chosen : ''}>English</button>` +
      '</span></span>' +
      '<button type="button" class="web-storefront-switch">切换回商城</button>'
  }

  function closeMenus() {
    for (const menu of topright.querySelectorAll('.folio-shell-menu.open')) menu.classList.remove('open')
  }

  if (topright) {
    topright.addEventListener('click', (event) => {
      const menu = event.target.closest('.folio-shell-menu')
      const trigger = event.target.closest('.folio-shell-trigger')
      if (menu && trigger) {
        const wasOpen = menu.classList.contains('open')
        closeMenus()
        if (!wasOpen) {
          menu.classList.add('open')
          trigger.setAttribute('aria-expanded', 'true')
        }
        return
      }
      const item = event.target.closest('[data-folio-action]')
      if (item) {
        const kind = item.dataset.folioAction
        closeMenus()
        if (kind === 'edit-profile') {
          editShopProfile()
        } else if (kind === 'logout') {
          const actions = window.__JOYPLAY_ACTIONS__
          if (actions && actions.logout) actions.logout()
        } else if (kind === 'language') {
          setLanguage(item.dataset.language)
        }
        return
      }
      if (event.target.closest('.web-storefront-switch')) {
        switchToMall()
        return
      }
      closeMenus()
    })
    document.addEventListener('click', (event) => {
      if (!event.target.closest('.topright')) closeMenus()
    })
    // 多店切换（行为同手机版 previewStorefrontTools 的 select）
    topright.addEventListener('change', (event) => {
      if (!event.target.matches('select.folio-shop-switch')) return
      const actions = window.__JOYPLAY_ACTIONS__
      if (actions && actions.switchShop) actions.switchShop(event.target.value)
    })
  }

  // --- 路由同步：真实 pathname（路径集合 = boot.js routeFromPath 33-51 行） ---
  const ROUTE_PATHS = {
    0: '/dashboard', 1: '/store', 2: '/catalog', 3: '/orders',
    5: '/wallet', 6: '/deposit', 7: '/after-sales', 8: '/activities',
    9: '/messages', 10: '/notifications',
  }

  function pathForRoute(route) {
    if (route === 4) {
      const order = orders[selected]
      return order ? '/orders/' + encodeURIComponent(order[0]) : '/orders'
    }
    return ROUTE_PATHS[route] || '/dashboard'
  }

  function currentPath() {
    return pathForRoute(current)
  }

  function normalizeUrl() {
    const want = currentPath()
    if (location.pathname !== want) {
      try { history.replaceState({ folioDesktop: true }, '', want) } catch { /* ignore */ }
    }
  }

  // boot-desktop.js 在 bootEngine 之后调用，把引擎实际落位回写地址条。
  window.__FOLIO_DESKTOP_SYNC__ = normalizeUrl

  const baseGo = go
  go = function (route) {
    baseGo(route)
    const want = currentPath()
    if (location.pathname !== want) {
      try { history.pushState({ folioDesktop: true }, '', want) } catch { /* ignore */ }
    }
  }

  function routeFromPath(path) {
    const order = String(path || '').match(/^\/orders\/([^/]+)/)
    if (order) {
      let orderId = order[1]
      try { orderId = decodeURIComponent(orderId) } catch { /* keep raw */ }
      return { route: 4, orderId }
    }
    const map = {
      '/': 0, '/dashboard': 0, '/store': 1, '/catalog': 2, '/orders': 3,
      '/wallet': 5, '/deposit': 6, '/after-sales': 7, '/activities': 8,
      '/messages': 9, '/notifications': 10, '/login': 0, '/no-shop': 0,
    }
    return { route: map[path] === undefined ? 0 : map[path] }
  }

  function navigatePath(pathname) {
    if (overlay && overlay.firstElementChild) closeModal()
    baseGo(routeFromPath(pathname).route)
    normalizeUrl()
  }

  window.addEventListener('popstate', () => {
    const order = String(location.pathname).match(/^\/orders\/([^/]+)/)
    if (order) {
      let orderId = order[1]
      try { orderId = decodeURIComponent(orderId) } catch { /* keep raw */ }
      const actions = window.__JOYPLAY_ACTIONS__
      if (actions && actions.openOrder) {
        // 异步落位：找不到该单时内部回 go(3)（wrapped → 地址条同步为 /orders）。
        actions.openOrder(orderId)
        return
      }
    }
    navigatePath(location.pathname)
  })

  // 切店后 api.js switchShop 会把 current 归零并 render（不走 go 包装），这里补地址同步。
  const shellActions = window.__JOYPLAY_ACTIONS__
  if (shellActions && typeof shellActions.switchShop === 'function') {
    const prevSwitchShop = shellActions.switchShop
    shellActions.switchShop = async (id) => {
      await prevSwitchShop(id)
      normalizeUrl()
    }
  }

  // --- render 包装：基础渲染链（含 base-3 自己的 topright 重绘）之后覆盖为最终接线态 ---
  const baseRender = render
  render = function () {
    baseRender()
    paintTopright()
  }

  // app/overlay 的常驻引用保留给未来扩展；当前无额外 DOM 手术（桌面即静态稿原生布局）。
  void app
  void overlay
})()
