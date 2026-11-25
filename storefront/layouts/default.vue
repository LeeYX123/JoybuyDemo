<script setup>
// 右上角购物车角标：按「商品件数之和」显示（A×3 + B×1 + C×2 = 6），
// 超过 99 显示 99+（AppHeader 内部格式化）。useCart 与页面共用 key='cart'，
// 不会产生重复请求。
import { computed } from 'vue'

import { useCart } from '../composables/useCart'

const { items } = await useCart()
const cartCount = computed(() =>
  items.value.reduce((sum, item) => sum + (Number(item.quantity) || 0), 0),
)
</script>

<template>
  <div class="app-shell">
    <a class="skip-link" href="#main-content">Skip to main content</a>
    <AppHeader :cart-count="cartCount" />
    <main id="main-content" class="app-main" tabindex="-1">
      <slot />
    </main>
    <AppFooter />
    <UiToast />
    <!-- 需求 21：全站右下角【客服】入口（Crisp 原生挂件已由 plugins/crisp.client.js
         的开关默认关闭）。 -->
    <SupportChatLauncher />
  </div>
</template>
