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
    <!-- Featured brands: circular logo + name, never clickable. -->
    <ul
      v-else-if="props.payload.variant === 'brand_logos'"
      class="cms-link-grid__row cms-link-grid__row--brands"
    >
      <li v-for="item in items" :key="item.label" class="brand-card">
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

/* Category discovery: 6 vertical cards per row (289×366 at 1512, fluid). */
.cms-link-grid__row--tiles {
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: var(--space-3);
}

.discovery-card {
  position: relative;
  display: flex;
  flex-direction: column;
  aspect-ratio: 289 / 366;
  overflow: hidden;
  border-radius: 16px;
  background: var(--colour-surface-soft);
  text-decoration: none;
  color: var(--colour-text);
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

/* Featured brands: circle logo (real card 194px at 1512) + name below. */
.cms-link-grid__row--brands {
  grid-template-columns: repeat(auto-fill, minmax(10rem, 1fr));
  gap: var(--space-6) var(--space-4);
  margin-top: var(--space-5);
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
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--font-size-md);
  color: var(--colour-text);
  text-align: center;
}

@media (max-width: 80rem) {
  .cms-link-grid__row--tiles {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 48rem) {
  .cms-link-grid__row--tiles {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .cms-link-grid__row--brands {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .brand-card__circle {
    width: 120px;
    height: 120px;
  }
}
</style>
