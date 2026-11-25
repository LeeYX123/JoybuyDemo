<script setup>
// 活动页 / 店铺页的视频模块（2026-11-26，真站店铺页 banner 下方同款）：
// 静音自动播放 + 循环，带原生控件（进度条 / 播放暂停 / 音量 / 时间）。
defineProps({
  src: {
    type: String,
    required: true,
  },
  poster: {
    type: String,
    default: '',
  },
})

</script>

<template>
  <div class="activity-video">
    <video
      class="activity-video__el"
      :src="src"
      :poster="poster || undefined"
      autoplay
      loop
      muted
      playsinline
      controls
      preload="metadata"
    ></video>
  </div>
</template>

<style scoped>
.activity-video {
  background: #000;
}

.activity-video__el {
  display: block;
  width: 100%;
  height: auto;
}
</style>
