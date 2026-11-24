<script setup>
// 频道页活动卡片「一组」（2026-11-23 多组契约）。
//
// 数据由 ChannelPageCards 归一化后按组传进来（items 已按 sort_order 排好），
// 本组件只负责按 layout 渲染一组：
//   行内 gap 17（三种布局外层同口径，真站 .adsModule display:flex; gap:17px）；
//   - row2        两列平铺 620×200，gap 24，无箭头不可滑；
//   - row3        三列平铺 410×200，gap 17，无箭头不可滑；
//   - row3_scroll 一屏 3 张 400.66×195.44，gap 31，可横滑，
//     hover 显示 40×48 半透明黑箭头（与真站 .buttonGroup 同口径）。
// 图片 cover 铺满 + 8px 圆角；lazy 加载。
// 跳转按 13.8 链接规则：http(s)://、//、www. 开头视为外链（新窗口 + noopener），
// 其余视为站内路径（NuxtLink）；空链接整张不可点。
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { useLocale } from '../composables/useLocale'

const props = defineProps({
  items: {
    type: Array,
    default: () => [],
  },
  // 'row2' | 'row3' | 'row3_scroll'（未知值退回 row3，见 utils/channelCards.js）。
  layout: {
    type: String,
    default: 'row3',
  },
})

const { t } = useLocale()

const cards = computed(() =>
  (Array.isArray(props.items) ? props.items : []).filter((item) => item && item.image_url),
)

const scrollable = computed(() => props.layout === 'row3_scroll')

// 箭头只在真正溢出时渲染（同 CmsProductPool / CategoryTileCarousel 的判定）。
const scroller = ref(null)
const overflowing = ref(false)
const atStart = ref(true)
const atEnd = ref(false)

let resizeObserver = null

function sync() {
  const el = scroller.value
  if (!el) return
  const max = el.scrollWidth - el.clientWidth
  overflowing.value = max > 1
  atStart.value = el.scrollLeft <= 1
  atEnd.value = el.scrollLeft >= max - 1
}

function scrollByPage(direction) {
  const el = scroller.value
  if (!el) return
  el.scrollBy({ left: direction * Math.round(el.clientWidth * 0.9), behavior: 'smooth' })
}

function observe() {
  resizeObserver?.disconnect()
  resizeObserver = null
  if (!scrollable.value || !scroller.value) {
    overflowing.value = false
    return
  }
  sync()
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(sync)
    resizeObserver.observe(scroller.value)
  }
}

onMounted(observe)
watch([cards, scrollable], observe, { flush: 'post' })

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
})

// 13.8 链接规则：外链 / 站内 / 无链接三种。
function linkKind(href) {
  const value = String(href || '').trim()
  if (!value) return 'none'
  if (/^(?:https?:)?\/\//i.test(value) || /^www\./i.test(value)) return 'external'
  return 'internal'
}
</script>

<template>
  <section
    v-if="cards.length > 0"
    class="channel-card-group"
    :class="`channel-card-group--${layout}`"
  >
    <div
      ref="scroller"
      class="channel-cards__track"
      :class="{ 'channel-cards__track--scroll': scrollable }"
      @scroll="sync"
    >
      <ul class="channel-cards__row">
        <li v-for="(item, index) in cards" :key="item.id || index" class="channel-cards__item">
          <NuxtLink
            v-if="linkKind(item.link_url) === 'internal'"
            class="channel-card"
            :to="item.link_url"
          >
            <img class="channel-card__img" :src="item.image_url" alt="" loading="lazy" />
          </NuxtLink>
          <a
            v-else-if="linkKind(item.link_url) === 'external'"
            class="channel-card"
            :href="item.link_url"
            target="_blank"
            rel="noopener"
          >
            <img class="channel-card__img" :src="item.image_url" alt="" loading="lazy" />
          </a>
          <span v-else class="channel-card channel-card--static">
            <img class="channel-card__img" :src="item.image_url" alt="" loading="lazy" />
          </span>
        </li>
      </ul>
    </div>

    <template v-if="scrollable && overflowing">
      <button
        class="channel-cards__arrow channel-cards__arrow--prev"
        type="button"
        :disabled="atStart"
        :aria-label="t('listing.prevCategories')"
        @click="scrollByPage(-1)"
      >
        <span aria-hidden="true">‹</span>
      </button>
      <button
        class="channel-cards__arrow channel-cards__arrow--next"
        type="button"
        :disabled="atEnd"
        :aria-label="t('listing.nextCategories')"
        @click="scrollByPage(1)"
      >
        <span aria-hidden="true">›</span>
      </button>
    </template>
  </section>
</template>

<style scoped>
.channel-card-group {
  position: relative;
}

.channel-cards__track {
  overflow-x: hidden;
}

.channel-cards__track--scroll {
  overflow-x: auto;
  overflow-y: hidden;
  scroll-snap-type: x proximity;
  scroll-behavior: smooth;
  scrollbar-width: none;
}

.channel-cards__track--scroll::-webkit-scrollbar {
  display: none;
}

.channel-cards__row {
  display: flex;
  flex-wrap: nowrap;
  gap: 17px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.channel-cards__item {
  flex: 0 0 auto;
}

/* row2 两列平铺：620×200、gap 24（真站 1264 = 620×2 + 24）。 */
.channel-card-group--row2 .channel-cards__row {
  gap: 24px;
}

.channel-card-group--row2 .channel-cards__item {
  flex: 0 0 calc((100% - 24px) / 2);
  height: 200px;
}

/* row3 三列平铺：410×200、gap 17（1264 = 410×3 + 17×2）。 */
.channel-card-group--row3 .channel-cards__item {
  flex: 0 0 calc((100% - 34px) / 3);
  height: 200px;
}

/* row3_scroll 一屏 3 张：400.66×195.44、gap 31（1264 = 400.66×3 + 31×2）。 */
.channel-card-group--row3_scroll .channel-cards__row {
  gap: 31px;
}

.channel-card-group--row3_scroll .channel-cards__item {
  flex: 0 0 calc((100% - 62px) / 3);
  aspect-ratio: 400.66 / 195.44;
  scroll-snap-align: start;
}

.channel-card {
  display: block;
  width: 100%;
  height: 100%;
  border-radius: 8px;
  overflow: hidden;
  background: #f5f6fa;
}

.channel-card--static {
  cursor: default;
}

.channel-card__img {
  display: block;
  width: 100%;
  height: 100%;
  border-radius: 8px;
  object-fit: cover;
}

/* Hover arrows: 40×48 半透明黑块，默认透明，模块 hover 才显示（真站同口径）。 */
.channel-cards__arrow {
  position: absolute;
  top: 0;
  bottom: 0;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 48px;
  margin: auto 0;
  padding: 0;
  border: 0;
  background: rgb(0 0 0 / 12%);
  color: #1a1a1a;
  font-size: 1.5rem;
  line-height: 1;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.channel-card-group:hover .channel-cards__arrow,
.channel-card-group:focus-within .channel-cards__arrow {
  opacity: 1;
}

.channel-cards__arrow:hover:not(:disabled) {
  background: rgb(0 0 0 / 22%);
}

.channel-cards__arrow:disabled {
  opacity: 0;
  cursor: default;
}

.channel-cards__arrow--prev {
  left: 0;
}

.channel-cards__arrow--next {
  right: 0;
}
</style>
