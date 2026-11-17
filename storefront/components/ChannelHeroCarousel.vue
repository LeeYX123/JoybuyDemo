<script setup>
// 频道页 hero：管理端配置的轮播图。
// 0 张 → 渐变占位（不报错、不留空白）；1 张 → 静态；多张 → 箭头 + 圆点 +
// 5s 自动轮播（hover / 键盘聚焦时暂停）。尺寸与占位一致：1264×280、r=8。
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { useLocale } from '../composables/useLocale'

const props = defineProps({
  items: {
    type: Array,
    default: () => [],
  },
  fallbackTitle: {
    type: String,
    default: '',
  },
})

const { t } = useLocale()

const index = ref(0)
const paused = ref(false)
const multiple = computed(() => props.items.length > 1)

let timer = null

function clearTimer() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

function syncTimer() {
  clearTimer()
  if (!multiple.value) return
  timer = setInterval(() => {
    if (!paused.value) go(index.value + 1)
  }, 5000)
}

function go(next) {
  const count = props.items.length
  if (!count) return
  index.value = ((next % count) + count) % count
}

function prev() {
  go(index.value - 1)
}

function next() {
  go(index.value + 1)
}

function isInternal(href) {
  return href.startsWith('/') && !href.startsWith('//')
}

function isExternal(href) {
  return /^https?:\/\//i.test(href)
}

watch(
  () => props.items.length,
  () => {
    index.value = 0
    syncTimer()
  },
)

// 只在客户端起定时器：SSR 里 setInterval 会泄漏且没有意义。
onMounted(syncTimer)

onBeforeUnmount(clearTimer)
</script>

<template>
  <div
    v-if="!items.length"
    class="channel-hero"
    aria-hidden="true"
    data-test="channel-hero-placeholder"
  >
    <p class="channel-hero__name">{{ fallbackTitle }}</p>
  </div>

  <div
    v-else
    class="channel-hero channel-hero--carousel"
    role="region"
    :aria-label="fallbackTitle"
    data-test="channel-hero-carousel"
    @mouseenter="paused = true"
    @mouseleave="paused = false"
    @focusin="paused = true"
    @focusout="paused = false"
  >
    <div class="channel-hero__track" :style="{ transform: `translateX(-${index * 100}%)` }">
      <div
        v-for="(item, itemIndex) in items"
        :key="item.id || itemIndex"
        class="channel-hero__slide"
        :aria-hidden="itemIndex !== index"
      >
        <NuxtLink v-if="isInternal(item.href)" :to="item.href" class="channel-hero__link">
          <img :src="item.image_url" alt="" class="channel-hero__img" />
        </NuxtLink>
        <a
          v-else-if="isExternal(item.href)"
          :href="item.href"
          target="_blank"
          rel="noopener"
          class="channel-hero__link"
        >
          <img :src="item.image_url" alt="" class="channel-hero__img" />
        </a>
        <span v-else class="channel-hero__link channel-hero__link--static">
          <img :src="item.image_url" alt="" class="channel-hero__img" />
        </span>
      </div>
    </div>

    <template v-if="multiple">
      <button
        type="button"
        class="channel-hero__arrow channel-hero__arrow--prev"
        :aria-label="t('channel.bannerPrev')"
        @click="prev"
      >
        <span aria-hidden="true">‹</span>
      </button>
      <button
        type="button"
        class="channel-hero__arrow channel-hero__arrow--next"
        :aria-label="t('channel.bannerNext')"
        @click="next"
      >
        <span aria-hidden="true">›</span>
      </button>
      <div class="channel-hero__dots">
        <button
          v-for="(item, itemIndex) in items"
          :key="`dot-${item.id || itemIndex}`"
          type="button"
          class="channel-hero__dot"
          :class="{ 'is-active': itemIndex === index }"
          :aria-label="`${t('channel.bannerDot')} ${itemIndex + 1}`"
          :aria-current="itemIndex === index ? 'true' : undefined"
          @click="go(itemIndex)"
        />
      </div>
    </template>
  </div>
</template>

<style scoped>
/* 与内容区同宽（1264）、高 280px、圆角 8px；无配置时是品牌红→深色渐变占位。
   窄屏按 1264:280 等比收缩；≤48rem 改固定高度（比例会过扁）。 */
.channel-hero {
  position: relative;
  display: flex;
  align-items: flex-end;
  aspect-ratio: 1264 / 280;
  max-height: 280px;
  margin-bottom: var(--space-8);
  padding: var(--space-5);
  border-radius: var(--radius-md);
  overflow: hidden;
  background: linear-gradient(120deg, #c8102e 0%, #7a0d20 55%, #1a1a1a 100%);
}

@media (max-width: 48rem) {
  .channel-hero {
    aspect-ratio: auto;
    height: 160px;
  }
}

.channel-hero--carousel {
  display: block;
  padding: 0;
}

.channel-hero__name {
  margin: 0;
  color: rgb(255 255 255 / 72%);
  font-size: 2.5rem;
  font-weight: var(--font-weight-bold);
  letter-spacing: 0.02em;
}

@media (max-width: 48rem) {
  .channel-hero__name {
    font-size: 1.75rem;
  }
}

.channel-hero__track {
  display: flex;
  height: 100%;
  transition: transform 0.4s ease;
}

.channel-hero__slide {
  flex: 0 0 100%;
  height: 100%;
}

.channel-hero__link {
  display: block;
  width: 100%;
  height: 100%;
}

.channel-hero__link--static {
  cursor: default;
}

.channel-hero__img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.channel-hero__arrow {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  height: 2.25rem;
  padding: 0;
  border: 1px solid rgb(255 255 255 / 45%);
  border-radius: var(--radius-pill);
  background: rgb(0 0 0 / 35%);
  color: #fff;
  font-size: 1.25rem;
  line-height: 1;
  cursor: pointer;
}

.channel-hero__arrow:hover {
  background: rgb(0 0 0 / 55%);
}

.channel-hero__arrow--prev {
  left: var(--space-3);
}

.channel-hero__arrow--next {
  right: var(--space-3);
}

.channel-hero__dots {
  position: absolute;
  bottom: var(--space-3);
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 8px;
}

.channel-hero__dot {
  width: 0.5rem;
  height: 0.5rem;
  padding: 0;
  border: none;
  border-radius: var(--radius-pill);
  background: rgb(255 255 255 / 55%);
  cursor: pointer;
}

.channel-hero__dot.is-active {
  width: 1.25rem;
  background: #fff;
}
</style>
