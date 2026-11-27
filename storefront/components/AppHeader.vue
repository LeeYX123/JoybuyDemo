<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from '#imports'

import { useBuyerAuth } from '../composables/useBuyerAuth'
import { useCategoryTree } from '../composables/useCategoryTree'
import { useLocale } from '../composables/useLocale'
import { useMarketLocale } from '../composables/useMarketLocale'
import { useMerchantEntry } from '../composables/useMerchantEntry'
import { categoryHref } from '../utils/categoryLinks'

import AppCategoryPanel from './AppCategoryPanel.vue'

const props = defineProps({
  cartCount: {
    type: Number,
    default: 0,
  },
  // 需求 16.1 → 17.1 纠正：政策/内容页复用同一个 site-header，只隐藏一级
  // 品类行（真站 /help/* 页实测：分类按钮仍在、header-mini-home-row 品类行
  // 不存在）。黑条、logo、搜索、分类按钮、账号/申请店铺/购物车照常。
  // 由 layouts/footer-page.vue 传入，不复制第二份 header。
  hideCategoryNav: {
    type: Boolean,
    default: false,
  },
})

const route = useRoute()
const { t, categoryName } = useLocale()
const { localeCode, availableLocales, setMarketLocale } = useMarketLocale()
const { categories } = useCategoryTree()
const { isAuthenticated, account, logout } = useBuyerAuth()

// 搜商家：一个搜索框 + 两个按键（WP-42 文档「三、购物端 → 搜索框」拍板形态）。
const searchInput = ref(null)

function searchMerchants() {
  const query = searchInput.value?.value?.trim() || ''
  navigateTo(query ? `/merchants?q=${encodeURIComponent(query)}` : '/merchants')
}

// The product detail page has its own top nav (breadcrumb); the global
// category trigger and row both stay hidden there (real-site behaviour).
// 需求 17.1（纠正 16.1）：【分类】按钮（含下拉面板）与一级品类行拆成两个条件——
// 政策/内容页（footer-page 布局传 hideCategoryNav）只隐藏品类行，分类按钮保留
// （真站 /help/privacy-policy 存档实测：category_category__UT5Yj ×1、
// header-mini-home-row ×0）。
// 活动页 / 店铺页用「沉浸式」头部（2026-11-26，参照真站）：
// 活动页与店铺页的头部不一样（2026-11-26 用户纠正）：
// - /active/*：沉浸式——分类扁平、搜索框白底方角、语言与 Me/Cart 文字化、公告左对齐；
// - /store/*：沿用站点头部原样式，只去掉品类行 + 吸顶滚动效果。
const isActivityRoute = computed(() => route.path.startsWith('/active/'))
const isStoreRoute = computed(() => route.path.startsWith('/store/'))
const isImmersiveRoute = computed(() => isActivityRoute.value || isStoreRoute.value)
const headerScrolled = ref(false)

function onWindowScroll() {
  headerScrolled.value = typeof window !== 'undefined' ? window.scrollY > 40 : false
}

const showCategoriesButton = computed(() => !route.path.startsWith('/p/'))
const showCategoryNav = computed(
  () => !props.hideCategoryNav && !route.path.startsWith('/p/') && !isImmersiveRoute.value,
)

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
  onWindowScroll()
  window.addEventListener('scroll', onWindowScroll, { passive: true })
  document.addEventListener('pointerdown', handleDocumentPointerDown, true)
  document.addEventListener('keydown', handleDocumentKeydown)
  syncHeaderHeight()
  if (typeof ResizeObserver !== 'undefined' && headerRef.value) {
    headerResizeObserver = new ResizeObserver(syncHeaderHeight)
    headerResizeObserver.observe(headerRef.value)
  }
})

onBeforeUnmount(() => {
  if (noticeTimer) clearInterval(noticeTimer)
  window.removeEventListener('scroll', onWindowScroll)
  document.removeEventListener('pointerdown', handleDocumentPointerDown, true)
  document.removeEventListener('keydown', handleDocumentKeydown)
  headerResizeObserver?.disconnect()
  headerResizeObserver = null
})

// Category row: the standard categories from the API (requirement 1-1),
// spread edge to edge like the real header. Roots with a channel code land on
// the channel page (/minihome/<code>, joybuy minihome parity); the rest keep
// the /c/<slug> results page. `visible_in_nav` comes from the backend
// (catalog.search_views.NAV_HIDDEN_ROOT_SLUGS) — hidden roots stay reachable
// by direct URL, so this filter only affects the header row and panel.
const navCategories = computed(() =>
  categories.value.filter((category) => category.visible_in_nav !== false),
)
const items = computed(() =>
  navCategories.value.map((category) => ({
    label: categoryName(category),
    to: categoryHref(category),
  })),
)

const formattedCartCount = computed(() => (props.cartCount > 99 ? '99+' : String(props.cartCount)))

// 未登录【登录】入口（需求 11.5）：沿用登录页 AuthForm 的 ?next= 回跳约定；
// 登录/注册页自身不再带 next，避免登录后跳回登录页。
const loginHref = computed(() => {
  if (route.path.startsWith('/auth')) return '/auth/login'
  return { path: '/auth/login', query: { next: route.fullPath } }
})

const panelOpen = ref(false)
const accountMenuOpen = ref(false)
const accountMenuRef = ref(null)
const accountTrigger = ref(null)
const headerRef = ref(null)
let panelCloseTimer = null
let accountMenuCloseTimer = null
let headerResizeObserver = null

// 16.1：把站头实际高度写到 :root，供页面内吸顶元素（如 help 中心左侧 tab）
// 计算 sticky 顶部偏移，避免滚到吸顶 header 下面被遮住。高度随窄屏换行变化，
// 用 ResizeObserver 同步。
function syncHeaderHeight() {
  const height = headerRef.value?.offsetHeight
  if (height) {
    document.documentElement.style.setProperty('--site-header-height', `${height}px`)
  }
}

// Outside-click dismissal for the account dropdown. The listener is
// registered on the document in the capture phase so a click on any element
// that swallows bubbling (or a nested overlay) still closes the menu.
// Root cause of the reported bug: the menu was only toggled by its trigger,
// with no document listener and no Escape handler, so it stayed open forever.
function handleDocumentPointerDown(event) {
  if (!accountMenuOpen.value) return
  const root = accountMenuRef.value
  if (root && !root.contains(event.target)) accountMenuOpen.value = false
}

function handleDocumentKeydown(event) {
  if (event.key !== 'Escape' || !accountMenuOpen.value) return
  accountMenuOpen.value = false
  accountTrigger.value?.focus?.()
}

// 需求 13.5-5：头像菜单悬停即展开、移出 ~200ms 延迟关闭（真站实测 hover 16ms 即开）；
// 触屏无 hover，点击触发器保持原有开/合行为。
function openAccountMenu() {
  if (accountMenuCloseTimer) {
    clearTimeout(accountMenuCloseTimer)
    accountMenuCloseTimer = null
  }
  accountMenuOpen.value = true
}

function scheduleAccountMenuClose() {
  if (accountMenuCloseTimer) clearTimeout(accountMenuCloseTimer)
  accountMenuCloseTimer = setTimeout(() => {
    accountMenuOpen.value = false
    accountMenuCloseTimer = null
  }, 200)
}

function toggleAccountMenu() {
  accountMenuOpen.value = !accountMenuOpen.value
}

// ---------------------------------------------------------------------------
// Top-right shop entry (requirement 12.2, 2026-11-19): the "Deliver to" pin
// and its address drawer trigger are replaced by the shop-application entry.
// The status comes from the buyer session payload (no extra request, correct
// on the SSR first paint): not signed in or no APPROVED shop -> "Apply for a
// shop" link; APPROVED -> "Switch to Seller console" action that swaps the
// buyer session for the merchant staff session
// (POST /api/v1/account/merchant-console-session) and jumps to merchant-web.
// The AddressDrawer component itself is kept (file not deleted); only this
// header trigger is removed. Address management stays in the account hub.
// ---------------------------------------------------------------------------
const {
  isConsoleEntry: sellerApproved,
  switching: sellerSwitching,
  openMerchantConsole,
} = useMerchantEntry()

// 未登录：点击先去登录，登录成功回申请页（沿用 AuthForm 的 ?next= 约定）。
const applyShopHref = computed(() => ({
  path: '/auth/login',
  query: { next: '/account/apply-shop' },
}))

async function openSellerConsole() {
  await openMerchantConsole()
}

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
  // 退出后回到登录页（用户要求：不要留在原页面）
  await navigateTo('/auth/login')
}

// 需求 13.5-6：展示名优先用后端生成/用户设置的 display_name（user+数字+字母），
// 未登录或老 payload 缺字段时退回邮箱/手机号。
const accountLabel = computed(
  () => account.value?.display_name || account.value?.email || account.value?.phone || '',
)

// 头像下拉行（真站：左文字 + 右侧线性 icon；会员中心一项已按需求 1-6 移除）。
const accountMenuRows = [
  { key: 'orders', to: '/account/orders', icon: 'orders' },
  { key: 'reviews', to: '/account', icon: 'reviews' },
  { key: 'wishlist', to: '/account/favourites', icon: 'wishlist' },
  { key: 'addresses', to: '/account/addresses', icon: 'addresses' },
  { key: 'signOut', action: true, icon: 'signOut' },
]

// 行尾线性 icon 的 path 集合（文本字形对齐真站 20px 线性风格）。
const menuIcons = {
  orders: 'M8 6h13M8 12h13M8 18h13M4 6h.01M4 12h.01M4 18h.01',
  reviews: 'M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l2.4-3.1A8.5 8.5 0 1 1 21 11.5Z',
  wishlist:
    'M12 20.3C8.4 17.7 3 13.9 3 9.5A4.5 4.5 0 0 1 12 7a4.5 4.5 0 0 1 9 2.5c0 4.4-5.4 8.2-9 10.8Z',
  addresses:
    'M12 21s-6.5-5.6-6.5-10.4a6.5 6.5 0 1 1 13 0C18.5 15.4 12 21 12 21Zm0-8.2a2.2 2.2 0 1 0 0-4.4 2.2 2.2 0 0 0 0 4.4Z',
  signOut: 'M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 8l-4 4 4 4M6 12h9',
}

// Logo asset lives in the Nuxt public dir (storefront/public/images).
const brandLogoUrl = '/images/logo.png'
</script>

<template>
  <header
    ref="headerRef"
    class="site-header"
    :class="{
      'site-header--activity': isActivityRoute,
      'site-header--store': isStoreRoute,
      'site-header--scrolled': headerScrolled,
    }"
  >
    <!-- Black notice strip: rotating service promises + locale switch. -->
    <div class="top-strip">
      <div class="top-strip__inner">
        <!-- 需求 11.4：顶栏只留语言下拉（国家选择仍在地址抽屉里）。 -->
        <div v-if="!isActivityRoute" class="top-strip__region" :aria-label="t('header.language')">
          <label class="visually-hidden" for="locale-select">{{ t('header.language') }}</label>
          <select
            id="locale-select"
            :value="localeCode"
            aria-label="Language"
            @change="setMarketLocale($event.target.value)"
          >
            <option v-for="option in availableLocales" :key="option.code" :value="option.code">
              {{ option.name }}
            </option>
          </select>
        </div>
        <div class="top-strip__notice">
          <button
            class="top-strip__arrow"
            type="button"
            :aria-label="t('header.prevNotice')"
            @click="showNotice(noticeIndex - 1)"
          >
            ‹
          </button>
          <p class="top-strip__text">{{ notices[noticeIndex] }}</p>
          <button
            class="top-strip__arrow"
            type="button"
            :aria-label="t('header.nextNotice')"
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
        <NuxtLink class="brand" to="/" :aria-label="t('header.joybuyHome')">
          <!-- Real Joybuy wordmark asset, hosted locally (no CDN). Bound at
               runtime so the bundler does not turn it into a module import. -->
          <img class="brand__logo" :src="brandLogoUrl" alt="" width="110" height="30" />
        </NuxtLink>

        <!-- 需求 17.1：政策/内容页保留【分类】按钮与下拉面板，只隐藏下方品类行。 -->
        <div
          v-if="showCategoriesButton"
          class="categories-anchor"
          @mouseenter="openPanel"
          @mouseleave="schedulePanelClose"
        >
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
            :categories="navCategories"
            @close="panelOpen = false"
            @mouseenter="openPanel"
            @mouseleave="schedulePanelClose"
          />
        </div>

        <form class="search" role="search" action="/search" method="get">
          <label class="visually-hidden" for="site-search">{{ t('header.searchLabel') }}</label>
          <input
            id="site-search"
            ref="searchInput"
            class="search__input"
            type="search"
            name="q"
            :placeholder="t('header.searchPlaceholder')"
            autocomplete="off"
          />
          <button class="search__submit" type="submit" :aria-label="t('header.search')">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path
                d="M10.5 3a7.5 7.5 0 1 1 0 15 7.5 7.5 0 0 1 0-15Zm0 2a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11Zm4.8 9.3 5.7 5.7-1.4 1.4-5.7-5.7 1.4-1.4Z"
                fill="currentColor"
              />
            </svg>
          </button>
          <button
            v-if="!isActivityRoute"
            class="search__merchant"
            type="button"
            @click="searchMerchants"
          >
            {{ t('header.searchMerchants') }}
          </button>
        </form>

        <nav class="account-nav" :aria-label="t('header.accountAndCart')">
          <!-- 需求 12.2：右上角【配送至】替换为【申请店铺】入口，状态随买家
               session 一次带回（SSR 首屏即正确）；未登录先去登录并回申请页。 -->
          <NuxtLink
            v-if="!isAuthenticated"
            class="account-nav__apply"
            :to="applyShopHref"
            :aria-label="t('header.applyShop.apply')"
          >
            {{ t('header.applyShop.apply') }}
          </NuxtLink>
          <button
            v-else-if="sellerApproved"
            class="account-nav__apply"
            type="button"
            :disabled="sellerSwitching"
            :aria-label="t('header.applyShop.switch')"
            @click="openSellerConsole"
          >
            {{ sellerSwitching ? t('merchantEntry.opening') : t('header.applyShop.switch') }}
          </button>
          <NuxtLink
            v-else
            class="account-nav__apply"
            to="/account/apply-shop"
            :aria-label="t('header.applyShop.apply')"
          >
            {{ t('header.applyShop.apply') }}
          </NuxtLink>

          <!-- 沉浸式（活动页/店铺页）：语言切换从黑条移到这里，位于【申请店铺】右侧。 -->
          <label v-if="isActivityRoute" class="header-locale" :aria-label="t('header.language')">
            <span class="visually-hidden">{{ t('header.language') }}</span>
            <select :value="localeCode" @change="setMarketLocale($event.target.value)">
              <option v-for="option in availableLocales" :key="option.code" :value="option.code">
                {{ option.code.slice(0, 2).toUpperCase() }}
              </option>
            </select>
          </label>

          <!-- 需求 17.3（2026-11-20）：右上角顺序按真站调整为 申请店铺 → 购物车 →
               头像/登录。真站四份 SSR 存档（real_home_{en,zh}/real_cart_nl，2026-11-19）
               jdi-header-user-info 内均为 cartEntry(购物车)在前、userInfoButton(头像)
               在后，且 header_userInfo 无 row-reverse/order、截图视觉一致；本条按
               任务口径「若真站是 购物车→头像 则按真站」执行，用 DOM 顺序（非 CSS order），
               SSR 首屏即正确。 -->
          <NuxtLink
            class="icon-button icon-button--cart"
            to="/cart"
            :aria-label="t('cart.itemsAria', { count: formattedCartCount })"
          >
            <!-- 角标要贴在**图标**右上角（活动页图标 + 文字并排时不能跑到文字上），
                 所以图标与角标包在同一个相对定位容器里。 -->
            <span class="cart-icon">
              <svg
                v-if="isActivityRoute"
                viewBox="0 0 24 24"
                width="24"
                height="24"
                fill="none"
                aria-hidden="true"
              >
                <path
                  d="M2.6 3.6h2.2l2.1 11.1h10.8l2.1-8H6.2"
                  stroke="currentColor"
                  stroke-width="1.6"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
                <circle cx="9.4" cy="19" r="1.5" stroke="currentColor" stroke-width="1.6" />
                <circle cx="17.2" cy="19" r="1.5" stroke="currentColor" stroke-width="1.6" />
              </svg>
              <svg v-else viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
                <path
                  d="M7 18a2 2 0 1 0 0 4 2 2 0 0 0 0-4Zm10 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4ZM3 2h2.6l.6 2H21a1 1 0 0 1 .98 1.2l-1.5 7A1 1 0 0 1 19.5 13H8.1l-.3 1.2a.6.6 0 0 0 .58.8H19v2H8a2.6 2.6 0 0 1-2.53-3.2L6.2 10 4.4 4H3V2Zm4.2 4 1.1 5h10.4l1.1-5H7.2Z"
                  fill="currentColor"
                />
              </svg>
              <span v-if="cartCount > 0" class="cart-count">{{ formattedCartCount }}</span>
            </span>
            <span v-if="isActivityRoute" class="icon-button__label">{{ t('header.cart') }}</span>
          </NuxtLink>

          <div
            v-if="isAuthenticated"
            ref="accountMenuRef"
            class="account-menu"
            @mouseenter="openAccountMenu"
            @mouseleave="scheduleAccountMenuClose"
          >
            <button
              ref="accountTrigger"
              class="icon-button"
              type="button"
              aria-haspopup="true"
              :aria-label="t('header.myAccount')"
              :aria-expanded="accountMenuOpen"
              @click="toggleAccountMenu"
            >
              <!-- 沉浸式（活动页/店铺页）：真站是线性人形图标 + Me + 下箭头。 -->
              <template v-if="isActivityRoute">
                <svg viewBox="0 0 24 24" width="24" height="24" fill="none" aria-hidden="true">
                  <circle cx="12" cy="7.8" r="3.7" stroke="currentColor" stroke-width="1.6" />
                  <path
                    d="M4.8 20c0-3.6 3.2-6 7.2-6s7.2 2.4 7.2 6"
                    stroke="currentColor"
                    stroke-width="1.6"
                    stroke-linecap="round"
                  />
                </svg>
                <span class="icon-button__label">{{ t('header.me') }}</span>
                <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
                  <path
                    d="m6 9 6 6 6-6"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.8"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
              </template>
              <!-- 真站笑脸头像（未设置头像时的占位），SSR 抓取原文内联复刻。 -->
              <svg v-else viewBox="0 0 56 56" width="30" height="30" aria-hidden="true">
                <rect width="56" height="56" fill="#E5E7F0" rx="28" />
                <path
                  fill="#fff"
                  fill-rule="evenodd"
                  clip-rule="evenodd"
                  d="M29.782 17.512a2.989 2.989 0 1 1-5.978 0 2.989 2.989 0 0 1 5.978 0m-9.284 9.415a2.988 2.988 0 1 1-5.977-.001 2.988 2.988 0 0 1 5.977 0m-3.02 9.574v6.082c13.81 0 25.042-11.235 25.042-25.044h-6.08c0 10.456-8.507 18.962-18.962 18.962"
                />
              </svg>
            </button>
            <div v-if="accountMenuOpen" class="account-menu__panel">
              <!-- 需求 22.3-1：头像 + 用户名整块是链接 → /account（用户中心），
                   点击后关闭下拉；下面 5 行菜单项与行为保持不变。 -->
              <NuxtLink
                class="account-menu__user"
                to="/account"
                data-testid="account-menu-profile"
                @click="accountMenuOpen = false"
              >
                <span class="account-menu__avatar" aria-hidden="true">
                  <!-- 需求 17.2：面板内头像 40×40（真站 meAvatar 40px 圆）。 -->
                  <svg viewBox="0 0 56 56" width="40" height="40">
                    <rect width="56" height="56" fill="#E5E7F0" rx="28" />
                    <path
                      fill="#fff"
                      fill-rule="evenodd"
                      clip-rule="evenodd"
                      d="M29.782 17.512a2.989 2.989 0 1 1-5.978 0 2.989 2.989 0 0 1 5.978 0m-9.284 9.415a2.988 2.988 0 1 1-5.977-.001 2.988 2.988 0 0 1 5.977 0m-3.02 9.574v6.082c13.81 0 25.042-11.235 25.042-25.044h-6.08c0 10.456-8.507 18.962-18.962 18.962"
                    />
                  </svg>
                </span>
                <span class="account-menu__name">{{ accountLabel }}</span>
              </NuxtLink>
              <!-- 需求 12.2：头像下拉菜单不再有「申请开店」入口（右上角统一承载）。
                   需求 13.5-6：每行左右对齐、右侧线性 icon（对齐真站行布局）。 -->
              <template v-for="row in accountMenuRows" :key="row.key">
                <NuxtLink
                  v-if="!row.action"
                  class="account-menu__item"
                  :to="row.to"
                  @click="accountMenuOpen = false"
                >
                  <span class="account-menu__label">{{ t(`accountMenu.${row.key}`) }}</span>
                  <svg
                    class="account-menu__icon"
                    viewBox="0 0 24 24"
                    width="20"
                    height="20"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.6"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    aria-hidden="true"
                  >
                    <path :d="menuIcons[row.icon]" />
                  </svg>
                </NuxtLink>
                <!-- 需求 17.2-5：退出登录灰化（真站 signOut = --sys-Text-Tertiary）。 -->
                <button
                  v-else
                  class="account-menu__item account-menu__item--sign-out"
                  type="button"
                  @click="signOut"
                >
                  <span class="account-menu__label">{{ t('accountMenu.signOut') }}</span>
                  <svg
                    class="account-menu__icon"
                    viewBox="0 0 24 24"
                    width="20"
                    height="20"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.6"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    aria-hidden="true"
                  >
                    <path :d="menuIcons[row.icon]" />
                  </svg>
                </button>
              </template>
            </div>
          </div>
          <!-- 需求 11.5：未登录时右上角为文本按钮【登录】（无图标圆框），
               登录成功经 AuthForm 的 ?next= 约定回跳来源页。 -->
          <NuxtLink
            v-else
            class="login-button"
            :class="{ 'login-button--immersive': isActivityRoute }"
            :to="loginHref"
            :aria-label="t('header.signIn')"
          >
            <template v-if="isActivityRoute">
              <svg viewBox="0 0 24 24" width="24" height="24" fill="none" aria-hidden="true">
                <circle cx="12" cy="7.8" r="3.7" stroke="currentColor" stroke-width="1.6" />
                <path
                  d="M4.8 20c0-3.6 3.2-6 7.2-6s7.2 2.4 7.2 6"
                  stroke="currentColor"
                  stroke-width="1.6"
                  stroke-linecap="round"
                />
              </svg>
              <span class="icon-button__label">{{ t('header.me') }}</span>
              <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
                <path
                  d="m6 9 6 6 6-6"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.8"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            </template>
            <template v-else>{{ t('header.signIn') }}</template>
          </NuxtLink>
        </nav>
      </div>

      <nav v-if="showCategoryNav" class="category-nav" :aria-label="t('header.allCategories')">
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
  /* Header drop shadow only — no divider line between rows (real header).
     需求 17.1-2：按真站 CSS 原文加深（css/fc6d34e1e663c66e.css，
     .header_header__KTVf_…：0 2px 12px 0 rgba(0,0,0,.039), 0 4px 6px 0
     rgba(0,0,0,.059)）——旧值第二层 1px/4px 偏淡即"阴影太淡"根因。 */
  box-shadow:
    rgb(0 0 0 / 3.9%) 0 2px 12px 0,
    rgb(0 0 0 / 5.9%) 0 4px 6px 0;
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
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
  opacity: 0.92;
}

.top-strip__region select {
  max-width: 140px;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.top-strip__region option {
  background: #1a1a1a;
  color: #fff;
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
  overflow: visible;
  min-width: 0;
  margin: 0;
  text-align: center;

  white-space: normal;
  word-break: break-word;
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

/* ---- 活动页 / 店铺页的沉浸式头部（2026-11-26，参照真站） ---- */

/* 活动页：头部不吸顶，滚动时随页面走。 */
.site-header--activity {
  position: static;
}

/* 内容铺满视口（真站活动页 logo 几乎贴左缘，搜索框一路拉到右侧）。 */
.site-header--activity .site-header__inner {
  max-width: none;
  padding-inline: 24px;
}

/* 黑条公告左对齐（真站活动页是左对齐纯文本 + 右侧入口），隐藏左右箭头。 */
.site-header--activity .top-strip__inner {
  max-width: none;
  justify-content: flex-start;
  padding-inline: 24px;
}

.site-header--activity .top-strip__notice {
  flex: 1;
  justify-content: flex-start;
  margin-inline: 0;
}

.site-header--activity .top-strip__arrow,
.site-header--activity .top-strip__spacer {
  display: none;
}

/* 搜索框拉满剩余宽度。 */
.site-header--activity .search {
  flex: 1;
  max-width: none;
}

/* 店铺页：吸顶 + 下滑隐藏黑条、header 半透明。 */
.site-header--store {
  position: sticky;
  top: 0;
  transition:
    background 220ms ease,
    box-shadow 220ms ease;
}

.site-header--store .top-strip {
  overflow: hidden;
  transition:
    height 220ms ease,
    min-height 220ms ease,
    opacity 180ms ease;
}

.site-header--store.site-header--scrolled .top-strip,
.site-header--store.site-header--scrolled .top-strip__inner {
  min-height: 0;
  height: 0;
  opacity: 0;
  overflow: hidden;
}

.site-header--store.site-header--scrolled {
  background: rgb(255 255 255 / 84%);
  backdrop-filter: blur(10px);
  box-shadow: 0 1px 8px rgb(0 0 0 / 8%);
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

/* Pill trigger with icon + label, like the real header.
   需求 13.5-3 实测值（真站 CSS）：16px / 600 / icon 24px / icon-文字 6px。 */
.categories-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 52px;
  padding: 8px 16px;
  border: 0;
  border-radius: 50px;
  cursor: pointer;
  background: var(--colour-surface-soft);
  color: var(--colour-text);
  font: inherit;
  font-size: 16px;
  font-weight: var(--font-weight-semibold);
  white-space: nowrap;
}

.categories-button svg {
  width: 24px;
  height: 24px;
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
  padding: 0 170px 0 var(--space-5);
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

/* 搜商家按键（WP-42）：与搜商品按键并列，文字形态。 */
.search__merchant {
  position: absolute;
  right: 72px;
  display: inline-flex;
  align-items: center;
  height: 44px;
  padding: 0 14px;
  border: 0;
  border-radius: var(--radius-pill);
  cursor: pointer;
  font-size: 13px;
  color: var(--colour-white);
  background: #e1251b;
  white-space: nowrap;
}

.search__merchant:hover {
  opacity: 0.9;
}

.account-nav {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

/* Top-right shop entry (requirement 12.2): text pill on the icon row; hover is
 * the same translucent navy pill the deliver-to entry used before the swap. */
.account-nav__apply {
  display: inline-flex;
  align-items: center;
  height: 52px;
  padding: 0 var(--space-4);
  border: 0;
  border-radius: 50px;
  background: transparent;
  color: var(--colour-text);
  font: inherit;
  font-size: 16px;
  font-weight: var(--font-weight-semibold);
  white-space: nowrap;
  text-decoration: none;
  cursor: pointer;
}

.account-nav__apply:hover {
  background: rgb(0 16 71 / 6%);
}

.account-nav__apply:disabled {
  cursor: progress;
  opacity: 0.75;
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

/* 未登录【登录】文本按钮（需求 11.5）：与导航图标同高、无图标圆框。 */
.login-button {
  display: inline-flex;
  align-items: center;
  height: 52px;
  padding: 0 var(--space-4);
  border-radius: 50px;
  color: var(--colour-text);
  text-decoration: none;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-semibold);
  white-space: nowrap;
}

.login-button:hover {
  background: var(--colour-hover);
}

.cart-icon {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.cart-count {
  position: absolute;
  top: -8px;
  right: -7px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.125rem;
  height: 1.125rem;
  padding: 0 4px;
  border-radius: var(--radius-pill);
  color: var(--colour-white);
  background: var(--colour-accent);
  font-size: 10px;
  font-weight: var(--font-weight-bold);
  line-height: 1;
}

/* Avatar dropdown (docs/12 global): account entries, no membership item.
   需求 13.5-5/6：hover 展开（脚本控制）；需求 17.2 一比一复刻真站
   userInfoButton_meListDropdownLayer（CSS 原文实测）：面板 280px / radius 16px /
   padding 12px / 无边框、阴影 0 4px 28px .039 + 0 8px 24px .059；行高 56px、
   16px / #1a1a1a、行内 flex + space-between + padding 0 16px（icon 右对齐）、
   hover #f0f1f4 + radius 4px；退出登录 = --sys-Text-Tertiary 灰；用户行 =
   40px 笑脸头像 + 16px/700/22px 昵称、无分隔线（用户口径：整行水平居中，
   真站实为左对齐 + gap 12px，17.2-3 明确要求居中，验收按用户口径）。 */
.account-menu {
  position: relative;
}

.account-menu__panel {
  position: absolute;
  top: calc(100% + var(--space-1));
  right: 0;
  z-index: var(--z-overlay);
  width: 280px;
  padding: 12px;
  border-radius: 16px;
  background: var(--colour-surface);
  box-shadow:
    rgb(0 0 0 / 3.9%) 0 4px 28px 0,
    rgb(0 0 0 / 5.9%) 0 8px 24px 0;
}

.account-menu__user {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  width: 100%;
  height: 56px;
  border-radius: 4px;
  color: inherit;
  text-decoration: none;
}

/* 需求 22.3-1：整块可点，hover 与菜单行同款浅灰反馈。 */
.account-menu__user:hover {
  background: var(--colour-hover);
}

.account-menu__avatar {
  display: inline-flex;
  flex-shrink: 0;
}

.account-menu__avatar svg {
  display: block;
  border-radius: 50%;
}

.account-menu__name {
  overflow: visible;
  max-width: 188px;

  white-space: normal;
  font-size: 16px;
  font-weight: var(--font-weight-bold);
  line-height: 22px;
  word-break: break-word;
}

.account-menu__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  width: 100%;
  height: 56px;
  padding: 0 16px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  text-align: left;
  text-decoration: none;
  font: inherit;
  font-size: 16px;
  color: #1a1a1a;
  cursor: pointer;
}

.account-menu__icon {
  flex-shrink: 0;
  color: inherit;
}

.account-menu__item:hover {
  background: var(--colour-hover);
}

/* 需求 17.2-5：退出登录灰化，与其它菜单项区分（真站 --sys-Text-Tertiary）。 */
.account-menu__item--sign-out,
.account-menu__item--sign-out:hover {
  color: #6e7078;
}

/* Category row: 11 links spread edge to edge; hover underlines (real header).
   需求 13.5-2 实测：真站品类行紧贴搜索行（gap=0），文本 14px/400/16px，
   行 padding-bottom 14px——去掉旧的 40px min-height 带来的多余间隙。 */
.category-nav {
  padding-bottom: 14px;
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
  padding: 0 var(--space-2);
  white-space: nowrap;
  text-decoration: none;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-regular);
  line-height: 16px;
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
  .account-nav__apply {
    display: none;
  }
}

/* ---- 活动页/店铺页头部：按真站样式（2026-11-26） ---- */

/* 分类：去掉灰底胶囊，纯图标 + 文字。 */
.site-header--activity .categories-button {
  padding: 0 10px;
  border-radius: 8px;
  background: transparent;
  gap: 8px;
}

.site-header--activity .categories-button:hover {
  background: var(--colour-hover);
}

/* 搜索框：白底 + 1px 浅灰边 + 8px 圆角（真站活动页），内嵌黑色方形按钮。 */
.site-header--activity .search {
  height: 44px;
  border-color: #e5e5e5;
  border-radius: 8px;
  background: #fff;
}

.site-header--activity .search__input {
  padding: 0 52px 0 16px;
  font-size: 15px;
}

.site-header--activity .search__submit {
  right: 4px;
  width: 36px;
  height: 36px;
  border-radius: 8px;
}

/* 语言切换（从黑条搬到【申请店铺】右侧）。 */
.header-locale {
  display: inline-flex;
  align-items: center;
  height: 52px;
  padding: 0 4px;
}

.header-locale select {
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  font-size: 16px;
  cursor: pointer;
}

/* 购物车 / 我的：图标 + 文字，无灰底圆。 */
.site-header--activity .icon-button {
  width: auto;
  padding: 0 8px;
  border-radius: 8px;
  background: transparent;
  gap: 6px;
}

.site-header--activity .icon-button:hover {
  background: var(--colour-hover);
}

.icon-button__label {
  font-size: 16px;
  line-height: 1;
  white-space: nowrap;
}

/* 活动页右侧按钮之间留更大间距（真站约 20px）。 */
.site-header--activity .account-nav {
  gap: 20px;
}

/* 真站顺序：申请店铺 → 语言 → 我的 → 购物车（Me 在 Cart 左侧）。 */
.site-header--activity .account-nav__apply {
  order: 0;
}

.site-header--activity .header-locale {
  order: 1;
}

.site-header--activity .account-menu,
.site-header--activity .login-button--immersive {
  order: 2;
}

.site-header--activity .icon-button--cart {
  order: 3;
}

/* 图标 + 文字并排时，给文字多留一点空隙，让角标只压在图标角上。 */
.site-header--activity .icon-button--cart .icon-button__label {
  margin-left: 8px;
}

/* 沉浸式的「登录」按钮与「我的」同款（图标 + 文字 + 箭头）。 */
.login-button--immersive {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 52px;
  padding: 0 8px;
  border-radius: 8px;
  color: var(--colour-text);
  font-size: 16px;
  text-decoration: none;
}

.login-button--immersive:hover {
  background: var(--colour-hover);
}
</style>
