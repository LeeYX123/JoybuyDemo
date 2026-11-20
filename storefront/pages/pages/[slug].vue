<script setup>
import { computed } from 'vue'
import { useRoute, createError } from '#imports'

import { helpPageBySlug, resolveHelpSlug } from '../../content/helpPages'
import { csArticleBySlug } from '../../content/help/csArticles'
import { useLocale } from '../../composables/useLocale'

// 页脚内容页路由（需求 11.1 / 12.1 → 批次 Q 15.1 改版）：/pages/<slug>。
// 现在 /pages/* 与真站 /help/* 是同一套 help 中心页面（左 tab + 右内容），
// 保留该前缀是为了页脚既有链接（AppFooter 不归属本批次）不用改动。
// 批次 0am（2026-11-20）：/pages/<slug> 与 /help/<slug> 一样可解析 16 篇文章详情。
// 未知 slug 直接 404。
definePageMeta({ layout: 'footer-page' })

const route = useRoute()
const { locale } = useLocale()

const article = computed(() => csArticleBySlug[route.params.slug] || null)
const page = computed(() =>
  article.value ? null : helpPageBySlug[resolveHelpSlug(route.params.slug)] || null,
)

if (!article.value && !page.value) {
  throw createError({ statusCode: 404, statusMessage: 'Page not found', fatal: true })
}

const title = computed(() => {
  if (article.value) return article.value.title[locale.value] || article.value.title.en
  return page.value.title[locale.value] || page.value.title.en
})

useHead({ title })
</script>

<template>
  <!-- 批次 0am：customer-service 文章详情（16 篇）用真站文章页版式 -->
  <CsArticlePage v-if="article" :slug="article.slug" />
  <!-- 批次 U（17.5）：customer-service 两页用真站 customer-service 版式，其余仍为 help 中心版式 -->
  <CustomerServicePage v-else-if="page.customerService" :slug="page.slug" />
  <HelpCenter v-else-if="page" :slug="page.slug" />
</template>
