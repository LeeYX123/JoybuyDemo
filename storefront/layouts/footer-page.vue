<script setup>
// 页脚内容页布局（需求 12.1 → 16.1）：复用全局 site-header，只隐藏品类那一栏
// （分类按钮 + 一级品类行 + 其下拉）。黑条（语言）、logo、搜索、账号/申请店铺/
// 购物车与首页完全一致——不再维护第二份简顶栏，避免两套 header 漂移。
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
    <AppHeader hide-category-nav :cart-count="cartCount" />
    <main id="main-content" class="app-main" tabindex="-1">
      <slot />
    </main>
    <AppFooter />
    <UiToast />
    <!-- 需求 21：内容页同样保留全站【客服】入口。 -->
    <SupportChatLauncher />
  </div>
</template>

<style scoped>
/* 16.1：内容页的 help 中心左栏沿用本地 sticky 改进（真站为 static）。站头现在
   是吸顶的，sticky 顶部偏移必须让到站头实际高度之下，否则左栏会滚到站头下面
   被遮住；高度由 AppHeader 实时写入 --site-header-height（含窄屏换行）。
   只覆盖偏移，不改 HelpCenter 自身样式。 */
.app-main :deep(.help-center__nav) {
  top: calc(var(--site-header-height, 120px) + 16px);
}

/* 需求 17.1-3：收紧政策/帮助页 header→正文间距。真站 detail_detailWrapper
   （存档 CSS aa6a29a3f278211f.css）自带 padding:32px 0、无额外外边距 →
   header 下缘到白色内容卡正好 32px；我们的 HelpCenter 已复刻 32px 顶 padding，
   但全局 `.app-main > * { margin-block: var(--space-6) }` 又叠了 24px（合计 56px）。
   仅对 HelpCenter 根元素归零该 margin（about/contact/news 等页不受影响），
   使间距与真站一致 = 32px。 */
.app-main > :deep(.help-center) {
  margin-block: 0;
}
</style>
