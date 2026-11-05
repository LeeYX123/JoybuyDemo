import { createRouter, createWebHistory } from 'vue-router'

import { useStaffAuth } from '@/composables/useStaffAuth'

import BuyersView from '@/views/BuyersView.vue'
import CatalogView from '@/views/CatalogView.vue'
import CmsView from '@/views/CmsView.vue'
import CrawlersView from '@/views/CrawlersView.vue'
import LoginView from '@/views/LoginView.vue'
import NotFoundView from '@/views/NotFoundView.vue'
import ReviewsView from '@/views/ReviewsView.vue'

// 默认落地页：进入第一个有权限的模块（A01「登录后进入第一个有权限模块」）。
const LANDING_CANDIDATES = [
  { path: '/merchants', module: 'merchants' },
  { path: '/products', module: 'catalog.pool' },
  { path: '/listings', module: 'catalog.listings' },
  { path: '/orders', module: 'orders' },
  { path: '/finance', module: 'finance' },
  { path: '/deposits', module: 'deposits' },
  { path: '/aftersales', module: 'aftersales' },
  { path: '/activities', module: 'activities' },
  { path: '/banners', module: 'cms.banners' },
  { path: '/notifications', module: 'notifications' },
  { path: '/support', module: 'support' },
  { path: '/buyers', module: 'buyers' },
  { path: '/whitelist', module: 'whitelist' },
  { path: '/growth', module: 'merchants.growth' },
  { path: '/staff', module: 'staff.roles' },
  { path: '/audit-logs', module: 'audit.logs' },
  { path: '/crawlers', module: 'crawler.jobs' },
]

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { title: '登录', public: true },
    },
    {
      path: '/',
      component: () => import('@/layouts/AdminLayout.vue'),
      children: [
        {
          path: '',
          name: 'home',
          redirect: () => {
            const { canView } = useStaffAuth()
            const target = LANDING_CANDIDATES.find((item) => canView(item.module))
            return target ? target.path : '/no-access'
          },
        },
        {
          path: 'no-access',
          name: 'no-access',
          component: NotFoundView,
          meta: { title: '暂无可用模块' },
        },
        {
          path: 'merchants',
          name: 'merchants',
          component: () => import('@/views/MerchantsView.vue'),
          meta: { title: '商家管理', module: 'merchants' },
        },
        {
          path: 'products',
          name: 'products',
          component: () => import('@/views/ProductPoolView.vue'),
          meta: { title: '商品池管理', module: 'catalog.pool' },
        },
        {
          path: 'listings',
          name: 'listings',
          component: () => import('@/views/MerchantListingsView.vue'),
          meta: { title: '商家商品管理', module: 'catalog.listings' },
        },
        {
          path: 'orders',
          name: 'orders',
          component: () => import('@/views/MerchantOrdersView.vue'),
          meta: { title: '订单管理', module: 'orders' },
        },
        {
          path: 'finance',
          name: 'finance',
          component: () => import('@/views/FinanceView.vue'),
          meta: { title: '资金审核', module: 'finance' },
        },
        {
          path: 'deposits',
          name: 'deposits',
          component: () => import('@/views/DepositsView.vue'),
          meta: { title: '保证金管理', module: 'deposits' },
        },
        {
          path: 'aftersales',
          name: 'aftersales',
          component: () => import('@/views/AfterSalesView.vue'),
          meta: { title: '售后处理', module: 'aftersales' },
        },
        {
          path: 'activities',
          name: 'activities',
          component: () => import('@/views/ActivitiesView.vue'),
          meta: { title: '平台活动与推荐返佣', module: 'activities' },
        },
        {
          path: 'banners',
          name: 'banners',
          component: () => import('@/views/BannersView.vue'),
          meta: { title: '商城首页轮播图', module: 'cms.banners' },
        },
        {
          path: 'notifications',
          name: 'notifications',
          component: () => import('@/views/NotificationsView.vue'),
          meta: { title: '平台通知推送', module: 'notifications' },
        },
        {
          path: 'support',
          name: 'support',
          component: () => import('@/views/SupportView.vue'),
          meta: { title: '客服中心', module: 'support' },
        },
        {
          path: 'whitelist',
          name: 'whitelist',
          component: () => import('@/views/WhitelistView.vue'),
          meta: { title: '白名单账号', module: 'whitelist' },
        },
        {
          path: 'growth',
          name: 'growth',
          component: () => import('@/views/GrowthView.vue'),
          meta: { title: '商家关注与曝光', module: 'merchants.growth' },
        },
        {
          path: 'staff',
          name: 'staff',
          component: () => import('@/views/StaffAccountsView.vue'),
          meta: { title: '账号与权限', module: 'staff.roles' },
        },
        {
          path: 'audit-logs',
          name: 'audit-logs',
          component: () => import('@/views/AuditLogsView.vue'),
          meta: { title: '操作日志', module: 'audit.logs' },
        },
        {
          path: 'catalog',
          name: 'catalog',
          component: CatalogView,
          meta: { title: '商品目录', module: 'catalog.products' },
        },
        {
          path: 'reviews',
          name: 'reviews',
          component: ReviewsView,
          meta: { title: '评价管理', module: 'catalog.products' },
        },
        {
          path: 'crawlers',
          name: 'crawlers',
          component: CrawlersView,
          meta: { title: '爬虫任务', module: 'crawler.jobs' },
        },
        {
          path: 'cms',
          name: 'cms',
          component: CmsView,
          meta: { title: '内容管理', module: 'catalog.products' },
        },
        {
          path: 'buyers',
          name: 'buyers',
          component: BuyersView,
          meta: { title: '买家与订单', module: 'staff.roles' },
        },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: NotFoundView,
      meta: { title: '页面不存在' },
    },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async (to) => {
  const { isAuthenticated, loaded, loadSession, canView } = useStaffAuth()
  if (to.meta.public) return true
  if (!loaded.value) await loadSession()
  if (!isAuthenticated.value) {
    return { name: 'login', query: { next: to.fullPath } }
  }
  // RBAC parity with the API: the menu hides unauthorized sections and the
  // guard blocks direct URL access (the API still 403s as the backstop).
  if (to.meta.module && !canView(to.meta.module)) {
    return { name: 'home' }
  }
  return true
})

router.afterEach((to) => {
  document.title = `${to.meta.title || '管理平台'} · Joybuy`
})

export default router
