<script setup>
// 活动页 / 店铺页加载骨架（2026-11-26）。
//
// 背景：慢网络下从首页点卡片进 /active、/store 时，客户端导航会先渲染一帧
// 「This page is not available」再跳到内容（用户反馈）。原因是 useFetch 的
// pending 阶段 page 为空，页面把「未拿到数据」当成「页面不存在」。
// 这里用与真实布局同尺寸的骨架占位，pending 结束后再切内容/降级态。
//
// 形状对齐 ActivityPageView：店铺页黑条 + hero + 楼层标题 + 5 列商品卡。
import { useLocale } from '../../composables/useLocale'

const props = defineProps({
  kind: {
    type: String,
    default: 'activity',
  },
})

const { t } = useLocale()
</script>

<template>
  <div class="activity-skeleton" role="status" aria-busy="true" :aria-label="t('activity.loading')">
    <div v-if="props.kind === 'store'" class="activity-skeleton__store-bar">
      <span class="activity-skeleton__store-logo shimmer" />
      <span class="activity-skeleton__store-name shimmer" />
    </div>

    <div class="activity-skeleton__inner">
      <div class="activity-skeleton__hero shimmer" />

      <section v-for="floor in 2" :key="floor" class="activity-skeleton__floor">
        <div class="activity-skeleton__title shimmer" />
        <ul class="activity-skeleton__grid">
          <li v-for="card in 5" :key="card" class="activity-skeleton__card">
            <span class="activity-skeleton__media shimmer" />
            <span class="activity-skeleton__line shimmer" />
            <span class="activity-skeleton__line activity-skeleton__line--short shimmer" />
            <span class="activity-skeleton__price shimmer" />
          </li>
        </ul>
      </section>
    </div>

    <span class="activity-skeleton__sr">{{ t('activity.loading') }}</span>
  </div>
</template>

<style scoped>
.activity-skeleton {
  /* 与真实页面同口径：内容区 1224 居中、上方与 header 无缝。 */
  --skeleton-gap: 24px;
  margin-block-start: 0;
  padding-bottom: var(--space-8);
  background: #fff;
}

.activity-skeleton__store-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  height: 72px;
  padding-inline: max(24px, calc((100vw - 1224px) / 2));
  background: #1a1a1a;
}

.activity-skeleton__store-logo {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: rgb(255 255 255 / 22%);
}

.activity-skeleton__store-name {
  width: 180px;
  height: 18px;
  border-radius: 4px;
  background: rgb(255 255 255 / 22%);
}

.activity-skeleton__inner {
  width: min(1224px, 100% - 48px);
  margin-inline: auto;
}

.activity-skeleton__hero {
  width: 100%;
  aspect-ratio: 1224 / 360;
  margin-top: 24px;
  border-radius: 8px;
  background: #f1f2f4;
}

.activity-skeleton__floor {
  margin-top: 32px;
}

.activity-skeleton__title {
  width: 240px;
  height: 26px;
  margin: 0 auto 20px;
  border-radius: 4px;
  background: #f1f2f4;
}

.activity-skeleton__grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 24px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.activity-skeleton__card {
  display: block;
  padding: 12px;
  border: 1px solid #f0f0f0;
  border-radius: 12px;
}

.activity-skeleton__media {
  display: block;
  width: 100%;
  aspect-ratio: 1 / 1;
  border-radius: 8px;
  background: #f1f2f4;
}

.activity-skeleton__line {
  display: block;
  width: 100%;
  height: 12px;
  margin-top: 12px;
  border-radius: 4px;
  background: #f1f2f4;
}

.activity-skeleton__line--short {
  width: 62%;
}

.activity-skeleton__price {
  display: block;
  width: 40%;
  height: 18px;
  margin-top: 12px;
  border-radius: 4px;
  background: #f1f2f4;
}

/* 一次性的高光扫过，避免长时间静止看着像卡死。 */
.shimmer {
  position: relative;
  overflow: hidden;
}

.shimmer::after {
  content: '';
  position: absolute;
  inset: 0;
  transform: translateX(-100%);
  background: linear-gradient(90deg, transparent, rgb(255 255 255 / 62%), transparent);
  animation: activity-skeleton-sweep 1.4s infinite;
}

@keyframes activity-skeleton-sweep {
  100% {
    transform: translateX(100%);
  }
}

.activity-skeleton__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

@media (prefers-reduced-motion: reduce) {
  .shimmer::after {
    animation: none;
  }
}

@media (max-width: 900px) {
  .activity-skeleton__inner {
    width: min(100% - 24px, 720px);
  }

  .activity-skeleton__grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;
  }

  .activity-skeleton__hero {
    aspect-ratio: 4 / 3;
  }

  .activity-skeleton__title {
    width: 180px;
    height: 22px;
  }
}
</style>
