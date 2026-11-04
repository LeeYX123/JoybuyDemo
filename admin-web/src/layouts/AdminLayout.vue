<script setup>
import { useRouter } from 'vue-router'

import { useStaffAuth } from '@/composables/useStaffAuth'

const { staff, logout, hasPermission } = useStaffAuth()
const router = useRouter()

const navItems = [
  { to: '/', label: '仪表盘', permission: null },
  { to: '/catalog', label: '商品目录', permission: 'catalog.products.manage' },
  { to: '/reviews', label: '评价管理', permission: 'catalog.products.manage' },
  { to: '/crawlers', label: '爬虫任务', permission: 'crawler.jobs.manage' },
  { to: '/cms', label: '内容管理', permission: 'catalog.products.manage' },
  { to: '/buyers', label: '买家与订单', permission: 'staff.roles.manage' },
]

function visible(item) {
  return !item.permission || hasPermission(item.permission)
}

async function signOut() {
  await logout()
  router.push('/login')
}
</script>

<template>
  <div class="admin-shell">
    <header class="admin-header">
      <span class="admin-brand">Joybuy 管理平台</span>
      <nav aria-label="管理端导航">
        <template v-for="item in navItems.filter(visible)" :key="item.to">
          <RouterLink :to="item.to">{{ item.label }}</RouterLink>
        </template>
      </nav>
      <div v-if="staff" class="admin-session">
        <span>{{ staff.display_name }}</span>
        <button type="button" @click="signOut">退出登录</button>
      </div>
    </header>
    <main class="admin-main">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.admin-shell {
  min-height: 100vh;
}

.admin-header {
  display: flex;
  align-items: center;
  gap: var(--space-5);
  min-height: 56px;
  padding: 0 var(--space-5);
  border-bottom: 1px solid var(--colour-border);
  background: var(--colour-surface);
}

.admin-brand {
  font-weight: 700;
  color: var(--colour-accent);
}

.admin-header nav {
  display: flex;
  gap: var(--space-2);
}

.admin-header nav a {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  padding: 0 var(--space-3);
  border-radius: var(--radius-md);
  color: var(--colour-text-secondary);
  text-decoration: none;
}

.admin-header nav a.router-link-active {
  color: var(--colour-accent);
  background: var(--colour-accent-soft);
}

.admin-session {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.admin-session button {
  min-height: 44px;
  padding: 0 var(--space-4);
  border: 1px solid var(--colour-border-strong);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  cursor: pointer;
}

.admin-main {
  padding: var(--space-6);
}
</style>
