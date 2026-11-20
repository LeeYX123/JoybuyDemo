<script setup>
import { defineAsyncComponent } from 'vue'

import { useMobileShell } from '@/shell'

// 根布局双壳：路由表 '/' 只挂一个布局组件，壳内各自渲染 <RouterView>。
// 两个布局都走异步 chunk，桌面壳不加载手机布局代码（反之亦然）。
// 跨阈值切换时本组件原地换布局（无 reload、无路由跳转），子路由视图重新挂载取数。
const MobileLayout = defineAsyncComponent(() => import('./MobileShell.vue'))
const DesktopLayout = defineAsyncComponent(() => import('./MerchantLayout.vue'))
const { isMobileShell } = useMobileShell()
</script>

<template>
  <MobileLayout v-if="isMobileShell" />
  <DesktopLayout v-else />
</template>
