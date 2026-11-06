<script setup>
defineProps({
  // open 缺省为 true：老页面用外层 v-if 控制显隐（不传 open），
  // 新页面（CampaignCardsView）用 :open 传值，两种用法都成立。
  open: { type: Boolean, default: true },
  title: { type: String, default: '' },
  confirmText: { type: String, default: '确认' },
  busy: { type: Boolean, default: false },
})
const emit = defineEmits(['confirm', 'cancel'])
</script>

<template>
  <div v-if="open" class="modal-mask" role="presentation" @click.self="emit('cancel')">
    <section class="modal" role="dialog" aria-modal="true">
      <header class="modal__head">{{ title }}</header>
      <div class="modal__body">
        <slot />
      </div>
      <footer class="modal__foot">
        <button type="button" class="btn" :disabled="busy" @click="emit('cancel')">取消</button>
        <button type="button" class="btn btn--primary" :disabled="busy" @click="emit('confirm')">
          {{ busy ? '处理中…' : confirmText }}
        </button>
      </footer>
    </section>
  </div>
</template>
