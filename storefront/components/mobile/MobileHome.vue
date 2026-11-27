<script setup>
import { computed } from 'vue'
import { useFetch, useRuntimeConfig } from '#imports'

import { useLocale } from '../../composables/useLocale'

import MobileBestsellers from './MobileBestsellers.vue'

// Mobile homepage (docs/19 §2). Renders the same CMS payload as the desktop
// home (decision: reuse the desktop CMS data, m. layout) in the m.joybuy
// mobile floor order:
//   Welcome -> Offers for you -> Category discovery -> Bestsellers ->
//   JoyPlus -> Brands we love -> (rich_text tail note) -> Recommended ->
//   About Joybuy. hero/banner modules render as full-width image cards.
const props = defineProps({
  modules: {
    type: Array,
    default: () => [],
  },
  loadFailed: {
    type: Boolean,
    default: false,
  },
})

const { t, locale } = useLocale()

function payloadOf(module) {
  return module && typeof module.payload === 'object' && module.payload !== null
    ? module.payload
    : {}
}

const campaignModule = computed(() =>
  props.modules.find((m) => m?.type === 'campaign_grid' && Array.isArray(payloadOf(m).items)),
)
const discoveryModule = computed(() =>
  props.modules.find(
    (m) =>
      m?.type === 'link_grid' &&
      payloadOf(m).variant !== 'brand_logos' &&
      Array.isArray(payloadOf(m).items),
  ),
)
const brandsModule = computed(() =>
  props.modules.find((m) => m?.type === 'link_grid' && payloadOf(m).variant === 'brand_logos'),
)
const richTextModules = computed(() => props.modules.filter((m) => m?.type === 'rich_text'))
const bannerModules = computed(() =>
  props.modules.filter(
    (m) => (m?.type === 'hero' || m?.type === 'banner') && Object.keys(payloadOf(m)).length > 0,
  ),
)

const campaignTiles = computed(() => {
  const items = campaignModule.value ? payloadOf(campaignModule.value).items : []
  return items.filter((tile) => tile && typeof tile.title === 'string' && tile.title.trim())
})
const campaignBackground = computed(() => {
  const image = campaignModule.value ? payloadOf(campaignModule.value).background_path : null
  return image ? { backgroundImage: `url(${image})` } : { background: 'rgba(245, 246, 250, 0.9)' }
})

const discoveryTiles = computed(() => {
  const items = discoveryModule.value ? payloadOf(discoveryModule.value).items : []
  return items.filter((tile) => tile && (tile.label || tile.title))
})

const brandItems = computed(() => {
  const payload = brandsModule.value ? payloadOf(brandsModule.value) : {}
  return Array.isArray(payload.items) ? payload.items.slice(0, 12) : []
})

function tileTitle(tile) {
  return locale.value === 'zh' && tile.title_zh ? tile.title_zh : tile.title
}
function tileSubtitle(tile) {
  return locale.value === 'zh' && tile.subtitle_zh ? tile.subtitle_zh : tile.subtitle
}
function tileSubtitleVisible(tile) {
  return Boolean(tileSubtitle(tile))
}
function tileLabel(tile) {
  if (locale.value === 'zh' && tile.label_zh) return tile.label_zh
  return tile.label || tile.title || ''
}

// Recommended for you: 2-col grid, first page of the recommendations pool
// (same API and URL pattern as the desktop HomeRecommended floor).
const config = useRuntimeConfig()
const recoUrl = import.meta.server
  ? `${config.apiBaseInternal}/recommendations?page=1`
  : '/api/v1/recommendations?page=1'
const { data: recoData } = useFetch(() => recoUrl, {
  key: 'mobile-home-reco',
})
const recoItems = computed(() => {
  const items = Array.isArray(recoData.value?.items) ? recoData.value.items : []
  return items.slice(0, 20)
})

const imgFallback = '/images/logo.png'
function imgOf(item) {
  const src = item?.image_path || item?.image
  return typeof src === 'string' && src ? src : imgFallback
}
function priceOf(item) {
  const raw = item?.retail_price
  if (typeof raw === 'string' && raw.trim()) return raw.trim()
  const price = item?.family_max_price ?? item?.price_min ?? item?.price
  return price == null ? '' : String(price)
}

// Welcome floor bullet icons reuse the About floor SVGs.
const welcomeBullets = computed(() => [
  { key: 'speedy', label: t('mobile.home.speedy') },
  { key: 'trusted', label: t('mobile.home.trusted') },
  { key: 'support', label: t('mobile.home.support') },
])
const aboutBullets = computed(() => [
  { key: 'speedy', label: t('mobile.home.about1') },
  { key: 'trusted', label: t('mobile.home.about2') },
  { key: 'support', label: t('mobile.home.about3') },
])
</script>

<template>
  <div class="m-home">
    <template v-if="props.modules.length > 0">
      <!-- Welcome floor -->
      <section class="m-welcome">
        <h2 class="m-welcome__title">{{ t('mobile.home.welcomeTitle') }}</h2>
        <ul class="m-welcome__bullets">
          <li v-for="bullet in welcomeBullets" :key="bullet.key">
            <span class="m-welcome__circle" aria-hidden="true">
              <svg
                v-if="bullet.key === 'speedy'"
                viewBox="0 0 24 24"
                width="26"
                height="26"
                fill="none"
                stroke="currentColor"
                stroke-width="1.6"
              >
                <path d="M3 7h11v9H3zM14 10h4l3 3v3h-7z" stroke-linejoin="round" />
                <circle cx="7" cy="18" r="1.8" />
                <circle cx="17" cy="18" r="1.8" />
              </svg>
              <svg
                v-else-if="bullet.key === 'trusted'"
                viewBox="0 0 24 24"
                width="26"
                height="26"
                fill="none"
                stroke="currentColor"
                stroke-width="1.6"
              >
                <circle cx="12" cy="9" r="5" />
                <path d="m9.5 13 -1.5 8 4-2.4 4 2.4-1.5-8" stroke-linejoin="round" />
              </svg>
              <svg
                v-else
                viewBox="0 0 24 24"
                width="26"
                height="26"
                fill="none"
                stroke="currentColor"
                stroke-width="1.6"
              >
                <path d="M21 12a9 9 0 1 0-3 6.7" stroke-linecap="round" />
                <path d="M21 12V7m0 5h-5" stroke-linecap="round" stroke-linejoin="round" />
                <text
                  x="10"
                  y="15"
                  font-size="7"
                  fill="currentColor"
                  stroke="none"
                  font-weight="700"
                >
                  24/7
                </text>
              </svg>
            </span>
            <span class="m-welcome__bullet-label">{{ bullet.label }}</span>
          </li>
        </ul>
        <NuxtLink class="m-welcome__cta" to="/auth/register">{{
          t('mobile.home.registerCta')
        }}</NuxtLink>
        <NuxtLink class="m-welcome__learn" to="/pages/about-us">{{
          t('mobile.home.learnMore')
        }}</NuxtLink>
      </section>

      <!-- hero/banner floors: full-width image cards -->
      <section v-for="(module, index) in bannerModules" :key="`banner-${index}`" class="m-banner">
        <NuxtLink
          v-if="
            payloadOf(module).href ||
            payloadOf(module).image_path ||
            payloadOf(module).background_path
          "
          class="m-banner__card"
          :to="payloadOf(module).href || ''"
          :style="{
            backgroundImage:
              payloadOf(module).image_path || payloadOf(module).background_path
                ? `url(${payloadOf(module).image_path || payloadOf(module).background_path})`
                : null,
          }"
        >
          <span v-if="payloadOf(module).title" class="m-banner__title">{{
            locale === 'zh' && payloadOf(module).title_zh
              ? payloadOf(module).title_zh
              : payloadOf(module).title
          }}</span>
        </NuxtLink>
      </section>

      <!-- Offers for you (campaign_grid, horizontal cards) -->
      <section v-if="campaignTiles.length > 0" class="m-offers">
        <h2 class="m-floor-title">{{ t('mobile.home.offers') }}</h2>
        <ul class="m-offers__row" :style="campaignBackground">
          <li v-for="tile in campaignTiles" :key="tile.title">
            <NuxtLink
              class="m-offers__card"
              :to="tile.href || ''"
              :style="tile.image_path ? { backgroundImage: `url(${tile.image_path})` } : null"
            >
              <span class="m-offers__scrim" aria-hidden="true"></span>
              <span class="m-offers__text">
                <strong class="m-offers__title">{{ tileTitle(tile) }}</strong>
                <span v-if="tileSubtitleVisible(tile)" class="m-offers__subtitle">{{
                  tileSubtitle(tile)
                }}</span>
              </span>
              <span class="m-offers__shop">{{ t('mobile.home.shopNow') }}</span>
            </NuxtLink>
          </li>
        </ul>
      </section>

      <!-- Category discovery (link_grid tiles, horizontal circles) -->
      <section v-if="discoveryTiles.length > 0" class="m-discovery">
        <h2 class="m-floor-title">{{ t('mobile.home.discovery') }}</h2>
        <ul class="m-discovery__row">
          <li v-for="tile in discoveryTiles" :key="tileLabel(tile)">
            <NuxtLink class="m-discovery__item" :to="tile.href || ''">
              <span class="m-discovery__circle">
                <img
                  v-if="tile.icon_path || tile.image_path"
                  :src="tile.icon_path || tile.image_path"
                  alt=""
                  loading="lazy"
                />
              </span>
              <span class="m-discovery__label">{{ tileLabel(tile) }}</span>
            </NuxtLink>
          </li>
        </ul>
      </section>

      <!-- Bestsellers (search API, horizontal ranked cards) -->
      <MobileBestsellers class="m-home__bestsellers" />

      <!-- JoyPlus -->
      <section class="m-joyplus">
        <h2 class="m-joyplus__title">{{ t('mobile.home.joyplusTitle') }}</h2>
        <ul class="m-joyplus__list">
          <li
            v-for="(line, index) in [
              t('mobile.home.joyplus1'),
              t('mobile.home.joyplus2'),
              t('mobile.home.joyplus3'),
            ]"
            :key="index"
          >
            <span class="m-joyplus__badge" aria-hidden="true"></span>
            {{ line }}
          </li>
        </ul>
        <NuxtLink class="m-joyplus__cta" to="/joyplus">{{ t('mobile.home.joyplusCta') }}</NuxtLink>
      </section>

      <!-- Brands we love (marquee circles) -->
      <section v-if="brandItems.length > 0" class="m-brands">
        <h2 class="m-floor-title">{{ t('mobile.home.brands') }}</h2>
        <div class="m-brands__marquee">
          <ul class="m-brands__row">
            <li v-for="(brand, index) in brandItems" :key="`${brand.name}-${index}`">
              <span class="m-brands__circle">
                <img v-if="brand.logo_path" :src="brand.logo_path" alt="" loading="lazy" />
              </span>
              <span class="m-brands__name">{{ brand.name }}</span>
            </li>
          </ul>
        </div>
      </section>

      <!-- CMS rich_text tail notes -->
      <section v-for="(module, index) in richTextModules" :key="`rich-${index}`" class="m-richtext">
        <CmsRichText :payload="payloadOf(module)" />
      </section>

      <!-- Recommended for you (2-col grid) -->
      <section class="m-reco">
        <h2 class="m-floor-title">{{ t('mobile.home.reco') }}</h2>
        <ul v-if="recoItems.length > 0" class="m-reco__grid">
          <li v-for="(item, index) in recoItems" :key="`${item.spu_public_id}-${index}`">
            <NuxtLink class="m-reco__card" :to="`/p/${item.spu_public_id}`">
              <img class="m-reco__img" :src="imgOf(item)" alt="" loading="lazy" />
              <span class="m-reco__name">{{
                locale === 'zh' && item.title_zh ? item.title_zh : item.title
              }}</span>
              <span
                v-if="Number(item.rating_average) > 0 || item.sold_amount"
                class="m-reco__meta"
              >
                <span v-if="Number(item.rating_average) > 0" class="m-reco__rating">
                  ★ {{ Number(item.rating_average).toFixed(1) }}
                </span>
                <span v-if="item.sold_amount" class="m-reco__sold">
                  {{ t('product.soldCount', { n: item.sold_amount }) }}
                </span>
              </span>
              <span class="m-reco__self-operated">{{ t('product.soldByJoybuy') }}</span>
              <span class="m-reco__price">{{ priceOf(item) }}</span>
            </NuxtLink>
          </li>
        </ul>
      </section>

      <!-- About Joybuy -->
      <section class="m-about">
        <h2 class="m-about__title">{{ t('mobile.home.about') }}</h2>
        <ul class="m-about__list">
          <li v-for="bullet in aboutBullets" :key="bullet.key">
            <span class="m-about__icon" aria-hidden="true">
              <svg
                viewBox="0 0 24 24"
                width="22"
                height="22"
                fill="none"
                stroke="currentColor"
                stroke-width="1.6"
              >
                <path d="M3 7h11v9H3zM14 10h4l3 3v3h-7z" stroke-linejoin="round" />
                <circle cx="7" cy="18" r="1.8" />
                <circle cx="17" cy="18" r="1.8" />
              </svg>
            </span>
            {{ bullet.label }}
          </li>
        </ul>
        <NuxtLink class="m-about__learn" to="/help/customer-service">{{
          t('mobile.home.learnMore')
        }}</NuxtLink>
      </section>
    </template>

    <section v-else-if="props.loadFailed" class="m-home__unavailable" role="status">
      <p>The home page is temporarily unavailable. Please try again shortly.</p>
    </section>
  </div>
</template>

<style scoped>
.m-home {
  background: #ffffff;
}

.m-home__unavailable {
  margin: 48px 16px;
  padding: 32px;
  border: 1px dashed var(--colour-border-strong, #c2c4cc);
  border-radius: 12px;
  color: var(--colour-muted, #7a7d85);
  text-align: center;
}

/* Floor title: 28px/700, matches the real m. floors. */
.m-floor-title {
  margin: 0;
  padding: 0 16px;
  color: #1a1a1a;
  font-size: 28px;
  font-weight: var(--font-weight-bold);
  line-height: 1.2;
}

/* Welcome floor */
.m-welcome {
  padding: 20px 16px 28px;
  text-align: center;
}

.m-welcome__title {
  margin: 0;
  color: #1a1a1a;
  font-size: 28px;
  font-weight: var(--font-weight-semibold);
}

.m-welcome__bullets {
  display: flex;
  justify-content: space-between;
  max-width: 358px;
  margin: 24px auto 0;
  padding: 0;
  list-style: none;
}

.m-welcome__circle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 76px;
  height: 76px;
  border-radius: 50%;
  background: #f0f1f4;
  color: #1a1a1a;
}

.m-welcome__bullet-label {
  display: block;
  margin-top: 10px;
  color: #1a1a1a;
  font-size: 16px;
}

.m-welcome__cta {
  display: flex;
  align-items: center;
  justify-content: center;
  max-width: 358px;
  height: 36px;
  margin: 24px auto 0;
  border-radius: 4px;
  background: #1a1a1a;
  color: #ffffff;
  font-size: 16px;
  font-weight: var(--font-weight-semibold);
}

.m-welcome__learn {
  display: inline-block;
  margin-top: 16px;
  color: #1a1a1a;
  font-size: 16px;
  text-decoration: underline;
  text-underline-offset: 3px;
}

/* Banner floors */
.m-banner {
  margin-top: 16px;
}

.m-banner__card {
  display: flex;
  align-items: flex-end;
  width: 100%;
  min-height: 140px;
  padding: 16px;
  background-color: #f0f1f4;
  background-size: cover;
  background-position: center;
  color: #ffffff;
  font-size: 20px;
  font-weight: var(--font-weight-bold);
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.45);
}

/* Offers for you: horizontal cards ~248×267 r16 */
.m-offers {
  margin-top: 32px;
}

.m-offers__row {
  display: flex;
  gap: 12px;
  margin: 12px 0 0;
  padding: 16px;
  list-style: none;
  overflow-x: auto;
  scrollbar-width: none;
}

.m-offers__row::-webkit-scrollbar {
  display: none;
}

.m-offers__row > li {
  flex-shrink: 0;
}

.m-offers__card {
  position: relative;
  display: flex;
  flex-direction: column;
  width: 248px;
  height: 267px;
  padding: 16px;
  border-radius: 16px;
  background-color: #f4f5f9;
  background-size: cover;
  background-position: center;
  overflow: hidden;
}

.m-offers__scrim {
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.72) 0%, rgba(255, 255, 255, 0) 55%);
}

.m-offers__text {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.m-offers__title {
  color: #1a1a1a;
  font-size: 22px;
  font-weight: var(--font-weight-bold);
  line-height: 1.25;
}

.m-offers__subtitle {
  color: #55565b;
  font-size: 14px;
}

.m-offers__shop {
  position: relative;
  margin-top: auto;
  align-self: flex-start;
  color: #1a1a1a;
  font-size: 16px;
  font-weight: var(--font-weight-semibold);
  text-decoration: underline;
  text-underline-offset: 3px;
}

/* Category discovery: horizontal circles ~95px */
.m-discovery {
  margin-top: 32px;
}

.m-discovery__row {
  display: flex;
  gap: 20px;
  margin: 14px 0 0;
  padding: 0 16px 4px;
  list-style: none;
  overflow-x: auto;
  scrollbar-width: none;
}

.m-discovery__row::-webkit-scrollbar {
  display: none;
}

.m-discovery__row > li {
  flex-shrink: 0;
}

.m-discovery__item {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 95px;
}

.m-discovery__circle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 95px;
  height: 95px;
  border-radius: 50%;
  background: #f0f1f4;
  overflow: hidden;
}

.m-discovery__circle img {
  max-width: 72%;
  max-height: 72%;
  object-fit: contain;
}

.m-discovery__label {
  margin-top: 8px;
  max-width: 95px;
  overflow: hidden;
  color: #1a1a1a;
  font-size: 14px;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* JoyPlus: pale gradient band */
.m-joyplus {
  margin-top: 32px;
  padding: 24px 16px 28px;
  background: linear-gradient(135deg, #eef0fa 0%, #f7f0fa 100%);
}

.m-joyplus__title {
  margin: 0;
  color: #1a1a1a;
  font-size: 28px;
  font-weight: var(--font-weight-bold);
}

.m-joyplus__list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin: 20px 0 0;
  padding: 0;
  list-style: none;
  color: #1a1a1a;
  font-size: 18px;
}

.m-joyplus__list li {
  display: flex;
  align-items: center;
  gap: 12px;
}

.m-joyplus__badge {
  display: inline-flex;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  background: #ffffff;
  box-shadow: 0 1px 3px rgba(26, 26, 26, 0.08);
}

.m-joyplus__cta {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 44px;
  margin-top: 24px;
  border-radius: 8px;
  background: #1a1a1a;
  color: #ffffff;
  font-size: 18px;
  font-weight: var(--font-weight-bold);
}

/* Brands we love */
.m-brands {
  margin-top: 32px;
}

.m-brands__row {
  display: flex;
  gap: 20px;
  margin: 14px 0 0;
  padding: 0 16px 4px;
  list-style: none;
  overflow-x: auto;
  scrollbar-width: none;
}

.m-brands__row::-webkit-scrollbar {
  display: none;
}

.m-brands__row > li {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 96px;
}

.m-brands__circle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 96px;
  height: 96px;
  border-radius: 50%;
  background: #f0f1f4;
  overflow: hidden;
}

.m-brands__circle img {
  max-width: 64%;
  max-height: 64%;
  object-fit: contain;
}

.m-brands__name {
  margin-top: 8px;
  max-width: 96px;
  overflow: hidden;
  color: #1a1a1a;
  font-size: 13px;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* rich text tail note */
.m-richtext {
  margin-top: 24px;
  padding: 0 16px;
  color: #55565b;
  font-size: 13px;
  line-height: 1.6;
}

/* Recommended: 2-col grid */
.m-reco {
  margin-top: 32px;
}

.m-reco__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin: 14px 0 0;
  padding: 0 16px;
  list-style: none;
}

.m-reco__card {
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  background: #ffffff;
  overflow: hidden;
  box-shadow: 0 1px 2px rgba(26, 26, 26, 0.06);
}

.m-reco__img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  background: #f0f1f4;
}

.m-reco__name {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  padding: 8px 10px 0;
  color: #1a1a1a;
  font-size: 14px;
  line-height: 20px;
  min-height: 48px;
}

/* 评分 | 已售 + 自营徽标（ADR-0003，真站 m 站卡片同款行）。 */
.m-reco__meta {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  color: var(--colour-muted, #666);
  font-size: 12px;
}

.m-reco__rating {
  color: var(--colour-text, #1a1a1a);
  font-weight: 500;
}

.m-reco__self-operated {
  padding: 2px 10px 0;
  color: var(--colour-text, #1a1a1a);
  font-size: 12px;
  font-weight: 500;
}

.m-reco__price {
  padding: 6px 10px 12px;
  color: var(--colour-accent, #e1251b);
  font-size: 16px;
  font-weight: var(--font-weight-bold);
}

/* About Joybuy: light grey band */
.m-about {
  margin-top: 32px;
  padding: 24px 16px 32px;
  background: #f5f6fa;
}

.m-about__title {
  margin: 0;
  color: #1a1a1a;
  font-size: 24px;
  font-weight: var(--font-weight-bold);
}

.m-about__list {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin: 20px 0 0;
  padding: 0;
  list-style: none;
  color: #1a1a1a;
  font-size: 16px;
}

.m-about__list li {
  display: flex;
  align-items: center;
  gap: 12px;
}

.m-about__icon {
  display: inline-flex;
  color: #1a1a1a;
}

.m-about__learn {
  display: inline-block;
  margin-top: 20px;
  color: #1a1a1a;
  font-size: 16px;
  font-weight: var(--font-weight-semibold);
  text-decoration: underline;
  text-underline-offset: 3px;
}
</style>
