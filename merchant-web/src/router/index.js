import { createRouter, createWebHistory } from 'vue-router'

import { useMerchantSession } from '@/composables/useMerchantSession'
import { dualShell, isMobileShell } from '@/shell'

// 商家端落地的第一个有权限模块（M01 经营看板 → 店铺管理 → 商品上架…）。
// 桌面壳沿用；手机壳的落点是首页宫格（'/'，见下方 beforeEach 的双壳分支）。
const LANDING = [
  { path: '/dashboard', permission: 'merchant.dashboard.view' },
  { path: '/store', permission: 'merchant.store.manage' },
  { path: '/orders', permission: 'merchant.orders.manage' },
  { path: '/catalog', permission: 'merchant.listings.manage' },
  { path: '/after-sales', permission: 'merchant.aftersales.manage' },
  { path: '/messages', permission: 'merchant.messages.use' },
]

// 路由级双壳包装：同一份路由表，桌面视图一行不改，手机视图在 src/mobile/。
const PlaceholderView = () => import('@/views/PlaceholderView.vue')

const router = createRouter({
  // 必须显式传 BASE_URL：createWebHistory() 不会自动跟随 vite --base，
  // 否则生产以非根 base 构建时路由会生成裸路径，刷新/守卫重定向会 404。
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: dualShell(
        () => import('@/views/LoginView.vue'),
        () => import('@/mobile/MobileLoginView.vue'),
        'LoginShellRoute',
      ),
      meta: { title: '登录', public: true },
    },
    {
      path: '/',
      // 根布局也是双壳：RootShell 按 isMobileShell 渲染 MobileShell 或 MerchantLayout。
      component: () => import('@/layouts/RootShell.vue'),
      children: [
        {
          path: '',
          name: 'home',
          // 落点由全局 beforeEach 在会话/店铺加载完成后决定（见下方
          // `to.name === 'home'` 分支）。这里不能用 redirect：redirect 在
          // beforeEach 之前执行，冷启动会因权限未加载而误判成 /no-shop。
          // 桌面壳该路由始终被重定向走（PlaceholderView 只是兜底）；
          // 手机壳的 '/' 是首页宫格（folio 核心），守卫放行。
          component: dualShell(
            PlaceholderView,
            () => import('@/mobile/MobileHomeView.vue'),
            'HomeShellRoute',
          ),
        },
        {
          path: 'dashboard',
          name: 'dashboard',
          // folio 把经营看板并进首页宫格：手机壳的 /dashboard 复用同一视图。
          component: dualShell(
            () => import('@/views/DashboardView.vue'),
            () => import('@/mobile/MobileHomeView.vue'),
            'DashboardShellRoute',
          ),
          meta: { title: '经营看板', permission: 'merchant.dashboard.view' },
        },
        {
          path: 'store',
          name: 'store',
          component: dualShell(
            () => import('@/views/StoreView.vue'),
            () => import('@/mobile/MobileStoreView.vue'),
            'StoreShellRoute',
          ),
          meta: { title: '店铺管理', permission: 'merchant.store.manage' },
        },
        {
          path: 'catalog',
          name: 'catalog',
          component: dualShell(
            () => import('@/views/CatalogueView.vue'),
            () => import('@/mobile/MobileCatalogueView.vue'),
            'CatalogueShellRoute',
          ),
          meta: { title: '商品上架中心', permission: 'merchant.listings.manage' },
        },
        {
          path: 'orders',
          name: 'orders',
          component: dualShell(
            () => import('@/views/OrdersView.vue'),
            () => import('@/mobile/MobileOrdersView.vue'),
            'OrdersShellRoute',
          ),
          meta: { title: '订单管理', permission: 'merchant.orders.manage' },
        },
        {
          path: 'orders/:id',
          name: 'order-detail',
          // 手机壳的独立订单详情页（folio route 4）；桌面壳订单详情是列表页抽屉，
          // 守卫里把桌面直连重定向回 /orders，桌面行为零变化。
          component: dualShell(
            PlaceholderView,
            () => import('@/mobile/MobileOrderDetailView.vue'),
            'OrderDetailShellRoute',
          ),
          meta: { title: '订单详情', permission: 'merchant.orders.manage' },
        },
        {
          path: 'wallet',
          name: 'wallet',
          component: dualShell(
            () => import('@/views/WalletView.vue'),
            () => import('@/mobile/MobileWalletView.vue'),
            'WalletShellRoute',
          ),
          meta: { title: '钱包管理', permission: 'merchant.wallet.manage' },
        },
        {
          path: 'deposit',
          name: 'deposit',
          component: dualShell(
            () => import('@/views/DepositView.vue'),
            () => import('@/mobile/MobileDepositView.vue'),
            'DepositShellRoute',
          ),
          meta: { title: '保证金管理', permission: 'merchant.deposit.view' },
        },
        {
          path: 'after-sales',
          name: 'after-sales',
          component: dualShell(
            () => import('@/views/AfterSalesView.vue'),
            () => import('@/mobile/MobileAfterSalesView.vue'),
            'AfterSalesShellRoute',
          ),
          meta: { title: '售后中心', permission: 'merchant.aftersales.manage' },
        },
        {
          path: 'activities',
          name: 'activities',
          component: dualShell(
            () => import('@/views/ActivitiesView.vue'),
            () => import('@/mobile/MobileActivitiesView.vue'),
            'ActivitiesShellRoute',
          ),
          meta: { title: '平台活动中心', permission: 'merchant.activities.view' },
        },
        {
          path: 'messages',
          name: 'messages',
          component: dualShell(
            () => import('@/views/MessagesView.vue'),
            () => import('@/mobile/MobileMessagesView.vue'),
            'MessagesShellRoute',
          ),
          meta: { title: '消息中心', permission: 'merchant.messages.use' },
        },
        {
          path: 'notifications',
          name: 'notifications',
          component: dualShell(
            () => import('@/views/NotificationsView.vue'),
            () => import('@/mobile/MobileNotificationsView.vue'),
            'NotificationsShellRoute',
          ),
          meta: { title: '平台通知中心', permission: 'merchant.notifications.view' },
        },
        {
          path: 'no-shop',
          name: 'no-shop',
          component: dualShell(
            PlaceholderView,
            () => import('@/mobile/MobilePlaceholderView.vue'),
            'NoShopShellRoute',
          ),
          meta: { title: '暂无可用店铺', noShop: true },
        },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: dualShell(
        PlaceholderView,
        () => import('@/mobile/MobilePlaceholderView.vue'),
        'NotFoundShellRoute',
      ),
      meta: { title: '页面不存在', public: true },
    },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async (to) => {
  const { isAuthenticated, loaded, loadSession, can, shops } = useMerchantSession()
  if (to.meta.public) return true
  if (!loaded.value) await loadSession()
  if (!isAuthenticated.value) {
    return { name: 'login', query: { next: to.fullPath } }
  }
  // 手机壳的订单详情页在桌面壳没有对应页面（桌面是列表抽屉）：直连回列表。
  if (to.name === 'order-detail' && !isMobileShell.value) {
    return { name: 'orders' }
  }
  // 冷启动落点：此时 loadSession 已完成，权限可读，再选第一个有权限的模块。
  if (to.name === 'home') {
    // 手机壳：'/' 就是首页宫格（folio 核心），只要绑定了店铺就放行；
    // 模块入口的显隐由宫格按 can() 过滤，不沿用桌面 LANDING 重定向。
    if (isMobileShell.value) {
      return shops.value.length ? true : { name: 'no-shop' }
    }
    const target = LANDING.find((item) => can(item.permission))
    return target ? target.path : { name: 'no-shop' }
  }
  // 菜单按权限隐藏，直连 URL 也要挡（接口仍会 403 兜底）。
  if (to.meta.permission && !can(to.meta.permission)) {
    return { name: 'home' }
  }
  return true
})

router.afterEach((to) => {
  document.title = `${to.meta.title || '商家中心'} · Joybuy`
})

export default router
