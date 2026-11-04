<script setup>
import { computed } from 'vue'

import { useLocale } from '../../composables/useLocale'
import { pickName } from '../../locales/messages'

// Link grid for homepage entry tiles. Variants:
// - default: pill tiles in an auto-fill grid (brand wall);
// - "quick_entries": circular icons with the label below (activity entries);
// - "tiles": light rounded tiles with a thumbnail on the right (category
//   discovery). Items without an href render static; a bad item never
//   breaks the grid. Labels support optional `label_zh` (docs/12 bilingual).
const props = defineProps({
  payload: {
    type: Object,
    required: true,
  },
})

const { locale } = useLocale()

const VARIANT_CLASSES = {
  quick_entries: 'cms-link-grid__row--entries',
  tiles: 'cms-link-grid__row--tiles',
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
    <ul class="cms-link-grid__row" :class="variantClass">
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
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
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

/* Circular quick entries (Lightning offers, Outlet, JoyPlus...). */
.cms-link-grid__row--entries {
  grid-template-columns: repeat(auto-fill, minmax(6.5rem, 1fr));
}

.cms-link-grid__row--entries .cms-link-grid__tile {
  flex-direction: column;
  border: 0;
  background: transparent;
  min-height: 6.5rem;
}

.cms-link-grid__row--entries .cms-link-grid__tile--link:hover {
  background: var(--colour-accent-soft);
  color: var(--colour-accent);
}

.cms-link-grid__row--entries .cms-link-grid__icon {
  width: 3.75rem;
  height: 3.75rem;
  border-radius: 50%;
  object-fit: cover;
  background: var(--colour-surface-muted);
}

/* Category discovery tiles: light background, thumbnail on the right. */
.cms-link-grid__row--tiles {
  grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
}

.cms-link-grid__row--tiles .cms-link-grid__tile {
  justify-content: space-between;
  border: 0;
  background: #f5f6fa;
  min-height: 4.5rem;
  padding-inline: var(--space-4);
}

.cms-link-grid__row--tiles .cms-link-grid__tile--link:hover {
  background: var(--colour-accent-soft);
  color: var(--colour-accent);
}

.cms-link-grid__row--tiles .cms-link-grid__icon {
  width: 3rem;
  height: 3rem;
  object-fit: cover;
  border-radius: var(--radius-sm);
}
</style>
