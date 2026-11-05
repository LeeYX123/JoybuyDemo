<script setup>
import { computed } from 'vue'

// 状态 → 文案与色调的唯一映射表，避免每个页面各写一份。
const MAP = {
  // 店铺
  DRAFT: ['草稿', ''],
  PENDING_REVIEW: ['待审核', 'warn'],
  PENDING_DEPOSIT: ['待缴保证金', 'warn'],
  ACTIVE: ['接单中', 'ok'],
  REJECTED: ['已驳回', 'danger'],
  SUSPENDED: ['已封店', 'danger'],
  // 商品池
  INACTIVE: ['已下架', ''],
  // 上架关系
  LISTED: ['已上架', 'ok'],
  REMOVED: ['已下架', ''],
  // 订单
  PENDING: ['待处理', 'warn'],
  SHIPPED: ['已发货', 'info'],
  COMPLETED: ['已完成', 'ok'],
  // 提现
  APPROVED: ['审核通过', 'info'],
  TRANSFERRING: ['转账中', 'info'],
  FAILED: ['转账失败', 'danger'],
  PAID: ['已到账', 'ok'],
  // 售后
  PROCESSING: ['处理中', 'info'],
  PLATFORM: ['平台介入中', 'warn'],
  // 活动
  ONGOING: ['进行中', 'ok'],
  ENDED: ['已结束', ''],
  // 返佣
  PENDING_CALC: ['待核算', 'warn'],
  PENDING_PAY: ['待发放', 'warn'],
  // 资金类型
  RECHARGE: ['充值入账', 'ok'],
  WITHDRAWAL: ['提现申请', 'warn'],
  ORDER_SHIPPING: ['订单发货', ''],
  ORDER_SETTLEMENT: ['订单回款', 'ok'],
  REFERRAL_COMMISSION: ['推荐返佣', 'info'],
  ADJUSTMENT: ['余额调整', ''],
  // 保证金记录
  INITIAL: ['首次缴纳', 'info'],
}

const props = defineProps({
  value: { type: String, default: '' },
  labels: { type: Object, default: () => ({}) },
})

const entry = computed(() => {
  if (props.labels[props.value]) return [props.labels[props.value], '']
  return MAP[props.value] || [props.value || '—', '']
})
</script>

<template>
  <span class="tag" :class="entry[1] ? `tag--${entry[1]}` : ''">{{ entry[0] }}</span>
</template>
