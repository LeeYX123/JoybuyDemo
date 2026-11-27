<script setup>
import { computed } from 'vue'

import { useLocale } from '../../composables/useLocale'
import { pickName } from '../../locales/messages'

// Home "Weekly picks" floor (需求文档03 14.2). Measured from the live site
// pc-theme-module (2026-11-20 CSS bundle): 28px/600 title, square cards in a
// 16px-gap row, each card is a full-bleed image with a bottom gradient mask
// and a 20px/700 white title, linking to the activity landing page.
const props = defineProps({
  payload: {
    type: Object,
    required: true,
  },
})

const { t, locale } = useLocale()

const items = computed(() =>
  (Array.isArray(props.payload.items) ? props.payload.items : []).filter(
    (item) => item && typeof item.title === 'string' && item.title.trim(),
  ),
)

const heading = computed(() => {
  if (locale.value === 'zh' && props.payload.title_zh) return props.payload.title_zh
  return props.payload.title || t('home.weekly.title')
})

function itemTitle(item) {
  return pickName(item, locale.value, 'title')
}

function itemSubtitle(item) {
  return locale.value === 'zh' && item.subtitle_zh ? item.subtitle_zh : item.subtitle
}
</script>

<template>
  <section class="weekly-picks" aria-labelledby="weekly-picks-title">
    <h2 id="weekly-picks-title" class="weekly-picks__title">{{ heading }}</h2>
    <ul class="weekly-picks__list">
      <li v-for="item in items" :key="item.title" class="weekly-picks__item">
        <NuxtLink v-if="item.href" class="weekly-picks__card" :to="item.href">
          <img v-if="item.image_path" :src="item.image_path" alt="" loading="lazy" />
          <span class="weekly-picks__mask" aria-hidden="true"></span>
          <span class="weekly-picks__text">
            <strong class="weekly-picks__card-title">{{ itemTitle(item) }}</strong>
            <span v-if="item.subtitle" class="weekly-picks__card-subtitle">{{
              itemSubtitle(item)
            }}</span>
          </span>
        </NuxtLink>
        <span v-else class="weekly-picks__card">
          <img v-if="item.image_path" :src="item.image_path" alt="" loading="lazy" />
          <span class="weekly-picks__mask" aria-hidden="true"></span>
          <span class="weekly-picks__text">
            <strong class="weekly-picks__card-title">{{ itemTitle(item) }}</strong>
          </span>
        </span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.weekly-picks {
  width: 100%;
  background: #fff;
}

.weekly-picks__title {
  margin: 0;
  color: #1a1a1a;
  font-size: 28px;
  font-weight: 600;
  line-height: 42px;
  text-align: start;
}

.weekly-picks__list {
  display: grid;
  /* 2026-11-27：模块换成 4 张本地营销页卡，与真站每周甄选 4 卡一排一致。 */
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-top: 16px;
  padding: 0;
  list-style: none;
}

.weekly-picks__item {
  min-width: 0;
}

.weekly-picks__card {
  position: relative;
  display: block;
  aspect-ratio: 1;
  overflow: hidden;
  border-radius: 8px;
  background: #f5f6fa;
  text-decoration: none;
}

.weekly-picks__card img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s ease;
  transform-origin: center center;
}

.weekly-picks__card:hover img {
  transform: scale(1.1);
}

.weekly-picks__mask {
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, transparent 51.92%, rgb(0 0 0 / 40%));
  pointer-events: none;
}

.weekly-picks__text {
  position: absolute;
  z-index: 1;
  bottom: 16px;
  left: 16px;
  display: grid;
  gap: 2px;
  width: calc(100% - 32px);
}

.weekly-picks__card-title {
  overflow: visible;
  color: #fff;
  font-size: 20px;
  font-weight: 700;
  line-height: 36px;

  display: block;

  word-break: break-word;
}

.weekly-picks__card-subtitle {
  overflow: visible;
  color: rgb(255 255 255 / 88%);
  font-size: 14px;
  font-weight: 500;
  line-height: 20px;

  white-space: normal;
  word-break: break-word;
}

@media (max-width: 64rem) {
  .weekly-picks__list {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 48rem) {
  .weekly-picks__list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
