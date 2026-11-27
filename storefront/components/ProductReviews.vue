<script setup>
import { computed, ref } from 'vue'
import { useFetch, useRuntimeConfig } from '#imports'

import { useLocale } from '../composables/useLocale'

// Reviews section for the product detail page: overview (average + star
// distribution), optional AI summary of the reviews, facets, pagination and
// local media viewer. Unknown/degraded media renders as a broken-image
// state, never as a page error.
const props = defineProps({
  productId: {
    type: String,
    required: true,
  },
  // AI 评价总结（Joybuy 布局：与左侧评分分布并排，位于评价区顶部）。
  aiSummary: {
    type: String,
    default: '',
  },
  // 商品详情接口的评分汇总：本地有评价时 count>0（source=local），
  // 爬虫商品回退到源站快照（source=crawler）。
  reviewSummary: {
    type: Object,
    default: null,
  },
})

const { t } = useLocale()

const config = useRuntimeConfig()
const activeRating = ref('')
const page = ref(1)

const baseUrl = computed(() =>
  import.meta.server
    ? `${config.apiBaseInternal}/products/${props.productId}/reviews`
    : `/api/v1/products/${props.productId}/reviews`,
)
const url = computed(() => {
  const search = new URLSearchParams()
  if (activeRating.value) search.set('rating', activeRating.value)
  if (page.value > 1) search.set('page', String(page.value))
  const query = search.toString()
  return query ? `${baseUrl.value}?${query}` : baseUrl.value
})

const { data } = await useFetch(url, {
  key: `reviews-${props.productId}-${activeRating.value}-${page.value}`,
})

const items = computed(() => (Array.isArray(data.value?.items) ? data.value.items : []))
const count = computed(() => data.value?.count ?? 0)
const totalPages = computed(() => data.value?.total_pages ?? 0)
const filteredTotal = computed(() => data.value?.filtered_total ?? count.value)
const distribution = computed(() => data.value?.distribution ?? {})

// 本地评价为空时使用详情接口带来的源站评分快照（评分/评价数/星级分布）。
const fallbackSummary = computed(() => props.reviewSummary || null)
const displayCount = computed(() => count.value || Number(fallbackSummary.value?.count || 0))
const displayDistribution = computed(() => {
  if (count.value) return distribution.value
  const value = fallbackSummary.value?.distribution
  return value && typeof value === 'object' ? value : {}
})
const displayAverage = computed(() => {
  if (count.value) return Number(data.value?.average || 0)
  return Number(fallbackSummary.value?.average || 0)
})

function barWidth(star) {
  const total = displayCount.value
  if (!total) return 0
  const value = Number(displayDistribution.value[String(star)] || 0)
  return Math.round((value / total) * 100)
}

const averageText = computed(() => {
  const average = displayAverage.value
  return average ? average.toFixed(1) : '—'
})

function filterBy(rating) {
  activeRating.value = activeRating.value === rating ? '' : rating
  page.value = 1
}

function goToPage(next) {
  if (next >= 1 && (totalPages.value === 0 || next <= totalPages.value)) {
    page.value = next
  }
}
</script>

<template>
  <!-- 无评分且无 AI 摘要时整块不渲染；只有 AI 摘要（爬虫商品无本地评价）也要展示。 -->
  <section
    v-if="displayCount > 0 || aiSummary"
    id="reviews"
    class="reviews"
    aria-labelledby="reviews-heading"
  >
    <h2 id="reviews-heading" class="reviews__heading">{{ t('reviews.heading') }}</h2>

    <div class="reviews__overview" :class="{ 'reviews__overview--ai-only': displayCount === 0 }">
      <div v-if="displayCount > 0" class="reviews__stats">
        <div class="reviews__score">
          <p class="reviews__average">{{ averageText }}</p>
          <span class="reviews__stars" aria-hidden="true">
            <svg
              v-for="star in 5"
              :key="star"
              class="reviews__star"
              :class="{ 'reviews__star--filled': star <= Math.round(displayAverage) }"
              viewBox="0 0 20 20"
            >
              <path
                d="M10 1.6l2.5 5.2 5.7.8-4.1 4 1 5.6-5.1-2.7-5.1 2.7 1-5.6-4.1-4 5.7-.8z"
                fill="currentColor"
              />
            </svg>
          </span>
          <p class="reviews__count">{{ displayCount }} {{ t('reviews.countSuffix') }}</p>
        </div>

        <div class="reviews__distribution" role="group" :aria-label="t('reviews.filterLabel')">
          <button
            v-for="star in [5, 4, 3, 2, 1]"
            :key="star"
            type="button"
            class="reviews__dist-row"
            :class="{ 'reviews__dist-row--active': activeRating === String(star) }"
            :aria-pressed="activeRating === String(star)"
            @click="filterBy(String(star))"
          >
            <span class="reviews__dist-label">{{ star }}</span>
            <span class="reviews__dist-track" aria-hidden="true">
              <span class="reviews__dist-fill" :style="{ width: `${barWidth(star)}%` }"></span>
            </span>
            <span class="reviews__dist-count">{{ displayDistribution[String(star)] || 0 }}</span>
          </button>
        </div>
      </div>

      <aside v-if="aiSummary" class="reviews__ai" :aria-label="t('reviews.aiSummary')">
        <h3 class="reviews__ai-title">{{ t('reviews.aiSummary') }}</h3>
        <p class="reviews__ai-text">{{ aiSummary }}</p>
      </aside>
    </div>

    <p v-if="filteredTotal !== count" class="reviews__filtered" role="status">
      Showing {{ filteredTotal }} of {{ count }} reviews.
    </p>

    <ul v-if="items.length > 0" class="reviews__list">
      <li v-for="review in items" :key="review.public_id" class="review">
        <header class="review__head">
          <span class="review__stars" aria-hidden="true">
            <span v-for="star in 5" :key="star" :class="{ filled: star <= review.rating }">★</span>
          </span>
          <span class="visually-hidden">{{ review.rating }} out of 5 stars</span>
          <strong class="review__title">{{ review.title || 'Review' }}</strong>
        </header>
        <p class="review__meta">
          {{ review.display_name }}
          <template v-if="review.reviewed_at">
            · {{ new Date(review.reviewed_at).toLocaleDateString('en-GB') }}
          </template>
          <template v-if="review.variant_text"> · {{ review.variant_text }}</template>
        </p>
        <p class="review__body">{{ review.body }}</p>

        <div v-if="review.media.length > 0" class="review__media">
          <figure v-for="(item, index) in review.media" :key="index">
            <img
              v-if="item.kind === 'IMAGE'"
              :src="item.url"
              :alt="`Review image ${index + 1}`"
              loading="lazy"
              @error="item.failed = true"
            />
            <video v-else-if="item.kind === 'VIDEO'" :src="item.url" controls preload="none" />
            <span v-if="item.failed" class="review__media-failed">{{
              t('reviews.mediaUnavailable')
            }}</span>
          </figure>
        </div>
      </li>
    </ul>

    <p v-else-if="!aiSummary && count > 0" class="reviews__empty" role="status">
      No reviews yet{{ activeRating ? ' for this star rating' : '' }}.
    </p>

    <nav v-if="totalPages > 1" class="reviews__pagination" aria-label="Reviews pagination">
      <button type="button" :disabled="page <= 1" @click="goToPage(page - 1)">
        {{ t('pagination.previous') }}
      </button>
      <span>Page {{ page }} of {{ totalPages }}</span>
      <button type="button" :disabled="page >= totalPages" @click="goToPage(page + 1)">
        {{ t('pagination.next') }}
      </button>
    </nav>
  </section>
</template>

<style scoped>
/* 需求 22.1-2：评价区按真站实测（customer-reviews-box）——整块无外框/圆角，
   上方一条分隔线，内边距 20px 8px 16px；标题 24px/600 line-height 26。 */
.reviews {
  margin-block: 0;
  padding: 20px 8px 16px;
  border-top: 1px solid #f0f1f2;
  background: var(--colour-surface);
}

.reviews__heading {
  margin: 0 0 16px;
  font-size: 24px;
  font-weight: 600;
  line-height: 26px;
  color: #1a1a1a;
}

/* Joybuy 布局：左侧评分卡（736px），右侧 AI 评价总结（736px），gap 24。 */
.reviews__overview {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 24px;
  margin-top: 0;
}

.reviews__overview--ai-only {
  grid-template-columns: minmax(0, 1fr);
}

/* 评分卡：1px #F0F1F2、radius 12、padding 20，内部 gap 32。 */
.reviews__stats {
  display: flex;
  min-width: 0;
  gap: 32px;
  padding: 20px;
  border: 1px solid #f0f1f2;
  border-radius: 12px;
}

.reviews__score {
  flex: none;
  width: 100px;
}

.reviews__average {
  margin: 0;
  color: #1a1a1a;
  font-size: 32px;
  font-weight: 700;
  line-height: 40px;
}

.reviews__stars {
  display: flex;
  align-items: center;
  height: 16px;
  margin-top: 4px;
  color: #d17d00;
}

.reviews__star {
  width: 13px;
  height: 13px;
  margin-right: 2px;
  color: #e5e7eb;
}

.reviews__star--filled {
  color: #d17d00;
}

.reviews__count {
  margin: 8px 0 0;
  color: #6e7078;
  font-size: 14px;
  font-weight: 500;
  line-height: 20px;
}

.reviews__distribution {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
  gap: 8px;
  margin-top: 0;
}

/* 分布行：高 22、18/1fr/auto 三列、列间距 16，无多余内边距。
   2026-11-27 去截断：末列由固定 24px 改为 auto，三位数评价数（如 402）
   不再溢出或被挤压，完整展示。 */
.reviews__dist-row {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) auto;
  align-items: center;
  gap: 16px;
  height: 22px;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: none;
  color: #1a1a1a;
  cursor: pointer;
  font-size: 16px;
  line-height: 22px;
  text-align: left;
}

.reviews__dist-row:hover .reviews__dist-fill {
  background: #b96f00;
}

.reviews__dist-row--active {
  color: #d17d00;
  font-weight: 600;
}

.reviews__dist-label {
  white-space: nowrap;
}

.reviews__dist-track {
  height: 6px;
  overflow: hidden;
  border-radius: 999px;
  background: #f5f6fa;
}

.reviews__dist-fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: #d17d00;
}

.reviews__dist-count {
  color: #6e7078;
  text-align: right;
  white-space: nowrap;
}

/* AI 总结：真站无卡片（无背景/边框/圆角/内边距），正文 16px/500 lh22，
   说明文字 14px/500 #6E7078 lh20。 */
.reviews__ai {
  display: flex;
  flex-direction: column;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: none;
}

.reviews__ai-title {
  margin: 0;
  color: #6e7078;
  font-size: 14px;
  font-weight: 500;
  line-height: 20px;
}

.reviews__ai-text {
  margin: 0 0 8px;
  color: #1a1a1a;
  font-size: 16px;
  font-weight: 500;
  line-height: 22px;
  white-space: pre-line;
  order: -1;
}

.reviews__filtered {
  margin-top: var(--space-3);
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}

.reviews__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  margin-top: var(--space-6);
}

.review {
  border-top: 1px solid var(--colour-border);
  padding-top: var(--space-4);
}

.review__head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.review__stars .filled {
  color: var(--colour-star);
}

.review__meta {
  margin-top: var(--space-1);
  color: var(--colour-muted);
  font-size: var(--font-size-sm);
}

.review__body {
  margin-top: var(--space-2);
  color: var(--colour-text-secondary);
}

.review__media {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-3);
}

.review__media img,
.review__media video {
  width: 96px;
  height: 96px;
  object-fit: cover;
  border-radius: var(--radius-md);
  border: 1px solid var(--colour-border);
}

.review__media-failed {
  color: var(--colour-muted);
  font-size: var(--font-size-xs);
}

.reviews__empty {
  margin-top: var(--space-6);
  color: var(--colour-muted);
}

.reviews__pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  margin-top: var(--space-6);
}

.reviews__pagination button {
  min-height: 44px;
  padding: 0 var(--space-5);
  border: 1px solid var(--colour-border-strong);
  border-radius: var(--radius-md);
  background: var(--colour-surface);
  cursor: pointer;
  font-weight: var(--font-weight-semibold);
}

.reviews__pagination button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

@media (max-width: 64rem) {
  .reviews__overview {
    grid-template-columns: minmax(0, 1fr);
    gap: 24px;
  }

  .reviews__stats {
    gap: 20px;
  }
}
</style>
