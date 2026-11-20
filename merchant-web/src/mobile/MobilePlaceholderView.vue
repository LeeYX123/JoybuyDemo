<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

// 手机壳占位页：覆盖 no-shop（未绑店铺）与 404 两种场景，文案与桌面
// PlaceholderView 同源。
const route = useRoute()
const noShop = computed(() => Boolean(route.meta.noShop))
const title = computed(() => route.meta.title || '页面不存在')
</script>

<template>
  <div class="m-page">
    <div class="m-card m-card--pad">
      <h1 class="m-section-title">{{ title }}</h1>
      <p class="m-hint" style="margin: 8px 0 0">
        {{
          noShop
            ? '当前账号还没有绑定任何店铺，请联系平台客服开通。'
            : '请求的页面不存在，请从首页重新进入。'
        }}
      </p>
    </div>
    <button type="button" class="m-btn m-btn--tint m-btn--block" @click="$router.push('/')">
      返回首页
    </button>
  </div>
</template>
