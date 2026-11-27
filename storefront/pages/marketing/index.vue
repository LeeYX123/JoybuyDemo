<script setup>
import { computed, ref } from 'vue'
import { useFetch, useHead, useRoute, useRuntimeConfig } from '#imports'

import { useLocale } from '../composables/useLocale'

import AppContainer from '../components/AppContainer.vue'
import ProductCard from '../components/ProductCard.vue'

// Activity landing page /marketing?activityId=&tagId= (需求文档03 14.2).
// Real-site structure (joybuy.co.uk/marketing, measured 2026-11-20):
// 384px full-bleed banner with 44px title / 18px subtitle, then a 234px
// left filter column (1px #E0E1E5 divider) and a 4-column product grid.
// Deliberately omitted: the top tab row (运动服饰/女性/男性) and the brand
// filter — only the 类别 filter remains, per the requirement.
// Products come from the recommendations pool filtered to the clothing and
// outdoor-sports categories, merged (no per-activity product pool).
const route = useRoute()
const { t, locale } = useLocale()
const config = useRuntimeConfig()
const apiBase = import.meta.server ? config.apiBaseInternal : config.public.apiBase

const activityId = computed(() => String(route.query.activityId || '').trim())

function recommendationUrl(category) {
  // has_local_image=1: skip crawled products whose image file never landed on
  // disk, so the landing page never renders broken images (console errors).
  return `${apiBase}/recommendations?page=1&has_local_image=1&category=${encodeURIComponent(category)}`
}

// Two awaited SSR fetches (24 items each) keep the floor server-rendered.
const { data: clothingData } = await useFetch(() => recommendationUrl('clothing-accessories'), {
  key: 'marketing-clothing',
})
const { data: outdoorData } = await useFetch(() => recommendationUrl('outdoor-sports'), {
  key: 'marketing-outdoor',
})
// The home CMS payload carries the weekly card title/subtitle/banner image;
// matching by activityId keeps the landing banner consistent with the card.
const { data: homeData } = await useFetch(`${apiBase}/storefront/home`, {
  key: 'marketing-home',
})

const weeklyItems = computed(() => {
  const modules = Array.isArray(homeData.value?.modules) ? homeData.value.modules : []
  const weekly = modules.find((module) => module.type === 'weekly_picks')
  return Array.isArray(weekly?.payload?.items) ? weekly.payload.items : []
})

function itemActivityId(item) {
  const match = /[?&]activityId=(\d+)/.exec(String(item?.href || ''))
  return match ? match[1] : ''
}

const matchedItem = computed(
  () => weeklyItems.value.find((item) => itemActivityId(item) === activityId.value) || null,
)

const banner = computed(() => ({
  title:
    (locale.value === 'zh' && matchedItem.value?.title_zh) ||
    matchedItem.value?.title ||
    t('marketing.title'),
  subtitle:
    (locale.value === 'zh' && matchedItem.value?.subtitle_zh) ||
    matchedItem.value?.subtitle ||
    t('marketing.subtitle'),
  image:
    matchedItem.value?.image_path ||
    weeklyItems.value.find((item) => item?.image_path)?.image_path ||
    '',
}))

useHead(() => ({ title: `${banner.value.title} | Joybuy` }))

const bannerStyle = computed(() =>
  banner.value.image
    ? { backgroundImage: `url(${banner.value.image})` }
    : { background: 'linear-gradient(120deg, #2a2a2a, #555)' },
)

function withSource(items, source) {
  return (Array.isArray(items) ? items : []).map((item) => ({ ...item, _source: source }))
}

// Deterministic merge: alternate clothing / outdoor so both categories are
// visible at the top; de-duplicate by SPU (a product can carry one category
// only, but the guard keeps the list stable if the API ever overlaps).
const products = computed(() => {
  const clothing = withSource(clothingData.value?.items, 'clothing')
  const outdoor = withSource(outdoorData.value?.items, 'outdoor')
  const merged = []
  const seen = new Set()
  const max = Math.max(clothing.length, outdoor.length)
  for (let index = 0; index < max; index += 1) {
    for (const item of [clothing[index], outdoor[index]]) {
      if (!item) continue
      const key = String(item.spu_public_id || item.public_id || item.title)
      if (seen.has(key)) continue
      seen.add(key)
      merged.push(item)
    }
  }
  return merged
})

const activeCategory = ref('all')
const categoryOptions = computed(() => [
  { value: 'all', label: t('marketing.filter.all') },
  { value: 'clothing', label: t('marketing.category.clothing') },
  { value: 'outdoor', label: t('marketing.category.outdoor') },
])

const visibleProducts = computed(() =>
  activeCategory.value === 'all'
    ? products.value
    : products.value.filter((item) => item._source === activeCategory.value),
)
</script>

<template>
  <div class="marketing-page">
    <section class="marketing-banner" :style="bannerStyle" aria-labelledby="marketing-title">
      <div class="marketing-banner__inner">
        <h1 id="marketing-title" class="marketing-banner__title">{{ banner.title }}</h1>
        <p v-if="banner.subtitle" class="marketing-banner__subtitle">{{ banner.subtitle }}</p>
      </div>
    </section>

    <AppContainer class="marketing-body">
      <aside class="marketing-filters" :aria-label="t('marketing.filter.title')">
        <p class="marketing-filters__heading">{{ t('marketing.filter.title') }}</p>
        <div class="marketing-filters__group">
          <h2 class="marketing-filters__group-title">{{ t('marketing.filter.category') }}</h2>
          <ul class="marketing-filters__options">
            <li v-for="option in categoryOptions" :key="option.value">
              <button
                class="marketing-filters__option"
                :class="{ 'marketing-filters__option--active': activeCategory === option.value }"
                type="button"
                :aria-pressed="activeCategory === option.value"
                @click="activeCategory = option.value"
              >
                {{ option.label }}
              </button>
            </li>
          </ul>
        </div>
      </aside>

      <section class="marketing-products" :aria-label="banner.title">
        <ul v-if="visibleProducts.length > 0" class="marketing-products__grid">
          <li v-for="product in visibleProducts" :key="product.spu_public_id || product.title">
            <ProductCard :product="product" />
          </li>
        </ul>
        <p v-else class="marketing-products__empty" role="status">
          {{ t('marketing.empty') }}
        </p>
      </section>
    </AppContainer>
  </div>
</template>

<style scoped>
.marketing-page {
  margin-top: 0;
  background: #fff;
}

/* Measured real banner: 384px tall, full-bleed background image, centered
 * 1264px content (44px/700 title, 18px/500 subtitle). */
.marketing-banner {
  width: 100vw;
  height: 384px;
  margin-inline: calc(50% - 50vw);
  background-position: center;
  background-size: cover;
  background-repeat: no-repeat;
}

.marketing-banner__inner {
  display: flex;
  flex-direction: column;
  justify-content: center;
  width: 100%;
  max-width: var(--container-max);
  height: 100%;
  margin-inline: auto;
  padding-inline: var(--container-pad);
  box-sizing: border-box;
  background: linear-gradient(90deg, rgb(0 0 0 / 35%), rgb(0 0 0 / 5%) 70%);
}

.marketing-banner__title {
  width: 632px;
  max-width: 100%;
  margin: 0 0 12px;
  overflow: hidden;
  color: #fff;
  font-size: 44px;
  font-weight: 700;
  line-height: 44px;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.marketing-banner__subtitle {
  width: 632px;
  max-width: 100%;
  margin: 0;
  overflow: hidden;
  color: #fff;
  font-size: 18px;
  font-weight: 500;
  line-height: 24px;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

/* Real content row: 234px filter column + product list, 34px below banner. */
.marketing-body {
  display: flex;
  align-items: flex-start;
  margin-top: 34px;
}

.marketing-filters {
  flex: 0 0 234px;
  width: 234px;
  padding: 0 24px 12px 0;
  border-right: 1px solid #e0e1e5;
}

.marketing-filters__heading {
  margin: 0;
  padding: 4px 0 16px;
  border-bottom: 1px solid #e0e1e5;
  color: #1a1a1a;
  font-size: 16px;
  font-weight: 600;
  line-height: 22px;
}

.marketing-filters__group {
  padding-top: 16px;
}

.marketing-filters__group-title {
  margin: 0 0 8px;
  color: #1a1a1a;
  font-size: 16px;
  font-weight: 600;
  line-height: 22px;
}

.marketing-filters__options {
  margin: 0;
  padding: 0;
  list-style: none;
}

.marketing-filters__option {
  display: block;
  width: 100%;
  padding: 7px 0;
  border: 0;
  background: none;
  color: #1a1a1a;
  font: inherit;
  font-size: 14px;
  line-height: 20px;
  text-align: left;
  cursor: pointer;
}

.marketing-filters__option:hover,
.marketing-filters__option--active {
  font-weight: 600;
}

.marketing-products {
  flex: 1;
  min-width: 0;
  margin-left: 24px;
}

.marketing-products__grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 24px 16px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.marketing-products__empty {
  margin-block: 48px;
  color: var(--colour-muted);
  text-align: center;
}

@media (max-width: 80rem) {
  .marketing-products__grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 48rem) {
  .marketing-banner {
    height: 240px;
  }

  .marketing-banner__title {
    font-size: 30px;
    line-height: 34px;
  }

  .marketing-body {
    display: block;
  }

  .marketing-filters {
    width: 100%;
    border-right: 0;
    border-bottom: 1px solid #e0e1e5;
    padding: 12px 0;
  }

  .marketing-filters__options {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .marketing-filters__option {
    width: auto;
    padding: 4px 12px;
    border: 1px solid #d9dbe1;
    border-radius: 16px;
  }

  .marketing-products {
    margin-left: 0;
    margin-top: 20px;
  }

  .marketing-products__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
