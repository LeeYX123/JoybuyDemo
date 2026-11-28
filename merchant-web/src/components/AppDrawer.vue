<script setup>
defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '' },
  wide: { type: Boolean, default: false },
})
const emit = defineEmits(['close'])
</script>

<template>
  <div v-if="open" class="drawer-mask" role="presentation" @click.self="emit('close')">
    <section class="drawer" :class="{ 'drawer--wide': wide }" role="dialog" aria-modal="true">
      <header class="drawer__head">
        <h2>{{ title }}</h2>
        <button type="button" class="btn btn--sm" @click="emit('close')">关闭</button>
      </header>
      <div class="drawer__body">
        <slot />
      </div>
      <footer v-if="$slots.footer" class="drawer__foot">
        <slot name="footer" />
      </footer>
    </section>
  </div>
</template>
