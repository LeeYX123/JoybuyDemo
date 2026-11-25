<script setup>
// 活动页 / 店铺页的轮播 banner（2026-11-26，真站店铺页顶部同款）：
// 每 5s 自动切换，鼠标移入显示左右箭头并暂停，底部小圆点指示当前页。
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({
  images: {
    type: Array,
    default: () => [],
  },
  interval: {
    type: Number,
    default: 5000,
  },
})

const current = ref(0)
const hovering = ref(false)
let timer = null

const total = computed(() => props.images.length)

function go(index) {
  if (!total.value) return
  current.value = (index + total.value) % total.value
}

function next() {
  go(current.value + 1)
}

function prev() {
  go(current.value - 1)
}

function start() {
  stop()
  if (total.value > 1) {
    timer = setInterval(() => {
      if (!hovering.value) next()
    }, props.interval)
  }
}

function stop() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

onMounted(start)
onBeforeUnmount(stop)
</script>

<template>
  <div
    v-if="total"
    class="activity-carousel"
    @mouseenter="hovering = true"
    @mouseleave="hovering = false"
  >
    <div class="activity-carousel__track" :style="{ transform: `translateX(-${current * 100}%)` }">
      <img
        v-for="(image, index) in images"
        :key="image + index"
        class="activity-carousel__img"
        :src="image"
        alt=""
        loading="lazy"
      />
    </div>

    <template v-if="total > 1">
      <button
        v-show="hovering"
        type="button"
        class="activity-carousel__arrow activity-carousel__arrow--prev"
        aria-label="Previous"
        @click="prev"
      >
        ‹
      </button>
      <button
        v-show="hovering"
        type="button"
        class="activity-carousel__arrow activity-carousel__arrow--next"
        aria-label="Next"
        @click="next"
      >
        ›
      </button>
      <div class="activity-carousel__dots">
        <button
          v-for="(image, index) in images"
          :key="'dot-' + index"
          type="button"
          class="activity-carousel__dot"
          :class="{ 'activity-carousel__dot--active': index === current }"
          :aria-label="`Slide ${index + 1}`"
          @click="go(index)"
        ></button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.activity-carousel {
  position: relative;
  overflow: hidden;
  background: #f5f5f5;
}

.activity-carousel__track {
  display: flex;
  transition: transform 420ms ease;
}

.activity-carousel__img {
  display: block;
  flex: 0 0 100%;
  width: 100%;
  height: auto;
}

.activity-carousel__arrow {
  position: absolute;
  top: 50%;
  translate: 0 -50%;
  width: 44px;
  height: 44px;
  border: 0;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.45);
  color: #fff;
  font-size: 26px;
  line-height: 1;
  cursor: pointer;
}

.activity-carousel__arrow--prev {
  left: 16px;
}

.activity-carousel__arrow--next {
  right: 16px;
}

.activity-carousel__arrow:hover {
  background: rgba(0, 0, 0, 0.7);
}

.activity-carousel__dots {
  position: absolute;
  left: 50%;
  bottom: 12px;
  translate: -50% 0;
  display: flex;
  gap: 6px;
}

.activity-carousel__dot {
  width: 8px;
  height: 8px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.55);
  cursor: pointer;
}

.activity-carousel__dot--active {
  background: #fff;
}
</style>
