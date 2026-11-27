<script setup>
import { computed } from 'vue'

import { useBuyerAuth } from '../../composables/useBuyerAuth'
import { useLocale } from '../../composables/useLocale'
import { useMerchantEntry } from '../../composables/useMerchantEntry'

// Mobile drawer (docs/19 §3): 320px white left panel, dimmed page behind.
// Structure replicates the user-supplied real-site screenshot
// (var/mjoybuy_survey_20261124/drawer_real.png): user area, bold "Categories"
// / "Joybuy Home" rows, then 57px item rows with icons and chevrons.
// Content wiring reuses existing web surfaces (orders/wishlist/addresses/
// help policy pages); 优惠券 is dropped (no web counterpart). 语言 and
// 设置&隐私 open dedicated pages (/account/language, /account/settings).
defineProps({
  open: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['close'])

const { t } = useLocale()
const { isAuthenticated, account, logout } = useBuyerAuth()
const {
  isConsoleEntry: sellerApproved,
  switching: sellerSwitching,
  openMerchantConsole,
} = useMerchantEntry()

const accountName = computed(() => account.value?.display_name || account.value?.email || '')
const applyShopHref = computed(() => ({
  path: '/auth/login',
  query: { next: '/account/apply-shop' },
}))

async function onSignOut() {
  try {
    await logout()
  } finally {
    emit('close')
  }
}

function closeOnEscape(event) {
  if (event.key === 'Escape') emit('close')
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="m-drawer"
      role="dialog"
      aria-modal="true"
      :aria-label="t('header.categories')"
      @keydown="closeOnEscape"
    >
      <div class="m-drawer__backdrop" @click="emit('close')"></div>
      <div class="m-drawer__panel">
        <button
          class="m-drawer__close"
          type="button"
          :aria-label="t('support.close')"
          @click="emit('close')"
        >
          <svg
            viewBox="0 0 24 24"
            width="20"
            height="20"
            aria-hidden="true"
            fill="none"
            stroke="currentColor"
            stroke-width="1.6"
          >
            <path d="M6 6l12 12M18 6 6 18" stroke-linecap="round" />
          </svg>
        </button>

        <!-- User area -->
        <div v-if="isAuthenticated" class="m-drawer__user">
          <span class="m-drawer__avatar" aria-hidden="true">
            <svg
              viewBox="0 0 24 24"
              width="26"
              height="26"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
            >
              <circle cx="12" cy="12" r="9" />
              <circle cx="9" cy="10.5" r="1" fill="currentColor" stroke="none" />
              <circle cx="15" cy="10.5" r="1" fill="currentColor" stroke="none" />
              <path d="M8.5 14.5c1 1.2 2.2 1.8 3.5 1.8s2.5-.6 3.5-1.8" stroke-linecap="round" />
            </svg>
          </span>
          <span class="m-drawer__username">{{ accountName }}</span>
          <button class="m-drawer__signout" type="button" @click="onSignOut">
            {{ t('mobile.drawer.settings.signOut') }}
          </button>
        </div>
        <div v-else class="m-drawer__user">
          <span class="m-drawer__avatar" aria-hidden="true">
            <svg
              viewBox="0 0 24 24"
              width="26"
              height="26"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
            >
              <circle cx="12" cy="12" r="9" />
              <circle cx="9" cy="10.5" r="1" fill="currentColor" stroke="none" />
              <circle cx="15" cy="10.5" r="1" fill="currentColor" stroke="none" />
              <path d="M8.5 14.5c1 1.2 2.2 1.8 3.5 1.8s2.5-.6 3.5-1.8" stroke-linecap="round" />
            </svg>
          </span>
          <NuxtLink class="m-drawer__signin" to="/auth/login">{{
            t('mobile.drawer.signIn')
          }}</NuxtLink>
        </div>

        <!-- Root view -->
        <!-- 分类：真站不是抽屉内展开，而是跳转独立品类落地页
             /categories（用户 2026-11-24 展开态截图实测）。 -->
        <div class="m-drawer__body">
          <NuxtLink
            class="m-drawer__row m-drawer__row--strong"
            to="/categories"
            @click="emit('close')"
          >
            {{ t('mobile.drawer.categories') }}
            <svg
              class="m-drawer__chevron"
              viewBox="0 0 24 24"
              width="18"
              height="18"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
            >
              <path d="m9 5 7 7-7 7" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </NuxtLink>

          <NuxtLink class="m-drawer__row m-drawer__row--strong" to="/" @click="emit('close')">
            {{ t('mobile.drawer.home') }}
            <svg
              class="m-drawer__chevron"
              viewBox="0 0 24 24"
              width="18"
              height="18"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
            >
              <path d="m9 5 7 7-7 7" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </NuxtLink>

          <div class="m-drawer__gap"></div>

          <NuxtLink class="m-drawer__row" to="/account/orders" @click="emit('close')">
            <svg
              class="m-drawer__icon"
              viewBox="0 0 24 24"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
            >
              <rect x="5" y="3" width="14" height="18" rx="2" />
              <path d="M9 8h6M9 12h6M9 16h4" stroke-linecap="round" />
            </svg>
            {{ t('mobile.drawer.orders') }}
            <svg
              class="m-drawer__chevron"
              viewBox="0 0 24 24"
              width="18"
              height="18"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
            >
              <path d="m9 5 7 7-7 7" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </NuxtLink>
          <!-- 消息（docs/20 §5.7）：改指向 /account/messages 消息页
               （客服/订单两 tab），不再直达客服页。 -->
          <NuxtLink class="m-drawer__row" to="/account/messages" @click="emit('close')">
            <svg
              class="m-drawer__icon"
              viewBox="0 0 24 24"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
            >
              <path
                d="M18 8a6 6 0 1 0-12 0c0 7-3 8-3 8h18s-3-1-3-8"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <path d="M10.3 21a2 2 0 0 0 3.4 0" stroke-linecap="round" />
            </svg>
            {{ t('mobile.drawer.messages') }}
            <svg
              class="m-drawer__chevron"
              viewBox="0 0 24 24"
              width="18"
              height="18"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
            >
              <path d="m9 5 7 7-7 7" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </NuxtLink>
          <NuxtLink class="m-drawer__row" to="/account/favourites" @click="emit('close')">
            <svg
              class="m-drawer__icon"
              viewBox="0 0 24 24"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
            >
              <path
                d="M12 20s-7-4.6-9.3-9A5.3 5.3 0 0 1 12 6.7 5.3 5.3 0 0 1 21.3 11C19 15.4 12 20 12 20Z"
                stroke-linejoin="round"
              />
            </svg>
            {{ t('mobile.drawer.wishlist') }}
            <svg
              class="m-drawer__chevron"
              viewBox="0 0 24 24"
              width="18"
              height="18"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
            >
              <path d="m9 5 7 7-7 7" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </NuxtLink>
          <NuxtLink class="m-drawer__row" to="/account/addresses" @click="emit('close')">
            <svg
              class="m-drawer__icon"
              viewBox="0 0 24 24"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
            >
              <path d="M12 21s7-5.5 7-11a7 7 0 1 0-14 0c0 5.5 7 11 7 11Z" stroke-linejoin="round" />
              <circle cx="12" cy="10" r="2.6" />
            </svg>
            {{ t('mobile.drawer.addresses') }}
            <svg
              class="m-drawer__chevron"
              viewBox="0 0 24 24"
              width="18"
              height="18"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
            >
              <path d="m9 5 7 7-7 7" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </NuxtLink>

          <!-- 申请店铺 (decided 2026-11-24): three states like the header pill. -->
          <NuxtLink
            v-if="!isAuthenticated"
            class="m-drawer__row"
            :to="applyShopHref"
            @click="emit('close')"
          >
            <svg
              class="m-drawer__icon"
              viewBox="0 0 24 24"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
            >
              <path
                d="M4 9.5 5.5 4h13L20 9.5M4 9.5V20h16V9.5M4 9.5h16M9.5 20v-6h5v6"
                stroke-linejoin="round"
              />
            </svg>
            {{ t('mobile.drawer.applyShop') }}
            <svg
              class="m-drawer__chevron"
              viewBox="0 0 24 24"
              width="18"
              height="18"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
            >
              <path d="m9 5 7 7-7 7" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </NuxtLink>
          <button
            v-else-if="sellerApproved"
            class="m-drawer__row"
            type="button"
            :disabled="sellerSwitching"
            @click="openMerchantConsole"
          >
            <svg
              class="m-drawer__icon"
              viewBox="0 0 24 24"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
            >
              <path
                d="M4 9.5 5.5 4h13L20 9.5M4 9.5V20h16V9.5M4 9.5h16M9.5 20v-6h5v6"
                stroke-linejoin="round"
              />
            </svg>
            {{ sellerSwitching ? t('merchantEntry.opening') : t('mobile.drawer.switchSeller') }}
            <svg
              class="m-drawer__chevron"
              viewBox="0 0 24 24"
              width="18"
              height="18"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
            >
              <path d="m9 5 7 7-7 7" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </button>
          <NuxtLink v-else class="m-drawer__row" to="/account/apply-shop" @click="emit('close')">
            <svg
              class="m-drawer__icon"
              viewBox="0 0 24 24"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
            >
              <path
                d="M4 9.5 5.5 4h13L20 9.5M4 9.5V20h16V9.5M4 9.5h16M9.5 20v-6h5v6"
                stroke-linejoin="round"
              />
            </svg>
            {{ t('mobile.drawer.applyShop') }}
            <svg
              class="m-drawer__chevron"
              viewBox="0 0 24 24"
              width="18"
              height="18"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
            >
              <path d="m9 5 7 7-7 7" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </NuxtLink>

          <NuxtLink class="m-drawer__row" to="/account/language" @click="emit('close')">
            <svg
              class="m-drawer__icon"
              viewBox="0 0 24 24"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
            >
              <circle cx="12" cy="12" r="9" />
              <path
                d="M3 12h18M12 3c2.5 2.6 3.8 5.7 3.8 9S14.5 18.4 12 21c-2.5-2.6-3.8-5.7-3.8-9S9.5 5.6 12 3Z"
              />
            </svg>
            {{ t('mobile.account.language') }}
            <svg
              class="m-drawer__chevron"
              viewBox="0 0 24 24"
              width="18"
              height="18"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
            >
              <path d="m9 5 7 7-7 7" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </NuxtLink>
          <NuxtLink class="m-drawer__row" to="/account/settings" @click="emit('close')">
            <svg
              class="m-drawer__icon"
              viewBox="0 0 24 24"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
            >
              <circle cx="12" cy="12" r="3.2" />
              <path
                d="M19 12a7 7 0 0 0-.2-1.6l2-1.5-2-3.4-2.3 1a7 7 0 0 0-2.7-1.6L13.4 2h-2.8l-.4 2.9a7 7 0 0 0-2.7 1.6l-2.3-1-2 3.4 2 1.5A7 7 0 0 0 5 12c0 .5.1 1.1.2 1.6l-2 1.5 2 3.4 2.3-1a7 7 0 0 0 2.7 1.6l.4 2.9h2.8l.4-2.9a7 7 0 0 0 2.7-1.6l2.3 1 2-3.4-2-1.5c.1-.5.2-1.1.2-1.6Z"
                stroke-linejoin="round"
              />
            </svg>
            {{ t('mobile.drawer.settings') }}
            <svg
              class="m-drawer__chevron"
              viewBox="0 0 24 24"
              width="18"
              height="18"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
            >
              <path d="m9 5 7 7-7 7" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </NuxtLink>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.m-drawer {
  position: fixed;
  inset: 0;
  z-index: 1600;
}

.m-drawer__backdrop {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
}

.m-drawer__panel {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  display: flex;
  flex-direction: column;
  width: 320px;
  background: #ffffff;
  overflow-y: auto;
}

.m-drawer__close {
  position: absolute;
  top: 12px;
  right: 12px;
  display: inline-flex;
  padding: 4px;
  border: 0;
  background: transparent;
  color: #7a7d85;
  cursor: pointer;
}

/* User area (screenshot: light-grey band with avatar/name/sign-out pill) */
.m-drawer__user {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 84px;
  padding: 20px 16px;
  background: #f7f8fa;
}

.m-drawer__avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: #eceef1;
  color: #55565b;
}

.m-drawer__username {
  flex: 1;
  overflow: visible;
  color: #1a1a1a;
  font-size: 16px;
  font-weight: var(--font-weight-bold);

  white-space: normal;
  word-break: break-word;
}

.m-drawer__signout,
.m-drawer__signin {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 36px;
  padding: 0 14px;
  border: 1px solid #e0e1e5;
  border-radius: 18px;
  background: #ffffff;
  color: #55565b;
  font-size: 14px;
  text-decoration: none;
  white-space: nowrap;
}

.m-drawer__body {
  flex: 1;
  background: #ffffff;
}

/* 57px rows, 1px #F0F1F2 separators (measured from the screenshot) */
.m-drawer__row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-height: 57px;
  padding: 0 16px;
  border: 0;
  border-bottom: 1px solid #f0f1f2;
  background: transparent;
  color: #1a1a1a;
  font: inherit;
  font-size: 16px;
  text-align: left;
  text-decoration: none;
  cursor: pointer;
}

button.m-drawer__row {
  width: 100%;
}

.m-drawer__row--strong {
  font-size: 17px;
  font-weight: var(--font-weight-bold);
}

.m-drawer__icon {
  width: 24px;
  height: 24px;
  flex-shrink: 0;
}

.m-drawer__row-label {
  flex: 1;
}

.m-drawer__row > :first-child {
  flex-shrink: 0;
}

.m-drawer__chevron {
  margin-left: auto;
  flex-shrink: 0;
  color: #7a7d85;
  transition: transform 0.2s ease;
}

.m-drawer__chevron--open {
  transform: rotate(90deg);
}

.m-drawer__sublist {
  margin: 0;
  padding: 0 16px 8px 52px;
  list-style: none;
  background: #ffffff;
}

.m-drawer__subitem {
  display: flex;
  align-items: center;
  min-height: 48px;
  color: #1a1a1a;
  font-size: 16px;
  text-decoration: none;
}

.m-drawer__gap {
  height: 8px;
  background: #f5f6fa;
}

/* UI-only switch */
.m-drawer__toggle {
  display: inline-flex;
  align-items: center;
  width: 44px;
  height: 26px;
  margin-left: auto;
  padding: 2px;
  border: 0;
  border-radius: 13px;
  background: #c7c9cf;
  cursor: pointer;
  transition: background 0.2s ease;
}

.m-drawer__toggle--on {
  background: #1a1a1a;
}

.m-drawer__toggle-knob {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #ffffff;
  transition: transform 0.2s ease;
}

.m-drawer__toggle--on .m-drawer__toggle-knob {
  transform: translateX(18px);
}
</style>
