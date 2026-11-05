const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

const MESSAGES = {
  MERCHANT_AUTH_REQUIRED: '登录状态已过期，请重新登录。',
  MERCHANT_MEMBERSHIP_REQUIRED: '该账号未绑定任何店铺，请联系平台客服。',
  MERCHANT_CONTEXT_REQUIRED: '你属于多家店铺，请先在顶部选择要操作的店铺。',
  MERCHANT_NOT_ACCESSIBLE: '无权访问该店铺。',
  MERCHANT_PERMISSION_DENIED: '当前店铺角色无权执行该操作。',
  STAFF_AUTH_REQUIRED: '登录状态已过期，请重新登录。',
  INVALID_STAFF_CREDENTIALS: '邮箱或密码不正确。',
  STAFF_ACCOUNT_DISABLED: '该账号已被停用。',
}

export class ApiError extends Error {
  constructor(message, { status = 0, code = 'NETWORK_ERROR', requestId = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.requestId = requestId
  }
}

// 当前选中的店铺，由 useMerchantSession 维护；请求时以头部显式带上。
let currentShopId = ''

export function setCurrentShop(id) {
  currentShopId = id || ''
}

export function getCurrentShop() {
  return currentShopId
}

export async function apiRequest(path, options = {}) {
  const requestId = crypto.randomUUID()
  const headers = {
    Accept: 'application/json',
    'X-Request-ID': requestId,
    ...options.headers,
  }
  if (currentShopId) headers['X-Merchant-Id'] = currentShopId

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: 'include',
    headers,
  }).catch(() => {
    throw new ApiError('网络请求失败，请检查连接后重试。', { requestId })
  })

  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json') ? await response.json() : null

  if (!response.ok) {
    const code = payload?.error?.code || 'API_ERROR'
    const message =
      MESSAGES[code] || payload?.error?.message || `请求失败（${response.status}），请稍后重试。`
    throw new ApiError(message, {
      status: response.status,
      code,
      requestId: payload?.request_id || requestId,
    })
  }

  return payload
}

// 商家端写操作：/merchant/* 走同一套员工会话，CSRF 头不能少。
export async function merchantWrite(path, body, method = 'POST') {
  const session = await apiRequest('/admin/auth/session')
  return apiRequest(path, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': session.csrf_token || '',
    },
    body: JSON.stringify(body ?? {}),
  })
}

// 图片上传：multipart 表单。
// 不能手动设 Content-Type —— 浏览器要自己补 boundary，设了后端就解析不出文件。
export async function merchantUpload(file, purpose) {
  const session = await apiRequest('/admin/auth/session')
  const form = new FormData()
  form.append('file', file)
  form.append('purpose', purpose)
  return apiRequest('/merchant/media', {
    method: 'POST',
    headers: { 'X-CSRFToken': session.csrf_token || '' },
    body: form,
  })
}
