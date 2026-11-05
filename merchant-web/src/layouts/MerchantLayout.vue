<script setup>
import { computed } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'

import { useMerchantSession } from '@/composables/useMerchantSession'

const { staff, shops, activeShop, activeShopId, logout, switchShop, can } = useMerchantSession()
const route = useRoute()
const router = useRouter()

const ICONS = {
  dashboard: 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
  store: 'M3 10l2-6h14l2 6M4 10v10h16V10M9 20v-7h6v7',
  box: 'M3 7l9-4 9 4-9 5zM3 7v11l9 4 9-4V7M12 12v10',
  orders: 'M5 3h14v18H5zM8 7h8M8 11h8M8 15h5',
  wallet: 'M3 6h17v14H3zM3 6V4h14M15 11h6v5h-6z',
  shield: 'M12 3l8 3v6c0 6-8 10-8 10S4 18 4 12V6zM8 12l3 3 5-6',
  service: 'M4 14v-3a8 8 0 0116 0v3M4 11H2v7h5v-7zM20 11h2v7h-5v-7z',
  flag: 'M5 22V3M5 4h14l-3 5 3 5H5',
  chat: 'M4 5h16v11H9l-5 4z',
  bell: 'M5 17h14l-2-4V9a5 5 0 00-10 0v4zM10 20h4',
}

// 菜单按「模块 + 权限」声明；保证金菜单只在商家启用保证金时出现（M06）。
const NAV = [
  {
    group: '经营',
    items: [
      {
        to: '/dashboard',
        label: '经营看板',
        icon: 'dashboard',
        permission: 'merchant.dashboard.view',
      },
      { to: '/store', label: '店铺管理', icon: 'store', permission: 'merchant.store.manage' },
      {
        to: '/catalog',
        label: '商品上架中心',
        icon: 'box',
        permission: 'merchant.listings.manage',
      },
    ],
  },
  {
    group: '交易',
    items: [
      { to: '/orders', label: '订单管理', icon: 'orders', permission: 'merchant.orders.manage' },
      { to: '/wallet', label: '钱包管理', icon: 'wallet', permission: 'merchant.wallet.manage' },
      {
        to: '/deposit',
        label: '保证金管理',
        icon: 'shield',
        permission: 'merchant.deposit.view',
        requiresDeposit: true,
      },
      {
        to: '/after-sales',
        label: '售后中心',
        icon: 'service',
        permission: 'merchant.aftersales.manage',
      },
    ],
  },
  {
    group: '增长与消息',
    items: [
      {
        to: '/activities',
        label: '平台活动中心',
        icon: 'flag',
        permission: 'merchant.activities.view',
      },
      { to: '/messages', label: '消息中心', icon: 'chat', permission: 'merchant.messages.use' },
      {
        to: '/notifications',
        label: '平台通知中心',
        icon: 'bell',
        permission: 'merchant.notifications.view',
      },
    ],
  },
]

const visibleGroups = computed(() =>
  NAV.map((group) => ({
    ...group,
    items: group.items.filter((item) => {
      if (item.permission && !can(item.permission)) return false
      if (item.requiresDeposit && !activeShop.value?.deposit_enabled) return false
      return true
    }),
  })).filter((group) => group.items.length > 0),
)

const currentTitle = computed(() => route.meta.title || '商家中心')

function onSwitchShop(event) {
  switchShop(event.target.value)
  router.go(0)
}

async function signOut() {
  await logout()
  router.push('/login')
}
</script>

<template>
  <div class="merchant-shell">
    <aside class="merchant-side">
      <div class="merchant-brand">
        <span class="merchant-brand__logo" aria-hidden="true">J</span>
        <div>
          <strong>商家中心</strong>
          <small>JOYBUY SELLER</small>
        </div>
      </div>
      <nav class="merchant-nav" aria-label="商家端导航">
        <template v-for="group in visibleGroups" :key="group.group">
          <div class="merchant-side__group">{{ group.group }}</div>
          <RouterLink v-for="item in group.items" :key="item.to" :to="item.to">
            <svg class="merchant-nav__icon" viewBox="0 0 24 24" aria-hidden="true">
              <path :d="ICONS[item.icon]" />
            </svg>
            {{ item.label }}
          </RouterLink>
        </template>
      </nav>
      <div class="merchant-side__foot">
        <strong>{{ activeShop?.name || '未选择店铺' }}</strong>
        <span>{{ activeShop?.role || '—' }}</span>
      </div>
    </aside>

    <div class="merchant-main">
      <header class="merchant-topbar">
        <span class="merchant-topbar__crumb">商家中心 /</span>
        <h1>{{ currentTitle }}</h1>
        <div class="merchant-topbar__right">
          <label v-if="shops.length > 1" class="merchant-shop-chip">
            店铺
            <select :value="activeShopId" @change="onSwitchShop">
              <option v-for="shop in shops" :key="shop.id" :value="shop.id">
                {{ shop.name }}
              </option>
            </select>
          </label>
          <span v-else-if="activeShop" class="merchant-shop-chip">{{ activeShop.name }}</span>
          <span>{{ staff?.display_name }}</span>
          <button type="button" class="btn btn--sm" @click="signOut">退出</button>
        </div>
      </header>
      <main id="main-content" class="merchant-content">
        <RouterView />
      </main>
    </div>
  </div>
</template>
