<script setup>
import { computed } from 'vue'

import { csArticleBySlug } from '../content/help/csArticles'
import { helpPageBySlug } from '../content/helpPages'
import { useLocale } from '../composables/useLocale'

// 批次 0am（2026-11-20）：真站 customer-service 文章详情页（/help/<slug>，支付 5 篇 +
// 退货 11 篇）。结构与字号来自 2026-11-20 真站文章页存档实测
// （var/cs_articles_20261120/measure_real_article.cjs 本地渲染真站 SSR 存档 +
// 真站 CSS bundle aa6a29a3f278211f.css / styled-components 规则逐条对照）：
//   wrapper #f5f6fa padding 32px 0 flex 居中；mainWrapper 1264px/min-height 200px/flex；
//   白卡 margin-left 16px（真站 detail_itemContent 原值，无左菜单时保留）、radius 8、
//   padding 24px 36px；标题 32px/700/32；正文 16px/24px、块 margin 10px 0、
//   ul margin 10px 0 10px 20px + padding-left 40px disc、ol decimal；
//   链接 #0000EE 下划线（真站 -webkit-link）；图片宽 100% 高 auto、hover 阴影
//   0 0 5px #333（真站原值）。
// 与真站的差异（已记录 HANDOFF 0am / measurement.md）：
//   1. 真站文章页无面包屑/无页脚；本地按任务要求加清单页同款面包屑（分类项可点回清单页）、
//      footer-page 布局保留 AppFooter。
//   2. 正文内真站文章互链改为本地 /help/<slug>；giftcard-terms-conditions 等无本地页的
//      真站网址按 16.5 口径替换为 https://www.joyfumi.com（保留路径）。
const props = defineProps({
  slug: { type: String, required: true },
})

const { locale, t } = useLocale()

const article = computed(() => csArticleBySlug[props.slug] || null)
const category = computed(() => {
  if (!article.value) return null
  const page = helpPageBySlug[article.value.category]
  return page ? page.customerService.category[locale.value] : null
})
const title = computed(() => article.value.title[locale.value] || article.value.title.en)
const blocks = computed(() => article.value.blocks[locale.value] || article.value.blocks.en)

// 面包屑分类项回清单页：与文章行一致用真站 URL 形态 /help/<category>（本地同路径可达）。
const breadcrumbPath = computed(() => (article.value ? `/help/${article.value.category}` : '/'))
</script>

<template>
  <div class="cs-article">
    <!-- 真站文章页无面包屑；本地按任务要求复用清单页面包屑样式，分类项可回清单页 -->
    <nav class="cs-article__breadcrumb" aria-label="breadcrumb">
      <span class="cs-article__breadcrumb-root">{{ t('help.csBreadcrumbRoot') }}</span>
      <svg
        class="cs-article__breadcrumb-sep"
        viewBox="0 0 20 20"
        width="20"
        height="20"
        fill="none"
        aria-hidden="true"
      >
        <path
          stroke="#C2C4CC"
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="1.5"
          d="M14 3 6 17"
        />
      </svg>
      <NuxtLink class="cs-article__breadcrumb-link" :to="breadcrumbPath">
        {{ category }}
      </NuxtLink>
      <svg
        class="cs-article__breadcrumb-sep"
        viewBox="0 0 20 20"
        width="20"
        height="20"
        fill="none"
        aria-hidden="true"
      >
        <path
          stroke="#C2C4CC"
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="1.5"
          d="M14 3 6 17"
        />
      </svg>
      <span class="cs-article__breadcrumb-current">{{ title }}</span>
    </nav>

    <div class="cs-article__main">
      <article class="cs-article__card">
        <h1 class="cs-article__title">{{ title }}</h1>
        <div class="cs-article__body">
          <template v-for="(block, index) in blocks" :key="index">
            <component
              :is="block.ordered ? 'ol' : 'ul'"
              v-if="block.type === 'list'"
              class="cs-article__list"
            >
              <li v-for="(item, itemIndex) in block.items" :key="itemIndex">
                <template v-for="(seg, segIndex) in item" :key="segIndex">
                  <br v-if="seg.br" />
                  <a v-else-if="seg.href" :href="seg.href">
                    <b v-if="seg.b">{{ seg.t }}</b>
                    <template v-else>{{ seg.t }}</template>
                  </a>
                  <b v-else-if="seg.b">
                    <i v-if="seg.i"
                      ><u v-if="seg.u">{{ seg.t }}</u
                      ><template v-else>{{ seg.t }}</template></i
                    >
                    <template v-else>{{ seg.t }}</template>
                  </b>
                  <i v-else-if="seg.i">
                    <u v-if="seg.u">{{ seg.t }}</u>
                    <template v-else>{{ seg.t }}</template>
                  </i>
                  <u v-else-if="seg.u">{{ seg.t }}</u>
                  <span v-else>{{ seg.t }}</span>
                </template>
              </li>
            </component>
            <img
              v-else-if="block.type === 'image'"
              class="cs-article__image"
              :src="block.src"
              alt="image"
              loading="lazy"
            />
            <p v-else class="cs-article__paragraph">
              <template v-for="(seg, segIndex) in block.segments" :key="segIndex">
                <br v-if="seg.br" />
                <a v-else-if="seg.href" :href="seg.href">
                  <b v-if="seg.b">{{ seg.t }}</b>
                  <template v-else>{{ seg.t }}</template>
                </a>
                <b v-else-if="seg.b">
                  <i v-if="seg.i"
                    ><u v-if="seg.u">{{ seg.t }}</u
                    ><template v-else>{{ seg.t }}</template></i
                  >
                  <template v-else>{{ seg.t }}</template>
                </b>
                <i v-else-if="seg.i">
                  <u v-if="seg.u">{{ seg.t }}</u>
                  <template v-else>{{ seg.t }}</template>
                </i>
                <u v-else-if="seg.u">{{ seg.t }}</u>
                <span v-else>{{ seg.t }}</span>
              </template>
            </p>
          </template>
        </div>
      </article>
    </div>
  </div>
</template>

<style scoped>
/* 真站 detail_detailWrapper：bg #f5f6fa、padding 32px 0、flex 居中；
   本地沿用清单页 min-height 口径（footer-page 布局同款 108px header 高度）。 */
.cs-article {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-height: calc(100vh - 108px);
  padding: 32px 0;
  background: #f5f6fa;
}

/* 本地面包屑 = 清单页同款（真站文章页无面包屑）：宽 min(1264px,92vw)。 */
.cs-article__breadcrumb {
  display: flex;
  align-items: center;
  width: min(1264px, 92vw);
}

.cs-article__breadcrumb-root {
  overflow: hidden;
  color: #888b94;
  font-size: 14px;
  font-weight: 500;
  line-height: 20px;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.cs-article__breadcrumb-link {
  overflow: hidden;
  color: #888b94;
  font-size: 14px;
  font-weight: 500;
  line-height: 20px;
  white-space: nowrap;
  text-overflow: ellipsis;
  text-decoration: none;
}

.cs-article__breadcrumb-link:hover {
  color: #1a1a1a;
  text-decoration: underline;
}

.cs-article__breadcrumb-sep {
  flex-shrink: 0;
  margin: 0 8px;
}

.cs-article__breadcrumb-current {
  overflow: hidden;
  color: #1a1a1a;
  font-size: 14px;
  font-weight: 700;
  line-height: 20px;
  white-space: nowrap;
  text-overflow: ellipsis;
}

/* 真站 detail_mainWrapper：1264px、min-height 200px、flex。
   响应式沿用真站内容宽口径 min(1264px,92vw)（清单页同款）。 */
.cs-article__main {
  display: flex;
  width: min(1264px, 92vw);
  min-height: 200px;
  margin-top: 32px;
}

/* 真站 detail_itemContent：flex 1、margin-left 16px（真站原值）、白卡 radius 8、
   padding 24px 36px。 */
.cs-article__card {
  flex: 1;
  min-width: 0;
  box-sizing: border-box;
  margin-left: 16px;
  padding: 24px 36px;
  border-radius: 8px;
  background: #fff;
}

/* 真站 detail_contentTitle：32px/700/32、#000。 */
.cs-article__title {
  margin: 0;
  color: #000;
  font-size: 32px;
  font-weight: 700;
  line-height: 32px;
}

/* 真站富文本容器（styled-components）：line-height 1.5；块 margin 10px 0。 */
.cs-article__body {
  color: #000;
  font-size: 16px;
  line-height: 24px;
  overflow-wrap: break-word;
}

.cs-article__paragraph {
  margin: 10px 0;
}

/* 真站 ul：disc、padding-left 40px（全局 ul 规则）、margin 10px 0 10px 20px；
   ol decimal 同 margin。 */
.cs-article__list {
  margin: 10px 0 10px 20px;
  padding-left: 40px;
  font-size: 16px;
  line-height: 24px;
}

ul.cs-article__list {
  list-style-type: disc;
}

ol.cs-article__list {
  list-style-type: decimal;
}

/* 真站链接：#0000EE（-webkit-link）+ 下划线。 */
.cs-article__body a {
  color: #0000ee;
  text-decoration: underline;
}

.cs-article__body b {
  font-weight: 700;
}

/* 真站配图：width:100%、height:auto（内联原值）、cursor pointer、hover 阴影。 */
.cs-article__image {
  display: block;
  width: 100%;
  height: auto;
  margin: 10px 0;
  cursor: pointer;
}

.cs-article__image:hover {
  box-shadow: 0 0 5px #333;
}

/* 真站 @768（清单页实测口径）：卡片 padding 收窄、标题降级由内容自然流。 */
@media (max-width: 767px) {
  .cs-article__card {
    padding: 24px 16px;
  }

  .cs-article__title {
    font-size: 24px;
    line-height: 32px;
  }
}
</style>
