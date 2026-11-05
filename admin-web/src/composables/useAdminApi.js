import { apiRequest } from '@/lib/api'
import { useStaffAuth } from '@/composables/useStaffAuth'

// Admin write helper: attaches the session CSRF token to every mutation.
// Throws ApiError on failure so views can surface error.message.
export async function adminWrite(path, body, method = 'POST') {
  const { session } = useStaffAuth()
  return apiRequest(path, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': session.value.csrf_token || '',
    },
    body: JSON.stringify(body ?? {}),
  })
}

// 图片上传：multipart 表单。
// 注意不能手动设 Content-Type —— 浏览器要自己补 boundary，设了反而解析失败。
export async function adminUpload(file, purpose) {
  const { session } = useStaffAuth()
  const form = new FormData()
  form.append('file', file)
  form.append('purpose', purpose)
  return apiRequest('/media', {
    method: 'POST',
    headers: { 'X-CSRFToken': session.value.csrf_token || '' },
    body: form,
  })
}

// Small fetch wrapper for GET list endpoints that must not throw on empty.
export async function adminGet(path) {
  try {
    return await apiRequest(path)
  } catch (error) {
    return { error: { code: error.code, message: error.message }, items: [] }
  }
}
