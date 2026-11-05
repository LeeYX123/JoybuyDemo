<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const stage = computed(() => route.meta.stage || '')
const noShop = computed(() => Boolean(route.meta.noShop))
const title = computed(() => route.meta.title || '页面不存在')
</script>

<template>
  <section>
    <div class="page-intro">
      <div>
        <h1>{{ title }}</h1>
        <p v-if="noShop">当前账号还没有绑定任何店铺，请联系平台客服开通。</p>
        <p v-else-if="stage">该模块（{{ stage }}）正在开发中。</p>
        <p v-else>请求的页面不存在。</p>
      </div>
    </div>

    <div class="card">
      <div class="card__body">
        <p v-if="noShop" class="notice notice--info">
          商家账号需要在平台管理后台的「商家管理」中绑定到具体店铺，绑定后即可看到经营看板。
        </p>
        <p v-else-if="stage" class="notice notice--info">
          本模块的接口与页面尚未交付，先保留菜单占位，避免点击后 404。
        </p>
        <p v-else class="empty-state">请从左侧菜单进入已开放的模块。</p>
      </div>
    </div>
  </section>
</template>
