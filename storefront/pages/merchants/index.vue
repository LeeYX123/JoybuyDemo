<script setup>
// 搜商家结果页（WP-42，文档「三、购物端 → 搜索结果页（搜商家）」）。
// 原站 joybuy.co.uk 不支持搜商家；按商家店铺名称匹配，点击进入商家页。
import { useLocale } from '../../composables/useLocale'
import { noAutofillSearch } from '../../utils/noAutofill'

const route = useRoute()
const { t } = useLocale()

const query = computed(() => String(route.query.q || ''))

// SSR 直连后端（apiBaseInternal），客户端走 devProxy（与 useSearch 同一模式）。
const config = useRuntimeConfig()
const searchUrl = computed(() => {
  const qs = `q=${encodeURIComponent(query.value)}`
  return import.meta.server
    ? `${config.apiBaseInternal}/merchants/search?${qs}`
    : `/api/v1/merchants/search?${qs}`
})

const { data, status, error } = await useFetch(searchUrl, { key: 'merchant-search' })

const merchants = computed(() => data.value?.items || [])

useHead(() => ({
  title: query.value ? `${t('merchant.searchTitle')}: ${query.value}` : t('merchant.searchTitle'),
}))
</script>

<template>
  <div class="merchant-search">
    <div class="merchant-search__inner">
      <h1 class="merchant-search__title">{{ t('merchant.searchTitle') }}</h1>
      <form
        class="merchant-search__bar"
        @submit.prevent="navigateTo(`/merchants?q=${encodeURIComponent(query)}`)"
      >
        <input
          v-model="query"
          type="search"
          v-bind="noAutofillSearch"
          :placeholder="t('merchant.searchPlaceholder')"
        />
        <button type="submit" class="merchant-search__btn">{{ t('merchant.searchButton') }}</button>
      </form>

      <p v-if="status === 'pending'" class="merchant-search__hint">{{ t('common.loading') }}</p>
      <p v-else-if="error" class="merchant-search__hint merchant-search__hint--error">
        {{ error.message }}
      </p>
      <p v-else-if="!merchants.length" class="merchant-search__hint">
        {{ t('merchant.noResults') }}
      </p>

      <ul v-else class="merchant-list">
        <li v-for="merchant in merchants" :key="merchant.id">
          <NuxtLink :to="`/merchants/${merchant.slug}`" class="merchant-card">
            <span class="merchant-card__avatar">
              <img v-if="merchant.avatar" :src="merchant.avatar" :alt="merchant.name" />
              <template v-else>{{ merchant.name.slice(0, 1) }}</template>
            </span>
            <span class="merchant-card__info">
              <b>{{ merchant.name }}</b>
              <span class="merchant-card__stats">
                {{ t('merchant.followers') }} {{ merchant.followers_total }} ｜
                {{ t('merchant.exposure') }} {{ merchant.exposure_total }}
              </span>
            </span>
            <span class="merchant-card__arrow">→</span>
          </NuxtLink>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.merchant-search {
  padding: 24px 0 48px;
}

.merchant-search__inner {
  max-width: 760px;
  margin: 0 auto;
  padding: 0 16px;
}

.merchant-search__title {
  font-size: 22px;
  margin: 0 0 16px;
}

.merchant-search__bar {
  display: flex;
  gap: 8px;
  margin-bottom: 24px;
}

.merchant-search__bar input {
  flex: 1;
  height: 40px;
  border: 1px solid #d5d9de;
  border-radius: 8px;
  padding: 0 12px;
  font: inherit;
}

.merchant-search__btn {
  height: 40px;
  padding: 0 20px;
  border: 0;
  border-radius: 8px;
  background: #e1251b;
  color: #fff;
  font: inherit;
  cursor: pointer;
}

.merchant-search__hint {
  color: #707070;
  font-size: 14px;
}

.merchant-search__hint--error {
  color: #e1251b;
}

.merchant-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.merchant-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #fff;
  text-decoration: none;
  color: inherit;
}

.merchant-card:hover {
  border-color: #e1251b;
}

.merchant-card__avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  overflow: hidden;
  background: #f2f3f5;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  flex: none;
}

.merchant-card__avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.merchant-card__info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.merchant-card__stats {
  font-size: 12px;
  color: #707070;
}

.merchant-card__arrow {
  margin-left: auto;
  color: #b0b0b0;
}
</style>
