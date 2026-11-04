<script setup>
import { computed } from 'vue'

import { useLocale } from '../../composables/useLocale'

// Campaign tile area ("Offers for you"): a full-bleed floor with a
// decorative background layer (real site ships a background image; the
// payload carries it as `background_path` after localisation, with a
// translucent mask as the fallback) and square image cards on top. There is
// no visible heading on the real floor. A tile without an image degrades to
// a colour block; a bad payload never breaks the grid. Titles support
// optional `title_zh`/`subtitle_zh` (docs/12 bilingual).
const props = defineProps({
  payload: {
    type: Object,
    required: true,
  },
})

const { locale } = useLocale()

const tiles = computed(() =>
  (Array.isArray(props.payload.items) ? props.payload.items : []).filter(
    (item) => item && typeof item.title === 'string' && item.title.trim(),
  ),
)

const backgroundStyle = computed(() => {
  const image = props.payload.background_path
  return image ? { backgroundImage: `url(${image})` } : { background: 'rgba(245, 246, 250, 0.9)' }
})

function tileTitle(tile) {
  return locale.value === 'zh' && tile.title_zh ? tile.title_zh : tile.title
}

function tileSubtitle(tile) {
  return locale.value === 'zh' && tile.subtitle_zh ? tile.subtitle_zh : tile.subtitle
}
</script>

<template>
  <section class="cms-campaign" :style="backgroundStyle" aria-label="Offers for you">
    <ul class="cms-campaign__grid">
      <li v-for="tile in tiles" :key="tile.title">
        <NuxtLink v-if="tile.href" class="cms-campaign__tile" :to="tile.href">
          <img v-if="tile.image_path" :src="tile.image_path" alt="" loading="lazy" />
          <span class="cms-campaign__scrim" aria-hidden="true"></span>
          <span class="cms-campaign__text">
            <strong class="cms-campaign__title">{{ tileTitle(tile) }}</strong>
            <span v-if="tileSubtitle(tile)" class="cms-campaign__subtitle">{{
              tileSubtitle(tile)
            }}</span>
          </span>
        </NuxtLink>
        <span v-else class="cms-campaign__tile">
          <img v-if="tile.image_path" :src="tile.image_path" alt="" loading="lazy" />
          <span class="cms-campaign__scrim" aria-hidden="true"></span>
          <span class="cms-campaign__text">
            <strong class="cms-campaign__title">{{ tileTitle(tile) }}</strong>
            <span v-if="tileSubtitle(tile)" class="cms-campaign__subtitle">{{
              tileSubtitle(tile)
            }}</span>
          </span>
        </span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
/* Full-bleed floor: stretches to the viewport edges like the real site. */
.cms-campaign {
  display: flex;
  align-items: center;
  width: 100vw;
  min-height: 600px;
  margin-inline: calc(50% - 50vw);
  padding-block: var(--space-6);
  background-position: center;
  background-size: cover;
}

.cms-campaign__grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--space-3);
  width: 100%;
  max-width: var(--container-max);
  margin-inline: auto;
  padding-inline: var(--container-pad);
  list-style: none;
}

.cms-campaign__tile {
  position: relative;
  display: block;
  aspect-ratio: 1 / 1;
  overflow: hidden;
  border-radius: var(--radius-md);
  background: var(--colour-surface-soft);
}

.cms-campaign__tile img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform var(--transition-normal);
}

.cms-campaign__tile:hover img {
  transform: scale(1.04);
}

.cms-campaign__scrim {
  position: absolute;
  inset: 46% 0 0;
  background: linear-gradient(to bottom, rgb(0 0 0 / 0%), rgb(0 0 0 / 62%));
}

.cms-campaign__text {
  position: absolute;
  inset-inline: var(--space-3);
  bottom: var(--space-3);
  display: grid;
  gap: var(--space-1);
  color: var(--colour-white);
}

.cms-campaign__title {
  font-weight: var(--font-weight-bold);
  font-size: var(--font-size-lg);
  line-height: var(--line-height-tight);
}

.cms-campaign__subtitle {
  font-size: var(--font-size-sm);
  opacity: 0.88;
}

@media (max-width: 80rem) {
  .cms-campaign {
    min-height: 0;
  }

  .cms-campaign__grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 48rem) {
  .cms-campaign__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
