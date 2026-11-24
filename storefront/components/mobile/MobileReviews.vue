<script setup>
import { useLocale } from '../../composables/useLocale'

// Mobile reviews (docs/20 §5.6, user decision): review semantics only — the
// page header is 我的评价 (mobile.reviews.title, NOT the desktop "Reviews and
// Q&A") with two tabs (to review / reviewed). The buyer-review API is not
// implemented in this repo, so the panel body is the honest empty state from
// the desktop page (reviews.empty). No Q&A tab by design.
defineProps({
  tabs: { type: Array, default: () => [] },
  activeTab: { type: String, default: 'to_review' },
})

const emit = defineEmits(['tab', 'back'])

const { t } = useLocale()
</script>

<template>
  <div class="m-reviews">
    <MobilePageHeader :title="t('mobile.reviews.title')" @back="emit('back')" />

    <!-- Tab row (docs/20 §0: 16px selected 700 + 2px black underline). -->
    <nav class="m-reviews__tabs" :aria-label="t('account.tabs')">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="m-reviews__tab"
        :class="{ 'm-reviews__tab--active': tab.key === activeTab }"
        type="button"
        @click="emit('tab', tab.key)"
      >
        {{ tab.label }}
      </button>
    </nav>

    <!-- Empty state: same copy as the desktop reviews.empty. -->
    <div class="m-reviews__empty" role="status">
      <p class="m-reviews__empty-text">{{ t('reviews.empty') }}</p>
    </div>
  </div>
</template>

<style scoped>
.m-reviews {
  min-height: 60vh;
  padding-bottom: 24px;
  background: #f5f6fa;
}

.m-reviews__tabs {
  display: flex;
  background: #ffffff;
  border-bottom: 1px solid #f0f1f2;
}

.m-reviews__tab {
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

.m-reviews__tab--active {
  font-weight: var(--font-weight-bold);
  border-bottom-color: #1a1a1a;
}

.m-reviews__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin: 24px 16px;
  padding: 40px 16px;
  border-radius: 12px;
  background: #ffffff;
}

.m-reviews__empty-text {
  margin: 0;
  color: #1a1a1a;
  font-size: 16px;
  font-weight: var(--font-weight-semibold);
}
</style>
