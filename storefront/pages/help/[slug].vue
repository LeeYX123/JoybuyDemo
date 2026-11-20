<script setup>
import { computed } from 'vue'
import { useRoute, createError } from '#imports'

import { helpPageBySlug, resolveHelpSlug } from '../../content/helpPages'
import { useLocale } from '../../composables/useLocale'

// 批次 Q（需求 15.1）：真站 help 中心的原路径 /help/<slug>。
// 真站点击左栏是整页跳转，因此这里也按路由切换；/pages/<slug> 是页脚入口的别名路由，
// 两者渲染同一个 HelpCenter 组件（左 tab + 右内容）。
definePageMeta({ layout: 'footer-page' })

const route = useRoute()
const { locale } = useLocale()

const page = computed(() => helpPageBySlug[resolveHelpSlug(route.params.slug)] || null)

if (!page.value) {
  throw createError({ statusCode: 404, statusMessage: 'Page not found', fatal: true })
}

const title = computed(() => page.value.title[locale.value] || page.value.title.en)

useHead({ title })
</script>

<template>
  <!-- 批次 U（17.5）：customer-service 两页用真站 customer-service 版式，其余仍为 help 中心版式 -->
  <CustomerServicePage v-if="page.customerService" :slug="page.slug" />
  <HelpCenter v-else-if="page" :slug="page.slug" />
</template>
