<script setup>
import { computed } from 'vue'

import { helpPageBySlug, helpPagePath } from '../content/helpPages'
import { useLocale } from '../composables/useLocale'
import { noAutofillSearch } from '../utils/noAutofill'

// 批次 U（需求 17.5）：真站 customer-service 分类页版式（/customer-service/<Category>，
// 如 Checkout & Payments / Returns & Refunds）。结构与字号全部来自 2026-11-20 真站实测
// （var/customer_service_20261120/measurement.md，DOM + 真站 emotion/CSS 规则逐条对照）：
//   页面底 #F5F6FA、内容宽 min(1264px,92vw)、面包屑 14px（根 #888B94 / 当前 #1A1A1A 700）、
//   标题卡 24px/700 白卡 padding 16/24 radius 8、文章白卡 margin-top 16 padding 16、
//   行 padding 15px 0 + 0.5px #E0E1E5 分隔（末行无）、行文字 16px/400/22 hover 下划线、
//   类目标题 20px/600/26 #1E1E1E、chips 3 列 gap 8（白卡 padding 22/16，文字 16px/600）、
//   右栏白卡 319px（1200–1599；840–1199→245、1600+→360）+ 搜索框 36 高 #F5F6FA +
//   Online chat 按钮 40 高 1px #1A1A1A。
// 与真站的既知差异（见 measurement.md 第六节）：
//   1. 真站本页无站点页脚；本地 footer-page 布局固定带 AppFooter（layouts 本批次禁改）。
//   2. 真站面包屑根节点链到 /customer-service-centre，本地无此页 → 同款灰色文本非链接。
//   3. 真站文章行跳文章详情页；批次 0am（2026-11-20）起本地 16 篇详情页齐备
//      （/help/<slug>，真站 URL 形态，正文见 content/help/csArticles.js）→ 行改为可点链接；
//      chips 可跳分类页，本地仅互为对方分类的 chip 互链。
//   4. 搜索框 / Online chat 按钮视觉 1:1，不接真站客服系统。
//   5. 联系行邮箱按 16.5 口径替换为 Joybuyfumi@gmail.com。
const props = defineProps({
  slug: { type: String, required: true },
})

const { locale, t } = useLocale()

const page = computed(() => helpPageBySlug[props.slug] || null)
const cs = computed(() => (page.value && page.value.customerService) || null)
const category = computed(() => cs.value.category[locale.value] || cs.value.category.en)
// 批次 0am：行带真站文章 slug，详情页路由 /help/<slug>（真站 URL 形态）。
const articles = computed(() =>
  cs.value.articles.map((a) => ({ label: a[locale.value] || a.en, slug: a.slug })),
)
const categories = computed(() =>
  cs.value.categories.map((c) => ({ label: c[locale.value] || c.en, slug: c.slug || null })),
)
const CONTACT_EMAIL = 'Joybuyfumi@gmail.com'
</script>

<template>
  <div class="cs-page">
    <nav class="cs-page__breadcrumb" aria-label="breadcrumb">
      <span class="cs-page__breadcrumb-root">{{ t('help.csBreadcrumbRoot') }}</span>
      <svg
        class="cs-page__breadcrumb-sep"
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
      <span class="cs-page__breadcrumb-current">{{ category }}</span>
    </nav>

    <div class="cs-page__header">
      <div class="cs-page__main">
        <h1 class="cs-page__title">{{ category }}</h1>

        <div class="cs-page__articles">
          <NuxtLink
            v-for="(article, index) in articles"
            :key="article.slug"
            class="cs-page__article-row"
            :class="{ 'cs-page__article-row--last': index === articles.length - 1 }"
            :to="`/help/${article.slug}`"
          >
            <p class="cs-page__article-text">{{ article.label }}</p>
          </NuxtLink>
        </div>

        <div class="cs-page__browse">
          <h2 class="cs-page__browse-title">{{ t('help.csBrowseTitle') }}</h2>
          <div class="cs-page__categories">
            <template v-for="item in categories" :key="item.label">
              <NuxtLink v-if="item.slug" class="cs-page__chip" :to="helpPagePath(item.slug)">
                <span class="cs-page__chip-text">{{ item.label }}</span>
              </NuxtLink>
              <div v-else class="cs-page__chip">
                <span class="cs-page__chip-text">{{ item.label }}</span>
              </div>
            </template>
          </div>
        </div>
      </div>

      <aside class="cs-page__aside">
        <p class="cs-page__service-title">{{ t('help.csServiceTitle') }}</p>
        <div class="cs-page__search">
          <input
            class="cs-page__search-input"
            type="text"
            :placeholder="t('help.csSearchPlaceholder')"
            :aria-label="t('help.csSearchLabel')"
            v-bind="noAutofillSearch"
          />
          <button class="cs-page__search-btn" type="button" :aria-label="t('help.csSearchLabel')">
            <svg viewBox="0 0 17 17" width="17" height="17" fill="none" aria-hidden="true">
              <circle cx="8" cy="8" r="7.25" stroke="#1A1A1A" stroke-width="1.5" />
              <path stroke="#1A1A1A" stroke-width="1.5" d="M13.5 13.5 16 16" />
            </svg>
          </button>
        </div>
        <button class="cs-page__chat" type="button">
          <svg viewBox="0 0 17 17" width="20" height="20" fill="none" aria-hidden="true">
            <path
              fill="#1A1A1A"
              d="M13.958 9.253a1.98 1.98 0 0 0 2.108.533 2.082 2.082 0 0 1-1.028 3.496 8.35 8.35 0 0 1-6.705 3.384v-1.667c1.95 0 3.759-.853 5-2.257V9.709a2 2 0 0 0 .625-.456M8.333 0c.718 0 1.409.115 2.058.326a3.74 3.74 0 0 1-1.198 1.416 5.005 5.005 0 0 0-5.86 4.925v6.25a2.083 2.083 0 1 1-1.667-3.708V6.666A6.674 6.674 0 0 1 8.334 0M12.5.104c.127 0 .242.077.29.195l.18.444a5.4 5.4 0 0 0 2.954 2.953l.444.181a.313.313 0 0 1 0 .58l-.444.18a5.4 5.4 0 0 0-2.953 2.954l-.181.443a.313.313 0 0 1-.58 0l-.18-.443a5.4 5.4 0 0 0-2.954-2.954l-.444-.18a.313.313 0 0 1 0-.58l.444-.181A5.4 5.4 0 0 0 12.029.743l.181-.444a.31.31 0 0 1 .29-.195M15.418 5.939c.13 0 .249.082.293.206l.037.102a.84.84 0 0 0 .506.506l.102.037a.313.313 0 0 1 0 .587l-.102.037a.84.84 0 0 0-.506.506l-.037.102a.313.313 0 0 1-.587 0l-.037-.102a.84.84 0 0 0-.506-.506l-.102-.037a.313.313 0 0 1 0-.587l.102-.037a.84.84 0 0 0 .507-.506l.036-.102a.31.31 0 0 1 .294-.206"
            />
          </svg>
          <span>{{ t('help.csOnlineChat') }}</span>
        </button>
      </aside>
    </div>

    <div class="cs-page__contact">
      <svg
        class="cs-page__contact-icon"
        viewBox="0 0 20 20"
        width="20"
        height="20"
        fill="none"
        aria-hidden="true"
      >
        <path
          stroke="#505259"
          stroke-linejoin="round"
          stroke-width="1.2"
          d="M1.5 4.5A1.5 1.5 0 0 1 3 3h14a1.5 1.5 0 0 1 1.5 1.5v11A1.5 1.5 0 0 1 17 17H3a1.5 1.5 0 0 1-1.5-1.5z"
        />
        <path
          stroke="#505259"
          stroke-linecap="square"
          stroke-width="1.2"
          d="m18 5-6.727 6.727a1.8 1.8 0 0 1-2.546 0L2 5"
        />
      </svg>
      <span class="cs-page__contact-label">{{ t('help.csServiceContact') }}</span>
      <a class="cs-page__contact-email" :href="`mailto:${CONTACT_EMAIL}`">{{ CONTACT_EMAIL }}</a>
    </div>
  </div>
</template>

<style scoped>
.cs-page {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-height: calc(100vh - 108px);
  padding-bottom: 88px;
  background: #f5f6fa;
}

/* 真站面包屑：宽 min(1264px,92vw)、margin-top 32px；根 14px/500 #888B94、
   当前项 14px/700 #1A1A1A、chevron 20px #C2C4CC 间距 8px。 */
.cs-page__breadcrumb {
  display: flex;
  align-items: center;
  width: min(1264px, 92vw);
  margin-top: 32px;
}

.cs-page__breadcrumb-root {
  overflow: visible;
  color: #888b94;
  font-size: 14px;
  font-weight: 500;
  line-height: 20px;
  white-space: normal;
  word-break: break-word;
}

.cs-page__breadcrumb-sep {
  flex-shrink: 0;
  margin: 0 8px;
}

.cs-page__breadcrumb-current {
  overflow: visible;
  color: #1a1a1a;
  font-size: 14px;
  font-weight: 700;
  line-height: 20px;
  white-space: normal;
  word-break: break-word;
}

/* 主区：宽 min(1264px,92vw)、flex space-between、gap 16、margin-top 32。 */
.cs-page__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  width: min(1264px, 92vw);
  margin-top: 32px;
}

.cs-page__main {
  flex: 1;
  min-width: 0;
}

/* 真站标题卡：24px/700/32，白底 radius 8，padding 16px 24px。 */
.cs-page__title {
  margin: 0;
  padding: 16px 24px;
  border-radius: 8px;
  background: #fff;
  box-sizing: border-box;
  color: #1a1a1a;
  font-size: 24px;
  font-weight: 700;
  line-height: 32px;
}

/* 真站文章列表卡：margin-top 16、padding 16、radius 8；
   行 padding 15px 0 + 0.5px #E0E1E5 下分隔（末行无），hover 下划线（真站行可点）。 */
.cs-page__articles {
  margin-top: 16px;
  padding: 16px;
  border-radius: 8px;
  background: #fff;
  box-sizing: border-box;
}

.cs-page__article-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 15px 0;
  border-bottom: 0.5px solid #e0e1e5;
  color: inherit;
  cursor: pointer;
  text-decoration: none;
}

.cs-page__article-row:hover .cs-page__article-text {
  text-decoration: underline;
  text-underline-position: from-font;
  text-decoration-skip-ink: none;
}

.cs-page__article-row--last {
  border-bottom: none;
}

.cs-page__article-text {
  flex: 1;
  min-width: 0;
  margin: 0;
  color: #1a1a1a;
  font-size: 16px;
  font-weight: 400;
  line-height: 22px;
}

/* 真站 Browse 区：margin-top 17、标题 20px/600/26 #1E1E1E、chips margin-top 16。 */
.cs-page__browse {
  width: 100%;
  margin-top: 17px;
}

.cs-page__browse-title {
  margin: 0;
  color: #1e1e1e;
  font-size: 20px;
  font-weight: 600;
  line-height: 26px;
}

/* 真站 chips：flex wrap gap 8，每项 calc(33.333% - 5.4px)（max 405px），
   白卡 radius 8 padding 22px 16px，文字 16px/600/22 #1A1A1A。 */
.cs-page__categories {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  width: 100%;
  margin-top: 16px;
}

.cs-page__chip {
  display: flex;
  flex: 0 0 calc(33.333% - 5.4px);
  max-width: 405px;
  box-sizing: border-box;
  align-items: center;
  padding: 22px 16px;
  border-radius: 8px;
  background: #fff;
  color: #1a1a1a;
  text-decoration: none;
}

.cs-page__chip:hover .cs-page__chip-text {
  text-decoration: underline;
  text-underline-position: from-font;
  text-decoration-skip-ink: none;
}

.cs-page__chip-text {
  margin-left: 8px;
  color: #1a1a1a;
  font-size: 16px;
  font-weight: 600;
  line-height: 22px;
}

/* 真站右栏白卡：宽 319（1200–1599）/ 245（840–1199）/ 360（1600+），
   padding 16、radius 8，纵向排布。 */
.cs-page__aside {
  display: flex;
  flex: 0 0 319px;
  box-sizing: border-box;
  flex-direction: column;
  align-self: flex-start;
  padding: 16px;
  border-radius: 8px;
  background: #fff;
}

.cs-page__service-title {
  margin: 0;
  color: #000;
  font-size: 16px;
  font-weight: 400;
  line-height: 24px;
}

/* 真站搜索框：margin-top 16、高 36、bg #F5F6FA、radius 4、无边框、
   文字/占位 14px（占位 #C2C4CC），右侧 17px 放大镜。 */
.cs-page__search {
  display: flex;
  align-items: center;
  height: 36px;
  margin-top: 16px;
  padding: 0 12px;
  border-radius: 4px;
  background: #f5f6fa;
}

.cs-page__search:focus-within {
  outline: 1px solid #1a1a1a;
}

.cs-page__search-input {
  flex: 1;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: rgba(0, 0, 0, 0.87);
  font-size: 14px;
  line-height: 22px;
}

.cs-page__search-input::placeholder {
  color: #c2c4cc;
  opacity: 1;
}

.cs-page__search-btn {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
}

/* 真站 Online chat 按钮：margin-top 16、宽 100%、高 40、radius 4、
   1px #1A1A1A 边框白底、16px/600、左 20px 图标、hover #efefef。 */
.cs-page__chat {
  display: flex;
  width: 100%;
  height: 40px;
  margin-top: 16px;
  padding: 8px 16px;
  box-sizing: border-box;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 1px solid #1a1a1a;
  border-radius: 4px;
  background: #fff;
  color: #1a1a1a;
  cursor: pointer;
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
}

.cs-page__chat:hover {
  background: #efefef;
}

/* 真站联系行：整宽居中、14px/500/20 #000、信封 20px #505259 间距 12、
   邮箱下划线（16.5 口径替换为 Joybuyfumi@gmail.com）。
   真站 wrapper 为 min-height calc(100vh-108px) 的 flex 纵向容器，联系行贴底
   （实测 1440 视口联系行 y≈1219 ≈ wrapper 底），用 margin-top:auto 复现。 */
.cs-page__contact {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  margin-top: auto;
  padding-top: 24px;
  color: #000;
  font-size: 14px;
  font-weight: 500;
  line-height: 20px;
}

.cs-page__contact-icon {
  flex-shrink: 0;
  margin-right: 12px;
}

.cs-page__contact-email {
  color: inherit;
  text-decoration: underline;
  text-underline-position: from-font;
  text-decoration-skip-ink: none;
}

/* 真站响应式：840–1199 右栏 245；chips 两列（媒体查询上下文为推定，见 measurement.md）。 */
@media (min-width: 840px) and (max-width: 1199px) {
  .cs-page__aside {
    flex-basis: 245px;
  }

  .cs-page__chip {
    flex-basis: calc(50% - 12px);
    max-width: none;
  }
}

/* 真站 @768：面包屑与 header 间距 16、底部留白 80；chips 单列（推定）。 */
@media (max-width: 839px) {
  .cs-page {
    padding-bottom: 80px;
  }

  .cs-page__breadcrumb,
  .cs-page__header {
    margin-top: 16px;
  }

  .cs-page__chip {
    flex-basis: 100%;
    max-width: none;
  }

  .cs-page__header {
    flex-direction: column;
  }

  .cs-page__aside {
    flex-basis: auto;
    width: 100%;
  }
}
</style>
