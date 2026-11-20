<script setup>
import { computed } from 'vue'

import { helpNav, helpPageBySlug, helpPagePath } from '../content/helpPages'
import { useLocale } from '../composables/useLocale'

// 批次 Q（需求 15.1）：真站 help 中心版式 —— 左栏政策/条款 tab 列表 + 右栏内容。
// 版式与字号全部来自 2026-11-20 真站实测（var/policy_help_20261120/measure_nav.json）：
//   容器 1264、左栏 240（padding 4/12、圆角 8、白底）、间距 16、右卡 padding 24/36、
//   条目 16px/400/24 + 上下内边距 16/20、分隔线 1px #F0F1F2、选中/悬停文字 #FF0F23、
//   悬停底 #F5F6FA、正文 16px/24px、标题 32px/700/32px、表格 td 3px/5px + 1px #CCC 右边下边。
// 与真站的唯一差异：左栏改为 sticky（真站为 static，见 HANDOFF 0ad）。
const props = defineProps({
  slug: { type: String, required: true },
})

const { locale } = useLocale()

const page = computed(() => helpPageBySlug[props.slug] || null)
const title = computed(() => page.value.title[locale.value] || page.value.title.en)
const blocks = computed(() => page.value.blocks[locale.value] || page.value.blocks.en)
const ARCHIVE_LABEL = { en: 'Archived Version', zh: '存档版本' }
const archiveLabel = computed(() => ARCHIVE_LABEL[locale.value] || ARCHIVE_LABEL.en)

function label(item) {
  return item.title[locale.value] || item.title.en
}
</script>

<template>
  <div class="help-center">
    <div class="help-center__inner">
      <nav class="help-center__nav" :aria-label="title">
        <ul class="help-center__nav-list">
          <li v-for="item in helpNav" :key="item.slug" class="help-center__nav-item">
            <NuxtLink
              class="help-center__nav-link"
              :class="{ 'help-center__nav-link--active': item.slug === slug }"
              :to="helpPagePath(item.slug)"
              :aria-current="item.slug === slug ? 'page' : undefined"
            >
              {{ label(item) }}
            </NuxtLink>
          </li>
        </ul>
      </nav>

      <article class="help-center__content">
        <div class="help-center__head">
          <h1 class="help-center__title">{{ title }}</h1>
          <span v-if="page.hasArchive" class="help-center__archive">
            <svg
              class="help-center__archive-icon"
              viewBox="0 0 28 28"
              width="28"
              height="28"
              aria-hidden="true"
            >
              <path
                fill="#1A1A1A"
                d="M20.7 18.6v-1.8a.53.53 0 0 0-.52-.53c-.33 0-.57.27-.57.6v2.47c0 .19.16.35.35.35h1.96c.31 0 .57-.25.56-.56a.55.55 0 0 0-.6-.53Zm-11.76-8.22h7.25c.37 0 .67-.3.66-.68a.68.68 0 0 0-.67-.64H8.96a.68.68 0 0 0-.68.63.67.67 0 0 0 .19.5.67.67 0 0 0 .47.19Zm4.8 2.65a.66.66 0 0 0-.66-.66h-4.13a.66.66 0 0 0-.66.6.66.66 0 0 0 .65.71h4.15c.36.01.65-.29.65-.65Z"
              />
              <path
                fill="#1A1A1A"
                d="M15.33 21.84H7.81a1.04 1.04 0 0 1-1.03-1.03V6.97c0-.56.47-1.03 1.03-1.03h10.81c.56 0 1.03.47 1.03 1.03v5.23a.71.71 0 0 0 .63.71.7.7 0 0 0 .76-.7V6.97a2.43 2.43 0 0 0-2.42-2.43H7.81a2.42 2.42 0 0 0-2.42 2.3v14.1a2.42 2.42 0 0 0 2.42 2.3h7.5c.35 0 .66-.25.7-.6a.7.7 0 0 0-.68-.8Z"
              />
              <path
                fill="#1A1A1A"
                d="M20.35 13.77a4.74 4.74 0 0 0-4.74 4.77 4.7 4.7 0 0 0 4.7 4.7 4.74 4.74 0 0 0 4.77-4.73 4.74 4.74 0 0 0-4.73-4.74Zm3.43 4.73a3.44 3.44 0 0 1-3.48 3.43 3.44 3.44 0 0 1-3.39-3.37 3.44 3.44 0 0 1 3.44-3.49 3.43 3.43 0 0 1 3.43 3.43Z"
              />
            </svg>
            <span>{{ archiveLabel }}</span>
          </span>
        </div>

        <div class="help-center__body">
          <template v-for="(block, index) in blocks" :key="index">
            <div v-if="block.type === 'table'" class="help-center__table-wrap">
              <table class="help-center__table">
                <tbody>
                  <tr v-for="(row, rowIndex) in block.rows" :key="rowIndex">
                    <td
                      v-for="(cell, cellIndex) in row"
                      :key="cellIndex"
                      :class="{
                        'help-center__table-cell--bold': block.firstColBold && cellIndex === 0,
                      }"
                    >
                      {{ cell }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <component
              :is="block.ordered ? 'ol' : 'ul'"
              v-else-if="block.type === 'list'"
              class="help-center__list"
            >
              <li v-for="(item, itemIndex) in block.items" :key="itemIndex">
                <template v-for="(seg, segIndex) in item" :key="segIndex">
                  <br v-if="seg.br" />
                  <a v-else-if="seg.href" :href="seg.href">{{ seg.t }}</a>
                  <b v-else-if="seg.b">{{ seg.t }}</b>
                  <i v-else-if="seg.i">{{ seg.t }}</i>
                  <span v-else>{{ seg.t }}</span>
                </template>
              </li>
            </component>
            <img
              v-else-if="block.type === 'image'"
              class="help-center__image"
              :src="block.src"
              :alt="block.alt"
              loading="lazy"
            />
            <p
              v-else
              class="help-center__paragraph"
              :style="block.align === 'justify' ? { textAlign: 'justify' } : undefined"
            >
              <template v-for="(seg, segIndex) in block.segments" :key="segIndex">
                <br v-if="seg.br" />
                <a v-else-if="seg.href" :href="seg.href">{{ seg.t }}</a>
                <b v-else-if="seg.b">{{ seg.t }}</b>
                <i v-else-if="seg.i">{{ seg.t }}</i>
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
.help-center {
  padding: 32px 24px;
  background: #f5f6fa;
}

.help-center__inner {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  max-width: 1264px;
  margin-inline: auto;
}

/* 左栏：真站 240 宽、白底圆角 8、padding 4px 12px，条目间 1px 分隔线。 */
.help-center__nav {
  position: sticky;
  top: 16px;
  flex: 0 0 240px;
  box-sizing: border-box;
  padding: 4px 12px;
  border-radius: 8px;
  background: #fff;
}

.help-center__nav-list {
  margin: 0;
  padding: 8px 0;
  list-style: none;
}

.help-center__nav-link {
  display: block;
  padding: 16px 16px 20px;
  border-bottom: 1px solid #f0f1f2;
  color: #000;
  font-size: 16px;
  font-weight: 400;
  line-height: 24px;
  text-decoration: none;
  transition: background-color 0.15s cubic-bezier(0.4, 0, 0.2, 1);
}

.help-center__nav-item:last-child .help-center__nav-link {
  border-bottom: 0;
}

.help-center__nav-link:hover {
  background: #f5f6fa;
  color: #ff0f23;
}

.help-center__nav-link--active,
.help-center__nav-link--active:hover {
  background: #fff;
  color: #ff0f23;
}

.help-center__content {
  flex: 1 1 auto;
  min-width: 0;
  box-sizing: border-box;
  padding: 24px 36px;
  border-radius: 8px;
  background: #fff;
}

.help-center__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.help-center__title {
  margin: 0;
  color: #000;
  font-size: 32px;
  font-weight: 700;
  line-height: 32px;
}

.help-center__archive {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  color: #1a1a1a;
  font-size: 16px;
  font-weight: 400;
  line-height: 20px;
}

.help-center__archive-icon {
  display: block;
}

.help-center__body {
  color: #000;
  font-size: 16px;
  line-height: 24px;
  overflow-wrap: break-word;
}

.help-center__paragraph {
  margin: 10px 0;
}

/* 真站帮助文章内嵌配图：width:100%、height:auto（仅新增 image 块使用）。 */
.help-center__image {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 10px 0;
}

/* 真站 ol/ul 用的是浏览器默认样式（margin 16px 0、padding-left 40px、decimal/disc）；
   本地 base.css 全局重置了 list-style，这里显式恢复序号/圆点。 */
.help-center__list {
  margin: 16px 0;
  padding-left: 40px;
  font-size: 16px;
  line-height: 24px;
}

ol.help-center__list {
  list-style-type: decimal;
}

ul.help-center__list {
  list-style-type: disc;
}

.help-center__body a {
  color: #0000ee;
  text-decoration: underline;
}

.help-center__body b {
  font-weight: 700;
}

/* 真站表格（2026-11-20 实测）：整宽、自动列宽；table 自带 top/left 1px #CCC 外边，
   td 右/下 1px #CCC —— 拼成完整四边外框 + 内格线，无重复双线。 */
.help-center__table-wrap {
  margin: 10px 0;
  overflow-x: auto;
}

.help-center__table {
  width: 100%;
  box-sizing: border-box;
  border-top: 1px solid #ccc;
  border-left: 1px solid #ccc;
  border-collapse: collapse;
  table-layout: auto;
}

.help-center__table td {
  padding: 3px 5px;
  border-right: 1px solid #ccc;
  border-bottom: 1px solid #ccc;
  vertical-align: middle;
  white-space: pre-line;
}

/* 仅销售条款「第1条 定义」表（数据层 firstColBold）首列加粗，真站该列单元格内为 <b>。 */
.help-center__table td.help-center__table-cell--bold {
  font-weight: 700;
}

@media (max-width: 1023px) {
  .help-center {
    padding: 24px 16px;
  }

  .help-center__nav {
    flex-basis: 200px;
  }

  .help-center__content {
    padding: 24px;
  }
}

/* 真站无移动版（左栏恒 240、整页横向溢出）；本地在窄屏改为上下堆叠，保证内容不挤压。 */
@media (max-width: 767px) {
  .help-center {
    padding: 16px;
  }

  .help-center__inner {
    flex-direction: column;
    gap: 12px;
  }

  .help-center__nav {
    position: static;
    flex: 0 0 auto;
    width: 100%;
  }

  .help-center__content {
    width: 100%;
    padding: 20px;
  }

  .help-center__title {
    font-size: 24px;
    line-height: 32px;
  }
}
</style>
