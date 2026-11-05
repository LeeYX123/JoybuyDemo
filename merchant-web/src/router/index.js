import { createRouter, createWebHistory } from 'vue-router'

import { useMerchantSession } from '@/composables/useMerchantSession'

// 商家端落地的第一个有权限模块（M01 经营看板 → 店铺管理 → 商品上架…）。
const LANDING = [
  { path: '/dashboard', permission: 'merchant.dashboard.view' },
  { path: '/store', permission: 'merchant.store.manage' },
  { path: '/orders', permission: 'merchant.orders.manage' },
  { path: '/catalog', permission: 'merchant.listings.manage' },
  { path: '/after-sales', permission: 'merchant.aftersales.manage' },
  { path: '/messages', permission: 'merchant.messages.use' },
]

const PlaceholderView = () => import('@/views/PlaceholderView.vue')

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { title: '登录', public: true },
    },
    {
      path: '/',
      component: () => import('@/layouts/MerchantLayout.vue'),
      children: [
        {
          path: '',
          name: 'home',
          redirect: () => {
            const { can } = useMerchantSession()
            const target = LANDING.find((item) => can(item.permission))
            return target ? target.path : '/no-shop'
          },
        },
        {
          path: 'dashboard',
          name: 'dashboard',
          component: () => import('@/views/DashboardView.vue'),
          meta: { title: '经营看板', permission: 'merchant.dashboard.view' },
        },
        {
          path: 'store',
          name: 'store',
          component: () => import('@/views/StoreView.vue'),
          meta: { title: '店铺管理', permission: 'merchant.store.manage' },
        },
        {
          path: 'catalog',
          name: 'catalog',
          component: () => import('@/views/CatalogueView.vue'),
          meta: { title: '商品上架中心', permission: 'merchant.listings.manage' },
        },
        {
          path: 'orders',
          name: 'orders',
          component: () => import('@/views/OrdersView.vue'),
          meta: { title: '订单管理', permission: 'merchant.orders.manage' },
        },
        {
          path: 'wallet',
          name: 'wallet',
          component: () => import('@/views/WalletView.vue'),
          meta: { title: '钱包管理', permission: 'merchant.wallet.manage' },
        },
        {
          path: 'deposit',
          name: 'deposit',
          component: () => import('@/views/DepositView.vue'),
          meta: { title: '保证金管理', permission: 'merchant.deposit.view' },
        },
        {
          path: 'after-sales',
          name: 'after-sales',
          component: () => import('@/views/AfterSalesView.vue'),
          meta: { title: '售后中心', permission: 'merchant.aftersales.manage' },
        },
        {
          path: 'activities',
          name: 'activities',
          component: () => import('@/views/ActivitiesView.vue'),
          meta: { title: '平台活动中心', permission: 'merchant.activities.view' },
        },
        {
          path: 'messages',
          name: 'messages',
          component: () => import('@/views/MessagesView.vue'),
          meta: { title: '消息中心', permission: 'merchant.messages.use' },
        },
        {
          path: 'notifications',
          name: 'notifications',
          component: () => import('@/views/NotificationsView.vue'),
          meta: { title: '平台通知中心', permission: 'merchant.notifications.view' },
        },
        {
          path: 'no-shop',
          name: 'no-shop',
          component: PlaceholderView,
          meta: { title: '暂无可用店铺', noShop: true },
        },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: PlaceholderView,
      meta: { title: '页面不存在', public: true },
    },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async (to) => {
  const { isAuthenticated, loaded, loadSession, can } = useMerchantSession()
  if (to.meta.public) return true
  if (!loaded.value) await loadSession()
  if (!isAuthenticated.value) {
    return { name: 'login', query: { next: to.fullPath } }
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
