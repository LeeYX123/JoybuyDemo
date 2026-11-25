<script setup>
import { computed } from 'vue'
import { useRoute } from '#imports'

import { useBuyerAuth } from '../../composables/useBuyerAuth'
import { useCategoryTree } from '../../composables/useCategoryTree'
import { useLocale } from '../../composables/useLocale'
import { useMerchantEntry } from '../../composables/useMerchantEntry'

// Mobile header (docs/19 §1): main row 56px (burger + logo + apply-shop pill
// + account/cart icons), search row 52px (358×44 pill), category tab row
// 39px (16px text, active = 700 + black underline). Measured from the
// archived m.joybuy.co.uk homepage (2026-05-20 snapshot, iPhone 13 390px).
const emit = defineEmits(['open-drawer'])

const route = useRoute()
const { t, categoryName } = useLocale()
const { categories } = useCategoryTree()
const { isAuthenticated } = useBuyerAuth()
const {
  isConsoleEntry: sellerApproved,
  switching: sellerSwitching,
  openMerchantConsole,
} = useMerchantEntry()

// Same nav scope as the desktop header: categories hidden from the top nav
// stay hidden here (需求文档03 12.4).
const navCategories = computed(() =>
  (categories.value || []).filter((category) => category.visible_in_nav !== false),
)

// Category tab row target page and the drawer's 分类 page swap the burger
// for a back arrow (real-site expanded-state screenshots, 2026-11-24).
const showBack = computed(() => route.path === '/categories')

const tabs = computed(() => [{ slug: '', label: t('header.home') }, ...navCategories.value])

function tabTarget(category) {
  return category.slug ? `/c/${category.slug}` : '/'
}

function isTabActive(category) {
  if (!category.slug) return route.path === '/'
  return route.path === `/c/${category.slug}`
}

const applyShopHref = computed(() => ({
  path: '/auth/login',
  query: { next: '/account/apply-shop' },
}))

const accountTarget = computed(() => (isAuthenticated.value ? '/account' : '/auth/login'))
</script>

<template>
  <header class="m-header">
    <!-- Main row (56px) -->
    <div class="m-header__main">
      <button
        v-if="showBack"
        class="m-header__burger"
        type="button"
        :aria-label="t('mobile.drawer.back')"
        @click="$router.back()"
      >
        <svg
          viewBox="0 0 24 24"
          width="24"
          height="24"
          aria-hidden="true"
          fill="none"
          stroke="currentColor"
          stroke-width="1.8"
        >
          <path d="M15 5l-7 7 7 7" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </button>
      <button
        v-else
        class="m-header__burger"
        type="button"
        :aria-label="t('header.categories')"
        @click="emit('open-drawer')"
      >
        <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
          <g fill="currentColor">
            <circle cx="3" cy="5" r="1.6" />
            <circle cx="3" cy="12" r="1.6" />
            <circle cx="3" cy="19" r="1.6" />
            <rect x="7" y="3.8" width="14" height="2.4" rx="1.2" />
            <rect x="7" y="10.8" width="14" height="2.4" rx="1.2" />
            <rect x="7" y="17.8" width="14" height="2.4" rx="1.2" />
          </g>
        </svg>
      </button>

      <NuxtLink class="m-header__logo" to="/" aria-label="Joybuy">
        <img src="/images/logo.png" alt="Joybuy" width="88" height="24" />
      </NuxtLink>

      <div class="m-header__spacer"></div>

      <!-- 申请店铺 pill: replaces the real site's Ship-to pill (78×28, #F5F6FA),
           three states reused from the desktop header (requirement 12.2). -->
      <NuxtLink
        v-if="!isAuthenticated"
        class="m-header__apply"
        :to="applyShopHref"
        :aria-label="t('header.applyShop.apply')"
      >
        {{ t('mobile.applyShort') }}
      </NuxtLink>
      <button
        v-else-if="sellerApproved"
        class="m-header__apply"
        type="button"
        :disabled="sellerSwitching"
        :aria-label="t('header.applyShop.switch')"
        @click="openMerchantConsole"
      >
        {{ sellerSwitching ? t('merchantEntry.opening') : t('mobile.drawer.switchSeller') }}
      </button>
      <NuxtLink
        v-else
        class="m-header__apply"
        to="/account/apply-shop"
        :aria-label="t('header.applyShop.apply')"
      >
        {{ t('mobile.applyShort') }}
      </NuxtLink>

      <NuxtLink class="m-header__icon-btn" :to="accountTarget" :aria-label="t('header.myAccount')">
        <svg
          viewBox="0 0 24 24"
          width="24"
          height="24"
          aria-hidden="true"
          fill="none"
          stroke="currentColor"
          stroke-width="1.6"
        >
          <circle cx="12" cy="12" r="9" />
          <circle cx="9" cy="10.5" r="1" fill="currentColor" stroke="none" />
          <circle cx="15" cy="10.5" r="1" fill="currentColor" stroke="none" />
          <path d="M8.5 14.5c1 1.2 2.2 1.8 3.5 1.8s2.5-.6 3.5-1.8" stroke-linecap="round" />
        </svg>
      </NuxtLink>
      <NuxtLink class="m-header__icon-btn" to="/cart" :aria-label="t('header.cart')">
        <svg
          viewBox="0 0 24 24"
          width="24"
          height="24"
          aria-hidden="true"
          fill="none"
          stroke="currentColor"
          stroke-width="1.6"
        >
          <path
            d="M3.5 6.5h2l1.8 9.2a1.4 1.4 0 0 0 1.4 1.1h8.1a1.4 1.4 0 0 0 1.4-1.1l1.4-6.7H6.2"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
          <circle cx="9.6" cy="20" r="1.4" />
          <circle cx="16.6" cy="20" r="1.4" />
        </svg>
      </NuxtLink>
    </div>

    <!-- Search row (52px, pill 358×44 #F5F6FA) -->
    <div class="m-header__search-row">
      <NuxtLink class="m-header__search" to="/search" :aria-label="t('header.searchLabel')">
        <span class="m-header__search-text">{{ t('header.searchPlaceholder') }}</span>
        <svg
          viewBox="0 0 24 24"
          width="22"
          height="22"
          aria-hidden="true"
          fill="none"
          stroke="currentColor"
          stroke-width="1.8"
        >
          <circle cx="10.5" cy="10.5" r="6" />
          <path d="M15.5 15.5 20 20" stroke-linecap="round" />
        </svg>
      </NuxtLink>
    </div>

    <!-- Category tab row (39px, horizontal scroll) -->
    <nav class="m-header__tabs" :aria-label="t('header.categories')">
      <NuxtLink
        v-for="category in tabs"
        :key="category.slug || 'home'"
        class="m-header__tab"
        :class="{ 'm-header__tab--active': isTabActive(category) }"
        :to="tabTarget(category)"
      >
        <span class="m-header__tab-label">{{
          category.slug ? categoryName(category) : category.label
        }}</span>
      </NuxtLink>
    </nav>
  </header>
</template>

<style scoped>
.m-header {
  background: #ffffff;
}

/* Main row: 56px */
.m-header__main {
  display: flex;
  align-items: center;
  height: 56px;
  padding: 0 16px;
  gap: 8px;
}

.m-header__burger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #1a1a1a;
  cursor: pointer;
}

.m-header__logo img {
  display: block;
  width: 88px;
  height: 24px;
  object-fit: contain;
}

.m-header__spacer {
  flex: 1;
}

.m-header__apply {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 78px;
  height: 28px;
  padding: 0 10px;
  border-radius: 14px;
  background: #f5f6fa;
  color: #1a1a1a;
  font-size: 12px;
  font-weight: var(--font-weight-semibold, 600);
  white-space: nowrap;
}

/* Keep the three icons right-aligned as on the real site (icons 24×24). */
.m-header__icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  color: #1a1a1a;
}

/* Search row: 52px */
.m-header__search-row {
  display: flex;
  align-items: center;
  height: 52px;
  padding: 0 16px;
}

.m-header__search {
  display: flex;
  align-items: center;
  width: 100%;
  height: 44px;
  padding: 0 14px;
  border-radius: 22px;
  background: #f5f6fa;
  color: #9a9ca3;
}

.m-header__search-text {
  flex: 1;
  font-size: 16px;
  line-height: 24px;
}

/* Category tabs: 39px, active = bold + 2px black underline */
.m-header__tabs {
  display: flex;
  height: 39px;
  overflow-x: auto;
  scrollbar-width: none;
}

.m-header__tabs::-webkit-scrollbar {
  display: none;
}

.m-header__tab {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  height: 38px;
  padding: 0 12px;
  border-bottom: 2px solid transparent;
  color: #1a1a1a;
}

.m-header__tab-label {
  font-size: 16px;
  font-weight: var(--font-weight-regular);
  line-height: 22px;
  white-space: nowrap;
}

.m-header__tab--active .m-header__tab-label {
  font-weight: var(--font-weight-bold);
}

.m-header__tab--active {
  border-bottom-color: #1a1a1a;
}
</style>
