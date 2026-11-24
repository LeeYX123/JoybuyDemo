<script setup>
import { useLocale } from '../../composables/useLocale'

// Mobile order list (docs/20 §5.1): tab row (same keys/?tab= semantics as the
// desktop AccountTabs, 16px selected + 2px black underline) and one card per
// order (status badge, first item image, number/date/total, view-details
// link). Presentational only — tab filtering, pagination and formatting live
// in pages/account/orders/index.vue, which feeds resolved rows as props
// (ADR 0001: desktop template untouched).
defineProps({
  signedIn: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  tabs: { type: Array, default: () => [] },
  activeTab: { type: String, default: 'all' },
  orders: { type: Array, default: () => [] },
})

const emit = defineEmits(['tab'])

const { t } = useLocale()
</script>

<template>
  <div class="m-orders">
    <MobilePageHeader :title="t('accountMenu.orders')" />

    <!-- Signed out -->
    <div v-if="!signedIn" class="m-orders__empty" role="status">
      <p class="m-orders__empty-title">{{ t('orders.signInRequired') }}</p>
      <p class="m-orders__empty-note">{{ t('orders.signInNote') }}</p>
      <NuxtLink class="m-orders__signin" to="/auth/login">{{ t('header.signIn') }}</NuxtLink>
    </div>

    <template v-else>
      <!-- Tab row: 16px, selected 700 + 2px black underline (docs/20 §0). -->
      <nav class="m-orders__tabs" :aria-label="t('account.tabs')">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="m-orders__tab"
          :class="{ 'm-orders__tab--active': tab.key === activeTab }"
          type="button"
          @click="emit('tab', tab.key)"
        >
          {{ tab.label }}
          <span v-if="tab.count > 0" class="m-orders__tab-count">{{ tab.count }}</span>
        </button>
      </nav>

      <!-- Loading skeleton -->
      <div v-if="loading" class="m-orders__list" aria-hidden="true">
        <div v-for="index in 2" :key="index" class="m-orders__card m-orders__card--skeleton">
          <span class="m-orders__sk-line"></span>
          <span class="m-orders__sk-line m-orders__sk-line--short"></span>
        </div>
      </div>

      <!-- Empty state: same copy as the desktop orders.emptyTab*. -->
      <div v-else-if="orders.length === 0" class="m-orders__empty" role="status">
        <p class="m-orders__empty-title">{{ t('orders.emptyTab') }}</p>
        <p class="m-orders__empty-note">{{ t('orders.emptyTabNote') }}</p>
      </div>

      <!-- Order cards -->
      <ul v-else class="m-orders__list">
        <li v-for="order in orders" :key="order.publicId">
          <article class="m-orders__card">
            <header class="m-orders__card-head">
              <span class="m-orders__badge" :class="`m-orders__badge--${order.statusClass}`">
                {{ order.statusLabel }}
              </span>
              <span class="m-orders__number">#{{ order.number }}</span>
            </header>
            <div class="m-orders__card-body">
              <img
                v-if="order.image"
                class="m-orders__img"
                :src="order.image"
                :alt="order.title"
                loading="lazy"
              />
              <span v-else class="m-orders__img m-orders__img--placeholder" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="26" height="26">
                  <path
                    d="M12 2 3 7v10l9 5 9-5V7l-9-5Zm0 2.3L18.6 8 12 11.7 5.4 8 12 4.3ZM5 9.7l6 3.3v6.4l-6-3.3V9.7Zm8 9.7V13l6-3.3v6.4l-6 3.3Z"
                    fill="currentColor"
                  />
                </svg>
              </span>
              <div class="m-orders__info">
                <p class="m-orders__date">{{ order.date }}</p>
                <p class="m-orders__total">
                  {{ t('orders.total') }} <strong>{{ order.total }}</strong>
                </p>
              </div>
            </div>
            <footer class="m-orders__card-foot">
              <NuxtLink class="m-orders__detail" :to="`/account/orders/${order.publicId}`">
                {{ t('orders.viewDetails') }}
              </NuxtLink>
            </footer>
          </article>
        </li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.m-orders {
  min-height: 60vh;
  padding-bottom: 24px;
  background: #f5f6fa;
}

/* Tab row */
.m-orders__tabs {
  display: flex;
  overflow-x: auto;
  background: #ffffff;
  border-bottom: 1px solid #f0f1f2;
  scrollbar-width: none;
}

.m-orders__tabs::-webkit-scrollbar {
  display: none;
}

.m-orders__tab {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  min-height: 44px;
  padding: 0 14px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: #1a1a1a;
  font: inherit;
  font-size: 16px;
  white-space: nowrap;
  cursor: pointer;
}

.m-orders__tab--active {
  font-weight: var(--font-weight-bold);
  border-bottom-color: #1a1a1a;
}

.m-orders__tab-count {
  color: #7a7d85;
  font-size: 13px;
  font-weight: var(--font-weight-regular);
}

/* Cards */
.m-orders__list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 12px 16px 0;
  padding: 0;
  list-style: none;
}

.m-orders__card {
  border-radius: 12px;
  background: #ffffff;
  overflow: hidden;
}

.m-orders__card--skeleton {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px;
}

.m-orders__sk-line {
  height: 16px;
  width: 60%;
  border-radius: 4px;
  background: #eceef1;
}

.m-orders__sk-line--short {
  width: 40%;
}

.m-orders__card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 1px solid #f0f1f2;
}

/* Status badge: soft tint + state colour. */
.m-orders__badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: var(--font-weight-semibold);
}

.m-orders__badge--pending {
  background: #fff5e6;
  color: #995c00;
}

.m-orders__badge--shipped {
  background: #e8f1fd;
  color: #1869f5;
}

.m-orders__badge--completed {
  background: #e8f7ec;
  color: #16a34a;
}

.m-orders__badge--canceled {
  background: #f0f1f2;
  color: #7a7d85;
}

.m-orders__number {
  color: #55565b;
  font-size: 13px;
}

.m-orders__card-body {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
}

.m-orders__img {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
  flex-shrink: 0;
  border-radius: 8px;
  object-fit: cover;
  background: #f5f6fa;
  color: #c2c4cc;
}

.m-orders__img--placeholder {
  background: #f5f6fa;
}

.m-orders__info {
  flex: 1;
  min-width: 0;
}

.m-orders__date {
  margin: 0;
  color: #7a7d85;
  font-size: 13px;
}

.m-orders__total {
  margin: 6px 0 0;
  color: #55565b;
  font-size: 14px;
}

.m-orders__total strong {
  color: #1a1a1a;
  font-size: 16px;
  font-weight: var(--font-weight-bold);
}

.m-orders__card-foot {
  display: flex;
  justify-content: flex-end;
  padding: 10px 14px;
  border-top: 1px solid #f0f1f2;
}

.m-orders__detail {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 14px;
  border: 1px solid #1a1a1a;
  border-radius: 999px;
  color: #1a1a1a;
  font-size: 13px;
  font-weight: var(--font-weight-semibold);
  text-decoration: none;
}

/* Empty / signed-out state */
.m-orders__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin: 24px 16px;
  padding: 40px 16px;
  border-radius: 12px;
  background: #ffffff;
  text-align: center;
}

.m-orders__empty-title {
  margin: 0;
  color: #1a1a1a;
  font-size: 16px;
  font-weight: var(--font-weight-semibold);
}

.m-orders__empty-note {
  margin: 8px 0 0;
  color: #7a7d85;
  font-size: 14px;
  line-height: 1.5;
}

.m-orders__signin {
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
</style>
