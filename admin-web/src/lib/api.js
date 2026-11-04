const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1/admin'

const API_ERROR_MESSAGES = {
  ACTION_FAILED: '操作失败，请检查当前状态后重试。',
  ACTION_INVALID: '不支持该操作。',
  ADJUSTMENT_INVALID: '库存调整无效，请检查数量和原因。',
  BUYER_NOT_FOUND: '未找到该买家账号。',
  CATEGORY_NOT_FOUND: '未找到该来源类目。',
  DELTA_INVALID: '库存增减数量必须是整数。',
  JOB_INVALID: '爬取任务参数无效。',
  JOB_NOT_FOUND: '未找到该爬取任务。',
  OFFER_NOT_FOUND: '未找到该销售报价。',
  PAGE_INVALID: '页面模块数据无效。',
  PARAMS_MISSING: '请填写所有必填项。',
  PRODUCT_NOT_FOUND: '未找到该商品。',
  REASON_REQUIRED: '请填写操作原因。',
  REVIEW_NOT_FOUND: '未找到该评价。',
  RUN_NOT_FOUND: '未找到可操作的运行记录。',
  STAFF_AUTH_REQUIRED: '登录状态已过期，请重新登录。',
  STAFF_FORBIDDEN: '当前账号无权执行该操作。',
}

function localizedErrorMessage(code, status) {
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
  const requestId = crypto.randomUUID()
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'X-Request-ID': requestId,
      ...options.headers,
    },
  }).catch(() => {
    throw new ApiError('网络请求失败，请检查连接后重试。', { requestId })
  })

  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json') ? await response.json() : null

  if (!response.ok) {
    const code = payload?.error?.code || 'API_ERROR'
    throw new ApiError(localizedErrorMessage(code, response.status), {
      status: response.status,
      code,
      requestId: payload?.request_id || response.headers.get('X-Request-ID') || requestId,
      details: payload?.error?.details || null,
    })
  }

  return payload
}
