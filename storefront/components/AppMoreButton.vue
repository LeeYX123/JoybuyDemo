<script setup>
// 全站黑底【更多 / 查看更多】按钮（需求文档03 14.3 + 16.4 共用一份规格）。
// 首页【精选好物】与频道页底部【精选好物】都用它渲染，避免两处各写一套
// 魔法值（#1A1A1A 底、白字、131×48、radius 4、16px/500）。
defineProps({
  disabled: {
    type: Boolean,
    default: false,
  },
})
</script>

<template>
  <button class="app-more-btn" type="button" :disabled="disabled">
    <slot />
  </button>
</template>

<style scoped>
.app-more-btn {
  min-width: 131px;
  height: 48px;
  padding: 0 24px;
  border: 0;
  border-radius: 4px;
  background: #1a1a1a;
  color: #fff;
  font: inherit;
  font-size: 16px;
  font-weight: 500;
  line-height: 48px;
  cursor: pointer;
}

.app-more-btn:hover:not(:disabled) {
  background: #333;
}

.app-more-btn:disabled {
  cursor: progress;
  opacity: 0.65;
}
</style>
