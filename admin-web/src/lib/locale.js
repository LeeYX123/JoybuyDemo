const VALUE_LABELS = {
  ACTIVE: '启用',
  APPROVED: '已批准',
  ARCHIVED: '已归档',
  CANCELED: '已取消',
  CLEARED: '已清除',
  DELETED: '已删除',
  DISABLED: '已停用',
  DRAFT: '草稿',
  COMPLETED: '已完成',
  ERROR: '错误',
  EXPIRED: '已过期',
  FAILED: '失败',
  FULL_REFRESH: '全量刷新',
  HIDDEN: '已隐藏',
  INCREMENTAL: '增量同步',
  INFO: '信息',
  LOGIN_PENDING: '等待人工登录',
  CHECK_FAILED: '检查未通过',
  PAUSED: '已暂停',
  PAUSED_RISK_CONTROL: '风控暂停',
  SUCCEEDED: '成功',
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
  UNKNOWN: '未知',
  VALID: '会话有效',
  WARNING: '警告',
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
  login: '登录',
  logout: '清除会话',
  verify: '验证会话',
  reactivate: '解除风控',
  resume: '继续',
  start: '启动',
}

// 运行日志的事件级别与事件码（后端事件码保持英文常量，前端只做中文展示；
// 原始事件码留在 title 里，方便按码检索日志）。
const EVENT_CODE_LABELS = {
  ACCOUNT_FALLBACK: '指定账号不可用，已回退',
  ACCOUNT_POOL_EMPTY: '无可用账号（匿名抓取）',
  ACCOUNT_POOL_EXHAUSTED: '账号池已耗尽',
  ACCOUNT_POOL_READY: '账号池就绪',
  ACCOUNT_RISK_ROTATED: '命中风控，已换号',
  ACCOUNT_ROTATED: '已换号',
  DATASET_SAVED: '已落盘',
  DATASET_SUMMARY: '数据集汇总',
  DATASET_WRITE_FAILED: '数据集写入失败',
  DETAIL_FIELDS_MISSING: '详情页字段缺失',
  DETAIL_PARSE_FAILED: '详情页解析失败',
  IMPORT_FAILED: '导入失败',
  IMPORT_REJECTED: '导入被拒',
  LISTING_CARDS_REJECTED: '非商品卡片被丢弃',
  LISTING_FETCHED: '列表页已获取',
  LISTING_PARSE_FAILED: '列表页解析失败',
  LISTING_SHORTFALL: '列表页商品数不足',
  LOGIN_WALL_FALLBACK: '登录墙回退',
  PRICE_ANOMALY_MISSING: '价格异常：取不到价格',
  PRICE_ANOMALY_UNIFORM: '价格异常：价格全部相同',
  PRODUCT_IMPORTED: '商品已入库',
  PRODUCT_PARSED: '详情页已解析',
  RECORD_FLAGGED: '记录告警（已放行）',
  RECORD_REJECTED: '记录被拒（未入库）',
  RENDERED_OK: '浏览器渲染成功',
  RENDER_FAILED: '浏览器渲染失败',
  RISK_CONTROL_FALLBACK: '风控页回退',
  RUN_FAILED: '运行失败',
  RUN_ACCOUNT_SELECTED: '本轮使用账号',
  RUN_STARTED: '运行开始',
  RUN_UNAUTHENTICATED: '未登录状态启动',
  STAGING_FAILED: '暂存失败',
}

export function eventCodeLabel(code) {
  return EVENT_CODE_LABELS[code] || code || ''
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
