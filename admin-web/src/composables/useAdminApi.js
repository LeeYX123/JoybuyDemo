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

import { apiRequest } from '@/lib/api'

// Small fetch wrapper for GET list endpoints that must not throw on empty.
export async function adminGet(path) {
  try {
    return await apiRequest(path)
  } catch (error) {
    return { error: { code: error.code, message: error.message }, items: [] }
  }
}
