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
  <section
    class="cms-link-grid"
    :class="{ 'cms-link-grid--brands': props.payload.variant === 'brand_logos' }"
    :aria-label="heading || t('cms.highlights')"
  >
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
    <!-- Featured brands (心选品牌): one marquee row of circular logos with
         fading edges, sampled from the live site (194px circles, 24px gap).
         Static display only — requirement 14.4 explicitly keeps it
         non-clickable. The track renders the items twice so translateX()
         loops seamlessly; the duplicate is aria-hidden so the brand list is
         announced once. -->
    <div
      v-else-if="props.payload.variant === 'brand_logos'"
      class="brand-row"
      role="list"
      :aria-label="heading || t('cms.featuredBrands')"
    >
      <div class="brand-row__track">
        <ul class="brand-row__list" role="none">
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
        <ul class="brand-row__list" aria-hidden="true">
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

/* 14.4 acceptance fix: real 「心选品牌」 title is 28px with 100% line-height
 * (28px) and #1E1E1E; the generic title inherited a taller line box and the
 * page's default #17202A colour. */
.cms-link-grid--brands .cms-link-grid__title {
  color: #1e1e1e;
  line-height: 28px;
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

/* Category discovery (batch O 14.1): measured from the live site's
 * pc-popular-categoryV3 module (2026-11-20 CSS bundle 0047fbbd…css):
 * - card 366px tall, #F5F6FA, 16px radius, shadow 0 10px 30px rgba(0,0,0,.08);
 * - label absolutely placed 28px from the top/left, 18px/600/24px #1A1A1A,
 *   clamped to two lines;
 * - 275px-tall image at the bottom with 12px radius;
 * - cards overlap (deck): at 1200–1599px the width is
 *   calc((100% + 330px) / 6) with a -66px step; ≥1600px it is 279px with
 *   a -32px step; below 1200px calc((100% + 525px) / 6) with -105px. */
.cms-link-grid__row--tiles {
  display: flex;
  align-items: flex-start;
  /* The deck widths below already account for the overlap margins; the
     generic row's 12px flex gap would add gap*(n-1) and push the last card
     past the container edge. */
  gap: 0;
  margin-top: 16px;
  padding-block: 0;
}

.cms-link-grid__row--tiles li {
  position: relative;
  flex: 0 0 auto;
  /* Percentage deck widths live on the flex item (the card itself is a
     shrink-to-fit child, where a percentage width would resolve against its
     own auto width and collapse). */
  width: calc((100% + 525px) / 6);
}

.cms-link-grid__row--tiles li + li {
  margin-left: -105px;
}

.discovery-card {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  width: 100%;
  height: 366px;
  overflow: hidden;
  border-radius: 16px;
  background: #f5f6fa;
  text-decoration: none;
  color: #1a1a1a;
  box-shadow: 0 10px 30px rgb(0 0 0 / 8%);
  /* Live site (2026-11-25 measurement): the card CSS only transitions
     box-shadow 0.2s; the transform lift is a JS spring (framer-motion), which
     is reproduced below as a spring-shaped CSS transition. */
  transition:
    box-shadow 0.2s ease,
    transform 0.39s cubic-bezier(0.4, 0, 0.24, 1.38);
}

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

/* Hover, measured on the live site (2026-11-25 three-state Playwright probe,
 * var/category_hover_20261125/live_{1896,1440}.json + live_1896_curve.json):
 * - the card keeps #F5F6FA (background never changes), the label keeps
 *   18px/600/#1A1A1A with no underline, and the 275px image keeps
 *   transform: none (no zoom) and filter: none;
 * - the hovered card lifts translateY(-40px) and its two immediate
 *   neighbours lift translateY(-8px) (a wave), animated by a JS spring:
 *   peak 1.066× the distance at ~296ms, settled by ~470ms, with the leave
 *   path symmetric (peak +6% around 257ms). The box-shadow deepens from
 *   0 10px 30px/.08 to 0 14px 38px/.12 over 0.2s ease.
 * The spring is reproduced with a fitted cubic-bezier (max deviation <1px);
 * transform-only, so the 366px card box never changes size and nothing shifts
 * in layout.
 */
.cms-link-grid__row--tiles li:hover .discovery-card {
  box-shadow: 0 14px 38px rgb(0 0 0 / 12%);
  transform: translateY(-40px);
}

/* Wave: only the cards directly left/right of the hovered one rise 8px. */
.cms-link-grid__row--tiles li:hover + li .discovery-card,
.cms-link-grid__row--tiles li:has(+ li:hover) .discovery-card {
  transform: translateY(-8px);
}

/* Keyboard parity with the live rule
 * `.style_card:hover/:focus-visible { box-shadow: 0 14px 38px rgba(0,0,0,.12) }`
 * and `:focus-visible { outline: blue solid 2px; outline-offset: 2px }` — the
 * live site raises only on pointer hover, so focus gets shadow + outline
 * rather than the lift. */
.discovery-card:focus-visible {
  outline: 2px solid #00f;
  outline-offset: 2px;
  box-shadow: 0 14px 38px rgb(0 0 0 / 12%);
}

.discovery-card__label {
  position: absolute;
  z-index: 1;
  top: 28px;
  left: 28px;
  max-width: calc(100% - 28px - 125px);
  overflow: visible;
  color: #1a1a1a;
  font-size: 18px;
  font-weight: 600;
  line-height: 24px;

  display: block;

  word-break: break-word;
}

.cms-link-grid__row--tiles li:last-child .discovery-card__label {
  max-width: calc(100% - 28px - 20px);
}

.discovery-card__image {
  display: block;
  width: 275px;
  height: 275px;
  margin-top: auto;
  object-fit: cover;
  border-radius: 12px;
}

.discovery-card__image--empty {
  background: #ececee;
}

/* The storefront container caps at 1440px at every viewport, so the live
 * site's fixed 279px/-32px deck at ≥1600px would overflow here (6×279 - 5×32
 * = 1514 > 1344). Keep the fluid formula for all ≥1200px: it resolves to the
 * same 279px cards at our 1344px content width and always fits exactly. */
@media (min-width: 1200px) {
  .cms-link-grid__row--tiles li + li {
    margin-left: -66px;
  }

  .cms-link-grid__row--tiles li {
    width: calc((100% + 330px) / 6);
  }

  .discovery-card__label {
    max-width: calc(100% - 28px - 86px);
  }

  .discovery-card__image {
    width: 100%;
    height: 275px;
  }
}

/* Featured brands (心选品牌, 14.4): measured from the live site's
 * pc-new-brands-we-love module — a row of 194px circles with 24px gaps and
 * 194px edge fades. The live site auto-advances it at ~31px/s and pauses on
 * hover (measured 2026-11-25: scrollLeft 190→267 in 2.5s, constant while
 * hovered); a CSS marquee reproduces both. 12 items currently give a
 * 2616px loop, so 84s ≈ 31px/s — if the CMS item count changes the speed
 * scales with it. */
.brand-row {
  position: relative;
  overflow: hidden;
  margin-top: 24px;
}

.brand-row__track {
  display: flex;
  gap: 24px;
  width: max-content;
  animation: cms-brand-scroll 84s linear infinite;
}

/* Live-site behaviour: hovering the row freezes the marquee. */
.brand-row:hover .brand-row__track {
  animation-play-state: paused;
}

/* The track holds the same list twice; translating by one segment + the
 * 24px inter-segment gap lines segment two up exactly with segment one. */
@keyframes cms-brand-scroll {
  from {
    transform: translateX(0);
  }

  to {
    transform: translateX(calc(-50% - 12px));
  }
}

@media (prefers-reduced-motion: reduce) {
  /* No motion: drop the duplicate segment and let the row be swiped/rolled
     through instead, so the hidden brands stay reachable. */
  .brand-row {
    overflow-x: auto;
    scrollbar-width: none;
  }

  .brand-row::-webkit-scrollbar {
    display: none;
  }

  .brand-row__track {
    animation: none;
  }

  .brand-row__list[aria-hidden='true'] {
    display: none;
  }
}

.brand-row::before,
.brand-row::after {
  content: '';
  position: absolute;
  z-index: 1;
  top: 0;
  width: 194px;
  height: 100%;
  pointer-events: none;
}

.brand-row::before {
  left: 0;
  background: linear-gradient(90deg, #fff, rgb(255 255 255 / 0));
}

.brand-row::after {
  right: 0;
  background: linear-gradient(270deg, #fff, rgb(255 255 255 / 0));
}

.brand-row__list {
  display: flex;
  gap: 24px;
  padding: 0;
  list-style: none;
}

.brand-card {
  display: flex;
  flex: 0 0 194px;
  flex-direction: column;
  width: 194px;
}

.brand-card__circle {
  position: relative;
  display: block;
  width: 194px;
  height: 194px;
  overflow: hidden;
  border-radius: 50%;
}

.brand-card__circle img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transform: scale(0.79);
}

.brand-card__circle::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: rgb(0 0 0 / 4%);
}

.brand-card__name {
  padding: 6px;
  overflow: visible;
  color: #1a1a1a;
  font-size: 16px;
  font-weight: 600;
  line-height: 20px;
  text-align: center;

  display: block;
  word-break: break-word;
}

@media (max-width: 1199px) {
  /* Narrow screens: drop the deck overlap and use a wrapped grid. 1199px
     (not 80rem=1280px) keeps 1280 on the real-site single-row deck. */
  .cms-link-grid__row--tiles {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-3);
    margin-top: var(--space-3);
  }

  .cms-link-grid__row--tiles li {
    width: auto;
  }

  .cms-link-grid__row--tiles li + li {
    margin-left: 0;
  }

  .discovery-card {
    width: 100%;
    height: auto;
    aspect-ratio: 289 / 366;
  }

  .discovery-card__image {
    width: 100%;
    height: 275px;
  }
}

@media (max-width: 48rem) {
  .cms-link-grid__row--tiles {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .brand-card,
  .brand-card__circle {
    width: 120px;
  }

  .brand-card {
    flex-basis: 120px;
  }

  .brand-card__circle {
    height: 120px;
  }

  .brand-row::before,
  .brand-row::after {
    width: 80px;
  }
}
</style>
