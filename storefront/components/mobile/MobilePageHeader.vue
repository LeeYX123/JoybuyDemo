<script setup>
import { useLocale } from '../../composables/useLocale'

// Sub-page title row with a back arrow (real m. site sub-pages: centred
// 17px/700 title, back chevron on the left). Sits below the mobile shell
// header on settings/language/toggle pages.
defineProps({
  title: {
    type: String,
    required: true,
  },
})

const emit = defineEmits(['back'])
const { t } = useLocale()
</script>

<template>
  <div class="m-page-head">
    <button
      class="m-page-head__back"
      type="button"
      :aria-label="t('mobile.drawer.back')"
      @click="emit('back')"
    >
      <svg
        viewBox="0 0 24 24"
        width="22"
        height="22"
        aria-hidden="true"
        fill="none"
        stroke="currentColor"
        stroke-width="1.8"
      >
        <path d="M15 5l-7 7 7 7" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>
    <h1 class="m-page-head__title">{{ title }}</h1>
    <span class="m-page-head__spacer" aria-hidden="true"></span>
  </div>
</template>

<style scoped>
.m-page-head {
  display: flex;
  align-items: center;
  height: 48px;
  padding: 0 12px;
  background: #ffffff;
  border-bottom: 1px solid #f0f1f2;
}

.m-page-head__back {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #1a1a1a;
  cursor: pointer;
}

.m-page-head__title {
  flex: 1;
  margin: 0;
  color: #1a1a1a;
  font-size: 17px;
  font-weight: var(--font-weight-bold);
  text-align: center;
}

.m-page-head__spacer {
  width: 32px;
}
</style>
