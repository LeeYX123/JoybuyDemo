<script setup>
import { watch } from 'vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '' },
})

const emit = defineEmits(['close'])

// 打开时锁 body 滚动（folio：body.business-dialog-open）。
watch(
  () => props.open,
  (open) => {
    document.body.classList.toggle('m-sheet-locked', open)
  },
)
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="m-sheet-back" @click="emit('close')">
      <div
        class="m-sheet"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
        @click.stop
      >
        <div class="m-sheet__head">
          <h2>{{ title }}</h2>
          <button type="button" aria-label="关闭" @click="emit('close')">×</button>
        </div>
        <div class="m-sheet__body">
          <slot />
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style>
/* Teleport 到 body，样式不能 scoped。关闭时也要解锁滚动。 */
body.m-sheet-locked {
  overflow: hidden;
}
</style>

<style scoped>
.m-sheet-back {
  position: fixed;
  inset: 0;
  z-index: 40;
  display: grid;
  align-items: end;
  justify-items: center;
  background: rgb(17 27 50 / 63%);
}

.m-sheet {
  width: min(100%, 390px);
  max-height: min(85dvh, calc(100dvh - 16px));
  overflow: auto;
  border-radius: var(--m-sheet-radius) var(--m-sheet-radius) 0 0;
  background: var(--m-paper);
  padding-bottom: max(var(--m-space-4), env(safe-area-inset-bottom));
}

.m-sheet__head {
  position: sticky;
  top: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--m-space-2);
  padding: var(--m-space-4) var(--m-space-4) var(--m-space-3);
  background: var(--m-paper);
  border-bottom: 1px solid var(--m-line);
}

.m-sheet__head h2 {
  margin: 0;
  font-size: 16px;
  color: var(--m-ink);
}

.m-sheet__head button {
  flex: 0 0 var(--m-target);
  width: var(--m-target);
  height: var(--m-target);
  margin-right: -8px;
  border: 0;
  background: transparent;
  color: var(--m-muted);
  font-size: 24px;
  cursor: pointer;
}

.m-sheet__body {
  padding: var(--m-space-4);
}
</style>
