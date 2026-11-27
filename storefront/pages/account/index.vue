<script setup>
import { computed, onMounted } from 'vue'
import { NuxtLink } from '#components'
import { useFetch, useHead, useRequestHeaders, useRuntimeConfig } from '#imports'

import { useBuyerAuth } from '../../composables/useBuyerAuth'
import { useLocale } from '../../composables/useLocale'
import { useMerchantEntry } from '../../composables/useMerchantEntry'
import { useMobileView } from '../../composables/useMobileView'

// 需求 22.3-2（2026-11-22 真站 /profile 实测）：用户中心是**纵向堆叠**结构
// （无左侧导航）：用户信息行 → 订单状态条 → 权益 tile 网格；内容区 1264px、
// 页面白底、卡片 #f5f6fa / 8px 圆角。实测值见
// var/z2_support_account_20261122/real_profile_structure_zh.json 与
// real_profile_rules_zh.css。功能保持原样（订单/售后/评价/地址/收藏/浏览记录/
// 申请店铺），只重做视觉与结构。
const { isAuthenticated, account, logout } = useBuyerAuth()
const { t } = useLocale()
const { isMobileHost } = useMobileView()
const config = useRuntimeConfig()
const {
  label: merchantLabel,
  description: merchantDesc,
  linkTarget,
  switching,
  loadStatus,
  openMerchantConsole,
} = useMerchantEntry()

const ordersUrl = computed(() =>
  import.meta.server ? `${config.apiBaseInternal}/orders` : '/api/v1/orders',
)

const { data: ordersData } = await useFetch(ordersUrl, {
  key: 'buyer-orders',
  headers: { cookie: useRequestHeaders(['cookie']).cookie || '' },
})

const orders = computed(() =>
  Array.isArray(ordersData.value?.orders) ? ordersData.value.orders : [],
)

const counts = computed(() => ({
  pendingPayment: orders.value.filter((order) => order.state === 'PENDING_PAYMENT').length,
  shipped: orders.value.filter((order) => order.state === 'SHIPPED').length,
  completed: orders.value.filter((order) => order.state === 'COMPLETED').length,
}))

// 真站订单条：首格【我的订单】+ 状态格（数字 24/700、标签 18/400）。
const orderStats = computed(() => [
  {
    key: 'pending_payment',
    label: t('orders.tabPendingPayment'),
    count: counts.value.pendingPayment,
  },
  { key: 'shipped', label: t('orders.tabToReceive'), count: counts.value.shipped },
  { key: 'completed', label: t('orders.tabCompleted'), count: counts.value.completed },
])

// 真站权益 tile（22/700 标题 + 24px 图标 + 16px 右箭头 + 18px 灰描述）。
// 2026-11-25 与真站 /profile 重新对齐：磁贴 = 优惠券 / 心愿单(我的收藏) / 积分
// （真站口径）；原「售后/评价/最近浏览」磁贴移除，最近浏览页仍可直链访问。
const modules = computed(() => [
  {
    key: 'coupons',
    to: '/account/coupons',
    title: t('accountMenu.coupons'),
    description: t('account.couponsEmpty'),
    icon: 'coupons',
  },
  {
    key: 'favourites',
    to: '/account/favourites',
    title: t('accountMenu.favourites'),
    description: t('account.moduleFavouritesDesc'),
    icon: 'favourites',
  },
  {
    key: 'points',
    to: '/account/points',
    title: t('accountMenu.points'),
    description: t('account.pointsEmpty'),
    icon: 'points',
  },
  {
    key: 'merchant',
    to: linkTarget.value,
    title: merchantLabel.value,
    description: merchantDesc.value,
    icon: 'shop',
  },
])

onMounted(() => {
  // 2026-11-27：同 AccountNav——节流再校验由 useBuyerAuth 在路由完成时统一负责。
  if (isAuthenticated.value) loadStatus()
})

// 真站 /profile 昵称优先用账号 display_name（与右上角下拉一致），旧 payload
// 缺字段时退回 display_identifier / 邮箱 / 手机号。
const displayName = computed(
  () =>
    account.value?.display_name ||
    account.value?.display_identifier ||
    account.value?.email ||
    account.value?.phone_number,
)

async function signOut() {
  await logout()
  await navigateTo('/auth/login')
}

useHead(() => ({ title: t('account.myAccount') }))
</script>

<template>
  <!-- ADR 0001: on the m. host the account hub renders the mobile layout
       (docs/19 §3, real-site screenshots 2026-11-24); the desktop stacked
       profile below is untouched. -->
  <MobileAccount v-if="isMobileHost" />
  <div v-else class="profile-page">
    <AppContainer>
      <section
        v-if="isAuthenticated"
        class="profile"
        aria-labelledby="profile-title"
        data-testid="account-profile"
      >
        <!-- 真站 UserInfoSection（120px 高 / 20px 24px 内边距）：60px 头像 +
             28px/700 昵称 + 18px 文本链接行（8px 12px 内边距 / 4px 圆角）。 -->
        <header class="profile-me">
          <div class="profile-me__identity">
            <span class="profile-me__avatar" aria-hidden="true">
              <svg viewBox="0 0 56 56" width="60" height="60">
                <rect width="56" height="56" fill="#E5E7F0" rx="28" />
                <path
                  fill="#fff"
                  fill-rule="evenodd"
                  clip-rule="evenodd"
                  d="M29.782 17.512a2.989 2.989 0 1 1-5.978 0 2.989 2.989 0 0 1 5.978 0m-9.284 9.415a2.988 2.988 0 1 1-5.977-.001 2.988 2.988 0 0 1 5.977 0m-3.02 9.574v6.082c13.81 0 25.042-11.235 25.042-25.044h-6.08c0 10.456-8.507 18.962-18.962 18.962"
                />
              </svg>
            </span>
            <div class="profile-me__body">
              <h1 id="profile-title" class="profile-me__name" data-testid="account-profile-name">
                {{ displayName }}
              </h1>
              <div class="profile-me__links">
                <NuxtLink
                  class="profile-me__link"
                  to="/account/addresses"
                  data-testid="account-addresses"
                >
                  <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
                    <path
                      d="M12 2a7 7 0 0 1 7 7c0 5-7 13-7 13S5 14 5 9a7 7 0 0 1 7-7Zm0 4a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z"
                      fill="currentColor"
                    />
                  </svg>
                  {{ t('accountMenu.addresses') }}
                </NuxtLink>
                <span class="profile-me__divider" aria-hidden="true"></span>
                <button class="profile-me__link" type="button" @click="signOut">
                  <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
                    <path
                      d="M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 8l-4 4 4 4M6 12h9"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="1.6"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                  </svg>
                  {{ t('accountMenu.signOut') }}
                </button>
              </div>
            </div>
          </div>
        </header>

        <!-- 真站 OrderStatusSection：1264×120 的 #f5f6fa 卡片（20px 24px、
             8px 圆角）；首格透明，状态格 80px 高白底 8px 圆角。 -->
        <section class="profile-orders" :aria-label="t('accountMenu.orders')">
          <NuxtLink
            class="profile-orders__item profile-orders__item--all"
            to="/account/orders"
            data-testid="account-orders"
          >
            <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
              <path
                d="M6 3h12a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Zm2 4v2h8V7H8Zm0 4v2h8v-2H8Zm0 4v2h5v-2H8Z"
                fill="currentColor"
              />
            </svg>
            <span>{{ t('accountMenu.orders') }}</span>
            <svg
              class="profile-orders__arrow"
              viewBox="0 0 24 24"
              width="16"
              height="16"
              aria-hidden="true"
            >
              <path
                d="m9 5 7 7-7 7"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          </NuxtLink>
          <NuxtLink
            v-for="stat in orderStats"
            :key="stat.key"
            class="profile-orders__item"
            :to="`/account/orders?tab=${stat.key}`"
            :data-testid="`account-orders-${stat.key}`"
          >
            <strong class="profile-orders__num">{{ stat.count }}</strong>
            <span class="profile-orders__label">{{ stat.label }}</span>
          </NuxtLink>
        </section>

        <!-- 真站 UserBenefitsSection：3 列 tile（104px 高 / #f5f6fa / 8px 圆角 /
             24px 24px 16px 内边距；标题 22/700、描述 18/400 #888b94）。 -->
        <nav class="profile-modules" :aria-label="t('account.modules')">
          <component
            :is="module.to ? NuxtLink : 'button'"
            v-for="module in modules"
            :key="module.key"
            class="profile-module"
            :class="{ 'profile-module--action': !module.to }"
            :to="module.to || undefined"
            :type="module.to ? undefined : 'button'"
            :disabled="!module.to && switching"
            :data-testid="`account-module-${module.key}`"
            @click="!module.to && openMerchantConsole()"
          >
            <span class="profile-module__title">
              <span class="profile-module__title-text">
                <svg
                  v-if="module.icon === 'coupons'"
                  viewBox="0 0 24 24"
                  width="24"
                  height="24"
                  aria-hidden="true"
                >
                  <path
                    d="M3 5h18a1 1 0 0 1 1 1v4a2 2 0 0 0 0 4v4a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-4a2 2 0 0 0 0-4V6a1 1 0 0 1 1-1Zm3 4v2h6V9H6Zm0 4v2h10v-2H6Z"
                    fill="currentColor"
                  />
                </svg>
                <svg
                  v-else-if="module.icon === 'favourites'"
                  viewBox="0 0 24 24"
                  width="24"
                  height="24"
                  aria-hidden="true"
                >
                  <path
                    d="M12 20.3C8.4 17.7 3 13.9 3 9.5A4.5 4.5 0 0 1 12 7a4.5 4.5 0 0 1 9 2.5c0 4.4-5.4 8.2-9 10.8Z"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.7"
                    stroke-linejoin="round"
                  />
                </svg>
                <svg
                  v-else-if="module.icon === 'points'"
                  viewBox="0 0 24 24"
                  width="24"
                  height="24"
                  aria-hidden="true"
                >
                  <path
                    d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm1 5v3.2l3 1.7-1 1.7-3-1.7-3 1.7-1-1.7 3-1.7V7h2Z"
                    fill="currentColor"
                  />
                </svg>
                <svg v-else viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
                  <path
                    d="M4 4h16v3H4V4Zm0 5h16v10a1 1 0 0 1-1 1h-5v-5H10v5H5a1 1 0 0 1-1-1V9Zm2 2v2h2v-2H6Zm4 0v2h2v-2h-2Zm4 0v2h2v-2h-2Z"
                    fill="currentColor"
                  />
                </svg>
                <span>{{
                  switching && !module.to ? t('merchantEntry.opening') : module.title
                }}</span>
              </span>
              <svg
                class="profile-module__arrow"
                viewBox="0 0 24 24"
                width="16"
                height="16"
                aria-hidden="true"
              >
                <path
                  d="m9 5 7 7-7 7"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.8"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            </span>
            <span class="profile-module__desc">{{ module.description }}</span>
          </component>
        </nav>
      </section>

      <section v-else class="profile-signed-out" aria-labelledby="profile-title">
        <h1 id="profile-title">{{ t('account.myAccount') }}</h1>
        <p>{{ t('account.signInPrompt') }}</p>
        <div class="profile-signed-out__actions">
          <NuxtLink to="/auth/login"
            ><BaseButton variant="primary">{{ t('header.signIn') }}</BaseButton></NuxtLink
          >
          <NuxtLink to="/auth/register">
            <BaseButton variant="secondary">{{ t('auth.createAccount') }}</BaseButton>
          </NuxtLink>
        </div>
      </section>
    </AppContainer>
  </div>
</template>

<style scoped>
/* 真站 /profile 实测（1440×1200，2026-11-22）：
   profile_container = 白底 + 上下 48px，内层 w=1264 居中；无左侧导航。 */
.profile-page {
  --container-max: calc(1264px + 2 * var(--container-pad));

  padding-block: 48px;
  background: #fff;
}

.profile {
  display: flex;
  flex-direction: column;
}

/* UserInfoSection：120px 高、20px 24px 内边距。 */
.profile-me {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 120px;
  padding: 20px 24px;
}

.profile-me__identity {
  display: flex;
  flex: 1;
  align-items: center;
  min-width: 0;
}

.profile-me__avatar {
  display: inline-flex;
  width: 60px;
  height: 60px;
  flex: none;
  align-items: center;
  justify-content: center;
  margin-right: 10px;
  border-radius: 50%;
  background: #fff;
  overflow: hidden;
}

.profile-me__avatar svg {
  display: block;
  border-radius: 50%;
}

.profile-me__body {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-width: 0;
  min-height: 76px;
  margin-right: 20px;
}

.profile-me__name {
  overflow: visible;
  max-width: 750px;
  margin: 0 0 0 12px;
  color: #1a1a1a;
  font-size: 28px;
  font-weight: 700;
  line-height: 1.5;

  white-space: normal;
  word-break: break-word;
}

.profile-me__links {
  display: flex;
  align-items: center;
  margin-left: 12px;
}

.profile-me__link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 8px 12px;
  border: 0;
  border-radius: 4px;
  background: none;
  color: inherit;
  font: inherit;
  font-size: 20px;
  line-height: 24px;
  text-align: center;
  text-decoration: none;
  cursor: pointer;
}

.profile-me__link svg {
  display: inline-block;
  flex: none;
}

.profile-me__link:hover {
  background: rgb(0 16 71 / 6%);
}

.profile-me__link:active {
  background: rgb(0 16 71 / 10%);
}

.profile-me__divider {
  display: inline-block;
  width: 1px;
  height: 20px;
  margin: 0 16px;
  background: #f0f1f2;
}

/* OrderStatusSection：margin-top 24 / #f5f6fa / padding 20px 24px / 8px 圆角。 */
.profile-orders {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  margin-top: 24px;
  padding: 20px 24px;
  border-radius: 8px;
  background: #f5f6fa;
}

.profile-orders__item {
  display: flex;
  width: 224px;
  height: 80px;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
  border-radius: 8px;
  background: #fff;
  color: #1a1a1a;
  text-align: center;
  text-decoration: none;
  cursor: pointer;
  transition: background-color 120ms ease;
}

.profile-orders__item:hover {
  background: #fafafa;
}

.profile-orders__item--all {
  flex-direction: row;
  justify-content: center;
  gap: 4px;
  background: transparent;
  font-size: 22px;
  font-weight: 700;
  line-height: 24px;
}

.profile-orders__item--all:hover {
  background: rgb(0 0 0 / 2%);
}

.profile-orders__arrow {
  flex: none;
}

.profile-orders__num {
  color: #1a1a1a;
  font-size: 24px;
  font-weight: 700;
  line-height: 24px;
}

.profile-orders__label {
  color: #1a1a1a;
  font-size: 18px;
  font-weight: 400;
  line-height: 24px;
}

/* UserBenefitsSection：margin-top 32 / 3 列 / 104px 高 / #f5f6fa / 16px 间距。 */
.profile-modules {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin-top: 32px;
}

.profile-module {
  display: flex;
  min-height: 104px;
  flex-direction: column;
  justify-content: space-between;
  gap: 8px;
  padding: 24px 24px 16px;
  border: 0;
  border-radius: 8px;
  background: #f5f6fa;
  color: #1a1a1a;
  text-align: left;
  text-decoration: none;
  font: inherit;
  cursor: pointer;
  transition: background-color 120ms ease;
}

.profile-module:hover {
  background: #f0f1f4;
}

.profile-module--action:disabled {
  cursor: progress;
  opacity: 0.75;
}

.profile-module__title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  font-size: 22px;
  font-weight: 700;
  line-height: 22px;
}

.profile-module__title-text {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.profile-module__title-text svg {
  flex: none;
}

.profile-module__arrow {
  flex: none;
}

.profile-module__desc {
  color: #888b94;
  font-size: 18px;
  font-weight: 400;
  line-height: 24px;
}

.profile-signed-out {
  max-width: 30rem;
  margin: var(--space-10) auto;
  padding: var(--space-8);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-lg);
  background: var(--colour-surface);
}

.profile-signed-out p {
  margin-block: var(--space-3) var(--space-5);
  color: var(--colour-text-secondary);
}

.profile-signed-out__actions {
  display: flex;
  gap: var(--space-3);
}

.profile-signed-out__actions :deep(a) {
  text-decoration: none;
}

@media (max-width: 63.999rem) {
  .profile-module__title {
    font-size: 20px;
    line-height: 20px;
  }

  .profile-module__desc {
    font-size: 16px;
    line-height: 22px;
  }
}

@media (max-width: 47.999rem) {
  .profile-page {
    padding-block: 24px;
  }

  .profile-me {
    padding: 16px 0;
  }

  .profile-me__name {
    font-size: 24px;
  }

  .profile-me__link {
    padding: 8px 6px;
    font-size: 16px;
  }

  .profile-me__divider {
    margin: 0 4px;
  }

  .profile-orders {
    flex-wrap: wrap;
    gap: 12px;
    padding: 16px;
  }

  .profile-orders__item {
    width: calc(50% - 6px);
    height: 72px;
    flex: none;
  }

  .profile-orders__item--all {
    width: 100%;
    height: 56px;
  }

  .profile-orders__num {
    font-size: 22px;
  }

  .profile-orders__label {
    font-size: 16px;
  }

  .profile-modules {
    grid-template-columns: minmax(0, 1fr);
    gap: 12px;
    margin-top: 24px;
  }

  .profile-module {
    min-height: 88px;
    padding: 20px 16px 14px;
  }

  .profile-module__title {
    font-size: 20px;
    line-height: 20px;
  }

  .profile-module__desc {
    font-size: 16px;
    line-height: 22px;
  }
}
</style>
