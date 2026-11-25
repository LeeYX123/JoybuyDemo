<script setup>
import { computed } from 'vue'

import { useBuyerAuth } from '../../composables/useBuyerAuth'
import { useLocale } from '../../composables/useLocale'
import { useMarketLocale } from '../../composables/useMarketLocale'

// Mobile account hub (docs/19 §3, user-provided real-site screenshots
// 2026-11-24): user card, order stat tiles, favourites cards, activities &
// rewards, help rows, "more" rows, About Joybuy band.
// Scope decisions from the user: no JoyPlus trial banner, no coupons row,
// 活动与奖励 keeps only 评价, 更多 keeps 语言 + 设置&隐私 (no country/region).
const { t } = useLocale()
const { isAuthenticated, account } = useBuyerAuth()
const { availableLocales, localeCode } = useMarketLocale()

const displayName = computed(
  () =>
    account.value?.display_name ||
    account.value?.display_identifier ||
    account.value?.email ||
    account.value?.phone_number ||
    '',
)

const orderTiles = computed(() => [
  {
    key: 'pending',
    label: t('orders.tabPendingPayment'),
    to: '/account/orders?tab=pending_payment',
    icon: 'clock',
  },
  {
    key: 'ongoing',
    label: t('orders.tabToReceive'),
    to: '/account/orders?tab=to_receive',
    icon: 'truck',
  },
  {
    key: 'returns',
    label: t('accountMenu.returns'),
    to: '/account/returns',
    icon: 'doc',
  },
])

const favouriteCards = computed(() => [
  { key: 'wishlist', label: t('accountMenu.wishlist'), to: '/account/favourites', icon: 'heart' },
  {
    key: 'again',
    label: t('mobile.account.buyAgain'),
    to: '/account/recently-viewed',
    icon: 'bag',
  },
])

const helpRows = computed(() => [
  { key: 'support', label: t('mobile.account.support247'), to: '/help/customer-service' },
  { key: 'feedback', label: t('mobile.account.feedback'), to: '/pages/contact-us' },
])

const currentLanguageLabel = computed(() => {
  const current = (availableLocales.value || []).find((item) => item.code === localeCode.value)
  return current?.name || current?.label || localeCode.value
})

const aboutBullets = computed(() => [
  { key: 'speedy', label: t('mobile.home.about1') },
  { key: 'trusted', label: t('mobile.home.about2') },
  { key: 'support', label: t('mobile.home.about3') },
])

function iconFor(name) {
  const icons = {
    clock: 'M12 3a9 9 0 1 0 9 9 9 9 0 0 0-9-9Zm0 5v4l3 2',
    truck: 'M3 7h11v9H3zM14 10h4l3 3v3h-7z M7 18a1.8 1.8 0 1 0 0-.01M17 18a1.8 1.8 0 1 0 0-.01',
    doc: 'M6 3h9l4 4v14H6zM9 9h6M9 13h6M9 17h4',
    heart: 'M12 20s-7-4.6-9.3-9A5.3 5.3 0 0 1 12 6.7 5.3 5.3 0 0 1 21.3 11C19 15.4 12 20 12 20Z',
    bag: 'M6 8h12l1 12H5zM9 8a3 3 0 0 1 6 0',
    star: 'M12 4l2.4 4.9 5.4.8-3.9 3.8.9 5.3-4.8-2.5-4.8 2.5.9-5.3L4.2 9.7l5.4-.8z',
    chat: 'M21 12a8 8 0 1 0-3 6.2L21 20z',
    globe:
      'M12 3a9 9 0 1 0 9 9 9 9 0 0 0-9-9ZM3 12h18M12 3c2.5 2.6 3.8 5.7 3.8 9S14.5 18.4 12 21c-2.5-2.6-3.8-5.7-3.8-9S9.5 5.6 12 3Z',
    gear: 'M12 8.8A3.2 3.2 0 1 0 12 15.2 3.2 3.2 0 0 0 12 8.8Zm7.5 3.2a7 7 0 0 0-.2-1.6l2-1.5-2-3.4-2.3 1a7 7 0 0 0-2.7-1.6L13.9 2h-2.8l-.4 2.9a7 7 0 0 0-2.7 1.6l-2.3-1-2 3.4 2 1.5a7 7 0 0 0 0 3.2l-2 1.5 2 3.4 2.3-1a7 7 0 0 0 2.7 1.6l.4 2.9h2.8l.4-2.9a7 7 0 0 0 2.7-1.6l2.3 1 2-3.4-2-1.5c.1-.5.2-1.1.2-1.6Z',
  }
  return icons[name] || icons.star
}
</script>

<template>
  <div class="m-acct">
    <template v-if="isAuthenticated">
      <!-- User card -->
      <section class="m-acct__user">
        <span class="m-acct__avatar" aria-hidden="true">
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
        <span class="m-acct__username">{{ displayName }}</span>
      </section>

      <!-- Orders -->
      <section class="m-acct__section">
        <NuxtLink class="m-acct__section-head" to="/account/orders">
          <h2 class="m-acct__section-title">{{ t('mobile.drawer.orders') }}</h2>
          <svg
            class="m-acct__chevron"
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
        <div class="m-acct__tiles">
          <NuxtLink v-for="tile in orderTiles" :key="tile.key" class="m-acct__tile" :to="tile.to">
            <svg
              class="m-acct__tile-icon"
              viewBox="0 0 24 24"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
            >
              <path :d="iconFor(tile.icon)" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            <span class="m-acct__tile-label">{{ tile.label }}</span>
          </NuxtLink>
        </div>
      </section>

      <!-- Favourites -->
      <section class="m-acct__section">
        <div class="m-acct__section-head">
          <h2 class="m-acct__section-title">{{ t('mobile.account.favourites') }}</h2>
        </div>
        <div class="m-acct__cards">
          <NuxtLink
            v-for="card in favouriteCards"
            :key="card.key"
            class="m-acct__fav-card"
            :to="card.to"
          >
            <span class="m-acct__fav-art" aria-hidden="true">
              <svg
                viewBox="0 0 24 24"
                width="34"
                height="34"
                fill="none"
                stroke="currentColor"
                stroke-width="1.4"
              >
                <path :d="iconFor(card.icon)" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </span>
            <span class="m-acct__fav-label">{{ card.label }}</span>
          </NuxtLink>
        </div>
      </section>

      <!-- Activities & rewards: reviews only (优惠券/积分/邀请 don't exist on web) -->
      <section class="m-acct__section">
        <div class="m-acct__section-head">
          <h2 class="m-acct__section-title">{{ t('mobile.account.activities') }}</h2>
        </div>
        <div class="m-acct__list">
          <NuxtLink class="m-acct__row" to="/account/reviews">
            <svg
              class="m-acct__row-icon"
              viewBox="0 0 24 24"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
            >
              <path :d="iconFor('star')" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            {{ t('mobile.account.reviews') }}
            <svg
              class="m-acct__chevron"
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
      </section>

      <!-- Help -->
      <section class="m-acct__section">
        <div class="m-acct__section-head">
          <h2 class="m-acct__section-title">{{ t('mobile.account.help') }}</h2>
        </div>
        <div class="m-acct__list">
          <NuxtLink v-for="row in helpRows" :key="row.key" class="m-acct__row" :to="row.to">
            <svg
              class="m-acct__row-icon"
              viewBox="0 0 24 24"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
            >
              <path
                :d="iconFor(row.key === 'support' ? 'chat' : 'doc')"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            {{ row.label }}
            <svg
              class="m-acct__chevron"
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
      </section>

      <!-- More: language + settings & privacy (country/region dropped) -->
      <section class="m-acct__section">
        <div class="m-acct__section-head">
          <h2 class="m-acct__section-title">{{ t('mobile.account.more') }}</h2>
        </div>
        <div class="m-acct__list">
          <NuxtLink class="m-acct__row" to="/account/language">
            <svg
              class="m-acct__row-icon"
              viewBox="0 0 24 24"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
            >
              <path :d="iconFor('globe')" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            {{ t('mobile.account.language') }}
            <span class="m-acct__row-value">{{ currentLanguageLabel }}</span>
            <svg
              class="m-acct__chevron"
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
          <NuxtLink class="m-acct__row" to="/account/settings">
            <svg
              class="m-acct__row-icon"
              viewBox="0 0 24 24"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
            >
              <path :d="iconFor('gear')" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            {{ t('mobile.account.settingsPrivacy') }}
            <svg
              class="m-acct__chevron"
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
      </section>

      <!-- About Joybuy band -->
      <section class="m-acct__about">
        <h2 class="m-acct__about-title">{{ t('mobile.home.about') }}</h2>
        <ul class="m-acct__about-list">
          <li v-for="bullet in aboutBullets" :key="bullet.key">
            <svg
              viewBox="0 0 24 24"
              width="20"
              height="20"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
            >
              <path
                :d="
                  iconFor(
                    bullet.key === 'speedy' ? 'truck' : bullet.key === 'trusted' ? 'star' : 'chat',
                  )
                "
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            {{ bullet.label }}
          </li>
        </ul>
        <NuxtLink class="m-acct__about-learn" to="/help/customer-service">{{
          t('mobile.home.learnMore')
        }}</NuxtLink>
      </section>
    </template>

    <!-- Signed out: prompt to sign in -->
    <section v-else class="m-acct__signin">
      <span class="m-acct__avatar" aria-hidden="true">
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
      <NuxtLink class="m-acct__signin-btn" to="/auth/login">{{
        t('mobile.drawer.signIn')
      }}</NuxtLink>
      <div class="m-acct__list">
        <NuxtLink class="m-acct__row" to="/help/customer-service">
          <svg
            class="m-acct__row-icon"
            viewBox="0 0 24 24"
            aria-hidden="true"
            fill="none"
            stroke="currentColor"
            stroke-width="1.6"
          >
            <path :d="iconFor('chat')" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          {{ t('mobile.account.support247') }}
          <svg
            class="m-acct__chevron"
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
        <NuxtLink class="m-acct__row" to="/account/language">
          <svg
            class="m-acct__row-icon"
            viewBox="0 0 24 24"
            aria-hidden="true"
            fill="none"
            stroke="currentColor"
            stroke-width="1.6"
          >
            <path :d="iconFor('globe')" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          {{ t('mobile.account.language') }}
          <span class="m-acct__row-value">{{ currentLanguageLabel }}</span>
          <svg
            class="m-acct__chevron"
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
    </section>
  </div>
</template>

<style scoped>
.m-acct {
  min-height: 100%;
  padding-bottom: 24px;
  background: #f5f6fa;
}

/* User card */
.m-acct__user {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 20px 16px;
  background: #ffffff;
}

.m-acct__avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: #eceef1;
  color: #55565b;
}

.m-acct__username {
  color: #1a1a1a;
  font-size: 18px;
  font-weight: var(--font-weight-bold);
}

.m-acct__signin {
  padding: 20px 16px;
  background: #f5f6fa;
}

.m-acct__signin-btn {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 16px;
  padding: 14px 16px;
  border-radius: 12px;
  background: #ffffff;
  color: #1a1a1a;
  font-size: 16px;
  font-weight: var(--font-weight-bold);
  text-decoration: none;
}

/* Sections */
.m-acct__section {
  margin-top: 12px;
  padding: 16px;
  border-radius: 12px;
  background: #ffffff;
}

.m-acct__section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  color: #1a1a1a;
  text-decoration: none;
}

.m-acct__section-title {
  margin: 0;
  font-size: 18px;
  font-weight: var(--font-weight-bold);
}

.m-acct__chevron {
  flex-shrink: 0;
  color: #7a7d85;
}

/* Order tiles: 3-col grey tiles */
.m-acct__tiles {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.m-acct__tile {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 18px 8px;
  border-radius: 12px;
  background: #f5f6fa;
  color: #1a1a1a;
  text-decoration: none;
}

.m-acct__tile-icon {
  width: 26px;
  height: 26px;
}

.m-acct__tile-label {
  font-size: 14px;
}

/* Favourites: 2 big cards with heart/bag art */
.m-acct__cards {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.m-acct__fav-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 18px;
  border-radius: 12px;
  background: #f5f6fa;
  color: #1a1a1a;
  text-decoration: none;
}

.m-acct__fav-art {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  border-radius: 12px;
  background: #eceef1;
  color: #7a7d85;
}

.m-acct__fav-label {
  font-size: 15px;
  font-weight: var(--font-weight-semibold);
}

/* Row lists */
.m-acct__list {
  border: 1px solid #f0f1f2;
  border-radius: 12px;
  background: #ffffff;
  overflow: hidden;
}

.m-acct__row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-height: 54px;
  padding: 0 14px;
  border-bottom: 1px solid #f0f1f2;
  background: #ffffff;
  color: #1a1a1a;
  font-size: 16px;
  text-decoration: none;
}

.m-acct__list .m-acct__row:last-child {
  border-bottom: 0;
}

.m-acct__row-icon {
  width: 24px;
  height: 24px;
  flex-shrink: 0;
}

.m-acct__row-value {
  margin-left: auto;
  color: #7a7d85;
  font-size: 14px;
}

/* About band */
.m-acct__about {
  margin-top: 12px;
  padding: 24px 16px 28px;
  background: #ffffff;
}

.m-acct__about-title {
  margin: 0;
  color: #1a1a1a;
  font-size: 24px;
  font-weight: var(--font-weight-bold);
}

.m-acct__about-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin: 18px 0 0;
  padding: 0;
  list-style: none;
  color: #1a1a1a;
  font-size: 15px;
}

.m-acct__about-list li {
  display: flex;
  align-items: center;
  gap: 12px;
}

.m-acct__about-learn {
  display: inline-block;
  margin-top: 18px;
  color: #1a1a1a;
  font-size: 15px;
  font-weight: var(--font-weight-semibold);
  text-decoration: underline;
  text-underline-offset: 3px;
}
</style>
