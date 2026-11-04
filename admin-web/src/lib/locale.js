const VALUE_LABELS = {
  ACTIVE: '启用',
  APPROVED: '已批准',
  ARCHIVED: '已归档',
  CANCELED: '已取消',
  CLEARED: '已清除',
  DELETED: '已删除',
  DISABLED: '已停用',
  DRAFT: '草稿',
  FAILED: '失败',
  FULL_REFRESH: '全量刷新',
  HIDDEN: '已隐藏',
  INCREMENTAL: '增量同步',
  PAUSED: '已暂停',
  PENDING: '待审核',
  PENDING_PAYMENT: '待支付',
  PUBLISHED: '已发布',
  READY: '就绪',
  REJECTED: '已驳回',
  RUNNING: '运行中',
  SENT: '已发送',
  SOURCE_DEFAULT: '来源默认排序',
  BEST_SELLING: '销量优先',
  TOP_RATED: '评分优先',
  NEWEST: '最新优先',
  RANDOM: '随机排序',
  source: '来源值',
  local: '本地覆盖值',
  none: '无',
  home: '首页',
  GBP: '英镑',
}

const FIELD_LABELS = {
  title: '标题',
  subtitle: '副标题',
  description: '商品详情',
  promotion_label: '促销标签',
}

const ACTION_LABELS = {
  approve: '批准',
  cancel: '取消',
  clear: '清除',
  disable: '停用',
  enable: '启用',
  pause: '暂停',
  propose: '提议修改',
  reject: '驳回',
  requeue: '重新入队',
  resume: '继续',
  start: '启动',
}

export function valueLabel(value) {
  if (value === true) return '是'
  if (value === false) return '否'
  if (value === null || value === undefined || value === '') return '—'
  return VALUE_LABELS[value] || String(value)
}

export function fieldLabel(field) {
  return FIELD_LABELS[field] || field
}

export function actionLabel(action) {
  return ACTION_LABELS[action] || action
}
