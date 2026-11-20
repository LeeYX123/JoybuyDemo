<script setup>
import { computed } from 'vue'
import { useRoute, createError } from '#imports'

import { helpPageBySlug, resolveHelpSlug } from '../../content/helpPages'
import { csArticleBySlug } from '../../content/help/csArticles'
import { useLocale } from '../../composables/useLocale'

// 批次 Q（需求 15.1）：真站 help 中心的原路径 /help/<slug>。
// 真站点击左栏是整页跳转，因此这里也按路由切换；/pages/<slug> 是页脚入口的别名路由，
// 两者渲染同一个组件（左 tab + 右内容 / customer-service 清单页）。
// 批次 0am（2026-11-20）：真站文章详情也是 /help/<slug> 形态（支付 5 篇 + 退货 11 篇），
// 命中 csArticles 注册表时渲染文章详情版式。
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
