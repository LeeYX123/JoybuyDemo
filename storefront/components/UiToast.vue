<script setup>
import { useLocale } from '../composables/useLocale'
import { useUiToast } from '../composables/useUiToast'

// Global, non-blocking feedback stack. `aria-live="polite"` announces the
// message; the visual toast is dismissed automatically by the composable.
const { t } = useLocale()
const { toasts, dismiss } = useUiToast()
</script>

<template>
  <div class="ui-toasts" aria-live="polite" aria-atomic="false">
    <div
      v-for="toast in toasts"
      :key="toast.id"
      class="ui-toast"
      :class="`ui-toast--${toast.type}`"
      role="status"
    >
      <span class="ui-toast__message">{{ toast.message }}</span>
      <button
        class="ui-toast__close"
        type="button"
        :aria-label="t('common.dismiss')"
        @click="dismiss(toast.id)"
      >
        ×
      </button>
    </div>
  </div>
</template>

<style scoped>
.ui-toasts {
  position: fixed;
  right: var(--space-4);
  bottom: var(--space-4);
  z-index: var(--z-skip-link);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  width: min(24rem, calc(100vw - 2rem));
  pointer-events: none;
}

.ui-toast {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--colour-border);
  border-radius: var(--radius-md);
  background: var(--colour-text);
  color: var(--colour-white);
  box-shadow: var(--shadow-overlay);
  pointer-events: auto;
  font-size: var(--font-size-md);
}

.ui-toast--error {
  background: var(--colour-error);
  border-color: var(--colour-error);
}

.ui-toast--success {
  background: var(--colour-success);
  border-color: var(--colour-success);
}

.ui-toast__message {
  flex: 1;
}

.ui-toast__close {
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font-size: 1.125rem;
  line-height: 1;
}
</style>
