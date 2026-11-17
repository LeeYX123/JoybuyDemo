<script setup>
// Joybuy-style category tile grid, shared by the header dropdown and the
// category results page. One grey square per category with the image and the
// name inside the box (measured live 2026-11-11: 136×136 card, #F7F7F7,
// radius 8px, 8px padding, 72px image, 14px/500 name, 8px gap).
// Hover: white card + underlined name. Selected: white card + accent border,
// no underline.
import { categoryImages } from '../assets/category-images'
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
</script>

<template>
  <ul class="category-tiles" :class="{ 'category-tiles--row': props.row }">
    <li v-for="item in items" :key="item.slug">
      <NuxtLink
        class="category-tile"
        :class="{ 'category-tile--active': item.slug === props.activeSlug }"
        :to="`/c/${item.slug}`"
        @click="onSelect(item.slug)"
      >
        <img class="category-tile__image" :src="imageFor(item.slug)" alt="" loading="lazy" />
        <span class="category-tile__name">{{ categoryName(item) }}</span>
      </NuxtLink>
    </li>
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

/* Selected: white card with a visible outline, label NOT underlined. */
.category-tile--active {
  background: var(--colour-surface);
  border-color: var(--colour-accent);
}

.category-tile--active:hover .category-tile__name {
  text-decoration: none;
}
</style>
