<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { useBuyerAuth } from '../composables/useBuyerAuth'
import { useCategoryTree } from '../composables/useCategoryTree'
import { useLocale } from '../composables/useLocale'

import AppCategoryPanel from './AppCategoryPanel.vue'

const props = defineProps({
  cartCount: {
    type: Number,
    default: 0,
  },
})

const { t, locale, toggleLocale, categoryName } = useLocale()
const { categories } = useCategoryTree()
const { isAuthenticated, account, logout } = useBuyerAuth()

// Notice strip (docs/12 global): the "Same-day & Next-day Delivery" and
// "Download App for Welcome Offers" lines are removed per requirement 1-5,
// and the "Download Joybuy" entry per requirement 1-4.
const notices = computed(() => [
  t('topStrip.welcomeOffers'),
  t('topStrip.quality'),
  t('topStrip.support'),
  t('topStrip.freeReturns'),
])
const noticeIndex = ref(0)
let noticeTimer = null

function showNotice(index) {
  const total = notices.value.length
  noticeIndex.value = ((index % total) + total) % total
}

onMounted(() => {
  noticeTimer = setInterval(() => showNotice(noticeIndex.value + 1), 6000)
})

onBeforeUnmount(() => {
  if (noticeTimer) clearInterval(noticeTimer)
})

const regionLabel = computed(() => (locale.value === 'zh' ? 'UK | 中文(简体)' : 'UK | English'))

// Category row: the 11 standard categories from the API (requirement 1-1),
// spread edge to edge like the real header.
const items = computed(() =>
  categories.value.map((category) => ({
    label: categoryName(category),
    to: `/c/${category.slug}`,
  })),
)

const formattedCartCount = computed(() => (props.cartCount > 99 ? '99+' : String(props.cartCount)))

const panelOpen = ref(false)
const accountMenuOpen = ref(false)
let panelCloseTimer = null

// The categories panel opens on hover over the trigger (real-site behaviour);
// a short close delay lets the pointer travel to the panel without flicker.
function openPanel() {
  if (panelCloseTimer) {
    clearTimeout(panelCloseTimer)
    panelCloseTimer = null
  }
  panelOpen.value = true
}

function schedulePanelClose() {
  if (panelCloseTimer) clearTimeout(panelCloseTimer)
  panelCloseTimer = setTimeout(() => {
    panelOpen.value = false
    panelCloseTimer = null
  }, 150)
}

function togglePanel() {
  // Hover has usually already opened the panel; the click just keeps it
  // open (touch users). Closing happens on mouse-leave or the close button.
  panelOpen.value = true
}

async function signOut() {
  accountMenuOpen.value = false
  await logout()
}

const accountLabel = computed(() => account.value?.email || account.value?.phone || '')

// Logo asset lives in the Nuxt public dir (storefront/public/images).
const brandLogoUrl = '/images/logo.png'
</script>

<template>
  <header class="site-header">
    <!-- Black notice strip: rotating service promises + locale switch. -->
    <div class="top-strip">
      <div class="top-strip__inner">
        <button class="top-strip__region" type="button" @click="toggleLocale">
          {{ regionLabel }}
        </button>
        <div class="top-strip__notice">
          <button
            class="top-strip__arrow"
            type="button"
            aria-label="Previous notice"
            @click="showNotice(noticeIndex - 1)"
          >
            ‹
          </button>
          <p class="top-strip__text">{{ notices[noticeIndex] }}</p>
          <button
            class="top-strip__arrow"
            type="button"
            aria-label="Next notice"
            @click="showNotice(noticeIndex + 1)"
          >
            ›
          </button>
        </div>
        <span class="top-strip__spacer" aria-hidden="true"></span>
      </div>
    </div>

    <div class="site-header__inner">
      <div class="site-header__top">
        <NuxtLink class="brand" to="/" aria-label="Joybuy home">
          <!-- Real Joybuy wordmark asset, hosted locally (no CDN). Bound at
               runtime so the bundler does not turn it into a module import. -->
          <img class="brand__logo" :src="brandLogoUrl" alt="" width="110" height="30" />
        </NuxtLink>

        <div class="categories-anchor" @mouseenter="openPanel" @mouseleave="schedulePanelClose">
          <button
            class="categories-button"
            type="button"
            aria-haspopup="dialog"
            :aria-expanded="panelOpen"
            :aria-label="t('header.categories')"
            @click="togglePanel"
          >
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path d="M3 6h18v2H3V6Zm0 5h18v2H3v-2Zm0 5h18v2H3v-2Z" fill="currentColor" />
            </svg>
            <span class="categories-button__label">{{ t('header.categories') }}</span>
          </button>

          <AppCategoryPanel
            :open="panelOpen"
            :categories="categories"
            @close="panelOpen = false"
            @mouseenter="openPanel"
            @mouseleave="schedulePanelClose"
          />
        </div>

        <form class="search" role="search" action="/search" method="get">
          <label class="visually-hidden" for="site-search">{{ t('header.searchLabel') }}</label>
          <input
            id="site-search"
            class="search__input"
            type="search"
            name="q"
            :placeholder="t('header.searchPlaceholder')"
            autocomplete="off"
          />
          <button class="search__submit" type="submit" aria-label="Search">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path
                d="M10.5 3a7.5 7.5 0 1 1 0 15 7.5 7.5 0 0 1 0-15Zm0 2a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11Zm4.8 9.3 5.7 5.7-1.4 1.4-5.7-5.7 1.4-1.4Z"
                fill="currentColor"
              />
            </svg>
          </button>
        </form>

        <nav class="account-nav" :aria-label="t('header.accountAndCart')">
          <button class="account-nav__deliver" type="button">
            <svg
              class="account-nav__deliver-icon"
              viewBox="0 0 24 24"
              width="24"
              height="24"
              aria-hidden="true"
            >
              <path
                d="M12 2a7 7 0 0 1 7 7c0 2.4-1.2 4.5-3.2 5.7L12 22l-3.8-7.3A6.98 6.98 0 0 1 5 9a7 7 0 0 1 7-7Zm0 2a5 5 0 0 0-5 5c0 1.8.9 3.3 2.3 4.2l.7.5L12 18l2-4.3.7-.5A4.98 4.98 0 0 0 17 9a5 5 0 0 0-5-5Zm0 3a2 2 0 1 1 0 4 2 2 0 0 1 0-4Z"
                fill="currentColor"
              />
            </svg>
            <span class="account-nav__deliver-text">{{ t('header.deliverTo') }} SW1A 1AA</span>
          </button>

          <div v-if="isAuthenticated" class="account-menu">
            <button
              class="icon-button"
              type="button"
              :aria-label="t('header.myAccount')"
              :aria-expanded="accountMenuOpen"
              @click="accountMenuOpen = !accountMenuOpen"
            >
              <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
                <path
                  d="M12 4a4 4 0 1 1 0 8 4 4 0 0 1 0-8Zm0 2a2 2 0 1 0 0 4 2 2 0 0 0 0-4Zm0 8c3.6 0 7 1.8 7 4v2H5v-2c0-2.2 3.4-4 7-4Zm0 2c-2.9 0-5 1.3-5 2v.1h10V18c0-.7-2.1-2-5-2Z"
                  fill="currentColor"
                />
              </svg>
            </button>
            <div v-if="accountMenuOpen" class="account-menu__panel">
              <p class="account-menu__name">{{ accountLabel }}</p>
              <NuxtLink
                class="account-menu__item"
                to="/account/orders"
                @click="accountMenuOpen = false"
              >
                {{ t('accountMenu.orders') }}
              </NuxtLink>
              <NuxtLink class="account-menu__item" to="/account" @click="accountMenuOpen = false">
                {{ t('accountMenu.reviews') }}
              </NuxtLink>
              <NuxtLink
                class="account-menu__item"
                to="/account/favourites"
                @click="accountMenuOpen = false"
              >
                {{ t('accountMenu.wishlist') }}
              </NuxtLink>
              <NuxtLink
                class="account-menu__item"
                to="/account/addresses"
                @click="accountMenuOpen = false"
              >
                {{ t('accountMenu.addresses') }}
              </NuxtLink>
              <button
                class="account-menu__item account-menu__item--action"
                type="button"
                @click="signOut"
              >
                {{ t('accountMenu.signOut') }}
              </button>
            </div>
          </div>
          <NuxtLink v-else class="icon-button" to="/account" :aria-label="t('header.signIn')">
            <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
              <path
                d="M12 4a4 4 0 1 1 0 8 4 4 0 0 1 0-8Zm0 2a2 2 0 1 0 0 4 2 2 0 0 0 0-4Zm0 8c3.6 0 7 1.8 7 4v2H5v-2c0-2.2 3.4-4 7-4Zm0 2c-2.9 0-5 1.3-5 2v.1h10V18c0-.7-2.1-2-5-2Z"
                fill="currentColor"
              />
            </svg>
          </NuxtLink>

          <NuxtLink
            class="icon-button icon-button--cart"
            to="/cart"
            :aria-label="`Cart, ${formattedCartCount} items`"
          >
            <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
              <path
                d="M7 18a2 2 0 1 0 0 4 2 2 0 0 0 0-4Zm10 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4ZM3 2h2.6l.6 2H21a1 1 0 0 1 .98 1.2l-1.5 7A1 1 0 0 1 19.5 13H8.1l-.3 1.2a.6.6 0 0 0 .58.8H19v2H8a2.6 2.6 0 0 1-2.53-3.2L6.2 10 4.4 4H3V2Zm4.2 4 1.1 5h10.4l1.1-5H7.2Z"
                fill="currentColor"
              />
            </svg>
            <span v-if="cartCount > 0" class="cart-count">{{ formattedCartCount }}</span>
          </NuxtLink>
        </nav>
      </div>

      <nav class="category-nav" :aria-label="t('header.allCategories')">
        <ul class="category-nav__list">
          <li v-for="item in items" :key="item.to">
            <NuxtLink class="category-nav__link" :to="item.to">{{ item.label }}</NuxtLink>
          </li>
        </ul>
      </nav>
    </div>
  </header>
</template>

<style scoped>
.site-header {
  position: sticky;
  top: 0;
  z-index: var(--z-header);
  background: var(--colour-surface);
  /* Header drop shadow only — no divider line between rows (real header). */
  box-shadow:
    rgb(0 0 0 / 4%) 0 2px 12px 0,
    rgb(0 0 0 / 6%) 0 1px 4px 0;
}

/* Black notice strip: 40px tall, #1A1A1A (sampled from the real header). */
.top-strip {
  min-height: 40px;
  color: var(--colour-white);
  background: #1a1a1a;
  font-size: 14px;
}

.top-strip__inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  min-height: 40px;
  max-width: var(--container-max);
  margin-inline: auto;
  padding-inline: var(--container-pad);
}

.top-strip__region {
  flex-shrink: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
  opacity: 0.92;
}

.top-strip__region:hover {
  opacity: 1;
  text-decoration: underline;
}

.top-strip__notice {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  min-width: 0;
}

.top-strip__text {
  overflow: hidden;
  min-width: 0;
  margin: 0;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.top-strip__arrow {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  font-size: 1rem;
  line-height: 1;
  cursor: pointer;
  opacity: 0.85;
}

.top-strip__arrow:hover {
  opacity: 1;
}

.top-strip__spacer {
  flex-shrink: 0;
  width: 5rem;
}

.site-header__inner {
  max-width: var(--container-max);
  margin-inline: auto;
  padding-inline: var(--container-pad);
}

/* Search row: 52px content height with 14px breathing room above/below. */
.site-header__top {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  min-height: 52px;
  padding-block: 14px;
}

.brand {
  display: inline-flex;
  align-items: center;
  height: 52px;
  text-decoration: none;
  flex-shrink: 0;
}

/* 110x30 wordmark, sampled from the real header logo. */
.brand__logo {
  width: 110px;
  height: 30px;
  object-fit: contain;
}

.categories-anchor {
  position: relative;
  display: inline-flex;
  flex-shrink: 0;
}

/* Pill trigger with icon + label, like the real header. */
.categories-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  height: 52px;
  padding: 8px 16px;
  border: 0;
  border-radius: 50px;
  cursor: pointer;
  background: var(--colour-surface-soft);
  color: var(--colour-text);
  font: inherit;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  white-space: nowrap;
}

.categories-button:hover {
  background: var(--colour-hover);
}

.search {
  position: relative;
  display: flex;
  flex: 1;
  align-items: center;
  min-width: 0;
  height: 52px;
  border: 1px solid var(--colour-search-border);
  border-radius: var(--radius-pill);
  background: var(--colour-surface-soft);
}

.search:focus-within {
  border-color: var(--colour-text);
}

.search__input {
  flex: 1;
  min-width: 0;
  height: 100%;
  padding: 0 76px 0 var(--space-5);
  border: 0;
  background: transparent;
  font: inherit;
  color: var(--colour-text);
}

.search__input:focus-visible {
  outline: none;
}

/* Dark pill search button nested inside the search bar (real header). */
.search__submit {
  position: absolute;
  right: 4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 44px;
  border: 0;
  border-radius: var(--radius-pill);
  cursor: pointer;
  color: var(--colour-white);
  background: #1a1a1a;
}

.search__submit:hover {
  opacity: 0.9;
}

.account-nav {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

/* Deliver-to entry (real site): 24px grey pin + 16px/600 label; hover is a
 * translucent navy pill (rgba(0,16,71,.06), radius 50px, no shadow). */
.account-nav__deliver {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  height: 52px;
  padding: 8px 16px;
  border: 0;
  border-radius: 50px;
  background: transparent;
  color: var(--colour-text);
  font: inherit;
  font-size: 16px;
  font-weight: var(--font-weight-semibold);
  white-space: nowrap;
  cursor: pointer;
}

.account-nav__deliver-icon {
  color: #55565b;
  flex-shrink: 0;
}

.account-nav__deliver-text {
  min-width: 110px;
  text-align: left;
}

.account-nav__deliver:hover {
  background: rgb(0 16 71 / 6%);
}

/* Round 52px icon buttons for account and cart (real header). */
.icon-button {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  border: 0;
  border-radius: 50%;
  cursor: pointer;
  background: var(--colour-surface-soft);
  color: var(--colour-text);
  text-decoration: none;
}

.icon-button:hover {
  background: var(--colour-hover);
}

.cart-count {
  position: absolute;
  top: -2px;
  right: -4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.25rem;
  height: 1.25rem;
  padding: 0 var(--space-1);
  border-radius: var(--radius-pill);
  color: var(--colour-white);
  background: var(--colour-accent);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-bold);
}

/* Avatar dropdown (docs/12 global): account entries, no membership item. */
.account-menu {
  position: relative;
}

.account-menu__panel {
  position: absolute;
  top: calc(100% + var(--space-1));
  right: 0;
  z-index: var(--z-overlay);
  width: 16rem;
  padding: var(--space-3);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-lg);
  background: var(--colour-surface);
  box-shadow: var(--shadow-overlay);
}

.account-menu__name {
  overflow: hidden;
  margin: 0 0 var(--space-2);
  padding-bottom: var(--space-2);
  border-bottom: 1px solid var(--colour-border);
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: var(--font-weight-bold);
}

.account-menu__item {
  display: flex;
  align-items: center;
  width: 100%;
  min-height: 2.75rem;
  padding: 0 var(--space-2);
  border: 0;
  border-radius: var(--radius-md);
  background: transparent;
  text-align: left;
  text-decoration: none;
  font: inherit;
  font-size: var(--font-size-sm);
  color: var(--colour-text);
  cursor: pointer;
}

.account-menu__item:hover {
  background: var(--colour-hover);
}

/* Category row: 11 links spread edge to edge; hover underlines (real header). */
.category-nav {
  min-height: 40px;
}

.category-nav__list {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  overflow-x: auto;
  scrollbar-width: none;
}

.category-nav__list::-webkit-scrollbar {
  display: none;
}

.category-nav__link {
  display: inline-flex;
  align-items: center;
  min-height: 40px;
  padding: 0 var(--space-2);
  white-space: nowrap;
  text-decoration: none;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--colour-text);
}

.category-nav__link:hover {
  color: var(--colour-text);
  text-decoration: underline;
}

/* 390/375 widths: search drops to its own row, nav scrolls horizontally. */
@media (max-width: 48rem) {
  .site-header__top {
    flex-wrap: wrap;
    row-gap: var(--space-2);
  }

  .search {
    order: 3;
    flex-basis: 100%;
  }

  .categories-button__label,
  .top-strip__notice,
  .top-strip__spacer,
  .account-nav__deliver {
    display: none;
  }
}
</style>
