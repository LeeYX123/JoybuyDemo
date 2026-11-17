<script setup>
import { useLocale } from '../../composables/useLocale'

// Honest empty state used by orders/returns/reviews/addresses. The artwork is
// a local inline SVG (no CDN, no fabricated data), matching the grey pin +
// red dot placeholder on joybuy.co.uk/profile/my-address.
defineProps({
  message: {
    type: String,
    required: true,
  },
  note: {
    type: String,
    default: '',
  },
  compact: {
    type: Boolean,
    default: false,
  },
})

const { t } = useLocale()
</script>

<template>
  <div class="account-empty" :class="{ 'account-empty--compact': compact }" role="status">
    <svg
      class="account-empty__art"
      viewBox="0 0 120 96"
      width="120"
      height="96"
      role="img"
      :aria-label="t('account.emptyArtwork')"
    >
      <ellipse cx="60" cy="82" rx="42" ry="8" fill="#eef1f5" />
      <path
        d="M60 14c-13.3 0-24 10.4-24 23.3 0 17.2 24 40.7 24 40.7s24-23.5 24-40.7C84 24.4 73.3 14 60 14Z"
        fill="#d9dee5"
      />
      <circle cx="60" cy="37" r="9" fill="#f6f7f9" />
      <circle cx="83" cy="22" r="9" fill="#c8102e" />
      <path d="M83 18.5v4.5m0 3v.6" stroke="#fff" stroke-width="1.8" stroke-linecap="round" />
      <path d="M32 58c6-4 12-6 18-7" stroke="#c2c4cc" stroke-width="2" fill="none" />
      <path d="M88 58c-6-4-12-6-18-7" stroke="#c2c4cc" stroke-width="2" fill="none" />
    </svg>
    <p class="account-empty__message">{{ message }}</p>
    <p v-if="note" class="account-empty__note">{{ note }}</p>
  </div>
</template>

<style scoped>
.account-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  /* 真实站地址页空态区域高 394px（面板总高 522，标题/标签/内边距固定）。 */
  min-height: 24.625rem;
  padding: var(--space-8) var(--space-4);
  text-align: center;
}

.account-empty--compact {
  min-height: 12rem;
  padding: var(--space-6) var(--space-4);
}

.account-empty__message {
  margin: 0;
  color: var(--colour-text-secondary);
  font-size: var(--font-size-md);
}

.account-empty__note {
  max-width: 34rem;
  margin: 0;
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
  line-height: var(--line-height-normal);
}
</style>
