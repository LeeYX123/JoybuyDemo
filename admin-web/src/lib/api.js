import { uuidv4 } from './uuid.js'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1/admin'

// 迭代02：三端时间展示按"看的人所在时区"——请求头携带浏览器 IANA 时区，
// 后端序列化时间时据此转换（只影响展示，不改业务逻辑）。
function clientTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || ''
  } catch {
    return ''
  }
}

const API_ERROR_MESSAGES = {
  ACTION_FAILED: '操作失败，请检查当前状态后重试。',
  ACTION_INVALID: '不支持该操作。',
  ADJUSTMENT_INVALID: '库存调整无效，请检查数量和原因。',
  BALANCE_NEGATIVE: '余额不能为负。',
  BUYER_IDENTIFIER_REQUIRED: '邮箱和手机号至少保留一项，否则该账号将无法登录。',
  BUYER_NOT_FOUND: '未找到该买家账号。',
  BUYER_STATUS_INVALID: '状态只能是启用或停用。',
  CATEGORY_NOT_FOUND: '未找到该来源类目。',
  DELTA_INVALID: '库存增减数量必须是整数。',
  DISPLAY_NAME_TOO_LONG: '用户名不能超过 32 个字符。',
  EMAIL_INVALID: '邮箱格式不正确。',
  EMAIL_TAKEN: '该邮箱已被其他账号使用。',
  JOB_INVALID: '爬取任务参数无效。',
  JOB_NOT_FOUND: '未找到该爬取任务。',
  OFFER_NOT_FOUND: '未找到该销售报价。',
  PAGE_INVALID: '页面模块数据无效。',
  PARAMS_MISSING: '请填写所有必填项。',
  PASSWORD_TOO_LONG: '密码不能超过 64 位。',
  PASSWORD_TOO_SHORT: '密码至少 8 位。',
  PHONE_INVALID: '手机号必须是国际格式（含国家码，如 +447700900123）。',
  PHONE_TAKEN: '该手机号已被其他账号使用。',
  PRODUCT_NOT_FOUND: '未找到该商品。',
  REASON_REQUIRED: '请填写操作原因。',
  REVIEW_NOT_FOUND: '未找到该评价。',
  RUN_NOT_FOUND: '未找到可操作的运行记录。',
  STAFF_AUTH_REQUIRED: '登录状态已过期，请重新登录。',
  STAFF_FORBIDDEN: '当前账号无权执行该操作。',
}

function localizedErrorMessage(code, status, serverMessage) {
  // 后端给了明确的中文业务提示（如余额不足、规格失效）优先直接展示，
  // 只有通用/空提示时才回退到本地映射与默认文案。
  const generic = !serverMessage || serverMessage === 'The request could not be processed.'
  if (!generic) return serverMessage
  if (API_ERROR_MESSAGES[code]) return API_ERROR_MESSAGES[code]
  if (status === 403) return '当前账号无权执行该操作。'
  if (status === 404) return '未找到请求的数据。'
  return '请求失败，请稍后重试。'
}

export class ApiError extends Error {
  constructor(
    message,
    { status = 0, code = 'NETWORK_ERROR', requestId = null, details = null } = {},
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.requestId = requestId
    this.details = details
  }
}

export async function apiRequest(path, options = {}) {
  const requestId = uuidv4()
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'X-Request-ID': requestId,
      'X-Client-Timezone': clientTimezone(),
      ...options.headers,
    },
  }).catch(() => {
    throw new ApiError('网络请求失败，请检查连接后重试。', { requestId })
  })

  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json') ? await response.json() : null

  if (!response.ok) {
    const code = payload?.error?.code || 'API_ERROR'
    throw new ApiError(localizedErrorMessage(code, response.status, payload?.error?.message), {
      status: response.status,
      code,
      requestId: payload?.request_id || response.headers.get('X-Request-ID') || requestId,
      details: payload?.error?.details || null,
    })
  }

  return payload
}
