<script setup>
import { computed } from 'vue'
import { useRouter } from '#imports'

import { useLocale } from '../../composables/useLocale'
import { useMarketLocale } from '../../composables/useMarketLocale'

// 语言 page (user screenshot: 更多 → 语言 rows with the current value).
const { t } = useLocale()
const { availableLocales, localeCode, setMarketLocale } = useMarketLocale()
const router = useRouter()

const options = computed(() =>
  (availableLocales.value || []).map((item) => ({
    code: item.code,
    label: item.name || item.label || item.code,
  })),
)

function back() {
  router.back()
}

function pick(code) {
  setMarketLocale(code)
  router.back()
}
</script>

<template>
  <div class="m-lang">
    <MobilePageHeader :title="t('mobile.drawer.language')" @back="back" />
    <div class="m-lang__list">
      <button
        v-for="option in options"
        :key="option.code"
        class="m-lang__row"
        type="button"
        :aria-pressed="localeCode === option.code"
        @click="pick(option.code)"
      >
        <span>{{ option.label }}</span>
        <svg
          v-if="localeCode === option.code"
          viewBox="0 0 24 24"
          width="18"
          height="18"
          aria-hidden="true"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <path d="m5 13 4 4L19 7" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </button>
    </div>
  </div>
</template>

<style scoped>
.m-lang__list {
  background: #ffffff;
}

.m-lang__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  min-height: 56px;
  padding: 0 16px;
  border: 0;
  border-bottom: 1px solid #f0f1f2;
  background: #ffffff;
  color: #1a1a1a;
  font: inherit;
  font-size: 16px;
  text-align: left;
  cursor: pointer;
}
</style>
