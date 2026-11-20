<script setup>
import { computed } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'

import { useMerchantSession } from '@/composables/useMerchantSession'
import { useMobileToast } from '@/shell'

const route = useRoute()
const router = useRouter()
const { shops, activeShop, activeShopId, logout, switchShop } = useMerchantSession()

const toast = useMobileToast()

const title = computed(() => route.meta.title || '商家中心')

// 首页（宫格）是手机壳的导航根：不显示返回按钮（folio：homeButton.hidden = current === 0）。
const isHome = computed(() => route.name === 'home')

// 返回语义：vue-router 写入 history.state（position>0 表示本应用历史可回退），
// 可回退就 router.back()，否则兜底回首页宫格。
const canGoBack = computed(() => {
  const state = router.options.history.state
  return Boolean(state && typeof state.position === 'number' && state.position > 0)
})

function goBack() {
  if (canGoBack.value) router.back()
  else router.push('/')
}

// 多店切换与桌面壳同语义：切上下文后整页刷新，避免已挂载视图残留旧店铺数据。
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
  <div class="m-shell">
    <header class="m-topbar">
      <button
        v-if="!isHome"
        type="button"
        class="m-topbar__back"
        aria-label="返回"
        @click="goBack"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8">
          <path d="m15 5-7 7 7 7" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </button>
      <span v-else class="m-topbar__mark" aria-hidden="true">J</span>
      <h1 class="m-topbar__title">{{ title }}</h1>
      <div class="m-topbar__tools">
        <select
          v-if="shops.length > 1"
          class="m-topbar__shop"
          :value="activeShopId"
          aria-label="切换店铺"
          @change="onSwitchShop"
        >
          <option v-for="shop in shops" :key="shop.id" :value="shop.id">{{ shop.name }}</option>
        </select>
        <span v-else-if="activeShop" class="m-topbar__shop-name">{{ activeShop.name }}</span>
        <button type="button" class="m-topbar__logout" @click="signOut">退出</button>
      </div>
    </header>

    <main id="main-content" class="m-shell__content">
      <RouterView />
    </main>

    <!-- toast：aria-live 同步播报，给读屏与弱网操作反馈（folio readout 语义）。 -->
    <div v-if="toast" class="m-toast" role="status" aria-live="polite">{{ toast }}</div>
  </div>
</template>

<style scoped>
.m-shell {
  min-height: 100vh;
  background: var(--m-canvas);
  color: var(--m-ink);
}

/* 顶栏：sticky 跟手，安全区适配。 */
.m-topbar {
  position: sticky;
  top: 0;
  z-index: 6;
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 52px;
  padding: calc(var(--m-space-2) + env(safe-area-inset-top)) var(--m-gutter) var(--m-space-2);
  background: var(--m-paper);
  border-bottom: 1px solid var(--m-line);
}

.m-topbar__back {
  flex: 0 0 var(--m-target);
  width: var(--m-target);
  height: var(--m-target);
  display: grid;
  place-items: center;
  margin-left: -6px;
  border: 0;
  border-radius: var(--m-radius);
  background: transparent;
  color: var(--m-ink);
  cursor: pointer;
}

.m-topbar__back svg {
  width: 22px;
  height: 22px;
}

.m-topbar__back:active {
  background: var(--m-canvas);
  color: var(--m-accent);
}

.m-topbar__mark {
  flex: 0 0 30px;
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: var(--m-accent);
  color: #fff;
  font-weight: 700;
  font-size: 16px;
}

.m-topbar__title {
  flex: 1;
  min-width: 0;
  margin: 0;
  font-size: 17px;
  font-weight: 650;
  letter-spacing: -0.01em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.m-topbar__tools {
  flex: none;
  display: flex;
  align-items: center;
  gap: 6px;
  max-width: 56%;
}

.m-topbar__shop {
  max-width: 130px;
  min-height: 34px;
  padding: 2px 6px;
  border: 1px solid var(--m-line);
  border-radius: 8px;
  background: var(--m-canvas);
  color: var(--m-ink);
  font-size: 12px;
}

.m-topbar__shop-name {
  max-width: 130px;
  font-size: 12px;
  color: var(--m-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.m-topbar__logout {
  flex: none;
  min-height: 34px;
  padding: 0 10px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--m-accent);
  font-size: 12px;
  font-weight: 650;
  cursor: pointer;
}

/* 内容列：复刻 folio「电脑上居中显示手机宽度页面」（--merchant-phone-width: 390px）。 */
.m-shell__content {
  width: 100%;
  max-width: min(100%, 390px);
  margin: 0 auto;
  padding: var(--m-space-4) var(--m-gutter) calc(28px + env(safe-area-inset-bottom));
}

.m-toast {
  position: fixed;
  bottom: calc(20px + env(safe-area-inset-bottom));
  left: 50%;
  transform: translateX(-50%);
  z-index: 30;
  max-width: calc(100vw - 32px);
  padding: 10px 18px;
  border-radius: 8px;
  background: #243342;
  color: #fff;
  font-size: 13px;
  text-align: center;
  box-shadow: 0 6px 25px rgb(0 0 0 / 14%);
}

/* 内容列在超宽视口下也保持手机比例；再宽的屏由 max-width 兜底居中。 */
@media (min-width: 481px) {
  .m-shell__content {
    padding-inline: var(--m-space-4);
  }
}
</style>
