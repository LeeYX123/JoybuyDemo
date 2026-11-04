import { describe, expect, it, vi } from 'vitest'

vi.mock('@/composables/useStaffAuth', () => ({
  useStaffAuth: vi.fn(() => ({
    isAuthenticated: ref(false),
    loaded: ref(false),
    loadSession: vi.fn(async () => ({})),
  })),
}))

import { ref } from 'vue'

describe('router guard', () => {
  it('redirects unauthenticated staff to login', async () => {
    const router = (await import('./index.js')).default
    await router.push('/some-protected-page')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('login')
  })
})
