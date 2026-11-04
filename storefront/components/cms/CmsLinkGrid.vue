<script setup>
import { computed } from 'vue'

import { useLocale } from '../../composables/useLocale'
import { pickName } from '../../locales/messages'

// Link grid for homepage entry tiles. Variants:
// - default: pill tiles in an auto-fill grid (brand wall text pills);
// - "tiles": category-discovery cards — 16px-radius light card with the
//   category name top-left and a product image below (docs/12 §1, real-site
//   card 289×366 with the 289×275 image), clickable to the category page;
// - "brand_logos": featured-brands row (心选品牌) — circular logo cards with
//   the brand name below, rendered static (not clickable, per requirement).
// Items without an href render static; a bad item never breaks the grid.
// Labels support optional `label_zh` (docs/12 bilingual).
const props = defineProps({
  payload: {
    type: Object,
    required: true,
  },
})

const { locale } = useLocale()

const VARIANT_CLASSES = {
  tiles: 'cms-link-grid__row--tiles',
  brand_logos: 'cms-link-grid__row--brands',
}

const items = computed(() =>
  (Array.isArray(props.payload.items) ? props.payload.items : []).filter(
    (item) => item && typeof item.label === 'string' && item.label.trim(),
  ),
)

const heading = computed(() =>
  locale.value === 'zh' && props.payload.title_zh ? props.payload.title_zh : props.payload.title,
)

function displayLabel(item) {
  return pickName(item, locale.value, 'label')
}

const variantClass = computed(() => VARIANT_CLASSES[props.payload.variant] || '')
</script>

<template>
  <section class="cms-link-grid" :aria-label="heading || 'Highlights'">
    <h2 v-if="heading" class="cms-link-grid__title">{{ heading }}</h2>
    <!-- Category discovery cards: name top-left, product image below. -->
    <ul
      v-if="props.payload.variant === 'tiles'"
      class="cms-link-grid__row cms-link-grid__row--tiles"
    >
      <li v-for="item in items" :key="item.label">
        <NuxtLink v-if="item.href" class="discovery-card" :to="item.href">
          <span class="discovery-card__label">{{ displayLabel(item) }}</span>
          <img
            v-if="item.icon_path"
            class="discovery-card__image"
            :src="item.icon_path"
            alt=""
            loading="lazy"
          />
          <span
            v-else
            class="discovery-card__image discovery-card__image--empty"
            aria-hidden="true"
          ></span>
        </NuxtLink>
        <span v-else class="discovery-card">
          <span class="discovery-card__label">{{ displayLabel(item) }}</span>
          <img
            v-if="item.icon_path"
            class="discovery-card__image"
            :src="item.icon_path"
            alt=""
            loading="lazy"
          />
        </span>
      </li>
    </ul>
    <!-- Featured brands: one marquee row scrolling right→left with fading
         edges; circular logo + name, never clickable. The track renders the
         items twice so translateX(-50%) loops seamlessly. -->
    <div
      v-else-if="props.payload.variant === 'brand_logos'"
      class="brand-marquee"
      role="list"
      :aria-label="heading || 'Featured brands'"
    >
      <div class="brand-marquee__track">
        <ul class="brand-marquee__segment">
          <li v-for="item in items" :key="item.label" class="brand-card" role="listitem">
            <span class="brand-card__circle">
              <img
                v-if="item.icon_path"
                :src="item.icon_path"
                :alt="displayLabel(item)"
                loading="lazy"
              />
            </span>
            <span class="brand-card__name">{{ displayLabel(item) }}</span>
          </li>
        </ul>
        <ul class="brand-marquee__segment" aria-hidden="true">
          <li v-for="item in items" :key="`dup-${item.label}`" class="brand-card">
            <span class="brand-card__circle">
              <img v-if="item.icon_path" :src="item.icon_path" alt="" loading="lazy" />
            </span>
            <span class="brand-card__name">{{ displayLabel(item) }}</span>
          </li>
        </ul>
      </div>
    </div>
    <!-- Default pill grid (text tiles / brand wall). -->
    <ul v-else class="cms-link-grid__row" :class="variantClass">
      <li v-for="item in items" :key="item.label">
        <NuxtLink
          v-if="item.href"
          class="cms-link-grid__tile cms-link-grid__tile--link"
          :to="item.href"
        >
          <img
            v-if="item.icon_path"
            class="cms-link-grid__icon"
            :src="item.icon_path"
            alt=""
            loading="lazy"
          />
          <span class="cms-link-grid__label">{{ displayLabel(item) }}</span>
        </NuxtLink>
        <span v-else class="cms-link-grid__tile">
          <img
            v-if="item.icon_path"
            class="cms-link-grid__icon"
            :src="item.icon_path"
            alt=""
            loading="lazy"
          />
          <span class="cms-link-grid__label">{{ displayLabel(item) }}</span>
        </span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.cms-link-grid__title {
  font-size: 1.75rem;
  font-weight: var(--font-weight-semibold);
}

.cms-link-grid__row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(9.5rem, 1fr));
  gap: var(--space-3);
  margin-top: var(--space-3);
}

.cms-link-grid__tile {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  min-height: 3.5rem;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  font-weight: var(--font-weight-semibold);
  text-align: center;
}

.cms-link-grid__tile--link {
  text-decoration: none;
  color: var(--colour-text);
}

.cms-link-grid__tile--link:hover {
  border-color: var(--colour-accent);
  color: var(--colour-accent);
  background: var(--colour-accent-soft);
}

.cms-link-grid__icon {
  width: 3rem;
  height: 3rem;
  object-fit: cover;
  border-radius: var(--radius-sm);
}

/* Category discovery: stacked deck — fixed-width cards where each card
 * overlaps the previous one (real site: card 289px, step 222px ≈ 67px
 * overlap); later cards sit on top, shadows under the stack, and a hovered
 * card lifts above its neighbours. */
.cms-link-grid__row--tiles {
  display: flex;
  padding-block: var(--space-2) var(--space-4);
}

.cms-link-grid__row--tiles li {
  position: relative;
  flex: 0 0 auto;
}

.cms-link-grid__row--tiles li + li {
  margin-left: -72px;
}

.discovery-card {
  position: relative;
  display: flex;
  flex-direction: column;
  width: 289px;
  height: 366px;
  overflow: hidden;
  border-radius: 16px;
  background: var(--colour-surface-soft);
  text-decoration: none;
  color: var(--colour-text);
  box-shadow: 0 10px 24px rgb(23 32 42 / 14%);
  transition:
    transform 0.25s ease,
    box-shadow 0.25s ease;
}

/* Hover lift sampled from the live site (2026-11-04): hovered -40px,
 * immediate neighbours -8px, second neighbours stay put; the stack z-order
 * is fixed 1..12 by position, so the right card always keeps covering the
 * lifted card's edge. */
.cms-link-grid__row--tiles li:nth-child(1) {
  z-index: 1;
}
.cms-link-grid__row--tiles li:nth-child(2) {
  z-index: 2;
}
.cms-link-grid__row--tiles li:nth-child(3) {
  z-index: 3;
}
.cms-link-grid__row--tiles li:nth-child(4) {
  z-index: 4;
}
.cms-link-grid__row--tiles li:nth-child(5) {
  z-index: 5;
}
.cms-link-grid__row--tiles li:nth-child(6) {
  z-index: 6;
}
.cms-link-grid__row--tiles li:nth-child(7) {
  z-index: 7;
}
.cms-link-grid__row--tiles li:nth-child(8) {
  z-index: 8;
}
.cms-link-grid__row--tiles li:nth-child(9) {
  z-index: 9;
}
.cms-link-grid__row--tiles li:nth-child(10) {
  z-index: 10;
}
.cms-link-grid__row--tiles li:nth-child(11) {
  z-index: 11;
}
.cms-link-grid__row--tiles li:nth-child(12) {
  z-index: 12;
}

.discovery-card:hover {
  transform: translateY(-40px);
  box-shadow: 0 18px 36px rgb(23 32 42 / 22%);
}

.cms-link-grid__row--tiles li:hover + li .discovery-card,
.cms-link-grid__row--tiles li:has(+ li:hover) .discovery-card {
  transform: translateY(-8px);
}

.discovery-card__label {
  padding: var(--space-4);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  line-height: var(--line-height-tight);
}

.discovery-card__image {
  display: block;
  width: 100%;
  flex: 1;
  min-height: 0;
  margin-top: auto;
  object-fit: cover;
  border-radius: 12px;
}

.discovery-card__image--empty {
  background: var(--colour-surface-muted);
}

.discovery-card:hover .discovery-card__label {
  text-decoration: underline;
}

/* Featured brands: single marquee row scrolling right→left, both edges fade
 * out via a gradient mask. Hover pauses the scroll; reduced motion disables
 * it entirely. */
.brand-marquee {
  overflow: hidden;
  margin-top: var(--space-4);
  padding-block: var(--space-2);
  -webkit-mask-image: linear-gradient(to right, transparent, #000 8%, #000 92%, transparent);
  mask-image: linear-gradient(to right, transparent, #000 8%, #000 92%, transparent);
}

.brand-marquee__track {
  display: flex;
  width: max-content;
  animation: cms-brand-scroll 48s linear infinite;
}

.brand-marquee:hover .brand-marquee__track {
  animation-play-state: paused;
}

@keyframes cms-brand-scroll {
  from {
    transform: translateX(0);
  }

  to {
    transform: translateX(-50%);
  }
}

@media (prefers-reduced-motion: reduce) {
  .brand-marquee__track {
    animation: none;
  }
}

.brand-marquee__segment {
  display: flex;
  gap: var(--space-8);
  padding-right: var(--space-8);
}

.brand-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
}

.brand-card__circle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 160px;
  height: 160px;
  border-radius: 50%;
  overflow: hidden;
  background: var(--colour-surface-soft);
}

.brand-card__circle img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.brand-card__name {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--font-size-md);
  color: var(--colour-text);
  text-align: center;
}

@media (max-width: 80rem) {
  /* Narrow screens: drop the deck overlap and use a wrapped grid. */
  .cms-link-grid__row--tiles {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-3);
  }

  .cms-link-grid__row--tiles li + li {
    margin-left: 0;
  }

  .discovery-card {
    width: 100%;
    height: auto;
    aspect-ratio: 289 / 366;
  }
}

@media (max-width: 48rem) {
  .cms-link-grid__row--tiles {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .brand-card__circle {
    width: 120px;
    height: 120px;
  }

  .brand-card__name {
    max-width: 120px;
  }
}
</style>
