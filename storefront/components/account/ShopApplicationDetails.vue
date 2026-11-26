<script setup>
import { computed } from 'vue'

import { useLocale } from '../../composables/useLocale'

// 申请开店 / 待审核 / 已通过 / 未通过 共用的「申请信息」回显列表。
// 视觉依据：申请开店页面/待审核-电脑版.html 与 待审核-手机版.html 的
// `.panel.details`（两列 dl，label 列 minmax(98px,42%)，行高 54px，
// 分隔线 1px #dce0e7，最后两行（手机版只有最后一行）不画线）。
// 桌面/手机端只有容器内边距不同，由调用方的 class 控制。
const props = defineProps({
  application: { type: Object, default: null },
  documentTypeLabel: { type: String, default: '—' },
  statusLabel: { type: String, default: '' },
  showStatus: { type: Boolean, default: false },
  showReviewedAt: { type: Boolean, default: false },
  mobile: { type: Boolean, default: false },
})

const { t } = useLocale()

function formatTime(value) {
  if (!value) return '—'
  return String(value).replace('T', ' ').slice(0, 16)
}

// 待审核态字段顺序与设计稿一致：logo → 用户名字 → 店铺名称 → 手机号码 →
// 个人证件 → 个人居住地址 → 邀请码 → 申请时间；已通过/未通过额外追加
// 状态与审核时间（设计稿只覆盖待审核，这两行保留旧版信息）。
const rows = computed(() => {
  const app = props.application || {}
  const list = [
    {
      key: 'logo',
      label: t('shopApply.shopLogo'),
      required: true,
      kind: 'logo',
      image: app.logo_image_url || '',
    },
    {
      key: 'user',
      label: t('shopApply.userName'),
      required: true,
      value: app.user_name,
    },
    {
      key: 'shop',
      label: t('shopApply.shopName'),
      required: true,
      value: app.shop_name,
    },
    {
      key: 'phone',
      label: t('shopApply.phone'),
      required: true,
      value: app.phone,
    },
    {
      key: 'doc',
      label: t('shopApply.idDocument'),
      required: true,
      value: props.documentTypeLabel,
      kind: 'doc',
      image: app.id_document_image_url || '',
    },
    {
      key: 'address',
      label: t('shopApply.residentialAddress'),
      required: true,
      value: app.residential_address,
    },
    {
      key: 'referrer',
      label: t('shopApply.referrerCode'),
      value: app.referrer_code,
    },
    {
      key: 'submitted',
      label: t('shopApply.submittedAt'),
      value: formatTime(app.submitted_at),
    },
  ]
  if (props.showStatus && props.statusLabel) {
    list.push({ key: 'status', label: t('shopApply.statusLabel'), value: props.statusLabel })
  }
  if (props.showReviewedAt) {
    list.push({
      key: 'reviewed',
      label: t('shopApply.reviewedAt'),
      value: formatTime(app.reviewed_at),
    })
  }
  return list
})
</script>

<template>
  <dl class="shop-details" :class="{ 'shop-details--mobile': mobile }">
    <div v-for="row in rows" :key="row.key" class="shop-details__row">
      <dt class="shop-details__label">
        {{ row.label }}<b v-if="row.required" class="shop-details__req" aria-hidden="true">*</b>
      </dt>
      <dd class="shop-details__value">
        <template v-if="row.kind === 'logo'">
          <img v-if="row.image" class="shop-details__thumb" :src="row.image" :alt="row.label" />
          <span v-else class="shop-details__thumb" aria-hidden="true">
            <svg
              viewBox="0 0 24 24"
              width="18"
              height="18"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
            >
              <rect x="4" y="4" width="16" height="16" rx="2" />
              <rect x="8" y="8" width="8" height="8" rx="1" />
            </svg>
          </span>
        </template>
        <template v-else-if="row.kind === 'doc'">
          <span class="shop-details__doc-type">{{ row.value }}</span>
          <img
            v-if="row.image"
            class="shop-details__thumb shop-details__thumb--doc"
            :src="row.image"
            :alt="t('shopApply.idDocumentImage')"
          />
          <span v-else class="shop-details__thumb shop-details__thumb--doc" aria-hidden="true">
            <svg
              viewBox="0 0 24 24"
              width="18"
              height="18"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
            >
              <path d="M5 4h9l5 5v11H5z" />
              <path d="M8 12h8M8 16h5" />
            </svg>
          </span>
        </template>
        <template v-else>{{ row.value || '—' }}</template>
      </dd>
    </div>
  </dl>
</template>

<style scoped>
.shop-details {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 24px;
  margin: 15px 0 0;
  padding: 10px 22px;
  border: 1px solid #dce0e7;
  border-radius: 15px;
  background: #ffffff;
  font-size: 13px;
}

.shop-details__row {
  display: grid;
  grid-template-columns: minmax(98px, 42%) minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  min-height: 54px;
  padding: 10px 0;
  border-bottom: 1px solid #dce0e7;
}

.shop-details__row:nth-last-child(-n + 2) {
  border-bottom: 0;
}

.shop-details__label {
  color: #5a6373;
}

.shop-details__req {
  color: #bd113b;
}

.shop-details__value {
  margin: 0;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.shop-details__doc-type {
  display: block;
}

.shop-details__thumb {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border: 1px solid #dce0e7;
  border-radius: 8px;
  background: #fff5f7;
  color: #bd113b;
  object-fit: cover;
}

.shop-details__thumb--doc {
  width: 70px;
  height: 44px;
  margin-top: 5px;
  background: #f5f6f8;
  color: #5a6373;
}

/* 手机版：设计稿 `待审核-手机版.html` 为单列（.details 折成单列），
   行内仍是 label 42% / value 两栏；只有最后一行不画线。 */
.shop-details--mobile {
  grid-template-columns: minmax(0, 1fr);
  padding-inline: 14px;
}

.shop-details--mobile .shop-details__row:nth-last-child(2) {
  border-bottom: 1px solid #dce0e7;
}

@media (max-width: 590px) {
  .shop-details {
    grid-template-columns: minmax(0, 1fr);
    padding-inline: 14px;
  }

  .shop-details .shop-details__row:nth-last-child(2) {
    border-bottom: 1px solid #dce0e7;
  }
}
</style>
