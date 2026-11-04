import { createRouter, createWebHistory } from 'vue-router'

import { useStaffAuth } from '@/composables/useStaffAuth'

import BuyersView from '@/views/BuyersView.vue'
import CatalogView from '@/views/CatalogView.vue'
import CmsView from '@/views/CmsView.vue'
import CrawlersView from '@/views/CrawlersView.vue'
import DashboardView from '@/views/DashboardView.vue'
import LoginView from '@/views/LoginView.vue'
import NotFoundView from '@/views/NotFoundView.vue'
import ReviewsView from '@/views/ReviewsView.vue'

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
          name: 'dashboard',
          component: DashboardView,
          meta: { title: '仪表盘' },
        },
        {
          path: 'catalog',
          name: 'catalog',
          component: CatalogView,
          meta: { title: '商品目录', permission: 'catalog.products.manage' },
        },
        {
          path: 'reviews',
          name: 'reviews',
          component: ReviewsView,
          meta: { title: '评价管理', permission: 'catalog.products.manage' },
        },
        {
          path: 'crawlers',
          name: 'crawlers',
          component: CrawlersView,
          meta: { title: '爬虫任务', permission: 'crawler.jobs.manage' },
        },
        {
          path: 'cms',
          name: 'cms',
          component: CmsView,
          meta: { title: '内容管理', permission: 'catalog.products.manage' },
        },
        {
          path: 'buyers',
          name: 'buyers',
          component: BuyersView,
          meta: { title: '买家与订单', permission: 'staff.roles.manage' },
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
  const { isAuthenticated, loaded, loadSession, hasPermission } = useStaffAuth()
  if (to.meta.public) return true
  if (!loaded.value) await loadSession()
  if (!isAuthenticated.value) {
    return { name: 'login', query: { next: to.fullPath } }
  }
  // RBAC parity with the API: the menu hides unauthorized sections and the
  // guard blocks direct URL access (the API still 403s as the backstop).
  if (to.meta.permission && !hasPermission(to.meta.permission)) {
    return { name: 'dashboard' }
  }
  return true
})

router.afterEach((to) => {
  document.title = `${to.meta.title || '管理平台'} · Joybuy`
})

export default router
