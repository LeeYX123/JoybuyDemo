import { computed, ref } from 'vue'

import { apiRequest } from '@/lib/api'

// Staff session state backed by WP-06 cookie sessions (email + password login).
const session = ref({ authenticated: false, staff: null, permissions: [] })
const loaded = ref(false)

export function useStaffAuth() {
  const isAuthenticated = computed(() => session.value.authenticated)
  const staff = computed(() => session.value.staff)
  const permissions = computed(() => new Set(session.value.staff?.permissions || []))

  async function loadSession() {
    try {
      session.value = await apiRequest('/auth/session')
    } catch {
      session.value = { authenticated: false, staff: null, permissions: [] }
    }
    loaded.value = true
    return session.value
  }

  async function login(email, password) {
    // The login page is a public route, so the guard never loaded a session;
    // load it first to set the csrftoken cookie and obtain the CSRF token
    // (WP-06 requires CSRF on all admin writes).
    const fresh = await loadSession()
    const response = await apiRequest('/auth/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': fresh.csrf_token || '',
      },
      body: JSON.stringify({ email, password }),
    })
    await loadSession()
    return response
  }

  async function logout() {
    try {
      await apiRequest('/auth/logout', {
        method: 'POST',
        headers: { 'X-CSRFToken': session.value.csrf_token || '' },
      })
    } finally {
      session.value = { authenticated: false, staff: null, permissions: [] }
    }
  }

  function hasPermission(code) {
    return permissions.value.has(code)
  }

  return {
    session,
    isAuthenticated,
    staff,
    permissions,
    loaded,
    loadSession,
    login,
    logout,
    hasPermission,
  }
}
