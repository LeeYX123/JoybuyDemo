<script setup>
import { useLocale } from '../../composables/useLocale'

// Simple prev/next pager, same visual language as the existing favourites
// pagination (49px targets, white buttons, centred summary).
defineProps({
  page: {
    type: Number,
    required: true,
  },
  totalPages: {
    type: Number,
    required: true,
  },
})

const emit = defineEmits(['change'])
const { t } = useLocale()
</script>

<template>
  <nav v-if="totalPages > 1" class="account-pager" :aria-label="t('pagination.label')">
    <button
      class="account-pager__btn"
      type="button"
      :disabled="page <= 1"
      @click="emit('change', page - 1)"
    >
      {{ t('pagination.previous') }}
    </button>
    <span class="account-pager__summary">
      {{ t('pagination.pageOf').replace('{page}', page).replace('{total}', totalPages) }}
    </span>
    <button
      class="account-pager__btn"
      type="button"
      :disabled="page >= totalPages"
      @click="emit('change', page + 1)"
    >
      {{ t('pagination.next') }}
    </button>
  </nav>
</template>

<style scoped>
.account-pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  margin-top: var(--space-6);
}

.account-pager__btn {
  min-height: 44px;
  padding: 0 var(--space-4);
  border: 1px solid var(--colour-border-strong);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  color: var(--colour-text);
  cursor: pointer;
}

.account-pager__btn:hover:not(:disabled) {
  background: var(--colour-surface-muted);
}

.account-pager__btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.account-pager__summary {
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}
</style>
