<script setup>
import { computed } from 'vue'

import { categoryImages } from '../../assets/category-images'
import { useCategoryTree } from '../../composables/useCategoryTree'
import { useLocale } from '../../composables/useLocale'

// Mobile category landing page (docs/19 §1.4, user-provided real-site
// screenshots 2026-11-24): light-grey page, "为你推荐" 2-col card grid with
// product images, then "全部分类" 2-col card grid for every root category.
// A category without a local image degrades to a plain white card.
const { t, categoryName } = useLocale()
const { categories } = useCategoryTree()

const allCategories = computed(() =>
  (categories.value || []).filter((category) => category.visible_in_nav !== false),
)

// 为你推荐: the first categories that ship a local card image (matches the
// real page's image-backed cards); 全部分类: every root category.
const featuredCategories = computed(() =>
  allCategories.value.filter((c) => categoryImages[c.slug]).slice(0, 8),
)

function imageFor(category) {
  return categoryImages[category.slug] || null
}
</script>

<template>
  <div class="m-cats">
    <section
      v-if="featuredCategories.length > 0"
      class="m-cats__section"
      :aria-label="t('mobile.home.reco')"
    >
      <h2 class="m-cats__title">{{ t('mobile.categories.recommended') }}</h2>
      <ul class="m-cats__grid">
        <li v-for="category in featuredCategories" :key="category.slug">
          <NuxtLink class="m-cats__card" :to="`/c/${category.slug}`">
            <span class="m-cats__card-title">{{ categoryName(category) }}</span>
            <img
              v-if="imageFor(category)"
              class="m-cats__card-img"
              :src="imageFor(category)"
              alt=""
              loading="lazy"
            />
          </NuxtLink>
        </li>
      </ul>
    </section>

    <section class="m-cats__section" :aria-label="t('header.allCategories')">
      <h2 class="m-cats__title">{{ t('mobile.categories.all') }}</h2>
      <ul class="m-cats__grid">
        <li v-for="category in allCategories" :key="category.slug">
          <NuxtLink class="m-cats__card" :to="`/c/${category.slug}`">
            <span class="m-cats__card-title">{{ categoryName(category) }}</span>
            <img
              v-if="imageFor(category)"
              class="m-cats__card-img"
              :src="imageFor(category)"
              alt=""
              loading="lazy"
            />
          </NuxtLink>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.m-cats {
  min-height: 100%;
  padding: 16px;
  background: #f5f6fa;
}

.m-cats__section + .m-cats__section {
  margin-top: 24px;
}

.m-cats__title {
  margin: 0 0 12px;
  color: #1a1a1a;
  font-size: 20px;
  font-weight: var(--font-weight-bold);
}

.m-cats__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

/* White card: title top-left 16px/600, image centred below-right. */
.m-cats__card {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 148px;
  padding: 14px;
  border-radius: 12px;
  background: #ffffff;
  overflow: hidden;
}

.m-cats__card-title {
  color: #1a1a1a;
  font-size: 16px;
  font-weight: var(--font-weight-semibold);
  line-height: 1.35;
}

.m-cats__card-img {
  align-self: center;
  margin-top: auto;
  max-width: 72%;
  max-height: 88px;
  object-fit: contain;
}
</style>
