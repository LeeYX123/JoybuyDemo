<script setup>
import { computed } from 'vue'
import { useRoute, createError } from '#imports'

import { helpPageBySlug, resolveHelpSlug } from '../../content/helpPages'
import { useLocale } from '../../composables/useLocale'

// 页脚内容页路由（需求 11.1 / 12.1 → 批次 Q 15.1 改版）：/pages/<slug>。
// 现在 /pages/* 与真站 /help/* 是同一套 help 中心页面（左 tab + 右内容），
// 保留该前缀是为了页脚既有链接（AppFooter 不归属本批次）不用改动。
// 未知 slug 直接 404。
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
