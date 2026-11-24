<script setup>
import { ref } from 'vue'

import { useLocale } from '../../composables/useLocale'

// Mobile messages (docs/20 §5.7, new route /account/messages): two tabs —
// 【客服】a support entry card (description + 在线咨询 button to
// /help/customer-service) and 【订单】order status notifications built from
// the recent orders payload at page level. Presentational; tab state is
// local, the notification rows arrive via props (ADR 0001).
defineProps({
  signedIn: { type: Boolean, default: false },
  notifications: { type: Array, default: () => [] },
})

const emit = defineEmits(['back'])

const { t } = useLocale()

const activeTab = ref('support')

const tabs = [
  { key: 'support', label: t('mobile.messages.tabSupport') },
  { key: 'orders', label: t('mobile.messages.tabOrders') },
]
</script>

<template>
  <div class="m-msg">
    <MobilePageHeader :title="t('mobile.messages.title')" @back="emit('back')" />

    <!-- Tab row (docs/20 §0: 16px selected 700 + 2px black underline). -->
    <nav class="m-msg__tabs" :aria-label="t('account.tabs')">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="m-msg__tab"
        :class="{ 'm-msg__tab--active': tab.key === activeTab }"
        type="button"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </button>
    </nav>

    <!-- Support tab: entry card to the customer-service page. -->
    <section v-if="activeTab === 'support'" class="m-msg__card">
      <span class="m-msg__icon" aria-hidden="true">
        <svg
          viewBox="0 0 24 24"
          width="26"
          height="26"
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
      </span>
      <p class="m-msg__desc">{{ t('mobile.messages.supportDesc') }}</p>
      <NuxtLink class="m-msg__cta" to="/help/customer-service">
        {{ t('mobile.messages.supportCta') }}
      </NuxtLink>
    </section>

    <!-- Orders tab: status notifications from the recent orders. -->
    <template v-else>
      <div v-if="!signedIn" class="m-msg__card m-msg__card--empty" role="status">
        <p class="m-msg__empty-text">{{ t('orders.signInRequired') }}</p>
        <NuxtLink class="m-msg__signin" to="/auth/login">{{ t('header.signIn') }}</NuxtLink>
      </div>

      <div
        v-else-if="notifications.length === 0"
        class="m-msg__card m-msg__card--empty"
        role="status"
      >
        <p class="m-msg__empty-text">{{ t('mobile.messages.empty') }}</p>
      </div>

      <ul v-else class="m-msg__list">
        <li v-for="item in notifications" :key="item.key" class="m-msg__card m-msg__card--row">
          <span
            class="m-msg__dot"
            :class="`m-msg__dot--${item.statusClass}`"
            aria-hidden="true"
          ></span>
          <div class="m-msg__row-body">
            <p class="m-msg__row-title">#{{ item.number }} · {{ item.statusLabel }}</p>
            <p class="m-msg__row-time">{{ item.date }}</p>
          </div>
          <NuxtLink
            class="m-msg__row-link"
            :to="`/account/orders/${item.publicId}`"
            :aria-label="t('orders.viewDetails')"
          >
            <svg
              viewBox="0 0 24 24"
              width="18"
              height="18"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
            >
              <path d="m9 5 7 7-7 7" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </NuxtLink>
        </li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.m-msg {
  min-height: 60vh;
  padding-bottom: 24px;
  background: #f5f6fa;
}

.m-msg__tabs {
  display: flex;
  background: #ffffff;
  border-bottom: 1px solid #f0f1f2;
}

.m-msg__tab {
  min-height: 44px;
  flex: 1;
  padding: 0 14px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: #1a1a1a;
  font: inherit;
  font-size: 16px;
  cursor: pointer;
}

.m-msg__tab--active {
  font-weight: var(--font-weight-bold);
  border-bottom-color: #1a1a1a;
}

.m-msg__card {
  margin: 16px 16px 0;
  padding: 24px 16px;
  border-radius: 12px;
  background: #ffffff;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.m-msg__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: #f5f6fa;
  color: #55565b;
}

.m-msg__desc {
  margin: 14px 0 0;
  color: #1a1a1a;
  font-size: 15px;
  line-height: 1.5;
}

.m-msg__cta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 44px;
  margin-top: 16px;
  padding: 0 28px;
  border-radius: 22px;
  background: #e1251b;
  color: #ffffff;
  font-size: 15px;
  font-weight: var(--font-weight-semibold);
  text-decoration: none;
}

.m-msg__card--empty {
  padding: 40px 16px;
}

.m-msg__empty-text {
  margin: 0;
  color: #1a1a1a;
  font-size: 15px;
  font-weight: var(--font-weight-semibold);
}

.m-msg__signin {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 44px;
  margin-top: 16px;
  padding: 0 24px;
  border-radius: 22px;
  background: #1a1a1a;
  color: #ffffff;
  font-size: 15px;
  font-weight: var(--font-weight-semibold);
  text-decoration: none;
}

.m-msg__list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 16px 16px 0;
  padding: 0;
  list-style: none;
}

.m-msg__card--row {
  flex-direction: row;
  align-items: center;
  gap: 12px;
  padding: 14px;
  text-align: left;
}

.m-msg__dot {
  width: 10px;
  height: 10px;
  flex-shrink: 0;
  border-radius: 50%;
  background: #c2c4cc;
}

.m-msg__dot--pending {
  background: #e8a23b;
}

.m-msg__dot--shipped {
  background: #1869f5;
}

.m-msg__dot--completed {
  background: #16a34a;
}

.m-msg__row-body {
  flex: 1;
  min-width: 0;
}

.m-msg__row-title {
  margin: 0;
  color: #1a1a1a;
  font-size: 15px;
  font-weight: var(--font-weight-semibold);
}

.m-msg__row-time {
  margin: 4px 0 0;
  color: #7a7d85;
  font-size: 13px;
}

.m-msg__row-link {
  display: inline-flex;
  color: #7a7d85;
}
</style>
