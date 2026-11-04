<script setup>
const props = defineProps({
  variant: {
    type: String,
    default: 'primary', // primary | secondary | ghost
    validator: (value) => ['primary', 'secondary', 'ghost'].includes(value),
  },
  size: {
    type: String,
    default: 'md', // md | lg
    validator: (value) => ['md', 'lg'].includes(value),
  },
  disabled: {
    type: Boolean,
    default: false,
  },
  type: {
    type: String,
    default: 'button',
    validator: (value) => ['button', 'submit', 'reset'].includes(value),
  },
})

const emit = defineEmits(['click'])

function handleClick(event) {
  if (!props.disabled) {
    emit('click', event)
  }
}
</script>

<template>
  <button
    class="base-button"
    :class="[`base-button--${props.variant}`, `base-button--${props.size}`]"
    :type="props.type"
    :disabled="props.disabled"
    @click="handleClick"
  >
    <slot />
  </button>
</template>

<style scoped>
.base-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  min-height: 44px;
  padding: 0 var(--space-5);
  border: 1px solid transparent;
  border-radius: var(--radius-pill);
  cursor: pointer;
  font-weight: var(--font-weight-semibold);
  transition:
    background var(--transition-fast),
    border-color var(--transition-fast);
}

.base-button--lg {
  min-height: 48px;
  padding: 0 var(--space-8);
  font-size: var(--font-size-lg);
}

.base-button--primary {
  color: var(--colour-white);
  background: var(--colour-accent);
}

.base-button--primary:hover:not(:disabled) {
  background: var(--colour-accent-dark);
}

.base-button--secondary {
  color: var(--colour-text);
  border-color: var(--colour-border-strong);
  background: var(--colour-surface);
}

.base-button--secondary:hover:not(:disabled) {
  background: var(--colour-surface-muted);
}

.base-button--ghost {
  color: var(--colour-accent);
  background: transparent;
}

.base-button--ghost:hover:not(:disabled) {
  background: var(--colour-accent-soft);
}

.base-button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
</style>
