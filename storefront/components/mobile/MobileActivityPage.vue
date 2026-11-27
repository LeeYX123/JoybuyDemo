<script setup>
// 活动页 / 店铺页（手机版 m. 站，2026-11-25）。
// 与桌面版同一份数据；2 列网格、hero 满宽、楼层标题 20/700。
import { computed, reactive } from 'vue'

import { useLocale } from '../../composables/useLocale'

const props = defineProps({
  page: { type: Object, required: true },
  kind: { type: String, default: 'activity' },
})

const { t, locale } = useLocale()
const FIRST_BATCH = 4
const revealAll = reactive({})

const sections = computed(() => props.page?.sections || [])

function sectionTitle(section) {
  return locale.value === 'zh' && section.title_zh ? section.title_zh : section.title
}

// 与桌面同口径：真站标题是 floorTitle 模块，配色按页面配置（有底色→通栏条）。
function titleStyle(section) {
  const style = {}
  if (section.title_background) {
    style.background = section.title_background
    style.padding = '12px 0'
  }
  style.color = section.title_color || '#a33838'
  return style
}

function visibleProducts(section) {
  const items = section.products || []
  if (props.kind === 'store') return items
  // show_more=false = 真站该层平铺全部商品，直接展示（与桌面 ActivityPageView
  // 同口径，2026-11-27 修复 2wPM8 只出首屏 4 件的问题）。
  if (!section.show_more) return items
  return revealAll[section.public_id] ? items : items.slice(0, FIRST_BATCH)
}

function hasMore(section) {
  if (props.kind === 'store') return false
  return (section.products || []).length > FIRST_BATCH && !revealAll[section.public_id]
}

function priceLabel(product) {
  if (!product?.price) return ''
  const symbol = product.currency === 'GBP' ? '£' : ''
  const [integer, decimals] = String(product.price).split('.')
  return `${symbol}${integer}.${(decimals === undefined ? '00' : decimals).padEnd(2, '0').slice(0, 2)}`
}
</script>

<template>
  <div class="m-activity">
    <img v-if="page.hero_image" class="m-activity__hero" :src="page.hero_image" :alt="page.title" />
    <h1 v-if="kind === 'store' && page.store_name" class="m-activity__store">
      {{ page.store_name }}
    </h1>

    <section v-for="section in sections" :key="section.public_id" class="m-activity__section">
      <template v-if="section.kind === 'BANNER'">
        <NuxtLink v-if="section.href" :to="section.href">
          <img class="m-activity__banner" :src="section.image_url" alt="" loading="lazy" />
        </NuxtLink>
        <img v-else class="m-activity__banner" :src="section.image_url" alt="" loading="lazy" />
      </template>

      <template v-else>
        <h2
          v-if="sectionTitle(section)"
          class="m-activity__title"
          :class="{ 'm-activity__title--bar': !!section.title_background }"
          :style="titleStyle(section)"
        >
          {{ sectionTitle(section) }}
        </h2>
        <ul class="m-activity__grid">
          <li v-for="product in visibleProducts(section)" :key="product.item_key || product.spu_public_id">
            <NuxtLink class="m-activity__card" :to="product.href">
              <img v-if="product.image_path" :src="product.image_path" :alt="product.title" loading="lazy" />
              <span class="m-activity__name">{{ product.title }}</span>
              <span v-if="priceLabel(product)" class="m-activity__price">{{ priceLabel(product) }}</span>
            </NuxtLink>
          </li>
        </ul>
        <div v-if="section.show_more && hasMore(section)" class="m-activity__more">
          <button type="button" @click="revealAll[section.public_id] = true">
            {{ t('activity.viewMore') }}
          </button>
        </div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.m-activity {
  background: #fff;
  padding-bottom: 24px;
}

.m-activity__hero {
  display: block;
  width: 100%;
  height: auto;
}

.m-activity__store {
  margin: 14px 16px 2px;
  font-size: 20px;
  font-weight: 700;
  color: #1a1a1a;
}

.m-activity__section {
  padding: 0 12px;
  margin-top: 28px;
}

.m-activity__banner {
  display: block;
  width: calc(100% + 24px);
  margin-inline: -12px;
  height: auto;
}

.m-activity__title {
  margin: 0 0 20px;
  font-size: 22px;
  font-weight: 700;
  line-height: 28px;
  color: #a33838;
  text-align: center;
}

.m-activity__title--bar {
  margin-bottom: 14px;
}

.m-activity__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.m-activity__card {
  display: flex;
  flex-direction: column;
  padding: 6px;
  border-radius: 10px;
  background: #fff;
  color: inherit;
  text-decoration: none;
}

.m-activity__card img {
  border-radius: 6px;
  background: #f5f5f5;
  padding: 5px;
  width: 100%;
  aspect-ratio: 1;
  object-fit: contain;
  border-radius: 8px;
}

.m-activity__name {
  margin-top: 8px;
  font-size: 13px;
  font-weight: 500;
  line-height: 18px;
  color: #1a1a1a;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.m-activity__price {
  margin-top: 6px;
  font-size: 16px;
  font-weight: 700;
  color: #e1251b;
}

.m-activity__more {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}

/* 与桌面同款：黑底白字实心胶囊（真站 View more 移动端同色系）。 */
.m-activity__more button {
  display: block;
  padding: 10px 32px;
  border: 0;
  border-radius: 22px;
  background: #000;
  color: #fff;
  font-size: 14px;
  font-weight: 400;
  line-height: 21px;
  cursor: pointer;
}
</style>
