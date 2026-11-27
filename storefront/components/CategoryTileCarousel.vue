<script setup>
// Horizontal category carousel: one row of tiles plus two hover-revealed arrows
// overlaid on the row's sides and a 4px bottom scrollbar (default/listing
// variant, matching the live listing page measured 2026-11-27: arrows 20×24
// #c7c7c7, opacity 0 → 1 on container hover, transition all .5s ease; scrollbar
// 4px with a transparent thumb that colours on hover).
// The strip also remembers its horizontal offset per parent category
// (`scrollKey`) because picking a sibling L2 re-creates the listing subtree.
// The channel landing page (13.1②) reuses it with `variant="channel"` and
// stacks tiles into `rows`-tall columns so multi-row modules still slide
// horizontally as one unit.
import { onBeforeUnmount, onMounted, ref } from 'vue'

import { useLocale } from '../composables/useLocale'
import { recallStripScroll, rememberStripScroll } from '../utils/categoryStripScroll'

import CategoryTileGrid from './CategoryTileGrid.vue'

const { t } = useLocale()

const props = defineProps({
  items: {
    type: Array,
    default: () => [],
  },
  activeSlug: {
    type: String,
    default: '',
  },
  // Listing strip only: scope key (the parent category slug) under which the
  // horizontal offset is remembered across the remount caused by switching to
  // a sibling L2. Empty → no memory (channel page keeps its behaviour).
  scrollKey: {
    type: String,
    default: '',
  },
  // 'default' (listing strip) or 'channel' (channel page tiles).
  variant: {
    type: String,
    default: 'default',
  },
  // Channel variant: name wrap width in CJK chars (6 → 140px, 9 → 194px).
  nameChars: {
    type: Number,
    default: 6,
  },
  // Channel variant: tiles per vertical stack (rows of the 13.1② table).
  rows: {
    type: Number,
    default: 1,
  },
  // Channel variant: tiles that must fit in one viewport row (8 / 6 / 5).
  perRow: {
    type: Number,
    default: 0,
  },
  // Channel variant: multi-row reading order ('row' | 'column').
  fill: {
    type: String,
    default: 'column',
  },
  // 批次 CA：分类页 carousel 第一张「全部」卡（见 CategoryTileGrid.allCard）。
  allCard: {
    type: Object,
    default: null,
  },
})

const scroller = ref(null)
const barEl = ref(null)
const overflowing = ref(false)
const atStart = ref(true)
const atEnd = ref(false)
// Thumb geometry in PIXELS of the bar (bar width === track clientWidth). Pixels
// keep the drag mapping and the rendered thumb in one coordinate system — the
// old `%` + `Math.round` pair quantised the thumb to ~11px steps at 1440.
const thumbWidth = ref(24)
const thumbLeft = ref(0)
const draggingThumb = ref(false)

let resizeObserver = null
let restoreFrame = null
let syncFrame = 0
// `:ref` function is re-invoked on every patch of the track vnode, so restoring
// must be one-shot (it used to re-run during drags and yank scrollLeft back to
// the remembered offset → the thumb "thrashed").
let restoredOnce = false
// { startX, startThumbLeft, usable, max, scrollPerPx, previousScrollBehavior }
let dragState = null

// Snapshot taken at setup time: the component is re-created when the route
// moves to a sibling L2, and the new instance restores this offset on mount.
const savedScroll = props.scrollKey ? recallStripScroll(props.scrollKey) : undefined

function updateThumb(el) {
  const width = el.clientWidth
  if (width <= 0 || el.scrollWidth <= 0) return
  const max = el.scrollWidth - width
  const size = Math.min(width, Math.max(24, Math.round((width / el.scrollWidth) * width)))
  thumbWidth.value = size
  thumbLeft.value = max > 0 ? Math.round((el.scrollLeft / max) * (width - size)) : 0
}

function sync() {
  const el = scroller.value
  if (!el) return
  const max = el.scrollWidth - el.clientWidth
  overflowing.value = max > 1
  atStart.value = el.scrollLeft <= 1
  atEnd.value = el.scrollLeft >= max - 1
  // During a drag the pointer is the only writer of the thumb position;
  // scroll events fired by our own `scrollLeft` writes must not fight it.
  if (!draggingThumb.value) updateThumb(el)
  rememberNow()
}

// Coalesce scroll / resize notifications into one update per animation frame.
function scheduleSync() {
  if (syncFrame) return
  syncFrame = requestAnimationFrame(() => {
    syncFrame = 0
    sync()
  })
}

// 2026-11-27: remember the offset so re-mounting the strip (sibling L2 pick)
// keeps the user's horizontal position instead of snapping back to the left.
function rememberNow() {
  const el = scroller.value
  if (!el || !props.scrollKey) return
  const max = el.scrollWidth - el.clientWidth
  rememberStripScroll(props.scrollKey, {
    left: el.scrollLeft,
    ratio: max > 0 ? el.scrollLeft / max : 0,
    width: el.scrollWidth,
  })
}

// Programmatic scrolling must not animate (the track has scroll-behavior:
// smooth), otherwise restoring would visibly slide in from the left edge.
function setScrollLeft(el, left) {
  const previous = el.style.scrollBehavior
  el.style.scrollBehavior = 'auto'
  el.scrollLeft = left
  el.style.scrollBehavior = previous
}

// The restored offset wins, but the selected tile must stay visible: if it
// ended up outside the viewport, nudge the track by the smallest amount.
function ensureActiveVisible(el) {
  const tile = el.querySelector('.category-tile--active')
  if (!tile) return
  const track = el.getBoundingClientRect()
  const rect = tile.getBoundingClientRect()
  if (!rect.width) return // no layout (jsdom / display:none)
  const pad = 8
  if (rect.left < track.left + pad) {
    setScrollLeft(el, Math.max(0, el.scrollLeft - (track.left + pad - rect.left)))
  } else if (rect.right > track.right - pad) {
    setScrollLeft(el, el.scrollLeft + (rect.right - track.right + pad))
  }
}

function restoreScroll() {
  const el = scroller.value
  if (!el || !savedScroll || draggingThumb.value) return
  const max = el.scrollWidth - el.clientWidth
  if (max <= 1) return
  const left =
    savedScroll.width && Math.abs(savedScroll.width - el.scrollWidth) > 2
      ? Math.round(savedScroll.ratio * max)
      : Math.min(Math.max(savedScroll.left, 0), max)
  setScrollLeft(el, left)
  ensureActiveVisible(el)
}

function bindScroller(el) {
  scroller.value = el
  // One-shot: Vue re-invokes a function ref on every patch of this vnode, and
  // restoring each time would reset scrollLeft while the user is dragging.
  if (!el || restoredOnce) return
  restoredOnce = true
  // Apply the offset as soon as the element exists, before the browser paints
  // the remounted strip at scrollLeft 0.
  restoreScroll()
}

function scrollByPage(direction) {
  const el = scroller.value
  if (!el) return
  el.scrollBy({ left: direction * Math.round(el.clientWidth * 0.9), behavior: 'smooth' })
}

// 2026-11-27: the 4px bar is a real drag handle. The pointer delta is the ONLY
// source while dragging: the thumb's pixel position is `startThumbLeft + dx`
// and `scrollLeft` is derived from that same number (no per-move ratio
// recompute, no scroll-event feedback). `scroll-behavior` is switched to auto
// once on pointerdown and restored on pointerup.
function applyDragPosition(thumbLeftPx) {
  const el = scroller.value
  const state = dragState
  if (!el || !state) return
  const left = Math.min(Math.max(thumbLeftPx, 0), state.usable)
  thumbLeft.value = Math.round(left)
  el.scrollLeft = Math.round(left * state.scrollPerPx)
}

function startDrag(event) {
  if (!overflowing.value) return
  if (typeof event.button === 'number' && event.button !== 0) return
  const el = scroller.value
  const bar = barEl.value
  if (!el || !bar) return
  const rect = bar.getBoundingClientRect()
  const max = el.scrollWidth - el.clientWidth
  if (!rect.width || max <= 0) return
  event.preventDefault()
  draggingThumb.value = true
  const usable = Math.max(0, rect.width - thumbWidth.value)
  // Pressing anywhere on the bar jumps the thumb centre under the pointer
  // (native behaviour); the gesture then continues as a pure delta.
  const startThumbLeft = Math.min(
    Math.max(event.clientX - rect.left - thumbWidth.value / 2, 0),
    usable,
  )
  dragState = {
    startX: event.clientX,
    startThumbLeft,
    usable,
    scrollPerPx: usable > 0 ? max / usable : 0,
    previousScrollBehavior: el.style.scrollBehavior,
  }
  el.style.scrollBehavior = 'auto'
  applyDragPosition(startThumbLeft)
  if (bar.setPointerCapture && event.pointerId !== undefined) {
    try {
      bar.setPointerCapture(event.pointerId)
    } catch {
      /* capture is best-effort */
    }
  }
}

function moveDrag(event) {
  if (!dragState) return
  event.preventDefault()
  applyDragPosition(dragState.startThumbLeft + (event.clientX - dragState.startX))
}

function endDrag(event) {
  if (!dragState) return
  const el = scroller.value
  const bar = barEl.value
  const previousScrollBehavior = dragState.previousScrollBehavior
  dragState = null
  draggingThumb.value = false
  if (el) el.style.scrollBehavior = previousScrollBehavior
  if (bar?.releasePointerCapture && event.pointerId !== undefined) {
    try {
      bar.releasePointerCapture(event.pointerId)
    } catch {
      /* already released */
    }
  }
  // Re-align the thumb with the real scrollLeft (browser clamping/rounding).
  sync()
}

onMounted(() => {
  sync()
  if (savedScroll) {
    // Layout (images/fonts) may still settle after the ref callback.
    restoreFrame = requestAnimationFrame(() => {
      restoreScroll()
      sync()
    })
  }
  if (typeof ResizeObserver !== 'undefined' && scroller.value) {
    resizeObserver = new ResizeObserver(scheduleSync)
    resizeObserver.observe(scroller.value)
  }
})

onBeforeUnmount(() => {
  rememberNow()
  if (restoreFrame) cancelAnimationFrame(restoreFrame)
  restoreFrame = null
  if (syncFrame) cancelAnimationFrame(syncFrame)
  syncFrame = 0
  resizeObserver?.disconnect()
  resizeObserver = null
})
</script>

<template>
  <div class="category-carousel" :class="`category-carousel--${props.variant}`">
    <div :ref="bindScroller" class="category-carousel__track" @scroll="scheduleSync">
      <CategoryTileGrid
        row
        :items="props.items"
        :active-slug="props.activeSlug"
        :variant="props.variant"
        :name-chars="props.nameChars"
        :columns="props.variant === 'channel' ? Math.max(props.rows, 1) : 0"
        :per-row="props.variant === 'channel' ? props.perRow : 0"
        :fill="props.fill"
        :all-card="props.allCard"
      />
    </div>
    <!-- 真站（2026-11-27 实测 .thirdLevelCate_* CSS）：箭头是叠在横条两侧的
         20×24 灰色胶囊，默认 opacity:0，容器 hover 才淡入；底部滚动条 4px、
         thumb 默认透明、hover 才上色。两者都不从 DOM 里删除（键盘可达）。 -->
    <div v-if="overflowing" class="category-carousel__nav">
      <button
        class="category-carousel__arrow"
        type="button"
        :disabled="atStart"
        :aria-label="t('listing.prevCategories')"
        @click="scrollByPage(-1)"
      >
        <span aria-hidden="true">‹</span>
      </button>
      <button
        class="category-carousel__arrow"
        type="button"
        :disabled="atEnd"
        :aria-label="t('listing.nextCategories')"
        @click="scrollByPage(1)"
      >
        <span aria-hidden="true">›</span>
      </button>
    </div>
    <!-- 真站滚动条：4px 细条、轨道白色、thumb 默认透明，容器 hover（或键盘
         focus-within）才显出 rgba(0,0,0,.14)，thumb 自身 hover 加深到 .28。
         自绘而非原生：Chromium 对 scrollbar-width:thin 走浮层滚动条，hover 时
         不渲染，无法满足「hover 才显示」。4px 高度常驻，显隐不产生布局跳动。
         thumb 可拖动（pointer capture 到本元素，拖出边界也不会变成卡片点击）。 -->
    <div
      v-if="overflowing"
      ref="barEl"
      class="category-carousel__bar"
      :class="{ 'category-carousel__bar--dragging': draggingThumb }"
      role="presentation"
      @pointerdown="startDrag"
      @pointermove="moveDrag"
      @pointerup="endDrag"
      @pointercancel="endDrag"
    >
      <span
        class="category-carousel__thumb"
        :style="{ width: `${thumbWidth}px`, left: `${thumbLeft}px` }"
      />
    </div>
  </div>
</template>

<style scoped>
.category-carousel {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

/* 2026-11-27 真站实测（.thirdLevelCate_category-window__ykQqW / CSS bundle
   fc1c52870bc05c43.css）：底部是一条 4px 细滚动条，轨道白色、thumb 默认透明，
   容器 hover 才上色（thumb 自身 hover 再加深）。原生的 scrollbar-width:thin
   在 Chromium 走浮层滚动条（hover 不渲染、gutter 0），所以这里隐藏原生、用
   下面的 __bar/__thumb 自绘同规格的 4px 条；4px 高度常驻，显隐不跳布局。 */
.category-carousel__track {
  overflow-x: auto;
  overflow-y: hidden;
  scroll-behavior: smooth;
  scrollbar-width: none;
}

.category-carousel__track::-webkit-scrollbar {
  display: none;
}

/* 末端余量（2026-11-27 用户复报）：叠层右箭头占掉最右 20px，若没有额外可滚
   空间，滚到最大时最后一张卡永远被箭头压住（/c/electronics 14 张时最后一张
   Batteries 右缘正好 = track 右边界）。行尾补一个 20px 的 flex 空位（外加
   8px 卡片间距 = 28px 余量）：最大滚动位时最后一张卡右缘落在 track 右边界内
   侧 28px，箭头左缘在 -20px，视觉间距 8px。频道页不加，保持像素不变。 */
.category-carousel--default :deep(.category-tiles--row)::after {
  content: '';
  flex: 0 0 20px;
}

/* 箭头：真站是叠在横条左右两侧的灰胶囊（20×24，靠外一侧 12px 圆角，
   #c7c7c7 / hover #888），默认 opacity:0，容器 hover 或键盘 focus-within
   时 0.5s 淡入；不从 DOM 删除，保持键盘可达。 */
.category-carousel__nav {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0;
  pointer-events: none;
}

.category-carousel__arrow {
  position: absolute;
  top: 42.8%;
  transform: translateY(-50%);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 24px;
  padding: 0;
  border: 0;
  border-radius: 0;
  background-color: #c7c7c7;
  box-shadow: none;
  color: #fff;
  font-size: 0.875rem;
  line-height: 1;
  z-index: 2;
  cursor: pointer;
  opacity: 0;
  pointer-events: none;
  transition: all 0.5s ease;
}

.category-carousel__arrow:first-child {
  left: 0;
  border-radius: 0 12px 12px 0;
}

.category-carousel__arrow:last-child {
  right: 0;
  border-radius: 12px 0 0 12px;
}

.category-carousel--default:hover .category-carousel__arrow,
.category-carousel--default:focus-within .category-carousel__arrow {
  opacity: 1;
  pointer-events: auto;
}

.category-carousel__arrow:hover:not(:disabled) {
  background-color: #888;
}

.category-carousel__arrow:disabled {
  cursor: default;
}

.category-carousel--default:hover .category-carousel__arrow:disabled,
.category-carousel--default:focus-within .category-carousel__arrow:disabled {
  opacity: 0.5;
}

/* 4px 滚动条：轨道白色、thumb 透明，默认不可见；容器 hover / focus-within
   时才显出 thumb（真站是原生 ::-webkit-scrollbar-thumb 的同一套颜色）。
   它是真的可拖拽手柄：命中区上下各放宽 8px（视觉仍是 4px），拖动时 thumb 居中
   跟随指针（同原生），pointer capture 把手势锁在条上，不会变成卡片点击。 */
.category-carousel__bar {
  position: relative;
  width: 100%;
  height: 4px;
  margin-top: 4px;
  border-radius: 4px;
  background: #fff;
  pointer-events: none;
  touch-action: none;
  user-select: none;
}

.category-carousel__thumb {
  position: absolute;
  top: 0;
  height: 100%;
  border-radius: 4px;
  background-color: transparent;
}

.category-carousel__thumb::before {
  content: '';
  position: absolute;
  inset: -6px 0;
}

.category-carousel--default:hover .category-carousel__bar,
.category-carousel--default:focus-within .category-carousel__bar {
  pointer-events: auto;
  cursor: pointer;
}

.category-carousel--default:hover .category-carousel__thumb,
.category-carousel--default:focus-within .category-carousel__thumb {
  background-color: rgb(0 0 0 / 14%);
  pointer-events: auto;
  cursor: grab;
}

.category-carousel--default:hover .category-carousel__thumb:hover {
  background-color: rgb(0 0 0 / 28%);
}

/* 拖动中：即使指针移出横条也保持 thumb 可见 + 加深。 */
.category-carousel--default .category-carousel__bar--dragging .category-carousel__thumb {
  background-color: rgb(0 0 0 / 28%);
  cursor: grabbing;
}

/* ---------------------------------------------------------------------- */
/* Channel variant (13.1②, measured 2026-11-23 §A.1): on the live channel */
/* page the arrows are an overlay ON the row (40×48, rgba(0,0,0,0.12)),    */
/* invisible until the module is hovered, and there is no progress bar.    */
/* ---------------------------------------------------------------------- */
.category-carousel--channel {
  position: relative;
  gap: 0;
}

/* 频道页保持原样：隐藏原生滚动条（横条无可见滚动条）。 */
.category-carousel--channel .category-carousel__track {
  scrollbar-width: none;
}

.category-carousel--channel .category-carousel__track::-webkit-scrollbar {
  display: none;
}

.category-carousel--channel .category-carousel__nav {
  position: absolute;
  inset: 0;
  justify-content: space-between;
  gap: 0;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.category-carousel--channel:hover .category-carousel__nav,
.category-carousel--channel:focus-within .category-carousel__nav {
  opacity: 1;
}

.category-carousel--channel .category-carousel__arrow {
  position: static;
  top: auto;
  transform: none;
  width: 40px;
  height: 48px;
  border: 0;
  border-radius: 0;
  box-shadow: none;
  background: rgb(0 0 0 / 12%);
  color: #1a1a1a;
  font-size: 1.5rem;
  opacity: 1;
  pointer-events: auto;
  transition: none;
}

.category-carousel--channel .category-carousel__arrow:hover:not(:disabled) {
  border: 0;
  background: rgb(0 0 0 / 22%);
}

.category-carousel--channel .category-carousel__arrow:disabled {
  opacity: 0.35;
  cursor: default;
}

/* 频道页没有底部滚动条（13.1② 实测）。 */
.category-carousel--channel .category-carousel__bar {
  display: none;
}
</style>
