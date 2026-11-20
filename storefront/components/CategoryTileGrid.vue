<script setup>
// Joybuy-style category tile grid, shared by the header dropdown, the
// category results page and the channel landing page. Two variants:
// - default (dropdown/results): one grey square per category with the image
//   and the name inside the box (measured live 2026-11-11: 136×136 card,
//   #F7F7F7, radius 8px, 8px padding, 72px image, 14px/500 name, 8px gap).
//   Hover: white card + underlined name. Selected: white card + accent border.
// - channel (需求文档03 13.1①②, measured live 2026-11-19 in
//   var/channel_styles_20261119/measurement.md): the grey block wraps ONLY the
//   image (140px or 194px square, rgb(245,246,250), radius 8px); the name sits
//   OUTSIDE the block, centred, 18px/500/24px, margin-top 12px, wrapped at a
//   fixed name width (6 or 9 CJK chars = tile size minus 20px inset) and
//   clamped to 2 lines. Tiles line up with a 20px gap in `columns`-tall
//   vertical stacks so a 2-row module can slide horizontally as one unit.
import { computed } from 'vue'

import { categoryImages } from '../assets/category-images'
import { TILE_SIZE_BY_NAME_CHARS } from '../utils/channelTiles'
import { useLocale } from '../composables/useLocale'

const props = defineProps({
  items: {
    type: Array,
    default: () => [],
  },
  // Slug of the currently open category (results page only).
  activeSlug: {
    type: String,
    default: '',
  },
  // Single row (no wrapping) for the results-page carousel; the parent owns
  // the horizontal scroller.
  row: {
    type: Boolean,
    default: false,
  },
  // 'default' (header dropdown / listing strip) or 'channel' (channel page).
  variant: {
    type: String,
    default: 'default',
  },
  // Channel variant: name wrap width in CJK chars (6 → 140px, 9 → 194px).
  nameChars: {
    type: Number,
    default: 6,
  },
  // Channel variant: stack this many tiles vertically per column (rows of the
  // 13.1② table). 0 keeps the plain flat list.
  columns: {
    type: Number,
    default: 0,
  },
})

const emit = defineEmits(['select'])

const { categoryName } = useLocale()

// Local fallback for categories without a source tile (never a CDN URL).
const PLACEHOLDER_IMAGE = '/images/categories/_placeholder.svg'

function imageFor(slug) {
  return categoryImages[slug] || PLACEHOLDER_IMAGE
}

function onSelect(slug) {
  emit('select', slug)
}

const isChannel = computed(() => props.variant === 'channel')

// Chunk the flat list into vertical stacks of `columns` tiles (13.1② rows).
const chunkedItems = computed(() => {
  if (!isChannel.value || props.columns <= 0) return null
  const groups = []
  for (let index = 0; index < props.items.length; index += props.columns) {
    groups.push(props.items.slice(index, index + props.columns))
  }
  return groups
})

const tileStyle = computed(() => {
  if (!isChannel.value) return null
  return { '--tile-size': TILE_SIZE_BY_NAME_CHARS[props.nameChars] || TILE_SIZE_BY_NAME_CHARS[6] }
})
</script>

<template>
  <ul
    class="category-tiles"
    :class="{
      'category-tiles--row': props.row,
      'category-tiles--channel': isChannel,
    }"
    :style="tileStyle"
  >
    <template v-if="chunkedItems">
      <li v-for="(group, groupIndex) in chunkedItems" :key="groupIndex" class="category-tiles__col">
        <NuxtLink
          v-for="item in group"
          :key="item.slug"
          class="category-tile"
          :to="`/c/${item.slug}`"
          @click="onSelect(item.slug)"
        >
          <span class="category-tile__media">
            <img class="category-tile__image" :src="imageFor(item.slug)" alt="" loading="lazy" />
          </span>
          <span class="category-tile__name">{{ categoryName(item) }}</span>
        </NuxtLink>
      </li>
    </template>
    <template v-else>
      <li v-for="item in items" :key="item.slug">
        <NuxtLink
          class="category-tile"
          :class="{ 'category-tile--active': item.slug === props.activeSlug }"
          :to="`/c/${item.slug}`"
          @click="onSelect(item.slug)"
        >
          <span class="category-tile__media">
            <img class="category-tile__image" :src="imageFor(item.slug)" alt="" loading="lazy" />
          </span>
          <span class="category-tile__name">{{ categoryName(item) }}</span>
        </NuxtLink>
      </li>
    </template>
  </ul>
</template>

<style scoped>
.category-tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(7.5rem, 1fr));
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.category-tiles--row {
  display: flex;
  flex-wrap: nowrap;
  gap: var(--space-2);
}

.category-tiles--row > li {
  flex: 0 0 8.5rem; /* 136px, the source site's tile width */
}

.category-tile {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  aspect-ratio: 1 / 1;
  padding: var(--space-2);
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  background: var(--colour-surface-soft);
  text-decoration: none;
  text-align: center;
  color: var(--colour-text);
}

/* 需求 14.5：图 + 文整体居中。图片盒占满卡片宽度、图片本身 60% 宽，若图片盒
 * 是普通 block 图片会贴左（真站图片与名称中心线都在卡片中线，实测 delta 0）；
 * 这里用 flex 居中图片，名称由 .category-tile 的 text-align: center 居中。 */
.category-tile__media {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%; /* default variant: the image scales inside the tile box */
}

.category-tile__image {
  width: 60%; /* ≈72px inside the source site's 120px content box */
  aspect-ratio: 1 / 1;
  object-fit: cover;
  border-radius: var(--radius-sm);
}

.category-tile__name {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  max-width: 100%;
  font-size: 0.875rem; /* 14px — the source site's tile label size */
  font-weight: 500;
  line-height: 1.25rem; /* 20px, same as the source tiles */
}

/* Hover: white card, black label, underline under the label only. */
.category-tile:hover {
  background: var(--colour-surface);
  color: var(--colour-text);
}

.category-tile:hover .category-tile__name {
  text-decoration: underline;
}

/* Selected: white card with a 1px BLACK outline (需求 14.6), label NOT
 * underlined. The border is always 1px transparent above, so only the colour
 * changes — no layout shift. This rule is the /c page + header dropdown tile
 * language only; the home page's white-card/red-border rule lives in
 * CmsLinkGrid and is NOT touched here. */
.category-tile--active {
  background: var(--colour-surface);
  border-color: #1a1a1a;
}

.category-tile--active:hover .category-tile__name {
  text-decoration: none;
}

/* ------------------------------------------------------------------ */
/* Channel variant (13.1①②): grey block wraps the image only; the name */
/* lives outside the block with a fixed wrap width. Measured 2026-11-19. */
/* ------------------------------------------------------------------ */

.category-tiles--channel {
  gap: 20px; /* the source site's tile gap (measurement.md §1) */
}

.category-tiles--channel.category-tiles--row {
  gap: 20px;
}

.category-tiles--channel.category-tiles--row > li {
  flex: 0 0 auto;
}

/* Vertical stack: one column = `rows` tiles sliding together (13.1②). */
.category-tiles--channel .category-tiles__col {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.category-tiles--channel .category-tile {
  width: var(--tile-size, 140px);
  aspect-ratio: auto;
  gap: 0;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent; /* the name sits outside any background block */
}

.category-tiles--channel .category-tile:hover {
  background: transparent;
}

.category-tiles--channel .category-tile__media {
  width: var(--tile-size, 140px);
  height: var(--tile-size, 140px);
  border-radius: 8px;
  background: #f5f6fa; /* live-measured image-block colour */
  overflow: hidden;
}

.category-tiles--channel .category-tile__image {
  width: 100%;
  height: 100%;
  border-radius: 8px;
}

.category-tiles--channel .category-tile__name {
  /* The real site reserves the full two-line box (2 × 24px) under every tile
     (140px tile → 200px item even when the name takes one line), so tiles in
     a column stack at a fixed pitch. */
  min-height: 48px;
  max-width: calc(var(--tile-size, 140px) - 20px);
  margin-top: 12px;
  font-size: 18px;
  font-weight: 500;
  line-height: 24px;
  color: var(--colour-text);
  text-align: center;
}

.category-tiles--channel .category-tile:hover .category-tile__name {
  text-decoration: underline;
}

.category-tiles--channel .category-tile--active {
  background: transparent;
  border: 0;
}

.category-tiles--channel .category-tile--active:hover .category-tile__name {
  text-decoration: underline;
}
</style>
