<script setup>
import { computed } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'

import { useStaffAuth } from '@/composables/useStaffAuth'

const { staff, logout, canView } = useStaffAuth()
const route = useRoute()
const router = useRouter()

// 图标取自原型 shapes（同一套路径，保证视觉一致）。
const ICONS = {
  store: 'M3 10l2-6h14l2 6M4 10v10h16V10M9 20v-7h6v7M3 10c2 3 4 3 6 0 2 3 4 3 6 0 2 3 4 3 6 0',
  box: 'M3 7l9-4 9 4-9 5zM3 7v11l9 4 9-4V7M12 12v10',
  orders: 'M5 3h14v18H5zM8 7h8M8 11h8M8 15h5',
  wallet: 'M3 6h17v14H3zM3 6V4h14M15 11h6v5h-6z',
  shield: 'M12 3l8 3v6c0 6-8 10-8 10S4 18 4 12V6zM8 12l3 3 5-6',
  service: 'M4 14v-3a8 8 0 0116 0v3M4 11H2v7h5v-7zM20 11h2v7h-5v-7zM17 19c0 2-3 3-6 2',
  flag: 'M5 22V3M5 4h14l-3 5 3 5H5',
  crawler: 'M12 4v4M6 8h12v12H6zM9 12h.01M15 12h.01M9 16h6',
  image: 'M3 5h18v14H3zM3 16l5-5 4 4 3-3 6 6',
  bell: 'M5 17h14l-2-4V9a5 5 0 00-10 0v4zM10 20h4',
  chat: 'M4 5h16v11H9l-5 4z',
  users: 'M8 12a4 4 0 100-8 4 4 0 000 8M2 21v-3c0-5 12-5 12 0v3M17 4a4 4 0 010 8M17 15c4 0 5 2 5 6',
  card: 'M3 6h18v12H3zM3 10h18M7 15h4',
  trend: 'M3 17l6-6 4 4 8-8M21 7v5h-5',
  key: 'M14 10a4 4 0 10-4 4l1 1-2 2 2 2 2-2 1 1a4 4 0 000-8',
  logs: 'M6 3h9l4 4v14H6zM9 9h6M9 13h6M9 17h4',
}

const NAV = [
  {
    group: '交易管理',
    items: [
      { to: '/merchants', label: '商家管理', icon: 'store', module: 'merchants' },
      { to: '/products', label: '商品池管理', icon: 'box', module: 'catalog.pool' },
      { to: '/listings', label: '商家商品管理', icon: 'box', module: 'catalog.listings' },
      { to: '/orders', label: '订单管理', icon: 'orders', module: 'orders' },
    ],
  },
  {
    group: '资金与风控',
    items: [
      { to: '/finance', label: '资金审核', icon: 'wallet', module: 'finance' },
      { to: '/deposits', label: '保证金管理', icon: 'shield', module: 'deposits' },
    ],
  },
  {
    group: '服务与运营',
    items: [
      { to: '/aftersales', label: '售后处理', icon: 'service', module: 'aftersales' },
      { to: '/activities', label: '平台活动与返佣', icon: 'flag', module: 'activities' },
      { to: '/banners', label: '首页轮播图', icon: 'image', module: 'cms.banners' },
      { to: '/notifications', label: '平台通知推送', icon: 'bell', module: 'notifications' },
      { to: '/support', label: '客服中心', icon: 'chat', module: 'support' },
    ],
  },
  {
    group: '用户与权限',
    items: [
      { to: '/buyers', label: '用户端管理', icon: 'users', module: 'buyers' },
      { to: '/whitelist', label: '白名单账号', icon: 'card', module: 'whitelist' },
      { to: '/growth', label: '商家关注与曝光', icon: 'trend', module: 'merchants.growth' },
      { to: '/staff', label: '账号与权限', icon: 'key', module: 'staff.roles' },
      { to: '/audit-logs', label: '操作日志', icon: 'logs', module: 'audit.logs' },
    ],
  },
  {
    group: '采集与基础数据',
    items: [{ to: '/crawlers', label: '爬虫任务', icon: 'crawler', module: 'crawler.jobs' }],
  },
]

const visibleGroups = computed(() =>
  NAV.map((group) => ({
    ...group,
    items: group.items.filter((item) => !item.module || canView(item.module)),
  })).filter((group) => group.items.length > 0),
)

const currentTitle = computed(() => route.meta.title || '管理平台')
const avatarText = computed(() => {
  const name = staff.value?.display_name || staff.value?.email || '?'
  return name.trim().charAt(0).toUpperCase()
})

async function signOut() {
  await logout()
  router.push('/login')
}
</script>

<template>
  <div class="admin-shell">
    <aside class="admin-side">
      <div class="admin-brand">
        <span class="admin-brand__mark" aria-hidden="true">寰</span>
        <div>
          <b>寰球优选</b>
          <small>PLATFORM CONSOLE</small>
        </div>
      </div>
      <nav class="admin-nav" aria-label="管理端导航">
        <template v-for="group in visibleGroups" :key="group.group">
          <div class="admin-side__group">{{ group.group }}</div>
          <RouterLink v-for="item in group.items" :key="item.to" :to="item.to">
            <svg class="admin-nav__icon" viewBox="0 0 24 24" aria-hidden="true">
              <path :d="ICONS[item.icon]" />
            </svg>
            {{ item.label }}
          </RouterLink>
        </template>
      </nav>
      <div class="admin-side__foot">
        <strong>{{ staff?.display_name || '未登录' }}</strong>
        <span>{{ (staff?.roles || []).join(' / ') || '—' }}</span>
      </div>
    </aside>

    <div class="admin-main">
      <header class="admin-topbar">
        <span class="admin-topbar__crumb">平台管理控制台 /</span>
        <h1>{{ currentTitle }}</h1>
        <div class="admin-topbar__right">
          <span>{{ staff?.email }}</span>
          <span class="admin-topbar__avatar" :title="staff?.display_name || ''">
            {{ avatarText }}
          </span>
          <button type="button" class="btn btn--sm" @click="signOut">退出登录</button>
        </div>
      </header>
      <main id="main-content" class="admin-content">
        <RouterView />
      </main>
    </div>
  </div>
</template>
